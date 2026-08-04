"""FastAPI server for the Aureum web dashboard.

Run locally with:
    pip install -e "bindings/python[web]"
    cd bindings/python
    uvicorn aureum.server:app --reload --port 8000

The frontend (frontend/web) proxies /api to this server in dev and uses the
API_URL env var in production.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from aureum import __version__
from aureum.ai import DEFAULT_MODEL
from aureum.author import StrategyAuthor
from aureum.backtest import _SIGNALS, BacktestRunner, MarketData
from aureum.certificate import get_environment
from aureum.execution import (
    AlpacaPaperExecutionBackend,
    LiveRunner,
    LiveTradingConfig,
)
from aureum.reflector import StrategyReflector
from aureum.strategy import Strategy
from aureum.trading import AlpacaTradingAdapter

app = FastAPI(
    title="Aureum",
    description="Web API for the Aureum self-proving semantic kernel.",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve the repository examples directory from this file's location.
_REPO_ROOT = Path(__file__).parents[3]
_EXAMPLES_DIR = _REPO_ROOT / "examples"
_STRATEGIES_DIR = _EXAMPLES_DIR / "strategies"
_DATA_DIR = _EXAMPLES_DIR / "data"


class AuthorRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_MODEL
    max_correction_attempts: int = 2


class AuthorResponse(BaseModel):
    yaml: str
    rationale: str


class BacktestRequest(BaseModel):
    strategy_yaml: str
    data_path: str


class LiveRequest(BaseModel):
    strategy_yaml: str
    data_path: str
    dry_run: bool = True
    check_only: bool = False
    submit_orders: bool = False
    ignore_market_hours: bool = False
    max_single_position_pct: float | None = None
    max_total_invested_pct: float | None = None
    min_order_notional: float | None = None


class ReflectRequest(BaseModel):
    strategy_yaml: str
    data_path: str
    model: str = DEFAULT_MODEL
    max_attempts: int = 3


class ReflectResponse(BaseModel):
    success: bool
    attempts: int
    yaml: str | None = None
    certificate: dict[str, Any] | None = None
    drafts: list[str] = Field(default_factory=list)


def _data_path(name: str) -> Path:
    """Resolve a data file path relative to cwd, repo root, or examples/data."""
    path = Path(name)
    if path.exists():
        return path
    repo_relative = _REPO_ROOT / name
    if repo_relative.exists():
        return repo_relative
    data_relative = _DATA_DIR / name
    if data_relative.exists():
        return data_relative
    raise HTTPException(status_code=404, detail=f"Data file not found: {name}")


@app.get("/api/signals")
def list_signals() -> list[str]:
    return sorted(_SIGNALS)


@app.get("/api/examples")
def list_examples() -> list[dict[str, str]]:
    out = []
    if _STRATEGIES_DIR.exists():
        for path in sorted(_STRATEGIES_DIR.glob("*.yaml")):
            out.append(
                {
                    "name": path.stem,
                    "path": str(path.relative_to(_REPO_ROOT)),
                    "content": path.read_text(encoding="utf-8"),
                }
            )
    return out


@app.get("/api/data")
def list_data() -> list[dict[str, str]]:
    out = []
    if _DATA_DIR.exists():
        for path in sorted(_DATA_DIR.glob("*.csv")):
            out.append(
                {
                    "name": path.name,
                    "path": str(path.relative_to(_REPO_ROOT)),
                }
            )
    return out


@app.post("/api/author")
def author(request: AuthorRequest) -> AuthorResponse:
    try:
        author_ = StrategyAuthor(model=request.model)
        yaml_text, rationale = author_.from_prompt(
            request.prompt,
            max_correction_attempts=request.max_correction_attempts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AuthorResponse(yaml=yaml_text, rationale=rationale)


@app.post("/api/backtest")
def backtest(request: BacktestRequest) -> dict[str, Any]:
    try:
        strategy = Strategy.from_yaml(request.strategy_yaml)
        data_path = _data_path(request.data_path)
        # Materialise YAML so the certificate can hash the exact strategy file.
        tmp_strategy = data_path.parent / ".backtest-in.yaml"
        tmp_strategy.write_text(request.strategy_yaml, encoding="utf-8")
        data = MarketData.from_csv(data_path)
        runner = BacktestRunner(
            strategy, data, data_source=str(data_path)
        )
        env = get_environment(aureum_version=__version__, cwd=data_path.parent)
        cert = runner.build_certificate(
            strategy_path=tmp_strategy,
            data_path=data_path,
            environment=env,
        )
        return cert.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/live")
def live(request: LiveRequest) -> dict[str, Any]:
    try:
        strategy = Strategy.from_yaml(request.strategy_yaml)
        data_path = _data_path(request.data_path)
        tmp_strategy = _DATA_DIR / ".live-in.yaml"
        tmp_strategy.write_text(request.strategy_yaml, encoding="utf-8")
        data = MarketData.from_csv(data_path)

        overrides: dict[str, float] = {}
        if request.max_single_position_pct is not None:
            overrides["max_single_position_pct"] = request.max_single_position_pct
        if request.max_total_invested_pct is not None:
            overrides["max_total_invested_pct"] = request.max_total_invested_pct
        if request.min_order_notional is not None:
            overrides["min_order_notional"] = request.min_order_notional

        config = LiveTradingConfig.from_strategy_spec(strategy.spec, overrides=overrides)
        # Safety: submit_orders overrides dry_run. Never submit orders when the
        # market is closed unless explicitly requested.
        config.dry_run = not request.submit_orders
        config.market_open_required = not request.ignore_market_hours
        config.paper = True

        adapter = AlpacaTradingAdapter(
            paper=True,
            market_open_required=not request.ignore_market_hours,
        )
        backend = AlpacaPaperExecutionBackend(adapter, config)
        runner = LiveRunner(
            strategy=strategy,
            data=data,
            data_source=str(data_path),
            strategy_path=tmp_strategy,
            backend=backend,
        )
        cert = runner.run(
            check_only=request.check_only,
            dry_run=not request.submit_orders,
        )
        return cert.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/reflect")
def reflect(request: ReflectRequest) -> ReflectResponse:
    try:
        data_path = _data_path(request.data_path)
        # Materialise the incoming YAML to a temp file so the reflector can
        # compute lineage hashes and write drafts.
        tmp_strategy = _DATA_DIR / ".reflect-in.yaml"
        tmp_strategy.write_text(request.strategy_yaml, encoding="utf-8")
        out_path = _DATA_DIR / ".reflect-out.yaml"
        reflector = StrategyReflector(model=request.model)
        result = reflector.reflect(
            tmp_strategy,
            data_path,
            output_path=out_path,
            max_attempts=request.max_attempts,
        )
        return ReflectResponse(
            success=result.success,
            attempts=result.attempts,
            yaml=out_path.read_text(encoding="utf-8") if result.success else None,
            certificate=result.final_certificate.to_dict()
            if result.final_certificate
            else None,
            drafts=[str(d) for d in result.drafts],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}

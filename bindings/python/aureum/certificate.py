"""Aureum Backtest Certificate (ABC) — structured audit artifact for a backtest run.

A certificate is a JSON-serializable artifact that captures:
- the environment in which the backtest ran (tool versions, git commit);
- the content-addressed inputs (strategy YAML, data CSV);
- a summary of execution and results;
- static risk-constraint compliance checks;
- a tamper-evident input hash and a result hash for reproducibility validation.

In Phase 1 the certificate is evidence, not a cryptographic proof or regulatory
artifact.  A validator script can re-run the bundled inputs and confirm the
reported metrics match within a deterministic tolerance.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aureum.econsec import EconomicSecurityReport
from aureum.graph import KnowledgeGraph


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's raw bytes."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_json(obj: Any) -> str:
    """Serialize an object to a stable, sorted JSON string for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class Environment:
    """Runtime environment captured for reproducibility."""

    aureum_version: str
    git_commit: str
    git_dirty: bool
    python_version: str
    platform: str
    dependencies_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "aureum_version": self.aureum_version,
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "python_version": self.python_version,
            "platform": self.platform,
            "dependencies_digest": self.dependencies_digest,
        }


@dataclass
class InputLineage:
    """Content-addressed description of one input file."""

    path: str
    sha256: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "metadata": self.metadata,
        }


@dataclass
class Inputs:
    """All inputs that produced a backtest result."""

    strategy: InputLineage
    data: InputLineage

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.to_dict(),
            "data": self.data.to_dict(),
        }


@dataclass
class ExecutionSummary:
    """High-level execution metadata."""

    start_date: str
    end_date: str
    initial_nav: float
    rebalance_count: int
    trades: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_nav": round(self.initial_nav, 4),
            "rebalance_count": self.rebalance_count,
            "trades": self.trades,
        }


@dataclass
class Results:
    """Performance and risk metrics from the backtest."""

    final_nav: float
    total_return: float
    cagr: float
    volatility_annual: float
    sharpe_ratio: float | None
    max_drawdown: float
    turnover_annual: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_nav": round(self.final_nav, 4),
            "total_return": round(self.total_return, 6),
            "cagr": round(self.cagr, 6),
            "volatility_annual": round(self.volatility_annual, 6),
            "sharpe_ratio": round(self.sharpe_ratio, 4)
            if self.sharpe_ratio is not None
            else None,
            "max_drawdown": round(self.max_drawdown, 6),
            "turnover_annual": round(self.turnover_annual, 6),
        }


@dataclass
class Determinism:
    """Reproducibility claim and tolerance."""

    input_hash: str
    result_hash: str
    tolerance: str = "1e-6 relative + 1e-9 absolute"
    economic_security_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = {
            "input_hash": self.input_hash,
            "result_hash": self.result_hash,
            "tolerance": self.tolerance,
        }
        if self.economic_security_hash:
            out["economic_security_hash"] = self.economic_security_hash
        return out


@dataclass
class PortfolioConstruction:
    """Proof/evidence that a portfolio was built by a declared MPT optimizer.

    In Edge 1 this records the declared optimizer, its configuration, and the
    realized weights at each rebalance.  The ``frontier_hash`` field is reserved
    for a future hash of the full efficient frontier used to select the
    portfolio; it may be empty in this release.
    """

    objective: str
    risk_measure: str
    covariance_estimator: str
    risk_free_rate: float
    constraints: dict[str, Any]
    weights_history: list[dict[str, Any]]
    frontier_hash: str = ""
    optimization_inputs_hash: str = ""
    calibration_set_hash: str = ""
    coverage_level: float = 0.0
    prediction_set_width: float = 0.0
    causal_graph_hash: str = ""
    conditional_covariance_hash: str = ""
    model_architecture_hash: str = ""
    weights_hash: str = ""
    train_val_test_split_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "objective": self.objective,
            "risk_measure": self.risk_measure,
            "covariance_estimator": self.covariance_estimator,
            "risk_free_rate": self.risk_free_rate,
            "constraints": self.constraints,
            "weights_history": self.weights_history,
        }
        if self.frontier_hash:
            out["frontier_hash"] = self.frontier_hash
        if self.optimization_inputs_hash:
            out["optimization_inputs_hash"] = self.optimization_inputs_hash
        if self.calibration_set_hash:
            out["calibration_set_hash"] = self.calibration_set_hash
        if self.coverage_level:
            out["coverage_level"] = self.coverage_level
        if self.prediction_set_width:
            out["prediction_set_width"] = self.prediction_set_width
        if self.causal_graph_hash:
            out["causal_graph_hash"] = self.causal_graph_hash
        if self.conditional_covariance_hash:
            out["conditional_covariance_hash"] = self.conditional_covariance_hash
        if self.model_architecture_hash:
            out["model_architecture_hash"] = self.model_architecture_hash
        if self.weights_hash:
            out["weights_hash"] = self.weights_hash
        if self.train_val_test_split_hashes:
            out["train_val_test_split_hashes"] = self.train_val_test_split_hashes
        return out


@dataclass
class AlphaLineage:
    """Lineage for neuro-symbolic alpha signals used in a backtest."""

    alpha_signals: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"alpha_signals": self.alpha_signals}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlphaLineage":
        return cls(alpha_signals=data.get("alpha_signals", []))


@dataclass
class BacktestCertificate:
    """Structured, machine-checkable audit artifact for a single backtest run."""

    aureum_version: str
    certificate_spec_version: str
    generated_at: str
    environment: Environment
    inputs: Inputs
    execution: ExecutionSummary
    results: Results
    risk_constraints: list[dict[str, Any]]
    execution_trace: dict[str, Any]
    determinism: Determinism
    portfolio_construction: PortfolioConstruction | None = None
    economic_security: EconomicSecurityReport | None = None
    # Edge 5 — semantic knowledge graph lineage.
    graph_node_id: str | None = None
    linked_entity_hashes: list[str] = field(default_factory=list)
    knowledge_graph: KnowledgeGraph | None = None
    alpha_lineage: AlphaLineage | None = None

    @classmethod
    def from_run(
        cls,
        *,
        environment: Environment,
        inputs: Inputs,
        execution: ExecutionSummary,
        results: Results,
        risk_constraints: list[dict[str, Any]],
        execution_trace: dict[str, Any],
        portfolio_construction: PortfolioConstruction | None = None,
        economic_security: EconomicSecurityReport | None = None,
        graph_node_id: str | None = None,
        linked_entity_hashes: list[str] | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
        alpha_lineage: AlphaLineage | None = None,
    ) -> BacktestCertificate:
        """Build a certificate from the raw parts of a backtest run."""
        input_hash = _sha256_text(_stable_json(inputs.to_dict()))
        result_hash = _sha256_text(_stable_json(results.to_dict()))
        determinism = Determinism(
            input_hash=input_hash, result_hash=result_hash
        )
        if economic_security is not None and economic_security.enabled:
            determinism.economic_security_hash = _sha256_text(
                _stable_json(economic_security.to_dict())
            )
        return cls(
            aureum_version=environment.aureum_version,
            certificate_spec_version="1.0",
            generated_at=dt.datetime.now(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            environment=environment,
            inputs=inputs,
            execution=execution,
            results=results,
            risk_constraints=risk_constraints,
            execution_trace=execution_trace,
            determinism=determinism,
            portfolio_construction=portfolio_construction,
            economic_security=economic_security,
            graph_node_id=graph_node_id,
            linked_entity_hashes=list(linked_entity_hashes) if linked_entity_hashes else [],
            knowledge_graph=knowledge_graph,
            alpha_lineage=alpha_lineage,
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "aureum_version": self.aureum_version,
            "certificate_spec_version": self.certificate_spec_version,
            "generated_at": self.generated_at,
            "environment": self.environment.to_dict(),
            "inputs": self.inputs.to_dict(),
            "execution": self.execution.to_dict(),
            "results": self.results.to_dict(),
            "risk_constraints": self.risk_constraints,
            "execution_trace": self.execution_trace,
            "determinism": self.determinism.to_dict(),
        }
        if self.portfolio_construction is not None:
            out["portfolio_construction"] = self.portfolio_construction.to_dict()
        if self.economic_security is not None:
            out["economic_security"] = self.economic_security.to_dict()
        if self.graph_node_id is not None:
            out["graph_node_id"] = self.graph_node_id
        if self.linked_entity_hashes:
            out["linked_entity_hashes"] = self.linked_entity_hashes
        if self.knowledge_graph is not None:
            out["knowledge_graph"] = self.knowledge_graph.to_dict()
        if self.alpha_lineage is not None:
            out["alpha_lineage"] = self.alpha_lineage.to_dict()
        return out

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BacktestCertificate":
        """Reconstruct a BacktestCertificate from a plain dictionary."""
        env = data["environment"]
        inputs = data["inputs"]
        execution = data["execution"]
        results = data["results"]
        determinism = data["determinism"]

        portfolio_construction = None
        economic_security = None
        knowledge_graph = None
        if "knowledge_graph" in data:
            knowledge_graph = KnowledgeGraph.from_dict(data["knowledge_graph"])
        if "portfolio_construction" in data:
            pc = data["portfolio_construction"]
            portfolio_construction = PortfolioConstruction(
                objective=pc["objective"],
                risk_measure=pc["risk_measure"],
                covariance_estimator=pc["covariance_estimator"],
                risk_free_rate=pc["risk_free_rate"],
                constraints=pc.get("constraints", {}),
                weights_history=pc.get("weights_history", []),
                frontier_hash=pc.get("frontier_hash", ""),
                optimization_inputs_hash=pc.get("optimization_inputs_hash", ""),
                calibration_set_hash=pc.get("calibration_set_hash", ""),
                coverage_level=pc.get("coverage_level", 0.0),
                prediction_set_width=pc.get("prediction_set_width", 0.0),
                causal_graph_hash=pc.get("causal_graph_hash", ""),
                conditional_covariance_hash=pc.get("conditional_covariance_hash", ""),
                model_architecture_hash=pc.get("model_architecture_hash", ""),
                weights_hash=pc.get("weights_hash", ""),
                train_val_test_split_hashes=pc.get("train_val_test_split_hashes", {}),
            )
        if "economic_security" in data:
            economic_security = EconomicSecurityReport.from_dict(
                data["economic_security"]
            )

        alpha_lineage = None
        if "alpha_lineage" in data:
            alpha_lineage = AlphaLineage.from_dict(data["alpha_lineage"])

        knowledge_graph = None
        if "knowledge_graph" in data:
            knowledge_graph = KnowledgeGraph.from_dict(data["knowledge_graph"])

        return cls(
            aureum_version=data["aureum_version"],
            certificate_spec_version=data["certificate_spec_version"],
            generated_at=data["generated_at"],
            environment=Environment(
                aureum_version=env["aureum_version"],
                git_commit=env["git_commit"],
                git_dirty=env["git_dirty"],
                python_version=env["python_version"],
                platform=env["platform"],
                dependencies_digest=env.get("dependencies_digest", ""),
            ),
            inputs=Inputs(
                strategy=InputLineage(
                    path=inputs["strategy"]["path"],
                    sha256=inputs["strategy"]["sha256"],
                    metadata=inputs["strategy"].get("metadata", {}),
                ),
                data=InputLineage(
                    path=inputs["data"]["path"],
                    sha256=inputs["data"]["sha256"],
                    metadata=inputs["data"].get("metadata", {}),
                ),
            ),
            execution=ExecutionSummary(
                start_date=execution["start_date"],
                end_date=execution["end_date"],
                initial_nav=execution["initial_nav"],
                rebalance_count=execution["rebalance_count"],
                trades=execution["trades"],
            ),
            results=Results(
                final_nav=results["final_nav"],
                total_return=results["total_return"],
                cagr=results["cagr"],
                volatility_annual=results["volatility_annual"],
                sharpe_ratio=results.get("sharpe_ratio"),
                max_drawdown=results["max_drawdown"],
                turnover_annual=results["turnover_annual"],
            ),
            risk_constraints=data["risk_constraints"],
            execution_trace=data.get("execution_trace", {}),
            determinism=Determinism(
                input_hash=determinism["input_hash"],
                result_hash=determinism["result_hash"],
                tolerance=determinism.get("tolerance", "1e-6 relative + 1e-9 absolute"),
                economic_security_hash=determinism.get("economic_security_hash", ""),
            ),
            portfolio_construction=portfolio_construction,
            economic_security=economic_security,
            graph_node_id=data.get("graph_node_id"),
            linked_entity_hashes=list(data.get("linked_entity_hashes", [])),
            knowledge_graph=knowledge_graph,
            alpha_lineage=alpha_lineage,
        )

    def with_draft_lineage(self, draft_lineage: dict[str, Any]) -> "BacktestCertificate":
        """Return a new certificate with draft lineage injected into execution_trace."""
        new_trace = dict(self.execution_trace)
        new_trace["draft_lineage"] = draft_lineage
        return dataclasses.replace(self, execution_trace=new_trace)

    def with_strategy_path(self, path: str | Path) -> "BacktestCertificate":
        """Return a new certificate with the strategy input path rewritten.

        The strategy file content is assumed to be unchanged (e.g. the file was
        moved/copied), so its SHA-256 stays the same. The input hash is
        recomputed to reflect the new path.
        """
        new_inputs = dataclasses.replace(
            self.inputs,
            strategy=dataclasses.replace(
                self.inputs.strategy, path=str(Path(path))
            ),
        )
        new_input_hash = _sha256_text(_stable_json(new_inputs.to_dict()))
        new_determinism = dataclasses.replace(
            self.determinism, input_hash=new_input_hash
        )
        return dataclasses.replace(
            self, inputs=new_inputs, determinism=new_determinism
        )


def hash_file(path: str | Path) -> str:
    """Public helper for hashing input files."""
    return _sha256_file(Path(path))


def hash_text(text: str) -> str:
    """Public helper for hashing text inputs."""
    return _sha256_text(text)


def _git_commit(cwd: Path | None = None) -> tuple[str, bool]:
    """Return (commit_hash, dirty) for the current git repo, or ('unknown', False)."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        dirty = bool(status.stdout.strip())
        return commit, dirty
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", False


def _dependency_digest() -> str:
    """Best-effort digest of installed Python packages relevant to Aureum.

    Returns a hash of `pip freeze` output, or an empty string if unavailable.
    """
    try:
        freeze = subprocess.check_output(
            [sys.executable, "-m", "pip", "freeze"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return _sha256_text(freeze)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def get_environment(aureum_version: str, cwd: Path | None = None) -> Environment:
    """Capture the runtime environment for a certificate."""
    commit, dirty = _git_commit(cwd)
    return Environment(
        aureum_version=aureum_version,
        git_commit=commit,
        git_dirty=dirty,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.platform(),
        dependencies_digest=_dependency_digest(),
    )

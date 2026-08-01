"""Aureum CLI entry point."""

from __future__ import annotations

import json
import math
import tarfile
from pathlib import Path

import click
import yaml

from .adapter import AlpacaAdapter
from .alpha import AlphaMiner, safety_check
from .author import StrategyAuthor
from .backtest import BacktestRunner, MarketData
from .certificate import get_environment, hash_file
from .diffopt import DifferentiableSharpeOptimizer  # noqa: F401
from .mpt import OptimizationInputs, build_efficient_frontier, estimate_covariance, estimate_mean_returns
from .prover import Lean4Generator, SmtLibGenerator, extract_claims
from .reflector import StrategyReflector
from .strategy import Strategy
from aureum import __version__


@click.group()
@click.version_option(version=__version__)
def cli():
    """Aureum — self-proving semantic kernel for finance."""


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def validate(path: Path) -> None:
    """Validate a strategy YAML file."""
    strategy = Strategy.from_file(path)
    errors = strategy.validate()
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
        raise click.Abort()
    print(f"Strategy '{strategy.metadata['name']}' is valid.")


@cli.command("alpha")
@click.argument("prompt")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output YAML path for the emitted signals block",
)
@click.option("--model", default="claude-sonnet-5", help="Anthropic model name")
@click.option(
    "--validate-only",
    help="Run static safety gating on the given formula without calling the LLM",
)
@click.option("--name", default="alpha", help="Signal name for the generated alpha")
def alpha(
    prompt: str,
    output: Path | None,
    model: str,
    validate_only: str | None,
    name: str,
) -> None:
    """Generate or validate a symbolic alpha factor.

    In generate mode, sends the prompt to the configured Anthropic model and
    returns a validated ``AlphaSpec`` as a YAML signals block.

    In ``--validate-only FORMULA`` mode, runs the static safety gating without
    calling the LLM and prints the safety report to stderr.
    """
    if validate_only is not None:
        report = safety_check(validate_only)
        click.echo(f"passed: {report.passed}")
        if report.errors:
            click.echo("errors:")
            for error in report.errors:
                click.echo(f"  - {error}")
        if report.warnings:
            click.echo("warnings:")
            for warning in report.warnings:
                click.echo(f"  - {warning}")
        if not report.passed:
            raise click.Abort()
        return

    miner = AlphaMiner(model=model)
    spec = miner.mine(prompt, name=name, description=prompt)

    block = {
        "signals": [
            {
                "name": spec.name,
                "description": spec.description,
                "formula": spec.formula,
                "type": "rank",
                "generation": {
                    "prompt_hash": f"sha256:{spec.generation_prompt_hash}",
                    "safety_checks_passed": spec.safety_checks_passed,
                    "model": spec.model,
                },
            }
        ]
    }
    yaml_text = yaml.safe_dump(block, sort_keys=False)

    if output:
        output.write_text(yaml_text, encoding="utf-8")
        click.echo(f"Signal block written to {output.resolve()}")
    else:
        click.echo(yaml_text.strip())

    if not spec.safety_checks_passed:
        click.echo("Safety report:", err=True)
        for error in spec.safety_report:
            click.echo(f"  - {error}", err=True)
        raise click.Abort()


@cli.command()
@click.argument("prompt")
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Output strategy YAML path",
)
@click.option(
    "--data",
    type=click.Path(path_type=Path),
    help="Data CSV for optional dry-run backtest",
)
@click.option("--dry-run", is_flag=True, help="Run a dry-run backtest and emit certificate")
@click.option("--model", default="claude-sonnet-5", help="Anthropic model name")
@click.option(
    "--max-correction-attempts",
    default=2,
    show_default=True,
    help="Max retries if the LLM emits invalid YAML",
)
def author(
    prompt: str,
    output: Path,
    data: Path | None,
    dry_run: bool,
    model: str,
    max_correction_attempts: int,
) -> None:
    """Generate an Aureum strategy YAML from a natural-language prompt."""
    author_ = StrategyAuthor(model=model)
    result = author_.write_strategy(
        prompt,
        output,
        dry_run_data=data if dry_run else None,
        max_correction_attempts=max_correction_attempts,
    )
    click.echo(f"Strategy written to {output.resolve()}")
    if result.rationale:
        click.echo(f"Rationale: {result.rationale}")
    if result.certificate_path:
        click.echo(f"Dry-run certificate: {result.certificate_path.resolve()}")


@cli.command()
@click.argument("strategy", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--data",
    required=True,
    type=click.Path(path_type=Path),
    help="Data CSV for backtests",
)
@click.option(
    "--certificate",
    type=click.Path(path_type=Path),
    help="Existing certificate JSON (if omitted, one is generated)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output strategy path (defaults to overwriting input)",
)
@click.option(
    "--max-attempts",
    default=3,
    show_default=True,
    help="Maximum reflection iterations",
)
@click.option("--model", default="claude-sonnet-5", help="Anthropic model name")
def reflect(
    strategy: Path,
    data: Path,
    certificate: Path | None,
    output: Path | None,
    max_attempts: int,
    model: str,
) -> None:
    """Fix a failing strategy using an LLM reflection loop."""
    reflector = StrategyReflector(model=model)
    result = reflector.reflect(
        strategy,
        data,
        certificate_path=certificate,
        output_path=output,
        max_attempts=max_attempts,
    )
    if result.success:
        click.echo(
            f"Reflection succeeded after {result.attempts} attempt(s). "
            f"Accepted strategy: {result.accepted_draft}"
        )
        if result.final_certificate and result.accepted_draft:
            cert_path = Path(result.accepted_draft).with_suffix(".certificate.json")
            cert_path.write_text(
                result.final_certificate.to_json(indent=2), encoding="utf-8"
            )
            click.echo(f"Reflection certificate: {cert_path.resolve()}")
    else:
        click.echo(
            f"Reflection failed after {result.attempts} attempt(s). "
            f"Drafts preserved: {[str(d) for d in result.drafts]}"
        )
        raise click.Abort()


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option("--data", type=click.Path(path_type=Path), help="Path to price data")
@click.option("--output", type=click.Path(path_type=Path), help="Output report path")
@click.option(
    "--certificate", type=click.Path(path_type=Path), help="Output ABC certificate path"
)
@click.option(
    "--bundle",
    type=click.Path(path_type=Path),
    help="Output reproducibility bundle tarball path",
)
@click.option(
    "--smt",
    type=click.Path(path_type=Path),
    help="Output SMT-LIB verifier script path",
)
@click.option(
    "--lean",
    type=click.Path(path_type=Path),
    help="Output Lean 4 verifier theorem file path",
)
@click.option(
    "--economic-security",
    is_flag=True,
    help="Run the economic-security audit (uses default config if not in YAML)",
)
@click.option(
    "--graph",
    type=click.Choice(["none", "inline", "bundle"], case_sensitive=False),
    default="none",
    show_default=True,
    help="Knowledge graph persistence mode for lineage",
)
def backtest(
    path: Path,
    data: Path | None,
    output: Path | None,
    certificate: Path | None,
    bundle: Path | None,
    smt: Path | None,
    lean: Path | None,
    economic_security: bool,
    graph: str,
) -> None:
    """Run a deterministic backtest for a strategy."""
    strategy = Strategy.from_file(path)
    errors = strategy.validate()
    if errors:
        click.echo("Validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        raise click.Abort()

    if graph not in {"none", "inline", "bundle"}:
        click.echo(
            f"Error: --graph must be one of none, inline, bundle; got '{graph}'"
        )
        raise click.Abort()

    graph_persistence = strategy.graph_persistence()
    if graph != "none":
        graph_persistence = graph

    data_source = str(data) if data else "synthetic"
    click.echo(f"Running backtest for '{strategy.metadata['name']}'...")
    click.echo(f"Data source: {data_source}")

    if data is None:
        click.echo("Error: --data is required for real backtests in this version.")
        raise click.Abort()

    market_data = MarketData.from_csv(data)
    runner = BacktestRunner(
        strategy,
        market_data,
        data_source=data_source,
        initial_nav=1_000_000.0,
        strategy_path=path,
    )

    if certificate or bundle or smt or lean:
        env = get_environment(aureum_version=__version__, cwd=path.parent)
        contract_paths: list[tuple[str, str]] = []
        cert = runner.build_certificate(
            strategy_path=path,
            data_path=data,
            environment=env,
            economic_security=economic_security,
            graph_persistence=graph_persistence,
            contract_paths=contract_paths,
        )
        cert_json = cert.to_json(indent=2)
        cert_dict = cert.to_dict()

        if certificate:
            certificate = Path(certificate)
            try:
                certificate.write_text(cert_json, encoding="utf-8")
                click.echo(f"Certificate written to {certificate.resolve()}")
            except OSError as e:
                click.echo(f"Failed to write certificate: {e}")
                raise click.Abort()

        if smt:
            smt = Path(smt)
            claims = extract_claims(cert_dict)
            smt.write_text(SmtLibGenerator().generate(claims), encoding="utf-8")
            click.echo(f"SMT-LIB written to {smt.resolve()}")

        if lean:
            lean = Path(lean)
            claims = extract_claims(cert_dict)
            lean.write_text(Lean4Generator().generate(claims), encoding="utf-8")
            click.echo(f"Lean 4 file written to {lean.resolve()}")

        graph_path: Path | None = None
        if graph_persistence == "bundle" and certificate:
            graph_path = certificate.with_suffix(".graph.json")
        elif graph_persistence == "bundle" and bundle:
            graph_path = bundle.with_suffix(".graph.json")

        if graph_path is not None and cert.knowledge_graph is not None:
            graph_json = cert.knowledge_graph.to_json(indent=2)
            graph_path.write_text(graph_json, encoding="utf-8")
            cert_dict["graph_path"] = str(graph_path)
            cert_dict["graph_sha256"] = hash_file(graph_path)
            cert_json = json.dumps(cert_dict, indent=2, default=str, sort_keys=False)
            if certificate:
                certificate.write_text(cert_json, encoding="utf-8")
            click.echo(f"Graph sidecar written to {graph_path.resolve()}")

        extra_files: list[tuple[Path, str]] = []
        if graph_path is not None and graph_path.exists():
            extra_files.append((graph_path, "certificate.graph.json"))

        portfolio_spec = strategy.portfolio()
        if (
            portfolio_spec
            and portfolio_spec.get("objective") == "differentiable_sharpe"
        ):
            arch_file = path.parent / portfolio_spec["model"]["architecture_file"]
            extra_files.append((arch_file, "model_architecture.yaml"))
            if runner._diffopt and runner._diffopt.weights_path:
                extra_files.append((runner._diffopt.weights_path, "trained_weights.npz"))

        if bundle:
            _write_bundle(bundle, path, data, cert_json, extra_files=extra_files)
            click.echo(f"Bundle written to {bundle.resolve()}")

        if not output:
            click.echo(cert_json)

    if output or not (certificate or bundle):
        result = runner.run()
        report_json = json.dumps(result.to_dict(), indent=2)
        if output:
            output = Path(output)
            try:
                output.write_text(report_json, encoding="utf-8")
                click.echo(f"Report written to {output.resolve()}")
            except OSError as e:
                click.echo(f"Failed to write report: {e}")
                raise click.Abort()
        elif not certificate:
            click.echo(report_json)


@cli.command()
@click.argument("strategy", type=click.Path(exists=True, path_type=Path))
@click.option("--data", required=True, type=click.Path(exists=True, path_type=Path), help="Price CSV")
@click.option("--output", type=click.Path(path_type=Path), help="Output frontier JSON")
@click.option("--n-points", default=20, show_default=True, help="Number of frontier points")
def frontier(strategy: Path, data: Path, output: Path | None, n_points: int) -> None:
    """Compute the mean-variance efficient frontier for a portfolio strategy."""
    strat = Strategy.from_file(strategy)
    errors = strat.validate()
    if errors:
        click.echo("Validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        raise click.Abort()

    portfolio_spec = strat.portfolio()
    if portfolio_spec is None:
        click.echo("Error: frontier requires a strategy with spec.portfolio")
        raise click.Abort()

    market_data = MarketData.from_csv(data)
    lookback_days = int(portfolio_spec.get("lookback_days", 252))

    symbols = [s for s in market_data.symbols]
    returns_matrix: list[list[float]] = []
    valid_symbols: list[str] = []
    for symbol in symbols:
        closes = market_data.closes(symbol)
        if len(closes) < lookback_days + 1:
            continue
        window = closes[-(lookback_days + 1) :]
        rets = [window[i] / window[i - 1] - 1.0 for i in range(1, len(window))]
        if any(not math.isfinite(r) for r in rets):
            continue
        valid_symbols.append(symbol)
        returns_matrix.append(rets)

    if len(valid_symbols) < 2:
        click.echo("Error: fewer than 2 assets have enough history for the frontier")
        raise click.Abort()

    np = __import__("numpy")
    returns_arr = np.array(returns_matrix).T
    mu = estimate_mean_returns(returns_arr, method="sample")
    cov = estimate_covariance(returns_arr, estimator=portfolio_spec.get("covariance_estimator", "sample"))
    inputs = OptimizationInputs(
        expected_returns=mu,
        covariance=cov,
        risk_free_rate=float(portfolio_spec.get("risk_free_rate", 0.0)),
    )

    frontier_points = build_efficient_frontier(
        inputs,
        n_points=n_points,
        long_only=portfolio_spec.get("long_only", True),
        max_weight=portfolio_spec.get("max_weight"),
        min_weight=portfolio_spec.get("min_weight"),
    )

    out = {
        "strategy": strat.metadata.get("name"),
        "objective": portfolio_spec.get("objective"),
        "covariance_estimator": portfolio_spec.get("covariance_estimator", "sample"),
        "lookback_days": lookback_days,
        "symbols": valid_symbols,
        "frontier": frontier_points,
    }
    out_json = json.dumps(out, indent=2)
    if output:
        output.write_text(out_json, encoding="utf-8")
        click.echo(f"Frontier written to {output.resolve()}")
    else:
        click.echo(out_json)


@cli.command()
@click.option(
    "--symbols",
    required=True,
    help="Comma-separated list of symbols, e.g. AAPL,MSFT",
)
@click.option("--start", required=True, help="Start date ISO-8601, e.g. 2024-01-01")
@click.option("--end", required=True, help="End date ISO-8601, e.g. 2024-12-31")
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Output CSV snapshot path",
)
@click.option("--feed", default="iex", help="Alpaca data feed (iex, sip)")
@click.option("--timeframe", default="1Day", help="Bar timeframe")
def snapshot(symbols: str, start: str, end: str, output: Path, feed: str, timeframe: str) -> None:
    """Fetch a versionable Alpaca price snapshot and save it as CSV."""
    import datetime as dt

    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    start_date = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end)

    adapter = AlpacaAdapter(feed=feed)
    snap = adapter.write_snapshot(
        output, symbol_list, start_date, end_date, timeframe=timeframe
    )
    click.echo(f"Snapshot written to {snap.path.resolve()}")
    click.echo(f"Rows: {snap.rows}, SHA-256: {snap.sha256}")
    click.echo(f"Metadata: {snap.path.with_suffix('.snapshot.json')}")


def _write_bundle(
    bundle_path: Path,
    strategy_path: Path,
    data_path: Path,
    cert_json: str,
    extra_files: list[tuple[Path, str]] | None = None,
) -> None:
    """Create a reproducibility bundle tarball containing inputs and certificate."""
    bundle_path = Path(bundle_path)
    with tarfile.open(bundle_path, "w:gz") as tar:
        tar.add(strategy_path, arcname="strategy.yaml")
        tar.add(data_path, arcname="data.csv")
        cert_bytes = cert_json.encode("utf-8")
        from io import BytesIO

        info = tarfile.TarInfo(name="certificate.json")
        info.size = len(cert_bytes)
        tar.addfile(info, BytesIO(cert_bytes))
        for file_path, arcname in extra_files or []:
            tar.add(file_path, arcname=arcname)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

"""Aureum CLI entry point."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import click

from .backtest import BacktestRunner, MarketData
from .certificate import get_environment
from .strategy import Strategy


@click.group()
@click.version_option(version="0.2.0")
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
def backtest(
    path: Path,
    data: Path | None,
    output: Path | None,
    certificate: Path | None,
    bundle: Path | None,
) -> None:
    """Run a deterministic backtest for a strategy."""
    strategy = Strategy.from_file(path)
    errors = strategy.validate()
    if errors:
        click.echo("Validation failed:")
        for error in errors:
            click.echo(f"  - {error}")
        raise click.Abort()

    data_source = str(data) if data else "synthetic"
    click.echo(f"Running backtest for '{strategy.metadata['name']}'...")
    click.echo(f"Data source: {data_source}")

    if data is None:
        click.echo("Error: --data is required for real backtests in this version.")
        raise click.Abort()

    market_data = MarketData.from_csv(data)
    runner = BacktestRunner(
        strategy, market_data, data_source=data_source, initial_nav=1_000_000.0
    )

    if certificate or bundle:
        env = get_environment(aureum_version="0.2.0", cwd=path.parent)
        cert = runner.build_certificate(
            strategy_path=path, data_path=data, environment=env
        )
        cert_json = cert.to_json(indent=2)

        if certificate:
            certificate = Path(certificate)
            try:
                certificate.write_text(cert_json, encoding="utf-8")
                click.echo(f"Certificate written to {certificate.resolve()}")
            except OSError as e:
                click.echo(f"Failed to write certificate: {e}")
                raise click.Abort()

        if bundle:
            _write_bundle(bundle, path, data, cert_json)
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


def _write_bundle(
    bundle_path: Path, strategy_path: Path, data_path: Path, cert_json: str
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


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

"""Aureum CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import click

from .backtest import BacktestRunner, MarketData
from .strategy import Strategy


@click.group()
@click.version_option(version="0.1.0")
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
def backtest(path: Path, data: Path | None, output: Path | None) -> None:
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
    else:
        click.echo(report_json)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

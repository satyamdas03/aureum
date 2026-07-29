"""Tests for the Aureum backtest runner."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from aureum.backtest import BacktestRunner, MarketData
from aureum.cli import cli
from aureum.strategy import Strategy

EXAMPLE_STRATEGY = Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_market_data_loads_csv():
    data = MarketData.from_csv(EXAMPLE_DATA)
    assert len(data.symbols) == 10
    assert "AAPL" in data.symbols
    assert data.dates[0].isoformat() == "2022-01-03"
    assert data.sector("AAPL") == "Technology"
    assert data.price(data.dates[0], "AAPL") is not None


def test_backtest_produces_report():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy, data, data_source=str(EXAMPLE_DATA), initial_nav=1_000_000.0
    )
    result = runner.run()

    report = result.to_dict()
    assert report["strategy"] == "tech-momentum-sector-neutral"
    assert report["data_source"] == str(EXAMPLE_DATA)
    assert report["initial_nav"] == 1_000_000.0
    assert report["start_date"] == "2022-01-03"
    assert report["end_date"] == "2024-12-31"
    assert report["trades"] > 0
    assert len(report["rebalance_log"]) > 0
    assert len(report["daily_nav"]) == len(data.dates)
    assert 0.0 <= report["max_drawdown"] <= 1.0


def test_backtest_is_deterministic():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner1 = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    runner2 = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    assert runner1.run().to_dict() == runner2.run().to_dict()


def test_backtest_cli_output():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
        ],
    )
    assert result.exit_code == 0, result.output
    json_start = result.output.index("{")
    report = json.loads(result.output[json_start:])
    assert report["strategy"] == "tech-momentum-sector-neutral"
    assert report["trades"] > 0


def test_backtest_cli_writes_output_file(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["strategy"] == "tech-momentum-sector-neutral"

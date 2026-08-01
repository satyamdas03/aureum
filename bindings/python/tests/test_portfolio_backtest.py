"""Integration tests for MPT portfolio strategies in the backtest runner."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import BacktestCertificate
from aureum.cli import cli
from aureum.strategy import Strategy

EXAMPLE_MPT_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "mpt_max_sharpe.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_portfolio_strategy_validates():
    strategy = Strategy.from_file(EXAMPLE_MPT_STRATEGY)
    errors = strategy.validate()
    assert errors == [], errors


def test_portfolio_strategy_has_portfolio_block():
    strategy = Strategy.from_file(EXAMPLE_MPT_STRATEGY)
    portfolio = strategy.portfolio()
    assert portfolio is not None
    assert portfolio["objective"] == "maximum_sharpe"
    assert portfolio["covariance_estimator"] == "ledoit_wolf"


def test_portfolio_backtest_produces_report():
    strategy = Strategy.from_file(EXAMPLE_MPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy, data, data_source=str(EXAMPLE_DATA), initial_nav=1_000_000.0
    )
    result = runner.run()
    report = result.to_dict()
    assert report["strategy"] == "mpt-max-sharpe-tech"
    assert report["trades"] > 0
    assert len(report["rebalance_log"]) > 0
    assert 0.0 <= report["max_drawdown"] <= 1.0


def test_portfolio_backtest_rebalance_log_has_portfolio_meta():
    strategy = Strategy.from_file(EXAMPLE_MPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    result = runner.run()
    portfolio_entries = [
        entry for entry in result.rebalance_log if "portfolio" in entry
    ]
    assert len(portfolio_entries) > 0
    for entry in portfolio_entries:
        meta = entry["portfolio"]
        assert meta["objective"] == "maximum_sharpe"
        assert "weights" in meta
        assert "expected_return" in meta
        assert "risk" in meta


def test_portfolio_certificate_includes_construction():
    strategy = Strategy.from_file(EXAMPLE_MPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    from aureum.certificate import get_environment
    from aureum import __version__

    env = get_environment(__version__, cwd=EXAMPLE_MPT_STRATEGY.parent)
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_MPT_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
    )
    assert cert.portfolio_construction is not None
    pc = cert.portfolio_construction
    assert pc.objective == "maximum_sharpe"
    assert pc.covariance_estimator == "ledoit_wolf"
    assert pc.weights_history
    assert pc.optimization_inputs_hash

    # Round-trip through dict/JSON.
    cert_dict = cert.to_dict()
    assert "portfolio_construction" in cert_dict
    restored = BacktestCertificate.from_dict(cert_dict)
    assert restored.portfolio_construction is not None
    assert restored.portfolio_construction.objective == "maximum_sharpe"


def test_portfolio_backtest_cli(tmp_path: Path):
    runner = CliRunner()
    cert_path = tmp_path / "cert.json"
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_MPT_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--certificate",
            str(cert_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert cert_path.exists()
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    assert cert["portfolio_construction"]["objective"] == "maximum_sharpe"


def test_frontier_cli(tmp_path: Path):
    runner = CliRunner()
    out_path = tmp_path / "frontier.json"
    result = runner.invoke(
        cli,
        [
            "frontier",
            str(EXAMPLE_MPT_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--output",
            str(out_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["strategy"] == "mpt-max-sharpe-tech"
    assert data["objective"] == "maximum_sharpe"
    assert len(data["frontier"]) > 0

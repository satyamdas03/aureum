"""Demonstrate that the Aureum certificate catches a real configuration bug."""

from __future__ import annotations

from pathlib import Path

from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import Environment, hash_file
from aureum.strategy import Strategy
from aureum.verifier import all_passed

EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"
CORRECT_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
BUGGY_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "buggy_slippage.yaml"
)


def _run_certificate(strategy_path: Path):
    strategy = Strategy.from_file(strategy_path)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = Environment(
        aureum_version="0.2.0",
        git_commit="demo",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )
    return runner.build_certificate(
        strategy_path=strategy_path, data_path=EXAMPLE_DATA, environment=env
    )


def test_correct_strategy_passes_risk_constraints():
    cert = _run_certificate(CORRECT_STRATEGY)
    assert all_passed(cert.risk_constraints)


def test_buggy_slippage_is_caught_by_certificate():
    """A 5% slippage (entered as 0.05) instead of 5 bps (0.0005) crushes returns."""
    cert = _run_certificate(BUGGY_STRATEGY)

    drawdown_constraint = next(
        c for c in cert.risk_constraints if c["name"] == "max_drawdown"
    )
    assert drawdown_constraint["passed"] is False
    assert drawdown_constraint["actual"] > drawdown_constraint["limit"]

    correct_cert = _run_certificate(CORRECT_STRATEGY)
    correct_drawdown = next(
        c for c in correct_cert.risk_constraints if c["name"] == "max_drawdown"
    )
    assert drawdown_constraint["actual"] > correct_drawdown["actual"] * 1.5


def test_certificate_hashes_differ_between_correct_and_buggy():
    correct_cert = _run_certificate(CORRECT_STRATEGY)
    buggy_cert = _run_certificate(BUGGY_STRATEGY)
    assert correct_cert.inputs.strategy.sha256 != buggy_cert.inputs.strategy.sha256
    assert hash_file(CORRECT_STRATEGY) != hash_file(BUGGY_STRATEGY)

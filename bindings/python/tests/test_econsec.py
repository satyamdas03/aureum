"""Tests for the Aureum economic-security audit (Edge 7)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from aureum import EconomicSecurityReport, audit_economic_security
from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import Environment
from aureum.cli import cli
from aureum.econsec import extract_rebalancing_schedule
from aureum.strategy import Strategy

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
DEMO_STRATEGY = (
    Path(__file__).parents[3]
    / "examples"
    / "strategies"
    / "economic_security_demo.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def _make_env() -> Environment:
    return Environment(
        aureum_version="0.3.0",
        git_commit="abc1234",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )


def test_extract_rebalancing_schedule_computes_signed_deltas():
    rebalance_log = [{"date": "2023-02-01", "selected": ["AAPL"]}]
    daily_positions = [
        {"date": "2023-01-31", "positions": {"AAPL": 10.0}},
        {"date": "2023-02-01", "positions": {"AAPL": 10.0}},  # pre-rebalance
        {"date": "2023-02-02", "positions": {"AAPL": 25.0}},  # post-rebalance
    ]
    schedule = extract_rebalancing_schedule(rebalance_log, daily_positions)
    assert len(schedule) == 1
    item = schedule[0]
    assert item["symbol"] == "AAPL"
    assert item["rebalance_date"] == "2023-02-01"
    assert item["delta_shares"] == 15.0
    assert item["sign"] == 1
    assert item["pre_shares"] == 10.0
    assert item["post_shares"] == 25.0


def test_extract_rebalancing_schedule_ignores_zero_deltas():
    rebalance_log = [{"date": "2023-02-01", "selected": ["AAPL", "TSLA"]}]
    daily_positions = [
        {"date": "2023-01-31", "positions": {"AAPL": 10.0, "TSLA": 5.0}},
        {"date": "2023-02-01", "positions": {"AAPL": 10.0, "TSLA": 5.0}},
        {"date": "2023-02-02", "positions": {"AAPL": 10.0, "TSLA": 5.0}},
    ]
    schedule = extract_rebalancing_schedule(rebalance_log, daily_positions)
    assert schedule == []


def test_audit_enabled_from_yaml_produces_report():
    strategy = Strategy.from_file(DEMO_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    cert = runner.build_certificate(
        strategy_path=DEMO_STRATEGY, data_path=EXAMPLE_DATA, environment=_make_env()
    )
    assert cert.economic_security is not None
    assert cert.economic_security.enabled is True
    assert cert.economic_security.extractable_value_estimate_bps > 0
    assert cert.economic_security.schedule_entropy_bits >= 0
    assert len(cert.economic_security.replay_inputs_hash) == 64

    front_runs = [
        v
        for v in cert.economic_security.attack_vectors_found
        if v["vector"] == "front_run"
    ]
    assert front_runs, "expected at least one profitable front-run vector"
    assert any(v["profit_bps"] > 0 for v in front_runs)

    d = cert.to_dict()
    assert "economic_security" in d
    assert d["determinism"].get("economic_security_hash")


def test_audit_disabled_by_default():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY, data_path=EXAMPLE_DATA, environment=_make_env()
    )
    assert cert.economic_security is None
    assert "economic_security" not in cert.to_dict()


def test_low_turnover_strategy_has_negligible_extractable_value():
    yaml_text = """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: buy-and-hold-annual
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.00
  schedule:
    rebalance: 1Y
    lookback: 999d
  ranking:
    by: momentum_12_1
    ascending: false
  weights:
    kind: equal
    top_n: 1.0
  risk:
    max_drawdown:
      value: 0.50
      hard: false
  execution:
    slippage: 0.0005
  audit:
    economic_security: true
"""
    strategy = Strategy.from_yaml(yaml_text)
    errors = strategy.validate()
    assert not errors, errors
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    cert = runner.build_certificate(
        strategy_path=DEMO_STRATEGY, data_path=EXAMPLE_DATA, environment=_make_env()
    )
    assert cert.economic_security is not None
    ev = cert.economic_security.extractable_value_estimate_bps
    assert -1.0 <= ev <= 1.0, f"expected negligible EV, got {ev}"
    assert cert.economic_security.attack_vectors_found == []
    # Annual schedule on a single selection should have low entropy.
    assert cert.economic_security.schedule_entropy_bits <= 1.0


def test_capacity_clipping_reports_liquidity_squeeze():
    rows = []
    base_price = 100.0
    base_volume = 100  # ADV20 ~ $10K
    start = dt.date(2023, 1, 3)
    trading_days = 0
    current = start
    while trading_days < 40:
        if current.weekday() < 5:  # Monday=0 .. Friday=4
            rows.append(
                {
                    "date": current.isoformat(),
                    "symbol": "THIN",
                    "close": str(base_price),
                    "volume": str(base_volume),
                    "sector": "Technology",
                }
            )
            trading_days += 1
        current += dt.timedelta(days=1)
    data = MarketData(rows)

    rebalance_log = [{"date": "2023-02-09", "selected": ["THIN"]}]
    daily_positions = [
        {"date": "2023-02-08", "positions": {"THIN": 0.0}},
        {"date": "2023-02-09", "positions": {"THIN": 0.0}},  # pre-rebalance
        {"date": "2023-02-10", "positions": {"THIN": 1000.0}},  # post-rebalance
    ]
    # Craft a minimal BacktestResult directly; the audit only needs the
    # rebalance log, daily positions, and NAV series.
    from aureum.backtest import BacktestResult

    result = BacktestResult(
        strategy_name="dummy",
        data_source="fixture",
        start_date="2023-01-01",
        end_date="2023-02-10",
        initial_nav=1_000_000.0,
        final_nav=1_000_000.0,
        total_return=0.0,
        cagr=0.0,
        volatility_annual=0.0,
        sharpe_ratio=None,
        max_drawdown=0.0,
        trades=1,
        turnover_annual=0.0,
        max_leverage=0.0,
        max_concentration=0.0,
        dimensional_errors=[],
        daily_nav=[
            {"date": "2023-02-08", "nav": 1_000_000.0},
            {"date": "2023-02-09", "nav": 1_000_000.0},
            {"date": "2023-02-10", "nav": 1_000_000.0},
        ],
        daily_positions=daily_positions,
        rebalance_log=rebalance_log,
    )

    report = audit_economic_security(
        result,
        data,
        {
            "front_run_advance_days": 1,
            "adversary_cost_model": {
                "slippage": 0.001,
                "borrow_cost_annual": 0.03,
                "max_participation_rate": 0.10,
            },
            "attack_vectors": ["front_run", "liquidity_squeeze"],
        },
    )

    squeeze_vectors = [
        v for v in report.attack_vectors_found if v["vector"] == "liquidity_squeeze"
    ]
    assert squeeze_vectors, "expected a liquidity-squeeze vector"
    assert any(v["notional"] == pytest.approx(1000.0, rel=0.01) for v in squeeze_vectors)


def test_report_round_trips_through_dict():
    strategy = Strategy.from_file(DEMO_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    cert = runner.build_certificate(
        strategy_path=DEMO_STRATEGY, data_path=EXAMPLE_DATA, environment=_make_env()
    )
    report = cert.economic_security
    assert report is not None
    reconstructed = EconomicSecurityReport.from_dict(report.to_dict())
    assert reconstructed.to_dict() == report.to_dict()


def test_cli_economic_security_flag(tmp_path: Path) -> None:
    cert_path = tmp_path / "certificate.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--certificate",
            str(cert_path),
            "--economic-security",
        ],
    )
    assert result.exit_code == 0, result.output
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    assert cert.get("economic_security", {}).get("enabled") is True
    assert cert["economic_security"]["extractable_value_estimate_bps"] > 0

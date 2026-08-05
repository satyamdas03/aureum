"""Tests for live-trading equity-cap overrides and order-submission safety."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from aureum.certificate import Environment, LiveTradingCertificate
from aureum.cli import cli
from aureum.execution import ExecutionResult, LiveTradingConfig
from aureum.trading import AureumTradingError

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


@pytest.fixture
def fake_env():
    return Environment(
        aureum_version="0.4.2",
        git_commit="abc123",
        git_dirty=False,
        python_version="3.12.0",
        platform="win32",
        dependencies_digest="",
    )


@pytest.fixture
def patched_live(monkeypatch, fake_env):
    calls = {"adapter": [], "backend": [], "runner": []}

    class FakeAdapter:
        def __init__(self, paper: bool, market_open_required: bool):
            calls["adapter"].append(
                {"paper": paper, "market_open_required": market_open_required}
            )

    class FakeBackend:
        def __init__(self, adapter, config, run_id: str | None = None):
            calls["backend"].append(
                {
                    "paper": config.paper,
                    "dry_run": config.dry_run,
                    "max_total_invested_pct": config.max_total_invested_pct,
                    "run_id": run_id,
                }
            )
            self.config = config

        def execute(self, target, context):
            return ExecutionResult(
                positions={},
                cash=50_000.0,
                trades=0,
                turnover_notional=0.0,
                orders=[{"symbol": "AAPL", "dry_run": self.config.dry_run}],
            )

    class FakeRunner:
        def __init__(
            self,
            strategy,
            data,
            data_source,
            strategy_path,
            backend,
            notification_dir=None,
        ):
            calls["runner"].append(
                {
                    "strategy_path": str(strategy_path),
                    "data_source": data_source,
                    "notification_dir": str(notification_dir)
                    if notification_dir
                    else None,
                }
            )

        def run(self, check_only=False, dry_run=False, kill_switch=None):
            if kill_switch is not None and Path(kill_switch).exists():
                raise AureumTradingError(
                    f"Kill switch is active; exiting without action. ({kill_switch})"
                )
            return LiveTradingCertificate.from_run(
                environment=fake_env,
                run_id="r-1",
                strategy_path="/strategy.yaml",
                strategy_sha256="sha",
                live_mode="paper-dry-run" if dry_run else "paper",
                market_clock={},
                pre_trade_account={"equity": 100_000.0},
                post_trade_account={"equity": 100_000.0},
                target_portfolio={},
                current_positions=[],
                orders=[{"symbol": "AAPL", "dry_run": dry_run}],
                risk_checks=[],
                errors=[],
            )

    monkeypatch.setattr("aureum.cli.AlpacaTradingAdapter", FakeAdapter)
    monkeypatch.setattr("aureum.cli.AlpacaPaperExecutionBackend", FakeBackend)
    monkeypatch.setattr("aureum.cli.LiveRunner", FakeRunner)
    return calls


def test_live_default_is_dry_run_without_submit_orders(patched_live):
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        cert_path = Path(tmp) / "cert.json"
        result = runner.invoke(
            cli,
            [
                "live",
                str(EXAMPLE_STRATEGY),
                "--data",
                str(EXAMPLE_DATA),
                "--certificate",
                str(cert_path),
                "--paper",
            ],
        )
        assert result.exit_code == 0, result.output
        assert cert_path.exists()
        assert "paper-dry-run" in cert_path.read_text()
        assert patched_live["backend"][0]["dry_run"] is True


def test_live_submit_orders_sets_dry_run_false(patched_live):
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        cert_path = Path(tmp) / "cert.json"
        result = runner.invoke(
            cli,
            [
                "live",
                str(EXAMPLE_STRATEGY),
                "--data",
                str(EXAMPLE_DATA),
                "--certificate",
                str(cert_path),
                "--paper",
                "--submit-orders",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "[Aureum] SUBMITTING REAL PAPER ORDERS" in result.output
        assert cert_path.exists()
        assert 'paper"' in cert_path.read_text()
        assert "paper-dry-run" not in cert_path.read_text()
        assert patched_live["backend"][0]["dry_run"] is False


def test_live_dry_run_flag_overrides_submit_orders(patched_live):
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        cert_path = Path(tmp) / "cert.json"
        result = runner.invoke(
            cli,
            [
                "live",
                str(EXAMPLE_STRATEGY),
                "--data",
                str(EXAMPLE_DATA),
                "--certificate",
                str(cert_path),
                "--paper",
                "--submit-orders",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert cert_path.exists()
        assert "paper-dry-run" in cert_path.read_text()
        assert patched_live["backend"][0]["dry_run"] is True


def test_live_cli_parses_max_total_invested_pct(patched_live):
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        cert_path = Path(tmp) / "cert.json"
        result = runner.invoke(
            cli,
            [
                "live",
                str(EXAMPLE_STRATEGY),
                "--data",
                str(EXAMPLE_DATA),
                "--certificate",
                str(cert_path),
                "--paper",
                "--max-total-invested-pct",
                "0.65",
            ],
        )
        assert result.exit_code == 0, result.output
        assert patched_live["backend"][0]["max_total_invested_pct"] == pytest.approx(
            0.65
        )


def test_live_config_applies_max_total_invested_pct_override():
    spec = {
        "execution": {
            "max_total_invested_pct": 0.95,
            "max_single_position_pct": 0.25,
        }
    }
    config = LiveTradingConfig.from_strategy_spec(
        spec, overrides={"max_total_invested_pct": 0.65}
    )
    assert config.max_total_invested_pct == pytest.approx(0.65)
    assert config.max_single_position_pct == pytest.approx(0.25)


def test_live_config_default_uses_strategy_value():
    spec = {"execution": {"max_total_invested_pct": 0.80}}
    config = LiveTradingConfig.from_strategy_spec(spec)
    assert config.max_total_invested_pct == pytest.approx(0.80)


def test_live_config_default_without_spec():
    config = LiveTradingConfig.from_strategy_spec({})
    assert config.max_total_invested_pct == pytest.approx(0.95)

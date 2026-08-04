"""Tests for the live-trading CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from aureum.certificate import Environment, LiveTradingCertificate
from aureum.cli import cli
from aureum.execution import ExecutionResult
from aureum.trading import (
    AccountSnapshot,
    AureumTradingError,
    ClockSnapshot,
    PositionRecord,
)

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
EXAMPLE_DATA = (
    Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"
)


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
def patched_account(monkeypatch):
    calls = []

    class FakeAdapter:
        def __init__(self, paper: bool, market_open_required: bool):
            calls.append({"paper": paper, "market_open_required": market_open_required})
            self.paper = paper
            self.market_open_required = market_open_required

        def get_clock(self):
            return ClockSnapshot(
                timestamp="2024-01-01T09:30:00-05:00",
                is_open=True,
                next_open="2024-01-01T09:30:00-05:00",
                next_close="2024-01-01T16:00:00-05:00",
            )

        def get_account(self):
            return AccountSnapshot(
                account_number="PA1234",
                status="ACTIVE",
                currency="USD",
                equity=100_000.0,
                cash=50_000.0,
                buying_power=200_000.0,
                long_market_value=50_000.0,
                short_market_value=0.0,
                portfolio_value=100_000.0,
                daytrade_count=0,
                pattern_day_trader=False,
                trading_blocked=False,
            )

        def get_positions(self):
            return [
                PositionRecord(
                    symbol="AAPL",
                    qty=10.0,
                    side="long",
                    market_value=1_850.0,
                    avg_entry_price=180.0,
                    current_price=185.0,
                    cost_basis=1_800.0,
                    unrealized_pl=50.0,
                )
            ]

    monkeypatch.setattr("aureum.cli.AlpacaTradingAdapter", FakeAdapter)
    return calls


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
                {"paper": config.paper, "dry_run": config.dry_run, "run_id": run_id}
            )
            self.config = config

        def execute(self, target, context):
            return ExecutionResult(
                positions={},
                cash=50_000.0,
                trades=0,
                turnover_notional=0.0,
                orders=[{"symbol": "AAPL", "dry_run": True}],
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
                    "notification_dir": str(notification_dir) if notification_dir else None,
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
                live_mode="paper-dry-run" if dry_run else "paper-check-only",
                market_clock={},
                pre_trade_account={"equity": 100_000.0},
                post_trade_account={"equity": 100_000.0},
                target_portfolio={},
                current_positions=[],
                orders=[{"symbol": "AAPL", "dry_run": True}],
                risk_checks=[],
                errors=[],
            )

    monkeypatch.setattr("aureum.cli.AlpacaTradingAdapter", FakeAdapter)
    monkeypatch.setattr("aureum.cli.AlpacaPaperExecutionBackend", FakeBackend)
    monkeypatch.setattr("aureum.cli.LiveRunner", FakeRunner)
    return calls


def test_account_command_prints_snapshot(patched_account):
    runner = CliRunner()
    result = runner.invoke(cli, ["account", "--paper"])
    assert result.exit_code == 0
    assert "PA1234" in result.output
    assert "AAPL" in result.output
    assert patched_account[0]["paper"] is True


def test_account_command_kill_switch(patched_account, tmp_path: Path):
    runner = CliRunner()
    ks = tmp_path / "kill.switch"
    ks.write_text("stop")
    result = runner.invoke(cli, ["account", "--paper", "--kill-switch", str(ks)])
    assert result.exit_code == 0
    assert "Kill switch is active" in result.output
    assert "PA1234" not in result.output


def test_live_command_dry_run_writes_certificate(patched_live):
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
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert cert_path.exists()
        assert "paper-dry-run" in cert_path.read_text()
        assert patched_live["adapter"][0]["paper"] is True
        assert patched_live["runner"][0]["strategy_path"] == str(EXAMPLE_STRATEGY)


def test_live_command_check_only_writes_certificate(patched_live):
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
                "--check-only",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "paper-check-only" in cert_path.read_text()


def test_live_command_kill_switch(patched_live, tmp_path: Path):
    runner = CliRunner()
    ks = tmp_path / "kill.switch"
    ks.write_text("stop")
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
                "--kill-switch",
                str(ks),
            ],
        )
        assert result.exit_code == 0
        assert "Kill switch is active" in result.output
        assert not cert_path.exists()


def test_live_command_invalid_strategy_fails(patched_live):
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        bad = Path(tmp) / "bad.yaml"
        bad.write_text("not: a valid strategy")
        cert_path = Path(tmp) / "cert.json"
        result = runner.invoke(
            cli,
            [
                "live",
                str(bad),
                "--data",
                str(EXAMPLE_DATA),
                "--certificate",
                str(cert_path),
                "--paper",
            ],
        )
        assert result.exit_code != 0
        assert not cert_path.exists()

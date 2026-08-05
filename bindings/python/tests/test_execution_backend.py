"""Tests for execution backends and the live runner."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aureum.backtest import BacktestRunner, MarketData
from aureum.execution import (
    AlpacaPaperExecutionBackend,
    ExecutionContext,
    LiveRunner,
    LiveTradingConfig,
    SimulatedExecutionBackend,
    TargetPortfolio,
)
from aureum.strategy import Strategy
from aureum.trading import (
    AccountSnapshot,
    AlpacaTradingAdapter,
    OrderRecord,
    PositionRecord,
)

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
EXAMPLE_DATA = (
    Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"
)


def test_simulated_backend_matches_original_backtest():
    """The default backend must reproduce the original in-process backtest."""
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    backend = SimulatedExecutionBackend()
    runner = BacktestRunner(
        strategy,
        data,
        data_source=str(EXAMPLE_DATA),
        execution_backend=backend,
    )
    result = runner.run()
    assert result.trades == 65
    assert abs(result.final_nav - 897_736.14) < 0.01
    assert result.max_drawdown <= 0.25


def test_simulated_backend_sells_positions_not_in_target():
    backend = SimulatedExecutionBackend()
    target = TargetPortfolio(
        date=dt.date(2024, 1, 1),
        target_values={"AAPL": 5000.0, "MSFT": 0.0},
        target_weights={"AAPL": 0.5, "MSFT": 0.0},
        prices={"AAPL": 100.0, "MSFT": 200.0},
    )
    context = ExecutionContext(
        date=dt.date(2024, 1, 1),
        current_positions={"AAPL": 40.0, "MSFT": 20.0},
        cash=5_000.0,
        slippage=0.0,
    )
    result = backend.execute(target, context)
    assert result.positions == {"AAPL": pytest.approx(50.0)}
    assert result.trades == 2  # sell MSFT, buy more AAPL


def _fake_account(equity: float = 100_000.0, cash: float = 10_000.0) -> AccountSnapshot:
    return AccountSnapshot(
        account_number="PA1234",
        status="ACTIVE",
        currency="USD",
        equity=equity,
        cash=cash,
        buying_power=equity * 2,
        long_market_value=equity - cash,
        short_market_value=0.0,
        portfolio_value=equity,
        daytrade_count=0,
        pattern_day_trader=False,
        trading_blocked=False,
    )


def _fake_adapter(monkeypatch) -> AlpacaTradingAdapter:
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    adapter = AlpacaTradingAdapter(paper=True, market_open_required=False)
    return adapter


def test_paper_backend_computes_diff_orders_and_respects_min_notional(
    monkeypatch,
):
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter, "get_account", lambda: _fake_account(equity=100_000.0, cash=10_000.0)
    )
    monkeypatch.setattr(
        adapter,
        "get_positions",
        lambda: [
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
        ],
    )

    submitted: list[dict] = []

    def fake_submit_market_order(symbol, qty, side, client_order_id, **kwargs):
        submitted.append(
            {"symbol": symbol, "qty": qty, "side": side, "client_order_id": client_order_id}
        )
        return OrderRecord(
            client_order_id=client_order_id,
            alpaca_order_id="o-1",
            symbol=symbol,
            side=side,
            status="filled",
            qty_requested=qty,
            notional_requested=None,
            qty_filled=qty,
            filled_avg_price=185.0,
            submitted_at="2024-01-01T10:00:00Z",
            updated_at="2024-01-01T10:00:01Z",
            raw={},
        )

    monkeypatch.setattr(adapter, "submit_market_order", fake_submit_market_order)

    config = LiveTradingConfig(min_order_notional=50.0, use_notional_orders=False)
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")

    target = TargetPortfolio(
        date=dt.date(2024, 1, 1),
        target_values={"AAPL": 5_000.0, "MSFT": 20.0},
        target_weights={"AAPL": 0.05, "MSFT": 0.0002},
        prices={"AAPL": 185.0, "MSFT": 200.0},
    )
    context = ExecutionContext(
        date=dt.date(2024, 1, 1),
        current_positions={"AAPL": 10.0},
        cash=10_000.0,
        slippage=0.0,
    )
    backend.execute(target, context)

    # MSFT target $20 is below min_order_notional $50.
    assert len(submitted) == 1
    assert submitted[0]["symbol"] == "AAPL"
    assert submitted[0]["qty"] == pytest.approx(5000 / 185 - 10)
    assert submitted[0]["side"] == "buy"


def test_paper_backend_dry_run_returns_intended_orders(monkeypatch):
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(adapter, "get_account", lambda: _fake_account())
    monkeypatch.setattr(adapter, "get_positions", list)
    config = LiveTradingConfig(dry_run=True, market_open_required=False)
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")

    target = TargetPortfolio(
        date=dt.date(2024, 1, 1),
        target_values={"AAPL": 5_000.0},
        target_weights={"AAPL": 0.05},
        prices={"AAPL": 185.0},
    )
    context = ExecutionContext(
        date=dt.date(2024, 1, 1),
        current_positions={},
        cash=10_000.0,
        slippage=0.0,
    )
    result = backend.execute(target, context)
    assert result.trades == 0
    assert len(result.orders) == 1
    assert result.orders[0]["dry_run"] is True


def test_paper_backend_liquidates_positions_not_in_target(monkeypatch):
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter, "get_account", lambda: _fake_account(equity=100_000.0, cash=80_000.0)
    )
    monkeypatch.setattr(
        adapter,
        "get_positions",
        lambda: [
            PositionRecord(
                symbol="AAPL",
                qty=10.0,
                side="long",
                market_value=1_850.0,
                avg_entry_price=180.0,
                current_price=185.0,
                cost_basis=1_800.0,
                unrealized_pl=50.0,
            ),
            PositionRecord(
                symbol="OLD",
                qty=50.0,
                side="long",
                market_value=5_000.0,
                avg_entry_price=95.0,
                current_price=100.0,
                cost_basis=4_750.0,
                unrealized_pl=250.0,
            ),
        ],
    )

    submitted: list[dict] = []

    def fake_submit_market_order(symbol, qty, side, client_order_id, **kwargs):
        submitted.append({"symbol": symbol, "qty": qty, "side": side})
        return OrderRecord(
            client_order_id=client_order_id,
            alpaca_order_id="o-1",
            symbol=symbol,
            side=side,
            status="filled",
            qty_requested=qty,
            notional_requested=None,
            qty_filled=qty,
            filled_avg_price=185.0 if symbol == "AAPL" else 100.0,
            submitted_at="2024-01-01T10:00:00Z",
            updated_at="2024-01-01T10:00:01Z",
            raw={},
        )

    monkeypatch.setattr(adapter, "submit_market_order", fake_submit_market_order)

    config = LiveTradingConfig(
        min_order_notional=50.0, use_notional_orders=False, market_open_required=False
    )
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")

    target = TargetPortfolio(
        date=dt.date(2024, 1, 1),
        target_values={"AAPL": 5_000.0},
        target_weights={"AAPL": 0.05},
        prices={"AAPL": 185.0},
    )
    context = ExecutionContext(
        date=dt.date(2024, 1, 1),
        current_positions={"AAPL": 10.0, "OLD": 50.0},
        cash=80_000.0,
        slippage=0.0,
    )
    result = backend.execute(target, context)

    symbols = {o["symbol"] for o in submitted}
    assert "OLD" in symbols
    assert any(o["side"] == "sell" and o["symbol"] == "OLD" for o in submitted)
    assert result.trades == 2


def test_paper_backend_scales_target_to_max_total_invested_pct(monkeypatch):
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter, "get_account", lambda: _fake_account(equity=100_000.0)
    )
    monkeypatch.setattr(adapter, "get_positions", list)
    config = LiveTradingConfig(
        max_total_invested_pct=0.5,
        max_single_position_pct=0.5,
        dry_run=True,
        market_open_required=False,
    )
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")

    target = TargetPortfolio(
        date=dt.date(2024, 1, 1),
        target_values={"AAPL": 30_000.0, "MSFT": 30_000.0},
        target_weights={"AAPL": 0.3, "MSFT": 0.3},
        prices={"AAPL": 100.0, "MSFT": 100.0},
    )
    context = ExecutionContext(
        date=dt.date(2024, 1, 1),
        current_positions={},
        cash=50_000.0,
        slippage=0.0,
    )
    result = backend.execute(target, context)
    assert result.errors == []
    assert result.trades == 0  # dry-run is False, but no orders submitted in test
    # Deltas reflect scaled target: total $60k scaled to $50k (0.5 * equity).
    aapl_order = next(o for o in result.orders if o["symbol"] == "AAPL")
    msft_order = next(o for o in result.orders if o["symbol"] == "MSFT")
    assert aapl_order["target_qty"] == pytest.approx(250.0)
    assert msft_order["target_qty"] == pytest.approx(250.0)
    assert target.target_values["AAPL"] == pytest.approx(25_000.0)
    assert target.target_weights["AAPL"] == pytest.approx(0.25)


def test_live_runner_check_only_produces_certificate(monkeypatch, tmp_path: Path):
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter, "get_account", lambda: _fake_account(equity=1_000_000.0)
    )
    monkeypatch.setattr(adapter, "get_positions", list)
    monkeypatch.setattr(
        adapter, "get_clock", lambda: MagicMock(is_open=True, to_dict=dict)
    )

    config = LiveTradingConfig(market_open_required=False)
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")
    runner = LiveRunner(
        strategy=strategy,
        data=data,
        data_source=str(EXAMPLE_DATA),
        strategy_path=EXAMPLE_STRATEGY,
        backend=backend,
    )
    cert = runner.run(check_only=True)
    assert cert.live_mode == "paper-check-only"
    assert cert.strategy_sha256
    assert cert.errors == []
    assert cert.orders == []


def test_live_runner_dry_run_includes_intended_orders_in_certificate(monkeypatch):
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    adapter = _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter, "get_account", lambda: _fake_account(equity=1_000_000.0, cash=900_000.0)
    )
    monkeypatch.setattr(adapter, "get_positions", list)
    monkeypatch.setattr(
        adapter, "get_clock", lambda: MagicMock(is_open=True, to_dict=dict)
    )

    config = LiveTradingConfig(
        market_open_required=False,
        dry_run=True,
        max_single_position_pct=0.5,
        max_total_invested_pct=1.0,
    )
    backend = AlpacaPaperExecutionBackend(adapter, config, run_id="run1")
    runner = LiveRunner(
        strategy=strategy,
        data=data,
        data_source=str(EXAMPLE_DATA),
        strategy_path=EXAMPLE_STRATEGY,
        backend=backend,
    )
    cert = runner.run(dry_run=True)
    assert cert.live_mode == "paper-dry-run"
    assert cert.orders
    assert all(o.get("dry_run") is True for o in cert.orders)

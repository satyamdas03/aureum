"""Tests for the Alpaca trading adapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from aureum.trading import (
    AlpacaTradingAdapter,
    AureumTradingError,
    KillSwitchActive,
    MarketClosedError,
)


def _open_response(payload: dict | list) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


def test_trading_adapter_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(AureumTradingError, match="Alpaca API credentials missing"):
        AlpacaTradingAdapter(api_key="", secret_key="")


def test_get_clock_parses_open_state():
    adapter = AlpacaTradingAdapter(api_key="K", secret_key="S")
    response = _open_response(
        {
            "timestamp": "2024-01-02T14:30:00Z",
            "is_open": True,
            "next_open": "2024-01-02T14:30:00Z",
            "next_close": "2024-01-02T21:00:00Z",
        }
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response):
        clock = adapter.get_clock()
    assert clock.is_open is True
    assert clock.next_close == "2024-01-02T21:00:00Z"


def test_get_account_parses_snapshot():
    adapter = AlpacaTradingAdapter(api_key="K", secret_key="S")
    response = _open_response(
        {
            "account_number": "PA1234",
            "status": "ACTIVE",
            "currency": "USD",
            "equity": "105000.00",
            "cash": "5000.00",
            "buying_power": "210000.00",
            "long_market_value": "100000.00",
            "short_market_value": "0.00",
            "portfolio_value": "105000.00",
            "daytrade_count": 0,
            "pattern_day_trader": False,
            "trading_blocked": False,
        }
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response):
        account = adapter.get_account()
    assert account.equity == 105_000.0
    assert account.buying_power == 210_000.0
    assert account.cash == 5_000.0


def test_get_positions_parses_long_and_short():
    adapter = AlpacaTradingAdapter(api_key="K", secret_key="S")
    response = _open_response(
        [
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "long",
                "market_value": "1850.00",
                "avg_entry_price": "180.00",
                "current_price": "185.00",
                "cost_basis": "1800.00",
                "unrealized_pl": "50.00",
            },
            {
                "symbol": "TSLA",
                "qty": "5",
                "side": "short",
                "market_value": "950.00",
                "avg_entry_price": "200.00",
                "current_price": "190.00",
                "cost_basis": "1000.00",
                "unrealized_pl": "50.00",
            },
        ]
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response):
        positions = adapter.get_positions()
    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert positions[0].qty == 10.0
    assert positions[1].symbol == "TSLA"
    assert positions[1].qty == -5.0


def test_get_orders_parses_order_list():
    adapter = AlpacaTradingAdapter(api_key="K", secret_key="S")
    response = _open_response(
        [
            {
                "id": "order-1",
                "client_order_id": "aureum-abc-AAPL-buy",
                "symbol": "AAPL",
                "side": "buy",
                "status": "filled",
                "qty": "10",
                "filled_qty": "10",
                "filled_avg_price": "185.00",
                "submitted_at": "2024-01-02T14:30:00Z",
                "updated_at": "2024-01-02T14:30:01Z",
            }
        ]
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response):
        orders = adapter.get_orders()
    assert len(orders) == 1
    assert orders[0].alpaca_order_id == "order-1"
    assert orders[0].qty_filled == 10.0
    assert orders[0].filled_avg_price == 185.0


def test_submit_market_order_sends_body_and_parses_response():
    adapter = AlpacaTradingAdapter(
        api_key="K", secret_key="S", market_open_required=False
    )
    response = _open_response(
        {
            "id": "order-2",
            "client_order_id": "aureum-abc-MSFT-buy",
            "symbol": "MSFT",
            "side": "buy",
            "status": "accepted",
            "qty": "5",
            "filled_qty": "0",
        }
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response) as mock_urlopen:
        order = adapter.submit_market_order(
            symbol="MSFT", qty=5, side="buy", client_order_id="aureum-abc-MSFT-buy"
        )
    assert order.alpaca_order_id == "order-2"
    assert order.qty_requested == 5.0
    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)
    assert body["symbol"] == "MSFT"
    assert body["qty"] == "5"
    assert body["side"] == "buy"
    assert body["type"] == "market"


def test_submit_notional_order_uses_notional_field():
    adapter = AlpacaTradingAdapter(
        api_key="K", secret_key="S", market_open_required=False
    )
    response = _open_response(
        {
            "id": "order-3",
            "client_order_id": "aureum-abc-AAPL-buy",
            "symbol": "AAPL",
            "side": "buy",
            "status": "accepted",
            "notional": "1000.00",
            "filled_qty": "0",
        }
    )
    with patch("aureum.trading.urllib.request.urlopen", return_value=response) as mock_urlopen:
        order = adapter.submit_notional_order(
            symbol="AAPL", notional=1000, side="buy", client_order_id="aureum-abc-AAPL-buy"
        )
    assert order.notional_requested == 1000.0
    request = mock_urlopen.call_args[0][0]
    body = json.loads(request.data)
    assert body["notional"] == "1000"


def test_market_open_required_blocks_submission_when_closed(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    adapter = AlpacaTradingAdapter(market_open_required=True)
    clock_response = _open_response(
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "is_open": False,
            "next_open": "2024-01-02T14:30:00Z",
            "next_close": "2024-01-02T21:00:00Z",
        }
    )
    with (
        patch("aureum.trading.urllib.request.urlopen", return_value=clock_response),
        pytest.raises(MarketClosedError),
    ):
        adapter.submit_market_order(
            symbol="AAPL", qty=1, side="buy", client_order_id="x"
        )


def test_kill_switch_blocks_order_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    switch = tmp_path / "kill"
    switch.write_text("halt", encoding="utf-8")
    monkeypatch.setenv("AUREUM_KILL_SWITCH", str(switch))
    adapter = AlpacaTradingAdapter()
    with pytest.raises(KillSwitchActive):
        adapter.submit_market_order(
            symbol="AAPL", qty=1, side="buy", client_order_id="x"
        )


def test_live_endpoint_requires_force_live_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.delenv("AUREUM_FORCE_LIVE", raising=False)
    with pytest.raises(AureumTradingError, match="AUREUM_FORCE_LIVE"):
        AlpacaTradingAdapter(paper=False)


def test_live_endpoint_allowed_with_force_live(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "K")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "S")
    monkeypatch.setenv("AUREUM_FORCE_LIVE", "true")
    adapter = AlpacaTradingAdapter(paper=False)
    assert adapter.base_url == AlpacaTradingAdapter.LIVE_BASE_URL

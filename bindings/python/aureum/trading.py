"""Alpaca trading adapter for live (paper) execution.

This module talks directly to the Alpaca Broker API using only the standard
library.  It is intentionally dependency-free so that the live trading bridge
adds no new runtime requirements.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class AureumTradingError(RuntimeError):
    """Base class for live trading errors."""

    def to_certificate_dict(self) -> dict[str, Any]:
        return {
            "type": self.__class__.__name__,
            "message": str(self),
        }


class MarketClosedError(AureumTradingError):
    """Raised when the market is closed and market_open_required is set."""


class BuyingPowerError(AureumTradingError):
    """Raised when a target portfolio exceeds available buying power."""


class OrderSubmissionError(AureumTradingError):
    """Raised when Alpaca rejects an order submission."""


class RiskViolationError(AureumTradingError):
    """Raised when a proposed trade violates a configured risk guardrail."""


class KillSwitchActive(AureumTradingError):
    """Raised when the kill-switch file is present."""


@dataclass(frozen=True)
class AccountSnapshot:
    """Relevant subset of the Alpaca /v2/account response."""

    account_number: str
    status: str
    currency: str
    equity: float
    cash: float
    buying_power: float
    long_market_value: float
    short_market_value: float
    portfolio_value: float
    daytrade_count: int
    pattern_day_trader: bool
    trading_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_number": self.account_number,
            "status": self.status,
            "currency": self.currency,
            "equity": round(self.equity, 4),
            "cash": round(self.cash, 4),
            "buying_power": round(self.buying_power, 4),
            "long_market_value": round(self.long_market_value, 4),
            "short_market_value": round(self.short_market_value, 4),
            "portfolio_value": round(self.portfolio_value, 4),
            "daytrade_count": self.daytrade_count,
            "pattern_day_trader": self.pattern_day_trader,
            "trading_blocked": self.trading_blocked,
        }


@dataclass(frozen=True)
class PositionRecord:
    """Relevant subset of an Alpaca /v2/positions entry."""

    symbol: str
    qty: float
    side: str
    market_value: float
    avg_entry_price: float
    current_price: float
    cost_basis: float
    unrealized_pl: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "qty": round(self.qty, 6),
            "side": self.side,
            "market_value": round(self.market_value, 4),
            "avg_entry_price": round(self.avg_entry_price, 4),
            "current_price": round(self.current_price, 4),
            "cost_basis": round(self.cost_basis, 4),
            "unrealized_pl": round(self.unrealized_pl, 4),
        }


@dataclass(frozen=True)
class OrderRecord:
    """Record of an order submitted to Alpaca."""

    client_order_id: str
    alpaca_order_id: str | None
    symbol: str
    side: str
    status: str
    qty_requested: float | None
    notional_requested: float | None
    qty_filled: float
    filled_avg_price: float | None
    submitted_at: str | None
    updated_at: str | None
    raw: dict[str, Any] = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "alpaca_order_id": self.alpaca_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "status": self.status,
            "qty_requested": self.qty_requested,
            "notional_requested": self.notional_requested,
            "qty_filled": round(self.qty_filled, 6),
            "filled_avg_price": round(self.filled_avg_price, 4)
            if self.filled_avg_price is not None
            else None,
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ClockSnapshot:
    """Relevant subset of the Alpaca /v2/clock response."""

    timestamp: str
    is_open: bool
    next_open: str
    next_close: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "is_open": self.is_open,
            "next_open": self.next_open,
            "next_close": self.next_close,
        }


class AlpacaTradingAdapter:
    """Low-level Alpaca broker API adapter.

    Defaults to the Alpaca **paper** endpoint.  Passing ``paper=False`` switches
    to the live endpoint, but only if the environment variable
    ``AUREUM_FORCE_LIVE`` is set to ``true``.  This two-key safety makes it hard
    to accidentally trade real money.
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
    LIVE_BASE_URL = "https://api.alpaca.markets/v2"

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        paper: bool = True,
        market_open_required: bool = True,
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        if not self.api_key or not self.secret_key:
            raise AureumTradingError(
                "Alpaca API credentials missing. Set ALPACA_API_KEY and "
                "ALPACA_SECRET_KEY environment variables."
            )

        if paper:
            self.base_url = self.PAPER_BASE_URL
        else:
            if os.environ.get("AUREUM_FORCE_LIVE", "").lower() != "true":
                raise AureumTradingError(
                    "Live trading requested but AUREUM_FORCE_LIVE is not set to 'true'. "
                    "This is a safety guard; set the environment variable AND pass paper=False "
                    "only when you intend to trade real money."
                )
            self.base_url = self.LIVE_BASE_URL

        self.paper = paper
        self.market_open_required = market_open_required

    @staticmethod
    def _kill_switch_active() -> str | None:
        """Return a message if the kill-switch file exists, else None."""
        switch_path = os.environ.get("AUREUM_KILL_SWITCH", "")
        if not switch_path:
            return None
        path = Path(switch_path)
        if path.exists():
            return f"Kill switch active: {path.resolve()}"
        return None

    def _assert_no_kill_switch(self) -> None:
        msg = self._kill_switch_active()
        if msg:
            raise KillSwitchActive(msg)

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Send an authenticated JSON request to Alpaca and return JSON."""
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json" if data else "",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise OrderSubmissionError(
                f"Alpaca API error {exc.code} on {method} {path}: {body_text}"
            ) from exc

    def get_clock(self) -> ClockSnapshot:
        """Return the current market clock from Alpaca."""
        raw = self._request("GET", "/clock")
        return ClockSnapshot(
            timestamp=raw.get("timestamp", ""),
            is_open=bool(raw.get("is_open", False)),
            next_open=raw.get("next_open", ""),
            next_close=raw.get("next_close", ""),
        )

    def _require_market_open(self) -> None:
        """Raise MarketClosedError if the market is not open."""
        if not self.market_open_required:
            return
        clock = self.get_clock()
        if not clock.is_open:
            raise MarketClosedError(
                f"Market is closed (next open {clock.next_open}, "
                f"next close {clock.next_close})."
            )

    def get_account(self) -> AccountSnapshot:
        """Return the current Alpaca account snapshot."""
        raw = self._request("GET", "/account")
        return AccountSnapshot(
            account_number=str(raw.get("account_number", "")),
            status=str(raw.get("status", "")),
            currency=str(raw.get("currency", "USD")),
            equity=float(raw.get("equity", 0.0)),
            cash=float(raw.get("cash", 0.0)),
            buying_power=float(raw.get("buying_power", 0.0)),
            long_market_value=float(raw.get("long_market_value", 0.0)),
            short_market_value=float(raw.get("short_market_value", 0.0)),
            portfolio_value=float(raw.get("portfolio_value", 0.0)),
            daytrade_count=int(raw.get("daytrade_count", 0)),
            pattern_day_trader=bool(raw.get("pattern_day_trader", False)),
            trading_blocked=bool(raw.get("trading_blocked", False)),
        )

    def get_positions(self) -> list[PositionRecord]:
        """Return current open positions."""
        raw_positions = self._request("GET", "/positions")
        if not isinstance(raw_positions, list):
            return []
        out: list[PositionRecord] = []
        for raw in raw_positions:
            qty = float(raw.get("qty", 0.0))
            side = str(raw.get("side", "long"))
            if side == "short":
                qty = -abs(qty)
            out.append(
                PositionRecord(
                    symbol=str(raw.get("symbol", "")),
                    qty=qty,
                    side=side,
                    market_value=float(raw.get("market_value", 0.0)),
                    avg_entry_price=float(raw.get("avg_entry_price", 0.0)),
                    current_price=float(raw.get("current_price", 0.0)),
                    cost_basis=float(raw.get("cost_basis", 0.0)),
                    unrealized_pl=float(raw.get("unrealized_pl", 0.0)),
                )
            )
        return out

    def get_orders(self, status: str = "open") -> list[OrderRecord]:
        """Return orders filtered by status (open, closed, all)."""
        params: dict[str, str] = {}
        if status != "all":
            params["status"] = status
        query = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params.items())
        path = f"/orders?{query}" if query else "/orders"
        raw_orders = self._request("GET", path)
        if not isinstance(raw_orders, list):
            return []
        return [self._parse_order(raw) for raw in raw_orders]

    @staticmethod
    def _parse_order(raw: dict[str, Any]) -> OrderRecord:
        qty = raw.get("qty")
        notional = raw.get("notional")
        filled_avg = raw.get("filled_avg_price")
        return OrderRecord(
            client_order_id=str(raw.get("client_order_id", "")),
            alpaca_order_id=str(raw.get("id", "")) or None,
            symbol=str(raw.get("symbol", "")),
            side=str(raw.get("side", "")),
            status=str(raw.get("status", "")),
            qty_requested=float(qty) if qty is not None else None,
            notional_requested=float(notional) if notional is not None else None,
            qty_filled=float(raw.get("filled_qty", 0.0)),
            filled_avg_price=float(filled_avg) if filled_avg is not None else None,
            submitted_at=str(raw.get("submitted_at", "")) or None,
            updated_at=str(raw.get("updated_at", "")) or None,
            raw=raw,
        )

    def _submit_order(self, body: dict[str, Any]) -> OrderRecord:
        """Submit an order after kill-switch and market-open checks."""
        self._assert_no_kill_switch()
        self._require_market_open()
        raw = self._request("POST", "/orders", body=body)
        return self._parse_order(raw)

    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        client_order_id: str,
        time_in_force: str = "day",
    ) -> OrderRecord:
        """Submit a whole-share market order."""
        body = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": "market",
            "time_in_force": time_in_force,
            "client_order_id": client_order_id,
        }
        return self._submit_order(body)

    def submit_notional_order(
        self,
        symbol: str,
        notional: float,
        side: str,
        client_order_id: str,
        time_in_force: str = "day",
    ) -> OrderRecord:
        """Submit a fractional (notional) market order."""
        body = {
            "symbol": symbol.upper(),
            "notional": str(notional),
            "side": side.lower(),
            "type": "market",
            "time_in_force": time_in_force,
            "client_order_id": client_order_id,
        }
        return self._submit_order(body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel a single open order by Alpaca order ID."""
        return self._request("DELETE", f"/orders/{order_id}")

    def cancel_all_orders(self) -> list[dict[str, Any]]:
        """Cancel all open orders."""
        raw = self._request("DELETE", "/orders")
        return raw if isinstance(raw, list) else []

    def refresh_order(self, order_record: OrderRecord) -> OrderRecord:
        """Fetch the latest state of an order from Alpaca."""
        if not order_record.alpaca_order_id:
            return order_record
        raw = self._request("GET", f"/orders/{order_record.alpaca_order_id}")
        return self._parse_order(raw)


def get_default_adapter(
    paper: bool = True,
    market_open_required: bool = True,
) -> AlpacaTradingAdapter:
    """Return a default adapter using environment credentials."""
    return AlpacaTradingAdapter(paper=paper, market_open_required=market_open_required)

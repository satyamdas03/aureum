"""Execution backends that turn target portfolios into actual or simulated trades.

The protocol separates *strategy logic* (what target weights/values to hold)
from *execution mechanics* (how to move the portfolio to that target).  This
lets the same strategy YAML run either as a deterministic historical backtest
or as a live Alpaca paper-trading rebalance with minimal code change.
"""

from __future__ import annotations

import datetime as dt
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .backtest import BacktestRunner, DimensionalError, MarketData
from .certificate import LiveTradingCertificate
from .quantity import DOLLARS, PRICE_PER_SHARE, SHARE_COUNT, USD, Quantity, Unit
from .strategy import Strategy
from .trading import (
    AccountSnapshot,
    AlpacaTradingAdapter,
    AureumTradingError,
    OrderRecord,
    PositionRecord,
)


@dataclass
class TargetPortfolio:
    """The strategy output for a single rebalance date."""

    date: dt.date
    target_values: dict[str, float]
    target_weights: dict[str, float]
    prices: dict[str, float]
    portfolio_meta: dict[str, Any] | None = None
    scores: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "date": self.date.isoformat(),
            "target_values": {s: round(v, 4) for s, v in sorted(self.target_values.items())},
            "target_weights": {s: round(w, 6) for s, w in sorted(self.target_weights.items())},
            "prices": {s: round(p, 4) for s, p in sorted(self.prices.items())},
            "portfolio_meta": self.portfolio_meta,
        }
        if self.scores is not None:
            out["scores"] = {s: round(v, 6) for s, v in sorted(self.scores.items())}
        return out


@dataclass
class ExecutionContext:
    """Execution state passed to every backend invocation."""

    date: dt.date
    current_positions: dict[str, float]
    cash: float
    slippage: float
    market_data: MarketData | None = None


@dataclass
class ExecutionResult:
    """Outcome of a single rebalance execution."""

    positions: dict[str, float]
    cash: float
    trades: int
    turnover_notional: float
    orders: Sequence[OrderRecord | dict[str, Any]]
    dimensional_errors: list[DimensionalError] = field(default_factory=list)
    account_snapshot: AccountSnapshot | None = None
    pre_trade_positions: list[PositionRecord] = field(default_factory=list)
    post_trade_positions: list[PositionRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": {s: round(q, 6) for s, q in sorted(self.positions.items())},
            "cash": round(self.cash, 4),
            "trades": self.trades,
            "turnover_notional": round(self.turnover_notional, 4),
            "orders": [
                o.to_dict() if isinstance(o, OrderRecord) else dict(o) for o in self.orders
            ],
            "dimensional_errors": [
                {"step": e.step, "message": e.message} for e in self.dimensional_errors
            ],
            "account_snapshot": self.account_snapshot.to_dict()
            if self.account_snapshot
            else None,
            "pre_trade_positions": [p.to_dict() for p in self.pre_trade_positions],
            "post_trade_positions": [p.to_dict() for p in self.post_trade_positions],
            "errors": self.errors,
        }


class ExecutionBackend(Protocol):
    """Abstract interface between strategy logic and trade execution."""

    def execute(
        self,
        target: TargetPortfolio,
        context: ExecutionContext,
    ) -> ExecutionResult:
        ...


class SimulatedExecutionBackend:
    """Backend that fills target trades at the current close price with slippage.

    This is the historical backtest execution engine.  It uses the ``Quantity``
    dimensional system so the simulator catches unit mistakes exactly like the
    original in-process code did.
    """

    def execute(
        self,
        target: TargetPortfolio,
        context: ExecutionContext,
    ) -> ExecutionResult:
        current_positions = context.current_positions
        cash = context.cash
        slippage = context.slippage

        new_positions: dict[str, Quantity] = {}
        new_cash = Quantity(cash, Unit.base(USD), "cash")
        trades = 0
        turnover_notional = 0.0
        dimensional_errors: list[DimensionalError] = []
        orders: list[dict[str, Any]] = []

        relevant = set(target.target_values.keys()) | set(current_positions.keys())
        market_data = context.market_data
        for symbol in relevant:
            raw_price = target.prices.get(symbol)
            if (raw_price is None or raw_price <= 0) and market_data is not None:
                raw_price = market_data.price(target.date, symbol)
            if raw_price is None or raw_price <= 0:
                if symbol in current_positions:
                    new_positions[symbol] = Quantity(
                        current_positions[symbol], SHARE_COUNT, "carry"
                    )
                continue

            price = Quantity(raw_price, PRICE_PER_SHARE, f"price:{symbol}")
            target_value = Quantity(
                target.target_values.get(symbol, 0.0), DOLLARS, "target_value"
            )
            current_shares = Quantity(
                current_positions.get(symbol, 0.0), SHARE_COUNT, "current"
            )

            try:
                target_shares = target_value.divide(price)
                delta_shares = target_shares.add(
                    Quantity(-current_shares.value, SHARE_COUNT, "neg_current")
                )

                if delta_shares.value > 0:
                    exec_price = price.multiply(
                        Quantity(1.0 + slippage, Unit.dimensionless(), "slippage")
                    )
                else:
                    exec_price = price.multiply(
                        Quantity(1.0 - slippage, Unit.dimensionless(), "slippage")
                    )

                adjusted_delta_qty = target_value.divide(exec_price).add(
                    Quantity(-current_shares.value, SHARE_COUNT, "neg_current")
                )
                new_positions[symbol] = current_shares.add(adjusted_delta_qty)
                cash_spent = adjusted_delta_qty.multiply(exec_price)
                new_cash = new_cash.add(
                    Quantity(-cash_spent.value, DOLLARS, "cash_spent")
                )

                adjusted_delta = adjusted_delta_qty.value
                if abs(adjusted_delta) > 1e-9:
                    trades += 1
                turnover_notional += abs(cash_spent.value)

                orders.append(
                    {
                        "symbol": symbol,
                        "side": "buy" if adjusted_delta > 0 else "sell",
                        "qty": round(adjusted_delta, 6),
                        "exec_price": round(exec_price.value, 4),
                        "slippage": round(slippage, 6),
                        "simulated": True,
                    }
                )
            except (ValueError, ZeroDivisionError) as exc:
                dimensional_errors.append(
                    DimensionalError(
                        step=f"rebalance:{target.date}:{symbol}", message=str(exc)
                    )
                )
                new_positions[symbol] = current_shares

        # Drop positions that round to zero and convert to floats.
        float_positions = {
            s: v.value
            for s, v in new_positions.items()
            if abs(v.value) > 1e-9
        }

        return ExecutionResult(
            positions=float_positions,
            cash=new_cash.value,
            trades=trades,
            turnover_notional=turnover_notional,
            orders=orders,
            dimensional_errors=dimensional_errors,
        )


@dataclass
class LiveTradingConfig:
    """Safety and operational parameters for live Alpaca paper trading."""

    max_single_position_pct: float = 0.25
    max_total_invested_pct: float = 0.95
    max_positions: int = 20
    min_order_notional: float = 1.00
    fill_timeout_seconds: float = 30.0
    poll_interval_seconds: float = 2.0
    use_notional_orders: bool = True
    market_open_required: bool = True
    dry_run: bool = False
    paper: bool = True

    @classmethod
    def from_strategy_spec(cls, spec: dict[str, Any], overrides: dict[str, Any] | None = None) -> LiveTradingConfig:
        """Build a live-trading config from ``spec.execution`` and CLI overrides."""
        execution = spec.get("execution", {})
        cfg = cls(
            max_single_position_pct=float(
                execution.get("max_single_position_pct", 0.25)
            ),
            max_total_invested_pct=float(
                execution.get("max_total_invested_pct", 0.95)
            ),
            max_positions=int(execution.get("max_positions", 20)),
            min_order_notional=float(execution.get("min_order_notional", 1.00)),
            fill_timeout_seconds=float(execution.get("fill_timeout_seconds", 30.0)),
            poll_interval_seconds=float(execution.get("poll_interval_seconds", 2.0)),
            use_notional_orders=bool(execution.get("use_notional_orders", True)),
        )
        if overrides:
            for key, value in overrides.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, type(getattr(cfg, key))(value))
        return cfg


class AlpacaPaperExecutionBackend:
    """Execute a target portfolio against an Alpaca paper (or live) account.

    The backend fetches the live account snapshot and open positions, computes
    share deltas, applies risk guardrails, submits diff orders, polls for fills,
    and returns a structured ``ExecutionResult``.
    """

    def __init__(
        self,
        adapter: AlpacaTradingAdapter,
        config: LiveTradingConfig,
        run_id: str | None = None,
    ) -> None:
        self.adapter = adapter
        self.config = config
        self.run_id = run_id or uuid.uuid4().hex[:12]

    def execute(
        self,
        target: TargetPortfolio,
        context: ExecutionContext,
    ) -> ExecutionResult:
        account = self.adapter.get_account()
        pre_positions = self.adapter.get_positions()
        current_by_symbol = {p.symbol: p.qty for p in pre_positions}

        target_values = dict(target.target_values)
        prices = target.prices

        # 1. Validate target values fit within guardrails.
        errors = self._validate_guardrails(target_values, account)
        if errors:
            return ExecutionResult(
                positions=current_by_symbol,
                cash=account.cash,
                trades=0,
                turnover_notional=0.0,
                orders=[],
                account_snapshot=account,
                pre_trade_positions=pre_positions,
                errors=errors,
            )

        # 2. Compute target quantities and deltas.
        deltas: list[tuple[str, float, float]] = []  # symbol, delta_qty, target_qty
        for symbol, value in target_values.items():
            price = prices.get(symbol)
            if price is None or price <= 0:
                continue
            current_qty = current_by_symbol.get(symbol, 0.0)
            target_qty = value / price
            delta = target_qty - current_qty
            notional = abs(delta * price)
            if notional < self.config.min_order_notional:
                continue
            deltas.append((symbol, delta, target_qty))

        if not deltas:
            return ExecutionResult(
                positions=current_by_symbol,
                cash=account.cash,
                trades=0,
                turnover_notional=0.0,
                orders=[],
                account_snapshot=account,
                pre_trade_positions=pre_positions,
            )

        # 3. In dry-run mode, return intended orders without submitting.
        if self.config.dry_run:
            intended_orders = [
                {
                    "symbol": symbol,
                    "side": "buy" if delta > 0 else "sell",
                    "delta_qty": round(delta, 6),
                    "target_qty": round(target_qty, 6),
                    "estimated_notional": round(abs(delta * prices[symbol]), 4),
                    "dry_run": True,
                }
                for symbol, delta, target_qty in deltas
            ]
            return ExecutionResult(
                positions=current_by_symbol,
                cash=account.cash,
                trades=0,
                turnover_notional=0.0,
                orders=intended_orders,
                account_snapshot=account,
                pre_trade_positions=pre_positions,
                errors=[],
            )

        # 4. Submit orders with deterministic client order IDs.
        submitted: list[OrderRecord] = []
        for symbol, delta, _target_qty in deltas:
            side = "buy" if delta > 0 else "sell"
            client_order_id = f"aureum-{self.run_id}-{symbol}-{side}"
            try:
                if self.config.use_notional_orders:
                    notional = abs(delta * prices[symbol])
                    order = self.adapter.submit_notional_order(
                        symbol=symbol,
                        notional=notional,
                        side=side,
                        client_order_id=client_order_id,
                    )
                else:
                    order = self.adapter.submit_market_order(
                        symbol=symbol,
                        qty=abs(delta),
                        side=side,
                        client_order_id=client_order_id,
                    )
                submitted.append(order)
            except AureumTradingError as exc:
                errors.append(f"{symbol}: {exc}")

        # 5. Poll fills up to the configured timeout.
        polled = self._poll_fills(submitted)

        # 6. Capture post-trade state.
        post_positions = self.adapter.get_positions()
        post_by_symbol = {p.symbol: p.qty for p in post_positions}
        turnover = sum(
            abs(o.qty_filled * (o.filled_avg_price or prices.get(o.symbol, 0.0)))
            for o in polled
        )
        trades = sum(1 for o in polled if o.qty_filled > 0)

        return ExecutionResult(
            positions=post_by_symbol,
            cash=account.cash,
            trades=trades,
            turnover_notional=turnover,
            orders=polled,
            account_snapshot=account,
            pre_trade_positions=pre_positions,
            post_trade_positions=post_positions,
            errors=errors,
        )

    def _validate_guardrails(
        self,
        target_values: dict[str, float],
        account: AccountSnapshot,
    ) -> list[str]:
        """Return a list of risk-guardrail violations, empty if all pass."""
        errors: list[str] = []
        equity = account.equity
        if equity <= 0:
            errors.append(f"Account equity is non-positive: {equity}")
            return errors

        total_target = sum(target_values.values())
        if total_target > equity * self.config.max_total_invested_pct:
            errors.append(
                f"Total target value ${total_target:.2f} exceeds "
                f"max_total_invested_pct={self.config.max_total_invested_pct:.0%} "
                f"of equity ${equity:.2f}"
            )

        max_position = max(target_values.values()) if target_values else 0.0
        if max_position > equity * self.config.max_single_position_pct:
            errors.append(
                f"Single-name target ${max_position:.2f} exceeds "
                f"max_single_position_pct={self.config.max_single_position_pct:.0%} "
                f"of equity ${equity:.2f}"
            )

        if len(target_values) > self.config.max_positions:
            errors.append(
                f"Target portfolio has {len(target_values)} positions, "
                f"max_positions={self.config.max_positions}"
            )

        return errors

    def _poll_fills(self, orders: list[OrderRecord]) -> list[OrderRecord]:
        """Refresh submitted orders until they fill or the timeout elapses."""
        deadline = time.monotonic() + self.config.fill_timeout_seconds
        out = list(orders)
        terminal = {"filled", "canceled", "expired", "rejected"}
        pending = {i for i, o in enumerate(out) if o.status not in terminal}
        while pending and time.monotonic() < deadline:
            for idx in list(pending):
                try:
                    refreshed = self.adapter.refresh_order(out[idx])
                except AureumTradingError:
                    continue
                out[idx] = refreshed
                if refreshed.status in {"filled", "canceled", "expired", "rejected"}:
                    pending.discard(idx)
            if pending:
                time.sleep(self.config.poll_interval_seconds)
        return out


def make_paper_backend(
    paper: bool = True,
    dry_run: bool = False,
    market_open_required: bool = True,
    overrides: dict[str, Any] | None = None,
) -> AlpacaPaperExecutionBackend:
    """Factory for the default Alpaca paper backend."""
    adapter = AlpacaTradingAdapter(paper=paper, market_open_required=market_open_required)
    config = LiveTradingConfig.from_strategy_spec({}, overrides=overrides)
    config.dry_run = dry_run
    config.paper = paper
    config.market_open_required = market_open_required
    return AlpacaPaperExecutionBackend(adapter, config)


class LiveRunner:
    """Orchestrate a single live Alpaca paper-trading rebalance.

    The runner loads a strategy and a recent price CSV, computes the target
    portfolio for the latest available date, and hands execution to an
    ``AlpacaPaperExecutionBackend``.  The result is a ``LiveTradingCertificate``
    that can be written to disk for lineage and auditing.
    """

    def __init__(
        self,
        strategy: Strategy,
        data: MarketData,
        data_source: str,
        strategy_path: Path,
        backend: AlpacaPaperExecutionBackend,
    ) -> None:
        self.strategy = strategy
        self.data = data
        self.data_source = data_source
        self.strategy_path = Path(strategy_path)
        self.backend = backend
        self._runner = BacktestRunner(
            strategy,
            data,
            data_source=data_source,
            strategy_path=strategy_path,
        )

    def run(
        self,
        *,
        check_only: bool = False,
        dry_run: bool = False,
    ) -> LiveTradingCertificate:
        """Run one live rebalance and return a certificate."""
        from .certificate import get_environment, hash_file

        run_id = self.backend.run_id
        adapter = self.backend.adapter
        clock = adapter.get_clock()
        account = adapter.get_account()
        pre_positions = adapter.get_positions()

        if self.data.dates:
            latest_date = self.data.dates[-1]
        else:
            latest_date = dt.datetime.now(dt.UTC).date()
        nav = account.equity

        _spec, portfolio_spec, signal_fn, ascending, top_n = self._runner._strategy_setup()
        target = self._runner.compute_target_portfolio(
            latest_date,
            nav,
            portfolio_spec=portfolio_spec,
            signal_fn=signal_fn,
            ascending=ascending,
            top_n=top_n,
        )

        if check_only:
            from aureum import __version__

            return LiveTradingCertificate.from_run(
                environment=get_environment(
                    aureum_version=__version__, cwd=self.strategy_path.parent
                ),
                run_id=run_id,
                strategy_path=str(self.strategy_path),
                strategy_sha256=hash_file(self.strategy_path),
                live_mode="paper-check-only",
                market_clock=clock.to_dict(),
                pre_trade_account=account.to_dict(),
                post_trade_account=account.to_dict(),
                target_portfolio=target.to_dict(),
                current_positions=[p.to_dict() for p in pre_positions],
                orders=[],
                risk_checks=[],
                errors=[],
                data_path=self.data_source,
                data_sha256=hash_file(self.data_source) if Path(self.data_source).exists() else None,
                metadata={"check_only": True, "dry_run": False},
            )

        # Dry-run still goes through the backend so risk checks run.
        self.backend.config.dry_run = dry_run
        context = ExecutionContext(
            date=latest_date,
            current_positions={p.symbol: p.qty for p in pre_positions},
            cash=account.cash,
            slippage=0.0,
            market_data=self.data,
        )
        exec_result = self.backend.execute(target, context)

        post_account = account
        post_positions = pre_positions
        if not dry_run:
            try:
                post_account = adapter.get_account()
                post_positions = adapter.get_positions()
            except AureumTradingError as exc:
                exec_result.errors.append(str(exc))

        from aureum import __version__

        env = get_environment(
            aureum_version=__version__, cwd=self.strategy_path.parent
        )

        return LiveTradingCertificate.from_run(
            environment=env,
            run_id=run_id,
            strategy_path=str(self.strategy_path),
            strategy_sha256=hash_file(self.strategy_path),
            live_mode="paper-dry-run" if dry_run else "paper",
            market_clock=clock.to_dict(),
            pre_trade_account=account.to_dict(),
            post_trade_account=post_account.to_dict(),
            target_portfolio=target.to_dict(),
            current_positions=[p.to_dict() for p in post_positions],
            orders=[o.to_dict() for o in exec_result.orders if isinstance(o, OrderRecord)],
            risk_checks=[],  # populated by backend errors are not structured risk checks
            errors=list(exec_result.errors),
            data_path=self.data_source,
            data_sha256=hash_file(self.data_source) if Path(self.data_source).exists() else None,
            metadata={"check_only": False, "dry_run": dry_run},
        )

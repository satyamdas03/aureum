"""Deterministic backtest runner for the Aureum Quant Kernel.

This MVP implementation is intentionally dependency-light: it uses only the
standard library plus PyYAML (already required).  A future iteration can swap
the CSV store for Polars/Pandas or the Rust execution engine.
"""

from __future__ import annotations

import csv
import datetime as dt
import itertools
import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from aureum.certificate import (
    BacktestCertificate,
    Environment,
    ExecutionSummary,
    InputLineage,
    Inputs,
    PortfolioConstruction,
    Results,
    hash_file,
)
from aureum.graph import EntityType, KnowledgeGraph, Relation
from aureum.mpt import (
    OptimizationInputs,
    estimate_covariance,
    estimate_mean_returns,
    optimize_maximum_sharpe,
    optimize_mean_variance,
    optimize_minimum_variance,
    optimize_min_cvar,
    optimize_risk_parity,
)
from aureum.quantity import (
    DOLLARS,
    PRICE_PER_SHARE,
    SHARE_COUNT,
    USD,
    Quantity,
    Unit,
)
from aureum.strategy import Strategy
from aureum.verifier import verify_constraints


def _momentum_12_1(closes: list[float]) -> float:
    """12-month total return minus the most recent month total return.

    Expects ``closes`` ordered from oldest to newest, where the last element
    is the current close.  Needs at least 252 historical closes preceding the
    current one (253 total).
    """
    if len(closes) < 253:
        return float("nan")
    current = closes[-1]
    month_ago = closes[-22]  # ~21 trading days + current
    year_ago = closes[-253]  # ~252 trading days + current
    return (current / year_ago - 1.0) - (current / month_ago - 1.0)


def _volatility_20d(closes: list[float]) -> float:
    """Annualized realized volatility over the trailing 20 trading days.

    Higher values rank more volatile stocks first (use ascending=false for
    low-volatility screens). Needs at least 20 closes.
    """
    window = 20
    if len(closes) < window:
        return float("nan")
    recent = closes[-window:]
    returns = [
        recent[i] / recent[i - 1] - 1.0 for i in range(1, len(recent))
    ]
    if len(returns) < 2:
        return float("nan")
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    return std * math.sqrt(252)


def _sharpe_63d(closes: list[float]) -> float:
    """63-trading-day Sharpe-like ratio: annualized return / annualized vol.

    A rough risk-adjusted return signal. Needs at least 64 closes.
    """
    window = 63
    if len(closes) < window + 1:
        return float("nan")
    recent = closes[-(window + 1) :]
    total_return = recent[-1] / recent[0] - 1.0
    returns = [
        recent[i] / recent[i - 1] - 1.0 for i in range(1, len(recent))
    ]
    if len(returns) < 2:
        return float("nan")
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return float("nan")
    annual_return = total_return * (252 / window)
    annual_vol = std * math.sqrt(252)
    return annual_return / annual_vol


def _mean_reversion_5_20(closes: list[float]) -> float:
    """Z-score of the latest close against its trailing 20-day mean.

    Positive = price is above the mean (potential short / mean-reversion sell).
    Negative = price is below the mean (potential buy). Use ascending=true to
    buy the most beaten-down names. Needs at least 20 closes.
    """
    window = 20
    if len(closes) < window:
        return float("nan")
    recent = closes[-window:]
    mean = sum(recent) / len(recent)
    variance = sum((p - mean) ** 2 for p in recent) / len(recent)
    std = math.sqrt(variance)
    if std == 0:
        return float("nan")
    return (recent[-1] - mean) / std


# Registry of named signals referenced by ``spec.ranking.by``.
_SIGNALS: dict[str, Callable[[list[float]], float]] = {
    "momentum_12_1": _momentum_12_1,
    "volatility_20d": _volatility_20d,
    "sharpe_63d": _sharpe_63d,
    "mean_reversion_5_20": _mean_reversion_5_20,
}


class MarketData:
    """In-memory CSV price store with deterministic ordering."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
        all_dates: set[dt.date] = set()

        for row in rows:
            date = dt.date.fromisoformat(row["date"])
            symbol = row["symbol"]
            close = float(row["close"])
            volume = int(row["volume"])
            sector = row.get("sector", "")
            all_dates.add(date)
            by_symbol[symbol].append(
                {"date": date, "close": close, "volume": volume, "sector": sector}
            )

        for records in by_symbol.values():
            records.sort(key=lambda r: r["date"])

        self._by_symbol: dict[str, list[dict[str, Any]]] = dict(by_symbol)
        self._symbols = sorted(self._by_symbol.keys())
        self._dates = sorted(all_dates)

        self._price_index: dict[tuple[dt.date, str], dict[str, Any]] = {}
        for symbol, records in self._by_symbol.items():
            for rec in records:
                self._price_index[(rec["date"], symbol)] = rec

    @classmethod
    def from_csv(cls, path: str | Path) -> MarketData:
        with Path(path).open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return cls(rows)

    @property
    def dates(self) -> list[dt.date]:
        return self._dates.copy()

    @property
    def symbols(self) -> list[str]:
        return self._symbols.copy()

    def price(self, date: dt.date, symbol: str) -> float | None:
        rec = self._price_index.get((date, symbol))
        return rec["close"] if rec else None

    def volume(self, date: dt.date, symbol: str) -> int | None:
        rec = self._price_index.get((date, symbol))
        return rec["volume"] if rec else None

    def sector(self, symbol: str) -> str | None:
        recs = self._by_symbol.get(symbol)
        return recs[0]["sector"] if recs else None

    def closes(self, symbol: str) -> list[float]:
        return [rec["close"] for rec in self._by_symbol.get(symbol, [])]

    def closes_up_to(self, date: dt.date, symbol: str) -> list[float]:
        out = []
        for rec in self._by_symbol.get(symbol, []):
            if rec["date"] <= date:
                out.append(rec["close"])
            else:
                break
        return out


@dataclass
class DimensionalError:
    """Record of a unit-mismatch caught during execution."""

    step: str
    message: str


@dataclass
class BacktestResult:
    """Serializable backtest report."""

    strategy_name: str
    data_source: str
    start_date: str
    end_date: str
    initial_nav: float
    final_nav: float
    total_return: float
    cagr: float
    volatility_annual: float
    sharpe_ratio: float | None
    max_drawdown: float
    trades: int
    turnover_annual: float
    max_leverage: float
    max_concentration: float
    dimensional_errors: list[DimensionalError]
    daily_nav: list[dict[str, Any]] = field(default_factory=list)
    daily_positions: list[dict[str, Any]] = field(default_factory=list)
    rebalance_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "data_source": self.data_source,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_nav": round(self.initial_nav, 4),
            "final_nav": round(self.final_nav, 4),
            "total_return": round(self.total_return, 6),
            "cagr": round(self.cagr, 6),
            "volatility_annual": round(self.volatility_annual, 6),
            "sharpe_ratio": round(self.sharpe_ratio, 4)
            if self.sharpe_ratio is not None
            else None,
            "max_drawdown": round(self.max_drawdown, 6),
            "trades": self.trades,
            "turnover_annual": round(self.turnover_annual, 6),
            "max_leverage": round(self.max_leverage, 6),
            "max_concentration": round(self.max_concentration, 6),
            "dimensional_errors": [
                {"step": e.step, "message": e.message} for e in self.dimensional_errors
            ],
            "daily_nav": self.daily_nav,
            "daily_positions": self.daily_positions,
            "rebalance_log": self.rebalance_log,
        }


class BacktestRunner:
    """Run a strategy against a CSV price history."""

    def __init__(
        self,
        strategy: Strategy,
        data: MarketData,
        *,
        data_source: str = "csv",
        initial_nav: float = 1_000_000.0,
    ) -> None:
        self.strategy = strategy
        self.data = data
        self.data_source = data_source
        self.initial_nav = initial_nav

    def run(self) -> BacktestResult:
        spec = self.strategy.spec
        universe = spec["universe"]
        execution = spec["execution"]
        slippage = execution.get("slippage", 0.0)

        portfolio_spec = self.strategy.portfolio()

        if portfolio_spec is None:
            ranking = spec["ranking"]
            weights = spec["weights"]
            signal_name = ranking["by"]
            ascending = ranking.get("ascending", False)
            top_n = weights.get("top_n", 1.0)
            signal_fn = _SIGNALS.get(signal_name)
            if signal_fn is None:
                raise ValueError(f"unknown signal: {signal_name!r}")
        else:
            signal_fn = None
            ascending = False
            top_n = 1.0

        positions: dict[str, Quantity] = {}
        cash = Quantity(self.initial_nav, Unit.base(USD), "initial_nav")
        daily_nav: list[dict[str, Any]] = []
        daily_positions: list[dict[str, Any]] = []
        rebalance_log: list[dict[str, Any]] = []
        dimensional_errors: list[DimensionalError] = []
        trades = 0
        cumulative_turnover = 0.0
        max_leverage = 0.0
        max_concentration = 0.0

        rebalance_dates = self._rebalance_dates()

        for date in self.data.dates:
            nav = self._portfolio_value(date, positions, cash)
            daily_nav.append({"date": date.isoformat(), "nav": round(nav, 4)})

            gross_value = self._gross_position_value(date, positions)
            leverage = gross_value / nav if nav > 0 else 0.0
            concentration = (
                self._max_position_value(date, positions) / nav if nav > 0 else 0.0
            )
            max_leverage = max(max_leverage, leverage)
            max_concentration = max(max_concentration, concentration)
            daily_positions.append(
                {
                    "date": date.isoformat(),
                    "cash": round(cash.value, 4),
                    "positions": {s: round(v.value, 6) for s, v in sorted(positions.items())},
                    "leverage": round(leverage, 6),
                    "concentration": round(concentration, 6),
                }
            )

            if date in rebalance_dates:
                candidates = self._eligible_universe(date, universe)

                if portfolio_spec is not None:
                    target_values, portfolio_meta = self._portfolio_target_values(
                        date, candidates, nav, portfolio_spec
                    )
                    selected = sorted(target_values.keys())
                    scores: dict[str, float] = {}
                else:
                    scores = {}
                    for symbol in candidates:
                        closes = self.data.closes_up_to(date, symbol)
                        score = signal_fn(closes)  # type: ignore[misc]
                        if not math.isnan(score):
                            scores[symbol] = score

                    if not scores:
                        continue

                    ranked = sorted(
                        scores.items(), key=lambda item: item[1], reverse=not ascending
                    )
                    select_count = max(1, round(len(ranked) * top_n))
                    selected = [symbol for symbol, _ in ranked[:select_count]]

                    target_weight = 1.0 / len(selected)
                    target_values = {s: nav * target_weight for s in selected}
                    portfolio_meta = None

                new_positions: dict[str, Quantity] = {}
                new_cash = cash
                turnover_notional = 0.0
                relevant_symbols = set(selected) | set(positions.keys())
                for symbol in relevant_symbols:
                    raw_price = self.data.price(date, symbol)
                    if raw_price is None or raw_price <= 0:
                        continue

                    price = Quantity(raw_price, PRICE_PER_SHARE, f"price:{symbol}")
                    target_value = Quantity(
                        target_values.get(symbol, 0.0), DOLLARS, "target_value"
                    )
                    current_shares = positions.get(
                        symbol, Quantity(0.0, SHARE_COUNT, "zero")
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
                    except (ValueError, ZeroDivisionError) as exc:
                        dimensional_errors.append(
                            DimensionalError(
                                step=f"rebalance:{date}:{symbol}", message=str(exc)
                            )
                        )
                        new_positions[symbol] = current_shares

                positions = {s: v for s, v in new_positions.items() if abs(v.value) > 1e-9}
                cash = new_cash
                cumulative_turnover += turnover_notional / nav if nav > 0 else 0.0

                log_entry: dict[str, Any] = {
                    "date": date.isoformat(),
                    "selected": selected,
                    "nav": round(nav, 4),
                }
                if scores:
                    log_entry["scores"] = {s: round(scores[s], 6) for s in selected}
                if portfolio_meta is not None:
                    log_entry["portfolio"] = portfolio_meta
                rebalance_log.append(log_entry)

        final_nav = daily_nav[-1]["nav"] if daily_nav else self.initial_nav
        total_return = final_nav / self.initial_nav - 1.0
        cagr = self._cagr(total_return)
        vol, sharpe = self._sharpe(daily_nav)
        max_dd = self._max_drawdown(daily_nav)

        return BacktestResult(
            strategy_name=self.strategy.metadata.get("name", "unnamed"),
            data_source=self.data_source,
            start_date=self.data.dates[0].isoformat() if self.data.dates else "",
            end_date=self.data.dates[-1].isoformat() if self.data.dates else "",
            initial_nav=self.initial_nav,
            final_nav=final_nav,
            total_return=total_return,
            cagr=cagr,
            volatility_annual=vol,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            trades=trades,
            turnover_annual=cumulative_turnover,
            max_leverage=max_leverage,
            max_concentration=max_concentration,
            dimensional_errors=dimensional_errors,
            daily_nav=daily_nav,
            daily_positions=daily_positions,
            rebalance_log=rebalance_log,
        )

    def _rebalance_dates(self) -> set[dt.date]:
        """Return the first trading day of each month after warm-up."""
        schedule = self.strategy.spec.get("schedule", {})
        frequency = schedule.get("rebalance", "1M")
        lookback_text = schedule.get("lookback", "252d")
        lookback_days = int(lookback_text.rstrip("d"))

        dates = self.data.dates
        if len(dates) <= lookback_days:
            return set()

        if frequency != "1M":
            raise ValueError(f"unsupported rebalance frequency: {frequency!r}")

        eligible = dates[lookback_days:]
        rebalance_dates: set[dt.date] = set()
        prev_month: tuple[int, int] | None = None
        for date in eligible:
            month_key = (date.year, date.month)
            if month_key != prev_month:
                rebalance_dates.add(date)
                prev_month = month_key
        return rebalance_dates

    def _portfolio_target_values(
        self,
        date: dt.date,
        candidates: list[str],
        nav: float,
        portfolio_spec: dict[str, Any],
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Run an MPT optimizer and return dollar target values for each asset."""
        lookback_days = int(portfolio_spec.get("lookback_days", 252))
        objective = portfolio_spec["objective"]
        covariance_estimator = portfolio_spec.get("covariance_estimator", "sample")
        risk_measure = portfolio_spec.get("risk_measure", "variance")
        risk_free_rate = float(portfolio_spec.get("risk_free_rate", 0.0))
        long_only = portfolio_spec.get("long_only", True)
        max_weight = portfolio_spec.get("max_weight")
        min_weight = portfolio_spec.get("min_weight")

        # Gather returns for candidates that have enough history.
        symbols: list[str] = []
        return_matrix: list[list[float]] = []
        for symbol in candidates:
            closes = self.data.closes_up_to(date, symbol)
            if len(closes) < lookback_days + 1:
                continue
            window = closes[-(lookback_days + 1) :]
            rets = [window[i] / window[i - 1] - 1.0 for i in range(1, len(window))]
            if any(math.isnan(r) or math.isinf(r) for r in rets):
                continue
            symbols.append(symbol)
            return_matrix.append(rets)

        if len(symbols) < 2:
            # Not enough assets to optimize; hold cash.
            return {}, {
                "objective": objective,
                "error": "insufficient assets with required lookback",
                "eligible_count": len(symbols),
            }

        returns_arr = np.array(return_matrix).T
        mu = estimate_mean_returns(returns_arr, method="sample")
        cov = estimate_covariance(returns_arr, estimator=covariance_estimator)

        inputs = OptimizationInputs(
            expected_returns=mu,
            covariance=cov,
            risk_free_rate=risk_free_rate,
        )

        if objective == "mean_variance":
            target_return = portfolio_spec.get("target_return")
            target_risk = portfolio_spec.get("target_risk")
            result = optimize_mean_variance(
                inputs,
                target_return=target_return,
                target_risk=target_risk,
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
            )
        elif objective == "minimum_variance":
            result = optimize_minimum_variance(
                inputs,
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
            )
        elif objective == "maximum_sharpe":
            result = optimize_maximum_sharpe(
                inputs,
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
            )
        elif objective == "risk_parity":
            result = optimize_risk_parity(
                inputs,
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
            )
        elif objective == "minimum_cvar":
            alpha = 0.95 if risk_measure == "cvar_95" else 0.99
            result = optimize_min_cvar(
                inputs,
                alpha=alpha,
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
                scenarios=returns_arr,
            )
        else:
            raise ValueError(f"unsupported portfolio objective: {objective!r}")

        target_values = {
            symbol: nav * float(weight)
            for symbol, weight in zip(symbols, result.weights)
            if weight > 1e-12
        }
        meta = {
            "objective": objective,
            "risk_measure": result.risk_measure,
            "expected_return": round(result.expected_return, 8),
            "risk": round(result.risk, 8),
            "covariance_estimator": covariance_estimator,
            "lookback_days": lookback_days,
            "eligible_count": len(symbols),
            "weights": {
                symbol: round(float(weight), 6)
                for symbol, weight in zip(symbols, result.weights)
            },
        }
        return target_values, meta

    def _eligible_universe(
        self, date: dt.date, universe_spec: dict[str, Any]
    ) -> list[str]:
        """Apply sector, price, and ADV filters at a point in time."""
        filters = universe_spec.get("filter", {})
        sector_filter = filters.get("sector")
        min_price = filters.get("min_price")
        min_adv20 = filters.get("min_adv20")

        eligible: list[str] = []
        for symbol in self.data.symbols:
            if sector_filter and self.data.sector(symbol) != sector_filter:
                continue

            price = self.data.price(date, symbol)
            if price is None:
                continue
            if min_price is not None and price < min_price:
                continue

            if min_adv20 is not None:
                adv = self._adv20(date, symbol)
                if adv is None or adv < min_adv20:
                    continue

            eligible.append(symbol)
        return eligible

    def _adv20(self, date: dt.date, symbol: str) -> float | None:
        """Trailing 20-trading-day average dollar volume."""
        records = self.data._by_symbol.get(symbol, [])
        idx = next(
            (i for i, rec in enumerate(records) if rec["date"] == date),
            None,
        )
        if idx is None or idx < 19:
            return None
        window = records[idx - 19 : idx + 1]
        return sum(rec["close"] * rec["volume"] for rec in window) / len(window)

    def _portfolio_value(
        self, date: dt.date, positions: dict[str, Quantity], cash: Quantity
    ) -> float:
        value = cash.value
        for symbol, shares in positions.items():
            raw_price = self.data.price(date, symbol)
            if raw_price is not None:
                value += shares.value * raw_price
        return value

    def _gross_position_value(
        self, date: dt.date, positions: dict[str, Quantity]
    ) -> float:
        return sum(
            abs(qty.value * raw_price)
            for symbol, qty in positions.items()
            if (raw_price := self.data.price(date, symbol)) is not None
        )

    def _max_position_value(
        self, date: dt.date, positions: dict[str, Quantity]
    ) -> float:
        values = [
            abs(qty.value * raw_price)
            for symbol, qty in positions.items()
            if (raw_price := self.data.price(date, symbol)) is not None
        ]
        return max(values) if values else 0.0

    def _cagr(self, total_return: float) -> float:
        dates = self.data.dates
        if len(dates) < 2:
            return 0.0
        years = (dates[-1] - dates[0]).days / 365.25
        if years <= 0:
            return 0.0
        return (1.0 + total_return) ** (1.0 / years) - 1.0

    def _sharpe(self, daily_nav: list[dict[str, Any]]) -> tuple[float, float | None]:
        returns = []
        for prev, cur in itertools.pairwise(daily_nav):
            if prev["nav"] > 0:
                returns.append(cur["nav"] / prev["nav"] - 1.0)
        if len(returns) < 2:
            return 0.0, None
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0, None
        annual_std = std * math.sqrt(252)
        annual_mean = mean * 252
        return annual_std, annual_mean / annual_std

    def _max_drawdown(self, daily_nav: list[dict[str, Any]]) -> float:
        peak = -float("inf")
        max_dd = 0.0
        for point in daily_nav:
            nav = point["nav"]
            peak = max(peak, nav)
            if peak > 0:
                dd = (peak - nav) / peak
                max_dd = max(max_dd, dd)
        return max_dd

    def build_certificate(
        self,
        strategy_path: str | Path,
        data_path: str | Path,
        environment: Environment,
        *,
        graph_persistence: str = "none",
    ) -> BacktestCertificate:
        """Run the backtest and wrap the result in an Aureum Backtest Certificate."""
        from aureum.certificate import (
            ExecutionSummary,
            PortfolioConstruction,
            Results,
        )

        result = self.run()
        constraints = self.strategy.constraints()
        risk_results = verify_constraints(
            constraints,
            max_drawdown=result.max_drawdown,
            max_leverage=result.max_leverage,
            turnover_annual=result.turnover_annual,
            concentration_single_name=result.max_concentration,
        )

        strategy_path = Path(strategy_path)
        data_path = Path(data_path)

        inputs = Inputs(
            strategy=InputLineage(
                path=str(strategy_path),
                sha256=hash_file(strategy_path),
                metadata={"name": result.strategy_name},
            ),
            data=InputLineage(
                path=str(data_path),
                sha256=hash_file(data_path),
                metadata={
                    "symbols": len(self.data.symbols),
                    "dates": len(self.data.dates),
                    "start_date": result.start_date,
                    "end_date": result.end_date,
                },
            ),
        )

        execution = ExecutionSummary(
            start_date=result.start_date,
            end_date=result.end_date,
            initial_nav=result.initial_nav,
            rebalance_count=len(result.rebalance_log),
            trades=result.trades,
        )

        results = Results(
            final_nav=result.final_nav,
            total_return=result.total_return,
            cagr=result.cagr,
            volatility_annual=result.volatility_annual,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            turnover_annual=result.turnover_annual,
        )

        execution_trace = {
            "daily_nav": result.daily_nav,
            "daily_positions": result.daily_positions,
            "rebalance_log": result.rebalance_log,
        }

        portfolio_construction: PortfolioConstruction | None = None
        portfolio_spec = self.strategy.portfolio()
        if portfolio_spec:
            weights_history = [
                {
                    "date": entry["date"],
                    "weights": entry["portfolio"].get("weights", {}),
                    "expected_return": entry["portfolio"].get("expected_return"),
                    "risk": entry["portfolio"].get("risk"),
                }
                for entry in result.rebalance_log
                if "portfolio" in entry
            ]
            constraints = {
                k: v
                for k, v in portfolio_spec.items()
                if k
                not in {
                    "objective",
                    "risk_measure",
                    "covariance_estimator",
                    "risk_free_rate",
                    "lookback_days",
                }
            }
            config_for_hash = {
                "objective": portfolio_spec.get("objective"),
                "risk_measure": portfolio_spec.get("risk_measure", "variance"),
                "covariance_estimator": portfolio_spec.get("covariance_estimator", "sample"),
                "risk_free_rate": portfolio_spec.get("risk_free_rate", 0.0),
                "lookback_days": portfolio_spec.get("lookback_days", 252),
                "constraints": constraints,
            }
            from aureum.certificate import _sha256_text, _stable_json

            portfolio_construction = PortfolioConstruction(
                objective=portfolio_spec["objective"],
                risk_measure=portfolio_spec.get("risk_measure", "variance"),
                covariance_estimator=portfolio_spec.get("covariance_estimator", "sample"),
                risk_free_rate=float(portfolio_spec.get("risk_free_rate", 0.0)),
                constraints=constraints,
                weights_history=weights_history,
                optimization_inputs_hash=_sha256_text(_stable_json(config_for_hash)),
            )

        # Edge 5: build optional semantic knowledge graph.
        knowledge_graph: KnowledgeGraph | None = None
        graph_node_id: str | None = None
        linked_entity_hashes: list[str] = []
        if graph_persistence in {"inline", "bundle"}:
            knowledge_graph, graph_node_id, linked_entity_hashes = self._build_knowledge_graph(
                strategy_path=strategy_path,
                data_path=data_path,
                inputs=inputs,
                execution=execution,
                results=results,
                portfolio_construction=portfolio_construction,
                result=result,
                environment=environment,
            )

        return BacktestCertificate.from_run(
            environment=environment,
            inputs=inputs,
            execution=execution,
            results=results,
            risk_constraints=risk_results,
            execution_trace=execution_trace,
            portfolio_construction=portfolio_construction,
            graph_node_id=graph_node_id,
            linked_entity_hashes=linked_entity_hashes,
            knowledge_graph=knowledge_graph,
        )

    def _build_knowledge_graph(
        self,
        *,
        strategy_path: Path,
        data_path: Path,
        inputs: Inputs,
        execution: ExecutionSummary,
        results: Results,
        portfolio_construction: PortfolioConstruction | None,
        result: BacktestResult,
        environment: Environment,
    ) -> tuple[KnowledgeGraph, str, list[str]]:
        """Construct the semantic knowledge graph for this backtest run."""
        from aureum.certificate import _sha256_text, _stable_json

        graph = KnowledgeGraph()

        strategy_payload = {
            "api_version": self.strategy.api_version,
            "kind": self.strategy.kind,
            "name": self.strategy.metadata.get("name"),
            "spec": self.strategy.spec,
        }
        strategy_node = graph.add_entity(
            EntityType.STRATEGY, strategy_payload, source_path=str(strategy_path)
        )

        data_payload = {
            "sha256": inputs.data.sha256,
            "symbols": sorted(self.data.symbols),
            "dates": len(self.data.dates),
            "start_date": result.start_date,
            "end_date": result.end_date,
        }
        data_node = graph.add_entity(
            EntityType.DATA_SNAPSHOT, data_payload, source_path=str(data_path)
        )

        signal_nodes: list[Any] = []
        for signal in self.strategy.spec.get("signals", []):
            signal_payload = {
                "name": signal.get("name"),
                "expr": signal.get("expr"),
                "type": signal.get("type"),
            }
            signal_nodes.append(graph.add_entity(EntityType.SIGNAL, signal_payload))

        risk_model_node: Any | None = None
        portfolio_recipe_node: Any | None = None
        if portfolio_construction is not None:
            risk_model_payload = {
                "objective": portfolio_construction.objective,
                "risk_measure": portfolio_construction.risk_measure,
                "covariance_estimator": portfolio_construction.covariance_estimator,
                "risk_free_rate": portfolio_construction.risk_free_rate,
                "constraints": portfolio_construction.constraints,
            }
            risk_model_node = graph.add_entity(EntityType.RISK_MODEL, risk_model_payload)
            final_weights = (
                portfolio_construction.weights_history[-1].get("weights", {})
                if portfolio_construction.weights_history
                else {}
            )
            recipe_payload = {
                "optimization_inputs_hash": portfolio_construction.optimization_inputs_hash,
                "final_weights": final_weights,
            }
            portfolio_recipe_node = graph.add_entity(
                EntityType.PORTFOLIO_RECIPE, recipe_payload
            )

        position_nodes: list[Any] = []
        daily_positions_by_date = {dp["date"]: dp for dp in result.daily_positions}
        for entry in result.rebalance_log:
            date = entry["date"]
            dp = daily_positions_by_date.get(date, {})
            position_payload = {
                "date": date,
                "positions": dp.get("positions", {}),
                "leverage": dp.get("leverage", 0.0),
                "concentration": dp.get("concentration", 0.0),
            }
            position_nodes.append(graph.add_entity(EntityType.POSITION_SET, position_payload))

        run_payload = {
            "start_date": result.start_date,
            "end_date": result.end_date,
            "initial_nav": result.initial_nav,
            "rebalance_count": len(result.rebalance_log),
            "trades": result.trades,
        }
        run_node = graph.add_entity(EntityType.BACKTEST_RUN, run_payload)

        input_hash = _sha256_text(_stable_json(inputs.to_dict()))
        result_hash = _sha256_text(_stable_json(results.to_dict()))
        certificate_payload = {
            "aureum_version": environment.aureum_version,
            "certificate_spec_version": "1.0",
            "generated_at": dt.datetime.now(dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "determinism": {
                "input_hash": input_hash,
                "result_hash": result_hash,
            },
        }
        cert_node = graph.add_entity(EntityType.CERTIFICATE, certificate_payload)

        graph.add_relation(
            Relation.BACKTEST_INPUT, cert_node.entity_id, strategy_node.entity_id
        )
        graph.add_relation(
            Relation.BACKTEST_INPUT, cert_node.entity_id, data_node.entity_id
        )
        graph.add_relation(
            Relation.GENERATED_BY, cert_node.entity_id, run_node.entity_id
        )
        for signal_node in signal_nodes:
            graph.add_relation(
                Relation.USES_SIGNAL, run_node.entity_id, signal_node.entity_id
            )
        if risk_model_node is not None:
            graph.add_relation(
                Relation.CALIBRATED_WITH, run_node.entity_id, risk_model_node.entity_id
            )
        if portfolio_recipe_node is not None:
            graph.add_relation(
                Relation.DERIVED_FROM, run_node.entity_id, portfolio_recipe_node.entity_id
            )
        for position_node in position_nodes:
            graph.add_relation(
                Relation.BACKTEST_OUTPUT, run_node.entity_id, position_node.entity_id
            )

        linked_hashes = self._resolve_links(graph, strategy_path.parent)
        for linked_id in linked_hashes:
            graph.add_relation(
                Relation.DEPENDS_ON, strategy_node.entity_id, linked_id
            )

        return graph, cert_node.entity_id, linked_hashes

    def _resolve_links(
        self,
        graph: KnowledgeGraph,
        strategy_dir: Path,
    ) -> list[str]:
        """Resolve ``metadata.links`` to entity IDs and add edges to the graph."""
        import warnings

        linked_hashes: list[str] = []
        for link in self.strategy.links():
            if isinstance(link, str):
                entity_id = link
                if graph.has_entity(entity_id):
                    graph.add_relation(
                        Relation.DEPENDS_ON,
                        self._strategy_node_id(graph),
                        entity_id,
                    )
                else:
                    warnings.warn(
                        f"metadata.links entity_id '{entity_id}' not present in graph; "
                        "recording hash without edge"
                    )
                linked_hashes.append(entity_id)
                continue

            if not isinstance(link, dict):
                warnings.warn(
                    f"metadata.links entry ignored: unexpected type {type(link).__name__}"
                )
                continue

            entity_id = link.get("entity_id")
            path = link.get("path")
            relation_value = link.get("relation", Relation.DEPENDS_ON.value)
            relation = Relation(relation_value)

            if entity_id:
                linked_hashes.append(entity_id)
                if graph.has_entity(entity_id):
                    graph.add_relation(
                        relation, self._strategy_node_id(graph), entity_id
                    )
                else:
                    warnings.warn(
                        f"metadata.links entity_id '{entity_id}' not present in graph; "
                        "recording hash without edge"
                    )
                continue

            if path:
                full_path = Path(path) if Path(path).is_absolute() else strategy_dir / path
                if full_path.exists():
                    file_hash = hash_file(full_path)
                    placeholder = graph.add_entity(
                        EntityType.DATA_SNAPSHOT,
                        {"sha256": file_hash, "path": str(path)},
                        source_path=str(full_path),
                    )
                    graph.add_relation(
                        relation, self._strategy_node_id(graph), placeholder.entity_id
                    )
                    linked_hashes.append(placeholder.entity_id)
                else:
                    warnings.warn(f"metadata.links path not found: {path}")

        return linked_hashes

    def _strategy_node_id(self, graph: KnowledgeGraph) -> str:
        """Return the content-addressed ID of the strategy node in ``graph``."""
        strategy_payload = {
            "api_version": self.strategy.api_version,
            "kind": self.strategy.kind,
            "name": self.strategy.metadata.get("name"),
            "spec": self.strategy.spec,
        }
        from aureum.graph import _entity_id

        return _entity_id(EntityType.STRATEGY, strategy_payload)

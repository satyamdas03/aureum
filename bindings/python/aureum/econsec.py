"""Economic-security audit for deterministic rebalancing strategies.

Edge 7 estimates how much value an adversary could extract if they knew the
strategy's rebalancing schedule one day in advance.  The audit is intentionally
mechanical and conservative: it reports an upper bound on extractable value,
not a game-theoretic equilibrium.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aureum.backtest import BacktestResult, MarketData


DEFAULT_CONFIG: dict[str, Any] = {
    "front_run_advance_days": 1,
    "close_on_rebalance": True,
    "adversary_cost_model": {
        "slippage": 0.001,
        "borrow_cost_annual": 0.03,
        "max_participation_rate": 0.10,
    },
    "attack_vectors": ["front_run", "delayed_arbitrage", "liquidity_squeeze"],
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = dict(base)
    if not override:
        return out
    for key, value in override.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _stable_json(obj: Any) -> str:
    """Serialize an object to a stable, sorted JSON string for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(text: str) -> str:
    """Return the SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _avg_nav(daily_nav: list[dict[str, Any]]) -> float:
    """Average NAV over the backtest, ignoring empty series."""
    if not daily_nav:
        return 0.0
    return sum(day["nav"] for day in daily_nav) / len(daily_nav)


def _adv20(market_data: MarketData, date: dt.date, symbol: str) -> float | None:
    """Trailing 20-trading-day average dollar volume at ``date`` for ``symbol``."""
    records = market_data._by_symbol.get(symbol, [])
    idx = next((i for i, rec in enumerate(records) if rec["date"] == date), None)
    if idx is None or idx < 19:
        return None
    window = records[idx - 19 : idx + 1]
    return sum(rec["close"] * rec["volume"] for rec in window) / len(window)


@dataclass
class EconomicSecurityReport:
    """Result of an economic-security audit."""

    enabled: bool
    extractable_value_estimate_bps: float
    attack_vectors_found: list[dict[str, Any]]
    schedule_entropy_bits: float
    replay_inputs_hash: str
    config: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_CONFIG))

    def to_dict(self) -> dict[str, Any]:
        out = {
            "enabled": self.enabled,
            "extractable_value_estimate_bps": round(
                self.extractable_value_estimate_bps, 6
            ),
            "attack_vectors_found": self.attack_vectors_found,
            "schedule_entropy_bits": round(self.schedule_entropy_bits, 6),
            "replay_inputs_hash": self.replay_inputs_hash,
            "config": self.config,
        }
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EconomicSecurityReport":
        """Reconstruct a report from a plain dictionary."""
        return cls(
            enabled=data["enabled"],
            extractable_value_estimate_bps=data["extractable_value_estimate_bps"],
            attack_vectors_found=list(data.get("attack_vectors_found", [])),
            schedule_entropy_bits=data["schedule_entropy_bits"],
            replay_inputs_hash=data["replay_inputs_hash"],
            config=dict(data.get("config", DEFAULT_CONFIG)),
        )


def extract_rebalancing_schedule(
    rebalance_log: list[dict[str, Any]],
    daily_positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Infer intended signed trade list (symbol, delta_shares, rebalance_date).

    For each rebalance date ``t`` we compare the end-of-day positions on the
    previous trading day (pre-rebalance holdings) with the end-of-day positions
    on ``t`` itself (post-rebalance targets).  The difference is the signed
    delta the strategy intended to execute.
    """
    if not rebalance_log or not daily_positions:
        return []

    positions_by_date: dict[str, dict[str, float]] = {
        day["date"]: day.get("positions", {}) for day in daily_positions
    }
    ordered_dates = [day["date"] for day in daily_positions]
    date_to_index = {d: i for i, d in enumerate(ordered_dates)}

    schedule: list[dict[str, Any]] = []
    for entry in rebalance_log:
        date_str = entry["date"]
        idx = date_to_index.get(date_str)
        if idx is None:
            continue

        # The Aureum runner appends the daily position snapshot before it
        # applies the rebalance, so ``daily_positions[idx]`` is the pre-
        # rebalance holdings.  The executed target appears on the next
        # trading day, therefore we read post-rebalance positions from
        # ``idx + 1``.
        pre_positions = positions_by_date.get(date_str, {})
        if idx + 1 >= len(ordered_dates):
            continue
        post_positions = positions_by_date.get(ordered_dates[idx + 1], {})

        all_symbols = set(pre_positions.keys()) | set(post_positions.keys())
        for symbol in sorted(all_symbols):
            pre_shares = float(pre_positions.get(symbol, 0.0))
            post_shares = float(post_positions.get(symbol, 0.0))
            delta_shares = post_shares - pre_shares
            if abs(delta_shares) < 1e-9:
                continue

            schedule.append(
                {
                    "rebalance_date": date_str,
                    "symbol": symbol,
                    "delta_shares": delta_shares,
                    "sign": 1 if delta_shares > 0 else -1,
                    "pre_shares": pre_shares,
                    "post_shares": post_shares,
                }
            )

    return schedule


def _price_on(
    market_data: MarketData, date: dt.date, symbol: str
) -> float | None:
    """Convenience wrapper returning close price or None."""
    return market_data.price(date, symbol)


def _attack_vector(
    vector: str,
    symbol: str,
    rebalance_date: str,
    profit: float,
    notional: float,
    nav: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured attack-vector record."""
    out: dict[str, Any] = {
        "vector": vector,
        "symbol": symbol,
        "rebalance_date": rebalance_date,
        "profit": round(profit, 4),
        "profit_bps": round(10000 * profit / nav, 6) if nav > 0 else 0.0,
        "notional": round(notional, 4),
    }
    if extra:
        out.update(extra)
    return out


def _simulate_front_run(
    market_data: MarketData,
    schedule_item: dict[str, Any],
    advance: int,
    slippage: float,
    borrow_cost_annual: float,
    max_participation_rate: float,
    avg_nav: float,
    dates: list[dt.date],
) -> tuple[float, list[dict[str, Any]]]:
    """Return adversary profit and attack-vector records for one scheduled trade."""
    rebalance_date = dt.date.fromisoformat(schedule_item["rebalance_date"])
    symbol = schedule_item["symbol"]
    delta_shares = schedule_item["delta_shares"]
    strategy_is_buying = delta_shares > 0

    rebalance_idx = dates.index(rebalance_date)
    advance_idx = max(0, rebalance_idx - advance)
    entry_date = dates[advance_idx]

    entry_price = _price_on(market_data, entry_date, symbol)
    exit_price = _price_on(market_data, rebalance_date, symbol)
    if entry_price is None or exit_price is None or entry_price <= 0 or exit_price <= 0:
        return 0.0, []

    adv = _adv20(market_data, entry_date, symbol)
    if adv is None or adv <= 0:
        return 0.0, []

    # The adversary's capacity is limited by a fraction of the average dollar
    # volume over the advance window.
    max_notional = adv * max_participation_rate * advance

    # Raw notional the adversary would like to trade.
    raw_notional = abs(delta_shares) * entry_price
    clipped_notional = min(raw_notional, max_notional)
    if clipped_notional <= 0:
        return 0.0, []

    q = clipped_notional / entry_price

    if strategy_is_buying:
        # Adversary buys before the strategy, sells into the strategy's buys.
        entry_notional = q * entry_price * (1.0 + slippage)
        exit_notional = q * exit_price * (1.0 - slippage)
        profit = exit_notional - entry_notional
    else:
        # Adversary shorts before the strategy, covers into the strategy's sells.
        entry_notional = q * entry_price * (1.0 - slippage)
        exit_notional = q * exit_price * (1.0 + slippage)
        borrow_cost = (
            q * entry_price * borrow_cost_annual * advance / 252.0
        )
        profit = entry_notional - exit_notional - borrow_cost

    vectors: list[dict[str, Any]] = []

    if profit > 0:
        vectors.append(
            _attack_vector(
                "front_run",
                symbol,
                schedule_item["rebalance_date"],
                profit,
                clipped_notional,
                avg_nav,
            )
        )

    if clipped_notional + 1e-9 < raw_notional:
        vectors.append(
            _attack_vector(
                "liquidity_squeeze",
                symbol,
                schedule_item["rebalance_date"],
                profit,
                clipped_notional,
                avg_nav,
                {
                    "capacity_limit": round(max_notional, 4),
                    "desired_notional": round(raw_notional, 4),
                },
            )
        )

    return profit, vectors


def _simulate_delayed_arbitrage(
    market_data: MarketData,
    schedule_item: dict[str, Any],
    slippage: float,
    borrow_cost_annual: float,
    max_participation_rate: float,
    avg_nav: float,
    dates: list[dt.date],
    hold_days: int = 5,
) -> tuple[float, dict[str, Any] | None]:
    """Return adversary profit for a post-rebalance mean-reversion leg."""
    rebalance_date = dt.date.fromisoformat(schedule_item["rebalance_date"])
    symbol = schedule_item["symbol"]
    delta_shares = schedule_item["delta_shares"]

    rebalance_idx = dates.index(rebalance_date)
    exit_idx = min(len(dates) - 1, rebalance_idx + hold_days)
    exit_date = dates[exit_idx]

    entry_price = _price_on(market_data, rebalance_date, symbol)
    exit_price = _price_on(market_data, exit_date, symbol)
    if entry_price is None or exit_price is None or entry_price <= 0 or exit_price <= 0:
        return 0.0, None

    adv = _adv20(market_data, rebalance_date, symbol)
    if adv is None or adv <= 0:
        return 0.0, None

    max_notional = adv * max_participation_rate * hold_days
    raw_notional = abs(delta_shares) * entry_price
    clipped_notional = min(raw_notional, max_notional)
    if clipped_notional <= 0:
        return 0.0, None

    q = clipped_notional / entry_price
    hold_days_actual = exit_idx - rebalance_idx

    # Trade opposite to the strategy: if the strategy bought, the adversary
    # shorts into the temporary dislocation and covers later.
    if delta_shares > 0:
        entry_notional = q * entry_price * (1.0 - slippage)
        exit_notional = q * exit_price * (1.0 + slippage)
        borrow_cost = (
            q * entry_price * borrow_cost_annual * hold_days_actual / 252.0
        )
        profit = entry_notional - exit_notional - borrow_cost
    else:
        entry_notional = q * entry_price * (1.0 + slippage)
        exit_notional = q * exit_price * (1.0 - slippage)
        profit = exit_notional - entry_notional

    if profit <= 0:
        return 0.0, None

    return profit, _attack_vector(
        "delayed_arbitrage",
        symbol,
        schedule_item["rebalance_date"],
        profit,
        clipped_notional,
        avg_nav,
        {"hold_days": hold_days_actual, "exit_date": exit_date.isoformat()},
    )


def _schedule_entropy(schedule: list[dict[str, Any]]) -> float:
    """Shannon entropy over unique (date, symbol, sign) triples."""
    if not schedule:
        return 0.0

    keys = [
        (item["rebalance_date"], item["symbol"], item["sign"]) for item in schedule
    ]
    unique = set(keys)
    if not unique:
        return 0.0

    n_rebalances = len({item["rebalance_date"] for item in schedule})
    if n_rebalances == 0:
        return 0.0

    counts: dict[tuple[str, str, int], int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1

    total = len(keys)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    # Normalize by rebalance count so predictable monthly schedules report low
    # entropy even when they span many dates.
    return entropy / n_rebalances


def audit_economic_security(
    backtest_result: BacktestResult,
    market_data: MarketData,
    config: dict[str, Any] | None = None,
) -> EconomicSecurityReport:
    """Mechanically estimate extractable value from a deterministic strategy.

    Parameters
    ----------
    backtest_result:
        The result object produced by ``BacktestRunner.run()``.
    market_data:
        The same ``MarketData`` instance used for the backtest.
    config:
        Optional overrides for the default adversary configuration.

    Returns
    -------
    EconomicSecurityReport
        A structured report containing the extractable-value estimate, any
        triggered attack vectors, schedule entropy, and a replay-input hash.
    """
    merged_config = _deep_merge(DEFAULT_CONFIG, config)
    advance = int(merged_config.get("front_run_advance_days", 1))
    close_on_rebalance = bool(merged_config.get("close_on_rebalance", True))
    cost_model = merged_config.get("adversary_cost_model", {})
    slippage = float(cost_model.get("slippage", 0.001))
    borrow_cost_annual = float(cost_model.get("borrow_cost_annual", 0.03))
    max_participation_rate = float(cost_model.get("max_participation_rate", 0.10))
    enabled_vectors = set(merged_config.get("attack_vectors", []))

    schedule = extract_rebalancing_schedule(
        backtest_result.rebalance_log, backtest_result.daily_positions
    )

    if not schedule or not backtest_result.daily_nav:
        replay_inputs_hash = _sha256_text(
            _stable_json({"config": merged_config, "schedule": schedule})
        )
        return EconomicSecurityReport(
            enabled=True,
            extractable_value_estimate_bps=0.0,
            attack_vectors_found=[],
            schedule_entropy_bits=0.0,
            replay_inputs_hash=replay_inputs_hash,
            config=merged_config,
        )

    dates = market_data.dates
    avg_nav = _avg_nav(backtest_result.daily_nav)

    total_profit = 0.0
    vectors: list[dict[str, Any]] = []

    if close_on_rebalance and "front_run" in enabled_vectors:
        for item in schedule:
            profit, found = _simulate_front_run(
                market_data,
                item,
                advance,
                slippage,
                borrow_cost_annual,
                max_participation_rate,
                avg_nav,
                dates,
            )
            total_profit += profit
            vectors.extend(found)

    if "delayed_arbitrage" in enabled_vectors:
        for item in schedule:
            profit, record = _simulate_delayed_arbitrage(
                market_data,
                item,
                slippage,
                borrow_cost_annual,
                max_participation_rate,
                avg_nav,
                dates,
            )
            if record:
                total_profit += profit
                vectors.append(record)

    entropy = _schedule_entropy(schedule)
    replay_inputs_hash = _sha256_text(
        _stable_json({"config": merged_config, "schedule": schedule})
    )

    return EconomicSecurityReport(
        enabled=True,
        extractable_value_estimate_bps=10000 * total_profit / avg_nav
        if avg_nav > 0
        else 0.0,
        attack_vectors_found=vectors,
        schedule_entropy_bits=entropy,
        replay_inputs_hash=replay_inputs_hash,
        config=merged_config,
    )

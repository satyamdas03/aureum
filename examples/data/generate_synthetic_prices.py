"""Generate a deterministic synthetic price history for Aureum backtests.

The output is a plain CSV with daily OHLC-style rows for a small universe of
US technology stocks.  Prices are generated from a seeded random walk so the
result is bit-for-bit reproducible and safe to assert against in tests.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path


SEED = 42
START = dt.date(2022, 1, 3)
END = dt.date(2024, 12, 31)

# Ten technology symbols with heterogeneous long-term drift.  The drift is
# expressed as average daily log-return so some names trend up strongly while
# others are flat or slightly down.  This creates clean momentum dispersion.
SYMBOLS = [
    ("AAPL", 150.0, 0.00055, 0.014),
    ("MSFT", 300.0, 0.00050, 0.013),
    ("GOOGL", 110.0, 0.00035, 0.015),
    ("AMZN", 120.0, 0.00040, 0.017),
    ("NVDA", 200.0, 0.00080, 0.022),
    ("META", 330.0, 0.00025, 0.019),
    ("TSLA", 250.0, 0.00030, 0.025),
    ("AVGO", 600.0, 0.00045, 0.016),
    ("ORCL", 90.0, 0.00020, 0.012),
    ("NFLX", 400.0, 0.00060, 0.018),
]


def trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """Return weekdays between start and end inclusive."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Monday=0 ... Friday=4
            days.append(current)
        current += dt.timedelta(days=1)
    return days


def generate() -> list[dict[str, object]]:
    random.seed(SEED)
    days = trading_days(START, END)
    rows: list[dict[str, object]] = []

    for symbol, base_price, drift, volatility in SYMBOLS:
        price = base_price
        for day in days:
            # Daily log-return with drift and volatility.
            log_return = random.gauss(drift, volatility)
            price *= (1.0 + log_return)
            if price < 5.0:
                price = 5.0  # prevent delisting

            # Volume scales with price level and is always well above $1M ADV.
            volume = int(random.uniform(2_000_000, 20_000_000))

            rows.append(
                {
                    "date": day.isoformat(),
                    "symbol": symbol,
                    "close": round(price, 4),
                    "volume": volume,
                    "sector": "Technology",
                }
            )

    # Sort by date then symbol so the CSV is deterministic.
    rows.sort(key=lambda r: (r["date"], r["symbol"]))
    return rows


def main() -> None:
    root = Path(__file__).resolve().parent
    out_path = root / "synthetic_prices.csv"
    rows = generate()
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "symbol", "close", "volume", "sector"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()

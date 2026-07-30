"""Real-market data adapter with versionable snapshots.

This module fetches daily price bars from Alpaca and writes a deterministic,
content-addressable CSV snapshot that can be used as an input lineage source
for an Aureum Backtest Certificate.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .backtest import MarketData


@dataclass(frozen=True)
class Bar:
    """A single OHLCV bar from Alpaca."""

    symbol: str
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None


@dataclass(frozen=True)
class AlpacaSnapshot:
    """Metadata describing a fetched and saved market-data snapshot."""

    path: Path
    symbols: tuple[str, ...]
    start_date: dt.date
    end_date: dt.date
    rows: int
    sha256: str
    fetched_at: str
    feed: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "symbols": list(self.symbols),
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "rows": self.rows,
            "sha256": self.sha256,
            "fetched_at": self.fetched_at,
            "feed": self.feed,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlpacaSnapshot:
        return cls(
            path=Path(data["path"]),
            symbols=tuple(data["symbols"]),
            start_date=dt.date.fromisoformat(data["start_date"]),
            end_date=dt.date.fromisoformat(data["end_date"]),
            rows=data["rows"],
            sha256=data["sha256"],
            fetched_at=data["fetched_at"],
            feed=data.get("feed", "iex"),
            metadata=data.get("metadata", {}),
        )


class AlpacaAdapter:
    """Fetch daily bars from Alpaca and materialise deterministic snapshots."""

    DATA_BASE_URL = "https://data.alpaca.markets/v2"

    def __init__(
        self,
        api_key: str | None = None,
        secret_key: str | None = None,
        feed: str = "iex",
    ) -> None:
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self.feed = feed
        if not self.api_key or not self.secret_key:
            raise RuntimeError(
                "Alpaca API credentials missing. Set ALPACA_API_KEY and "
                "ALPACA_SECRET_KEY environment variables."
            )

    def fetch_bars(
        self,
        symbols: list[str],
        start: dt.date,
        end: dt.date,
        timeframe: str = "1Day",
    ) -> list[Bar]:
        """Return all daily bars for ``symbols`` between ``start`` and ``end``.

        Pagination is handled automatically via the ``next_page_token`` field.
        """
        if not symbols:
            return []

        bars: list[Bar] = []
        next_token: str | None = None
        symbol_param = ",".join(symbols)

        while True:
            url = self._build_url(
                symbol_param, start, end, timeframe, next_token
            )
            data = self._request_json(url)

            raw_bars = data.get("bars", {})
            for symbol, symbol_bars in raw_bars.items():
                for b in symbol_bars:
                    bars.append(self._parse_bar(symbol, b))

            next_token = data.get("next_page_token")
            if not next_token:
                break

        # Sort deterministically so the same query always yields the same CSV.
        bars.sort(key=lambda bar: (bar.date, bar.symbol))
        return bars

    def _build_url(
        self,
        symbols: str,
        start: dt.date,
        end: dt.date,
        timeframe: str,
        page_token: str | None,
    ) -> str:
        params = {
            "symbols": symbols,
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": (end + dt.timedelta(days=1)).isoformat(),
            "limit": "10000",
            "feed": self.feed,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token
        query = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params.items())
        return f"{self.DATA_BASE_URL}/stocks/bars?{query}"

    def _request_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": self.api_key,
                "APCA-API-SECRET-KEY": self.secret_key,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Alpaca API error {exc.code}: {body}") from exc

    @staticmethod
    def _parse_bar(symbol: str, raw: dict[str, Any]) -> Bar:
        # Alpaca timestamps are ISO-8601 UTC, e.g. "2024-01-02T00:00:00Z".
        timestamp = raw["t"]
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        parsed = dt.datetime.fromisoformat(timestamp)
        return Bar(
            symbol=symbol,
            date=parsed.date(),
            open=float(raw["o"]),
            high=float(raw["h"]),
            low=float(raw["l"]),
            close=float(raw["c"]),
            volume=int(raw["v"]),
            vwap=float(raw["vw"]) if "vw" in raw else None,
        )

    def write_snapshot(
        self,
        path: str | Path,
        symbols: list[str],
        start: dt.date,
        end: dt.date,
        *,
        sectors: dict[str, str] | None = None,
        timeframe: str = "1Day",
    ) -> AlpacaSnapshot:
        """Fetch bars and write a deterministic CSV snapshot.

        The written CSV uses a stable column order and is hashed with SHA-256
        so it can be referenced as input lineage in an ABC certificate.
        """
        path = Path(path)
        bars = self.fetch_bars(symbols, start, end, timeframe=timeframe)

        rows = 0
        fieldnames = ["date", "symbol", "open", "high", "low", "close", "volume", "sector"]
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for bar in bars:
                writer.writerow(
                    {
                        "date": bar.date.isoformat(),
                        "symbol": bar.symbol,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                        "sector": sectors.get(bar.symbol, "") if sectors else "",
                    }
                )
                rows += 1

        sha256 = _hash_file(path)
        meta_path = path.with_suffix(".snapshot.json")
        fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        snapshot = AlpacaSnapshot(
            path=path,
            symbols=tuple(sorted(symbols)),
            start_date=start,
            end_date=end,
            rows=rows,
            sha256=sha256,
            fetched_at=fetched_at,
            feed=self.feed,
            metadata={"timeframe": timeframe, "source": "alpaca"},
        )
        meta_path.write_text(
            json.dumps(snapshot.to_dict(), indent=2), encoding="utf-8"
        )
        return snapshot

    @staticmethod
    def market_data_from_csv(path: str | Path) -> MarketData:
        """Load a previously saved snapshot as a ``MarketData`` instance."""
        return MarketData.from_csv(path)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

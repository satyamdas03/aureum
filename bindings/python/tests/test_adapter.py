"""Tests for the Alpaca real-market data adapter."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aureum.adapter import AlpacaAdapter, AlpacaSnapshot
from aureum.backtest import MarketData


def test_adapter_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Alpaca API credentials missing"):
        AlpacaAdapter(api_key="", secret_key="")


def _alpaca_response():
    return {
        "bars": {
            "AAPL": [
                {
                    "t": "2024-01-02T00:00:00Z",
                    "o": 185.0,
                    "h": 187.0,
                    "l": 184.0,
                    "c": 186.5,
                    "v": 1000,
                    "vw": 186.2,
                },
                {
                    "t": "2024-01-03T00:00:00Z",
                    "o": 186.5,
                    "h": 188.0,
                    "l": 185.5,
                    "c": 187.0,
                    "v": 1200,
                    "vw": 186.8,
                },
            ],
            "MSFT": [
                {
                    "t": "2024-01-02T00:00:00Z",
                    "o": 370.0,
                    "h": 375.0,
                    "l": 369.0,
                    "c": 374.0,
                    "v": 800,
                    "vw": 373.5,
                }
            ],
        },
        "next_page_token": None,
    }


def test_write_snapshot_produces_csv_and_metadata(tmp_path: Path):
    output = tmp_path / "alpaca_snapshot.csv"
    adapter = AlpacaAdapter(api_key="TEST_KEY", secret_key="TEST_SECRET")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps(_alpaca_response()).encode("utf-8")

    with patch("aureum.adapter.urllib.request.urlopen", return_value=mock_response):
        snapshot = adapter.write_snapshot(
            output,
            symbols=["AAPL", "MSFT"],
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
            sectors={"AAPL": "Technology", "MSFT": "Technology"},
        )

    assert output.exists()
    assert snapshot.rows == 3
    assert len(snapshot.sha256) == 64
    assert snapshot.symbols == ("AAPL", "MSFT")

    data = MarketData.from_csv(output)
    assert sorted(data.symbols) == ["AAPL", "MSFT"]
    assert data.price(date(2024, 1, 2), "AAPL") == 186.5
    assert data.price(date(2024, 1, 3), "AAPL") == 187.0
    assert data.price(date(2024, 1, 2), "MSFT") == 374.0
    assert data.sector("AAPL") == "Technology"

    meta_path = output.with_suffix(".snapshot.json")
    assert meta_path.exists()
    loaded = AlpacaSnapshot.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
    assert loaded.sha256 == snapshot.sha256
    assert loaded.rows == 3


def test_write_snapshot_is_content_addressable(tmp_path: Path):
    """Two identical fetches produce the same SHA-256 hash."""
    output_a = tmp_path / "snap_a.csv"
    output_b = tmp_path / "snap_b.csv"
    adapter = AlpacaAdapter(api_key="TEST_KEY", secret_key="TEST_SECRET")

    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = json.dumps(_alpaca_response()).encode("utf-8")

    with patch("aureum.adapter.urllib.request.urlopen", return_value=mock_response):
        snap_a = adapter.write_snapshot(
            output_a, ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 12, 31)
        )
    with patch("aureum.adapter.urllib.request.urlopen", return_value=mock_response):
        snap_b = adapter.write_snapshot(
            output_b, ["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 12, 31)
        )

    assert snap_a.sha256 == snap_b.sha256

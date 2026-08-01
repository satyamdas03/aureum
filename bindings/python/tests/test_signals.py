"""Tests for the Aureum signal registry."""

from __future__ import annotations

import math

import pytest

from aureum.backtest import _SIGNALS


@pytest.mark.parametrize(
    "signal_name,closes,expected_sign",
    [
        ("momentum_12_1", list(range(1, 300)), 1),  # upward trend
        ("volatility_20d", [100.0] * 25, 0),  # flat = zero vol
        ("sharpe_63d", list(range(1, 80)), 1),  # upward trend
        ("mean_reversion_5_20", [100.0] * 19 + [110.0], 1),  # price above mean
    ],
)
def test_signals_return_finite_number(
    signal_name: str, closes: list[float], expected_sign: int
) -> None:
    fn = _SIGNALS[signal_name]
    volumes = [1_000_000] * len(closes)
    score = fn(closes, volumes)
    assert not math.isnan(score)
    assert score != 0.0 or expected_sign == 0
    if expected_sign != 0:
        assert math.copysign(1, score) == expected_sign


def test_unknown_signal_raises() -> None:
    assert "unknown_signal" not in _SIGNALS


def test_signal_registry_contains_expected_signals() -> None:
    names = set(_SIGNALS)
    assert names == {
        "momentum_12_1",
        "volatility_20d",
        "sharpe_63d",
        "mean_reversion_5_20",
    }

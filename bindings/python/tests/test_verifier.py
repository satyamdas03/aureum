"""Tests for the Aureum static risk-constraint verifier."""

from __future__ import annotations

from aureum.verifier import all_passed, verify_constraints


def _find(results, name):
    return next(r for r in results if r["name"] == name)


def test_max_drawdown_pass():
    results = verify_constraints(
        [{"name": "max_drawdown", "limit": 0.20, "operator": "<=", "hard": True}],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_drawdown")
    assert r["passed"] is True
    assert r["actual"] == 0.10


def test_max_drawdown_fail():
    results = verify_constraints(
        [{"name": "max_drawdown", "limit": 0.10, "operator": "<=", "hard": True}],
        max_drawdown=0.20,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_drawdown")
    assert r["passed"] is False


def test_max_leverage_pass():
    results = verify_constraints(
        [{"name": "max_leverage", "limit": 1.5, "operator": "<=", "hard": True}],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_leverage")
    assert r["passed"] is True


def test_max_turnover_pass():
    results = verify_constraints(
        [
            {
                "name": "max_turnover_annual",
                "limit": 3.0,
                "operator": "<=",
                "hard": False,
            }
        ],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=2.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_turnover_annual")
    assert r["passed"] is True
    assert r["hard"] is False


def test_max_concentration_pass():
    results = verify_constraints(
        [
            {
                "name": "max_concentration_single_name",
                "limit": 0.25,
                "operator": "<=",
                "hard": True,
            }
        ],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_concentration_single_name")
    assert r["passed"] is True


def test_unknown_constraint_is_recorded():
    results = verify_constraints(
        [{"name": "max_correlation", "limit": 0.50, "operator": "<=", "hard": True}],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    r = _find(results, "max_correlation")
    assert r["passed"] is False
    assert "not implemented" in r["note"]


def test_all_passed_true():
    results = verify_constraints(
        [
            {"name": "max_drawdown", "limit": 0.20, "operator": "<=", "hard": True},
            {"name": "max_leverage", "limit": 1.5, "operator": "<=", "hard": True},
        ],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    assert all_passed(results) is True


def test_all_passed_false():
    results = verify_constraints(
        [{"name": "max_drawdown", "limit": 0.05, "operator": "<=", "hard": True}],
        max_drawdown=0.10,
        max_leverage=1.0,
        turnover_annual=1.0,
        concentration_single_name=0.20,
    )
    assert all_passed(results) is False

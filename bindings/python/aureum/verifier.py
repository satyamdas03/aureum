"""Static risk-constraint verifier for Aureum backtest certificates.

The verifier takes a backtest results object and a list of risk constraints from
a strategy spec, then produces a machine-readable compliance report.  Each check
returns a dictionary that can be dropped directly into a BacktestCertificate.

Supported constraints in Phase 1:
- max_drawdown
- max_leverage
- max_turnover_annual
- max_concentration_single_name
"""

from __future__ import annotations

from typing import Any


def _check(
    name: str,
    limit: float,
    actual: float,
    operator: str,
    hard: bool,
) -> dict[str, Any]:
    """Return a standardized constraint-result dictionary."""
    passed = False
    if operator == "<=":
        passed = actual <= limit
    elif operator == ">=":
        passed = actual >= limit
    elif operator == "==":
        passed = actual == limit

    return {
        "name": name,
        "limit": limit,
        "actual": round(actual, 6),
        "operator": operator,
        "passed": passed,
        "hard": hard,
    }


def verify_constraints(
    constraints: list[dict[str, Any]],
    *,
    max_drawdown: float,
    max_leverage: float,
    turnover_annual: float,
    concentration_single_name: float,
) -> list[dict[str, Any]]:
    """Evaluate every declared risk constraint against actual backtest metrics.

    Parameters mirror the computed values from the backtest runner.  Unknown
    constraint names are skipped with a warning entry so the certificate still
    records that they were present but not verified in Phase 1.
    """
    out: list[dict[str, Any]] = []
    for constraint in constraints:
        name = constraint.get("name")
        limit = constraint.get("limit")
        operator = constraint.get("operator", "<=")
        hard = constraint.get("hard", False)

        if name is None or limit is None:
            out.append(
                {
                    "name": name or "unknown",
                    "limit": limit,
                    "actual": None,
                    "operator": operator,
                    "passed": False,
                    "hard": hard,
                    "note": "missing name or limit",
                }
            )
            continue

        if name == "max_drawdown":
            out.append(_check(name, limit, max_drawdown, operator, hard))
        elif name == "max_leverage":
            out.append(_check(name, limit, max_leverage, operator, hard))
        elif name == "max_turnover_annual":
            out.append(_check(name, limit, turnover_annual, operator, hard))
        elif name == "max_concentration_single_name":
            out.append(_check(name, limit, concentration_single_name, operator, hard))
        else:
            out.append(
                {
                    "name": name,
                    "limit": limit,
                    "actual": None,
                    "operator": operator,
                    "passed": False,
                    "hard": hard,
                    "note": "constraint not implemented in Phase 1 verifier",
                }
            )

    return out


def all_passed(results: list[dict[str, Any]]) -> bool:
    """Return True only if every hard constraint passed and every known constraint passed."""
    for result in results:
        if not result.get("passed", False):
            return False
    return True

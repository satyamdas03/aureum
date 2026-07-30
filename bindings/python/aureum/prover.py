"""Formal verifier bridge for Aureum Backtest Certificates.

This prototype turns the numeric claims inside a certificate into
machine-checkable artefacts:

* SMT-LIB v2 scripts suitable for Z3, CVC5, or MathSAT.
* Lean 4 theorem statements that can be tactic-proved with ``norm_num``.
* Optional Z3 invocation via the ``z3-solver`` Python package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RiskClaim:
    """One risk-constraint claim extracted from a certificate."""

    name: str
    limit: float
    actual: float
    operator: str  # "<=", ">=", "<", ">", "=="
    passed: bool


class SmtLibGenerator:
    """Generate an SMT-LIB v2 script that asserts all risk claims."""

    def generate(self, claims: list[RiskClaim]) -> str:
        lines = [
            "; Aureum Backtest Certificate — Risk-constraint SMT encoding",
            "(set-logic QF_LRA)",
        ]

        declared: set[str] = set()
        for claim in claims:
            var_name = self._var_name(claim.name)
            if var_name not in declared:
                lines.append(f"(declare-fun {var_name} () Real)")
                declared.add(var_name)
            lines.append(
                f"(assert ({self._smt_op(claim.operator)} {var_name} {claim.limit:.10g}))"
            )
            lines.append(
                f"(assert (= {var_name} {claim.actual:.10g})) ; certificate actual"
            )

        lines.append("(check-sat)")
        lines.append(
            "; If SAT, the certificate's risk claims are consistent with the stated limits."
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _var_name(name: str) -> str:
        return f"risk_{name}".replace("-", "_")

    @staticmethod
    def _smt_op(op: str) -> str:
        mapping = {"<=": "<=" , ">=": ">=", "<": "<", ">": ">", "==": "="}
        return mapping.get(op, "<=")


class Lean4Generator:
    """Generate a Lean 4 theorem for each risk claim.

    The generated file imports ``Mathlib`` only for ``norm_num`` and states
    one theorem per constraint.  The proof is a one-liner so that a Lean
    installation can check it automatically.
    """

    def generate(self, claims: list[RiskClaim]) -> str:
        lines = [
            "-- Aureum Backtest Certificate — Risk-constraint Lean 4 encoding",
            "import Mathlib",
            "",
            "namespace AureumCertificate",
        ]

        for claim in claims:
            op = self._lean_op(claim.operator)
            lines.append(
                f"\ntheorem risk_{self._safe_name(claim.name)} : "
                f"({claim.actual:.10g} {op} {claim.limit:.10g}) := by norm_num"
            )

        lines.append("")
        lines.append("end AureumCertificate")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _safe_name(name: str) -> str:
        return name.replace("-", "_").replace(".", "_")

    @staticmethod
    def _lean_op(op: str) -> str:
        mapping = {"<=": "≤", ">=": "≥", "<": "<", ">": ">", "==": "="}
        return mapping.get(op, "≤")


def extract_claims(certificate: dict[str, Any]) -> list[RiskClaim]:
    """Extract risk claims from a certificate dict.

    Handles both the legacy dict shape ``{"max_drawdown": {"limit": ...}}``
    and the current list shape ``[{"name": "max_drawdown", ...}]``.
    """
    claims: list[RiskClaim] = []
    risk = certificate.get("risk_constraints", [])
    if isinstance(risk, dict):
        for name, result in risk.items():
            if not isinstance(result, dict):
                continue
            claims.append(
                RiskClaim(
                    name=name,
                    limit=float(result.get("limit", 0.0)),
                    actual=float(result.get("actual", 0.0)),
                    operator=str(result.get("operator", "<=")),
                    passed=bool(result.get("passed", False)),
                )
            )
    elif isinstance(risk, list):
        for result in risk:
            if not isinstance(result, dict):
                continue
            claims.append(
                RiskClaim(
                    name=result.get("name", "unknown"),
                    limit=float(result.get("limit", 0.0)),
                    actual=float(result.get("actual", 0.0)),
                    operator=str(result.get("operator", "<=")),
                    passed=bool(result.get("passed", False)),
                )
            )
    return claims


def verify_with_z3(smtlib: str) -> bool:
    """Return True if Z3 reports ``sat`` for the given SMT-LIB script.

    Requires ``z3-solver`` to be installed.  If it is not available the
    function raises ``RuntimeError`` so callers can decide to fall back to
    static checking.
    """
    try:
        import z3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "z3-solver is not installed; install it to enable live verification"
        ) from exc

    solver = z3.Solver()
    solver.from_string(smtlib)
    return solver.check() == z3.sat

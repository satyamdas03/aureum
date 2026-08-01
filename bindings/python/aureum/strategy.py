"""Strategy DSL parser and backtest orchestrator (MVP pure-Python)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aureum.alpha import AlphaGrammar, safety_check


BUILTIN_RANKING_SIGNALS = {
    "momentum_12_1",
    "volatility_20d",
    "sharpe_63d",
    "mean_reversion_5_20",
}


@dataclass
class Strategy:
    """Parsed Aureum Quant Kernel strategy."""

    api_version: str
    kind: str
    metadata: dict[str, Any]
    spec: dict[str, Any]

    @classmethod
    def from_yaml(cls, text: str) -> Strategy:
        data = yaml.safe_load(text)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Strategy:
        return cls(
            api_version=data.get("apiVersion", ""),
            kind=data.get("kind", ""),
            metadata=data.get("metadata", {}),
            spec=data.get("spec", {}),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> Strategy:
        path = Path(path)
        return cls.from_yaml(path.read_text(encoding="utf-8"))

    def _validate_portfolio(self, errors: list[str]) -> None:
        """Validate the optional ``spec.portfolio`` MPT section."""
        portfolio = self.spec.get("portfolio", {})
        if not portfolio:
            return
        objective = portfolio.get("objective")
        if not objective:
            errors.append("spec.portfolio.objective is required when portfolio is present")
        elif objective not in {
            "mean_variance",
            "minimum_variance",
            "maximum_sharpe",
            "risk_parity",
            "minimum_cvar",
        }:
            errors.append(
                f"spec.portfolio.objective '{objective}' is not supported; "
                "supported values: mean_variance, minimum_variance, maximum_sharpe, "
                "risk_parity, minimum_cvar"
            )
        estimator = portfolio.get("covariance_estimator", "sample")
        if estimator not in {"sample", "ledoit_wolf"}:
            errors.append(
                f"spec.portfolio.covariance_estimator '{estimator}' is not supported; "
                "supported values: sample, ledoit_wolf"
            )
        risk_measure = portfolio.get("risk_measure", "variance")
        if risk_measure not in {"variance", "cvar_95", "cvar_99"}:
            errors.append(
                f"spec.portfolio.risk_measure '{risk_measure}' is not supported; "
                "supported values: variance, cvar_95, cvar_99"
            )
        max_weight = portfolio.get("max_weight")
        if max_weight is not None and (not isinstance(max_weight, (int, float)) or max_weight <= 0):
            errors.append("spec.portfolio.max_weight must be a positive number")
        min_weight = portfolio.get("min_weight")
        if min_weight is not None and (not isinstance(min_weight, (int, float)) or min_weight < 0):
            errors.append("spec.portfolio.min_weight must be a non-negative number")
        if (
            max_weight is not None
            and min_weight is not None
            and min_weight > max_weight
        ):
            errors.append("spec.portfolio.min_weight cannot exceed max_weight")

    def validate(self) -> list[str]:
        """Return a list of validation errors, empty if valid."""
        errors: list[str] = []
        if not self.metadata.get("name"):
            errors.append("metadata.name is required")
        spec = self.spec
        if "universe" not in spec:
            errors.append("spec.universe is required")
        if "schedule" not in spec:
            errors.append("spec.schedule is required")

        uses_portfolio = "portfolio" in spec
        uses_ranking = "ranking" in spec

        if not uses_portfolio and not uses_ranking:
            errors.append("spec.ranking is required (or use spec.portfolio for MPT optimization)")

        # Validate signal definitions (including neuro-symbolic formulas).
        defined_signals = self._validate_signals(errors)

        if uses_ranking:
            ranking = spec["ranking"]
            signal_name = ranking.get("by")
            if not signal_name:
                errors.append("spec.ranking.by is required")
            elif signal_name not in BUILTIN_RANKING_SIGNALS and signal_name not in defined_signals:
                errors.append(
                    f"spec.ranking.by '{signal_name}' is not defined; "
                    "define it under spec.signals or use a built-in signal"
                )

        if uses_portfolio:
            self._validate_portfolio(errors)
            if not uses_ranking and "weights" in spec:
                errors.append(
                    "spec.weights is not used when spec.portfolio is present; "
                    "portfolio weights come from the optimizer"
                )

        if not uses_portfolio and "weights" not in spec:
            errors.append("spec.weights is required")
        if "execution" not in spec:
            errors.append("spec.execution is required")
        return errors

    def _validate_signals(self, errors: list[str]) -> set[str]:
        """Validate signal definitions and return the set of defined names."""
        defined: set[str] = set()
        signals = self.spec.get("signals", {})
        if not signals:
            return defined

        if isinstance(signals, list):
            for signal in signals:
                name = signal.get("name")
                if not name:
                    continue
                defined.add(name)
        elif isinstance(signals, dict):
            for name, signal in signals.items():
                defined.add(name)
                if signal.get("type") == "neuro_symbolic":
                    formula = signal.get("formula", "")
                    if not formula:
                        errors.append(f"spec.signals.{name}.formula is required for neuro_symbolic signal")
                        continue
                    ast, parse_error = AlphaGrammar.parse(formula)
                    if parse_error or ast is None:
                        errors.append(f"spec.signals.{name}.formula parse error: {parse_error or 'unknown'}")
                        continue
                    report = safety_check(ast, formula=formula)
                    if not report.safe:
                        for failure in report.failures:
                            errors.append(f"spec.signals.{name}.formula safety: {failure}")
                        continue
                    # Safety-check flag must be honest when present.
                    generation = signal.get("generation", {})
                    if generation.get("safety_checks_passed") is False:
                        errors.append(
                            f"spec.signals.{name}.generation.safety_checks_passed is false; "
                            "formula must pass safety checks"
                        )
        return defined

    def portfolio(self) -> dict[str, Any] | None:
        """Return the ``spec.portfolio`` block if present, else None."""
        return self.spec.get("portfolio")

    def constraints(self) -> list[dict[str, Any]]:
        """Extract verifiable risk constraints."""
        risk = self.spec.get("risk", {})
        out = []
        for name in ["max_drawdown", "max_leverage", "max_turnover_annual"]:
            spec = risk.get(name)
            if spec:
                out.append(
                    {
                        "name": name,
                        "variable": name.replace("max_", ""),
                        "operator": "<=" if name.startswith("max_") else "==",
                        "limit": spec["value"],
                        "hard": spec.get("hard", False),
                    }
                )
        portfolio = self.portfolio()
        if portfolio:
            out.append(
                {
                    "name": "portfolio_objective",
                    "variable": "objective",
                    "operator": "==",
                    "limit": portfolio.get("objective"),
                    "hard": True,
                }
            )
            out.append(
                {
                    "name": "portfolio_covariance_estimator",
                    "variable": "covariance_estimator",
                    "operator": "==",
                    "limit": portfolio.get("covariance_estimator", "sample"),
                    "hard": True,
                }
            )
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata,
            "spec": self.spec,
        }

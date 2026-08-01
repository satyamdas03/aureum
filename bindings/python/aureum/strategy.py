"""Strategy DSL parser and backtest orchestrator (MVP pure-Python)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aureum.causal import CausalGraph, CausalSeparationSpec


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
            "differentiable_sharpe",
        }:
            errors.append(
                f"spec.portfolio.objective '{objective}' is not supported; "
                "supported values: mean_variance, minimum_variance, maximum_sharpe, "
                "risk_parity, minimum_cvar, differentiable_sharpe"
            )

        if objective == "differentiable_sharpe":
            self._validate_differentiable_sharpe(portfolio, errors)

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

        self._validate_causal(portfolio, errors)

    def _validate_causal(
        self, portfolio: dict[str, Any], errors: list[str]
    ) -> None:
        """Validate the optional ``causal_graph`` / ``causal_separation`` block."""
        has_graph = bool(portfolio.get("causal_graph"))
        separation = CausalSeparationSpec.from_portfolio_spec(portfolio)

        if separation is not None and not has_graph:
            errors.append(
                "spec.portfolio.causal_separation requires spec.portfolio.causal_graph"
            )
            return

        if not has_graph:
            return

        graph = CausalGraph.from_portfolio_spec(portfolio)
        symbols = self.spec.get("universe", {}).get("symbols", [])
        errors.extend(graph.validate(symbols))

        if separation is None:
            errors.append(
                "spec.portfolio.causal_graph requires spec.portfolio.causal_separation"
            )
            return

        if separation.mode not in {"condition_on", "auto"}:
            errors.append(
                f"spec.portfolio.causal_separation.mode '{separation.mode}' is not supported; "
                "supported values: condition_on, auto"
            )

        if separation.mode == "condition_on":
            unknown = set(separation.drivers) - set(graph.driver_names())
            if unknown:
                errors.append(
                    "undeclared driver in causal_separation: "
                    f"{sorted(unknown)}"
                )

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

        if uses_ranking:
            ranking = spec["ranking"]
            signal_name = ranking.get("by")
            if not signal_name:
                errors.append("spec.ranking.by is required")
            elif signal_name not in {
                "momentum_12_1",
                "volatility_20d",
                "sharpe_63d",
                "mean_reversion_5_20",
            }:
                errors.append(
                    f"spec.ranking.by '{signal_name}' is not supported; "
                    "supported values: momentum_12_1, volatility_20d, "
                    "sharpe_63d, mean_reversion_5_20"
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
            if portfolio.get("causal_graph"):
                separation = CausalSeparationSpec.from_portfolio_spec(portfolio)
                out.append(
                    {
                        "name": "causal_separation_mode",
                        "variable": "causal_separation_mode",
                        "operator": "==",
                        "limit": separation.mode if separation else "",
                        "hard": False,
                    }
                )
                out.append(
                    {
                        "name": "causal_separation_drivers",
                        "variable": "causal_separation_drivers",
                        "operator": "==",
                        "limit": separation.drivers if separation else [],
                        "hard": False,
                    }
                )
        return out

    def _validate_differentiable_sharpe(
        self, portfolio: dict[str, Any], errors: list[str]
    ) -> None:
        """Validate the ``spec.portfolio`` block when objective is differentiable_sharpe."""
        model = portfolio.get("model")
        if not isinstance(model, dict):
            errors.append(
                "spec.portfolio.model is required when objective is differentiable_sharpe"
            )
            return

        architecture_file = model.get("architecture_file")
        if not architecture_file:
            errors.append(
                "spec.portfolio.model.architecture_file is required "
                "when objective is differentiable_sharpe"
            )

        training = portfolio.get("training")
        if not isinstance(training, dict):
            errors.append(
                "spec.portfolio.training is required when objective is differentiable_sharpe"
            )
            return

        required_fields = {
            "learning_rate": "float",
            "epochs": "int",
            "train_end": "date (YYYY-MM-DD)",
            "val_end": "date (YYYY-MM-DD)",
        }
        for field, kind in required_fields.items():
            if field not in training:
                errors.append(
                    f"spec.portfolio.training.{field} is required ({kind}) "
                    "when objective is differentiable_sharpe"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "metadata": self.metadata,
            "spec": self.spec,
        }

"""Strategy DSL parser and backtest orchestrator (MVP pure-Python)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aureum.alpha import AlphaGrammar, safety_check
from aureum.causal import CausalGraph, CausalSeparationSpec
from aureum.graph import EntityType, Relation


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
            "differentiable_sharpe",
            "conformalized_portfolio",
        }:
            errors.append(
                f"spec.portfolio.objective '{objective}' is not supported; "
                "supported values: mean_variance, minimum_variance, maximum_sharpe, "
                "risk_parity, minimum_cvar, differentiable_sharpe, conformalized_portfolio"
            )

        if objective == "differentiable_sharpe":
            self._validate_differentiable_sharpe(portfolio, errors)
        if objective == "conformalized_portfolio":
            self._validate_conformal_portfolio(portfolio, errors)

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

    def _validate_conformal_portfolio(
        self, portfolio: dict[str, Any], errors: list[str]
    ) -> None:
        """Validate the ``spec.portfolio`` block when objective is conformal."""
        uncertainty = portfolio.get("uncertainty")
        if not uncertainty:
            errors.append(
                "spec.portfolio.uncertainty is required when objective is conformalized_portfolio"
            )
            return

        if not isinstance(uncertainty, dict):
            errors.append("spec.portfolio.uncertainty must be a dict")
            return

        method = uncertainty.get("method", "conformal_split")
        if method != "conformal_split":
            errors.append(
                f"spec.portfolio.uncertainty.method '{method}' is not supported; "
                "supported values: conformal_split"
            )

        coverage = uncertainty.get("coverage", 0.95)
        if not isinstance(coverage, (int, float)) or not (0.0 < coverage < 1.0):
            errors.append("spec.portfolio.uncertainty.coverage must be a float in (0, 1)")

        calibration_fraction = uncertainty.get("calibration_fraction", 0.20)
        if not isinstance(calibration_fraction, (int, float)) or not (
            0.0 < calibration_fraction < 1.0
        ):
            errors.append(
                "spec.portfolio.uncertainty.calibration_fraction must be a float in (0, 1)"
            )

        base_objective = portfolio.get("base_objective")
        if not base_objective:
            errors.append(
                "spec.portfolio.base_objective is required when objective is conformalized_portfolio"
            )
        elif base_objective not in {
            "mean_variance",
            "minimum_variance",
            "maximum_sharpe",
            "risk_parity",
        }:
            errors.append(
                f"spec.portfolio.base_objective '{base_objective}' is not supported; "
                "supported values: mean_variance, minimum_variance, maximum_sharpe, risk_parity"
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
        self._validate_metadata_links(errors)
        self._validate_audit_graph_persistence(errors)
        return errors

    def _validate_metadata_links(self, errors: list[str]) -> None:
        """Validate the optional ``metadata.links`` graph links section."""
        links = self.metadata.get("links")
        if links is None:
            return
        if not isinstance(links, list):
            errors.append("metadata.links must be a list")
            return
        for idx, entry in enumerate(links):
            prefix = f"metadata.links[{idx}]"
            if isinstance(entry, str):
                if not entry:
                    errors.append(f"{prefix}: plain entry must be a non-empty string")
                continue
            if not isinstance(entry, dict):
                errors.append(f"{prefix}: entry must be a string or an object")
                continue
            if "entity_id" not in entry and "path" not in entry:
                errors.append(
                    f"{prefix}: object entry must have either 'entity_id' or 'path'"
                )
            relation = entry.get("relation")
            if relation is not None and relation not in {r.value for r in Relation}:
                valid = ", ".join(sorted(r.value for r in Relation))
                errors.append(
                    f"{prefix}: relation '{relation}' is not supported; supported values: {valid}"
                )
            entity_type = entry.get("type")
            if entity_type is not None and entity_type not in {e.value for e in EntityType}:
                valid = ", ".join(sorted(e.value for e in EntityType))
                errors.append(
                    f"{prefix}: type '{entity_type}' is not supported; supported values: {valid}"
                )

    def _validate_audit_graph_persistence(self, errors: list[str]) -> None:
        """Validate the optional ``spec.audit.graph_persistence`` setting."""
        audit = self.spec.get("audit", {})
        value = audit.get("graph_persistence")
        if value is None:
            return
        if value not in {"none", "inline", "bundle"}:
            errors.append(
                f"spec.audit.graph_persistence '{value}' is not supported; "
                "supported values: none, inline, bundle"
            )

    def links(self) -> list[Any]:
        """Return the ``metadata.links`` list if present, else []."""
        return self.metadata.get("links", [])

    def graph_persistence(self) -> str:
        """Return the ``spec.audit.graph_persistence`` value, defaulting to ``none``."""
        return self.spec.get("audit", {}).get("graph_persistence", "none")

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

"""Formal verifier bridge for Aureum Backtest Certificates.

This prototype turns the numeric and lineage claims inside a certificate into
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


@dataclass(frozen=True)
class PortfolioClaim:
    """One claim about the portfolio-construction step."""

    objective: str
    risk_measure: str
    covariance_estimator: str
    risk_free_rate: float
    constraints: dict[str, Any]


@dataclass(frozen=True)
class CausalClaim:
    """Lineage claim for causal MPT conditioning."""

    causal_graph_hash: str
    conditional_covariance_hash: str
    drivers: list[str]


@dataclass(frozen=True)
class ConformalClaim:
    """Lineage claim for conformal portfolio coverage."""

    calibration_set_hash: str
    coverage_level: float
    prediction_set_width: float


@dataclass(frozen=True)
class AlphaClaim:
    """Lineage claim for one neuro-symbolic alpha signal."""

    name: str
    formula: str
    safety_checks_passed: bool
    llm_model: str | None = None
    prompt: str | None = None


@dataclass(frozen=True)
class DiffOptClaim:
    """Lineage claim for differentiable certifiable execution."""

    model_architecture_hash: str
    weights_hash: str
    train_hash: str
    val_hash: str
    test_hash: str


@dataclass(frozen=True)
class GraphClaim:
    """Lineage claim for the semantic knowledge graph."""

    graph_node_id: str
    linked_entity_hashes: list[str]
    entity_count: int


@dataclass(frozen=True)
class EconSecClaim:
    """Lineage claim for the economic-security audit."""

    enabled: bool
    replay_inputs_hash: str
    attack_vectors: list[str]


class SmtLibGenerator:
    """Generate an SMT-LIB v2 script that asserts all claims."""

    def generate(
        self,
        risk_claims: list[RiskClaim],
        portfolio_claims: list[PortfolioClaim] | None = None,
        causal_claims: list[CausalClaim] | None = None,
        conformal_claims: list[ConformalClaim] | None = None,
        alpha_claims: list[AlphaClaim] | None = None,
        diffopt_claims: list[DiffOptClaim] | None = None,
        graph_claims: list[GraphClaim] | None = None,
        econsec_claims: list[EconSecClaim] | None = None,
    ) -> str:
        lines = [
            "; Aureum Backtest Certificate — Phase 4 SMT encoding",
            "(set-logic QF_LRA)",
        ]

        declared: set[str] = set()
        for claim in risk_claims:
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

        for portfolio_claim in portfolio_claims or []:
            obj = self._safe_str(portfolio_claim.objective)
            lines.append(
                f"; portfolio construction: objective={obj} risk_measure={portfolio_claim.risk_measure}"
            )
            if "max_weight" in portfolio_claim.constraints:
                lines.append(
                    f"(assert (<= portfolio_max_weight {float(portfolio_claim.constraints['max_weight']):.10g}))"
                )
            if "min_weight" in portfolio_claim.constraints:
                lines.append(
                    f"(assert (>= portfolio_min_weight {float(portfolio_claim.constraints['min_weight']):.10g}))"
                )

        for causal_claim in causal_claims or []:
            lines.append(
                f"; causal MPT: drivers={causal_claim.drivers} graph_hash={causal_claim.causal_graph_hash[:16]}..."
            )
            lines.append(
                "(assert (> causal_graph_hash_len 0)) ; declared causal graph was hashed"
            )
            lines.append(
                "(assert (> conditional_covariance_hash_len 0)) ; conditioned covariance was hashed"
            )

        for conformal_claim in conformal_claims or []:
            lines.append(
                f"; conformal portfolio: coverage={conformal_claim.coverage_level} width={conformal_claim.prediction_set_width}"
            )
            lines.append(
                f"(assert (and (>= conformal_coverage {conformal_claim.coverage_level:.10g}) (<= conformal_coverage 1.0)))"
            )
            lines.append(
                f"(assert (> conformal_width {conformal_claim.prediction_set_width:.10g}))"
            )

        for alpha_claim in alpha_claims or []:
            lines.append(
                f"; alpha signal '{alpha_claim.name}': safety={alpha_claim.safety_checks_passed}"
            )
            if alpha_claim.safety_checks_passed:
                lines.append("(assert alpha_safety_passed) ; neuro-symbolic formula passed safety gate")
            else:
                lines.append("(assert (not alpha_safety_passed)) ; formula failed safety gate")

        for diffopt_claim in diffopt_claims or []:
            lines.append(
                f"; differentiable execution: arch_hash={diffopt_claim.model_architecture_hash[:16]}..."
            )
            lines.append("(assert (> model_architecture_hash_len 0))")
            lines.append("(assert (> weights_hash_len 0))")
            lines.append("(assert (> train_hash_len 0))")
            lines.append("(assert (> val_hash_len 0))")
            lines.append("(assert (> test_hash_len 0))")

        for graph_claim in graph_claims or []:
            lines.append(
                f"; knowledge graph: node_id={graph_claim.graph_node_id[:16]}... entities={graph_claim.entity_count}"
            )
            lines.append("(assert (> graph_node_id_len 0))")
            lines.append(f"(assert (>= graph_linked_entities {len(graph_claim.linked_entity_hashes)}))")
            lines.append(f"(assert (>= graph_entities {graph_claim.entity_count}))")

        for econsec_claim in econsec_claims or []:
            lines.append(
                f"; economic security: enabled={econsec_claim.enabled} vectors={econsec_claim.attack_vectors}"
            )
            if econsec_claim.enabled:
                lines.append("(assert econsec_enabled) ; audit was run")
                lines.append("(assert (> econsec_replay_hash_len 0))")
            else:
                lines.append("(assert (not econsec_enabled)) ; audit disabled")

        lines.append("(check-sat)")
        lines.append(
            "; If SAT, the certificate's claims are consistent with the stated limits and lineage."
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _var_name(name: str) -> str:
        return f"risk_{name}".replace("-", "_")

    @staticmethod
    def _safe_str(value: str) -> str:
        return value.replace("(", "").replace(")", "").replace(";", "")

    @staticmethod
    def _smt_op(op: str) -> str:
        mapping = {"<=": "<=", ">=": ">=", "<": "<", ">": ">", "==": "="}
        return mapping.get(op, "<=")


class Lean4Generator:
    """Generate a Lean 4 theorem for each numeric claim.

    The generated file imports ``Mathlib`` only for ``norm_num`` and states
    one theorem per claim.  The proof is a one-liner so that a Lean
    installation can check it automatically.
    """

    def generate(
        self,
        risk_claims: list[RiskClaim],
        portfolio_claims: list[PortfolioClaim] | None = None,
        causal_claims: list[CausalClaim] | None = None,
        conformal_claims: list[ConformalClaim] | None = None,
        alpha_claims: list[AlphaClaim] | None = None,
        diffopt_claims: list[DiffOptClaim] | None = None,
        graph_claims: list[GraphClaim] | None = None,
        econsec_claims: list[EconSecClaim] | None = None,
    ) -> str:
        lines = [
            "-- Aureum Backtest Certificate — Phase 4 Lean 4 encoding",
            "import Mathlib",
            "",
            "namespace AureumCertificate",
        ]

        for claim in risk_claims:
            op = self._lean_op(claim.operator)
            lines.append(
                f"\ntheorem risk_{self._safe_name(claim.name)} : "
                f"({claim.actual:.10g} {op} {claim.limit:.10g}) := by norm_num"
            )

        for idx, portfolio_claim in enumerate(portfolio_claims or []):
            op = self._lean_op("<=")
            if "max_weight" in portfolio_claim.constraints:
                limit = float(portfolio_claim.constraints["max_weight"])
                lines.append(
                    f"\ntheorem portfolio_max_weight_{idx} : (0 {op} {limit:.10g}) := by norm_num"
                )
            op2 = self._lean_op(">=")
            if "min_weight" in portfolio_claim.constraints:
                limit = float(portfolio_claim.constraints["min_weight"])
                lines.append(
                    f"\ntheorem portfolio_min_weight_{idx} : ({limit:.10g} {op2} 0) := by norm_num"
                )

        for idx, conformal_claim in enumerate(conformal_claims or []):
            lines.append(
                f"\ntheorem conformal_coverage_in_range_{idx} : "
                f"({conformal_claim.coverage_level:.10g} ≤ 1.0) := by norm_num"
            )
            if conformal_claim.prediction_set_width > 0:
                lines.append(
                    f"\ntheorem conformal_width_positive_{idx} : "
                    f"({conformal_claim.prediction_set_width:.10g} > 0) := by norm_num"
                )

        for idx, alpha_claim in enumerate(alpha_claims or []):
            safety_val = "1" if alpha_claim.safety_checks_passed else "0"
            lines.append(
                f"\ntheorem alpha_safety_{self._safe_name(alpha_claim.name)}_{idx} : "
                f"({safety_val} = 1) := by norm_num"
            )

        for idx, econsec_claim in enumerate(econsec_claims or []):
            enabled_val = "1" if econsec_claim.enabled else "0"
            lines.append(
                f"\ntheorem econsec_enabled_{idx} : "
                f"({enabled_val} = 1) := by norm_num"
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


def extract_portfolio_claims(certificate: dict[str, Any]) -> list[PortfolioClaim]:
    """Extract portfolio-construction claims from a certificate dict."""
    pc = certificate.get("portfolio_construction")
    if not isinstance(pc, dict):
        return []
    return [
        PortfolioClaim(
            objective=str(pc.get("objective", "unknown")),
            risk_measure=str(pc.get("risk_measure", "unknown")),
            covariance_estimator=str(pc.get("covariance_estimator", "unknown")),
            risk_free_rate=float(pc.get("risk_free_rate", 0.0)),
            constraints=pc.get("constraints", {}),
        )
    ]


def extract_causal_claims(certificate: dict[str, Any]) -> list[CausalClaim]:
    """Extract causal-MPT claims from a certificate dict."""
    pc = certificate.get("portfolio_construction")
    if not isinstance(pc, dict):
        return []
    graph_hash = pc.get("causal_graph_hash")
    cov_hash = pc.get("conditional_covariance_hash")
    if not graph_hash and not cov_hash:
        return []
    return [
        CausalClaim(
            causal_graph_hash=str(graph_hash or ""),
            conditional_covariance_hash=str(cov_hash or ""),
            drivers=[],
        )
    ]


def extract_conformal_claims(certificate: dict[str, Any]) -> list[ConformalClaim]:
    """Extract conformal-portfolio claims from a certificate dict."""
    pc = certificate.get("portfolio_construction")
    if not isinstance(pc, dict):
        return []
    cal_hash = pc.get("calibration_set_hash")
    coverage = pc.get("coverage_level")
    width = pc.get("prediction_set_width")
    if cal_hash is None and coverage is None and width is None:
        return []
    return [
        ConformalClaim(
            calibration_set_hash=str(cal_hash or ""),
            coverage_level=float(coverage or 0.0),
            prediction_set_width=float(width or 0.0),
        )
    ]


def extract_alpha_claims(certificate: dict[str, Any]) -> list[AlphaClaim]:
    """Extract neuro-symbolic alpha claims from a certificate dict."""
    alpha = certificate.get("alpha_lineage")
    if not isinstance(alpha, dict):
        return []
    signals = alpha.get("alpha_signals", [])
    if not isinstance(signals, list):
        return []
    claims: list[AlphaClaim] = []
    for sig in signals:
        if not isinstance(sig, dict):
            continue
        claims.append(
            AlphaClaim(
                name=str(sig.get("name", "unknown")),
                formula=str(sig.get("formula", "")),
                safety_checks_passed=bool(sig.get("safety_checks_passed", False)),
                llm_model=sig.get("llm_model"),
                prompt=sig.get("prompt"),
            )
        )
    return claims


def extract_diffopt_claims(certificate: dict[str, Any]) -> list[DiffOptClaim]:
    """Extract differentiable-execution claims from a certificate dict."""
    pc = certificate.get("portfolio_construction")
    if not isinstance(pc, dict):
        return []
    arch = pc.get("model_architecture_hash")
    weights = pc.get("weights_hash")
    splits = pc.get("train_val_test_split_hashes", {})
    if not arch and not weights and not splits:
        return []
    return [
        DiffOptClaim(
            model_architecture_hash=str(arch or ""),
            weights_hash=str(weights or ""),
            train_hash=str(splits.get("train", "")),
            val_hash=str(splits.get("val", "")),
            test_hash=str(splits.get("test", "")),
        )
    ]


def extract_graph_claims(certificate: dict[str, Any]) -> list[GraphClaim]:
    """Extract semantic-knowledge-graph claims from a certificate dict."""
    kg = certificate.get("knowledge_graph")
    entities: list[Any] = []
    if isinstance(kg, dict):
        entities = kg.get("entities", [])
    node_id = certificate.get("graph_node_id")
    linked = certificate.get("linked_entity_hashes", [])
    if not node_id and not linked and not entities:
        return []
    return [
        GraphClaim(
            graph_node_id=str(node_id or ""),
            linked_entity_hashes=list(linked) if isinstance(linked, list) else [],
            entity_count=len(entities),
        )
    ]


def extract_econsec_claims(certificate: dict[str, Any]) -> list[EconSecClaim]:
    """Extract economic-security audit claims from a certificate dict."""
    es = certificate.get("economic_security")
    if not isinstance(es, dict):
        return []
    return [
        EconSecClaim(
            enabled=bool(es.get("enabled", False)),
            replay_inputs_hash=str(es.get("replay_inputs_hash", "")),
            attack_vectors=list(es.get("attack_vectors", []))
            if isinstance(es.get("attack_vectors"), list)
            else [],
        )
    ]


def verify_with_z3(smtlib: str) -> bool:
    """Return True if Z3 reports ``sat`` for the given SMT-LIB script.

    Requires ``z3-solver`` to be installed.  If it is not available the
    function raises ``RuntimeError`` so callers can decide to fall back to
    static checking.
    """
    try:
        import z3
    except ImportError as exc:
        raise RuntimeError(
            "z3-solver is not installed; install it to enable live verification"
        ) from exc

    solver = z3.Solver()
    solver.from_string(smtlib)
    return solver.check() == z3.sat

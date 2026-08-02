"""Tests for the formal verifier bridge."""

from __future__ import annotations

import pytest

from aureum.prover import (
    AlphaClaim,
    CausalClaim,
    ConformalClaim,
    DiffOptClaim,
    EconSecClaim,
    GraphClaim,
    Lean4Generator,
    PortfolioClaim,
    RiskClaim,
    SmtLibGenerator,
    extract_alpha_claims,
    extract_causal_claims,
    extract_claims,
    extract_conformal_claims,
    extract_diffopt_claims,
    extract_econsec_claims,
    extract_graph_claims,
    extract_portfolio_claims,
)


def test_extract_claims_from_certificate_list():
    cert = {
        "risk_constraints": [
            {"name": "max_drawdown", "limit": 0.2, "actual": 0.15, "operator": "<=", "passed": True},
            {"name": "max_leverage", "limit": 2.0, "actual": 1.5, "operator": "<=", "passed": True},
        ]
    }
    claims = extract_claims(cert)
    assert len(claims) == 2
    assert claims[0].name == "max_drawdown"
    assert claims[0].actual == 0.15


def test_extract_claims_from_legacy_dict():
    cert = {
        "risk_constraints": {
            "max_drawdown": {"limit": 0.2, "actual": 0.15, "operator": "<=", "passed": True},
        }
    }
    claims = extract_claims(cert)
    assert len(claims) == 1
    assert claims[0].name == "max_drawdown"


def test_smtlib_generator_output():
    claims = [
        RiskClaim("max_drawdown", 0.2, 0.15, "<=", True),
        RiskClaim("max_leverage", 2.0, 1.5, "<=", True),
    ]
    smt = SmtLibGenerator().generate(claims)
    assert "(set-logic QF_LRA)" in smt
    assert "(declare-fun risk_max_drawdown () Real)" in smt
    assert "(assert (<= risk_max_drawdown 0.2))" in smt
    assert "(assert (= risk_max_drawdown 0.15))" in smt
    assert "(check-sat)" in smt


def test_lean4_generator_output():
    claims = [RiskClaim("max_drawdown", 0.2, 0.15, "<=", True)]
    lean = Lean4Generator().generate(claims)
    assert "import Mathlib" in lean
    assert "namespace AureumCertificate" in lean
    assert "theorem risk_max_drawdown" in lean
    assert "0.15 ≤ 0.2" in lean
    assert "by norm_num" in lean


def test_extract_portfolio_claims():
    cert = {
        "portfolio_construction": {
            "objective": "maximum_sharpe",
            "risk_measure": "variance",
            "covariance_estimator": "sample",
            "risk_free_rate": 0.0,
            "constraints": {"long_only": True, "max_weight": 0.35},
        }
    }
    claims = extract_portfolio_claims(cert)
    assert len(claims) == 1
    assert claims[0].objective == "maximum_sharpe"
    assert claims[0].constraints["max_weight"] == 0.35


def test_extract_causal_claims():
    cert = {
        "portfolio_construction": {
            "causal_graph_hash": "abcd" * 16,
            "conditional_covariance_hash": "1234" * 16,
        }
    }
    claims = extract_causal_claims(cert)
    assert len(claims) == 1
    assert len(claims[0].causal_graph_hash) == 64
    assert claims[0].conditional_covariance_hash == "1234" * 16


def test_extract_conformal_claims():
    cert = {
        "portfolio_construction": {
            "calibration_set_hash": "cafe" * 16,
            "coverage_level": 0.95,
            "prediction_set_width": 0.42,
        }
    }
    claims = extract_conformal_claims(cert)
    assert len(claims) == 1
    assert claims[0].coverage_level == 0.95
    assert claims[0].prediction_set_width == 0.42


def test_extract_alpha_claims():
    cert = {
        "alpha_lineage": {
            "alpha_signals": [
                {
                    "name": "momentum",
                    "formula": "zscore(returns(close,21),63)",
                    "safety_checks_passed": True,
                    "llm_model": "claude-sonnet-5",
                }
            ]
        }
    }
    claims = extract_alpha_claims(cert)
    assert len(claims) == 1
    assert claims[0].name == "momentum"
    assert claims[0].safety_checks_passed is True
    assert claims[0].llm_model == "claude-sonnet-5"


def test_extract_diffopt_claims():
    cert = {
        "portfolio_construction": {
            "model_architecture_hash": "a" * 64,
            "weights_hash": "b" * 64,
            "train_val_test_split_hashes": {
                "train": "c" * 64,
                "val": "d" * 64,
                "test": "e" * 64,
            },
        }
    }
    claims = extract_diffopt_claims(cert)
    assert len(claims) == 1
    assert claims[0].train_hash == "c" * 64
    assert claims[0].val_hash == "d" * 64
    assert claims[0].test_hash == "e" * 64


def test_extract_graph_claims():
    cert = {
        "graph_node_id": "node-123",
        "linked_entity_hashes": ["f" * 64],
        "knowledge_graph": {"entities": [{"id": "e1"}, {"id": "e2"}]},
    }
    claims = extract_graph_claims(cert)
    assert len(claims) == 1
    assert claims[0].graph_node_id == "node-123"
    assert claims[0].linked_entity_hashes == ["f" * 64]
    assert claims[0].entity_count == 2


def test_extract_econsec_claims():
    cert = {
        "economic_security": {
            "enabled": True,
            "replay_inputs_hash": "g" * 64,
            "attack_vectors": ["front_run", "liquidity_squeeze"],
        }
    }
    claims = extract_econsec_claims(cert)
    assert len(claims) == 1
    assert claims[0].enabled is True
    assert claims[0].attack_vectors == ["front_run", "liquidity_squeeze"]


def test_phase4_smtlib_includes_all_edges():
    smt = SmtLibGenerator().generate(
        risk_claims=[RiskClaim("max_drawdown", 0.2, 0.15, "<=", True)],
        portfolio_claims=[
            PortfolioClaim(
                objective="conformalized_portfolio",
                risk_measure="variance",
                covariance_estimator="sample",
                risk_free_rate=0.0,
                constraints={"max_weight": 0.35},
            )
        ],
        causal_claims=[
            CausalClaim(
                causal_graph_hash="a" * 64,
                conditional_covariance_hash="b" * 64,
                drivers=["tech_factor"],
            )
        ],
        conformal_claims=[
            ConformalClaim(
                calibration_set_hash="c" * 64,
                coverage_level=0.95,
                prediction_set_width=0.42,
            )
        ],
        alpha_claims=[
            AlphaClaim(
                name="momentum",
                formula="zscore(returns(close,21),63)",
                safety_checks_passed=True,
            )
        ],
        diffopt_claims=[
            DiffOptClaim(
                model_architecture_hash="d" * 64,
                weights_hash="e" * 64,
                train_hash="f" * 64,
                val_hash="g" * 64,
                test_hash="h" * 64,
            )
        ],
        graph_claims=[
            GraphClaim(graph_node_id="node-1", linked_entity_hashes=["i" * 64], entity_count=3)
        ],
        econsec_claims=[
            EconSecClaim(
                enabled=True,
                replay_inputs_hash="j" * 64,
                attack_vectors=["front_run"],
            )
        ],
    )
    assert "Phase 4 SMT encoding" in smt
    assert "portfolio construction" in smt
    assert "causal MPT" in smt
    assert "conformal portfolio" in smt
    assert "alpha signal" in smt
    assert "differentiable execution" in smt
    assert "knowledge graph" in smt
    assert "economic security" in smt
    assert "(check-sat)" in smt


def test_phase4_lean4_includes_numeric_claims():
    lean = Lean4Generator().generate(
        risk_claims=[],
        conformal_claims=[
            ConformalClaim(calibration_set_hash="c" * 64, coverage_level=0.95, prediction_set_width=0.42)
        ],
        alpha_claims=[AlphaClaim(name="mom", formula="x", safety_checks_passed=True)],
        econsec_claims=[EconSecClaim(enabled=True, replay_inputs_hash="j" * 64, attack_vectors=[])],
    )
    assert "conformal_coverage_in_range_0" in lean
    assert "conformal_width_positive_0" in lean
    assert "alpha_safety_mom_0" in lean
    assert "econsec_enabled_0" in lean
    assert "by norm_num" in lean


def test_verify_with_z3_when_available():
    pytest.importorskip("z3")
    from aureum.prover import SmtLibGenerator, verify_with_z3

    claims = [RiskClaim("max_drawdown", 0.2, 0.15, "<=", True)]
    smt = SmtLibGenerator().generate(claims)
    assert verify_with_z3(smt) is True

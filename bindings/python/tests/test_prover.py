"""Tests for the formal verifier bridge."""

from __future__ import annotations

import pytest

from aureum.prover import (
    Lean4Generator,
    RiskClaim,
    SmtLibGenerator,
    extract_claims,
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


def test_verify_with_z3_when_available():
    pytest.importorskip("z3")
    from aureum.prover import SmtLibGenerator, verify_with_z3

    claims = [RiskClaim("max_drawdown", 0.2, 0.15, "<=", True)]
    smt = SmtLibGenerator().generate(claims)
    assert verify_with_z3(smt) is True

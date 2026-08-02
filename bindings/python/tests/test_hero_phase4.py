"""Regression test for the combined Phase 4 hero strategy.

This test loads ``examples/strategies/hero_phase4.yaml``, runs a backtest over
the synthetic price history, builds a certificate, and asserts that every
Phase 4 edge field is populated:

* alpha_lineage (Edge 4 neuro-symbolic alpha)
* portfolio_construction.causal_graph_hash (Edge 2 causal MPT)
* portfolio_construction.conditional_covariance_hash (Edge 2)
* portfolio_construction.calibration_set_hash (Edge 3 conformal portfolio)
* knowledge_graph + graph_node_id + linked_entity_hashes (Edge 5 semantic graph)
* economic_security (Edge 7 economic-security audit)
"""

from __future__ import annotations

from pathlib import Path

from aureum import __version__
from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import BacktestCertificate, get_environment
from aureum.strategy import Strategy

HERO_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "hero_phase4.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_hero_strategy_validates():
    strategy = Strategy.from_file(HERO_STRATEGY)
    errors = strategy.validate()
    assert errors == [], errors
    assert strategy.graph_persistence() == "inline"
    assert strategy.spec["audit"]["economic_security"] is True


def test_hero_phase4_certificate_has_all_edge_fields():
    """Backtest the hero strategy and assert the certificate is fully populated."""
    strategy = Strategy.from_file(HERO_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy,
        data,
        data_source=str(EXAMPLE_DATA),
        initial_nav=1_000_000.0,
        strategy_path=HERO_STRATEGY,
    )
    env = get_environment(aureum_version=__version__, cwd=HERO_STRATEGY.parent)
    cert = runner.build_certificate(
        strategy_path=HERO_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
        graph_persistence=strategy.graph_persistence(),
    )

    assert isinstance(cert, BacktestCertificate)
    assert cert.execution.trades > 0
    assert cert.execution.rebalance_count > 0

    # Edge 4: neuro-symbolic alpha lineage.
    assert cert.alpha_lineage is not None
    assert len(cert.alpha_lineage.alpha_signals) >= 1
    alpha_signal = cert.alpha_lineage.alpha_signals[0]
    assert alpha_signal["name"] == "alpha"
    assert alpha_signal["formula"]
    assert alpha_signal["safety_checks_passed"] is True

    # Edge 2 + 3: portfolio construction with causal and conformal hashes.
    pc = cert.portfolio_construction
    assert pc is not None
    assert pc.objective == "conformalized_portfolio"
    assert len(pc.causal_graph_hash) == 64
    assert len(pc.conditional_covariance_hash) == 64
    assert len(pc.calibration_set_hash) == 64
    assert pc.coverage_level == 0.95
    assert pc.prediction_set_width > 0.0

    # Edge 5: semantic knowledge graph.
    assert cert.knowledge_graph is not None
    assert cert.graph_node_id is not None
    assert len(cert.graph_node_id) > 0
    assert len(cert.linked_entity_hashes) > 0
    assert len(cert.knowledge_graph.entities) > 0

    # Edge 7: economic-security audit.
    assert cert.economic_security is not None
    assert cert.economic_security.enabled is True
    assert cert.economic_security.replay_inputs_hash
    assert cert.determinism.economic_security_hash

    # Round-trip through dict should preserve all populated edge fields.
    cert_dict = cert.to_dict()
    assert cert_dict["portfolio_construction"]["causal_graph_hash"] == pc.causal_graph_hash
    assert cert_dict["portfolio_construction"]["conditional_covariance_hash"] == pc.conditional_covariance_hash
    assert cert_dict["portfolio_construction"]["calibration_set_hash"] == pc.calibration_set_hash
    assert "knowledge_graph" in cert_dict
    assert "graph_node_id" in cert_dict
    assert "linked_entity_hashes" in cert_dict
    assert "economic_security" in cert_dict
    assert "alpha_lineage" in cert_dict

    restored = BacktestCertificate.from_dict(cert_dict)
    assert restored.portfolio_construction is not None
    assert restored.portfolio_construction.causal_graph_hash == pc.causal_graph_hash
    assert restored.portfolio_construction.conditional_covariance_hash == pc.conditional_covariance_hash
    assert restored.portfolio_construction.calibration_set_hash == pc.calibration_set_hash
    assert restored.knowledge_graph is not None
    assert restored.graph_node_id == cert.graph_node_id
    assert restored.linked_entity_hashes == cert.linked_entity_hashes
    assert restored.economic_security is not None
    assert restored.alpha_lineage is not None

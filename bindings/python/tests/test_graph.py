"""Tests for the Aureum semantic knowledge graph (Edge 5)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import BacktestCertificate, get_environment
from aureum.cli import cli
from aureum.graph import EntityType, KnowledgeGraph, Relation
from aureum.strategy import Strategy

EXAMPLE_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"
)
LINKED_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "linked_strategy.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_graph_entity_hash_is_content_addressed():
    graph = KnowledgeGraph()
    a = graph.add_entity(EntityType.STRATEGY, {"name": "momentum", "top_n": 0.2})
    b = graph.add_entity(EntityType.STRATEGY, {"name": "momentum", "top_n": 0.2})
    assert a.entity_id == b.entity_id
    assert len(graph.entities) == 1


def test_graph_entity_hash_differs_across_payloads():
    graph = KnowledgeGraph()
    a = graph.add_entity(EntityType.STRATEGY, {"name": "momentum", "top_n": 0.2})
    b = graph.add_entity(EntityType.STRATEGY, {"name": "value", "top_n": 0.2})
    assert a.entity_id != b.entity_id


def test_graph_round_trips_json():
    graph = KnowledgeGraph()
    strategy = graph.add_entity(
        EntityType.STRATEGY, {"name": "momentum"}, source_path="strategy.yaml"
    )
    data = graph.add_entity(
        EntityType.DATA_SNAPSHOT, {"sha256": "abc"}, source_path="data.csv"
    )
    graph.add_relation(Relation.DEPENDS_ON, strategy.entity_id, data.entity_id)

    restored = KnowledgeGraph.from_json(graph.to_json(indent=2))
    assert len(restored.entities) == 2
    assert len(restored.relations) == 1
    assert restored.get_entity(strategy.entity_id) is not None
    edge = restored.relations[0]
    assert edge.relation == Relation.DEPENDS_ON
    assert edge.source == strategy.entity_id
    assert edge.target == data.entity_id


def test_graph_walk_upstream_and_downstream():
    graph = KnowledgeGraph()
    a = graph.add_entity(EntityType.STRATEGY, {"name": "a"})
    b = graph.add_entity(EntityType.DATA_SNAPSHOT, {"name": "b"})
    c = graph.add_entity(EntityType.SIGNAL, {"name": "c"})
    graph.add_relation(Relation.DEPENDS_ON, a.entity_id, b.entity_id)
    graph.add_relation(Relation.DERIVED_FROM, c.entity_id, b.entity_id)

    upstream = graph.walk_upstream(a.entity_id)
    assert len(upstream) == 1
    assert upstream[0].entity_id == b.entity_id

    downstream = graph.walk_downstream(b.entity_id)
    ids = {e.entity_id for e in downstream}
    assert ids == {a.entity_id, c.entity_id}


def test_graph_add_relation_requires_existing_entities():
    graph = KnowledgeGraph()
    a = graph.add_entity(EntityType.STRATEGY, {"name": "a"})
    try:
        graph.add_relation(Relation.DEPENDS_ON, a.entity_id, "missing")
    except ValueError as exc:
        assert "target entity not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_strategy_validate_rejects_invalid_links():
    text = """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: bad-links
  links:
    - 123
spec:
  universe: {source: sp500}
  schedule: {rebalance: 1M, lookback: 252d}
  ranking:
    by: momentum_12_1
  weights:
    kind: equal
    top_n: 0.2
  execution:
    open: market_on_open
  audit:
    graph_persistence: inline
"""
    strategy = Strategy.from_yaml(text)
    errors = strategy.validate()
    assert any("metadata.links" in e for e in errors)


def test_strategy_validate_rejects_invalid_graph_persistence():
    text = """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: bad-persistence
spec:
  universe: {source: sp500}
  schedule: {rebalance: 1M, lookback: 252d}
  ranking:
    by: momentum_12_1
  weights:
    kind: equal
    top_n: 0.2
  execution:
    open: market_on_open
  audit:
    graph_persistence: remote
"""
    strategy = Strategy.from_yaml(text)
    errors = strategy.validate()
    assert any("graph_persistence" in e for e in errors)


def test_linked_strategy_is_valid():
    strategy = Strategy.from_file(LINKED_STRATEGY)
    errors = strategy.validate()
    assert errors == []
    assert strategy.graph_persistence() == "inline"
    assert len(strategy.links()) == 3


def test_backtest_certificate_round_trip_with_graph():
    strategy = Strategy.from_file(EXAMPLE_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy, data, data_source=str(EXAMPLE_DATA), initial_nav=1_000_000.0
    )
    env = get_environment(aureum_version="0.3.0")
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
        graph_persistence="inline",
    )
    assert cert.knowledge_graph is not None
    assert cert.graph_node_id is not None

    restored = BacktestCertificate.from_dict(cert.to_dict())
    assert restored.knowledge_graph is not None
    assert restored.graph_node_id == cert.graph_node_id


def test_cli_graph_inline_writes_graph_inside_certificate(tmp_path: Path) -> None:
    cert_path = tmp_path / "certificate.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--certificate",
            str(cert_path),
            "--graph",
            "inline",
        ],
    )
    assert result.exit_code == 0, result.output
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    assert "knowledge_graph" in cert
    assert "graph_node_id" in cert
    graph = cert["knowledge_graph"]
    assert "entities" in graph
    assert "relations" in graph
    assert any(e["entity_type"] == "certificate" for e in graph["entities"].values())


def test_cli_graph_bundle_writes_sidecar_file(tmp_path: Path) -> None:
    cert_path = tmp_path / "certificate.json"
    bundle_path = tmp_path / "bundle.tar.gz"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backtest",
            str(EXAMPLE_STRATEGY),
            "--data",
            str(EXAMPLE_DATA),
            "--certificate",
            str(cert_path),
            "--bundle",
            str(bundle_path),
            "--graph",
            "bundle",
        ],
    )
    assert result.exit_code == 0, result.output
    graph_path = cert_path.with_suffix(".graph.json")
    assert graph_path.exists(), result.output
    sidecar = json.loads(graph_path.read_text(encoding="utf-8"))
    assert "entities" in sidecar
    assert "relations" in sidecar
    assert bundle_path.exists()

"""Semantic knowledge graph for Aureum backtest lineage.

Edge 5 adds a small, content-addressed, in-memory semantic knowledge graph to
Aureum.  Every meaningful artifact (strategy, data snapshot, signal, risk model,
portfolio construction recipe, position set, certificate contract, certificate,
and backtest run) becomes a typed node with a deterministic ID derived from its
canonical content.  Nodes declare typed edges to other nodes, and the resulting
graph can be persisted alongside certificates.

The module intentionally uses only the Python standard library.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class EntityType(str, Enum):
    """Known node types in the Aureum knowledge graph."""

    STRATEGY = "strategy"
    DATA_SNAPSHOT = "data_snapshot"
    SIGNAL = "signal"
    RISK_MODEL = "risk_model"
    PORTFOLIO_RECIPE = "portfolio_recipe"
    POSITION_SET = "position_set"
    CONTRACT = "contract"
    CERTIFICATE = "certificate"
    BACKTEST_RUN = "backtest_run"


class Relation(str, Enum):
    """Known edge types in the Aureum knowledge graph."""

    DEPENDS_ON = "depends_on"
    DERIVED_FROM = "derived_from"
    BACKTEST_INPUT = "backtest_input"
    BACKTEST_OUTPUT = "backtest_output"
    USES_SIGNAL = "uses_signal"
    CALIBRATED_WITH = "calibrated_with"
    GENERATED_BY = "generated_by"
    VERSION_OF = "version_of"
    VIOLATED_CONSTRAINT = "violated_constraint"


@dataclass(frozen=True)
class Entity:
    """A single typed node in the knowledge graph."""

    entity_id: str
    entity_type: EntityType
    payload: dict[str, Any]
    source_path: str | None
    created_at: str


@dataclass(frozen=True)
class RelationEdge:
    """A single directed edge between two entities."""

    relation: Relation
    source: str
    target: str
    edge_hash: str


def _canonical_json(obj: Any) -> str:
    """Serialize an object to a stable, sorted JSON string."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a determinism-friendly copy of ``payload``.

    * floats are rounded to 6 decimal places;
    * lists of strings are sorted (e.g. symbol lists);
    * nested dicts are processed recursively.
    """

    def _normalize(value: Any) -> Any:
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, list):
            normalized = [_normalize(item) for item in value]
            if all(isinstance(item, str) for item in normalized):
                return sorted(normalized)
            return normalized
        if isinstance(value, dict):
            return {key: _normalize(value[key]) for key in sorted(value)}
        return value

    return _normalize(payload)


def _entity_id(entity_type: EntityType, payload: dict[str, Any]) -> str:
    """Compute the content-addressed ID of an entity."""
    normalized_payload = _normalize_payload(payload)
    canonical = _canonical_json(
        {"entity_type": entity_type.value, "payload": normalized_payload}
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _relation_edge_hash(
    relation: Relation, source: str, target: str, timestamp: str
) -> str:
    """Compute the content-addressed hash of a relation edge."""
    canonical = _canonical_json(
        {
            "relation": relation.value,
            "source": source,
            "target": target,
            "timestamp": timestamp,
        }
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class KnowledgeGraph:
    """Content-addressed semantic knowledge graph for Aureum lineage."""

    def __init__(
        self,
        entities: dict[str, Entity] | None = None,
        relations: list[RelationEdge] | None = None,
    ) -> None:
        self._entities: dict[str, Entity] = dict(entities) if entities else {}
        self._relations: list[RelationEdge] = list(relations) if relations else []

    @property
    def entities(self) -> dict[str, Entity]:
        return dict(self._entities)

    @property
    def relations(self) -> list[RelationEdge]:
        return list(self._relations)

    def add_entity(
        self,
        entity_type: EntityType,
        payload: dict[str, Any],
        source_path: str | None = None,
    ) -> Entity:
        """Add a node.  Re-adding identical content returns the same node."""
        entity_id = _entity_id(entity_type, payload)
        if entity_id in self._entities:
            return self._entities[entity_id]

        entity = Entity(
            entity_id=entity_id,
            entity_type=entity_type,
            payload=payload,
            source_path=source_path,
            created_at=dt.datetime.now(dt.UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        )
        self._entities[entity_id] = entity
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._entities.get(entity_id)

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self._entities

    def add_relation(
        self,
        relation: Relation,
        source: str,
        target: str,
    ) -> RelationEdge:
        """Add a typed edge from ``source`` to ``target``."""
        if source not in self._entities:
            raise ValueError(f"source entity not found: {source}")
        if target not in self._entities:
            raise ValueError(f"target entity not found: {target}")

        timestamp = (
            dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
        )
        edge_hash = _relation_edge_hash(relation, source, target, timestamp)
        edge = RelationEdge(
            relation=relation,
            source=source,
            target=target,
            edge_hash=edge_hash,
        )
        self._relations.append(edge)
        return edge

    def relations_from(self, source: str) -> list[RelationEdge]:
        """Return all edges whose source is ``source``."""
        return [edge for edge in self._relations if edge.source == source]

    def relations_to(self, target: str) -> list[RelationEdge]:
        """Return all edges whose target is ``target``."""
        return [edge for edge in self._relations if edge.target == target]

    def walk_upstream(self, start_id: str, depth: int = 10) -> list[Entity]:
        """Return dependency entities reachable from ``start_id`` up to ``depth``.

        Edges are stored as ``dependent -> dependency`` (e.g.
        ``certificate -> strategy`` with relation ``BACKTEST_INPUT``), so walking
        upstream follows outgoing edges.
        """
        if start_id not in self._entities:
            return []

        queue: list[tuple[str, int]] = [(start_id, 0)]
        seen: set[str] = {start_id}
        result: list[Entity] = []

        while queue:
            current, d = queue.pop(0)
            if d == depth:
                continue
            for edge in self.relations_from(current):
                target = edge.target
                target_entity = self._entities.get(target)
                if target_entity is None:
                    continue
                if target not in seen:
                    seen.add(target)
                    result.append(target_entity)
                    queue.append((target, d + 1))
                elif target_entity not in result:
                    result.append(target_entity)

        return result

    def walk_downstream(self, start_id: str, depth: int = 10) -> list[Entity]:
        """Return dependents reachable from ``start_id`` up to ``depth``."""
        if start_id not in self._entities:
            return []

        queue: list[tuple[str, int]] = [(start_id, 0)]
        seen: set[str] = {start_id}
        result: list[Entity] = []

        while queue:
            current, d = queue.pop(0)
            if d == depth:
                continue
            for edge in self.relations_to(current):
                source = edge.source
                source_entity = self._entities.get(source)
                if source_entity is None:
                    continue
                if source not in seen:
                    seen.add(source)
                    result.append(source_entity)
                    queue.append((source, d + 1))
                elif source_entity not in result:
                    result.append(source_entity)

        return result

    def deduplicate(self) -> KnowledgeGraph:
        """Return a new graph with only the most recent edge per (relation, source, target)."""
        seen: set[tuple[str, str, str]] = set()
        unique: list[RelationEdge] = []
        for edge in reversed(self._relations):
            key = (edge.relation.value, edge.source, edge.target)
            if key not in seen:
                seen.add(key)
                unique.insert(0, edge)
        return KnowledgeGraph(entities=self._entities, relations=unique)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "entities": {
                entity_id: {
                    "entity_id": entity.entity_id,
                    "entity_type": entity.entity_type.value,
                    "payload": entity.payload,
                    "source_path": entity.source_path,
                    "created_at": entity.created_at,
                }
                for entity_id, entity in self._entities.items()
            },
            "relations": [
                {
                    "relation": edge.relation.value,
                    "source": edge.source,
                    "target": edge.target,
                    "edge_hash": edge.edge_hash,
                }
                for edge in self._relations
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeGraph:
        entities: dict[str, Entity] = {}
        for entity_id, raw in data.get("entities", {}).items():
            entities[entity_id] = Entity(
                entity_id=raw["entity_id"],
                entity_type=EntityType(raw["entity_type"]),
                payload=raw.get("payload", {}),
                source_path=raw.get("source_path"),
                created_at=raw.get("created_at", ""),
            )

        relations: list[RelationEdge] = []
        for raw in data.get("relations", []):
            relations.append(
                RelationEdge(
                    relation=Relation(raw["relation"]),
                    source=raw["source"],
                    target=raw["target"],
                    edge_hash=raw.get("edge_hash", ""),
                )
            )

        return cls(entities=entities, relations=relations)

    def to_json(self, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> KnowledgeGraph:
        return cls.from_dict(json.loads(text))

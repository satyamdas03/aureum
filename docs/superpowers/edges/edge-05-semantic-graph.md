# Edge 5 — Semantic Knowledge Graph

Edge 5 adds a content-addressed, in-memory semantic knowledge graph to Aureum.
Every meaningful artifact in a backtest becomes a typed node with a deterministic
ID derived from its canonical content; nodes declare typed edges to other nodes,
and the resulting graph can be persisted alongside certificates.

## Why

A backtest certificate proves that a strategy produced a set of results from a
set of inputs.  The semantic graph makes the *structure* of that proof explicit:
which strategy, data snapshot, signals, risk model, portfolio recipe, positions,
and certificate participated, and how they depend on each other.  Because node
IDs are content-addressed, the graph is stable under renames, moves, and copies
as long as the underlying content does not change.

## Entity types

| Entity type      | Meaning                                              |
|------------------|------------------------------------------------------|
| `strategy`       | Parsed strategy YAML                                 |
| `data_snapshot`  | Content-addressed input price data                   |
| `signal`         | A feature/alpha used by the strategy                 |
| `risk_model`     | The risk estimator used by the optimizer             |
| `portfolio_recipe` | The optimizer output and configuration               |
| `position_set`   | Realized positions at a rebalance                    |
| `contract`       | External verifier contract (e.g. SMT-LIB)            |
| `backtest_run`   | The execution that produced results                  |
| `certificate`    | The ABC audit artifact wrapping the run              |

## Relation types

| Relation             | Direction                                    |
|----------------------|----------------------------------------------|
| `depends_on`         | artifact -> dependency                       |
| `derived_from`       | artifact -> source artifact                  |
| `backtest_input`     | run/certificate -> strategy or data          |
| `backtest_output`    | run -> position set                          |
| `uses_signal`        | run/strategy -> signal                       |
| `calibrated_with`    | risk model / run -> data snapshot            |
| `generated_by`       | certificate / positions -> run               |
| `version_of`         | reserved for future versioning               |
| `violated_constraint`| certificate -> constraint violation signal   |

## DSL additions

### `metadata.links`

Declare explicit lineage to external entities before the backtest runs.

```yaml
metadata:
  name: linked-momentum
  links:
    # Untyped dependency by content hash.
    - "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    # Typed link to a known entity.
    - type: risk_model
      relation: calibrated_with
      entity_id: "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    # Link resolved from a local path.
    - type: data_snapshot
      relation: backtest_input
      path: examples/data/synthetic_prices.csv
```

Rules:

- A plain string is treated as a content hash with relation `depends_on`.
- An object must have either `entity_id` or `path`.
- `relation` and `type` are optional but validated against the known enums when present.

### `spec.audit.graph_persistence`

Controls whether and how the graph is persisted:

- `none` (default): no graph is built.
- `inline`: the graph is serialized inside `certificate.json` under `knowledge_graph`.
- `bundle`: the graph is written as a sidecar `certificate.graph.json` and added to the reproducibility bundle.

The CLI `--graph` option overrides the YAML value:

```bash
aureum backtest strategy.yaml --data data.csv --certificate cert.json --graph inline
```

## Python API

```python
from aureum.graph import KnowledgeGraph, EntityType, Relation

graph = KnowledgeGraph()
strategy = graph.add_entity(EntityType.STRATEGY, {"name": "momentum"})
data = graph.add_entity(EntityType.DATA_SNAPSHOT, {"sha256": "abc"})
graph.add_relation(Relation.DEPENDS_ON, strategy.entity_id, data.entity_id)

# Walk dependency/dependent chains.
deps = graph.walk_upstream(strategy.entity_id)
dependents = graph.walk_downstream(data.entity_id)
```

The backtest runner builds the graph automatically when
`graph_persistence` is `inline` or `bundle`:

```python
cert = runner.build_certificate(
    strategy_path=..., data_path=..., environment=env,
    graph_persistence="inline",
)
assert cert.knowledge_graph is not None
```

## Determinism

Node IDs are `sha256(canonical_json({entity_type, normalized_payload}))`.
Payload normalization rounds floats to 6 decimals, sorts string lists, and sorts
dictionary keys recursively.  Edge hashes include a UTC timestamp, so duplicate
edges between the same nodes are not collapsed unless you call `graph.deduplicate()`.

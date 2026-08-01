# Aureum DSL Reference

The Aureum Quant Kernel uses a declarative YAML-based DSL for strategies.

## Top-level structure

```yaml
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: my-strategy
  description: A short human-readable description
spec:
  universe: ...
  schedule: ...
  signals: ...
  ranking: ...
  weights: ...
  risk: ...
  execution: ...
  audit: ...
```

## Metadata

| Field | Type | Description |
|---|---|---|
| `name` | string | Unique identifier |
| `description` | string | Human-readable intent |
| `tags` | list | Search/discovery tags |
| `links` | list | Optional lineage links to external entities (Edge 5) |

### `metadata.links`

Declare explicit content-addressed lineage before a backtest runs.

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

See [Edge 5 — Semantic Knowledge Graph](./superpowers/edges/edge-05-semantic-graph.md)
for the entity/relation model and persistence modes.

## Universe

Defines the investment universe and filters.

```yaml
universe:
  source: sp500
  filter:
    sector: Technology
    min_price: 5.00
    min_adv20: 1_000_000
```

## Schedule

```yaml
schedule:
  rebalance: 1M
  lookback: 252d
```

## Signals

Each signal is a typed expression over market data.

```yaml
signals:
  - name: momentum_12_1
    expr: returns(close, 252).sum() - returns(close, 21).sum()
    type: return
```

## Risk

Risk constraints can be hard (must be provable) or soft (monitored).

```yaml
risk:
  max_drawdown:
    value: 0.10
    hard: true
  max_leverage:
    value: 1.00
    hard: true
```

## Audit

```yaml
audit:
  lineage: full
  deterministic: true
  deterministic_seed: 42
  graph_persistence: inline   # none | inline | bundle (Edge 5)
```

| Field | Values | Description |
|---|---|---|
| `graph_persistence` | `none`, `inline`, `bundle` | Build and persist the semantic knowledge graph (Edge 5) |

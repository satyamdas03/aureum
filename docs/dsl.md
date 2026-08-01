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

## Neuro-symbolic alpha formulas (Edge 4)

Aureum supports deterministic, neuro-symbolic alpha formulas written in a
whitelist Lisp-style grammar.  Formulas are parsed into an auditable AST,
run through a built-in safety checker, and evaluated over OHLCV bars.

```yaml
signals:
  alpha:
    type: neuro_symbolic
    formula: if_else(gt(dollar_volume(close, volume, 20), 5_000_000.0), zscore(returns(close, 5), 63), 0.0)
    generation:
      llm_model: claude-sonnet-5
      prompt: A liquid-aware short-term momentum alpha
      safety_checks_passed: true

ranking:
  by: alpha
  ascending: false
```

Supported primitives include `close`, `volume`, `returns`, `lag`, `sma`,
`ema`, `volatility`, `momentum`, `zscore`, `rsi`, `ts_argmax`, `ts_argmin`,
`dollar_volume`, `vwma`, arithmetic operators, comparisons, and `if_else`.
The safety checker rejects unknown functions, look-ahead (negative lags),
 stochastic primitives, and structural constants such as literal prices.

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

## Portfolio objectives

Aureum supports classical MPT optimizers and a conformalized wrapper that
replaces point forecasts with conservative lower bounds from split-conformal
prediction intervals.

### Conformalized portfolio

```yaml
portfolio:
  objective: conformalized_portfolio
  base_objective: mean_variance
  uncertainty:
    method: conformal_split
    coverage: 0.95
    calibration_fraction: 0.20
  target_return: 0.001
  risk_measure: variance
  covariance_estimator: sample
  lookback_days: 252
  long_only: true
  max_weight: 0.40
  min_weight: 0.00
```

Validation rules:

- `spec.portfolio.uncertainty` is required when `objective` is `conformalized_portfolio`.
- `spec.portfolio.uncertainty.method` must be `conformal_split`.
- `spec.portfolio.uncertainty.coverage` must be a float in `(0, 1)`; default `0.95`.
- `spec.portfolio.uncertainty.calibration_fraction` must be a float in `(0, 1)`; default `0.20`.
- `spec.portfolio.base_objective` is required and must be one of `mean_variance`, `minimum_variance`, `maximum_sharpe`, or `risk_parity`.

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

## Portfolio

The optional ``spec.portfolio`` block invokes an MPT optimizer.  When a
``causal_graph`` is declared, the covariance matrix is first conditioned on the
selected latent drivers.

```yaml
portfolio:
  objective: minimum_variance
  risk_measure: variance
  covariance_estimator: sample
  lookback_days: 252
  long_only: true
  max_weight: 0.25
  causal_graph:
    drivers:
      - name: tech_factor
    edges:
      - from: tech_factor
        to: [AAPL, MSFT, NVDA, GOOGL]
  causal_separation:
    mode: condition_on
    drivers: [tech_factor]
```

| Field | Type | Description |
|---|---|---|
| `objective` | string | `mean_variance`, `minimum_variance`, `maximum_sharpe`, `risk_parity`, `minimum_cvar` |
| `risk_measure` | string | `variance`, `cvar_95`, `cvar_99` |
| `covariance_estimator` | string | `sample`, `ledoit_wolf` |
| `lookback_days` | int | Trailing window for return estimation |
| `long_only` | bool | Prohibit short positions |
| `max_weight` | float | Optional per-asset upper bound |
| `min_weight` | float | Optional per-asset lower bound |
| `causal_graph` | object | Declared driver DAG with `drivers` and `edges` |
| `causal_separation` | object | `mode: condition_on|auto` and `drivers` list or `auto_r2_threshold` |

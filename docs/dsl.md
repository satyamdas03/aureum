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
```


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

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
```

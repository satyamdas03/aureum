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

## Differentiable certifiable execution (Edge 6)

`spec.portfolio.objective` can be set to `differentiable_sharpe` to train a
small JAX MLP to maximize out-of-sample Sharpe ratio.  The model architecture
lives in a separate YAML file so it can be content-addressed independently of
the strategy.

```yaml
portfolio:
  objective: differentiable_sharpe
  lookback_days: 252
  long_only: true
  max_weight: 0.25
  model:
    architecture_file: examples/models/sharpe_mlp.yaml
  training:
    learning_rate: 0.001
    epochs: 100
    batch_size: 16
    l2_penalty: 0.001
    max_weight_penalty: 10.0
    early_stopping_patience: 20
    train_end: "2023-06-30"
    val_end: "2023-12-31"
```

The `train_end`/`val_end` dates split the data chronologically into train,
validation, and test periods.  The MLP is trained on the train set, early-
stopped on the validation set, and the backtest only takes positions during
the test set.  The resulting weights, model architecture hash, and split
hashes are recorded in the Aureum Backtest Certificate.

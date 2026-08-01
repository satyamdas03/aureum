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

## Audit

```yaml
audit:
  lineage: full
  deterministic: true
  deterministic_seed: 42
```

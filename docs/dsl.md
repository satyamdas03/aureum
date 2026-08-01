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
| `links` | list | Semantic knowledge graph links |

### `metadata.links`

Declare explicit lineage links from this strategy to other Aureum entities.
Each entry is either a plain entity ID string or an object.

```yaml
metadata:
  name: linked-momentum
  links:
    - "sha256:abc123..."
    - type: risk_model
      relation: calibrated_with
      entity_id: "sha256:def456..."
    - type: data_snapshot
      relation: backtest_input
      path: snapshots/tech_2024.csv
```

Plain entries are treated as untyped `depends_on` links.  Object entries must
have either `entity_id` or `path`, and may specify `type` and `relation`.
`relation` must be one of the values in `aureum.graph.Relation` and `type`
must be one of the values in `aureum.graph.EntityType`.

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

### Neuro-symbolic alpha formulas (Edge 4)

A signal may also declare a deterministic, human-readable formula in the
``AlphaGrammar`` Lisp-like syntax instead of relying on a hard-coded signal
name.  This makes the alpha auditable and lineage-rich.

```yaml
signals:
  - name: volume_tension
    description: High relative volume but not an extreme price outlier
    formula: div(ts_rank(volume, 20), add(1.0, abs(ts_zscore(close, 20))))
    type: rank
    generation:
      prompt_hash: "sha256:..."
      safety_checks_passed: true
      model: claude-sonnet-5
```

Supported primitives:

| Primitive | Signature | Meaning |
|---|---|---|
| ``close`` / ``volume`` | variable | current bar value |
| ``ts_lag(x, n)`` | series, int > 0 | value ``n`` bars ago |
| ``returns(x, n)`` | series, int > 0 | ``x / ts_lag(x, n) - 1`` |
| ``ts_mean(x, n)`` | series, int > 0 | trailing mean |
| ``ts_std(x, n)`` | series, int > 0 | trailing sample std |
| ``ts_zscore(x, n)`` | series, int > 0 | z-score over trailing window |
| ``ts_rank(x, n)`` | series, int > 0 | percentile rank in window |
| ``ts_min(x, n)`` / ``ts_max(x, n)`` | series, int > 0 | trailing min / max |
| ``add`` / ``sub`` / ``mul`` / ``div`` | two arguments | arithmetic |
| ``abs(x)`` / ``sign(x)`` | one argument | absolute value / sign |
| ``sqrt(x)`` | one argument | square root |

Validation rules:

- ``formula`` must parse and validate against ``AlphaGrammar.default()``.
- Every signal referenced by ``spec.ranking.by`` must be a built-in signal or a
  signal defined in ``spec.signals``.
- If ``generation`` is present, ``safety_checks_passed`` is required and must be
  a boolean.

Use the CLI to generate or validate a formula signal:

```bash
aureum alpha "Build a mean-reversion-safe momentum factor" --name momentum_safe
aureum alpha x --validate-only "sub(returns(close, 252), returns(close, 21))"
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

### Causal MPT (Edge 2)

Declare latent macro drivers and the assets they influence.  Aureum builds the
 drivers from proxy returns or from the first principal component of the child
assets, estimates per-asset exposures, and conditions the covariance matrix on the
selected drivers before optimization.  This removes shared macro correlation
from the risk estimate while leaving the expected-return estimate unchanged.

```yaml
portfolio:
  objective: minimum_variance
  covariance_estimator: sample
  lookback_days: 252
  causal_graph:
    drivers:
      - name: liquidity_factor
        proxies: [SHV]
      - name: inflation_factor
        proxies: [TIP, GLD]
    edges:
      - from: liquidity_factor
        to: [AAPL, MSFT, NVDA, GOOGL]
      - from: inflation_factor
        to: [XOM, CVX]
  causal_separation:
    mode: condition_on
    drivers: [liquidity_factor]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `causal_graph` | object | No | Declared DAG of latent drivers and asset children. Required if `causal_separation` is present. |
| `causal_graph.drivers` | list | Yes (if graph present) | Latent drivers. Each must have a unique `name`. |
| `causal_graph.drivers[].proxies` | list[str] | No | Observed symbols whose equal-weighted returns proxy the driver. |
| `causal_graph.edges` | list | Yes (if graph present) | Directed edges `from` a driver `to` affected assets. |
| `causal_separation` | object | Yes (if graph present) | Controls which drivers are conditioned out. |
| `causal_separation.mode` | string | Yes | `condition_on` or `auto`. |
| `causal_separation.drivers` | list[str] | Yes when `mode == condition_on` | Driver names to remove from covariance. |
| `causal_separation.auto_r2_threshold` | float | No | R² threshold for `auto` mode; default `0.10`. |

Validation rules:

- Driver names must be unique.
- Every `edges[].from` must be a declared driver.
- Every `edges[].to` must be present in the optimization universe.
- The graph must be acyclic; an asset listed as a driver creates a cycle and is rejected.
- `causal_separation.drivers` must reference declared drivers.

## Audit

```yaml
audit:
  lineage: full
  deterministic: true
  deterministic_seed: 42
  graph_persistence: inline   # none | inline | bundle
```

`graph_persistence` controls how the Edge 5 semantic knowledge graph is emitted:

| Value | Behavior |
|---|---|
| `none` | Do not emit graph nodes (default). |
| `inline` | Embed the graph as `knowledge_graph` inside the certificate JSON. |
| `bundle` | Write a `certificate.graph.json` sidecar and reference it. |

### Economic-security audit (Edge 7)

Enable a mechanical adversarial audit that estimates how much value an
adversary could extract if they knew the rebalancing schedule one day in
advance.

```yaml
audit:
  economic_security: true
  economic_security_config:
    front_run_advance_days: 1
    close_on_rebalance: true
    adversary_cost_model:
      slippage: 0.001
      borrow_cost_annual: 0.03
      max_participation_rate: 0.10
    attack_vectors:
      - front_run
      - delayed_arbitrage
      - liquidity_squeeze
```

| Field | Type | Default | Description |
|---|---|---|---|
| `economic_security` | bool | `false` | Master toggle. |
| `economic_security_config.front_run_advance_days` | int | `1` | Trading days before each rebalance the adversary positions. |
| `economic_security_config.close_on_rebalance` | bool | `true` | Close the spoofed position on the rebalance day. |
| `economic_security_config.adversary_cost_model.slippage` | float | `0.001` | Adversary execution cost as a fraction of notional. |
| `economic_security_config.adversary_cost_model.borrow_cost_annual` | float | `0.03` | Shorting cost for delayed-arbitrage legs. |
| `economic_security_config.adversary_cost_model.max_participation_rate` | float | `0.10` | Max fraction of ADV the adversary can trade. |
| `economic_security_config.attack_vectors` | list[str] | all | Subset of `front_run`, `delayed_arbitrage`, `liquidity_squeeze`. |

## Differentiable certifiable execution (Edge 6)

`spec.portfolio.objective` can be set to `differentiable_sharpe` to train a
small JAX MLP by gradient descent and still emit an Aureum Backtest
Certificate.  The strategy must declare a `model.architecture_file` and a
`training` block with `train_end` / `val_end` splits.

```yaml
portfolio:
  objective: differentiable_sharpe
  long_only: true
  max_weight: 0.35

  model:
    architecture_file: models/sharpe_mlp.yaml
    input_features: [mean_return_252d, volatility_252d, momentum_12_1]
    hidden_units: [64, 32]
    activation: softplus
    output_temperature: 1.0

  training:
    learning_rate: 0.001
    epochs: 200
    batch_size: 16
    l2_penalty: 0.0001
    max_weight_penalty: 10.0
    early_stopping_patience: 20
    train_end: "2022-12-31"
    val_end: "2023-12-31"
```

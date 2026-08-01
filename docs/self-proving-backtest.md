# Self-Proving Backtest

Aureum's first commercial wedge is an **audit-ready backtest certificate**.  Instead
of producing a plain report, the `aureum backtest` command emits a structured,
content-addressed artifact — the **Aureum Backtest Certificate (ABC)** — that a
model validator can re-run and inspect.

## Why certificates matter

A 2026 cross-engine study found that popular backtesters can diverge by **3.71%**
on identical high-turnover strategies — roughly **$37M per year of ambiguity for a
$1B portfolio**.  The divergence comes mostly from cost-model implementation:
slippage, commissions, and fill assumptions that each engine interprets
differently.

A notebook or CSV report does not defend itself.  An ABC does:

- It records the exact input hashes (strategy YAML + price CSV).
- It records the code version and Python environment.
- It reports the execution trace (fills, NAV, rebalances).
- It evaluates declared risk constraints and marks each as passed / failed.
- It can be re-run in CI to confirm the same P&L within a deterministic tolerance.

## Generate a certificate

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate certificate.json
```

The output is a JSON file with this structure:

```json
{
  "aureum_version": "0.3.0",
  "certificate_spec_version": "1.0",
  "generated_at": "2026-07-30T12:00:00Z",
  "environment": {
    "git_commit": "abc1234",
    "git_dirty": false,
    "python_version": "3.11.9",
    "aureum_version": "0.3.0"
  },
  "inputs": {
    "strategy": {
      "path": "examples/strategies/momentum.yaml",
      "sha256": "...",
      "metadata": {"name": "tech-momentum-sector-neutral"}
    },
    "data": {
      "path": "examples/data/synthetic_prices.csv",
      "sha256": "...",
      "metadata": {"symbols": 10, "dates": 757}
    }
  },
  "execution": {
    "start_date": "2022-01-03",
    "end_date": "2024-12-31",
    "initial_nav": 1000000.0,
    "rebalance_count": 36,
    "trades": 142
  },
  "results": {
    "final_nav": 1198321.44,
    "total_return": 0.1983,
    "cagr": 0.0621,
    "volatility_annual": 0.1521,
    "sharpe_ratio": 0.4083,
    "max_drawdown": 0.1245,
    "turnover_annual": 2.15
  },
  "risk_constraints": [
    {"name": "max_drawdown", "limit": 0.30, "actual": 0.1245, "operator": "<=", "passed": true},
    {"name": "max_leverage", "limit": 1.50, "actual": 1.0, "operator": "<=", "passed": true},
    {"name": "max_turnover_annual", "limit": 20.00, "actual": 2.15, "operator": "<=", "passed": true},
    {"name": "max_concentration_single_name", "limit": 0.30, "actual": 0.20, "operator": "<=", "passed": true}
  ],
  "execution_trace": {
    "daily_nav": [...],
    "daily_positions": [...],
    "rebalance_log": [...]
  },
  "determinism": {
    "input_hash": "sha256:...",
    "result_hash": "sha256:...",
    "tolerance": "1e-6 relative + 1e-9 absolute"
  }
}
```

## Create a reproducibility bundle

For model-risk review, bundle the inputs and the certificate together:

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --bundle momentum-run.tar.gz
```

The tarball contains `strategy.yaml`, `data.csv`, and `certificate.json`.  A
validator can extract the bundle, re-run the exact same command, and compare the
new certificate against the bundled one.

## Catch a real bug

The repo includes a deliberately misconfigured strategy that demonstrates what
the certificate catches:

```bash
aureum backtest examples/strategies/buggy_slippage.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate buggy.json
```

The buggy strategy sets slippage to `0.05` (5%) instead of `0.0005` (5 bps) — a
classic percentage-vs-fraction data-entry error.  The certificate flags the
result:

```json
{"name": "max_drawdown", "limit": 0.30, "actual": 0.6174, "operator": "<=", "passed": false, "hard": true}
```

Because the constraint is marked `hard: true`, a CI pipeline or validator can
treat this run as a failure before any capital is allocated.

## Validate a certificate programmatically

```python
from pathlib import Path
from aureum import BacktestCertificate
from aureum.verifier import all_passed

raw = Path("certificate.json").read_text(encoding="utf-8")
cert = BacktestCertificate(**json.loads(raw))

print("Input hash:", cert.determinism.input_hash)
print("All constraints passed:", all_passed(cert.risk_constraints))
```

## Phase 2: dimensional types, real data, and theorem-prover bridges

### Dimensional type enforcement

Aureum's backtest runner now tracks cash, prices, shares, and notional values as
dimensioned quantities.  `USD / (USD/share)` is `shares`; adding `USD` to
`shares` raises a `ValueError` and is recorded in the certificate as a
`DimensionalError`.  This prevents the classic unit-mismatch bugs that cost real
money in quant systems.

Under the hood the runner uses:

- `DOLLARS` (`USD`)
- `SHARE_COUNT` (`shares`)
- `PRICE_PER_SHARE` (`USD / shares`)
- `RATE` (dimensionless return)

### Real market data snapshots

The `aureum snapshot` command fetches daily bars from Alpaca and writes a
deterministic CSV with a sidecar `.snapshot.json` file that records SHA-256
hashes, symbols, date range, and feed.  The snapshot CSV can be fed directly
into `aureum backtest --data ...` and its hash appears in the certificate's
input lineage.

```bash
export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...

aureum snapshot --symbols AAPL,MSFT,NVDA,GOOGL \
  --start 2024-01-01 --end 2024-12-31 \
  --output snapshots/tech_2024.csv

aureum backtest examples/strategies/momentum.yaml \
  --data snapshots/tech_2024.csv \
  --certificate certificate.json
```

### SMT-LIB and Lean 4 verifier bridge

The `--smt` and `--lean` flags export the certificate's risk-constraint claims
as machine-checkable artefacts:

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --smt risk.smt2 --lean risk.lean
```

`risk.smt2` is a QF_LRA SMT-LIB script suitable for Z3, CVC5, or MathSAT.
`risk.lean` is a Lean 4 file with one theorem per risk constraint proved by
`norm_num`.  These are prototypes: they encode the *claims* of the certificate,
and a future phase will connect them to a full proof of the execution itself.

## What is "machine-checkable" now?

- **Static verification**: input lineage, deterministic re-run, and risk
  constraints are all independently checkable.
- **Dimensional verification**: unit mismatches are caught at execution time and
  surfaced in the certificate.
- **Solver-ready encoding**: risk claims can be fed directly to SMT or Lean.

A fully formal proof of the runner's correctness (and cryptographic signing of
certificates) remains on the roadmap.

## Phase 3: AI authoring and reflection

### Generate strategies from natural language

```bash
export ANTHROPIC_API_KEY=...
aureum author "Tech momentum strategy with 12-1 ranking, equal weights on top 20%, max drawdown 30%, max leverage 1.5" \
  --output examples/strategies/ai_momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --dry-run
```

The `author` command sends the prompt to Claude, validates the generated YAML,
and optionally runs a dry-run backtest before writing the file.

### Autonomous reflection on failing strategies

```bash
aureum reflect examples/strategies/buggy_slippage.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate buggy.json \
  --max-attempts 3
```

The `reflect` command reads the backtest certificate, identifies hard
constraint failures and dimensional errors, asks Claude for a fix, and
iterates. Each attempt is saved as a numbered draft (`strategy.001.yaml`,
`strategy.002.yaml`, …). The original file is only overwritten once all hard
constraints pass.

This is the foundation for the future **Aureum Cloud** tier, where the same
loop runs continuously on a portfolio of strategies and emails a model-risk
report.

## Alpha lineage (Edge 4)

When a backtest uses neuro-symbolic alpha signals, the certificate records an
`alpha_lineage` block describing each formula, its parsed AST, and the safety
verdict.  This makes the alpha fully auditable: every primitive is drawn from
a deterministic, whitelist grammar with no look-ahead and no stochastic
inputs.

### Generate an alpha from a prompt

```bash
export ANTHROPIC_API_KEY=...
aureum alpha "A liquid-aware short-term momentum alpha" \
  --name alpha-momentum-reversal \
  --output examples/strategies/alpha_momentum_reversal.yaml
```

### Validate a formula without calling the LLM

```bash
aureum alpha "sma(close, 20) / close" --validate-only
```

The safety checker rejects unknown functions, negative lags, stochastic
primitives, and price-level constants.  When the backtest certificate is
emitted, the alpha lineage is included so reviewers can reconstruct exactly
which signal was evaluated on each bar.

## Next steps

- Read the [DSL reference](./dsl.md) to design your own strategies.
- Read the [architecture](./architecture.md) to understand the Rust execution
  engine and verifier bridge.
- Open an issue on [GitHub](https://github.com/satyamdas03/aureum) if you want a
  specific risk constraint or data adapter supported.

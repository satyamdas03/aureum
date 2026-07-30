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
  "aureum_version": "0.2.0",
  "certificate_spec_version": "1.0",
  "generated_at": "2026-07-30T12:00:00Z",
  "environment": {
    "git_commit": "abc1234",
    "git_dirty": false,
    "python_version": "3.11.9",
    "aureum_version": "0.2.0"
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

## What is "machine-checkable" in Phase 1?

Phase 1 provides **model-risk evidence**, not a formal proof or regulator-signed
artifact.  A validator can mechanically:

1. Recompute the SHA-256 of the bundled inputs and compare to the certificate.
2. Re-run `aureum backtest` in the recorded environment and compare metrics to
   the deterministic tolerance.
3. Inspect the risk-constraint compliance list.

Formal proof (Lean / SMT) and cryptographic signing are on the roadmap for later
phases.

## Next steps

- Read the [DSL reference](./dsl.md) to design your own strategies.
- Read the [architecture](./architecture.md) to understand the Rust execution
  engine and verifier bridge.
- Open an issue on [GitHub](https://github.com/satyamdas03/aureum) if you want a
  specific risk constraint or data adapter supported.

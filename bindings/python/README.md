# Aureum Python Bindings

Python developer API and CLI for the Aureum self-proving semantic kernel for finance.

This package provides:

- `aureum` — the command-line interface for deterministic backtests, strategy authoring, snapshots, reflection, and the new Phase 4 portfolio-construction edges.
- Python modules for classical MPT, causal MPT, conformal portfolios, neuro-symbolic alpha, semantic knowledge graphs, differentiable execution, and economic-security audit.
- A self-proving backtest certificate (ABC) with SHA-256 lineage and reproducibility guarantees.

For the full project README, roadmap, and documentation, see the repository root:
https://github.com/satyamdas03/aureum

## Install

```bash
pip install aureum
```

## Quick start

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate certificate.json
```

## License

Apache-2.0

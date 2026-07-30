# Getting Started

## Installation

Aureum requires Python 3.11+ and Rust 1.80+.

```bash
pip install aureum
```

For development:

```bash
git clone https://github.com/point/aureum.git
cd aureum
cargo build --workspace
pip install -e bindings/python
```

## Run your first backtest

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate certificate.json
```

## Generate a reproducibility bundle

```bash
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --bundle momentum-run.tar.gz
```

## Next steps

- Read the [Self-Proving Backtest tutorial](./self-proving-backtest.md)
- Read the [DSL reference](./dsl.md)
- Explore the [architecture](./architecture.md)
- Join the community on GitHub

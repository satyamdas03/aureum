# Aureum

Aureum is a **self-proving semantic kernel for finance**.

It lets you write, run, and audit financial models, contracts, reports, and trading strategies in one meaning-layer — so an AI agent can propose a trade, and a theorem prover can prove it is safe.

## What makes Aureum different

- **Self-proving backtests:** Every run emits a structured, content-addressed
  **Aureum Backtest Certificate (ABC)** that a model validator can re-run and
  inspect.
- **Semantic substrate:** Every object has a canonical identity and meaning (FIBO, CDM, ACTUS).
- **Dimensional types:** `float<USD>` and `float<shares>` cannot be added by mistake.
- **Deterministic execution:** The same inputs produce the same outputs within a deterministic tolerance.
- **Proof as a service:** Risk constraints are checked by Lean 4 / SMT, not just unit tests.
- **Polyglot:** Use Python, Excel, SQL, or Solidity. Aureum provides the meaning-layer underneath.

## Get started

```bash
pip install aureum
```

```python
from aureum import Strategy

strategy = Strategy.from_yaml("examples/strategies/momentum.yaml")
report = strategy.backtest(data="examples/data/prices.parquet")
report.summary()
```

## Learn more

- [Architecture](./architecture.md)
- [Contributing](./contributing.md)
- [GitHub](https://github.com/satyamdas03/aureum)

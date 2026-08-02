# Aureum Phase 4 — Provable Portfolio Construction + Seven Revolutionary Edges

**Version:** 0.4.0  
**Ship date:** 2026-08-01  
**Repo:** https://github.com/satyamdas03/aureum  
**Release:** https://github.com/satyamdas03/aureum/releases/tag/v0.4.0

## TL;DR

Aureum is a self-proving semantic kernel for quantitative finance. With v0.4.0 it now ships **seven mutually-reinforcing edges** that turn a strategy YAML file into a machine-checkable audit artifact:

1. **Classical MPT** — mean-variance, GMVP, max-Sharpe, risk-parity, min-CVaR optimizers.
2. **Causal MPT** — condition covariance on declared latent drivers before optimization.
3. **Conformal portfolios** — wrap point forecasts in split-conformal prediction sets so the optimizer respects uncertainty.
4. **Neuro-symbolic alpha** — auditable, grammar-safe formulas with LLM provenance.
5. **Semantic knowledge graph** — content-addressed entities and typed relations across the whole investment process.
6. **Differentiable certifiable execution** — JAX/Optax learned Sharpe policy with model lineage.
7. **Economic-security audit** — adversarial extractable-value analysis against front-running and liquidity squeezes.

All seven are integrated into a single backtest runner, recorded in the **Aureum Backtest Certificate (ABC)**, and exposed through a YAML/CLI + web-studio interface.

## The problem we are solving

The quant research-to-production pipeline is broken in three places:

1. **Rewrite gap.** A strategy validated in a Jupyter notebook is rewritten in C++/Java for production. The two implementations diverge; compliance cannot verify that the live code matches the research.
2. **Opaqueness.** Black-box alphas and optimizers produce weights, but the certificate of correctness is a PowerPoint deck, not a reproducible artifact.
3. **Adversarial blindness.** Most backtests ignore market-impact and front-running. A strategy that looks great in simulation can be bled dry the moment it goes live.

Aureum fixes this by making the backtest certificate itself the source of truth. Every number, hash, and claim in the certificate is reproducible from the committed inputs.

## What is new in v0.4.0

### A single hero strategy exercises five edges at once

```yaml
# examples/strategies/hero_phase4.yaml
spec:
  signals:
    alpha:
      type: neuro_symbolic
      formula: if_else(gt(dollar_volume(close, volume, 20), 1_000_000.0), zscore(returns(close, 21), 63), 0.0)
      generation:
        llm_model: claude-sonnet-5
        safety_checks_passed: true

  portfolio:
    objective: conformalized_portfolio
    base_objective: maximum_sharpe
    uncertainty:
      method: conformal_split
      coverage: 0.95
      calibration_fraction: 0.20
    causal_graph:
      drivers:
        - name: tech_factor
      edges:
        - from: tech_factor
          to: [AAPL, MSFT, NVDA, GOOGL, META, AMZN, AVGO]
    causal_separation:
      mode: condition_on
      drivers: [tech_factor]

  audit:
    lineage: full
    deterministic: true
    graph_persistence: inline
    economic_security: true
```

Running `aureum backtest examples/strategies/hero_phase4.yaml --data examples/data/synthetic_prices.csv` produces a certificate whose lineage fields are all populated:

- `portfolio_construction.causal_graph_hash`
- `portfolio_construction.conditional_covariance_hash`
- `portfolio_construction.calibration_set_hash`
- `portfolio_construction.coverage_level`
- `portfolio_construction.prediction_set_width`
- `alpha_lineage.alpha_signals[].formula`
- `alpha_lineage.alpha_signals[].safety_checks_passed`
- `knowledge_graph`, `graph_node_id`, `linked_entity_hashes`
- `economic_security.enabled`, `economic_security.replay_inputs_hash`
- `determinism.economic_security_hash`

### The verifier bridge now speaks Phase 4

`aureum/prover.py` exports SMT-LIB and Lean 4 encodings for every edge claim, not just risk constraints. Z3 (or CVC5/MathSAT) can check that the certificate is internally consistent.

### Aureum Studio visualizes the new lineage

The web dashboard now shows an expandable **Phase 4 Lineage** panel with hashes, coverage levels, alpha formulas, graph entity counts, and economic-security status.

## Why this matters for real-world finance

| Pain | Aureum answer |
|---|---|
| "Did the research code match production?" | One content-addressed strategy YAML + deterministic runner = same inputs always produce the same certificate. |
| "Is this alpha safe to run?" | Neuro-symbolic formulas are grammar-checked; every formula is in the certificate with LLM provenance. |
| "What if my factor is spurious correlation?" | Causal MPT explicitly models latent drivers and conditions them out of covariance. |
| "How do I know the optimizer respected uncertainty?" | Conformal prediction sets replace point forecasts; coverage is recorded in the certificate. |
| "Can an adversary front-run me?" | Economic-security audit simulates front-running and liquidity squeezes and records an upper bound on extractable value. |
| "Where is the audit trail?" | Semantic knowledge graph links strategy, data, model weights, and certificate as a single content-addressed graph. |

## Roadmap

- **v0.4.x** (now): PyPI package + documentation push.
- **v0.5.0**: Cloud-hosted backtest runner, team workspaces, live Alpaca paper-trading adapter.
- **v0.6.0**: Theorem-prover hardening — generate and check proofs for MPT optimality and causal separation claims.
- **v0.7.0**: Expand from quant strategies into contract lifecycle (ACTUS/CDM) and regulatory reporting DSLs.

## Try it

```bash
git clone https://github.com/satyamdas03/aureum.git
cd aureum/bindings/python
pip install -e .
aureum backtest examples/strategies/hero_phase4.yaml --data examples/data/synthetic_prices.csv
```

Or launch the studio:

```bash
pip install -e ".[web]"
uvicorn aureum.server:app --reload --port 8000
cd ../../frontend/web
npm install
npm run dev
```

## Acknowledgements

Aureum v0.4.0 was built by combining the v0.3.0 self-proving backtest core with research-backed extensions in causal inference, conformal prediction, neuro-symbolic programming, differentiable optimization, knowledge graphs, and adversarial market analysis. The goal remains the same: a financial semantic substrate where every claim is reproducible, auditable, and machine-checkable.

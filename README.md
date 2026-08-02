<div align="center">

# ✨ Aureum

## The Self-Proving Semantic Kernel for Finance

**Write financial logic. Prove it correct. Run it anywhere.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/rust-1.80%2B-orange)](https://www.rust-lang.org/)
[![Tests](https://img.shields.io/badge/tests-160%2B%20passing-brightgreen)](https://github.com/satyamdas03/aureum/actions)
[![Docs](https://img.shields.io/badge/docs-aureum.finance-in%20repo-lightgrey)](https://github.com/satyamdas03/aureum/tree/main/docs)

</div>

---

> *"Aureum is what happens when you stop building yet another quant library and start building the meaning-layer underneath all of finance."*

Aureum is an **open-source semantic kernel** for financial computation. It gives every contract, model, report, and trading strategy a single canonical identity, a deterministic execution path, and a machine-checkable proof of safety — so that AI agents can propose financial actions and theorem provers can decide whether they are allowed.

**This is not a new programming language.** It is the missing semantics layer that makes finance’s existing code safer, faster to write, and regulator-friendly — then lets the language emerge from the platform.

---

## 🌍 The Problem

Finance runs on **silos that pretend to understand each other**:

- A loan contract lives in a PDF.
- Its cashflow model lives in Excel.
- Its risk model lives in Python.
- Its regulatory report lives in another system.
- Its tokenized on-chain version lives in Solidity.

When a regulator asks *“prove this number”*, a bank opens 17 files. When an AI agent proposes a trade, no tool can formally guarantee it respects drawdown, leverage, or turnover limits. When a spreadsheet cell is wrong, **billions vanish**.

**The real failure mode is semantic fragmentation.**

---

## ✨ Aureum’s Solution

Aureum unifies finance under one **self-proving semantic substrate**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 4: Applications                                                │
│  Risk models · Contracts · Regulatory reports · DeFi · Quant strategies│
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: AI agents operate THROUGH the kernel                         │
│  Natural-language authoring · Reflection · Attribution                 │
│  Every proposed action = conjecture; the kernel proves or rejects it   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: Polyglot surfaces                                           │
│  Excel formulas · Python/Polars · SQL · FIX · Bloomberg · Solidity   │
│  ACTUS · CDM · XBRL                                                   │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: Formal execution engine (Rust core)                         │
│  Deterministic DAG · Dimensional types · Lean/SMT verifier bridge    │
│  Full lineage · Audit trail · Content-addressed identities             │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 0: Semantic substrate                                          │
│  FIBO · FINOS CDM · ACTUS · Custom ontologies                        │
│  One canonical identity per instrument, contract, metric, entity      │
└─────────────────────────────────────────────────────────────────────┘
```

**The result:** the same financial object can be represented as a contract, a risk model, a regulatory report, and a smart contract — and Aureum can *prove they mean the same thing*.

---

## 🚀 What Makes Aureum Extraordinary

| Capability | Why it changes everything |
|---|---|
| **🔬 Self-proving** | Risk constraints are checked by a theorem prover (Lean 4 / SMT), not just backtests. |
| **📐 Dimensional types** | `float<USD>` + `float<shares>` = compiler error, not a $900 million wire. |
| **🔗 Cross-domain equivalence** | Prove that a contract’s cashflows == the model’s cashflows == the report’s cashflows. |
| **🤖 AI-native** | LLMs author through a schema-constrained DSL; the kernel rejects unsafe outputs. |
| **🧬 Deterministic lineage** | Every output is traceable to source data, transforms, and assumptions. |
| **🌉 TradFi ↔ DeFi bridge** | Map ACTUS/CDM contracts to formally equivalent, verifiable smart contracts. |

---

## 🛠️ Quick Start

```bash
pip install aureum

# Run a deterministic backtest with a machine-checkable certificate
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate certificate.json

# Bundle inputs + certificate for model-risk review
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --bundle momentum-run.tar.gz

# Fetch a real market snapshot from Alpaca and version it by SHA-256
aureum snapshot --symbols AAPL,MSFT,NVDA,GOOGL \
  --start 2024-01-01 --end 2024-12-31 \
  --output snapshots/tech_2024.csv

# Emit SMT-LIB and Lean 4 proof obligations alongside the certificate
aureum backtest examples/strategies/momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate certificate.json \
  --smt risk.smt2 --lean risk.lean

# Generate a strategy from a plain-English prompt
export ANTHROPIC_API_KEY=...
aureum author "Long-only tech momentum, top 20% by 12-1 month momentum, equal weights, max drawdown 30%" \
  --output examples/strategies/ai_momentum.yaml

# Fix a failing strategy with the reflection loop
aureum reflect examples/strategies/buggy_slippage.yaml \
  --data examples/data/synthetic_prices.csv \
  --max-attempts 3
```

---

## 📋 Example Strategy DSL

```yaml
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: tech-momentum-sector-neutral
  description: |
    Long the top 20% of S&P 500 tech stocks by 12-1 month momentum,
    neutralized by sector, with a 10% max-drawdown guardrail.
  tags: [momentum, equity, sector-neutral]

spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.00
      min_adv20: 1_000_000

  schedule:
    rebalance: 1M
    lookback: 252d

  signals:
    - name: momentum_12_1
      expr: returns(close, 252).sum() - returns(close, 21).sum()
      type: return

  ranking:
    by: momentum_12_1
    ascending: false

  weights:
    kind: equal
    top_n: 0.20

  risk:
    max_drawdown:
      value: 0.30
      hard: true
    max_leverage:
      value: 1.50
      hard: true
    max_turnover_annual:
      value: 20.00
      hard: false
    max_concentration_single_name:
      value: 0.30
      hard: true

  audit:
    lineage: full
    deterministic: true
    deterministic_seed: 42
```

---

## 📜 Self-Proving Backtest Certificate

Aureum `0.4.0` ships the first commercial wedge: every backtest produces a
structured, content-addressed **Aureum Backtest Certificate (ABC)**.

The certificate captures:

- SHA-256 hashes of the strategy YAML and price CSV.
- Git commit, Python version, and Aureum version.
- Execution trace, daily NAV, rebalances, and fills.
- Static risk-constraint compliance (`max_drawdown`, `max_leverage`, `max_turnover_annual`, `max_concentration_single_name`).
- A deterministic input hash and result hash for CI reproducibility.

A model validator can re-run the exact same command in a fresh environment and
confirm the metrics match within a deterministic tolerance.  The repo includes a
`buggy_slippage.yaml` example that shows the certificate catching a 5% vs 5 bps
slippage misconfiguration.

Read the full tutorial in the [docs](./docs/self-proving-backtest.md).

## 🧠 Phase 4 — Provable Portfolio Construction + Seven Revolutionary Edges

Phase 4 turns the backtest certificate into a full portfolio-construction
workbench.  The `spec.portfolio` block now supports classical MPT optimizers
and six additional research-grade extensions, each with its own lineage fields
in the certificate.

| Edge | Objective / capability | Module | What the certificate records |
|---|---|---|---|
| **1** | Classical MPT: mean-variance, GMVP, max-Sharpe, risk-parity, min-CVaR | `aureum.mpt` | `PortfolioConstruction` with weights history and optimizer-inputs hash |
| **2** | **Causal MPT** — condition covariance on declared latent drivers | `aureum.causal` | `causal_graph_hash`, `conditional_covariance_hash`, per-rebalance driver betas/R² |
| **3** | **Conformal portfolios** — point forecasts replaced by conservative split-conformal prediction sets | `aureum.conformal` | `calibration_set_hash`, `coverage_level`, `prediction_set_width` |
| **4** | **Neuro-symbolic alpha** — deterministic, auditable formulas from a whitelist grammar | `aureum.alpha` | `alpha_lineage` with formula, safety verdict, and generation provenance |
| **5** | **Semantic knowledge graph** — content-addressed entities and typed relations across the investment process | `aureum.graph` | `graph_node_id`, `linked_entity_hashes`, `knowledge_graph` |
| **6** | **Differentiable certifiable execution** — JAX/Optax learned Sharpe policy with full model lineage | `aureum.diffopt` | `model_architecture_hash`, `weights_hash`, `train_val_test_split_hashes` |
| **7** | **Economic-security audit** — adversarial extractable-value analysis against front-running and liquidity squeezes | `aureum.econsec` | `economic_security` block + `economic_security_hash` in determinism |

These edges are intentionally additive: you can combine `causal_graph` with a
`conformalized_portfolio`, run a `differentiable_sharpe` policy, attach the
knowledge graph, and add the economic-security audit in one backtest.  Every
lineage hash makes the certificate reproducible and auditable.

### Example: causal + conformal portfolio with graph persistence

```yaml
portfolio:
  objective: conformalized_portfolio
  base_objective: minimum_variance
  covariance_estimator: ledoit_wolf
  uncertainty:
    method: conformal_split
    coverage: 0.90
    calibration_fraction: 0.20
  causal_graph:
    drivers:
      - name: tech_factor
    edges:
      - from: tech_factor
        to: [AAPL, MSFT, NVDA, GOOGL]
  causal_separation:
    mode: condition_on
    drivers: [tech_factor]

audit:
  graph_persistence: inline
  economic_security: true
```

### Example: neuro-symbolic alpha signal

```yaml
signals:
  alpha:
    type: neuro_symbolic
    formula: if_else(gt(dollar_volume(close, volume, 20), 5_000_000.0), zscore(returns(close, 5), 63), 0.0)
    generation:
      llm_model: claude-sonnet-5
      safety_checks_passed: true

ranking:
  by: alpha
  ascending: false
```

### CLI for the new edges

```bash
# Efficient frontier for a portfolio block
aureum frontier examples/strategies/mpt_minimum_variance.yaml

# Backtest with causal + conformal + graph + audit
aureum backtest examples/strategies/causal_conformal.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate cert.json \
  --graph inline \
  --economic-security

# Generate a neuro-symbolic alpha from a prompt
export ANTHROPIC_API_KEY=...
aureum alpha "A liquid-aware short-term momentum alpha" \
  --name momentum_reversal \
  --output examples/strategies/alpha_momentum_reversal.yaml

# Validate a formula without calling the LLM
aureum alpha "sma(close, 20) / close" --validate-only

# Backtest a learned JAX/Optax policy
aureum backtest examples/strategies/diffopt_sharpe.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate diffopt.json \
  --bundle diffopt-run.tar.gz
```

## 🖥️ Aureum Studio (Web Dashboard)

Aureum ships with a browser-based studio for interactive strategy authoring and
backtesting:

```bash
# 1. Start the API server
cd bindings/python
pip install -e ".[web]"
export ANTHROPIC_API_KEY=...
uvicorn aureum.server:app --reload --port 8000

# 2. In another terminal, start the UI
cd frontend/web
npm install
npm run dev
```

Open http://localhost:5173 to:
- Author strategies from natural-language prompts with Claude.
- Edit YAML in Monaco with instant validation.
- Run backtests and inspect NAV curves.
- View self-proving backtest certificates with SHA-256 lineage.
- Fix failing strategies with the reflection loop.

## 🎯 The Five Wedge Products

Aureum is designed to grow into five high-value financial surfaces from a single kernel:

| Wedge | Surface | Aureum advantage |
|---|---|---|
| **A** | Excel replacement for risk models | Deterministic, dimensionally typed, fully auditable models. |
| **B** | Contract lifecycle language (ACTUS/CDM/MLFi successor) | Natural-language term sheets → executable + provable cashflow machine. |
| **C** | Regulatory reporting DSL | Reports become derivable views of the semantic kernel. |
| **D** | DeFi safety language | TradFi contracts with formally equivalent on-chain semantics. |
| **E** | Quant strategy workbench | AI-authored strategies with theorem-prover risk guardrails. |

**Beachhead: E.** Quant strategy workbenches have budgets, urgency, and a research-to-production rewrite gap. Success here funds expansion into A–D.

---

## 📊 Market Context

Aureum sits at the intersection of several large, fast-growing markets:

- **Financial modeling & risk software:** ~$10–18B in 2025
- **RegTech / banking compliance:** ~$13–20B in 2025
- **Quant / algorithmic trading platforms:** ~$18–22B in 2025
- **DeFi security / smart contract audit:** ~$4.8B in 2025
- **AI in financial services:** ~$15–47B in 2025

**Combined intersection:** ~$40–100B in 2025, growing at 10–20% CAGR.

Aureum does not ask buyers to add a new budget line. It replaces the **semantic-fragmentation tax** they already pay.

---

## 🗺️ Roadmap

| Phase | Goal | Status |
|---|---|---|
| **0** | Repo, docs, and buildable skeleton | ✅ Done |
| **1** | Self-proving backtest: DSL + deterministic runner + ABC certificate | ✅ Done |
| **2** | Dimensional type enforcement + real data adapter + Lean/SMT verifier bridge | ✅ Done |
| **3** | AI authoring + reflection loop | ✅ Done |
| **4** | Provable MPT core + revolutionary edges (causal, conformal, neuro-symbolic alpha, semantic graph, diffopt, econsec) | ✅ Done |
| **5** | Multi-user surfaces (indie, fund, fintech, DeFi) | Planned |
| **6** | Public launch + community | Planned |

---

## 🏗️ Repository Structure

```
.
├── crates/aureum-core      # Rust execution engine (deterministic DAG, dimensional types, lineage)
├── crates/aureum-py        # PyO3 bindings for the Rust core
├── bindings/python         # Python package: `pip install aureum`
│   ├── aureum/mpt.py       # Classical + robust MPT optimizers (Edge 1)
│   ├── aureum/causal.py    # Driver DAG + conditioned covariance (Edge 2)
│   ├── aureum/conformal.py # Split-conformal portfolio construction (Edge 3)
│   ├── aureum/alpha.py     # Neuro-symbolic alpha DSL + safety gating (Edge 4)
│   ├── aureum/graph.py     # Content-addressed semantic knowledge graph (Edge 5)
│   ├── aureum/diffopt.py   # JAX/Optax learned Sharpe optimizer (Edge 6)
│   ├── aureum/econsec.py   # Economic-security audit (Edge 7)
│   ├── aureum/certificate.py # Self-proving backtest certificate
│   ├── aureum/backtest.py  # Deterministic runner
│   └── aureum/cli.py       # Command-line interface
├── frontend/web            # React/TypeScript web IDE and demo
├── docs                    # Documentation site (MkDocs)
├── examples/strategies     # Sample strategy DSLs
└── tests                   # Integration tests
```

---

## 🙌 Contributing

Aureum is Apache-2.0 and community-built. We are actively looking for contributors in:

- Rust core development
- Python quant tooling
- Lean 4 / formal methods
- Financial domain modeling (ACTUS, CDM, FIBO)
- Frontend / developer experience
- Documentation and examples

See [CONTRIBUTING.md](./CONTRIBUTING.md) and join the discussion in [GitHub Issues](https://github.com/satyamdas03/aureum/issues).

---

## 📜 License

Apache-2.0. See [LICENSE](./LICENSE).

The semantic substrate of finance should be a public good. Aureum is open source so that banks, funds, fintechs, researchers, and regulators can build on a shared, auditable foundation.

---

<div align="center">

**[🌐 Website](https://github.com/satyamdas03/aureum) · [📖 Docs](./docs) · [💬 Issues](https://github.com/satyamdas03/aureum/issues) · [🚀 Discussions](https://github.com/satyamdas03/aureum/discussions)**

</div>

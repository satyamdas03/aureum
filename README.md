<div align="center">

# ✨ Aureum

## The Self-Proving Semantic Kernel for Finance

**Write financial logic. Prove it correct. Run it anywhere.**

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/rust-1.80%2B-orange)](https://www.rust-lang.org/)
[![Build](https://img.shields.io/badge/build-in%20progress-yellow)](https://github.com/satyamdas03/aureum/actions)
[![Docs](https://img.shields.io/badge/docs-aureum.finance-coming%20soon-lightgrey)](https://github.com/satyamdas03/aureum)

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
aureum backtest examples/strategies/momentum.yaml --data examples/data/prices.parquet
```

**Or describe a strategy in plain English and let Aureum build it:**

```bash
aureum generate "momentum strategy on S&P 500 tech stocks, sector neutral, max drawdown 10%"
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
      value: 0.10
      hard: true
    max_leverage:
      value: 1.00
      hard: true

  audit:
    lineage: full
    deterministic: true
    deterministic_seed: 42
```

---

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
| **1** | Quant Kernel MVP: DSL + deterministic backtest + lineage | 🔨 In progress |
| **2** | Dimensional types + formal risk guardrails | Planned |
| **3** | AI authoring + reflection loop | Planned |
| **4** | Multi-user surfaces (indie, fund, fintech, DeFi) | Planned |
| **5** | Public launch + community | Planned |

---

## 🏗️ Repository Structure

```
.
├── crates/aureum-core      # Rust execution engine (deterministic DAG, dimensional types, lineage)
├── crates/aureum-py        # PyO3 bindings for the Rust core
├── bindings/python         # Python package: `pip install aureum`
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

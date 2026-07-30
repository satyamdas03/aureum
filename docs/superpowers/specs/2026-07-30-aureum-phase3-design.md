# Aureum Phase 3 — AI Authoring + Reflection Loop Design

**Date:** 2026-07-30  
**Status:** Approved for implementation  
**Project:** Aureum — self-proving semantic kernel for finance  
**Repo:** https://github.com/satyamdas03/aureum

---

## 1. Goal

Add an **AI-assisted authoring and reflection loop** to the Aureum quant strategy workbench so that:

1. A user can describe a strategy in plain English and receive a valid, runnable Aureum YAML strategy.
2. A failing strategy can be automatically diagnosed and repaired by an LLM using its backtest certificate, with bounded retries and an auditable draft trail.

This is the first premium-capability wedge that also supports a future **Aureum Cloud** commercial tier.

---

## 2. Startup Positioning

Aureum follows an **open-core + commercial services** model suitable for a bootstrapped, one-person startup:

| Tier | Offering | Revenue model |
|---|---|---|
| **Open Core** | `aureum` Python/Rust package, backtest engine, certificates, dimensional types, SMT/Lean bridge. | Free / Apache-2.0 |
| **Aureum Cloud (Solo)** | Hosted AI author/reflection, private snapshots, web dashboard, one-click certificates. | $49–99/month |
| **Aureum Cloud (Team)** | Shared workspaces, audit history, role-based access, multiple data connectors, alerts. | $299–799/month |
| **Enterprise Support** | Custom risk constraints, bespoke data adapters, SLAs, onboarding. | $5K–20K/month |
| **Consulting / Fractional CTO** | Model-risk infrastructure advisory, audit pipeline design, quant architecture. | $300–500/hour |

### Why this works for a solo founder

- Open source builds trust and acts as the best marketing channel in finance.
- Revenue can start with consulting and support before the cloud product is mature.
- The AI author/reflection loop is a natural premium feature: it saves users time and reduces model-risk mistakes.
- Public portfolio value remains high even if revenue is initially modest.

### Go-to-market phases

| Phase | Timeframe | Goal |
|---|---|---|
| Ship Phase 3 | Weeks 1–2 | Open-source AI author + reflector in `aureum` CLI. |
| Nurture | Weeks 3–8 | Case studies, LinkedIn/Twitter posts, free strategy audits. |
| Monetize | Months 2–4 | Aureum Cloud waitlist, paid beta, consulting bookings. |
| Scale | Months 6–12 | Team features, more data sources, enterprise support contracts. |

---

## 3. Architecture & Components

| Module | Purpose |
|---|---|
| `aureum/ai.py` | Thin Anthropic SDK wrapper. Reads `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (default `claude-sonnet-5`). Builds prompts and extracts YAML from LLM responses. |
| `aureum/author.py` | `StrategyAuthor` — turns a natural-language prompt into a valid Aureum strategy YAML, validates it, and optionally dry-runs a backtest. |
| `aureum/reflector.py` | `StrategyReflector` — reads a backtest certificate, diagnoses hard-constraint failures / dimensional errors, asks the LLM for a YAML fix, re-runs, and iterates up to `--max-attempts`. |
| `aureum/cli.py` | Adds `aureum author` and `aureum reflect` subcommands. |

### Component dependencies

```text
aureum/author.py  ──uses──▶ aureum/ai.py
                    ──uses──▶ aureum/strategy.py
                    ──uses──▶ aureum/backtest.py (optional dry-run)

aureum/reflector.py ──uses──▶ aureum/ai.py
                    ──uses──▶ aureum/strategy.py
                    ──uses──▶ aureum/backtest.py
                    ──uses──▶ aureum/certificate.py
```

### Key design principles

- **No real-money trades.** The loop only runs the existing paper backtest engine.
- **Always validate first.** Every LLM response is parsed and validated against the existing `Strategy` schema before any backtest runs.
- **Always keep drafts.** Each reflection attempt is saved as a numbered draft (`strategy.001.yaml`, `strategy.002.yaml`, …). Only a passing final draft overwrites the original.
- **Never leak keys.** The Anthropic API key is read only from the `ANTHROPIC_API_KEY` environment variable. No key is written to files or memory.

---

## 4. Data Flow

### `aureum author`

```text
prompt + schema + one-shot example
        │
        ▼
  StrategyAuthor
        │
        ▼
  Anthropic API call
        │
        ▼
  Extract YAML block from response
        │
        ▼
  Strategy.from_yaml().validate()
        │
        ├─ invalid ──▶ feed validation errors back to LLM (max 2 retries)
        │
        └─ valid ─────▶ optional dry-run backtest
                        │
                        ├─ dry-run requested ──▶ run backtest, build certificate
                        │
                        └─ write strategy.yaml
```

### `aureum reflect`

```text
strategy.yaml + certificate.json
        │
        ▼
  StrategyReflector
        │
        ▼
  Build diagnostic prompt from failed constraints / dimensional errors
        │
        ▼
  Anthropic API call
        │
        ▼
  Extract YAML patch / full strategy
        │
        ▼
  Validate new YAML
        │
        ├─ invalid ──▶ stop and report
        │
        └─ valid ────▶ run backtest
                        │
                        ├─ hard constraints pass ──▶ overwrite original, stop
                        │
                        └─ still failing ──▶ save draft.N.yaml, repeat
```

### Draft file naming

- Original: `strategy.yaml`
- Attempt 1: `strategy.001.yaml`
- Attempt 2: `strategy.002.yaml`
- …
- Final accepted: overwrites `strategy.yaml`

The certificate of the accepted run records the draft lineage under `execution_trace.draft_lineage`:

```json
{
  "draft_lineage": {
    "attempts": 2,
    "drafts": ["strategy.001.yaml", "strategy.002.yaml"],
    "accepted": "strategy.002.yaml"
  }
}
```

---

## 5. Prompt Design

Prompts are stored as Python string constants for portability and version control. They are explicit, schema-aware, and include one-shot examples.

### 5.1 Author prompt

Inputs:
- User prompt.
- Optional target data file path (used to infer symbols/sector context).
- Optional existing example strategies (one-shot learning).

Output instructions:
- Return **only** a fenced YAML block (` ```yaml ... ``` `).
- Provide a one-line rationale **after** the YAML block.
- Do not invent unsupported fields; only fields in the schema may appear.

The prompt explicitly lists:
- Top-level fields: `apiVersion`, `kind`, `metadata`, `spec`.
- `spec` sub-sections: `universe`, `schedule`, `signals`, `ranking`, `weights`, `risk`, `audit`.
- Risk constraint names: `max_drawdown`, `max_leverage`, `max_turnover_annual`, `max_concentration_single_name`.
- Hard vs soft semantics.

### 5.2 Reflector prompt

Inputs:
- Current strategy YAML.
- Certificate `risk_constraints` list (name, limit, actual, operator, passed, hard).
- Certificate `dimensional_errors` list (if any).
- Total return / Sharpe / max drawdown (for context).

Output instructions:
- Return a **single concrete YAML edit** that fixes the most severe hard failure.
- Explain the root cause and why the edit fixes it in 2–3 sentences.
- If no hard failure exists, explain why no edit is needed.

The prompt deliberately focuses the LLM on one failure at a time to avoid overcorrection.

---

## 6. Error Handling & Safety

| Failure | Behavior |
|---|---|
| LLM returns no YAML block | Log raw response, raise `StrategyAuthorError`, write no files. |
| YAML parses but fails validation | Send validation errors back to LLM in a correction prompt. Max 2 correction attempts. If still invalid, stop and report. |
| Backtest raises an exception during reflection | Record exception, ask LLM to fix. If the next attempt still raises, stop and report best draft. |
| Hard constraint still fails after `max_attempts` | Keep numbered drafts, leave original untouched, print failure report with paths to all drafts. |
| Anthropic API error / rate limit | Surface immediately; do not silently retry. |
| Missing `ANTHROPIC_API_KEY` | Raise `RuntimeError` with a clear message; do not proceed. |
| Draft number collision | Use the next available integer (scan existing `strategy.*.yaml` files). |

---

## 7. CLI Commands

### 7.1 `aureum author`

```bash
aureum author "Long-only tech momentum, top 20% by 12-1 month momentum, equal weights, max drawdown 30%" \
  --output examples/strategies/ai_momentum.yaml \
  --data examples/data/synthetic_prices.csv \
  --dry-run \
  --model claude-sonnet-5 \
  --max-correction-attempts 2
```

Flags:
- `PROMPT` (required positional string).
- `--output` (required): path to write the generated strategy YAML.
- `--data` (optional): data CSV used for dry-run backtest.
- `--dry-run` (flag): run a backtest and emit a certificate before writing the YAML.
- `--model` (optional): Anthropic model name.
- `--max-correction-attempts` (default 2): how many times to ask the LLM to correct invalid YAML.

### 7.2 `aureum reflect`

```bash
aureum reflect examples/strategies/buggy_slippage.yaml \
  --data examples/data/synthetic_prices.csv \
  --certificate buggy.json \
  --max-attempts 3 \
  --model claude-sonnet-5
```

Flags:
- `STRATEGY` (required positional): path to the strategy YAML to fix.
- `--data` (required): data CSV for backtests.
- `--certificate` (optional): path to an existing certificate. If omitted, the reflector runs a fresh backtest first.
- `--max-attempts` (default 3): maximum reflection iterations.
- `--model` (optional): Anthropic model name.
- `--output` (optional): path to write the accepted strategy. Defaults to overwriting the input strategy.

---

## 8. Testing Strategy

| Test | Approach |
|---|---|
| YAML extraction | Unit tests for `_extract_yaml` with fenced YAML, bare YAML, markdown prose, and missing YAML. |
| Author validation retry | Mock Anthropic to return invalid YAML first, then valid YAML; assert second prompt contains validation errors. |
| Reflector success path | Provide buggy slippage strategy + failing certificate, mock LLM to return fixed YAML; assert new certificate passes all hard constraints. |
| Reflector draft numbering | Mock LLM that never fixes the strategy; assert `strategy.001.yaml`, `strategy.002.yaml` exist and original is unchanged. |
| API key guardrail | `monkeypatch.delenv("ANTHROPIC_API_KEY")`; assert `RuntimeError` with helpful message. |
| CLI integration | `click.testing.CliRunner` for `author` and `reflect` subcommands. |
| Cost safety | Assert no API calls when prompts are missing or YAML is already valid (no unnecessary spend). |

---

## 9. Success Criteria

- `aureum author` produces a valid YAML strategy from a plain-English prompt in ≥80% of test prompts.
- `aureum reflect` fixes `buggy_slippage.yaml` within 3 attempts in CI (using a mocked LLM response that demonstrates the loop).
- All generated strategies pass `Strategy.validate()` before any backtest runs.
- Numbered drafts are preserved; originals are never overwritten unless constraints pass.
- No Anthropic API key is written to disk.
- `ruff` and `mypy` remain clean; Python test suite remains green.

---

## 10. Out of Scope for Phase 3

- Multi-provider LLM abstraction (OpenAI, local Ollama). Keep Anthropic-only for speed.
- Web UI / cloud dashboard. This is the open-source CLI foundation for a future cloud tier.
- Real-time reflection during market hours. Reflection is offline/backtest-only.
- Automatic deployment to Alpaca live trading. Aureum stays paper/research-only in the open core.
- Cryptographic signing of certificates. Remains on the roadmap.

---

## 11. Commercial Roadmap Notes

The features in Phase 3 map directly to future paid tiers:

| Open-core feature | Cloud premium extension |
|---|---|
| `aureum author` | Web-based prompt editor with template library and version history. |
| `aureum reflect` | Continuous monitoring: run reflection nightly on all strategies and email a report. |
| Versioned snapshots | Private cloud storage with team sharing and retention policies. |
| SMT/Lean bridge | PDF audit reports and regulator-facing certificate bundles. |

---

## 12. Spec Self-Review Checklist

- **Placeholders:** None. All defaults, paths, and commands are explicit.
- **Internal consistency:** CLI flags align with `author.py` / `reflector.py` responsibilities.
- **Scope:** Focused on Anthropic-only CLI loop; provider abstraction and web UI explicitly out of scope.
- **Ambiguity:** Draft numbering, overwrite rules, and validation retry counts are explicit.

---

*Spec written and committed. Ready for implementation planning.*

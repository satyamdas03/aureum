# Aureum Phase 3 — AI Authoring + Reflection Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `aureum author` and `aureum reflect` CLI commands powered by Anthropic Claude, turning plain-English prompts into valid Aureum strategy YAML and autonomously fixing failing strategies with bounded retries and numbered draft backups.

**Architecture:** A thin Anthropic SDK wrapper in `aureum/ai.py` is consumed by two orchestrators: `StrategyAuthor` (natural-language → YAML) and `StrategyReflector` (certificate → YAML fix → backtest loop). Both enforce schema validation before any backtest, keep numbered draft backups, and never write an API key to disk.

**Tech Stack:** Python 3.11+, `anthropic>=0.40.0`, existing `aureum` backtest/certificate/strategy modules, `pytest` for tests, `click` for CLI.

## Global Constraints

- Python version: `>=3.11`.
- All new dependencies must be declared in `bindings/python/pyproject.toml`.
- Anthropic API key must be read **only** from the `ANTHROPIC_API_KEY` environment variable; never hardcoded or persisted.
- Every LLM-generated YAML must pass `Strategy.validate()` before a backtest runs.
- Reflection drafts are named `<stem>.001.yaml`, `<stem>.002.yaml`, etc., in the same directory as the input strategy.
- Original strategy file is only overwritten when all hard constraints pass.
- No real-money trading: only the existing paper backtest engine may be invoked.
- `ruff` and `mypy` must remain clean; the Python test suite must stay green.
- Default Anthropic model: `claude-sonnet-5`.

---

## File Structure

| File | Responsibility |
|---|---|
| `bindings/python/pyproject.toml` | Add `anthropic` runtime dependency. |
| `bindings/python/aureum/ai.py` | Anthropic SDK wrapper, YAML extraction, prompt builders. |
| `bindings/python/aureum/author.py` | `StrategyAuthor`: prompt → validated YAML → optional dry-run. |
| `bindings/python/aureum/reflector.py` | `StrategyReflector`: failing certificate → YAML fix → loop with drafts. |
| `bindings/python/aureum/cli.py` | Add `author` and `reflect` subcommands. |
| `bindings/python/aureum/certificate.py` | Allow augmenting `execution_trace` with draft lineage (one small helper). |
| `bindings/python/tests/test_ai.py` | Unit tests for `ai.py`. |
| `bindings/python/tests/test_author.py` | Tests for `StrategyAuthor` and `author` CLI. |
| `bindings/python/tests/test_reflector.py` | Tests for `StrategyReflector` and `reflect` CLI. |
| `README.md` | Update quick-start with `author` / `reflect` examples. |
| `docs/self-proving-backtest.md` | Add Phase 3 section. |

---

## Task 1: Add Anthropic Dependency

**Files:**
- Modify: `bindings/python/pyproject.toml`

**Interfaces:**
- No code interfaces yet; this is a build/dependency task.

- [ ] **Step 1: Add `anthropic` to runtime dependencies**

```toml
[project]
dependencies = [
    "pyyaml>=6.0.2",
    "click>=8.1.0",
    "anthropic>=0.40.0",
]
```

- [ ] **Step 2: Install locally for development**

```bash
cd bindings/python
python -m pip install -e .
```

- [ ] **Step 3: Commit**

```bash
git add bindings/python/pyproject.toml
git commit -m "chore(aureum): add anthropic sdk dependency for Phase 3"
```

---

## Task 2: Anthropic Client + YAML Extraction

**Files:**
- Create: `bindings/python/aureum/ai.py`
- Test: `bindings/python/tests/test_ai.py`

**Interfaces:**
- Consumes: `anthropic.Anthropic` SDK, `ANTHROPIC_API_KEY` env var.
- Produces: `AnthropicClient.complete(prompt: str) -> str`, `_extract_yaml(text: str) -> str`, `build_author_prompt(...)` and `build_reflector_prompt(...)`.

- [ ] **Step 1: Write the failing test for YAML extraction**

```python
"""Tests for the Aureum AI client wrapper."""

from __future__ import annotations

import pytest

from aureum.ai import AnthropicClient, _extract_yaml


def test_extract_yaml_from_fenced_block():
    text = "Some prose.\n\n```yaml\napiVersion: aureum.io/v1alpha1\nkind: Strategy\n```"
    assert _extract_yaml(text) == "apiVersion: aureum.io/v1alpha1\nkind: Strategy"


def test_extract_yaml_bare_yaml():
    text = "apiVersion: aureum.io/v1alpha1\nkind: Strategy"
    assert _extract_yaml(text) == text


def test_extract_yaml_missing_yaml_raises():
    with pytest.raises(ValueError, match="No YAML block found"):
        _extract_yaml("Just prose, no code.")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python
python -m pytest tests/test_ai.py -v
```

Expected: `ImportError` or `function not defined` failures.

- [ ] **Step 3: Implement `aureum/ai.py`**

```python
"""Thin Anthropic client wrapper and prompt builders for Aureum AI features."""

from __future__ import annotations

import os
import re
from typing import Any

DEFAULT_MODEL = "claude-sonnet-5"


class StrategyAIError(Exception):
    """Raised when the AI layer produces an unusable response."""


class AnthropicClient:
    """Minimal wrapper around the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Set it and retry."
            )

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


def _extract_yaml(text: str) -> str:
    """Extract a YAML block from an LLM response.

    Looks for a fenced ```yaml block first, then any fenced block, then a bare
    YAML document starting with 'apiVersion:'.
    """
    # 1. Explicit yaml fence
    match = re.search(r"```yaml\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Any fenced block
    match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if candidate.startswith("apiVersion:") or candidate.startswith("kind:"):
            return candidate

    # 3. Bare YAML document
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("apiVersion:") or line.startswith("kind:"):
            return "\n".join(lines[i:]).strip()

    raise StrategyAIError("No YAML block found in LLM response")


def build_author_prompt(user_prompt: str, example_strategy: str | None = None) -> str:
    base = f"""You are an expert quantitative strategist using the Aureum strategy DSL.

Write a valid Aureum Strategy YAML that satisfies the user's request.

Aureum Strategy schema:
- apiVersion: aureum.io/v1alpha1
- kind: Strategy
- metadata.name (required): short slug name
- metadata.description: optional
- spec.universe (required): source, filter (sector, min_price, min_adv20)
- spec.schedule (required): rebalance (only "1M" supported), lookback (e.g. "252d")
- spec.signals: list of named signals (only momentum_12_1 is supported in the runner)
- spec.ranking (required): by, ascending, optional signal reference
- spec.weights (required): kind (only "equal"), top_n (fraction 0.0-1.0)
- spec.execution (required): slippage (e.g. 0.0005 for 5 bps)
- spec.risk: max_drawdown, max_leverage, max_turnover_annual, max_concentration_single_name
  Each constraint has value and hard (boolean). Hard failures block the strategy.

Output rules:
- Return ONLY a fenced YAML block using ```yaml.
- After the YAML block, provide a single-line rationale starting with "Rationale:".
- Do not invent unsupported fields or signals.
- Slippage must be a small decimal (e.g. 0.0005), never 0.05.
"""
    if example_strategy:
        base += f"\n\nExample strategy:\n```yaml\n{example_strategy}\n```"
    base += f"\n\nUser request:\n{user_prompt}\n\nGenerate the YAML:"
    return base


def build_refinement_prompt(
    user_prompt: str, yaml_text: str, validation_errors: list[str]
) -> str:
    return f"""The following Aureum strategy YAML is invalid.

Validation errors:
{chr(10).join(f"- {e}" for e in validation_errors)}

Original user request:
{user_prompt}

Current YAML:
```yaml
{yaml_text}
```

Fix the YAML so it passes validation. Return ONLY a fenced YAML block using ```yaml, followed by a single-line rationale starting with "Rationale:"."""


def build_reflector_prompt(
    strategy_yaml: str, certificate: dict[str, Any]
) -> str:
    risk = certificate.get("risk_constraints", [])
    hard_failures = [
        r for r in risk
        if not r.get("passed", True) and r.get("hard", False)
    ]
    soft_failures = [
        r for r in risk
        if not r.get("passed", True) and not r.get("hard", False)
    ]
    dim_errors = certificate.get("dimensional_errors", [])
    results = certificate.get("results", {})

    return f"""You are an expert model-risk engineer auditing an Aureum backtest certificate.

The strategy below failed one or more hard risk constraints, or produced dimensional errors. Propose ONE concrete YAML edit that fixes the most severe hard failure. Do not rewrite the whole strategy unless necessary.

Strategy YAML:
```yaml
{strategy_yaml}
```

Backtest results:
- total_return: {results.get("total_return")}
- max_drawdown: {results.get("max_drawdown")}
- max_leverage: {results.get("max_leverage")}
- turnover_annual: {results.get("turnover_annual")}

Hard failures:
{chr(10).join(f"- {r['name']}: limit {r['limit']}, actual {r['actual']}" for r in hard_failures) if hard_failures else "None"}

Soft failures:
{chr(10).join(f"- {r['name']}: limit {r['limit']}, actual {r['actual']}" for r in soft_failures) if soft_failures else "None"}

Dimensional errors:
{chr(10).join(f"- {e.get('step')}: {e.get('message')}" for e in dim_errors) if dim_errors else "None"}

Output rules:
- Return the COMPLETE fixed strategy as a fenced YAML block using ```yaml.
- Follow with 2-3 sentences explaining the root cause and the fix.
- If there are no hard failures, return the original YAML unchanged and explain why."""
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd bindings/python
python -m pytest tests/test_ai.py -v
```

Expected: all `test_ai.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add bindings/python/aureum/ai.py bindings/python/tests/test_ai.py
git commit -m "feat(aureum): Anthropic client wrapper and prompt builders"
```

---

## Task 3: StrategyAuthor

**Files:**
- Create: `bindings/python/aureum/author.py`
- Test: `bindings/python/tests/test_author.py`

**Interfaces:**
- Consumes: `AnthropicClient`, `_extract_yaml`, `build_author_prompt`, `build_refinement_prompt`, `Strategy.from_yaml`, `Strategy.validate`, `BacktestRunner`, `MarketData.from_csv`.
- Produces: `StrategyAuthor.from_prompt(...) -> tuple[str, str]` returning `(yaml_text, rationale)`.

- [ ] **Step 1: Write the failing test for StrategyAuthor**

```python
"""Tests for the Aureum AI strategy author."""

from __future__ import annotations

import pytest

from aureum.author import StrategyAuthor
from aureum.strategy import Strategy


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0)


def _valid_strategy_yaml() -> str:
    return """apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: ai-momentum
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.0
  schedule:
    rebalance: 1M
    lookback: 252d
  ranking:
    by: momentum_12_1
    ascending: false
  weights:
    kind: equal
    top_n: 0.20
  execution:
    slippage: 0.0005
  risk:
    max_drawdown:
      value: 0.30
      hard: true
    max_leverage:
      value: 1.50
      hard: true
"""


def test_author_returns_valid_yaml():
    client = _FakeClient([f"```yaml\n{_valid_strategy_yaml()}\n```\nRationale: momentum tech strategy"])
    author = StrategyAuthor(client)
    yaml_text, rationale = author.from_prompt("tech momentum top 20%")

    strategy = Strategy.from_yaml(yaml_text)
    assert strategy.validate() == []
    assert strategy.metadata["name"] == "ai-momentum"
    assert "momentum" in rationale.lower()


def test_author_retries_on_validation_error():
    bad_yaml = _valid_strategy_yaml().replace("metadata:", "")
    good_response = f"```yaml\n{_valid_strategy_yaml()}\n```\nRationale: fixed missing metadata"
    client = _FakeClient([
        f"```yaml\n{bad_yaml}\n```\nRationale: bad draft",
        good_response,
    ])
    author = StrategyAuthor(client)
    yaml_text, _ = author.from_prompt("tech momentum")

    assert Strategy.from_yaml(yaml_text).validate() == []
    assert len(client.calls) == 2
    assert "metadata.name is required" in client.calls[1]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python
python -m pytest tests/test_author.py -v
```

Expected: `ImportError` or attribute errors.

- [ ] **Step 3: Implement `aureum/author.py`**

```python
"""AI-assisted Aureum strategy authoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai import (
    AnthropicClient,
    DEFAULT_MODEL,
    StrategyAIError,
    _extract_yaml,
    build_author_prompt,
    build_refinement_prompt,
)
from .backtest import BacktestRunner, MarketData
from .certificate import get_environment
from .strategy import Strategy


@dataclass
class AuthorResult:
    """Result of an authoring run."""

    yaml_text: str
    rationale: str
    certificate_path: Path | None = None


class StrategyAuthor:
    """Turn a natural-language prompt into a validated Aureum strategy YAML."""

    def __init__(
        self,
        client: AnthropicClient | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.client = client or AnthropicClient(model=model)

    def from_prompt(
        self,
        prompt: str,
        *,
        example_strategy: str | None = None,
        max_correction_attempts: int = 2,
    ) -> tuple[str, str]:
        """Generate validated YAML from a user prompt.

        Returns `(yaml_text, rationale)`.
        """
        current_prompt = build_author_prompt(prompt, example_strategy=example_strategy)
        last_yaml = ""

        for attempt in range(1 + max_correction_attempts):
            response = self.client.complete(current_prompt)
            try:
                last_yaml = _extract_yaml(response)
            except StrategyAIError as exc:
                if attempt == max_correction_attempts:
                    raise StrategyAIError(
                        f"LLM never returned a YAML block. Last response:\n{response}"
                    ) from exc
                current_prompt += (
                    "\n\nYour previous response did not contain a valid YAML block. "
                    "Return ONLY a fenced YAML block using ```yaml."
                )
                continue

            strategy = Strategy.from_yaml(last_yaml)
            errors = strategy.validate()
            if not errors:
                rationale = self._extract_rationale(response)
                return last_yaml, rationale

            if attempt == max_correction_attempts:
                raise StrategyAIError(
                    f"Could not produce valid YAML after {attempt} correction attempts. "
                    f"Last validation errors: {errors}"
                )

            current_prompt = build_refinement_prompt(prompt, last_yaml, errors)

        # Unreachable, but keeps mypy happy.
        return last_yaml, ""

    @staticmethod
    def _extract_rationale(response: str) -> str:
        for line in response.splitlines():
            if line.strip().lower().startswith("rationale:"):
                return line.split(":", 1)[1].strip()
        return ""

    def write_strategy(
        self,
        prompt: str,
        output_path: Path,
        *,
        example_strategy: str | None = None,
        dry_run_data: Path | None = None,
        max_correction_attempts: int = 2,
    ) -> AuthorResult:
        """Generate YAML, optionally dry-run it, and write it to disk."""
        yaml_text, rationale = self.from_prompt(
            prompt,
            example_strategy=example_strategy,
            max_correction_attempts=max_correction_attempts,
        )

        output_path = Path(output_path)
        output_path.write_text(yaml_text, encoding="utf-8")

        cert_path: Path | None = None
        if dry_run_data is not None:
            strategy = Strategy.from_yaml(yaml_text)
            data = MarketData.from_csv(dry_run_data)
            runner = BacktestRunner(
                strategy, data, data_source=str(dry_run_data)
            )
            env = get_environment(aureum_version="0.2.0", cwd=output_path.parent)
            cert = runner.build_certificate(
                strategy_path=output_path,
                data_path=dry_run_data,
                environment=env,
            )
            cert_path = output_path.with_suffix(".certificate.json")
            cert_path.write_text(cert.to_json(indent=2), encoding="utf-8")

        return AuthorResult(
            yaml_text=yaml_text,
            rationale=rationale,
            certificate_path=cert_path,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd bindings/python
python -m pytest tests/test_author.py -v
```

- [ ] **Step 5: Commit**

```bash
git add bindings/python/aureum/author.py bindings/python/tests/test_author.py
git commit -m "feat(aureum): AI strategy author with validation retry"
```

---

## Task 4: StrategyReflector

**Files:**
- Create: `bindings/python/aureum/reflector.py`
- Modify: `bindings/python/aureum/certificate.py` (small helper to inject draft lineage)
- Test: `bindings/python/tests/test_reflector.py`

**Interfaces:**
- Consumes: `AnthropicClient`, `_extract_yaml`, `build_reflector_prompt`, `Strategy.from_file`, `BacktestRunner`, `MarketData.from_csv`, `BacktestCertificate`.
- Produces: `ReflectionResult` dataclass with `success`, `attempts`, `drafts`, `accepted_draft`, `final_certificate`.

- [ ] **Step 1: Write the failing test for StrategyReflector**

```python
"""Tests for the Aureum AI strategy reflector."""

from __future__ import annotations

from pathlib import Path

import pytest

from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import get_environment
from aureum.reflector import ReflectionResult, StrategyReflector
from aureum.strategy import Strategy


EXAMPLE_STRATEGY = Path(__file__).parents[3] / "examples" / "strategies" / "buggy_slippage.yaml"
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0)


def _fixed_strategy_yaml() -> str:
    # Same as buggy_slippage but slippage is 0.0005 instead of 0.05
    return """apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: momentum-fixed
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.0
  schedule:
    rebalance: 1M
    lookback: 252d
  ranking:
    by: momentum_12_1
    ascending: false
  weights:
    kind: equal
    top_n: 0.20
  execution:
    slippage: 0.0005
  risk:
    max_drawdown:
      value: 0.30
      hard: true
    max_leverage:
      value: 1.50
      hard: true
    max_turnover_annual:
      value: 20.0
      hard: false
    max_concentration_single_name:
      value: 0.30
      hard: true
"""


def test_reflector_fixes_buggy_slippage(tmp_path: Path):
    client = _FakeClient([f"```yaml\n{_fixed_strategy_yaml()}\n```\nFixed slippage from 0.05 to 0.0005."])
    reflector = StrategyReflector(client)
    result = reflector.reflect(
        EXAMPLE_STRATEGY,
        EXAMPLE_DATA,
        output_path=tmp_path / "fixed.yaml",
        max_attempts=3,
    )

    assert isinstance(result, ReflectionResult)
    assert result.success is True
    assert result.attempts == 1
    assert result.accepted_draft is not None
    assert result.accepted_draft.name == "fixed.yaml"
    assert result.final_certificate is not None
    hard_passed = all(
        c.get("passed", False) for c in result.final_certificate.to_dict()["risk_constraints"] if c.get("hard")
    )
    assert hard_passed


def test_reflector_keeps_drafts_when_fix_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    bad_yaml = _fixed_strategy_yaml().replace("slippage: 0.0005", "slippage: 0.05")
    client = _FakeClient([
        f"```yaml\n{bad_yaml}\n```\nFailed fix.",
        f"```yaml\n{bad_yaml}\n```\nFailed fix again.",
    ])
    reflector = StrategyReflector(client)
    result = reflector.reflect(
        EXAMPLE_STRATEGY,
        EXAMPLE_DATA,
        output_path=tmp_path / "fixed.yaml",
        max_attempts=2,
    )

    assert result.success is False
    assert result.attempts == 2
    assert (tmp_path / "fixed.001.yaml").exists()
    assert (tmp_path / "fixed.002.yaml").exists()
    assert not (tmp_path / "fixed.yaml").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd bindings/python
python -m pytest tests/test_reflector.py -v
```

Expected: import/attribute failures.

- [ ] **Step 3: Add a small helper to `aureum/certificate.py`**

Add this method to `BacktestCertificate`:

```python
    def with_draft_lineage(self, draft_lineage: dict[str, Any]) -> "BacktestCertificate":
        """Return a new certificate with draft lineage injected into execution_trace."""
        new_trace = dict(self.execution_trace)
        new_trace["draft_lineage"] = draft_lineage
        return dataclasses.replace(self, execution_trace=new_trace)
```

Also ensure `dataclasses` is imported at the top of `certificate.py` (add `import dataclasses`).

- [ ] **Step 4: Implement `aureum/reflector.py`**

```python
"""AI-driven reflection loop that fixes failing Aureum strategies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai import (
    AnthropicClient,
    DEFAULT_MODEL,
    StrategyAIError,
    _extract_yaml,
    build_reflector_prompt,
)
from .backtest import BacktestRunner, MarketData
from .certificate import BacktestCertificate, get_environment
from .strategy import Strategy


@dataclass
class ReflectionResult:
    """Result of a reflection run."""

    success: bool
    attempts: int
    drafts: list[Path]
    accepted_draft: Path | None
    final_certificate: BacktestCertificate | None


class StrategyReflector:
    """Diagnose a failing strategy from a certificate and propose YAML fixes."""

    def __init__(
        self,
        client: AnthropicClient | None = None,
        *,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.client = client or AnthropicClient(model=model)

    def _load_or_build_certificate(
        self,
        strategy: Strategy,
        data_path: Path,
        certificate_path: Path | None,
    ) -> BacktestCertificate:
        if certificate_path is not None:
            raw = Path(certificate_path).read_text(encoding="utf-8")
            data = json.loads(raw)
            return BacktestCertificate(**data)

        data_obj = MarketData.from_csv(data_path)
        runner = BacktestRunner(
            strategy, data_obj, data_source=str(data_path)
        )
        env = get_environment(aureum_version="0.2.0", cwd=data_path.parent)
        return runner.build_certificate(
            strategy_path=Path("strategy.yaml"),
            data_path=data_path,
            environment=env,
        )

    @staticmethod
    def _has_hard_failures(certificate: BacktestCertificate) -> bool:
        for item in certificate.risk_constraints:
            if not item.get("passed", True) and item.get("hard", False):
                return True
        return False

    @staticmethod
    def _next_draft_path(output_path: Path, attempt: int) -> Path:
        return output_path.with_suffix(f".{attempt:03d}{output_path.suffix}")

    def reflect(
        self,
        strategy_path: str | Path,
        data_path: str | Path,
        *,
        certificate_path: str | Path | None = None,
        max_attempts: int = 3,
        output_path: str | Path | None = None,
    ) -> ReflectionResult:
        """Run the reflection loop.

        Saves numbered drafts for every failed attempt. Overwrites the output
        file only when all hard constraints pass.
        """
        strategy_path = Path(strategy_path)
        data_path = Path(data_path)
        output_path = Path(output_path) if output_path else strategy_path

        strategy = Strategy.from_file(strategy_path)
        certificate = self._load_or_build_certificate(
            strategy, data_path, Path(certificate_path) if certificate_path else None
        )

        drafts: list[Path] = []
        current_yaml = strategy_path.read_text(encoding="utf-8")

        for attempt in range(1, max_attempts + 1):
            if not self._has_hard_failures(certificate):
                # Already passes; nothing to fix.
                return ReflectionResult(
                    success=True,
                    attempts=0,
                    drafts=[],
                    accepted_draft=None,
                    final_certificate=certificate,
                )

            prompt = build_reflector_prompt(current_yaml, certificate.to_dict())
            response = self.client.complete(prompt)
            new_yaml = _extract_yaml(response)
            new_strategy = Strategy.from_yaml(new_yaml)
            validation_errors = new_strategy.validate()

            if validation_errors:
                # Invalid YAML: save as a draft anyway for forensics, but do not run.
                draft_path = self._next_draft_path(output_path, attempt)
                draft_path.write_text(new_yaml, encoding="utf-8")
                drafts.append(draft_path)
                current_yaml = new_yaml
                continue

            # Run backtest on the candidate.
            data_obj = MarketData.from_csv(data_path)
            runner = BacktestRunner(
                new_strategy, data_obj, data_source=str(data_path)
            )
            env = get_environment(aureum_version="0.2.0", cwd=data_path.parent)
            certificate = runner.build_certificate(
                strategy_path=strategy_path,
                data_path=data_path,
                environment=env,
            )

            if not self._has_hard_failures(certificate):
                output_path.write_text(new_yaml, encoding="utf-8")
                certificate = certificate.with_draft_lineage(
                    {
                        "attempts": attempt,
                        "drafts": [str(d) for d in drafts],
                        "accepted": str(output_path),
                    }
                )
                return ReflectionResult(
                    success=True,
                    attempts=attempt,
                    drafts=drafts,
                    accepted_draft=output_path,
                    final_certificate=certificate,
                )

            draft_path = self._next_draft_path(output_path, attempt)
            draft_path.write_text(new_yaml, encoding="utf-8")
            drafts.append(draft_path)
            current_yaml = new_yaml

        return ReflectionResult(
            success=False,
            attempts=max_attempts,
            drafts=drafts,
            accepted_draft=None,
            final_certificate=certificate,
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd bindings/python
python -m pytest tests/test_reflector.py -v
```

- [ ] **Step 6: Commit**

```bash
git add bindings/python/aureum/reflector.py bindings/python/aureum/certificate.py bindings/python/tests/test_reflector.py
git commit -m "feat(aureum): AI reflection loop with numbered draft backups"
```

---

## Task 5: CLI Commands

**Files:**
- Modify: `bindings/python/aureum/cli.py`
- Test: `bindings/python/tests/test_author.py`, `bindings/python/tests/test_reflector.py`

**Interfaces:**
- Consumes: `StrategyAuthor.write_strategy`, `StrategyReflector.reflect`.
- Produces: `aureum author` and `aureum reflect` CLI subcommands.

- [ ] **Step 1: Write failing CLI tests**

Append to `tests/test_author.py`:

```python
from click.testing import CliRunner
from aureum.cli import cli


def test_author_cli_writes_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    out = tmp_path / "ai.yaml"
    runner = CliRunner()

    # Patch AnthropicClient.complete inside the CLI path.
    import aureum.author as author_module
    original = author_module.AnthropicClient

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def complete(self, prompt, *, max_tokens=4096):
            return f"```yaml\n{_valid_strategy_yaml()}\n```\nRationale: test"

    try:
        author_module.AnthropicClient = FakeClient  # type: ignore[misc]
        result = runner.invoke(
            cli,
            [
                "author",
                "tech momentum strategy",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
    finally:
        author_module.AnthropicClient = original  # type: ignore[misc]
```

Append to `tests/test_reflector.py`:

```python
from click.testing import CliRunner
from aureum.cli import cli


def test_reflect_cli_with_mocked_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    import aureum.reflector as reflector_module
    original = reflector_module.AnthropicClient

    class FakeClient:
        def __init__(self, **kwargs):
            pass
        def complete(self, prompt, *, max_tokens=4096):
            return f"```yaml\n{_fixed_strategy_yaml()}\n```\nFixed."

    out = tmp_path / "fixed.yaml"
    runner = CliRunner()
    try:
        reflector_module.AnthropicClient = FakeClient  # type: ignore[misc]
        result = runner.invoke(
            cli,
            [
                "reflect",
                str(EXAMPLE_STRATEGY),
                "--data",
                str(EXAMPLE_DATA),
                "--output",
                str(out),
                "--max-attempts",
                "1",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
    finally:
        reflector_module.AnthropicClient = original  # type: ignore[misc]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd bindings/python
python -m pytest tests/test_author.py tests/test_reflector.py -v
```

Expected: CLI subcommands do not exist yet.

- [ ] **Step 3: Modify `aureum/cli.py`**

Add imports at the top:

```python
from .adapter import AlpacaAdapter
from .author import StrategyAuthor
from .backtest import BacktestRunner, MarketData
from .certificate import get_environment
from .prover import Lean4Generator, SmtLibGenerator, extract_claims
from .reflector import StrategyReflector
from .strategy import Strategy
```

Add the `author` command after the `validate` command:

```python
@cli.command()
@click.argument("prompt")
@click.option(
    "--output",
    required=True,
    type=click.Path(path_type=Path),
    help="Output strategy YAML path",
)
@click.option(
    "--data",
    type=click.Path(path_type=Path),
    help="Data CSV for optional dry-run backtest",
)
@click.option("--dry-run", is_flag=True, help="Run a dry-run backtest and emit certificate")
@click.option("--model", default="claude-sonnet-5", help="Anthropic model name")
@click.option(
    "--max-correction-attempts",
    default=2,
    show_default=True,
    help="Max retries if the LLM emits invalid YAML",
)
def author(
    prompt: str,
    output: Path,
    data: Path | None,
    dry_run: bool,
    model: str,
    max_correction_attempts: int,
) -> None:
    """Generate an Aureum strategy YAML from a natural-language prompt."""
    author_ = StrategyAuthor(model=model)
    result = author_.write_strategy(
        prompt,
        output,
        dry_run_data=data if dry_run else None,
        max_correction_attempts=max_correction_attempts,
    )
    click.echo(f"Strategy written to {output.resolve()}")
    if result.rationale:
        click.echo(f"Rationale: {result.rationale}")
    if result.certificate_path:
        click.echo(f"Dry-run certificate: {result.certificate_path.resolve()}")
```

Add the `reflect` command after `author`:

```python
@cli.command()
@click.argument("strategy", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--data",
    required=True,
    type=click.Path(path_type=Path),
    help="Data CSV for backtests",
)
@click.option(
    "--certificate",
    type=click.Path(path_type=Path),
    help="Existing certificate JSON (if omitted, one is generated)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output strategy path (defaults to overwriting input)",
)
@click.option(
    "--max-attempts",
    default=3,
    show_default=True,
    help="Maximum reflection iterations",
)
@click.option("--model", default="claude-sonnet-5", help="Anthropic model name")
def reflect(
    strategy: Path,
    data: Path,
    certificate: Path | None,
    output: Path | None,
    max_attempts: int,
    model: str,
) -> None:
    """Fix a failing strategy using an LLM reflection loop."""
    reflector = StrategyReflector(model=model)
    result = reflector.reflect(
        strategy,
        data,
        certificate_path=certificate,
        output_path=output,
        max_attempts=max_attempts,
    )
    if result.success:
        click.echo(
            f"Reflection succeeded after {result.attempts} attempt(s). "
            f"Accepted strategy: {result.accepted_draft}"
        )
    else:
        click.echo(
            f"Reflection failed after {result.attempts} attempt(s). "
            f"Drafts preserved: {[str(d) for d in result.drafts]}"
        )
        raise click.Abort()
```

- [ ] **Step 4: Run the full Python test suite**

```bash
cd bindings/python
python -m pytest -q
```

- [ ] **Step 5: Run lint and type checks**

```bash
cd bindings/python
python -m ruff check aureum tests
python -m mypy aureum
```

- [ ] **Step 6: Commit**

```bash
git add bindings/python/aureum/cli.py bindings/python/tests/test_author.py bindings/python/tests/test_reflector.py
git commit -m "feat(aureum): add author and reflect CLI subcommands"
```

---

## Task 6: Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/self-proving-backtest.md`

**Interfaces:**
- No code interfaces; documentation only.

- [ ] **Step 1: Update `README.md` quick-start**

Add after the existing `aureum backtest` / `aureum snapshot` examples:

```markdown
# Generate a strategy from a plain-English prompt
export ANTHROPIC_API_KEY=...
aureum author "Long-only tech momentum, top 20% by 12-1 month momentum, equal weights, max drawdown 30%" \
  --output examples/strategies/ai_momentum.yaml

# Fix a failing strategy with the reflection loop
aureum reflect examples/strategies/buggy_slippage.yaml \
  --data examples/data/synthetic_prices.csv \
  --max-attempts 3
```

- [ ] **Step 2: Update `docs/self-proving-backtest.md`**

Append a new Phase 3 section before the existing "Next steps":

```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/self-proving-backtest.md
git commit -m "docs(aureum): document Phase 3 author and reflect commands"
```

---

## Task 7: Final Quality Assurance

**Files:**
- All modified files.

- [ ] **Step 1: Run full test suite**

```bash
cd bindings/python
python -m pytest -q
```

Expected: 40+ passed, 1 skipped (z3 optional).

- [ ] **Step 2: Run lint and type checks**

```bash
cd bindings/python
python -m ruff check aureum tests
python -m mypy aureum
```

Expected: clean.

- [ ] **Step 3: Manual smoke test (requires ANTHROPIC_API_KEY)**

```bash
export ANTHROPIC_API_KEY=...
cd bindings/python
python -m aureum.cli author "Momentum strategy for technology stocks, top 20% by 12-1 month return, equal weights, max drawdown 30%" \
  --output /tmp/ai_strategy.yaml \
  --data ../../examples/data/synthetic_prices.csv \
  --dry-run
```

Verify `/tmp/ai_strategy.yaml` is valid YAML and `/tmp/ai_strategy.certificate.json` exists.

- [ ] **Step 4: Commit any fixes**

If ruff/mypy/pytest found issues, fix them and commit:

```bash
git add -A
git commit -m "chore(aureum): Phase 3 QA fixes"
```

- [ ] **Step 5: Push to GitHub**

```bash
cd /c/Users/point/projects/aureum
git push origin main
```

---

## Self-Review Checklist

- **Spec coverage:**
  - AI author prompt → YAML: Task 3.
  - Validation retry: Task 3.
  - Reflection loop with drafts: Task 4.
  - CLI commands: Task 5.
  - Safety (API key from env, no overwrites unless passing): Tasks 2, 4, 5.
  - Documentation: Task 6.
  - Startup positioning notes are in the spec; no extra code needed beyond open-source foundation.

- **Placeholder scan:**
  - No "TBD", "TODO", or vague steps.
  - Every code block contains concrete implementation content.
  - Every test shows exact assertions.

- **Type consistency:**
  - `AnthropicClient.complete(prompt: str, *, max_tokens: int = 4096) -> str` is consistent across `ai.py`, `author.py`, `reflector.py`, and tests.
  - `StrategyReflector.reflect` signature matches CLI usage.
  - `StrategyAuthor.write_strategy` returns `AuthorResult` used by CLI.

- **No uncovered spec requirements.**

---

*Plan complete. Ready for execution.*

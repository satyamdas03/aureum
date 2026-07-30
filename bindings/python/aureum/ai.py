"""Thin Anthropic client wrapper and prompt builders for Aureum AI features."""

from __future__ import annotations

import os
import re
from typing import Any

DEFAULT_MODEL = "claude-sonnet-5"


class StrategyAIError(ValueError):
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
        text_parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text" and hasattr(block, "text"):
                text_parts.append(block.text)
        if not text_parts:
            raise StrategyAIError(
                "No text block found in Anthropic response: "
                f"{[getattr(b, 'type', type(b).__name__) for b in response.content]}"
            )
        return "\n".join(text_parts)


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


_DEFAULT_EXAMPLE_STRATEGY = """apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: tech-momentum-sector-neutral
  description: Long the top 20% of S&P 500 tech stocks by 12-1 month momentum.
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.00
      min_adv20: 1000000
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
      value: 20.00
      hard: false
    max_concentration_single_name:
      value: 0.30
      hard: true
"""


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
- spec.ranking (required): by, ascending. The ONLY valid value for "by" is "momentum_12_1".
- spec.weights (required): kind (only "equal"), top_n (fraction 0.0-1.0)
- spec.execution (required): slippage (e.g. 0.0005 for 5 bps)
- spec.risk: max_drawdown, max_leverage, max_turnover_annual, max_concentration_single_name
  Each constraint has value and hard (boolean). Hard failures block the strategy.

Output rules:
- Return ONLY a fenced YAML block using ```yaml.
- After the YAML block, provide a single-line rationale starting with "Rationale:".
- Do not invent unsupported fields or custom signal names; ranking.by must be exactly "momentum_12_1".
- Slippage must be a small decimal (e.g. 0.0005), never 0.05.

Example strategy:
```yaml
{_DEFAULT_EXAMPLE_STRATEGY}
```
"""
    if example_strategy:
        base += f"\n\nAlternate example strategy:\n```yaml\n{example_strategy}\n```"
    base += f"\nUser request:\n{user_prompt}\n\nGenerate the YAML:"
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

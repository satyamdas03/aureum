"""Tests for the Aureum AI strategy reflector."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from aureum.certificate import hash_file
from aureum.cli import cli
from aureum.reflector import ReflectionResult, StrategyReflector

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


def test_reflector_accepted_certificate_lineage_matches_output_file(tmp_path: Path):
    client = _FakeClient([f"```yaml\n{_fixed_strategy_yaml()}\n```\nFixed slippage from 0.05 to 0.0005."])
    reflector = StrategyReflector(client)
    output_path = tmp_path / "fixed.yaml"
    result = reflector.reflect(
        EXAMPLE_STRATEGY,
        EXAMPLE_DATA,
        output_path=output_path,
        max_attempts=1,
    )

    assert result.success is True
    certificate = result.final_certificate
    assert certificate is not None
    inputs = certificate.to_dict()["inputs"]
    assert Path(inputs["strategy"]["path"]) == output_path
    assert inputs["strategy"]["sha256"] == hash_file(output_path)
    assert inputs["strategy"]["sha256"] != hash_file(EXAMPLE_STRATEGY)


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

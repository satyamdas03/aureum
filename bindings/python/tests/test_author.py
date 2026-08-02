"""Tests for the Aureum AI strategy author."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from aureum.author import StrategyAuthor
from aureum.cli import cli
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
    bad_yaml = _valid_strategy_yaml().replace("name: ai-momentum", "name:")
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
        author_module.AnthropicClient = FakeClient  # type: ignore[assignment]
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

"""Tests for the Aureum neuro-symbolic alpha DSL (Edge 4)."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from click.testing import CliRunner

from aureum.alpha import (
    AlphaGrammar,
    AlphaMiner,
    AlphaSpec,
    SafetyReport,
    safety_check,
)
from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import AlphaLineage, BacktestCertificate
from aureum.cli import cli
from aureum.strategy import Strategy


EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"
ALPHA_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "alpha_momentum_reversal.yaml"
)


# ---------- parsing -----------------------------------------------------


def test_parse_numeric_literal():
    ast, err = AlphaGrammar.parse("42.0")
    assert err is None
    assert ast is not None
    assert ast.is_literal()
    assert ast.value == 42.0


def test_parse_variable():
    ast, err = AlphaGrammar.parse("close")
    assert err is None
    assert ast is not None
    assert ast.is_variable()
    assert ast.name == "close"


def test_parse_simple_function():
    ast, err = AlphaGrammar.parse("sma(close, 20)")
    assert err is None
    assert ast is not None
    assert ast.name == "sma"
    assert len(ast.args) == 2
    assert ast.args[0].name == "close"
    assert ast.args[1].value == 20


def test_parse_complex_formula():
    formula = "if_else(gt(dollar_volume(close, volume, 20), 5_000_000.0), zscore(returns(close, 5), 63), 0.0)"
    ast, err = AlphaGrammar.parse(formula)
    assert err is None
    assert ast is not None
    assert ast.name == "if_else"


def test_parse_unknown_function_is_rejected_by_safety():
    ast, err = AlphaGrammar.parse("future(close, 5)")
    assert err is None
    report = safety_check(ast)
    assert not report.safe
    assert any("unknown" in f.lower() for f in report.failures)


def test_parse_rejects_unbalanced_parens():
    _, err = AlphaGrammar.parse("sma(close, 20")
    assert err is not None


# ---------- evaluation --------------------------------------------------


def close_series() -> list[float]:
    return [float(i) for i in range(1, 101)]


def volume_series() -> list[int]:
    return [1_000_000] * 100


def test_evaluate_close_returns_full_array():
    closes = close_series()
    ast, _ = AlphaGrammar.parse("close")
    result = ast.evaluate(closes, volume_series())
    assert isinstance(result, np.ndarray)
    assert len(result) == len(closes)


def test_evaluate_sma():
    closes = close_series()
    ast, _ = AlphaGrammar.parse("sma(close, 20)")
    result = ast.evaluate(closes, volume_series())
    assert len(result) == len(closes)
    assert math.isnan(result[18])
    assert not math.isnan(result[19])


def test_evaluate_returns():
    closes = close_series()
    ast, _ = AlphaGrammar.parse("returns(close, 5)")
    result = ast.evaluate(closes, volume_series())
    assert math.isnan(result[4])
    assert result[5] == closes[5] / closes[0] - 1.0


def test_evaluate_lag():
    closes = close_series()
    ast, _ = AlphaGrammar.parse("lag(close, 3)")
    result = ast.evaluate(closes, volume_series())
    assert math.isnan(result[2])
    assert result[3] == closes[0]


def test_evaluate_if_else_with_comparison():
    closes = close_series()
    volumes = volume_series()
    ast, _ = AlphaGrammar.parse("if_else(gt(close, 50.0), 1.0, sub(0, 1.0))")
    result = ast.evaluate(closes, volumes)
    assert result[49] == -1.0
    assert result[50] == 1.0


def test_evaluate_dollar_volume():
    closes = close_series()
    volumes = [i * 1000 for i in range(1, 101)]
    ast, _ = AlphaGrammar.parse("dollar_volume(close, volume, 5)")
    result = ast.evaluate(closes, volumes)
    assert len(result) == len(closes)
    assert math.isnan(result[3])
    assert not math.isnan(result[4])


def test_evaluate_volume_primitive():
    volumes = volume_series()
    ast, _ = AlphaGrammar.parse("volume")
    result = ast.evaluate(close_series(), volumes)
    assert result[-1] == volumes[-1]


# ---------- safety checker ---------------------------------------------


def test_safety_check_accepts_valid_formula():
    ast, _ = AlphaGrammar.parse("sma(close, 20)")
    report = safety_check(ast)
    assert isinstance(report, SafetyReport)
    assert report.safe
    assert not report.failures


def test_safety_check_rejects_unknown_primitive():
    ast, _ = AlphaGrammar.parse("unknown(close)")
    report = safety_check(ast)
    assert not report.safe
    assert any("unknown" in f.lower() for f in report.failures)


def test_safety_check_rejects_negative_lag():
    # lag offsets are parsed as a positive literal; negative values are a parse error.
    _, err = AlphaGrammar.parse("lag(close, -1)")
    assert err is not None


def test_safety_check_rejects_non_literal_window():
    ast, _ = AlphaGrammar.parse("sma(close, add(1, 2))")
    report = safety_check(ast)
    assert not report.safe
    assert any("window must be a constant literal" in f for f in report.failures)


def test_safety_check_rejects_structural_constant():
    ast, _ = AlphaGrammar.parse("sub(close, 100.0)")
    report = safety_check(ast)
    assert not report.safe
    assert any("structural constant" in f for f in report.failures)


def test_safety_check_allows_threshold_literal():
    ast, _ = AlphaGrammar.parse("gt(dollar_volume(close, volume, 20), 5_000_000.0)")
    report = safety_check(ast)
    assert report.safe


# ---------- alpha miner -------------------------------------------------


class _FakeAnthropicClient:
    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        return "```formula\nzscore(returns(close, 5), 63)\n```"


class _BadAnthropicClient:
    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        return "sub(close, 100.0)"


class _UnparsableAnthropicClient:
    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.model = model

    def complete(self, prompt: str, *, max_tokens: int = 4096) -> str:
        return "not a formula"


def test_alpha_miner_generates_safe_formula(monkeypatch):
    monkeypatch.setattr("aureum.alpha.AnthropicClient", _FakeAnthropicClient)
    miner = AlphaMiner()
    result = miner.generate(prompt="short term momentum z-score")
    assert result.formula == "zscore(returns(close, 5), 63)"
    assert "Generated" in result.rationale


def test_alpha_miner_rejects_unsafe_formula(monkeypatch):
    monkeypatch.setattr("aureum.alpha.AnthropicClient", _BadAnthropicClient)
    miner = AlphaMiner()
    result = miner.generate(prompt="price minus a constant")
    assert result.formula == ""
    assert "safety" in result.rationale.lower()


def test_alpha_miner_rejects_unparsable_response(monkeypatch):
    monkeypatch.setattr("aureum.alpha.AnthropicClient", _UnparsableAnthropicClient)
    miner = AlphaMiner()
    result = miner.generate(prompt="nonsense")
    assert result.formula == ""


# ---------- strategy integration ----------------------------------------


def test_strategy_validates_neuro_symbolic_signal():
    strategy = Strategy.from_file(ALPHA_STRATEGY)
    errors = strategy.validate()
    assert not errors, errors


def test_strategy_rejects_unsafe_formula():
    data = {
        "apiVersion": "aureum.io/v1alpha1",
        "kind": "Strategy",
        "metadata": {"name": "bad-alpha"},
        "spec": {
            "universe": {"source": "sp500"},
            "schedule": {"rebalance": "1M", "lookback": "252d"},
            "signals": {
                "alpha": {
                    "type": "neuro_symbolic",
                    "formula": "sub(close, 100.0)",
                    "generation": {"llm_model": "claude-sonnet-5", "safety_checks_passed": True},
                }
            },
            "ranking": {"by": "alpha", "ascending": False},
            "weights": {"kind": "equal", "top_n": 0.2},
            "execution": {"open": "market_on_open", "slippage": 0.0005},
        },
    }
    strategy = Strategy.from_dict(data)
    errors = strategy.validate()
    assert any("structural constant" in e for e in errors)


def test_strategy_rejects_undefined_ranking_signal():
    data = {
        "apiVersion": "aureum.io/v1alpha1",
        "kind": "Strategy",
        "metadata": {"name": "missing-signal"},
        "spec": {
            "universe": {"source": "sp500"},
            "schedule": {"rebalance": "1M", "lookback": "252d"},
            "ranking": {"by": "not_defined", "ascending": False},
            "weights": {"kind": "equal", "top_n": 0.2},
            "execution": {"open": "market_on_open", "slippage": 0.0005},
        },
    }
    strategy = Strategy.from_dict(data)
    errors = strategy.validate()
    assert any("not defined" in e for e in errors)


# ---------- backtest integration ---------------------------------------


def test_backtest_runs_with_alpha_signal():
    data = MarketData.from_csv(EXAMPLE_DATA)
    strategy = Strategy.from_file(ALPHA_STRATEGY)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    result = runner.run()
    assert result.trades > 0
    assert len(result.rebalance_log) > 0


def test_alpha_signal_registry_includes_formula():
    data = MarketData.from_csv(EXAMPLE_DATA)
    strategy = Strategy.from_file(ALPHA_STRATEGY)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    registry = runner._build_signal_registry()
    assert "alpha" in registry
    closes = data.closes_up_to(data.dates[-1], data.symbols[0])
    volumes = data.volumes_up_to(data.dates[-1], data.symbols[0])
    score = registry["alpha"](closes, volumes)
    assert isinstance(score, float)


def test_certificate_includes_alpha_lineage():
    from aureum.certificate import get_environment
    from aureum import __version__

    data = MarketData.from_csv(EXAMPLE_DATA)
    strategy = Strategy.from_file(ALPHA_STRATEGY)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = get_environment(aureum_version=__version__, cwd=Path(__file__).parent)
    cert = runner.build_certificate(strategy_path=ALPHA_STRATEGY, data_path=EXAMPLE_DATA, environment=env)
    assert isinstance(cert, BacktestCertificate)
    assert cert.alpha_lineage is not None
    assert len(cert.alpha_lineage.alpha_signals) == 1
    assert cert.alpha_lineage.alpha_signals[0]["name"] == "alpha"
    assert "formula" in cert.alpha_lineage.alpha_signals[0]


# ---------- CLI ---------------------------------------------------------


def test_cli_alpha_validate_only_passes():
    runner = CliRunner()
    result = runner.invoke(cli, ["alpha", "sma(close, 20)", "--validate-only"])
    assert result.exit_code == 0, result.output
    assert "passed all safety checks" in result.output


def test_cli_alpha_validate_only_fails_on_unsafe():
    runner = CliRunner()
    result = runner.invoke(cli, ["alpha", "sub(close, 100.0)", "--validate-only"])
    assert result.exit_code != 0
    assert "Safety check failed" in result.output


def test_cli_alpha_generate_writes_yaml(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("aureum.alpha.AnthropicClient", _FakeAnthropicClient)
    out = tmp_path / "alpha.yaml"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "alpha",
            "short term momentum z-score",
            "--output",
            str(out),
            "--name",
            "test-alpha",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    strategy = Strategy.from_file(out)
    assert strategy.metadata["name"] == "test-alpha"
    assert strategy.spec["signals"]["alpha"]["type"] == "neuro_symbolic"


# ---------- spec utilities --------------------------------------------


def test_alpha_spec_from_dict():
    spec = AlphaSpec.from_dict(
        {"name": "alpha", "formula": "sma(close, 20)", "generation": {"llm_model": "claude-sonnet-5"}}
    )
    assert spec.name == "alpha"
    assert spec.formula == "sma(close, 20)"
    assert spec.generation["llm_model"] == "claude-sonnet-5"


def test_alpha_lineage_round_trip():
    lineage = AlphaLineage(
        alpha_signals=[{"name": "alpha", "formula": "sma(close, 20)", "generation": {}}]
    )
    data = lineage.to_dict()
    restored = AlphaLineage.from_dict(data)
    assert restored.alpha_signals[0]["name"] == "alpha"

"""Tests for Edge 6 — differentiable certifiable execution."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from aureum import __version__, get_environment
from aureum.backtest import BacktestRunner, MarketData
from aureum.diffopt import ArchitectureSpec, DifferentiableSharpeOptimizer
from aureum.strategy import Strategy

EXAMPLE_DIFFOPT_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "diffopt_sharpe.yaml"
)
EXAMPLE_ARCHITECTURE = (
    Path(__file__).parents[3] / "examples" / "models" / "sharpe_mlp.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def test_architecture_spec_from_yaml():
    spec = ArchitectureSpec.from_yaml(EXAMPLE_ARCHITECTURE)
    assert spec.input_features == [
        "mean_return_252d",
        "volatility_252d",
        "momentum_12_1",
    ]
    assert spec.hidden_units == [64, 32]
    assert spec.activation == "softplus"
    assert spec.output_temperature == 1.0


def test_architecture_spec_rejects_unknown_activation(tmp_path: Path):
    arch_path = tmp_path / "bad_arch.yaml"
    arch_path.write_text(
        yaml.safe_dump(
            {
                "input_features": ["mean_return_252d"],
                "hidden_units": [16],
                "activation": "swish",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported activation"):
        ArchitectureSpec.from_yaml(arch_path)


def test_diffopt_strategy_is_valid():
    strategy = Strategy.from_file(EXAMPLE_DIFFOPT_STRATEGY)
    errors = strategy.validate()
    assert errors == []


def test_diffopt_strategy_requires_architecture_file():
    strategy = Strategy.from_yaml(
        """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: missing-arch
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
  schedule:
    rebalance: 1M
    lookback: 252d
  portfolio:
    objective: differentiable_sharpe
    model: {}
    training:
      learning_rate: 0.001
      epochs: 10
      train_end: "2022-12-31"
      val_end: "2023-12-31"
  execution:
    slippage: 0.0005
"""
    )
    errors = strategy.validate()
    assert any(
        "architecture_file" in err and "differentiable_sharpe" in err
        for err in errors
    )


def test_diffopt_train_val_order():
    strategy = Strategy.from_yaml(
        """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: bad-order
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
  schedule:
    rebalance: 1M
    lookback: 252d
  portfolio:
    objective: differentiable_sharpe
    model:
      architecture_file: examples/models/sharpe_mlp.yaml
    training:
      learning_rate: 0.001
      epochs: 10
      train_end: "2023-12-31"
      val_end: "2022-12-31"
  execution:
    slippage: 0.0005
"""
    )
    errors = strategy.validate()
    assert any("train_end must be strictly before val_end" in err for err in errors)


def test_diffopt_train_produces_long_only_weights(tmp_path: Path):
    strategy = Strategy.from_file(EXAMPLE_DIFFOPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    opt = DifferentiableSharpeOptimizer.from_strategy(
        strategy, data, strategy_path=EXAMPLE_DIFFOPT_STRATEGY
    )
    result = opt.train_and_backtest(weights_dir=tmp_path)
    assert result.weights_hash.startswith("sha256:")
    assert result.backtest_result is not None
    assert result.backtest_result.rebalance_log
    weights = result.backtest_result.rebalance_log[-1]["portfolio"]["weights"]
    values = np.array(list(weights.values()))
    assert np.all(values >= -1e-6)
    assert abs(values.sum() - 1.0) < 1e-5


def test_diffopt_reproducible_weights(tmp_path: Path):
    strategy = Strategy.from_file(EXAMPLE_DIFFOPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)

    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    dir1.mkdir()
    dir2.mkdir()

    opt1 = DifferentiableSharpeOptimizer.from_strategy(
        strategy, data, strategy_path=EXAMPLE_DIFFOPT_STRATEGY
    )
    result1 = opt1.train_and_backtest(weights_dir=dir1)

    opt2 = DifferentiableSharpeOptimizer.from_strategy(
        strategy, data, strategy_path=EXAMPLE_DIFFOPT_STRATEGY
    )
    result2 = opt2.train_and_backtest(weights_dir=dir2)

    assert result1.weights_hash == result2.weights_hash


def test_diffopt_certificate_includes_model_and_split_hashes():
    strategy = Strategy.from_file(EXAMPLE_DIFFOPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy,
        data,
        data_source=str(EXAMPLE_DATA),
        strategy_path=EXAMPLE_DIFFOPT_STRATEGY,
    )
    env = get_environment(__version__, cwd=EXAMPLE_DIFFOPT_STRATEGY.parent)
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_DIFFOPT_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
    )
    assert cert.portfolio_construction is not None
    pc = cert.portfolio_construction
    assert pc.objective == "differentiable_sharpe"
    assert pc.model_architecture_hash.startswith("sha256:")
    assert pc.weights_hash.startswith("sha256:")
    assert set(pc.train_val_test_split_hashes.keys()) == {"train", "val", "test"}
    assert all(
        h.startswith("sha256:") for h in pc.train_val_test_split_hashes.values()
    )
    assert pc.optimization_inputs_hash


def test_diffopt_certificate_uses_relaxed_tolerance():
    strategy = Strategy.from_file(EXAMPLE_DIFFOPT_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(
        strategy,
        data,
        data_source=str(EXAMPLE_DATA),
        strategy_path=EXAMPLE_DIFFOPT_STRATEGY,
    )
    env = get_environment(__version__, cwd=EXAMPLE_DIFFOPT_STRATEGY.parent)
    cert = runner.build_certificate(
        strategy_path=EXAMPLE_DIFFOPT_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
    )
    assert cert.determinism.tolerance == "1e-5 relative + 1e-8 absolute"

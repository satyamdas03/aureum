"""Tests for Edge 2 — Causal MPT in Aureum."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aureum import __version__
from aureum.backtest import BacktestRunner, MarketData
from aureum.causal import (
    CausalGraph,
    CausalSeparationSpec,
    build_driver_returns,
    condition_covariance,
    estimate_exposures,
)
from aureum.certificate import Environment
from aureum.mpt import OptimizationInputs, optimize_minimum_variance
from aureum.strategy import Strategy


def test_conditioning_removes_synthetic_common_driver():
    """A declared common driver should be removed from residual covariance."""
    rng = np.random.default_rng(42)
    t = 252
    n = 4
    factor = rng.normal(0.0, 0.05, size=t)
    noise = rng.normal(0.0, 0.005, size=(t, n))
    returns = 0.5 * factor[:, None] + noise

    symbols = ["A", "B", "C", "D"]
    graph = CausalGraph(
        drivers=[{"name": "common_factor"}],
        edges=[{"from": "common_factor", "to": ["A", "B", "C", "D"]}],
    )
    assert graph.validate(symbols) == []

    separation = CausalSeparationSpec(mode="condition_on", drivers=["common_factor"])
    cov, meta = condition_covariance(returns, symbols, graph, separation)

    assert cov.shape == (n, n)
    off_diag = cov[np.triu_indices(n, k=1)]
    assert np.all(np.abs(off_diag) < 0.02)

    uncond = np.cov(returns, rowvar=False, bias=True)
    uncond_off = uncond[np.triu_indices(n, k=1)]
    assert np.mean(np.abs(uncond_off)) > 0.0005

    assert meta["selected_drivers"] == ["common_factor"]
    assert "driver_r2" in meta
    assert "betas" in meta
    assert len(meta["conditional_covariance_hash"]) == 64

    mu = np.mean(returns, axis=0)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    result = optimize_minimum_variance(inputs, long_only=True)
    assert abs(result.weights.sum() - 1.0) < 1e-6
    assert np.all(np.abs(result.weights - 0.25) < 0.05)


def test_driver_returns_with_proxies():
    """Proxies should be averaged when available."""
    rng = np.random.default_rng(7)
    t = 60
    proxy = rng.normal(0.0, 0.01, size=t)
    noise = rng.normal(0.0, 0.005, size=(t, 3))
    returns = np.column_stack([proxy + noise[:, 0], proxy + noise[:, 1], noise[:, 2]])
    symbols = ["A", "B", "C"]
    graph = CausalGraph(
        drivers=[{"name": "mkt", "proxies": ["A", "B"]}],
        edges=[{"from": "mkt", "to": ["A", "B", "C"]}],
    )
    driver_returns = build_driver_returns(returns, symbols, graph)
    assert driver_returns.shape == (t, 1)


@pytest.mark.parametrize(
    ("yaml_snippet", "expected_substring"),
    [
        (
            """
    causal_graph:
      drivers:
        - name: x
        - name: x
      edges: []
    causal_separation:
      mode: condition_on
      drivers: [x]
            """,
            "duplicate driver name",
        ),
        (
            """
    causal_graph:
      drivers:
        - name: x
      edges: []
    causal_separation:
      mode: condition_on
      drivers: [missing]
            """,
            "undeclared driver in causal_separation",
        ),
        (
            """
    causal_graph:
      drivers:
        - name: x
      edges:
        - from: not_a_driver
          to: [A]
    causal_separation:
      mode: condition_on
      drivers: [x]
            """,
            "edge source is not a driver",
        ),
        (
            """
    causal_graph:
      drivers:
        - name: x
      edges:
        - from: x
          to: [Z]
    causal_separation:
      mode: condition_on
      drivers: [x]
            """,
            "edge target not in optimization universe",
        ),
        (
            """
    causal_graph:
      drivers:
        - name: A
        - name: B
      edges:
        - from: A
          to: [B]
        - from: B
          to: [A]
    causal_separation:
      mode: condition_on
      drivers: [A]
            """,
            "causal graph contains a cycle",
        ),
    ],
)
def test_validation_rejects_malformed_causal_specs(yaml_snippet, expected_substring):
    base = """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: causal-validation-test
spec:
  universe:
    symbols: [A, B]
  schedule:
    rebalance: 1M
    lookback: 252d
  execution:
    slippage: 0.0
  portfolio:
    objective: minimum_variance
    covariance_estimator: sample
{snippet}
"""
    yaml_text = base.format(snippet=yaml_snippet)
    strategy = Strategy.from_yaml(yaml_text)
    errors = strategy.validate()
    assert any(expected_substring in e for e in errors), errors


def test_certificate_records_causal_lineage(tmp_path: Path):
    """A backtest certificate should include causal hashes and metadata."""
    data_path = (
        Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"
    )
    strategy_path = tmp_path / "causal_strategy.yaml"
    strategy_path.write_text(
        """
apiVersion: aureum.io/v1alpha1
kind: Strategy
metadata:
  name: causal-mpt-cert-test
spec:
  universe:
    source: sp500
    filter:
      sector: Technology
      min_price: 5.00
  schedule:
    rebalance: 1M
    lookback: 252d
  portfolio:
    objective: minimum_variance
    risk_measure: variance
    covariance_estimator: sample
    lookback_days: 252
    long_only: true
    causal_graph:
      drivers:
        - name: tech_factor
      edges:
        - from: tech_factor
          to: [AAPL, MSFT, NVDA, GOOGL]
    causal_separation:
      mode: condition_on
      drivers: [tech_factor]
  risk:
    max_drawdown:
      value: 0.30
      hard: true
    max_leverage:
      value: 1.00
      hard: true
  execution:
    slippage: 0.0005
""",
        encoding="utf-8",
    )

    strategy = Strategy.from_file(strategy_path)
    data = MarketData.from_csv(data_path)
    runner = BacktestRunner(strategy, data, data_source=str(data_path))
    env = Environment(
        aureum_version=__version__,
        git_commit="test",
        git_dirty=False,
        python_version="3.11.9",
        platform="test",
    )
    cert = runner.build_certificate(
        strategy_path=strategy_path,
        data_path=data_path,
        environment=env,
    )

    pc = cert.portfolio_construction
    assert pc is not None
    assert len(pc.causal_graph_hash) == 64
    assert len(pc.conditional_covariance_hash) == 64

    causal_entries = [
        entry
        for entry in cert.execution_trace["rebalance_log"]
        if "portfolio" in entry and "causal" in entry["portfolio"]
    ]
    assert causal_entries, "rebalance log should include causal metadata"

    # Optimization input hash should change when the causal graph changes.
    original_hash = pc.optimization_inputs_hash
    strategy_path2 = tmp_path / "causal_strategy2.yaml"
    strategy_path2.write_text(
        strategy_path.read_text(encoding="utf-8").replace(
            "tech_factor", "renamed_tech_factor"
        ),
        encoding="utf-8",
    )
    strategy2 = Strategy.from_file(strategy_path2)
    runner2 = BacktestRunner(strategy2, data, data_source=str(data_path))
    cert2 = runner2.build_certificate(
        strategy_path=strategy_path2,
        data_path=data_path,
        environment=env,
    )
    assert cert2.portfolio_construction.optimization_inputs_hash != original_hash


def test_auto_mode_selects_drivers_by_r2():
    """Auto mode selects drivers whose aggregate R² exceeds the threshold."""
    rng = np.random.default_rng(99)
    t = 200
    n = 5
    strong = rng.normal(0.0, 0.02, size=t)
    noise = rng.normal(0.0, 0.01, size=(t, n))
    returns = np.empty((t, n))
    returns[:, :4] = 0.8 * strong[:, None] + noise[:, :4]
    returns[:, 4] = noise[:, 4]

    symbols = ["A", "B", "C", "D", "E"]
    graph = CausalGraph(
        drivers=[{"name": "strong"}, {"name": "weak"}],
        edges=[
            {"from": "strong", "to": ["A", "B", "C", "D"]},
            {"from": "weak", "to": ["E"]},
        ],
    )
    separation = CausalSeparationSpec(
        mode="auto", drivers=[], auto_r2_threshold=0.10
    )
    cov, meta = condition_covariance(returns, symbols, graph, separation)
    assert "strong" in meta["selected_drivers"]
    assert "weak" not in meta["selected_drivers"]
    assert cov.shape == (n, n)


def test_estimate_exposures_empty_driver_set():
    """Exposure matrix is empty when no drivers are supplied."""
    returns = np.random.default_rng(5).normal(0.0, 0.01, size=(30, 3))
    driver_returns = np.empty((30, 0))
    b = estimate_exposures(returns, driver_returns)
    assert b.shape == (3, 0)

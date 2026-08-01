"""Tests for the Aureum MPT optimizer module."""

from __future__ import annotations

import numpy as np
import pytest

from aureum.mpt import (
    OptimizationInputs,
    build_efficient_frontier,
    estimate_covariance,
    estimate_mean_returns,
    optimize_maximum_sharpe,
    optimize_mean_variance,
    optimize_minimum_variance,
    optimize_min_cvar,
    optimize_risk_parity,
)


def _sample_returns(seed: int = 42, n: int = 5, t: int = 252) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mu = rng.normal(0.0005, 0.001, n)
    # Build a random positive-definite covariance matrix.
    a = rng.standard_normal((n, n))
    cov = a @ a.T / n + np.eye(n) * 0.0001
    return rng.multivariate_normal(mu, cov, size=t)


def test_estimate_mean_returns():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets, method="sample")
    assert mu.shape == (rets.shape[1],)
    assert np.all(np.isfinite(mu))


def test_estimate_covariance_sample():
    rets = _sample_returns()
    cov = estimate_covariance(rets, estimator="sample")
    assert cov.shape == (rets.shape[1], rets.shape[1])
    assert np.all(np.isfinite(cov))
    eigvals = np.linalg.eigvalsh(cov)
    assert np.min(eigvals) >= -1e-12


def test_estimate_covariance_ledoit_wolf():
    rets = _sample_returns()
    cov = estimate_covariance(rets, estimator="ledoit_wolf")
    assert cov.shape == (rets.shape[1], rets.shape[1])
    assert np.all(np.isfinite(cov))
    eigvals = np.linalg.eigvalsh(cov)
    assert np.min(eigvals) > 0


def test_optimize_minimum_variance():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    result = optimize_minimum_variance(inputs, long_only=True)
    assert abs(result.weights.sum() - 1.0) < 1e-6
    assert np.all(result.weights >= -1e-9)
    assert result.risk >= 0
    assert result.objective == "minimum_variance"


def test_optimize_maximum_sharpe():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(
        expected_returns=mu,
        covariance=cov,
        risk_free_rate=0.02 / 252,
    )
    result = optimize_maximum_sharpe(inputs, long_only=True)
    assert abs(result.weights.sum() - 1.0) < 1e-6
    assert np.all(result.weights >= -1e-9)
    assert result.objective == "maximum_sharpe"
    # Tangency should have non-zero weights for at least one asset.
    assert np.max(result.weights) > 0


def test_optimize_mean_variance_target_return():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    target = float(np.mean(mu)) * 1.2
    result = optimize_mean_variance(
        inputs, target_return=target, long_only=True, max_weight=0.5
    )
    assert abs(result.weights.sum() - 1.0) < 1e-4
    assert np.all(result.weights >= -1e-9)
    assert np.all(result.weights <= 0.5 + 1e-6)
    assert result.objective == "mean_variance"


def test_optimize_mean_variance_target_risk():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    gmvp = optimize_minimum_variance(inputs, long_only=True)
    result = optimize_mean_variance(
        inputs, target_risk=gmvp.risk * 1.1, long_only=True
    )
    assert abs(result.weights.sum() - 1.0) < 1e-4
    assert result.objective == "mean_variance"


def test_optimize_risk_parity():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    result = optimize_risk_parity(inputs, long_only=True)
    assert abs(result.weights.sum() - 1.0) < 1e-4
    assert np.all(result.weights >= -1e-9)
    assert result.objective == "risk_parity"


def test_optimize_min_cvar():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    result = optimize_min_cvar(inputs, alpha=0.95, long_only=True, scenarios=rets)
    assert abs(result.weights.sum() - 1.0) < 1e-4
    assert np.all(result.weights >= -1e-9)
    assert result.objective == "minimum_cvar"
    assert result.risk_measure == "cvar_95"


def test_build_efficient_frontier():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    frontier = build_efficient_frontier(inputs, n_points=10, long_only=True)
    assert len(frontier) > 0
    for point in frontier:
        assert "expected_return" in point
        assert "risk" in point
        assert "weights" in point
        assert abs(sum(point["weights"]) - 1.0) < 1e-4


def test_box_constraints_respected():
    rets = _sample_returns(n=5)
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    result = optimize_maximum_sharpe(
        inputs, long_only=True, max_weight=0.25, min_weight=0.05
    )
    assert np.all(result.weights >= 0.05 - 1e-6)
    assert np.all(result.weights <= 0.25 + 1e-6)
    assert abs(result.weights.sum() - 1.0) < 1e-4


def test_covariance_estimator_unknown():
    rets = _sample_returns()
    with pytest.raises(ValueError, match="unsupported covariance estimator"):
        estimate_covariance(rets, estimator="magic")


def test_mean_estimator_unknown():
    rets = _sample_returns()
    with pytest.raises(ValueError, match="unsupported mean estimator"):
        estimate_mean_returns(rets, method="magic")


def test_optimize_unknown_objective():
    rets = _sample_returns()
    mu = estimate_mean_returns(rets)
    cov = estimate_covariance(rets)
    inputs = OptimizationInputs(expected_returns=mu, covariance=cov)
    with pytest.raises(ValueError, match="specify either target_return"):
        optimize_mean_variance(inputs)

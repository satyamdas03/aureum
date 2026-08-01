"""Tests for Edge 3 — conformal portfolio construction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from aureum import __version__
from aureum.backtest import BacktestRunner, MarketData
from aureum.certificate import BacktestCertificate, get_environment
from aureum.conformal import (
    ConformalForecast,
    ConformalForecastSet,
    ConformalPortfolioResult,
    conformalize_forecasts,
    optimize_conformalized_portfolio,
)
from aureum.strategy import Strategy

CONFORMAL_STRATEGY = (
    Path(__file__).parents[3] / "examples" / "strategies" / "conformal_mean_variance.yaml"
)
EXAMPLE_DATA = Path(__file__).parents[3] / "examples" / "data" / "synthetic_prices.csv"


def _gaussian_returns(seed: int = 42, n: int = 5, t: int = 500) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mu = rng.normal(0.0005, 0.001, n)
    a = rng.standard_normal((n, n))
    cov = a @ a.T / n + np.eye(n) * 0.0001
    return rng.multivariate_normal(mu, cov, size=t)


def test_conformal_forecast_dataclass_fields():
    forecast = ConformalForecast(
        point=0.001, lower=-0.02, upper=0.022, quantile=0.021, coverage=0.95
    )
    assert forecast.point == 0.001
    assert forecast.lower == -0.02
    assert forecast.upper == 0.022


def test_conformalize_forecasts_returns_set():
    rets = _gaussian_returns()
    forecast_set = conformalize_forecasts(rets, coverage=0.90, calibration_fraction=0.25)
    assert isinstance(forecast_set, ConformalForecastSet)
    assert len(forecast_set.forecasts) == rets.shape[1]
    assert forecast_set.lower_bounds.shape == (rets.shape[1],)
    assert forecast_set.upper_bounds.shape == (rets.shape[1],)
    assert np.all(forecast_set.widths >= 0.0)
    assert np.all(forecast_set.lower_bounds <= forecast_set.upper_bounds)
    assert 0.0 < forecast_set.quantile_level <= 1.0
    assert forecast_set.calibration_hash


def test_conformal_coverage_on_synthetic_gaussian():
    """Empirical coverage should be close to the target marginal guarantee.

    The split-conformal correction used in ``conformalize_forecasts`` gives a
    finite-sample marginal coverage of 0.90.  We allow a small tolerance on this
    deterministic synthetic test so the CI assertion is not flaky.
    """
    rets = _gaussian_returns(t=500)
    train = rets[:400]
    test = rets[400:]

    forecast_set = conformalize_forecasts(
        train, coverage=0.90, calibration_fraction=0.25
    )

    coverages = []
    for i in range(rets.shape[1]):
        covered = np.count_nonzero(
            (test[:, i] >= forecast_set.lower_bounds[i])
            & (test[:, i] <= forecast_set.upper_bounds[i])
        )
        coverages.append(covered / len(test))

    mean_coverage = float(np.mean(coverages))
    assert mean_coverage >= 0.88, f"mean coverage {mean_coverage} below tolerance"


def test_conformalized_portfolio_result_structure():
    rets = _gaussian_returns(t=252)
    result = optimize_conformalized_portfolio(
        rets,
        base_objective="minimum_variance",
        coverage=0.95,
        calibration_fraction=0.20,
        long_only=True,
    )
    assert isinstance(result, ConformalPortfolioResult)
    assert result.objective == "conformalized_portfolio"
    assert result.base_objective == "minimum_variance"
    assert result.weights.shape == (rets.shape[1],)
    assert abs(result.weights.sum() - 1.0) < 1e-4
    assert result.coverage == 0.95
    assert result.calibration_fraction == 0.20
    assert result.calibration_hash
    assert result.mean_width > 0.0
    assert len(result.prediction_set_widths) == rets.shape[1]


def test_conformalized_portfolio_fallback_on_short_window():
    """With fewer than 60 rows we should fall back to the base objective."""
    rng = np.random.default_rng(7)
    rets = rng.normal(0.001, 0.02, size=(40, 3))
    result = optimize_conformalized_portfolio(
        rets, base_objective="minimum_variance", long_only=True
    )
    assert result.objective == "conformalized_portfolio"
    assert result.warning == "conformal_warning: insufficient calibration/optimization rows"
    assert result.weights.shape == (3,)
    assert result.calibration_hash == ""
    assert result.mean_width == 0.0


def test_conformalized_portfolio_rejects_bad_base_objective():
    rets = _gaussian_returns()
    with pytest.raises(ValueError, match="unsupported conformal base objective"):
        optimize_conformalized_portfolio(rets, base_objective="minimum_cvar")


def test_conformal_strategy_yaml_validates():
    strategy = Strategy.from_file(CONFORMAL_STRATEGY)
    errors = strategy.validate()
    assert errors == [], errors


def test_conformal_strategy_has_conformal_block():
    strategy = Strategy.from_file(CONFORMAL_STRATEGY)
    portfolio = strategy.portfolio()
    assert portfolio is not None
    assert portfolio["objective"] == "conformalized_portfolio"
    assert portfolio["base_objective"] == "mean_variance"
    assert portfolio["uncertainty"]["method"] == "conformal_split"
    assert portfolio["uncertainty"]["coverage"] == 0.95


def test_conformal_portfolio_backtest_produces_rebalance_log():
    strategy = Strategy.from_file(CONFORMAL_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    result = runner.run()
    assert result.trades > 0
    conformal_entries = [
        entry for entry in result.rebalance_log if "conformal" in entry
    ]
    assert len(conformal_entries) > 0
    for entry in conformal_entries:
        conformal = entry["conformal"]
        assert conformal["coverage"] == 0.95
        assert conformal["calibration_fraction"] == 0.20
        assert conformal["mean_width"] > 0.0
        assert "lower_bounds" in conformal
        assert "upper_bounds" in conformal


def test_conformal_portfolio_certificate_includes_lineage():
    strategy = Strategy.from_file(CONFORMAL_STRATEGY)
    data = MarketData.from_csv(EXAMPLE_DATA)
    runner = BacktestRunner(strategy, data, data_source=str(EXAMPLE_DATA))
    env = get_environment(__version__, cwd=CONFORMAL_STRATEGY.parent)
    cert = runner.build_certificate(
        strategy_path=CONFORMAL_STRATEGY,
        data_path=EXAMPLE_DATA,
        environment=env,
    )
    assert cert.portfolio_construction is not None
    pc = cert.portfolio_construction
    assert pc.objective == "conformalized_portfolio"
    assert pc.calibration_set_hash
    assert isinstance(pc.calibration_set_hash, str)
    assert pc.coverage_level == 0.95
    assert pc.prediction_set_width > 0.0

    cert_dict = cert.to_dict()
    assert cert_dict["portfolio_construction"]["coverage_level"] == 0.95
    restored = BacktestCertificate.from_dict(cert_dict)
    assert restored.portfolio_construction is not None
    assert restored.portfolio_construction.coverage_level == 0.95
    assert restored.portfolio_construction.calibration_set_hash


def test_strategy_validation_rejects_missing_uncertainty():
    text = CONFORMAL_STRATEGY.read_text(encoding="utf-8")
    # Remove the uncertainty block from a copy of the YAML.
    strategy = Strategy.from_yaml(text)
    del strategy.spec["portfolio"]["uncertainty"]
    errors = strategy.validate()
    assert any("uncertainty is required" in err for err in errors)


def test_strategy_validation_rejects_bad_coverage():
    strategy = Strategy.from_file(CONFORMAL_STRATEGY)
    strategy.spec["portfolio"]["uncertainty"]["coverage"] = 1.5
    errors = strategy.validate()
    assert any("coverage must be a float in (0, 1)" in err for err in errors)

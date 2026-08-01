"""Split-conformal prediction sets for portfolio construction.

Edge 3 wraps Aureum's existing MPT optimizers with marginal, per-asset
prediction intervals so the backtest certificate can record not just the point
forecast that produced a portfolio, but the coverage level and prediction-set
width used to stress-test that forecast.

The implementation uses only NumPy and the existing ``aureum.mpt`` optimizers;
it makes no distributional assumptions beyond the marginal coverage guarantee
provided by split conformal inference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from aureum.certificate import _sha256_text, _stable_json
from aureum.mpt import (
    OptimizationInputs,
    OptimizationResult,
    estimate_covariance,
    estimate_mean_returns,
    optimize_maximum_sharpe,
    optimize_mean_variance,
    optimize_minimum_variance,
    optimize_risk_parity,
)

_ALLOWED_BASE_OBJECTIVES: frozenset[str] = frozenset(
    {"mean_variance", "minimum_variance", "maximum_sharpe", "risk_parity"}
)


@dataclass
class ConformalForecast:
    """Prediction interval for a single point forecast."""

    point: float
    lower: float
    upper: float
    quantile: float
    coverage: float


@dataclass
class ConformalForecastSet:
    """Per-asset conformal prediction intervals produced from a return matrix."""

    forecasts: list[ConformalForecast]
    point_forecast: np.ndarray
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    widths: np.ndarray
    quantile_level: float
    coverage: float
    calibration_fraction: float
    calibration_hash: str
    warning: str = ""


@dataclass
class ConformalPortfolioResult:
    """Result of optimizing a portfolio on conservative conformal lower bounds."""

    weights: np.ndarray
    expected_return: float
    base_expected_return: float
    risk: float
    objective: str
    base_objective: str
    risk_measure: str
    covariance_estimator: str
    coverage: float
    calibration_fraction: float
    calibration_hash: str
    prediction_set_widths: np.ndarray
    mean_width: float
    max_width: float
    lower_bounds: np.ndarray
    upper_bounds: np.ndarray
    quantile_level: float
    warning: str = ""


def _validate_returns(returns: np.ndarray) -> np.ndarray:
    """Ensure ``returns`` is a 2-D finite array."""
    arr = np.asarray(returns, dtype=float)
    if arr.ndim != 2:
        raise ValueError("returns must be a 2-D array (observations x assets)")
    if arr.shape[0] < 2:
        raise ValueError("returns must have at least two observations")
    if not np.all(np.isfinite(arr)):
        raise ValueError("returns must be finite")
    return arr


def _split_window(
    returns: np.ndarray,
    calibration_fraction: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Split ``returns`` into calibration and optimization rows."""
    t = returns.shape[0]
    n_cal = int(math.floor(calibration_fraction * t))
    n_cal = max(0, min(t - 1, n_cal))
    return returns[:n_cal], returns[n_cal:]


def _calibration_hash(calibration_set: np.ndarray) -> str:
    """Return a stable SHA-256 hash of the calibration return matrix."""
    return _sha256_text(_stable_json(calibration_set.tolist()))


def _run_base_objective(
    base_objective: str,
    inputs: OptimizationInputs,
    base_kwargs: dict[str, Any],
) -> OptimizationResult:
    """Dispatch to the appropriate MPT optimizer."""
    long_only = bool(base_kwargs.get("long_only", True))
    max_weight: float | None = base_kwargs.get("max_weight")
    min_weight: float | None = base_kwargs.get("min_weight")

    common: dict[str, Any] = {
        "long_only": long_only,
        "max_weight": max_weight,
        "min_weight": min_weight,
    }

    if base_objective == "mean_variance":
        target_return: float | None = base_kwargs.get("target_return")
        target_risk: float | None = base_kwargs.get("target_risk")
        return optimize_mean_variance(
            inputs,
            target_return=target_return,
            target_risk=target_risk,
            **common,
        )
    if base_objective == "minimum_variance":
        return optimize_minimum_variance(inputs, **common)
    if base_objective == "maximum_sharpe":
        return optimize_maximum_sharpe(inputs, **common)
    if base_objective == "risk_parity":
        return optimize_risk_parity(inputs, **common)

    raise ValueError(
        f"unsupported conformal base objective: {base_objective!r}; "
        f"allowed values: {', '.join(sorted(_ALLOWED_BASE_OBJECTIVES))}"
    )


def conformalize_forecasts(
    returns: np.ndarray,
    coverage: float = 0.95,
    calibration_fraction: float = 0.20,
) -> ConformalForecastSet:
    """Build marginal split-conformal prediction intervals for per-asset returns.

    Parameters
    ----------
    returns:
        T x N matrix of asset returns, oldest-to-newest.
    coverage:
        Target marginal coverage in ``(0, 1)``.
    calibration_fraction:
        Fraction of rows reserved for calibration in ``(0, 1)``.

    Returns
    -------
    A :class:`ConformalForecastSet` containing point forecasts, lower/upper
    bounds, interval widths, and a content-addressed hash of the calibration
    window.
    """
    if not 0.0 < coverage < 1.0:
        raise ValueError(f"coverage must be in (0, 1), got {coverage}")
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError(
            f"calibration_fraction must be in (0, 1), got {calibration_fraction}"
        )

    arr = _validate_returns(returns)
    t, n = arr.shape
    R_cal, R_opt = _split_window(arr, calibration_fraction)
    n_cal = R_cal.shape[0]

    if n_cal < 30 or R_opt.shape[0] < 30:
        raise ValueError(
            "insufficient rows for split conformal: "
            f"need at least 30 calibration and 30 optimization rows, "
            f"got {n_cal} and {R_opt.shape[0]}"
        )

    mu_hat = estimate_mean_returns(R_opt, method="sample")
    scores = np.abs(R_cal - mu_hat)

    quantile_level = math.ceil((n_cal + 1) * coverage) / n_cal
    quantile_level = min(1.0, quantile_level)

    q = np.array(
        [float(np.quantile(scores[:, i], quantile_level, method="higher")) for i in range(n)]
    )

    lower = mu_hat - q
    upper = mu_hat + q
    widths = upper - lower

    forecasts = [
        ConformalForecast(
            point=float(mu_hat[i]),
            lower=float(lower[i]),
            upper=float(upper[i]),
            quantile=float(q[i]),
            coverage=float(coverage),
        )
        for i in range(n)
    ]

    return ConformalForecastSet(
        forecasts=forecasts,
        point_forecast=mu_hat,
        lower_bounds=lower,
        upper_bounds=upper,
        widths=widths,
        quantile_level=quantile_level,
        coverage=float(coverage),
        calibration_fraction=float(calibration_fraction),
        calibration_hash=_calibration_hash(R_cal),
    )


def optimize_conformalized_portfolio(
    returns: np.ndarray,
    base_objective: str,
    coverage: float = 0.95,
    calibration_fraction: float = 0.20,
    **base_kwargs: Any,
) -> ConformalPortfolioResult:
    """Optimize a portfolio on conservative conformal lower-bound returns.

    Parameters
    ----------
    returns:
        T x N matrix of asset returns, oldest-to-newest.
    base_objective:
        Underlying MPT objective to run on the conservative expected returns.
        One of ``mean_variance``, ``minimum_variance``, ``maximum_sharpe``,
        or ``risk_parity``.
    coverage:
        Target marginal coverage of the per-asset prediction sets.
    calibration_fraction:
        Share of ``returns`` reserved as a calibration set.
    base_kwargs:
        Forwarded to the base MPT optimizer. Typical keys: ``covariance_estimator``,
        ``risk_measure`` (recorded for lineage), ``risk_free_rate``,
        ``long_only``, ``max_weight``, ``min_weight``, ``target_return``,
        ``target_risk``.

    Returns
    -------
    A :class:`ConformalPortfolioResult` carrying the optimized weights, the
    conservative expected return, and conformal lineage metadata.

    Raises
    ------
    ValueError
        If ``base_objective`` is not supported or if the inputs are invalid.
    """
    if base_objective not in _ALLOWED_BASE_OBJECTIVES:
        raise ValueError(
            f"unsupported conformal base objective: {base_objective!r}; "
            f"allowed values: {', '.join(sorted(_ALLOWED_BASE_OBJECTIVES))}"
        )

    arr = _validate_returns(returns)
    covariance_estimator: str = base_kwargs.get("covariance_estimator", "sample")
    risk_free_rate = float(base_kwargs.get("risk_free_rate", 0.0))

    R_cal, R_opt = _split_window(arr, calibration_fraction)
    n_cal = R_cal.shape[0]
    n_opt = R_opt.shape[0]

    if n_cal < 30 or n_opt < 30:
        # Fallback: run the base objective on the full window with a point
        # forecast and record a warning in the lineage metadata.
        mu_hat = estimate_mean_returns(arr, method="sample")
        cov = estimate_covariance(arr, estimator=covariance_estimator)
        inputs = OptimizationInputs(
            expected_returns=mu_hat,
            covariance=cov,
            risk_free_rate=risk_free_rate,
        )
        result = _run_base_objective(base_objective, inputs, base_kwargs)
        n = arr.shape[1]
        return ConformalPortfolioResult(
            weights=result.weights,
            expected_return=float(result.weights @ mu_hat),
            base_expected_return=float(result.weights @ mu_hat),
            risk=result.risk,
            objective="conformalized_portfolio",
            base_objective=base_objective,
            risk_measure=result.risk_measure,
            covariance_estimator=covariance_estimator,
            coverage=float(coverage),
            calibration_fraction=float(calibration_fraction),
            calibration_hash="",
            prediction_set_widths=np.zeros(n),
            mean_width=0.0,
            max_width=0.0,
            lower_bounds=mu_hat,
            upper_bounds=mu_hat,
            quantile_level=0.0,
            warning="conformal_warning: insufficient calibration/optimization rows",
        )

    forecast_set = conformalize_forecasts(
        arr, coverage=coverage, calibration_fraction=calibration_fraction
    )
    mu_hat = forecast_set.point_forecast
    mu_lower = forecast_set.lower_bounds

    cov = estimate_covariance(R_opt, estimator=covariance_estimator)
    inputs = OptimizationInputs(
        expected_returns=mu_lower,
        covariance=cov,
        risk_free_rate=risk_free_rate,
    )
    result = _run_base_objective(base_objective, inputs, base_kwargs)

    weights = result.weights
    return ConformalPortfolioResult(
        weights=weights,
        expected_return=float(weights @ mu_lower),
        base_expected_return=float(weights @ mu_hat),
        risk=result.risk,
        objective="conformalized_portfolio",
        base_objective=base_objective,
        risk_measure=result.risk_measure,
        covariance_estimator=covariance_estimator,
        coverage=float(coverage),
        calibration_fraction=float(calibration_fraction),
        calibration_hash=forecast_set.calibration_hash,
        prediction_set_widths=forecast_set.widths,
        mean_width=float(np.mean(forecast_set.widths)),
        max_width=float(np.max(forecast_set.widths)),
        lower_bounds=mu_lower,
        upper_bounds=forecast_set.upper_bounds,
        quantile_level=forecast_set.quantile_level,
    )

"""Modern Portfolio Theory optimizers for Aureum.

Implements classical mean-variance optimization and practical extensions using
only NumPy (plus optional scikit-learn for Ledoit-Wolf shrinkage).  All
functions return portfolio weights that sum to one by default and are designed
to emit reproducible, auditable inputs for the Aureum certificate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


def _validate_returns(returns: np.ndarray) -> np.ndarray:
    """Ensure returns is a 2-D array with at least two observations."""
    arr = np.asarray(returns, dtype=float)
    if arr.ndim != 2:
        raise ValueError("returns must be a 2-D array (observations x assets)")
    if arr.shape[0] < 2:
        raise ValueError("returns must have at least two observations")
    return arr


def estimate_covariance(
    returns: np.ndarray,
    estimator: str = "sample",
    **kwargs: Any,
) -> np.ndarray:
    """Estimate an asset covariance matrix.

    Supported estimators:

    - ``sample``: the usual maximum-likelihood / unbiased sample covariance.
    - ``ledoit_wolf``: Ledoit-Wolf shrinkage toward a scalar multiple of the
      identity matrix.  Requires ``scikit-learn`` to be installed.  The
      shrinkage intensity is estimated from the data automatically.

    Parameters
    ----------
    returns:
        T x N matrix of asset returns (e.g. daily log-returns).
    estimator:
        Name of the estimator to use.
    kwargs:
        Extra arguments forwarded to the underlying estimator.

    Returns
    -------
    N x N positive-definite covariance matrix.
    """
    arr = _validate_returns(returns)
    t, n = arr.shape
    if estimator == "sample":
        if t == 1:
            return np.zeros((n, n))
        # Use maximum-likelihood denominator (T) for consistency with sklearn.
        return np.cov(arr, rowvar=False, bias=True)
    if estimator == "ledoit_wolf":
        try:
            from sklearn.covariance import LedoitWolf
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Ledoit-Wolf covariance requires scikit-learn; "
                "install it or use estimator='sample'"
            ) from exc
        lw = LedoitWolf(**kwargs).fit(arr)
        return np.asarray(lw.covariance_, dtype=float)
    raise ValueError(f"unsupported covariance estimator: {estimator!r}")


def estimate_mean_returns(returns: np.ndarray, method: str = "sample") -> np.ndarray:
    """Estimate expected returns.

    - ``sample``: arithmetic mean of historical returns.
    """
    arr = _validate_returns(returns)
    if method == "sample":
        return np.mean(arr, axis=0)
    raise ValueError(f"unsupported mean estimator: {method!r}")


@dataclass
class OptimizationInputs:
    """Bundled inputs for an MPT optimization problem."""

    expected_returns: np.ndarray
    covariance: np.ndarray
    risk_free_rate: float = 0.0

    def __post_init__(self) -> None:
        self.expected_returns = np.asarray(self.expected_returns, dtype=float)
        self.covariance = np.asarray(self.covariance, dtype=float)
        n = self.expected_returns.shape[0]
        if self.covariance.shape != (n, n):
            raise ValueError("expected_returns and covariance dimensions do not match")


@dataclass
class OptimizationResult:
    """Result of an MPT optimization."""

    weights: np.ndarray
    expected_return: float
    risk: float
    objective: str
    risk_measure: str
    frontier_point: bool = False

    def __post_init__(self) -> None:
        self.weights = np.asarray(self.weights, dtype=float)


# ---------------------------------------------------------------------------
# Mean-variance helpers
# ---------------------------------------------------------------------------


def _check_psd(cov: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    """Return a well-conditioned copy of ``cov``, raising if it is too pathological."""
    cov = np.asarray(cov, dtype=float)
    eigvals = np.linalg.eigvalsh(cov)
    if np.min(eigvals) < -tol:
        raise ValueError(
            f"covariance matrix is not positive semi-definite (min eigenvalue {np.min(eigvals):.3e})"
        )
    if np.min(eigvals) < tol:
        # Add a tiny ridge to make it safely invertible.
        cov = cov + np.eye(cov.shape[0]) * (tol - np.min(eigvals))
    return cov


def _annualize_daily(return_value: float, risk_value: float) -> tuple[float, float]:
    """Annualize daily mean and standard deviation using 252 trading days."""
    return return_value * 252, risk_value * math.sqrt(252)


def _mean_variance_closed_form(
    mu: np.ndarray,
    sigma: np.ndarray,
    target_return: float,
) -> np.ndarray:
    """Analytic Markowitz weights for a target expected return."""
    inv = np.linalg.inv(sigma)
    ones = np.ones(len(mu))
    a = float(ones.T @ inv @ ones)
    b = float(ones.T @ inv @ mu)
    c = float(mu.T @ inv @ mu)
    delta = a * c - b * b
    if abs(delta) < 1e-18:
        raise ValueError("efficient frontier is degenerate (delta ~ 0)")
    lam0 = (c - target_return * b) / delta
    lam1 = (target_return * a - b) / delta
    return inv @ (lam0 * ones + lam1 * mu)


# ---------------------------------------------------------------------------
# Public optimizers
# ---------------------------------------------------------------------------


def optimize_mean_variance(
    inputs: OptimizationInputs,
    *,
    target_return: float | None = None,
    target_risk: float | None = None,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
) -> OptimizationResult:
    """Mean-variance efficient portfolio.

    Exactly one of ``target_return`` or ``target_risk`` must be supplied.  When
    ``target_return`` is supplied the weights are the closed-form Markowitz
    solution optionally projected onto box constraints.  When ``target_risk``
    is supplied a numerical search over the frontier is performed.
    """
    mu = inputs.expected_returns
    sigma = _check_psd(inputs.covariance)
    n = len(mu)

    if target_return is None and target_risk is None:
        raise ValueError("specify either target_return or target_risk")
    if target_return is not None and target_risk is not None:
        raise ValueError("specify only one of target_return or target_risk")

    if target_return is not None:
        w = _mean_variance_closed_form(mu, sigma, target_return)
    else:
        # Search the frontier for the weight vector with the target risk.
        # Build a frontier by scanning target returns from the GMVP return upward.
        inv = np.linalg.inv(sigma)
        ones = np.ones(n)
        a = float(ones.T @ inv @ ones)
        b = float(ones.T @ inv @ mu)
        gmvp_return = b / a
        best: tuple[float, np.ndarray] | None = None
        assert target_risk is not None
        for stretch in np.linspace(0.0, 3.0, 200):
            trial_return = gmvp_return + stretch * abs(gmvp_return)
            try:
                w_trial = _mean_variance_closed_form(mu, sigma, trial_return)
                risk = math.sqrt(float(w_trial.T @ sigma @ w_trial))
            except ValueError:
                continue
            gap = abs(risk - target_risk)
            if best is None or gap < best[0]:
                best = (gap, w_trial)
        if best is None:
            raise ValueError(f"could not find portfolio with target risk {target_risk}")
        w = best[1]

    if long_only or max_weight is not None or min_weight is not None:
        w = _project_box_constraints(w, long_only, max_weight, min_weight)

    ret = float(w.T @ mu)
    risk = math.sqrt(max(0.0, float(w.T @ sigma @ w)))
    return OptimizationResult(
        weights=w,
        expected_return=ret,
        risk=risk,
        objective="mean_variance",
        risk_measure="variance",
    )


def optimize_minimum_variance(
    inputs: OptimizationInputs,
    *,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
) -> OptimizationResult:
    """Global minimum-variance portfolio (does not use expected returns)."""
    sigma = _check_psd(inputs.covariance)
    inv = np.linalg.inv(sigma)
    ones = np.ones(len(sigma))
    w = inv @ ones / float(ones.T @ inv @ ones)

    if long_only or max_weight is not None or min_weight is not None:
        w = _project_box_constraints(w, long_only, max_weight, min_weight)

    ret = float(w.T @ inputs.expected_returns)
    risk = math.sqrt(max(0.0, float(w.T @ sigma @ w)))
    return OptimizationResult(
        weights=w,
        expected_return=ret,
        risk=risk,
        objective="minimum_variance",
        risk_measure="variance",
    )


def optimize_maximum_sharpe(
    inputs: OptimizationInputs,
    *,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
) -> OptimizationResult:
    """Tangency portfolio: maximize (mu - rf) / sigma."""
    mu = inputs.expected_returns - inputs.risk_free_rate
    sigma = _check_psd(inputs.covariance)
    inv = np.linalg.inv(sigma)
    ones = np.ones(len(mu))
    raw = inv @ mu
    denom = float(ones.T @ raw)
    if abs(denom) < 1e-18:
        raise ValueError("tangency portfolio is undefined for these inputs")
    w = raw / denom

    if long_only or max_weight is not None or min_weight is not None:
        w = _project_box_constraints(w, long_only, max_weight, min_weight)
        # Re-normalise to full investment after projection.
        if w.sum() != 0:
            w = w / w.sum()

    ret = float(w.T @ (mu + inputs.risk_free_rate))
    risk = math.sqrt(max(0.0, float(w.T @ sigma @ w)))
    return OptimizationResult(
        weights=w,
        expected_return=ret,
        risk=risk,
        objective="maximum_sharpe",
        risk_measure="variance",
    )


def optimize_risk_parity(
    inputs: OptimizationInputs,
    *,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> OptimizationResult:
    """Equal risk contribution portfolio.

    Uses the iterative cyclical coordinate descent algorithm from Spinu (2013).
    """
    sigma = _check_psd(inputs.covariance)
    n = len(sigma)
    w = np.ones(n) / n

    for _ in range(max_iter):
        for i in range(n):
            alpha = sigma[i, i]
            beta = float((sigma @ w)[i] - w[i] * sigma[i, i])
            if alpha == 0:
                w[i] = 0.0
                continue
            # Solve w_i * (alpha * w_i + beta) = 1 / n * portfolio_variance.
            portfolio_var = float(w.T @ sigma @ w)
            target = portfolio_var / n
            # Quadratic alpha * w_i^2 + beta * w_i - target = 0.
            disc = beta * beta + 4 * alpha * target
            root = (-beta + math.sqrt(disc)) / (2 * alpha)
            w[i] = max(0.0, root)
        w = w / w.sum() if w.sum() > 0 else np.ones(n) / n
        mrc = sigma @ w
        rc = w * mrc
        if np.max(np.abs(rc - rc.mean())) < tol:
            break

    if long_only or max_weight is not None or min_weight is not None:
        w = _project_box_constraints(w, long_only, max_weight, min_weight)
        if w.sum() > 0:
            w = w / w.sum()

    ret = float(w.T @ inputs.expected_returns)
    risk = math.sqrt(max(0.0, float(w.T @ sigma @ w)))
    return OptimizationResult(
        weights=w,
        expected_return=ret,
        risk=risk,
        objective="risk_parity",
        risk_measure="variance",
    )


def optimize_min_cvar(
    inputs: OptimizationInputs,
    *,
    alpha: float = 0.95,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
    scenarios: np.ndarray | None = None,
) -> OptimizationResult:
    """Minimum Conditional Value-at-Risk portfolio.

    Solves the Rockafellar-Uryasev linear-programming formulation using scipy's
    linprog.  ``scenarios`` is a T x N matrix of asset returns; if omitted, the
    historical returns used to build ``inputs`` are assumed.
    """
    try:
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "CVaR optimization requires scipy; install it or use a variance-based objective"
        ) from exc

    if scenarios is None:
        raise ValueError("scenarios (T x N return matrix) is required for CVaR optimization")
    R = np.asarray(scenarios, dtype=float)
    t, n = R.shape
    if n != len(inputs.expected_returns):
        raise ValueError("scenarios must have the same number of assets as expected_returns")

    # Variables: [weights (n), auxiliary t (1), u_i (T)].
    c = np.zeros(n + 1 + t)
    c[n] = 1.0
    c[n + 1 :] = 1.0 / ((1.0 - alpha) * t)

    A_eq = np.zeros((1, n + 1 + t))
    A_eq[0, :n] = 1.0
    b_eq = np.array([1.0])

    A_ub = np.zeros((t, n + 1 + t))
    A_ub[:, :n] = -R  # portfolio return scenarios
    A_ub[:, n] = -1.0
    A_ub[:, n + 1 :] = -np.eye(t)
    b_ub = np.zeros(t)

    bounds = [(0.0, 1.0) for _ in range(n)] + [(None, None)] + [(0.0, None) for _ in range(t)]

    if max_weight is not None:
        for i in range(n):
            current_upper = bounds[i][1]
            new_upper = min(current_upper, max_weight) if current_upper is not None else max_weight
            bounds[i] = (bounds[i][0], new_upper)
    if min_weight is not None:
        for i in range(n):
            bounds[i] = (max(bounds[i][0], min_weight), bounds[i][1])

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"CVaR optimization failed: {res.message}")

    w = res.x[:n]
    # Re-normalise to account for any tiny numerical drift.
    if w.sum() > 0:
        w = w / w.sum()

    cvar = res.fun
    ret = float(w.T @ inputs.expected_returns)
    return OptimizationResult(
        weights=w,
        expected_return=ret,
        risk=cvar,
        objective="minimum_cvar",
        risk_measure=f"cvar_{int(alpha * 100)}",
    )


# ---------------------------------------------------------------------------
# Box-projection helper
# ---------------------------------------------------------------------------


def _project_box_constraints(
    weights: np.ndarray,
    long_only: bool,
    max_weight: float | None,
    min_weight: float | None,
    max_iter: int = 100,
) -> np.ndarray:
    """Project weights onto the simplex intersected with optional box constraints.

    Uses a simple iterative clipping + re-normalisation scheme.  This is not a
    formal quadratic-programming projection but is deterministic, fast, and
    sufficient for the certificate-backed MVP.  Future iterations can swap in an
    exact QP solver.
    """
    w = np.asarray(weights, dtype=float).copy()
    if long_only:
        w = np.maximum(w, 0.0)
    if min_weight is not None:
        w = np.maximum(w, min_weight)
    if max_weight is not None:
        w = np.minimum(w, max_weight)

    # Iteratively project onto the simplex while respecting bounds.
    for _ in range(max_iter):
        total = w.sum()
        if abs(total - 1.0) < 1e-12:
            break
        if total == 0:
            n = len(w)
            w = np.ones(n) / n
            if long_only:
                w = np.maximum(w, 0.0)
            if min_weight is not None:
                w = np.maximum(w, min_weight)
            if max_weight is not None:
                w = np.minimum(w, max_weight)
            continue
        # Scale to sum to 1.
        scale = 1.0 / total
        w = w * scale
        if long_only:
            w = np.maximum(w, 0.0)
        if max_weight is not None:
            # If any weight exceeds the cap, clip it and redistribute the excess.
            excess = np.maximum(w - max_weight, 0.0)
            if excess.sum() > 1e-12:
                w = np.minimum(w, max_weight)
                redistribute = excess / max(len(w) - 1, 1)
                mask = w < max_weight
                if mask.any():
                    w[mask] += redistribute[mask]
                else:
                    break
        if min_weight is not None:
            deficit = np.maximum(min_weight - w, 0.0)
            if deficit.sum() > 1e-12:
                # Take from the largest positions to satisfy minimums.
                w = np.maximum(w, min_weight)
                shortfall = w.sum() - 1.0
                if shortfall > 1e-12:
                    order = np.argsort(w)[::-1]
                    for idx in order:
                        if shortfall <= 0:
                            break
                        room = w[idx] - (min_weight if min_weight is not None else 0.0)
                        take = min(room, shortfall)
                        w[idx] -= take
                        shortfall -= take

    # Final clean-up.
    if long_only:
        w = np.maximum(w, 0.0)
    if max_weight is not None:
        w = np.minimum(w, max_weight)
    if w.sum() > 0:
        w = w / w.sum()
    return w


# ---------------------------------------------------------------------------
# Efficient frontier
# ---------------------------------------------------------------------------


def build_efficient_frontier(
    inputs: OptimizationInputs,
    *,
    n_points: int = 20,
    long_only: bool = True,
    max_weight: float | None = None,
    min_weight: float | None = None,
) -> list[dict[str, Any]]:
    """Compute ``n_points`` along the mean-variance efficient frontier.

    Returns a list of dicts with keys ``return``, ``risk``, and ``weights``.
    """
    mu = inputs.expected_returns
    sigma = _check_psd(inputs.covariance)
    inv = np.linalg.inv(sigma)
    ones = np.ones(len(mu))
    a = float(ones.T @ inv @ ones)
    b = float(ones.T @ inv @ mu)
    gmvp_return = b / a

    # Upper bound: max individual asset return, but allow leverage up to 2x GMVP risk.
    max_asset_return = float(np.max(mu))
    max_return = max(max_asset_return, gmvp_return * 1.5)
    targets = np.linspace(gmvp_return, max_return, n_points)

    points: list[dict[str, Any]] = []
    for target in targets:
        try:
            res = optimize_mean_variance(
                inputs,
                target_return=float(target),
                long_only=long_only,
                max_weight=max_weight,
                min_weight=min_weight,
            )
            points.append(
                {
                    "expected_return": float(res.expected_return),
                    "risk": float(res.risk),
                    "weights": res.weights.tolist(),
                }
            )
        except ValueError:
            continue
    return points

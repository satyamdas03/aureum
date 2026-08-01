"""Causal MPT — declared latent-driver covariance conditioning for Aureum.

Edge 2 of the Aureum superpowers adds a user-declared causal graph of latent
macro drivers and asset children.  The optimizer conditions the covariance
matrix on those drivers, removing the shared macro component before portfolio
construction.  The certificate records the declared graph and the resulting
conditional covariance so a validator can reproduce the separation step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np

from aureum.certificate import _sha256_text, _stable_json
from aureum.mpt import _check_psd


@dataclass
class CausalGraph:
    """Declared latent-driver DAG for a portfolio."""

    drivers: list[dict[str, Any]]
    edges: list[dict[str, Any]]

    @classmethod
    def from_portfolio_spec(cls, spec: dict[str, Any]) -> CausalGraph:
        """Build a CausalGraph from ``spec.portfolio``."""
        graph = spec.get("causal_graph", {}) or {}
        return cls(
            drivers=list(graph.get("drivers", [])),
            edges=list(graph.get("edges", [])),
        )

    def driver_names(self) -> list[str]:
        """Return the declared driver names in order."""
        return [d["name"] for d in self.drivers]

    def children(self, driver: str) -> list[str]:
        """Return all asset targets of edges originating from ``driver``."""
        out: list[str] = []
        for edge in self.edges:
            if edge.get("from") == driver:
                targets = edge.get("to", [])
                if isinstance(targets, str):
                    targets = [targets]
                out.extend(targets)
        return out

    def validate(self, symbols: list[str]) -> list[str]:
        """Return a list of validation errors; empty if valid."""
        errors: list[str] = []
        names = self.driver_names()
        if len(names) != len(set(names)):
            errors.append("duplicate driver name")

        known_drivers = set(names)
        known_symbols = set(symbols)
        has_symbol_list = bool(known_symbols)

        # Structural edge checks.
        for edge in self.edges:
            src = edge.get("from")
            if src not in known_drivers:
                errors.append("edge source is not a driver")
            targets = edge.get("to", [])
            if isinstance(targets, str):
                targets = [targets]
            if has_symbol_list:
                for target in targets:
                    if target not in known_symbols:
                        errors.append("edge target not in optimization universe")

        # Cycle detection on the declared causal graph.  Drivers and assets
        # share a namespace so that an asset listed as a driver (or a driver
        # listed as its own child) creates a self-loop / cycle.
        g = nx.DiGraph()
        g.add_nodes_from(known_drivers | known_symbols)
        for edge in self.edges:
            src = edge.get("from")
            targets = edge.get("to", [])
            if isinstance(targets, str):
                targets = [targets]
            if src not in known_drivers:
                continue
            for target in targets:
                if target in known_symbols:
                    g.add_edge(src, target)
        try:
            nx.find_cycle(g, orientation="original")
            errors.append("causal graph contains a cycle")
        except nx.NetworkXNoCycle:
            pass

        return errors


@dataclass
class CausalSeparationSpec:
    """Which drivers to condition out of the covariance matrix."""

    mode: str
    drivers: list[str]
    auto_r2_threshold: float = 0.10

    @classmethod
    def from_portfolio_spec(
        cls, spec: dict[str, Any]
    ) -> CausalSeparationSpec | None:
        """Parse ``spec.portfolio.causal_separation`` if present."""
        sep = spec.get("causal_separation")
        if sep is None:
            return None
        return cls(
            mode=str(sep.get("mode", "")),
            drivers=list(sep.get("drivers", [])),
            auto_r2_threshold=float(sep.get("auto_r2_threshold", 0.10)),
        )


def _fix_sign(vector: np.ndarray) -> np.ndarray:
    """Return a deterministic sign for a principal-component loading vector."""
    v = np.asarray(vector, dtype=float).copy()
    nonzero = np.nonzero(np.abs(v) > 1e-12)[0]
    if nonzero.size and v[nonzero[0]] < 0:
        v = -v
    return v


def _driver_r2(returns: np.ndarray, driver: np.ndarray) -> float:
    """Aggregate R² of all asset returns regressed on a single driver."""
    r = np.asarray(returns, dtype=float)
    f = np.asarray(driver, dtype=float).reshape(-1, 1)
    if f.shape[0] != r.shape[0]:
        raise ValueError("returns and driver must have the same number of rows")
    if r.shape[0] == 0:
        return 0.0

    mean_r = r.mean(axis=0, keepdims=True)
    sst = float(np.sum((r - mean_r) ** 2))
    if sst <= 0.0:
        return 0.0

    # Univariate OLS of every asset on this driver.
    beta = np.linalg.solve(f.T @ f + 1e-12, f.T @ r).ravel()
    fitted = (f @ beta.reshape(1, -1)).reshape(r.shape)
    sse = float(np.sum((r - fitted) ** 2))
    return max(0.0, 1.0 - sse / sst)


def build_driver_returns(
    returns: np.ndarray,
    symbols: list[str],
    graph: CausalGraph,
) -> np.ndarray:
    """Build a T x K matrix of latent driver returns.

    For each driver:

    - If proxies are declared and at least one proxy symbol is available in
      ``symbols``, use the equal-weighted arithmetic mean of available proxy
      returns.
    - Otherwise use the first principal component of the child-asset returns.

    Drivers are orthogonalized in declared order using Gram-Schmidt to avoid
    double-counting overlapping proxies.
    """
    arr = np.asarray(returns, dtype=float)
    if arr.ndim != 2:
        raise ValueError("returns must be a 2-D array")
    t, n = arr.shape
    if n != len(symbols):
        raise ValueError("returns column count must match len(symbols)")

    sym_to_idx = {s: i for i, s in enumerate(symbols)}
    raw_drivers: list[np.ndarray] = []

    for driver in graph.drivers:
        proxies = driver.get("proxies")
        if proxies:
            available = [p for p in proxies if p in sym_to_idx]
            if available:
                cols = [sym_to_idx[p] for p in available]
                raw_drivers.append(arr[:, cols].mean(axis=1))
                continue

        children = [c for c in graph.children(driver["name"]) if c in sym_to_idx]
        if not children:
            raise ValueError(
                f"driver '{driver['name']}' has no proxies or children "
                "available in the optimization universe"
            )
        child_rets = arr[:, [sym_to_idx[c] for c in children]]
        centered = child_rets - child_rets.mean(axis=0, keepdims=True)
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        loadings = _fix_sign(vt[0])
        drv = centered @ loadings
        raw_drivers.append(drv)

    if not raw_drivers:
        return np.empty((t, 0))

    f = np.column_stack(raw_drivers)
    # Gram-Schmidt orthogonalization in declared order.
    f_orth = np.empty_like(f)
    for k in range(f.shape[1]):
        col = f[:, k].copy()
        for j in range(k):
            prev = f_orth[:, j]
            denom = float(prev @ prev)
            if denom > 1e-18:
                col = col - (float(col @ prev) / denom) * prev
        norm = float(np.linalg.norm(col))
        if norm > 1e-18:
            col = col / norm
        f_orth[:, k] = col
    return f_orth


def estimate_exposures(
    returns: np.ndarray,
    driver_returns: np.ndarray,
) -> np.ndarray:
    """Return the N x K exposure (beta) matrix via OLS.

    For each asset ``i`` the model is ``R_i = alpha_i + B_i @ F + eps_i``.
    A tiny ridge is added for numerical stability.
    """
    r = np.asarray(returns, dtype=float)
    f = np.asarray(driver_returns, dtype=float)
    if r.ndim != 2 or f.ndim != 2:
        raise ValueError("returns and driver_returns must be 2-D arrays")
    t, n = r.shape
    if f.shape[0] != t:
        raise ValueError("returns and driver_returns must have the same row count")
    k = f.shape[1]
    if k == 0:
        return np.zeros((n, 0))

    x = np.column_stack([np.ones(t), f])
    ridge = 1e-12
    xtx = x.T @ x + ridge * np.eye(k + 1)
    xtr = x.T @ r
    coef = np.linalg.solve(xtx, xtr)
    return coef[1:].T


def condition_covariance(
    returns: np.ndarray,
    symbols: list[str],
    graph: CausalGraph,
    separation: CausalSeparationSpec,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return the conditional covariance of residuals after removing drivers.

    The returned metadata dict includes driver R² values, per-asset betas, the
    selected driver list, and a SHA-256 hash of the conditional covariance
    matrix so the certificate can record lineage.
    """
    arr = np.asarray(returns, dtype=float)
    all_driver_returns = build_driver_returns(arr, symbols, graph)
    driver_names = graph.driver_names()

    r2_all: dict[str, float] = {}
    for i, name in enumerate(driver_names):
        r2_all[name] = _driver_r2(arr, all_driver_returns[:, i])

    if separation.mode == "auto":
        selected = [
            name for name in driver_names if r2_all[name] > separation.auto_r2_threshold
        ]
    elif separation.mode == "condition_on":
        selected = list(separation.drivers)
        unknown = set(selected) - set(driver_names)
        if unknown:
            raise ValueError(
                f"undeclared driver in causal_separation: {sorted(unknown)}"
            )
    else:
        raise ValueError(
            f"unsupported causal_separation.mode '{separation.mode}'; "
            "supported values: condition_on, auto"
        )

    if not selected:
        sigma = np.cov(arr, rowvar=False, bias=True)
        meta: dict[str, Any] = {
            "selected_drivers": [],
            "driver_r2": r2_all,
            "betas": {},
            "conditional_covariance_hash": _sha256_text(
                _stable_json(sigma.tolist())
            ),
        }
        return _check_psd(sigma, tol=1e-12), meta

    selected_indices = [driver_names.index(name) for name in selected]
    f_selected = all_driver_returns[:, selected_indices]
    b = estimate_exposures(arr, f_selected)
    eps = arr - f_selected @ b.T
    sigma_cond = eps.T @ eps / arr.shape[0]
    sigma_cond = _check_psd(sigma_cond, tol=1e-12)

    betas = {symbol: b[i].tolist() for i, symbol in enumerate(symbols)}
    meta = {
        "selected_drivers": selected,
        "driver_r2": {name: r2_all[name] for name in selected},
        "betas": betas,
        "conditional_covariance_hash": _sha256_text(
            _stable_json(sigma_cond.tolist())
        ),
    }
    return sigma_cond, meta

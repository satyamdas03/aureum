"""Differentiable certifiable portfolio optimizer for Aureum (Edge 6).

This module implements a JAX-based, gradient-trained allocation policy that
still emits the same content-addressed Aureum Backtest Certificate as the
classical MPT objectives.  The MVP supports a single differentiable Sharpe
objective backed by a small per-asset MLP.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jax
import jax.numpy as jnp
import numpy as np
import optax
import yaml

from aureum.mpt import _project_box_constraints


@dataclass
class ArchitectureSpec:
    """Parsed model architecture file for a differentiable strategy."""

    input_features: list[str]
    hidden_units: list[int]
    activation: str
    dropout: float
    output_temperature: float

    @classmethod
    def from_yaml(cls, path: str | Path) -> ArchitectureSpec:
        """Load an architecture specification from a YAML file."""
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        activation = data.get("activation", "softplus")
        if activation not in {"softplus", "tanh", "relu"}:
            raise ValueError(
                f"unsupported activation '{activation}'; "
                "supported values: softplus, tanh, relu"
            )
        hidden_units = data.get("hidden_units", [64, 32])
        if not isinstance(hidden_units, list) or not all(
            isinstance(u, int) and u > 0 for u in hidden_units
        ):
            raise ValueError("hidden_units must be a list of positive integers")
        return cls(
            input_features=list(data.get("input_features", [])),
            hidden_units=hidden_units,
            activation=activation,
            dropout=float(data.get("dropout", 0.0)),
            output_temperature=float(data.get("output_temperature", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable dict representation used for hashing/debugging."""
        return {
            "input_features": self.input_features,
            "hidden_units": self.hidden_units,
            "activation": self.activation,
            "dropout": self.dropout,
            "output_temperature": self.output_temperature,
        }


@dataclass
class DiffoptResult:
    """Result bundle returned by ``DifferentiableSharpeOptimizer.train_and_backtest``."""

    weights_hash: str
    train_hash: str
    val_hash: str
    test_hash: str
    backtest_result: Any = None


class DifferentiableSharpeOptimizer:
    """Train a small MLP to maximize out-of-sample Sharpe ratio, then backtest it.

    The optimizer is deterministic: the JAX PRNG key is seeded from the SHA-256
    of the strategy YAML, the architecture file, and the training split CSV.  The
    resulting weights and each data split are content-addressed so that the
    Aureum Backtest Certificate can record the full learned lineage.
    """

    _FEATURE_FUNCS: dict[str, str] = {
        "mean_return_252d": "mean_return",
        "volatility_252d": "volatility",
        "momentum_12_1": "momentum",
    }

    def __init__(
        self,
        strategy: Any,
        data: Any,
        strategy_path: Path | None = None,
    ) -> None:
        self.strategy = strategy
        self.data = data
        self.strategy_path = strategy_path

        base_dir = (
            _find_repo_root(Path(strategy_path)) if strategy_path else Path.cwd()
        )

        portfolio = strategy.portfolio()
        if portfolio is None or portfolio.get("objective") != "differentiable_sharpe":
            raise ValueError(
                "DifferentiableSharpeOptimizer requires spec.portfolio.objective "
                "== 'differentiable_sharpe'"
            )

        self.portfolio_spec = portfolio
        self.model_spec = portfolio.get("model", {})
        self.training_spec = portfolio.get("training", {})

        arch_path = base_dir / self.model_spec["architecture_file"]
        self.architecture = ArchitectureSpec.from_yaml(arch_path)
        self.architecture_path = arch_path.resolve()
        self.architecture_hash = _sha256_file(arch_path)

        weights_file = self.model_spec.get("weights_file")
        self.weights_file_path = (
            (base_dir / weights_file).resolve() if weights_file else None
        )

        self.lookback_days = int(self.portfolio_spec.get("lookback_days", 252))
        self.long_only = bool(self.portfolio_spec.get("long_only", True))
        self.max_weight = self.portfolio_spec.get("max_weight")
        self.min_weight = self.portfolio_spec.get("min_weight")
        self.temperature = float(self.architecture.output_temperature)

        self.learning_rate = float(self.training_spec["learning_rate"])
        self.epochs = int(self.training_spec["epochs"])
        self.batch_size = int(self.training_spec.get("batch_size", 16))
        self.l2_penalty = float(self.training_spec.get("l2_penalty", 0.0))
        self.max_weight_penalty = float(
            self.training_spec.get("max_weight_penalty", 0.0)
        )
        self.patience = int(self.training_spec.get("early_stopping_patience", 20))
        self.train_end = dt.date.fromisoformat(self.training_spec["train_end"])
        self.val_end = dt.date.fromisoformat(self.training_spec["val_end"])

        self._validate_dates()

        # Data splits and hashes (computed once).
        self._split_rows = self._split_data_rows()
        self.split_hashes = {
            name: _sha256_bytes(_csv_bytes(rows))
            for name, rows in self._split_rows.items()
        }

        # PRNG seeded from strategy + architecture + train split for reproducibility.
        strategy_bytes = _read_bytes(Path(strategy_path)) if strategy_path else b""
        arch_bytes = _read_bytes(self.architecture_path)
        train_bytes = _csv_bytes(self._split_rows["train"])
        seed_material = strategy_bytes + arch_bytes + train_bytes
        seed = int.from_bytes(
            hashlib.sha256(seed_material).digest()[:4], byteorder="big"
        )
        self._rng_key = jax.random.PRNGKey(seed)

        # Computed during training.
        self._params: Any = None
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None
        self._trained = False
        self.weights_hash = ""
        self.weights_path: Path | None = None

    @classmethod
    def from_strategy(
        cls,
        strategy: Any,
        data: Any,
        strategy_path: str | Path | None = None,
    ) -> DifferentiableSharpeOptimizer:
        """Build an optimizer from a parsed strategy and market data."""
        return cls(
            strategy,
            data,
            strategy_path=Path(strategy_path) if strategy_path else None,
        )

    def _validate_dates(self) -> None:
        last_date = self.data.dates[-1]
        if self.train_end >= self.val_end:
            raise ValueError(
                f"spec.portfolio.training.train_end ({self.train_end}) "
                f"must be strictly before val_end ({self.val_end})"
            )
        if self.val_end >= last_date:
            raise ValueError(
                f"spec.portfolio.training.val_end ({self.val_end}) "
                f"must be strictly before the last data date ({last_date})"
            )

    def _split_data_rows(self) -> dict[str, list[dict[str, Any]]]:
        """Return deterministic CSV row lists for train/val/test splits."""
        rows: list[dict[str, Any]] = []
        for symbol in self.data.symbols:
            for rec in self.data._by_symbol.get(symbol, []):
                rows.append(
                    {
                        "date": rec["date"].isoformat(),
                        "symbol": symbol,
                        "close": rec["close"],
                        "volume": rec["volume"],
                        "sector": rec.get("sector", ""),
                    }
                )
        rows.sort(key=lambda r: (r["date"], r["symbol"]))

        def _split(row: dict[str, Any]) -> str:
            d = dt.date.fromisoformat(row["date"])
            if d <= self.train_end:
                return "train"
            if d <= self.val_end:
                return "val"
            return "test"

        return {
            "train": [r for r in rows if _split(r) == "train"],
            "val": [r for r in rows if _split(r) == "val"],
            "test": [r for r in rows if _split(r) == "test"],
        }

    def _rebalance_dates(self) -> list[dt.date]:
        """Return the first trading day of each month after the warm-up period."""
        dates = self.data.dates
        if len(dates) <= self.lookback_days:
            return []
        eligible = dates[self.lookback_days :]
        rebalance_dates: list[dt.date] = []
        prev_month: tuple[int, int] | None = None
        for date in eligible:
            month_key = (date.year, date.month)
            if month_key != prev_month:
                rebalance_dates.append(date)
                prev_month = month_key
        return rebalance_dates

    def _eligible_symbols(self, date: dt.date) -> list[str]:
        """Apply the strategy universe filters at a single date."""
        universe_spec = self.strategy.spec.get("universe", {})
        filters = universe_spec.get("filter", {})
        sector_filter = filters.get("sector")
        min_price = filters.get("min_price")
        min_adv20 = filters.get("min_adv20")

        eligible: list[str] = []
        for symbol in self.data.symbols:
            if sector_filter and self.data.sector(symbol) != sector_filter:
                continue
            price = self.data.price(date, symbol)
            if price is None:
                continue
            if min_price is not None and price < min_price:
                continue
            if min_adv20 is not None:
                adv = self._adv20(date, symbol)
                if adv is None or adv < min_adv20:
                    continue
            eligible.append(symbol)
        return eligible

    def _adv20(self, date: dt.date, symbol: str) -> float | None:
        """Trailing 20-trading-day average dollar volume."""
        records = self.data._by_symbol.get(symbol, [])
        idx = next(
            (i for i, rec in enumerate(records) if rec["date"] == date), None
        )
        if idx is None or idx < 19:
            return None
        window = records[idx - 19 : idx + 1]
        return sum(rec["close"] * rec["volume"] for rec in window) / len(window)

    def _build_features(
        self, date: dt.date, symbols: list[str]
    ) -> tuple[np.ndarray, list[str]]:
        """Compute standardized feature matrix for ``symbols`` at ``date``."""
        feats: list[list[float]] = []
        valid_symbols: list[str] = []
        for symbol in symbols:
            closes = self.data.closes_up_to(date, symbol)
            if len(closes) < self.lookback_days + 1:
                continue
            window = closes[-(self.lookback_days + 1) :]
            rets = [
                window[i] / window[i - 1] - 1.0
                for i in range(1, len(window))
            ]
            mean_ret = sum(rets) / len(rets)
            variance = sum((r - mean_ret) ** 2 for r in rets) / (len(rets) - 1)
            std = math.sqrt(variance) if variance > 0 else 0.0
            vol = std * math.sqrt(252)
            mom = (window[-1] / window[-252] - 1.0) - (
                window[-1] / window[-22] - 1.0
            )
            feats.append([mean_ret, vol, mom])
            valid_symbols.append(symbol)
        return np.asarray(feats, dtype=float), valid_symbols

    def _next_date(self, date: dt.date) -> dt.date | None:
        """Return the next trading date after ``date`` in the data calendar."""
        dates = self.data.dates
        idx = dates.index(date) if date in dates else None
        if idx is None or idx + 1 >= len(dates):
            return None
        return dates[idx + 1]

    def _next_day_returns(
        self, date: dt.date, symbols: list[str]
    ) -> np.ndarray | None:
        """Compute the vector of next-day simple returns for ``symbols``."""
        next_date = self._next_date(date)
        if next_date is None:
            return None
        rets: list[float] = []
        for symbol in symbols:
            p0 = self.data.price(date, symbol)
            p1 = self.data.price(next_date, symbol)
            if p0 is None or p1 is None or p0 <= 0:
                return None
            rets.append(p1 / p0 - 1.0)
        return np.asarray(rets, dtype=float)

    def _mlp_forward(self, params: Any, x: jnp.ndarray) -> jnp.ndarray:
        """Forward pass returning one logit per asset row in ``x``."""
        out = x
        for layer in params["hidden"]:
            out = jnp.dot(out, layer["W"]) + layer["b"]
            if self.architecture.activation == "softplus":
                out = jax.nn.softplus(out)
            elif self.architecture.activation == "tanh":
                out = jnp.tanh(out)
            else:
                out = jax.nn.relu(out)
        logits = jnp.dot(out, params["output"]["W"]) + params["output"]["b"]
        return jnp.squeeze(logits, axis=-1)

    def _init_params(self) -> Any:
        """Xavier-uniform initialization with the deterministic PRNG key."""
        key = self._rng_key
        keys = jax.random.split(key, len(self.architecture.hidden_units) + 2)
        in_dim = len(self.architecture.input_features)
        hidden = self.architecture.hidden_units

        param_layers: list[dict[str, jnp.ndarray]] = []
        prev = in_dim
        for i, h in enumerate(hidden):
            limit = math.sqrt(6.0 / (prev + h))
            W = jax.random.uniform(keys[i], (prev, h), minval=-limit, maxval=limit)
            b = jnp.zeros((h,))
            param_layers.append({"W": W, "b": b})
            prev = h

        limit = math.sqrt(6.0 / (prev + 1))
        W_out = jax.random.uniform(keys[-2], (prev, 1), minval=-limit, maxval=limit)
        b_out = jnp.zeros((1,))

        return {"hidden": param_layers, "output": {"W": W_out, "b": b_out}}

    def _load_seed_weights(self) -> Any:
        """Load the optional ``weights_file`` as the initial parameter tree."""
        if self.weights_file_path is None or not self.weights_file_path.exists():
            return None
        raw = dict(np.load(self.weights_file_path))
        hidden: list[dict[str, jnp.ndarray]] = []
        for i in range(len(self.architecture.hidden_units)):
            W = jnp.asarray(raw[f"layer{i}/W"])
            b = jnp.asarray(raw[f"layer{i}/b"])
            hidden.append({"W": W, "b": b})
        out_W = jnp.asarray(raw["output/W"])
        out_b = jnp.asarray(raw["output/b"])
        return {"hidden": hidden, "output": {"W": out_W, "b": out_b}}

    def _save_weights(self, params: Any, weights_dir: Path) -> Path:
        """Persist ``params`` to an ``.npz`` file and return its path."""
        weights_dir = Path(weights_dir)
        weights_dir.mkdir(parents=True, exist_ok=True)
        path = weights_dir / "trained_weights.npz"
        arrays: dict[str, np.ndarray] = {}
        for i, layer in enumerate(params["hidden"]):
            arrays[f"layer{i}/W"] = np.asarray(layer["W"])
            arrays[f"layer{i}/b"] = np.asarray(layer["b"])
        arrays["output/W"] = np.asarray(params["output"]["W"])
        arrays["output/b"] = np.asarray(params["output"]["b"])
        np.savez(path, **arrays)  # type: ignore[arg-type]
        return path

    def _prepare_batches(
        self, dates: list[dt.date]
    ) -> tuple[list[jnp.ndarray], list[jnp.ndarray]]:
        """Build (features, next-day returns) pairs for the given rebalance dates."""
        features: list[jnp.ndarray] = []
        returns: list[jnp.ndarray] = []
        for date in dates:
            candidates = self._eligible_symbols(date)
            X, symbols = self._build_features(date, candidates)
            rets = self._next_day_returns(date, symbols)
            if X.shape[0] < 2 or rets is None:
                continue
            features.append(jnp.asarray(X, dtype=jnp.float32))
            returns.append(jnp.asarray(rets, dtype=jnp.float32))
        return features, returns

    def train(self, weights_dir: str | Path | None = None) -> None:
        """Train the MLP on the train split and validate on the val split."""
        if self._trained:
            return

        rebalance_dates = self._rebalance_dates()
        train_dates = [d for d in rebalance_dates if d <= self.train_end]
        val_dates = [
            d for d in rebalance_dates if self.train_end < d <= self.val_end
        ]
        if len(train_dates) < 2:
            raise ValueError(
                f"insufficient training rebalance dates: {len(train_dates)}"
            )
        if len(val_dates) < 1:
            raise ValueError(
                f"insufficient validation rebalance dates: {len(val_dates)}"
            )

        train_features, train_returns = self._prepare_batches(train_dates)
        val_features, val_returns = self._prepare_batches(val_dates)
        if not train_features or not val_features:
            raise ValueError("could not build any training/validation batches")

        # Standardize features using training-split statistics.
        flat = jnp.concatenate(train_features, axis=0)
        self._feature_mean = np.asarray(jnp.mean(flat, axis=0))
        self._feature_std = np.asarray(jnp.std(flat, axis=0) + 1e-8)

        def _standardize(x_list: list[jnp.ndarray]) -> list[jnp.ndarray]:
            mean = jnp.asarray(self._feature_mean)
            std = jnp.asarray(self._feature_std)
            return [(x - mean) / std for x in x_list]

        train_features = _standardize(train_features)
        val_features = _standardize(val_features)

        # Loss function: negative Sharpe + L2 + soft max-weight penalty.
        @jax.jit
        def loss_fn(params, xs, rs):
            per_date_rets = []
            all_weights: list[jnp.ndarray] = []
            for x, r in zip(xs, rs, strict=True):
                logits = self._mlp_forward(params, x)
                w = jax.nn.softmax(logits / self.temperature)
                per_date_rets.append(jnp.dot(w, r))
                all_weights.append(w)
            port_rets = jnp.stack(per_date_rets)
            sharpe = jnp.mean(port_rets) / (jnp.std(port_rets) + 1e-8)
            l2 = self.l2_penalty * sum(
                jnp.sum(p * p) for p in jax.tree_util.tree_leaves(params)
            )
            max_pen = 0.0
            if self.max_weight is not None and self.max_weight_penalty > 0:
                all_w = jnp.concatenate(all_weights)
                max_pen = jnp.mean(jnp.maximum(all_w - self.max_weight, 0.0))
            return -sharpe + l2 + self.max_weight_penalty * max_pen

        @jax.jit
        def val_sharpe_fn(params, xs, rs):
            per_date_rets = []
            for x, r in zip(xs, rs, strict=True):
                logits = self._mlp_forward(params, x)
                w = jax.nn.softmax(logits / self.temperature)
                per_date_rets.append(jnp.dot(w, r))
            port_rets = jnp.stack(per_date_rets)
            return jnp.mean(port_rets) / (jnp.std(port_rets) + 1e-8)

        params = self._load_seed_weights() or self._init_params()
        optimizer = optax.adam(self.learning_rate)
        opt_state = optimizer.init(params)

        best_params = params
        best_val_sharpe = float("-inf")
        patience_counter = 0

        for epoch in range(self.epochs):
            loss, grads = jax.value_and_grad(loss_fn)(
                params, train_features, train_returns
            )
            updates, opt_state = optimizer.update(grads, opt_state)
            params = optax.apply_updates(params, updates)

            val_sharpe = float(val_sharpe_fn(params, val_features, val_returns))
            if val_sharpe > best_val_sharpe + 1e-8:
                best_val_sharpe = val_sharpe
                best_params = params
                patience_counter = 0
            else:
                patience_counter += 1

            if patience_counter >= self.patience:
                break

        self._params = best_params
        self._trained = True

        if weights_dir is not None:
            self.weights_path = self._save_weights(best_params, Path(weights_dir))
        else:
            import tempfile

            tmp_dir = Path(tempfile.mkdtemp(prefix="aureum_diffopt_"))
            self.weights_path = self._save_weights(best_params, tmp_dir)

        self.weights_hash = _sha256_file(self.weights_path)

    def weights_for_date(
        self, date: dt.date, candidates: list[str]
    ) -> tuple[dict[str, float], dict[str, Any]]:
        """Return projected portfolio weights for ``candidates`` at ``date``."""
        if not self._trained:
            raise RuntimeError("weights requested before training")
        X, symbols = self._build_features(date, candidates)
        if X.shape[0] < 2:
            return {}, {
                "objective": "differentiable_sharpe",
                "error": "insufficient assets with required lookback",
                "eligible_count": X.shape[0],
            }

        X_std = (X - self._feature_mean) / self._feature_std
        logits = self._mlp_forward(self._params, jnp.asarray(X_std))
        w = np.asarray(jax.nn.softmax(logits / self.temperature))
        w = _project_box_constraints(
            w,
            long_only=self.long_only,
            max_weight=self.max_weight,
            min_weight=self.min_weight,
        )

        weights_dict = {symbol: float(w[i]) for i, symbol in enumerate(symbols)}
        meta = {
            "objective": "differentiable_sharpe",
            "eligible_count": len(symbols),
            "weights": {
                symbol: round(weights_dict[symbol], 6) for symbol in symbols
            },
        }
        return weights_dict, meta

    def train_and_backtest(
        self, weights_dir: str | Path | None = None
    ) -> DiffoptResult:
        """Train the model and run the test-split backtest."""
        self.train(weights_dir=weights_dir)

        from aureum.backtest import BacktestRunner

        runner = BacktestRunner(
            self.strategy,
            self.data,
            data_source=str(self.strategy_path) if self.strategy_path else "csv",
            initial_nav=1_000_000.0,
        )
        runner._diffopt = self
        backtest_result = runner.run()
        return DiffoptResult(
            weights_hash=self.weights_hash,
            train_hash=self.split_hashes["train"],
            val_hash=self.split_hashes["val"],
            test_hash=self.split_hashes["test"],
            backtest_result=backtest_result,
        )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def _sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Render rows to a deterministic CSV and return its UTF-8 bytes."""
    if not rows:
        return b""
    keys = sorted(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row[k] for k in keys})
    return buf.getvalue().encode("utf-8")


def _find_repo_root(path: Path) -> Path:
    """Walk upward from ``path`` until a ``.git`` file or directory is found."""
    current = path.resolve()
    if current.is_file():
        current = current.parent
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback to the strategy file's parent if no git root is found.
    return path.parent if path.is_file() else path

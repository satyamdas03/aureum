"""Neuro-symbolic alpha DSL (Edge 4).

Provides a deterministic, whitelist Lisp-style formula language over OHLCV
bars.  Formulas are parsed into an auditable AST, safety-checked, and
evaluated with NumPy vector primitives.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np

from .ai import AnthropicClient


@dataclass
class AlphaSpec:
    """Configuration for a neuro-symbolic alpha signal."""

    name: str
    formula: str
    generation: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlphaSpec:
        return cls(
            name=data.get("name", "alpha"),
            formula=data.get("formula", ""),
            generation=data.get("generation", {}),
        )


@dataclass
class AlphaAst:
    """Node in a parsed neuro-symbolic alpha formula."""

    name: str
    args: list[AlphaAst] = field(default_factory=list)
    value: float | None = None

    def is_literal(self) -> bool:
        return self.value is not None

    def is_variable(self) -> bool:
        return not self.args and self.value is None and self.name in {"close", "volume"}

    def is_call(self) -> bool:
        return bool(self.args) or self.name in AlphaGrammar().primitives

    def evaluate(self, closes: list[float], volumes: list[int]) -> np.ndarray:
        """Evaluate the AST to a full-length NumPy array."""
        return AlphaGrammar().evaluate(self, closes, volumes)


@dataclass
class SafetyReport:
    """Result of a neuro-symbolic alpha safety audit."""

    safe: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class AlphaResult:
    """Result of an LLM alpha-mining attempt."""

    formula: str
    rationale: str = ""


class AlphaGrammar:
    """Registry of deterministic primitives for the alpha DSL."""

    variables: ClassVar[set[str]] = {"close", "volume"}

    # Primitives whose numeric argument is a lookback window.
    window_primitives: ClassVar[set[str]] = {
        "returns",
        "lag",
        "sma",
        "ema",
        "volatility",
        "momentum",
        "zscore",
        "rsi",
        "ts_argmax",
        "ts_argmin",
        "dollar_volume",
        "vwma",
    }

    # Primitives where numeric literals are allowed as thresholds or selectors.
    threshold_primitives: ClassVar[set[str]] = {
        "gt",
        "gte",
        "lt",
        "lte",
        "eq",
        "if_else",
    }

    def __init__(self) -> None:
        self.primitives: dict[str, Callable[..., np.ndarray]] = {
            "close": self._close,
            "volume": self._volume,
            "returns": self._returns,
            "lag": self._lag,
            "sma": self._sma,
            "ema": self._ema,
            "volatility": self._volatility,
            "momentum": self._momentum,
            "zscore": self._zscore,
            "rsi": self._rsi,
            "ts_argmax": self._ts_argmax,
            "ts_argmin": self._ts_argmin,
            "dollar_volume": self._dollar_volume,
            "vwma": self._vwma,
            "add": lambda *args: args[0] + args[1],
            "sub": lambda *args: args[0] - args[1],
            "mul": lambda *args: args[0] * args[1],
            "div": lambda *args: _safe_div(args[0], args[1]),
            "neg": lambda *args: -args[0],
            "gt": lambda *args: (args[0] > args[1]).astype(float),
            "gte": lambda *args: (args[0] >= args[1]).astype(float),
            "lt": lambda *args: (args[0] < args[1]).astype(float),
            "lte": lambda *args: (args[0] <= args[1]).astype(float),
            "eq": lambda *args: (args[0] == args[1]).astype(float),
            "if_else": lambda *args: np.where(args[0] != 0, args[1], args[2]),
        }

    # ---------- parsing -------------------------------------------------

    @staticmethod
    def parse(formula: str) -> tuple[AlphaAst | None, str | None]:
        """Parse a formula string into an AST.

        Returns ``(ast, None)`` on success or ``(None, error_message)``.
        """
        try:
            tokens = _tokenize(formula)
        except ValueError as exc:
            return None, str(exc)
        if not tokens:
            return None, "empty formula"
        try:
            ast, pos = _parse_expr(tokens, 0)
        except ValueError as exc:
            return None, str(exc)
        if pos != len(tokens):
            return None, f"unexpected token '{tokens[pos]}' after parsed expression"
        return ast, None

    # ---------- evaluation ---------------------------------------------

    def evaluate(
        self,
        ast: AlphaAst,
        closes: list[float],
        volumes: list[int],
    ) -> np.ndarray:
        """Evaluate an AST against full series and return an array."""
        ctx = {"closes": closes, "volumes": volumes}
        return self._eval(ast, ctx)

    def _eval(self, ast: AlphaAst, ctx: dict[str, Any]) -> np.ndarray:
        if ast.is_literal():
            arr = np.full(len(ctx["closes"]), ast.value, dtype=float)
            return arr
        if ast.name in self.variables and not ast.args:
            if ast.name == "close":
                return np.asarray(ctx["closes"], dtype=float)
            if ast.name == "volume":
                return np.asarray(ctx["volumes"], dtype=float)
        if ast.name not in self.primitives:
            raise ValueError(f"unknown primitive: {ast.name}")
        arg_arrays = [self._eval(arg, ctx) for arg in ast.args]
        return self.primitives[ast.name](*arg_arrays)

    # ---------- primitive implementations -------------------------------

    @staticmethod
    def _close(closes: np.ndarray) -> np.ndarray:
        return closes

    @staticmethod
    def _volume(volumes: np.ndarray) -> np.ndarray:
        return volumes

    @staticmethod
    def _returns(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("returns window must be positive")
        if len(series) <= window:
            return np.full_like(series, np.nan)
        out = np.full_like(series, np.nan)
        out[window:] = series[window:] / series[:-window] - 1.0
        return out

    @staticmethod
    def _lag(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        offset = round(float(n[-1]))
        if offset < 0:
            raise ValueError("lag offset must be non-negative")
        if offset == 0:
            return series.copy()
        out = np.full_like(series, np.nan)
        if offset < len(series):
            out[offset:] = series[:-offset]
        return out

    @staticmethod
    def _sma(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("sma window must be positive")
        if len(series) < window:
            return np.full_like(series, np.nan)
        out = np.full_like(series, np.nan)
        weights = np.ones(window) / window
        out[window - 1 :] = np.convolve(series, weights, mode="valid")
        return out

    @staticmethod
    def _ema(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("ema window must be positive")
        if len(series) < window:
            return np.full_like(series, np.nan)
        alpha = 2.0 / (window + 1.0)
        out = np.full_like(series, np.nan)
        out[window - 1] = np.mean(series[:window])
        for i in range(window, len(series)):
            out[i] = alpha * series[i] + (1.0 - alpha) * out[i - 1]
        return out

    @staticmethod
    def _volatility(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 1:
            raise ValueError("volatility window must be > 1")
        rets = np.full_like(series, np.nan)
        rets[1:] = series[1:] / series[:-1] - 1.0
        out = np.full_like(series, np.nan)
        for i in range(window, len(series)):
            out[i] = np.std(rets[i - window + 1 : i + 1], ddof=1) * math.sqrt(252)
        return out

    @staticmethod
    def _momentum(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("momentum window must be positive")
        out = np.full_like(series, np.nan)
        if window < len(series):
            out[window:] = series[window:] / series[:-window] - 1.0
        return out

    @staticmethod
    def _zscore(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 1:
            raise ValueError("zscore window must be > 1")
        out = np.full_like(series, np.nan)
        for i in range(window - 1, len(series)):
            w = series[i - window + 1 : i + 1]
            mean = np.mean(w)
            std = np.std(w, ddof=1)
            out[i] = (series[i] - mean) / std if std > 0 else 0.0
        return out

    @staticmethod
    def _rsi(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 1:
            raise ValueError("rsi window must be > 1")
        rets = np.full_like(series, np.nan)
        rets[1:] = series[1:] - series[:-1]
        gains = np.where(rets > 0, rets, 0.0)
        losses = np.where(rets < 0, -rets, 0.0)
        avg_gain = np.full_like(series, np.nan)
        avg_loss = np.full_like(series, np.nan)
        if len(series) > window:
            avg_gain[window] = np.mean(gains[1 : window + 1])
            avg_loss[window] = np.mean(losses[1 : window + 1])
            for i in range(window + 1, len(series)):
                avg_gain[i] = (avg_gain[i - 1] * (window - 1) + gains[i]) / window
                avg_loss[i] = (avg_loss[i - 1] * (window - 1) + losses[i]) / window
        rs = _safe_div(avg_gain, avg_loss)
        out = 100.0 - (100.0 / (1.0 + rs))
        return out

    @staticmethod
    def _ts_argmax(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("ts_argmax window must be positive")
        out = np.full_like(series, np.nan)
        for i in range(window - 1, len(series)):
            out[i] = float(np.argmax(series[i - window + 1 : i + 1]))
        return out

    @staticmethod
    def _ts_argmin(series: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("ts_argmin window must be positive")
        out = np.full_like(series, np.nan)
        for i in range(window - 1, len(series)):
            out[i] = float(np.argmin(series[i - window + 1 : i + 1]))
        return out

    @staticmethod
    def _dollar_volume(close: np.ndarray, volume: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("dollar_volume window must be positive")
        dv = close * volume
        out = np.full_like(dv, np.nan)
        weights = np.ones(window) / window
        if len(dv) >= window:
            out[window - 1 :] = np.convolve(dv, weights, mode="valid")
        return out

    @staticmethod
    def _vwma(close: np.ndarray, volume: np.ndarray, n: np.ndarray) -> np.ndarray:
        window = round(float(n[-1]))
        if window <= 0:
            raise ValueError("vwma window must be positive")
        numerator = close * volume
        out = np.full_like(close, np.nan)
        for i in range(window - 1, len(close)):
            out[i] = np.sum(numerator[i - window + 1 : i + 1]) / np.sum(
                volume[i - window + 1 : i + 1]
            )
        return out


# ---------- helpers -----------------------------------------------------


def _safe_div(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(b) > 1e-12, a / b, 0.0)
    return out


def _tokenize(formula: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    s = formula.strip()
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c in "(),":
            tokens.append(c)
            i += 1
            continue
        # number (supports underscores for readability)
        if c.isdigit() or (c == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            j = i
            while j < len(s) and (s[j].isdigit() or s[j] in "._"):
                j += 1
            tokens.append(s[i:j])
            i = j
            continue
        # identifier
        if c.isalpha() or c == "_":
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            tokens.append(s[i:j])
            i = j
            continue
        raise ValueError(f"unexpected character '{c}' at position {i}")
    return tokens


def _parse_expr(tokens: list[str], pos: int) -> tuple[AlphaAst, int]:
    if pos >= len(tokens):
        raise ValueError("unexpected end of formula")
    token = tokens[pos]

    # numeric literal
    if _is_number(token):
        value = float(token.replace("_", ""))
        return AlphaAst(name=token, value=value), pos + 1

    name = token
    if name in AlphaGrammar.variables and (pos + 1 >= len(tokens) or tokens[pos + 1] != "("):
        return AlphaAst(name=name), pos + 1

    # function call
    if pos + 1 >= len(tokens) or tokens[pos + 1] != "(":
        raise ValueError(f"expected '(' after '{name}' at position {pos}")
    pos += 2  # consume name and '('

    args: list[AlphaAst] = []
    if pos < len(tokens) and tokens[pos] == ")":
        return AlphaAst(name=name, args=args), pos + 1

    while True:
        arg, pos = _parse_expr(tokens, pos)
        args.append(arg)
        if pos >= len(tokens):
            raise ValueError(f"missing ')' for call to '{name}'")
        if tokens[pos] == ")":
            pos += 1
            break
        if tokens[pos] == ",":
            pos += 1
            continue
        raise ValueError(f"expected ',' or ')' in call to '{name}', got '{tokens[pos]}'")

    return AlphaAst(name=name, args=args), pos


def _is_number(token: str) -> bool:
    try:
        float(token.replace("_", ""))
        return True
    except ValueError:
        return False


# ---------- safety checker ---------------------------------------------


def _window_arg_index(primitive: str) -> int:
    """Return the argument index that holds the lookback window."""
    if primitive in {"dollar_volume", "vwma"}:
        return 2
    return 1


def safety_check(ast: AlphaAst, formula: str = "") -> SafetyReport:
    """Audit an AST for whitelist, look-ahead, stochastic, and data-leakage rules."""
    failures: list[str] = []
    _check_node(ast, parent=None, arg_index=-1, failures=failures)
    return SafetyReport(safe=not failures, failures=failures)


def _check_node(
    ast: AlphaAst,
    parent: AlphaAst | None,
    arg_index: int,
    failures: list[str],
) -> None:
    if ast.is_literal():
        # Structural constants are numeric literals used outside of a window or
        # threshold context.  We allow numeric literals as windows for rolling
        # primitives and as thresholds inside comparison / if_else nodes.
        if parent is None:
            failures.append(f"top-level numeric literal: {ast.name}")
            return
        if parent.name in AlphaGrammar.window_primitives and arg_index == _window_arg_index(parent.name):
            return
        if parent.name in AlphaGrammar.threshold_primitives:
            return
        failures.append(f"structural constant: {ast.name}")
        return

    if ast.is_variable():
        return

    grammar = AlphaGrammar()
    if ast.name not in grammar.primitives:
        failures.append(f"unknown function/variable: {ast.name}")
        return

    # Look-ahead guard: lag/returns/sma/etc. must use non-negative windows.
    if ast.name in AlphaGrammar.window_primitives:
        window_idx = _window_arg_index(ast.name)
        if len(ast.args) <= window_idx:
            failures.append(f"'{ast.name}' requires a window argument")
            return
        window_arg = ast.args[window_idx]
        if window_arg.is_literal():
            window = window_arg.value
            if window is None or window < 0:
                failures.append(f"'{ast.name}' window must be non-negative")
                return
            if ast.name in {"sma", "ema", "volatility", "zscore", "rsi"} and window < 1:
                failures.append(f"'{ast.name}' window must be at least 1")
        elif not window_arg.is_literal():
            failures.append(f"'{ast.name}' window must be a constant literal")

    for idx, child in enumerate(ast.args):
        _check_node(child, parent=ast, arg_index=idx, failures=failures)


# ---------- LLM miner ---------------------------------------------------


class AlphaMiner:
    """LLM-driven generator for neuro-symbolic alpha formulas."""

    def __init__(self, model: str = "claude-sonnet-5") -> None:
        self.client = AnthropicClient(model=model)
        self.model = model

    def generate(
        self,
        *,
        prompt: str,
        strategy_name: str = "alpha_strategy",
        max_tokens: int = 4096,
    ) -> AlphaResult:
        """Ask the LLM for a safe, deterministic alpha formula."""
        full_prompt = _alpha_prompt(prompt)
        try:
            text = self.client.complete(full_prompt, max_tokens=max_tokens)
        except Exception as exc:  # pragma: no cover - LLM/network failures  # noqa: BLE001
            return AlphaResult(formula="", rationale=f"LLM call failed: {exc}")

        formula = _extract_formula(text)
        if not formula:
            return AlphaResult(
                formula="",
                rationale="No formula found in LLM response",
            )

        ast, parse_error = AlphaGrammar.parse(formula)
        if parse_error or ast is None:
            return AlphaResult(
                formula="",
                rationale=f"Generated formula could not be parsed: {parse_error}",
            )
        report = safety_check(ast, formula=formula)
        if not report.safe:
            return AlphaResult(
                formula="",
                rationale=f"Generated formula failed safety checks: {report.failures}",
            )

        return AlphaResult(formula=formula, rationale=f"Generated for {strategy_name}")


def _extract_formula(text: str) -> str:
    """Pull a Lisp-style formula out of an LLM response."""
    import re

    # fenced formula block
    match = re.search(r"```(?:formula|alpha)?\n(.*?)\n```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if "(" in candidate:
            return candidate
    # bare formula on a line
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("(") and ")" in stripped:
            return stripped
    # first line that contains a primitive call
    primitive_names = set(AlphaGrammar().primitives.keys())
    for line in text.splitlines():
        if any(p in line for p in primitive_names):
            return line.strip()
    return ""


def _alpha_prompt(user_prompt: str) -> str:
    primitives = ", ".join(sorted(AlphaGrammar().primitives.keys()))
    return (
        "You are an alpha researcher for the Aureum Quant Kernel. "
        "Write a single deterministic, Lisp-style alpha formula using only the "
        "whitelist primitives below.  Do not invent functions.  Do not use "
        "future data or stochastic primitives.  Use comparisons and if_else "
        "for conditional logic; numeric thresholds are allowed.\n\n"
        f"Available primitives: {primitives}\n\n"
        "Return ONLY the formula, optionally inside a ```formula fenced block.\n\n"
        f"Prompt: {user_prompt}\n\nFormula:"
    )

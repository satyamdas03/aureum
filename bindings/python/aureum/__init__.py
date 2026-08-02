"""Aureum — self-proving semantic kernel for finance.

This is the Python developer API. The performance-critical execution engine
will be backed by the Rust `aureum-core` crate via PyO3; the pure-Python
implementation below is the MVP scaffolding.
"""

from __future__ import annotations

import pathlib
import tomllib

from .backtest import BacktestRunner, MarketData
from .certificate import (
    BacktestCertificate,
    Environment,
    ExecutionSummary,
    InputLineage,
    Inputs,
    Results,
    get_environment,
    hash_file,
)
from .dag import Dag, Node
from .econsec import EconomicSecurityReport, audit_economic_security
from .quantity import Dimension, Quantity, Unit
from .strategy import Strategy
from .verifier import verify_constraints


def _read_version() -> str:
    """Read the package version from pyproject.toml at import time."""
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
        return str(data.get("project", {}).get("version", "0.4.0"))
    return "0.4.1"


__version__ = _read_version()

__all__ = [
    "BacktestCertificate",
    "BacktestRunner",
    "Dag",
    "Dimension",
    "EconomicSecurityReport",
    "Environment",
    "ExecutionSummary",
    "InputLineage",
    "Inputs",
    "MarketData",
    "Node",
    "Quantity",
    "Results",
    "Strategy",
    "Unit",
    "__version__",
    "audit_economic_security",
    "get_environment",
    "hash_file",
    "verify_constraints",
]

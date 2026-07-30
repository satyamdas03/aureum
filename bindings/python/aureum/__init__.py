"""Aureum — self-proving semantic kernel for finance.

This is the Python developer API. The performance-critical execution engine
will be backed by the Rust `aureum-core` crate via PyO3; the pure-Python
implementation below is the MVP scaffolding.
"""

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
from .quantity import Dimension, Quantity, Unit
from .strategy import Strategy
from .verifier import verify_constraints

__all__ = [
    "BacktestCertificate",
    "BacktestRunner",
    "Dag",
    "Dimension",
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
    "get_environment",
    "hash_file",
    "verify_constraints",
]

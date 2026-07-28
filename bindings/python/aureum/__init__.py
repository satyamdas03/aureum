"""Aureum — self-proving semantic kernel for finance.

This is the Python developer API. The performance-critical execution engine
will be backed by the Rust `aureum-core` crate via PyO3; the pure-Python
implementation below is the MVP scaffolding.
"""

from .dag import Dag, Node
from .quantity import Dimension, Quantity, Unit
from .strategy import Strategy

__all__ = ["Strategy", "Quantity", "Unit", "Dimension", "Dag", "Node"]

"""Smoke tests for the Aureum strategy DSL parser."""

from pathlib import Path

from aureum.strategy import Strategy


EXAMPLE = Path(__file__).parents[3] / "examples" / "strategies" / "momentum.yaml"


def test_parse_sample_strategy():
    strategy = Strategy.from_file(EXAMPLE)
    assert strategy.metadata["name"] == "tech-momentum-sector-neutral"
    assert strategy.spec["schedule"]["rebalance"] == "1M"
    assert len(strategy.spec["signals"]) == 1


def test_validate_sample_strategy():
    strategy = Strategy.from_file(EXAMPLE)
    errors = strategy.validate()
    assert errors == []


def test_constraints_extracted():
    strategy = Strategy.from_file(EXAMPLE)
    constraints = strategy.constraints()
    names = {c["name"] for c in constraints}
    assert "max_drawdown" in names
    assert "max_leverage" in names

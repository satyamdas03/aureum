"""Smoke tests for the Aureum Python MVP."""

from aureum.quantity import Dimension, Quantity, Unit


def test_dimensionless_quantity():
    q = Quantity.dimensionless(42.0, "test")
    assert q.value == 42.0
    assert str(q.unit) == "1"


def test_adding_compatible_quantities():
    usd = Unit.base(Dimension("USD"))
    a = Quantity(100.0, usd, "a")
    b = Quantity(50.0, usd, "b")
    c = a.add(b)
    assert c.value == 150.0
    assert c.unit == usd


def test_adding_incompatible_quantities_raises():
    usd = Unit.base(Dimension("USD"))
    eur = Unit.base(Dimension("EUR"))
    a = Quantity(100.0, usd, "a")
    b = Quantity(50.0, eur, "b")
    try:
        a.add(b)
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "dimension mismatch" in str(e)


def test_multiplying_units():
    usd = Unit.base(Dimension("USD"))
    share = Unit.base(Dimension("share"))
    position = usd.multiply(share)
    assert str(position) == "USD * share"


def test_dividing_units():
    usd = Unit.base(Dimension("USD"))
    share = Unit.base(Dimension("share"))
    price = usd.divide(share)
    assert str(price) == "USD / share"

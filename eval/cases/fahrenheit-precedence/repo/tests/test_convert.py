import pytest

from weather.convert import celsius_to_fahrenheit, fahrenheit_to_celsius
from weather.forecast import describe


def test_boiling_point():
    assert fahrenheit_to_celsius(212) == pytest.approx(100)


def test_freezing_point():
    assert fahrenheit_to_celsius(32) == pytest.approx(0)


def test_celsius_to_fahrenheit():
    assert celsius_to_fahrenheit(100) == pytest.approx(212)


def test_forecast_text():
    assert describe("Leeds", 50) == "Leeds: high of 10.0°C"

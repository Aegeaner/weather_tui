"""Tests for unit conversion, WMO helpers and rendered output."""

from __future__ import annotations

import pytest

from weather_tui.render import IMPERIAL, METRIC, render_current, render_daily, render_hourly
from weather_tui.wmo import compass, describe


def test_temperature_wind_precipitation_and_visibility_conversion():
    assert IMPERIAL.temperature(0.0) == pytest.approx(32.0)
    assert IMPERIAL.temperature(100.0) == pytest.approx(212.0)
    assert IMPERIAL.wind(100.0) == pytest.approx(62.1371, rel=1e-4)
    assert IMPERIAL.precipitation(25.4) == pytest.approx(1.0)
    assert IMPERIAL.visibility(1609.344) == pytest.approx(1.0)

    assert METRIC.temperature(20.0) == pytest.approx(20.0)
    assert METRIC.wind(20.0) == pytest.approx(20.0)
    assert METRIC.precipitation(2.0) == pytest.approx(2.0)
    assert METRIC.visibility(1500.0) == pytest.approx(1.5)

    for value in (None,):
        assert METRIC.temperature(value) is None
        assert IMPERIAL.temperature(value) is None
        assert IMPERIAL.wind(value) is None
        assert IMPERIAL.precipitation(value) is None
        assert IMPERIAL.visibility(value) is None


def test_describe_handles_known_unknown_and_none():
    assert describe(0) == ("\u2600", "Clear sky")
    assert describe(61)[1] == "Light rain"
    assert describe(None) == ("\u2013", "Unknown")
    assert describe(1234) == ("?", "Code 1234")


def test_compass_rounds_to_sixteen_points():
    assert compass(0) == "N"
    assert compass(90) == "E"
    assert compass(225) == "SW"
    assert compass(359) == "N"
    assert compass(None) == "\u2013"


def test_render_current_shows_place_model_and_units(forecast, flatten):
    text = flatten(render_current(forecast, METRIC))
    assert "Dublin, Ireland" in text
    assert "ECMWF IFS HRES (9 km, native)" in text
    assert "\u00b0C" in text
    assert "Wind" in text and "Sunrise" in text
    assert "Unknown" not in text  # weather code 0 is resolved


def test_render_tables_reflect_unit_system(forecast, flatten):
    metric = flatten(render_hourly(forecast, METRIC, count=24))
    assert "Hourly \u2014 next 24 h" in metric
    assert "°C" in metric and "km/h" in metric
    assert "UV" not in metric

    imperial = flatten(render_hourly(forecast, IMPERIAL, count=24))
    assert "°F" in imperial and "mph" in imperial

    daily_metric = flatten(render_daily(forecast, METRIC))
    assert "Daily \u2014 4 days" in daily_metric
    assert "07:35" in daily_metric and "18:45" in daily_metric
    # ecmwf_ifs returns no UV values, so the column must be omitted entirely.
    assert "UV" not in daily_metric

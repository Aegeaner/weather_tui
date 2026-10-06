"""Shared fixtures: a synthetic Open-Meteo payload shaped like a real response."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
from rich.console import Console

from weather_tui.api import DUBLIN, parse_forecast


@pytest.fixture
def flatten():
    """Render any Rich renderable to plain text (no colour, fixed width)."""

    def _flatten(renderable, width: int = 140) -> str:
        console = Console(width=width, record=True, color_system=None)
        console.print(renderable)
        return console.export_text()

    return _flatten


def build_payload(*, n_hours: int = 72, n_days: int = 4) -> dict:
    """Build a payload whose hourly times straddle 'now' by three hours."""
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=3
    )
    times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n_hours)]

    hourly: dict[str, object] = {
        "time": times,
        "temperature_2m": [10.0 + 0.5 * i for i in range(n_hours)],
        "apparent_temperature": [9.0 + 0.5 * i for i in range(n_hours)],
        "relative_humidity_2m": [80.0] * n_hours,
        "dew_point_2m": [8.0] * n_hours,
        "precipitation": [0.2 * (i % 3) for i in range(n_hours)],
        "rain": [0.2 * (i % 3) for i in range(n_hours)],
        "showers": [0.0] * n_hours,
        "snowfall": [0.0] * n_hours,
        "precipitation_probability": [(i * 7) % 100 for i in range(n_hours)],
        "weather_code": [[0, 1, 2, 3, 61][i % 5] for i in range(n_hours)],
        "cloud_cover": [50.0] * n_hours,
        "pressure_msl": [1013.0] * n_hours,
        "wind_speed_10m": [12.0] * n_hours,
        "wind_direction_10m": [225.0] * n_hours,
        "wind_gusts_10m": [25.0] * n_hours,
        "visibility": [20000.0] * n_hours,
        "boundary_layer_height": [500.0] * n_hours,
    }

    dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n_days)]
    daily = {
        "time": dates,
        "weather_code": [61] * n_days,
        "temperature_2m_max": [15.0] * n_days,
        "temperature_2m_min": [7.0] * n_days,
        "apparent_temperature_max": [14.0] * n_days,
        "precipitation_sum": [3.2] * n_days,
        "rain_sum": [3.0] * n_days,
        "showers_sum": [0.2] * n_days,
        "snowfall_sum": [0.0] * n_days,
        "precipitation_hours": [5.0] * n_days,
        "precipitation_probability_max": [80.0] * n_days,
        "wind_speed_10m_max": [30.0] * n_days,
        "wind_gusts_10m_max": [55.0] * n_days,
        "wind_direction_10m_dominant": [240.0] * n_days,
        "sunrise": [f"{d}T07:35" for d in dates],
        "sunset": [f"{d}T18:45" for d in dates],
        "daylight_duration": [40000.0] * n_days,
        # The 9 km IFS model does not produce UV; the API returns nulls.
        "uv_index_max": [None] * n_days,
    }

    return {
        "latitude": 53.3498,
        "longitude": -6.2603,
        "generationtime_ms": 0.5,
        "utc_offset_seconds": 0,
        "timezone": "UTC",
        "timezone_abbreviation": "UTC",
        "elevation": 11.0,
        "hourly": hourly,
        "daily": daily,
    }


@pytest.fixture
def payload() -> dict:
    return build_payload()


@pytest.fixture
def forecast(payload: dict):
    return parse_forecast(DUBLIN, copy.deepcopy(payload), model="ecmwf_ifs")

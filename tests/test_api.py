"""Tests for parsing, cache behaviour and HTTP error handling."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from weather_tui.api import (
    DUBLIN,
    OpenMeteoError,
    Place,
    ResponseCache,
    fetch_forecast,
    geocode,
    parse_forecast,
)


def test_parse_forecast_maps_every_field(forecast):
    assert forecast.timezone == "UTC"
    assert forecast.utc_offset_seconds == 0
    assert forecast.elevation == 11.0
    assert forecast.place is DUBLIN

    assert len(forecast.hours) == 72
    first = forecast.hours[0]
    assert first.temperature == pytest.approx(10.0)
    assert first.apparent_temperature == pytest.approx(9.0)
    assert first.weather_code == 0
    assert first.precipitation_probability == 0
    assert first.wind_direction == pytest.approx(225.0)
    assert first.visibility == pytest.approx(20000.0)

    assert len(forecast.days) == 4
    day = forecast.days[0]
    assert day.temperature_min == pytest.approx(7.0)
    assert day.temperature_max == pytest.approx(15.0)
    assert day.precipitation_sum == pytest.approx(3.2)
    assert day.uv_index_max is None
    assert day.sunrise is not None and (day.sunrise.hour, day.sunrise.minute) == (7, 35)


def test_parse_forecast_tolerates_missing_columns():
    payload = {
        "hourly": {"time": ["2026-01-01T00:00", "2026-01-01T01:00"]},
        "daily": {"time": []},
    }
    forecast = parse_forecast(DUBLIN, payload)
    assert len(forecast.hours) == 2
    assert forecast.hours[0].temperature is None
    assert forecast.hours[0].weather_code is None
    assert forecast.days == ()


def test_parse_forecast_skips_unparsable_timestamps():
    payload = {"hourly": {"time": ["not-a-time", "2026-01-01T00:00"]}, "daily": {"time": []}}
    forecast = parse_forecast(DUBLIN, payload)
    # API timestamps are naive local wall-clock values.
    assert [h.time.isoformat() for h in forecast.hours] == ["2026-01-01T00:00:00"]


def test_current_index_boundaries(forecast):
    hours = forecast.hours
    assert forecast.current_index(hours[0].time - timedelta(hours=5)) == 0
    assert forecast.current_index(hours[0].time) == 0
    assert forecast.current_index(hours[10].time) == 10
    assert forecast.current_index(hours[10].time + timedelta(minutes=30)) == 10
    assert forecast.current_index(hours[-1].time + timedelta(hours=9)) == len(hours) - 1


def test_cache_expires_and_survives_corruption(tmp_path):
    now = [1000.0]
    cache = ResponseCache(tmp_path, ttl=10.0, clock=lambda: now[0])

    cache.put("key", {"value": 1})
    assert cache.get("key") == {"value": 1}

    now[0] += 9.0
    assert cache.get("key") == {"value": 1}

    now[0] += 2.0
    assert cache.get("key") is None

    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert cache.get("broken") is None
    assert cache.get("never-written") is None


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_forecast_sends_ecmwf_ifs_and_parses():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "latitude": 53.3498,
                "longitude": -6.2603,
                "elevation": 11.0,
                "utc_offset_seconds": 0,
                "timezone": "UTC",
                "hourly": {"time": ["2026-01-01T00:00"]},
                "daily": {"time": []},
            },
        )

    forecast = fetch_forecast(DUBLIN, days=30, client=_client(handler))
    assert seen["models"] == "ecmwf_ifs"
    assert seen["forecast_days"] == "16"  # clamped to the API maximum
    assert "temperature_2m" in seen["hourly"]
    assert forecast.model == "ecmwf_ifs"


def test_fetch_forecast_raises_on_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": True, "reason": "bad latitude"})

    with pytest.raises(OpenMeteoError, match="bad latitude"):
        fetch_forecast(DUBLIN, client=_client(handler))


def test_fetch_forecast_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="unavailable")

    with pytest.raises(httpx.HTTPStatusError):
        fetch_forecast(DUBLIN, client=_client(handler))


def test_geocode_builds_places_and_handles_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["name"] == "Dublin"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "Dublin",
                        "latitude": 53.3498,
                        "longitude": -6.2603,
                        "country": "Ireland",
                        "admin1": "Leinster",
                    }
                ]
            },
        )

    places = geocode("Dublin", client=_client(handler))
    assert places == [Place("Dublin", 53.3498, -6.2603, "Ireland", "Leinster")]
    assert places[0].label() == "Dublin, Leinster, Ireland"

    empty = geocode("Nowhere", client=_client(lambda r: httpx.Response(200, json={})))
    assert empty == []

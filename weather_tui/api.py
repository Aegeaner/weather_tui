"""Open-Meteo ECMWF IFS forecast client, response cache and parsing.

Uses the generic forecast endpoint with ``models=ecmwf_ifs``, which serves the
full-resolution ECMWF IFS HRES forecast (native ~9 km, reduced Gaussian grid
O1280) that ECMWF moved to open data on 2025-10-01.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path
from typing import Any

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

DEFAULT_MODEL = "ecmwf_ifs"
MAX_FORECAST_DAYS = 16
USER_AGENT = "weather-tui/0.1 (+https://open-meteo.com)"

MODEL_LABELS = {
    "ecmwf_ifs": "ECMWF IFS HRES (9 km, native)",
    "ecmwf_ifs025": "ECMWF IFS open-data (0.25°)",
    "ecmwf_aifs025_single": "ECMWF AIFS single (0.25°)",
    "best_match": "Open-Meteo best match",
}

# Order matters: it is the order of the values returned by the API.
HOURLY_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "rain",
    "showers",
    "snowfall",
    "precipitation_probability",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "visibility",
    "boundary_layer_height",
)

# ``uv_index_max`` is not produced by the 9 km IFS model; it is requested but
# rendered only when at least one value is present (e.g. with --model best_match).
DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_sum",
    "rain_sum",
    "showers_sum",
    "snowfall_sum",
    "precipitation_hours",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "sunrise",
    "sunset",
    "daylight_duration",
    "uv_index_max",
)


class OpenMeteoError(RuntimeError):
    """Raised when the API returns an error payload or unusable data."""


@dataclass(frozen=True)
class Place:
    """A named geographic location."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    admin1: str | None = None

    def label(self) -> str:
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts)


DUBLIN = Place("Dublin", 53.3498, -6.2603, country="Ireland")


@dataclass(frozen=True)
class Hour:
    """One forecast hour (local wall-clock time)."""

    time: datetime
    temperature: float | None = None
    apparent_temperature: float | None = None
    relative_humidity: float | None = None
    dew_point: float | None = None
    precipitation: float | None = None
    rain: float | None = None
    showers: float | None = None
    snowfall: float | None = None
    precipitation_probability: float | None = None
    weather_code: int | None = None
    cloud_cover: float | None = None
    pressure_msl: float | None = None
    wind_speed: float | None = None
    wind_direction: float | None = None
    wind_gusts: float | None = None
    visibility: float | None = None
    boundary_layer_height: float | None = None


@dataclass(frozen=True)
class Day:
    """One forecast day (local dates)."""

    date: date_type
    weather_code: int | None = None
    temperature_max: float | None = None
    temperature_min: float | None = None
    apparent_temperature_max: float | None = None
    precipitation_sum: float | None = None
    rain_sum: float | None = None
    showers_sum: float | None = None
    snowfall_sum: float | None = None
    precipitation_hours: float | None = None
    precipitation_probability_max: float | None = None
    wind_speed_max: float | None = None
    wind_gusts_max: float | None = None
    wind_direction_dominant: float | None = None
    sunrise: datetime | None = None
    sunset: datetime | None = None
    daylight_duration: float | None = None
    uv_index_max: float | None = None


@dataclass(frozen=True)
class Forecast:
    """A parsed Open-Meteo forecast response."""

    place: Place
    latitude: float
    longitude: float
    elevation: float | None
    timezone: str
    utc_offset_seconds: int
    model: str
    fetched_at: datetime
    hours: tuple[Hour, ...]
    days: tuple[Day, ...]

    def local_now(self) -> datetime:
        """Current wall-clock time at the forecast location (naive)."""
        utc_now = datetime.now(dt_timezone.utc).replace(tzinfo=None)
        return utc_now + timedelta(seconds=self.utc_offset_seconds)

    def current_index(self, now: datetime | None = None) -> int:
        """Index of the last hour at or before ``now`` (0 if none)."""
        now = now or self.local_now()
        index = 0
        for i, hour in enumerate(self.hours):
            if hour.time <= now:
                index = i
            else:
                break
        return index

    def current_hour(self, now: datetime | None = None) -> Hour | None:
        if not self.hours:
            return None
        return self.hours[self.current_index(now)]


# --------------------------------------------------------------------------- #
# Caching
# --------------------------------------------------------------------------- #


def default_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base) / "weather-tui"


class ResponseCache:
    """Tiny JSON-on-disk cache with a time-to-live."""

    def __init__(
        self,
        directory: Path | str,
        ttl: float = 3600.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.directory = Path(directory)
        self.ttl = float(ttl)
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    @staticmethod
    def make_key(url: str, params: dict[str, Any]) -> str:
        blob = json.dumps({"url": url, "params": params}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            age = self._clock() - float(stored["stored_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if age > self.ttl:
            return None
        payload = stored.get("payload")
        return payload if isinstance(payload, dict) else None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            tmp = self._path(key).with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"stored_at": self._clock(), "payload": payload}),
                encoding="utf-8",
            )
            tmp.replace(self._path(key))
        except OSError:
            pass  # A cache miss is never fatal.


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        transport=httpx.HTTPTransport(retries=3),
    )


def _request_json(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
    cache: ResponseCache | None,
) -> dict[str, Any]:
    key = ResponseCache.make_key(url, params) if cache is not None else ""
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    response = client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise OpenMeteoError("Unexpected response from Open-Meteo API")
    if data.get("error"):
        raise OpenMeteoError(str(data.get("reason") or "Unknown Open-Meteo error"))
    if cache is not None:
        cache.put(key, data)
    return data


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #


def _column(block: dict[str, Any], name: str, length: int) -> list[Any]:
    values = block.get(name)
    if not isinstance(values, list):
        return [None] * length
    if len(values) < length:
        return list(values) + [None] * (length - len(values))
    return list(values[:length])


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_forecast(
    place: Place,
    payload: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    fetched_at: datetime | None = None,
) -> Forecast:
    """Turn a raw forecast payload into a :class:`Forecast`."""
    hourly_block = payload.get("hourly") or {}
    hourly_times = hourly_block.get("time") or []
    if not isinstance(hourly_times, list):
        raise OpenMeteoError("Malformed 'hourly.time' in response")
    n_hours = len(hourly_times)

    cols = {name: _column(hourly_block, name, n_hours) for name in HOURLY_VARIABLES}
    hours: list[Hour] = []
    for i, raw_time in enumerate(hourly_times):
        moment = _datetime(raw_time)
        if moment is None:
            continue
        hours.append(
            Hour(
                time=moment,
                temperature=_number(cols["temperature_2m"][i]),
                apparent_temperature=_number(cols["apparent_temperature"][i]),
                relative_humidity=_number(cols["relative_humidity_2m"][i]),
                dew_point=_number(cols["dew_point_2m"][i]),
                precipitation=_number(cols["precipitation"][i]),
                rain=_number(cols["rain"][i]),
                showers=_number(cols["showers"][i]),
                snowfall=_number(cols["snowfall"][i]),
                precipitation_probability=_number(cols["precipitation_probability"][i]),
                weather_code=_integer(cols["weather_code"][i]),
                cloud_cover=_number(cols["cloud_cover"][i]),
                pressure_msl=_number(cols["pressure_msl"][i]),
                wind_speed=_number(cols["wind_speed_10m"][i]),
                wind_direction=_number(cols["wind_direction_10m"][i]),
                wind_gusts=_number(cols["wind_gusts_10m"][i]),
                visibility=_number(cols["visibility"][i]),
                boundary_layer_height=_number(cols["boundary_layer_height"][i]),
            )
        )

    daily_block = payload.get("daily") or {}
    daily_times = daily_block.get("time") or []
    daily_cols = {name: _column(daily_block, name, len(daily_times)) for name in DAILY_VARIABLES}
    days: list[Day] = []
    for i, raw_date in enumerate(daily_times):
        day = _datetime(raw_date)
        if day is None:
            continue
        days.append(
            Day(
                date=day.date(),
                weather_code=_integer(daily_cols["weather_code"][i]),
                temperature_max=_number(daily_cols["temperature_2m_max"][i]),
                temperature_min=_number(daily_cols["temperature_2m_min"][i]),
                apparent_temperature_max=_number(daily_cols["apparent_temperature_max"][i]),
                precipitation_sum=_number(daily_cols["precipitation_sum"][i]),
                rain_sum=_number(daily_cols["rain_sum"][i]),
                showers_sum=_number(daily_cols["showers_sum"][i]),
                snowfall_sum=_number(daily_cols["snowfall_sum"][i]),
                precipitation_hours=_number(daily_cols["precipitation_hours"][i]),
                precipitation_probability_max=_number(
                    daily_cols["precipitation_probability_max"][i]
                ),
                wind_speed_max=_number(daily_cols["wind_speed_10m_max"][i]),
                wind_gusts_max=_number(daily_cols["wind_gusts_10m_max"][i]),
                wind_direction_dominant=_number(daily_cols["wind_direction_10m_dominant"][i]),
                sunrise=_datetime(daily_cols["sunrise"][i]),
                sunset=_datetime(daily_cols["sunset"][i]),
                daylight_duration=_number(daily_cols["daylight_duration"][i]),
                uv_index_max=_number(daily_cols["uv_index_max"][i]),
            )
        )

    return Forecast(
        place=place,
        latitude=float(payload.get("latitude", place.latitude)),
        longitude=float(payload.get("longitude", place.longitude)),
        elevation=_number(payload.get("elevation")),
        timezone=str(payload.get("timezone") or "UTC"),
        utc_offset_seconds=int(payload.get("utc_offset_seconds") or 0),
        model=model,
        fetched_at=fetched_at or datetime.now(dt_timezone.utc),
        hours=tuple(hours),
        days=tuple(days),
    )


# --------------------------------------------------------------------------- #
# Public requests
# --------------------------------------------------------------------------- #


def fetch_forecast(
    place: Place,
    *,
    days: int = 7,
    model: str = DEFAULT_MODEL,
    timezone: str = "auto",
    cache: ResponseCache | None = None,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> Forecast:
    """Fetch and parse a forecast for ``place``."""
    days = max(1, min(int(days), MAX_FORECAST_DAYS))
    params = {
        "latitude": round(float(place.latitude), 6),
        "longitude": round(float(place.longitude), 6),
        "hourly": ",".join(HOURLY_VARIABLES),
        "daily": ",".join(DAILY_VARIABLES),
        "models": model,
        "forecast_days": days,
        "timezone": timezone,
    }
    owns_client = client is None
    client = client or make_client(timeout)
    try:
        payload = _request_json(client, FORECAST_URL, params, cache)
    finally:
        if owns_client:
            client.close()
    return parse_forecast(place, payload, model=model)


def geocode(
    name: str,
    *,
    count: int = 5,
    language: str = "en",
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> list[Place]:
    """Look up locations by name via the Open-Meteo geocoding API."""
    params = {
        "name": name,
        "count": max(1, min(int(count), 100)),
        "language": language,
        "format": "json",
    }
    owns_client = client is None
    client = client or make_client(timeout)
    try:
        payload = _request_json(client, GEOCODING_URL, params, None)
    finally:
        if owns_client:
            client.close()
    results = payload.get("results") or []
    places: list[Place] = []
    for item in results:
        try:
            places.append(
                Place(
                    name=str(item.get("name") or name),
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                    country=item.get("country"),
                    admin1=item.get("admin1"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return places

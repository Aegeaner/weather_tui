"""WMO weather-code descriptions and wind-direction helpers."""

from __future__ import annotations

# WMO 4677 weather codes used by Open-Meteo.  Symbol first, short text second.
WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("\u2600", "Clear sky"),
    1: ("\U0001f324", "Mainly clear"),
    2: ("\u26c5", "Partly cloudy"),
    3: ("\u2601", "Overcast"),
    45: ("\U0001f32b", "Fog"),
    48: ("\U0001f32b", "Rime fog"),
    51: ("\U0001f326", "Light drizzle"),
    53: ("\U0001f326", "Drizzle"),
    55: ("\U0001f326", "Dense drizzle"),
    56: ("\U0001f327", "Freezing drizzle"),
    57: ("\U0001f327", "Freezing drizzle"),
    61: ("\U0001f327", "Light rain"),
    63: ("\U0001f327", "Rain"),
    65: ("\U0001f327", "Heavy rain"),
    66: ("\U0001f327", "Freezing rain"),
    67: ("\U0001f327", "Freezing rain"),
    71: ("\U0001f328", "Light snow"),
    73: ("\U0001f328", "Snow"),
    75: ("\U0001f328", "Heavy snow"),
    77: ("\u2744", "Snow grains"),
    80: ("\U0001f326", "Light showers"),
    81: ("\U0001f326", "Showers"),
    82: ("\u26c8", "Violent showers"),
    85: ("\U0001f328", "Snow showers"),
    86: ("\U0001f328", "Heavy snow showers"),
    95: ("\u26c8", "Thunderstorm"),
    96: ("\u26c8", "Thunderstorm, hail"),
    99: ("\u26c8", "Thunderstorm, heavy hail"),
}

_COMPASS = (
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
)


def describe(code: int | None) -> tuple[str, str]:
    """Return (symbol, description) for a WMO code; tolerate unknown/None."""
    if code is None:
        return ("\u2013", "Unknown")
    try:
        return WMO_CODES[int(code)]
    except (KeyError, TypeError, ValueError):
        return ("?", f"Code {code}")


def compass(degrees: float | None) -> str:
    """Return a 16-point compass direction for a bearing in degrees."""
    if degrees is None:
        return "\u2013"
    index = int((float(degrees) % 360) / 22.5 + 0.5) % 16
    return _COMPASS[index]

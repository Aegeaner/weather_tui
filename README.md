# weather-tui

A terminal weather-forecast TUI written in Python against the [Open-Meteo](https://open-meteo.com/)
API, using the **ECMWF IFS HRES** model at its full native ~9 km resolution.

Since ECMWF moved to open data on 2025-10-01, Open-Meteo serves the native-resolution IFS HRES
forecast on the reduced Gaussian grid O1280 (model id `ecmwf_ifs`) with no extra dissemination
delay, under the CC-BY 4.0 licence. This tool requests that model explicitly.

* Default location: **Dublin, Ireland** (`53.3498, -6.2603`) — override with `--city` or `--lat/--lon`.
* Forecast horizon: 1–16 days, current hour highlighted, next 24 hourly rows by default.
* Metric/imperial units, auto-refresh, on-disk response cache, retries with backoff.
* Interactive TUI built with [Textual](https://textual.textualize.io/); tables rendered with Rich.

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e .          # runtime dependencies: httpx, textual
```

Requires Python 3.10+.

## Usage

```bash
weather-tui                                   # Dublin, 7 days
weather-tui --city Cork                       # geocode any place name
weather-tui --lat 52.52 --lon 13.41           # explicit coordinates
weather-tui --days 14 --units imperial        # 14-day imperial forecast
weather-tui --model ecmwf_ifs025 --no-cache   # 0.25° open-data IFS, no cache
```

Full option list:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--city NAME` | — | Geocode a place name (Open-Meteo geocoding API). |
| `--lat DEG`, `--lon DEG` | Dublin | Explicit coordinates (must be given together). |
| `--days N` | `7` | Forecast length, 1–16. |
| `--model ID` | `ecmwf_ifs` | Open-Meteo model (`ecmwf_ifs` is native 9 km IFS HRES). |
| `--units {metric,imperial}` | `metric` | °C/km-h/mm or °F/mph/inch. |
| `--refresh SECONDS` | `900` | Auto-refresh interval, `0` disables. |
| `--hourly-rows N` | `24` | Number of hourly rows shown. |
| `--timezone TZ` | `auto` | Timezone for timestamps. |
| `--cache-ttl SECONDS` | `3600` | Response cache lifetime. |
| `--no-cache` | — | Disable the on-disk cache. |

### Keys

| Key | Action |
| --- | --- |
| `q` / `Ctrl+C` | Quit |
| `r` | Refresh now (bypasses the cache) |
| `u` | Toggle metric/imperial units |
| `+` / `=` | One more forecast day |
| `-` | One fewer forecast day |
| `↑` `↓` `PgUp` `PgDn` | Scroll the forecast |

## Data source

Requests go to the Open-Meteo generic forecast endpoint:

```
https://api.open-meteo.com/v1/forecast?models=ecmwf_ifs&...
```

Hourly variables: temperature, apparent temperature, humidity, dew point, precipitation
(rain/showers/snowfall), precipitation probability, weather code, cloud cover, mean sea-level
pressure, wind speed/direction/gusts, visibility and boundary-layer height. Daily variables:
weather code, min/max and apparent temperature, precipitation sums/hours/probability, max wind
and gusts, dominant direction, sunrise, sunset and daylight duration. `uv_index_max` is requested
but the 9 km IFS model does not produce it, so the column is omitted unless the data is present.

Data © ECMWF / Open-Meteo, CC-BY 4.0. This tool is an independent client and is not affiliated
with Open-Meteo.

## Architecture

```
weather_tui/
├── api.py      # HTTP client, on-disk TTL cache, payload parsing, dataclasses
├── wmo.py      # WMO weather-code descriptions and compass directions
├── render.py   # Units + pure Rich renderers (current panel, hourly/daily tables)
├── app.py      # Textual application: layout, key bindings, refresh worker
└── __main__.py # argparse CLI, location resolution, entry point
```

Rendering is a pure function of a parsed `Forecast`, so it is unit-testable without a terminal.
Network access runs in a worker thread and never blocks the UI.

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests are fully offline: they use a synthetic API payload plus `httpx.MockTransport`, and the TUI
tests drive the real app headlessly through Textual's test pilot.

## Licence

This code base is released under the [MIT Licence](LICENSE). Forecast data is provided by ECMWF
and Open-Meteo under the CC-BY 4.0 licence.

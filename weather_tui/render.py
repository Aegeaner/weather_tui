"""Pure renderers: units, current-conditions panel, hourly and daily tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .api import MODEL_LABELS, Forecast, Hour
from .wmo import compass, describe

MISSING = "\u2013"


@dataclass(frozen=True)
class Units:
    """Unit system plus conversions from Open-Meteo metric base values."""

    key: str
    temperature_symbol: str
    wind_symbol: str
    precipitation_symbol: str
    visibility_symbol: str

    @property
    def is_metric(self) -> bool:
        return self.key == "metric"

    def temperature(self, celsius: float | None) -> float | None:
        if celsius is None:
            return None
        return celsius if self.is_metric else celsius * 9.0 / 5.0 + 32.0

    def wind(self, kmh: float | None) -> float | None:
        if kmh is None:
            return None
        return kmh if self.is_metric else kmh * 0.621371

    def precipitation(self, mm: float | None) -> float | None:
        if mm is None:
            return None
        return mm if self.is_metric else mm / 25.4

    def visibility(self, meters: float | None) -> float | None:
        if meters is None:
            return None
        return meters / 1000.0 if self.is_metric else meters / 1609.344


METRIC = Units("metric", "\u00b0C", "km/h", "mm", "km")
IMPERIAL = Units("imperial", "\u00b0F", "mph", "in", "mi")
UNIT_SYSTEMS = {"metric": METRIC, "imperial": IMPERIAL}


def _num(value: float | None, digits: int = 1, missing: str = MISSING) -> str:
    if value is None:
        return missing
    return f"{value:.{digits}f}"


def _int(value: float | None, missing: str = MISSING) -> str:
    if value is None:
        return missing
    return f"{value:.0f}"


def _clock(value: datetime | None) -> str:
    return value.strftime("%H:%M") if value else MISSING


def render_current(fc: Forecast, units: Units, *, now: datetime | None = None) -> RenderableType:
    """Top panel: location, model and the current hour."""
    now = now or fc.local_now()
    hour = fc.current_hour(now)
    model_label = MODEL_LABELS.get(fc.model, fc.model)

    lines: list[RenderableType] = []

    head = Text()
    head.append(fc.place.label(), style="bold cyan")
    head.append(
        f"   {fc.latitude:.3f}\u00b0, {fc.longitude:.3f}\u00b0   "
        f"{_int(fc.elevation, '?')} m asl   {fc.timezone}"
    )
    lines.append(head)

    sub = Text()
    sub.append(model_label, style="magenta")
    sub.append(f"   local {now:%a %d %b %H:%M}")
    sub.append(f"   fetched {fc.fetched_at.astimezone().strftime('%H:%M:%S')}", style="dim")
    lines.append(sub)

    if hour is None:
        lines.append(Text(""))
        lines.append(Text("No hourly data available for this location.", style="yellow"))
        return Panel(Group(*lines), title="[b]Now[/b]", border_style="cyan")

    symbol, description = describe(hour.weather_code)
    lines.append(Text(""))
    headline = Text()
    headline.append(f"{symbol}  ", style="bold yellow")
    headline.append(
        f"{_num(units.temperature(hour.temperature))} {units.temperature_symbol}", style="bold"
    )
    headline.append(
        f"   feels like {_num(units.temperature(hour.apparent_temperature))} "
        f"{units.temperature_symbol}"
    )
    headline.append(f"   {description}", style="bold")
    lines.append(headline)
    lines.append(Text(""))

    today = next((d for d in fc.days if d.date == now.date()), None)

    details = Table.grid(padding=(0, 3))
    details.add_column(justify="left")
    details.add_column(justify="left")
    wind = (
        f"{_num(units.wind(hour.wind_speed), 0)} {units.wind_symbol} "
        f"{compass(hour.wind_direction)} ({_int(hour.wind_direction, '?')}\u00b0)"
    )
    details.add_row(
        Text.from_markup(f"[b]Wind[/b]      {wind}"),
        Text.from_markup(
            f"[b]Gusts[/b]     {_num(units.wind(hour.wind_gusts), 0)} {units.wind_symbol}"
        ),
    )
    details.add_row(
        Text.from_markup(f"[b]Humidity[/b]  {_int(hour.relative_humidity, '?')} %"),
        Text.from_markup(
            f"[b]Dew point[/b] {_num(units.temperature(hour.dew_point))} {units.temperature_symbol}"
        ),
    )
    details.add_row(
        Text.from_markup(f"[b]Cloud[/b]     {_int(hour.cloud_cover, '?')} %"),
        Text.from_markup(f"[b]Pressure[/b]  {_num(hour.pressure_msl, 0)} hPa"),
    )
    details.add_row(
        Text.from_markup(
            f"[b]Precip[/b]    {_num(units.precipitation(hour.precipitation), 1)} "
            f"{units.precipitation_symbol} "
            f"({_int(hour.precipitation_probability, '?')} %)"
        ),
        Text.from_markup(
            f"[b]Visibility[/b] "
            f"{_num(units.visibility(hour.visibility), 1)} {units.visibility_symbol}"
        ),
    )
    if today is not None:
        details.add_row(
            Text.from_markup(f"[b]Sunrise[/b]   {_clock(today.sunrise)}"),
            Text.from_markup(f"[b]Sunset[/b]    {_clock(today.sunset)}"),
        )
    lines.append(details)

    return Panel(Group(*lines), title="[b]Now[/b]", border_style="cyan")


def render_hourly(
    fc: Forecast,
    units: Units,
    *,
    now: datetime | None = None,
    count: int = 24,
) -> RenderableType:
    """Table of the next ``count`` hours starting at the current hour."""
    now = now or fc.local_now()
    start = fc.current_index(now)
    hours: tuple[Hour, ...] = fc.hours[start : start + max(0, count)]

    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold",
        title=f"Hourly \u2014 next {len(hours)} h",
        title_justify="left",
        expand=False,
    )
    table.add_column("Time", no_wrap=True)
    table.add_column("Weather", no_wrap=True)
    table.add_column(f"Temp\n{units.temperature_symbol}", justify="right")
    table.add_column(f"Feels\n{units.temperature_symbol}", justify="right")
    table.add_column(f"Precip\n{units.precipitation_symbol}", justify="right")
    table.add_column("PoP\n%", justify="right")
    table.add_column(f"Wind\n{units.wind_symbol}", justify="right")
    table.add_column(f"Gust\n{units.wind_symbol}", justify="right")
    table.add_column("Hum\n%", justify="right")

    for hour in hours:
        symbol, description = describe(hour.weather_code)
        table.add_row(
            hour.time.strftime("%a %H:%M"),
            f"{symbol} {description}",
            _num(units.temperature(hour.temperature)),
            _num(units.temperature(hour.apparent_temperature)),
            _num(units.precipitation(hour.precipitation)),
            _int(hour.precipitation_probability),
            f"{_int(units.wind(hour.wind_speed))} {compass(hour.wind_direction)}",
            _int(units.wind(hour.wind_gusts)),
            _int(hour.relative_humidity),
        )
    return table


def render_daily(fc: Forecast, units: Units) -> RenderableType:
    """Table of daily forecasts."""
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold",
        title=f"Daily \u2014 {len(fc.days)} days",
        title_justify="left",
        expand=False,
    )
    table.add_column("Day", no_wrap=True)
    table.add_column("Weather", no_wrap=True)
    table.add_column(f"Min\n{units.temperature_symbol}", justify="right")
    table.add_column(f"Max\n{units.temperature_symbol}", justify="right")
    table.add_column(f"Precip\n{units.precipitation_symbol}", justify="right")
    table.add_column("PoP\n%", justify="right")
    table.add_column(f"Wind\n{units.wind_symbol}", justify="right")
    table.add_column(f"Gust\n{units.wind_symbol}", justify="right")
    table.add_column("Sunrise", justify="right")
    table.add_column("Sunset", justify="right")

    show_uv = any(day.uv_index_max is not None for day in fc.days)
    if show_uv:
        table.add_column("UV", justify="right")

    for day in fc.days:
        symbol, description = describe(day.weather_code)
        row = [
            day.date.strftime("%a %d %b"),
            f"{symbol} {description}",
            _num(units.temperature(day.temperature_min)),
            _num(units.temperature(day.temperature_max)),
            _num(units.precipitation(day.precipitation_sum)),
            _int(day.precipitation_probability_max),
            _int(units.wind(day.wind_speed_max)),
            _int(units.wind(day.wind_gusts_max)),
            _clock(day.sunrise),
            _clock(day.sunset),
        ]
        if show_uv:
            row.append(_num(day.uv_index_max, 1))
        table.add_row(*row)
    return table

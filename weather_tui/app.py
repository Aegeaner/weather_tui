"""Textual application: live weather forecast in the terminal."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static

from .api import (
    DEFAULT_MODEL,
    MAX_FORECAST_DAYS,
    MODEL_LABELS,
    Forecast,
    Place,
    ResponseCache,
    fetch_forecast,
)
from .render import IMPERIAL, METRIC, Units, render_current, render_daily, render_hourly

Fetcher = Callable[..., Forecast]


class WeatherApp(App[None]):
    """Open-Meteo ECMWF IFS forecast TUI."""

    TITLE = "Weather"

    CSS = """
    Screen {
        background: $surface;
    }
    #body {
        padding: 1 2 0 2;
    }
    #current {
        margin-bottom: 1;
    }
    #hourly {
        margin-bottom: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q,ctrl+c", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("u", "toggle_units", "Units"),
        Binding("plus,equals_sign", "more_days", "+ Days"),
        Binding("minus", "fewer_days", "\u2212 Days"),
    ]

    def __init__(
        self,
        *,
        place: Place,
        days: int = 7,
        model: str = DEFAULT_MODEL,
        units: Units = METRIC,
        timezone: str = "auto",
        hourly_rows: int = 24,
        refresh_seconds: int = 900,
        cache: ResponseCache | None = None,
        fetcher: Fetcher = fetch_forecast,
    ) -> None:
        super().__init__()
        self.place = place
        self.days = max(1, min(int(days), MAX_FORECAST_DAYS))
        self.model = model
        self.units = units
        self.timezone = timezone
        self.hourly_rows = max(1, int(hourly_rows))
        self.refresh_seconds = int(refresh_seconds)
        self.cache = cache
        self.forecast: Forecast | None = None
        self._fetcher = fetcher

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="body"):
            yield Static("Loading forecast \u2026", id="current")
            yield Static(id="hourly")
            yield Static(id="daily")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{self.place.label()} \u2014 loading \u2026"
        if self.refresh_seconds > 0:
            self.set_interval(self.refresh_seconds, self.load_forecast)
        self.load_forecast()

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #

    @work(exclusive=True, group="forecast")
    async def load_forecast(self, *, force: bool = False) -> None:
        """Fetch the forecast in a worker thread and repaint."""
        self.sub_title = f"{self.place.label()} \u2014 loading \u2026"
        try:
            forecast = await asyncio.to_thread(
                self._fetcher,
                self.place,
                days=self.days,
                model=self.model,
                timezone=self.timezone,
                cache=None if force else self.cache,
            )
        except Exception as exc:
            self.sub_title = f"{self.place.label()} \u2014 error: {exc}"
            self.notify(f"Forecast request failed: {exc}", severity="error", timeout=10)
            return
        self.forecast = forecast
        self.repaint(forecast)

    def repaint(self, forecast: Forecast | None = None) -> None:
        forecast = forecast or self.forecast
        if forecast is None:
            return
        self.query_one("#current", Static).update(render_current(forecast, self.units))
        self.query_one("#hourly", Static).update(
            render_hourly(forecast, self.units, count=self.hourly_rows)
        )
        self.query_one("#daily", Static).update(render_daily(forecast, self.units))
        model_label = MODEL_LABELS.get(forecast.model, forecast.model)
        self.sub_title = (
            f"{forecast.place.label()} \u00b7 {model_label} \u00b7 "
            f"{forecast.fetched_at.astimezone().strftime('%H:%M:%S')} \u00b7 "
            f"{'metric' if self.units.is_metric else 'imperial'}"
        )

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #

    def action_refresh(self) -> None:
        self.load_forecast(force=True)

    def action_toggle_units(self) -> None:
        self.units = IMPERIAL if self.units.is_metric else METRIC
        self.repaint()

    def action_more_days(self) -> None:
        if self.days >= MAX_FORECAST_DAYS:
            return
        self.days += 1
        self.load_forecast(force=True)

    def action_fewer_days(self) -> None:
        if self.days <= 1:
            return
        self.days -= 1
        self.load_forecast(force=True)

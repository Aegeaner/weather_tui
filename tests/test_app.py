"""Headless TUI tests driving the real Textual app with a stubbed fetcher."""

from __future__ import annotations

import asyncio

from textual.widgets import Static

from weather_tui.app import WeatherApp


class FakeFetcher:
    def __init__(self, forecast):
        self.forecast = forecast
        self.calls: list[dict] = []

    def __call__(self, place, **kwargs):
        self.calls.append({"place": place, **kwargs})
        return self.forecast


def _run(coro):
    return asyncio.run(coro)


def _panel_text(app: WeatherApp, widget_id: str, flatten) -> str:
    widget = app.query_one(f"#{widget_id}", Static)
    return flatten(widget.content)


def test_app_renders_forecast_and_responds_to_keys(forecast, flatten):
    fetcher = FakeFetcher(forecast)

    async def scenario() -> None:
        app = WeatherApp(
            place=forecast.place,
            days=7,
            refresh_seconds=0,
            cache=None,
            fetcher=fetcher,
        )
        async with app.run_test(size=(160, 60)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            assert "Dublin" in _panel_text(app, "current", flatten)
            assert "Hourly" in _panel_text(app, "hourly", flatten)
            assert "Daily" in _panel_text(app, "daily", flatten)
            assert len(fetcher.calls) == 1

            # 'u' flips to imperial units without refetching.
            await pilot.press("u")
            await pilot.pause()
            assert app.units.key == "imperial"
            assert "\u00b0F" in _panel_text(app, "hourly", flatten)
            assert len(fetcher.calls) == 1

            # '+' extends the forecast horizon and refetches.
            await pilot.press("plus")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.days == 8
            assert fetcher.calls[-1]["days"] == 8

            # '-' shrinks it again, but never below one day.
            for _ in range(9):
                await pilot.press("minus")
                await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.days == 1

            # 'r' forces a refresh that bypasses the cache.
            await pilot.press("r")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert fetcher.calls[-1]["cache"] is None

    _run(scenario())


def test_app_surfaces_fetch_errors(forecast, flatten):
    def failing_fetcher(place, **kwargs):
        raise RuntimeError("network down")

    async def scenario() -> None:
        app = WeatherApp(place=forecast.place, refresh_seconds=0, fetcher=failing_fetcher)
        async with app.run_test(size=(120, 40)) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "error" in app.sub_title.lower()
            assert app.forecast is None
            assert "Loading" in _panel_text(app, "current", flatten)

    _run(scenario())

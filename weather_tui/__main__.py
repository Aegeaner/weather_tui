"""Command-line entry point for the weather TUI."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .api import (
    DEFAULT_MODEL,
    DUBLIN,
    MAX_FORECAST_DAYS,
    Place,
    ResponseCache,
    default_cache_dir,
    geocode,
)
from .app import WeatherApp
from .render import METRIC, UNIT_SYSTEMS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weather-tui",
        description=(
            "Terminal weather forecast using the Open-Meteo API with the ECMWF "
            "IFS HRES 9 km model. Defaults to Dublin."
        ),
    )
    parser.add_argument("--version", action="version", version=f"weather-tui {__version__}")
    location = parser.add_argument_group("location")
    location.add_argument(
        "--city", metavar="NAME", help="look the location up by name (e.g. 'Dublin', 'Cork, IE')"
    )
    location.add_argument("--lat", type=float, metavar="DEG", help="latitude in degrees")
    location.add_argument("--lon", type=float, metavar="DEG", help="longitude in degrees")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        metavar=f"1-{MAX_FORECAST_DAYS}",
        help="forecast length in days (default: 7)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Open-Meteo weather model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--units",
        choices=sorted(UNIT_SYSTEMS),
        default=METRIC.key,
        help="unit system (default: metric)",
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=900,
        metavar="SECONDS",
        help="auto-refresh interval, 0 disables (default: 900)",
    )
    parser.add_argument(
        "--hourly-rows",
        type=int,
        default=24,
        metavar="N",
        help="number of hourly rows to display (default: 24)",
    )
    parser.add_argument(
        "--timezone", default="auto", help="timezone for timestamps (default: auto)"
    )
    parser.add_argument("--no-cache", action="store_true", help="disable the on-disk cache")
    parser.add_argument(
        "--cache-ttl",
        type=float,
        default=3600.0,
        metavar="SECONDS",
        help="cache lifetime (default: 3600)",
    )
    return parser


def resolve_place(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Place:
    if args.lat is not None or args.lon is not None:
        if args.lat is None or args.lon is None:
            parser.error("--lat and --lon must be provided together")
        assert args.lat is not None and args.lon is not None
        return Place(f"{args.lat:.3f}, {args.lon:.3f}", args.lat, args.lon)
    if args.city:
        try:
            results = geocode(args.city, count=1)
        except Exception as exc:
            parser.error(f"geocoding failed: {exc}")
        if not results:
            parser.error(f"no location found for {args.city!r}")
        return results[0]
    return DUBLIN


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    place = resolve_place(args, parser)

    cache = None
    if not args.no_cache:
        cache = ResponseCache(default_cache_dir(), ttl=args.cache_ttl)

    app = WeatherApp(
        place=place,
        days=args.days,
        model=args.model,
        units=UNIT_SYSTEMS[args.units],
        timezone=args.timezone,
        hourly_rows=args.hourly_rows,
        refresh_seconds=args.refresh,
        cache=cache,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

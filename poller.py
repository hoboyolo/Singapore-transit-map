"""
Polling + caching layer sitting between lta_client.py (raw API calls) and
main.py (HTTP endpoints).

Two very different caching strategies live here, because bus data and taxi/
crowd data have fundamentally different shapes (see README):

- Buses: no citywide feed exists, so we poll on-demand, scoped to whatever
  bbox the frontend asks about, with a short per-stop TTL cache shared
  across concurrent viewers of overlapping areas (the thing that makes this
  viable on a free-tier API quota).
- Taxis & station crowd: genuinely citywide single-call feeds, so these are
  refreshed on a fixed background interval regardless of who's looking,
  and every request just reads the shared cache — no per-request LTA calls
  at all for these two layers.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

import lta_client

BUS_STOPS_PATH = Path(__file__).resolve().parent.parent / "data" / "bus_stops.json"
BUS_STOP_TTL_SECONDS = 15          # matches LTA's real-world update cadence for Bus Arrival
TAXI_REFRESH_SECONDS = 30
CROWD_REFRESH_SECONDS = 60
TRAIN_LINES = ["NSL", "EWL", "CCL", "NEL", "DTL", "TEL"]

_bus_stops_index: list[dict[str, Any]] = []
_bus_arrival_cache: dict[str, tuple[float, dict]] = {}   # stop_code -> (fetched_at, payload)
_taxi_cache: dict[str, Any] = {"fetched_at": 0.0, "data": []}
_crowd_cache: dict[str, Any] = {"fetched_at": 0.0, "data": {}}


def load_bus_stops_index() -> None:
    """Loaded once at FastAPI startup — see main.py's startup event."""
    global _bus_stops_index
    if BUS_STOPS_PATH.exists():
        _bus_stops_index = json.loads(BUS_STOPS_PATH.read_text())
    else:
        # Fall back to the small bundled sample so the app is runnable
        # before scripts/fetch_bus_stops.py has ever been run.
        sample_path = Path(__file__).resolve().parent.parent / "data" / "bus_stops_sample.json"
        _bus_stops_index = json.loads(sample_path.read_text())


def stops_in_bbox(west: float, south: float, east: float, north: float, limit: int = 60) -> list[dict]:
    """
    Local, in-memory bbox filter over the cached stops list — no network
    call. `limit` caps how many stops a single viewport request will trigger
    Bus Arrival calls for for, so a user who zooms out over half the island
    doesn't accidentally fire off hundreds of LTA calls in one request; the
    frontend should nudge users to zoom in for live buses (see README).
    """
    matches = [
        s for s in _bus_stops_index
        if west <= s["Longitude"] <= east and south <= s["Latitude"] <= north
    ]
    return matches[:limit]


async def get_bus_sightings_for_bbox(west: float, south: float, east: float, north: float) -> list[dict]:
    """
    Returns a flat list of {service_no, lat, lon, eta_seconds, stop_code,
    load} sightings for every bus currently estimated to be near a stop
    inside the given bbox. Each matched stop is polled at most once every
    BUS_STOP_TTL_SECONDS, shared across all concurrent callers.
    """
    stops = stops_in_bbox(west, south, east, north)
    now = time.time()

    async with httpx.AsyncClient() as client:
        tasks = []
        stops_to_fetch = []
        for stop in stops:
            code = stop["BusStopCode"]
            cached = _bus_arrival_cache.get(code)
            if cached and (now - cached[0]) < BUS_STOP_TTL_SECONDS:
                continue  # fresh enough, skip the network call
            stops_to_fetch.append(code)
            tasks.append(lta_client.get_bus_arrival(client, code))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for code, result in zip(stops_to_fetch, results):
                if isinstance(result, Exception):
                    continue  # skip a failed stop rather than fail the whole viewport
                _bus_arrival_cache[code] = (now, result)

    sightings = []
    for stop in stops:
        code = stop["BusStopCode"]
        cached = _bus_arrival_cache.get(code)
        if not cached:
            continue
        payload = cached[1]
        for service in payload.get("Services", []):
            next_bus = service.get("NextBus", {})
            lat, lon = next_bus.get("Latitude"), next_bus.get("Longitude")
            if not lat or not lon or float(lat) == 0.0:
                continue  # LTA returns 0/0 or blank when no live estimate is available
            sightings.append({
                "service_no": service.get("ServiceNo"),
                "lat": float(lat),
                "lon": float(lon),
                "load": next_bus.get("Load"),          # 'SEA' / 'SDA' / 'LSD' seat availability
                "eta_seconds": _eta_seconds(next_bus.get("EstimatedArrival")),
                "near_stop_code": code,
            })
    return sightings


def _eta_seconds(iso_timestamp: str | None) -> int | None:
    if not iso_timestamp:
        return None
    from datetime import datetime, timezone
    try:
        eta = datetime.fromisoformat(iso_timestamp)
        return max(0, int((eta - datetime.now(timezone.utc)).total_seconds()))
    except ValueError:
        return None


async def refresh_taxis_loop():
    """Background task started at FastAPI startup — see main.py."""
    async with httpx.AsyncClient() as client:
        while True:
            try:
                data = await lta_client.get_taxi_availability(client)
                _taxi_cache["data"] = data
                _taxi_cache["fetched_at"] = time.time()
            except Exception:
                pass  # keep serving the last good cache on a transient failure
            await asyncio.sleep(TAXI_REFRESH_SECONDS)


async def refresh_crowd_loop():
    async with httpx.AsyncClient() as client:
        while True:
            try:
                combined = {}
                for line in TRAIN_LINES:
                    result = await lta_client.get_station_crowd_density(client, line)
                    combined[line] = result.get("value", [])
                _crowd_cache["data"] = combined
                _crowd_cache["fetched_at"] = time.time()
            except Exception:
                pass
            await asyncio.sleep(CROWD_REFRESH_SECONDS)


def get_cached_taxis() -> dict:
    return _taxi_cache


def get_cached_crowd() -> dict:
    return _crowd_cache

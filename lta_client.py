"""
Thin wrapper around LTA DataMall's REST APIs.

All endpoints require an `AccountKey` header (free, instant on registration —
see https://datamall.lta.gov.sg/content/datamall/en/request-for-api.html).
No OAuth, no per-endpoint keys — one key for everything.

Base URL and endpoint paths verified against LTA DataMall API User Guide
v6.8 (21 Apr 2026) and the live Dynamic Datasets listing. Re-check
https://datamall.lta.gov.sg/content/dam/datamall/datasets/LTA_DataMall_API_User_Guide.pdf
before relying on this in production — LTA does rename/version endpoints
occasionally (e.g. Bus Arrival is now v3; ERP Rates was removed as a live
endpoint and is static-only now).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice"


def _headers() -> dict[str, str]:
    key = os.environ.get("LTA_ACCOUNT_KEY")
    if not key:
        raise RuntimeError("LTA_ACCOUNT_KEY environment variable not set.")
    return {"AccountKey": key, "accept": "application/json"}


async def get_bus_arrival(client: httpx.AsyncClient, bus_stop_code: str,
                           service_no: str | None = None) -> dict[str, Any]:
    """
    Real-time arrivals + estimated live position for buses approaching a
    single stop. Returns up to the next 3 buses per service calling at
    this stop (NextBus / NextBus2 / NextBus3), each with Latitude/Longitude
    of its current estimated position — this is the closest thing to "bus
    GPS" the public API exposes, and it's scoped to this one stop only.
    """
    params = {"BusStopCode": bus_stop_code}
    if service_no:
        params["ServiceNo"] = service_no
    resp = await client.get(f"{BASE_URL}/v3/BusArrival", headers=_headers(), params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


async def get_taxi_availability(client: httpx.AsyncClient) -> list[dict[str, float]]:
    """
    Live coordinates of every taxi currently available for hire, islandwide.
    Paginated at 500 records/call — this loop drains all pages. Unlike bus
    data, this genuinely is a single-feed, citywide, real-time layer.
    """
    all_coords: list[dict[str, float]] = []
    skip = 0
    while True:
        resp = await client.get(
            f"{BASE_URL}/Taxi-Availability", headers=_headers(),
            params={"$skip": skip}, timeout=15,
        )
        resp.raise_for_status()
        batch = resp.json().get("value", [])
        if not batch:
            break
        all_coords.extend(batch)
        if len(batch) < 500:
            break
        skip += 500
    return all_coords


async def get_station_crowd_density(client: httpx.AsyncClient, train_line: str) -> dict[str, Any]:
    """
    Real-time crowd level per station for a given line (e.g. 'NSL', 'EWL',
    'CCL'). Used to render MRT stations as color-coded markers since actual
    train GPS isn't available.
    """
    resp = await client.get(
        f"{BASE_URL}/PCDRealTime", headers=_headers(),
        params={"TrainLine": train_line}, timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


async def get_bus_stops_page(client: httpx.AsyncClient, skip: int) -> list[dict[str, Any]]:
    """One page (500 records) of the static bus stops dataset. Used by
    scripts/fetch_bus_stops.py to build the local cache — not called at
    request-serving time, since this list barely changes."""
    resp = await client.get(
        f"{BASE_URL}/BusStops", headers=_headers(),
        params={"$skip": skip}, timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("value", [])

"""
FastAPI backend for the Singapore transit map.

Three endpoints, matching the three data-shape categories described in the
README: viewport-scoped buses, islandwide taxis, and per-line station crowd.
The frontend polls these on its own interval and interpolates between polls
client-side (see frontend/app.js) — this backend's only job is caching and
shaping LTA's responses, not animation.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import poller


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller.load_bus_stops_index()
    taxi_task = asyncio.create_task(poller.refresh_taxis_loop())
    crowd_task = asyncio.create_task(poller.refresh_crowd_loop())
    yield
    taxi_task.cancel()
    crowd_task.cancel()


app = FastAPI(title="Singapore Transit Map API", lifespan=lifespan)

# MVP: wide open CORS since the frontend is a static file served from
# anywhere in dev. Lock this down to your actual frontend origin before
# deploying publicly.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


@app.get("/api/buses")
async def buses(
    west: float = Query(...), south: float = Query(...),
    east: float = Query(...), north: float = Query(...),
):
    """
    Live (≈ interpolatable) bus sightings for stops inside the given bbox.
    Query params are a Leaflet/MapLibre-style bounding box: west, south,
    east, north (in decimal degrees).
    """
    if east - west > 0.08 or north - south > 0.08:
        # ~8km at Singapore's latitude — beyond this, too many stops would
        # be in-scope for a single request to stay within a friendly LTA
        # call budget. Ask the frontend to zoom in instead of silently
        # truncating results in a way the user won't understand.
        raise HTTPException(
            status_code=400,
            detail="Viewport too large for live bus data — zoom in further (roughly street/neighbourhood level).",
        )
    sightings = await poller.get_bus_sightings_for_bbox(west, south, east, north)
    return {"count": len(sightings), "buses": sightings}


@app.get("/api/taxis")
async def taxis():
    """Islandwide available-taxi positions, served from the shared background cache."""
    cache = poller.get_cached_taxis()
    return {"fetched_at": cache["fetched_at"], "taxis": cache["data"]}


@app.get("/api/crowd")
async def crowd():
    """Per-station real-time crowd density, all lines, from the shared background cache."""
    cache = poller.get_cached_crowd()
    return {"fetched_at": cache["fetched_at"], "lines": cache["data"]}


@app.get("/api/health")
async def health():
    return {"status": "ok", "bus_stops_indexed": len(poller._bus_stops_index)}

"""
One-time (or occasional-rerun) job: fetch LTA's full static Bus Stops
dataset and cache it as data/bus_stops.json.

This exists so the backend never has to hit LTA just to answer "which stops
are inside this map viewport?" — that's a local lookup against ~5,000
records loaded once at startup. Only the *dynamic* Bus Arrival calls for
those matched stops go out to LTA per request.

Re-run this occasionally (e.g. monthly via cron) since LTA lists this
dataset's update frequency as "Ad-Hoc" — new stops do get added.
"""
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.append(str(Path(__file__).resolve().parent.parent / "backend"))
from lta_client import get_bus_stops_page  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "bus_stops.json"


async def main():
    all_stops = []
    async with httpx.AsyncClient() as client:
        skip = 0
        while True:
            batch = await get_bus_stops_page(client, skip)
            if not batch:
                break
            all_stops.extend(batch)
            print(f"Fetched {len(all_stops)} stops so far...")
            if len(batch) < 500:
                break
            skip += 500

    OUTPUT_PATH.write_text(json.dumps(all_stops, indent=2))
    print(f"Wrote {len(all_stops)} bus stops to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

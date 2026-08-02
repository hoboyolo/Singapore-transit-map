# Singapore Transit Map — Project 3

A live 2D transit map for Singapore, inspired by `london.pengrubin.com`, built on top of LTA DataMall open APIs.

---

## Why the Architecture Differs from a London-Style Feed

London's TfL Unified API publishes **direct per-vehicle GPS** feeds. **LTA DataMall does not offer an equivalent.** Its `Bus Arrival` endpoint is scoped **per bus stop** (covering ~5,000 stops), returning ETAs for the next 1–3 arriving buses without a persistent global vehicle ID. 

### Practical Solutions for the MVP:
1. **Viewport-Scoped Polling:** To respect LTA rate limits and bandwidth, the backend only polls bus stops falling inside the user's current map bounding box, utilizing a shared short TTL cache.
2. **Client-Side Interpolation:** Because sightings are point-in-time approximations near specific stops, the frontend interpolates movement smoothly between updates rather than relying on continuous high-frequency tracking.
3. **Station-Level MRT Data:** Since trains lack public GPS coordinates, the MRT layer features **animated station markers** colored by live crowd density and pulsing on service alerts.
4. **Direct Taxi Layer:** `Taxi Availability` provides an islandwide coordinate set in a single call[cite: 10], matching the direct-port approach.

---

## Project Structure

```text
singapore_transit_map/
├── README.md                 # Project documentation
├── backend/                  # FastAPI polling & caching service
│   ├── requirements.txt      # Python dependencies
│   ├── main.py               # HTTP endpoints polled by the frontend
│   ├── lta_client.py         # Thin LTA DataMall API wrapper
│   └── poller.py             # Viewport-scoped bus polling & taxi/crowd cache
├── frontend/                 # Static frontend (no build step required)
│   ├── index.html            # Map container and layout
│   └── app.js                # MapLibre GL + OpenFreeMap + interpolation loop
├── scripts/
│   └── fetch_bus_stops.py    # Utility script to cache static bus stops locally
└── data/
    └── bus_stops_sample.json # Sample dataset for immediate out-of-the-box testing



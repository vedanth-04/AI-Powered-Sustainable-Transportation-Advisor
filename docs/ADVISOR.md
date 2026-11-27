# Delhi multimodal sustainable transport advisor

A separate app from the MLOps dashboard. It plans journeys across Delhi that combine **DTC/cluster buses, Delhi Metro, local passenger trains and cabs or auto-rickshaws**, with walking, waiting and interchange time. It ranks the options by fare (within an optional budget), time, transfers and CO₂, and explains each recommendation. The final report, with evaluation and limitations, is [FINAL_REPORT.md](FINAL_REPORT.md); real outputs for ten fixed requests are in [DEMO_CASES.md](DEMO_CASES.md).

| | MLOps dashboard | Transport advisor |
|---|---|---|
| Entry point | `python -m dashboard.server` | `python -m advisor.server` |
| Port | 8050 (Vite dev 5173) | **8070** (Vite dev 5174) |
| Front end | `dashboard/web` | `advisor/web` |
| Touches models/outputs? | reads them | reads the approved bus bundle read-only; its own reports go to `outputs/advisor/` |

The advisor does not change the Phase 2 deployment or move the champion. Its release is recorded as model version 4 (a system release) only when you run `scripts.register_advisor_release`; see the final report.

Check everything on your machine (data, model governance, prediction parity, place search, API):

```powershell
.\.venv-dev\Scripts\python.exe -m scripts.advisor_check
```

## Run it

```powershell
cd C:\Users\...\AI-Powered-Sustainable-Transportation-Advisor
.\.venv-dev\Scripts\python.exe -m scripts.advisor_fetch_data      # ~460 MB of public data, sha256-verified
.\.venv-dev\Scripts\python.exe -m scripts.advisor_build_network   # ~1 min -> data/processed/advisor/
cd advisor\web; npm install; npm run build; cd ..\..
.\.venv-dev\Scripts\python.exe -m advisor.server                  # http://127.0.0.1:8070
```

For front-end development run `npm run dev` in `advisor/web` (http://localhost:5174, proxies `/api` to :8070).

## Data (Delhi only, no synthetic data)

All sources are pinned by commit and sha256 in `advisor/config/sources.json`.

| Mode | Dataset | Publisher | Vintage | What is used |
|---|---|---|---|---|
| Bus | Delhi bus static GTFS (DTC + DIMTS cluster) | Open Transit Data Delhi (otd.delhi.gov.in, Transport Dept. GNCTD + IIIT-Delhi) | June 2024 | 10,514 stops, 2,403 route patterns, 89,393 trips, **official stage fares** (`fare_rules`/`fare_attributes`) |
| Metro | DMRC static GTFS | Open Transit Data Delhi | Aug 2023 | 224 stations inside the Delhi area, 4,766 trips, track distances (`shape_dist_traveled`) |
| Rail | Indian Railways stations/trains/schedules | DataMeet (github.com/datameet/railways) | 2016 | 53 halts inside Delhi, 83 passenger/MEMU services |
| Fares | DMRC fare revision of 25 Aug 2025 | DMRC (press release) | 2025 | slabs ₹11/21/32/43/54/64; Sunday ₹11/11/21/32/43/54 |
| Places | Delhi NCT boundary + municipal ward localities | DataMeet Municipal Spatial Data (CC BY-SA 2.5 IN) | 2023 | 272 named localities (offline search), the boundary that decides what is "in Delhi" |
| Places | Addresses and landmarks | OpenStreetMap via Photon (search) / Nominatim (reverse fallback) | live | only when the server has internet; cached, limited to Delhi |

Known limits, all shown to the user in the app:

- OTD says its bus `stop_times` were generated assuming a constant speed. They are a schedule, not observed times.
- The DMRC feed has weekday trips, a few Saturday trips and no Sunday trips. On weekends the weekday timetable is used and a note is shown.
- The rail timetable is from 2016 and has no running days, so trains are treated as daily. Times and numbers may have changed since.
- Noida (Aqua line) and other stops outside the Delhi bounding box are dropped.

## Choosing places

You type a **place name** - a locality (Lajpat Nagar), landmark (India Gate), hospital, college, market or address - or click on the map.

- Online, the backend asks OpenStreetMap (Photon) for matches inside Delhi and merges them with the offline gazetteer; offline, the 272 ward localities and the transit stop names are searched.
- A locality is placed at its same-named metro station, rail halt or bus stop when one exists inside or near the ward (e.g. "Karol Bagh" -> Karol Bagh metro), otherwise at the ward centre.
- On the map you can click anywhere and choose **Start** or **Destination**, use the map button next to each field, drag the A/B pins, or use **My location**. The clicked point is reverse-geocoded (OpenStreetMap, or the nearest stop and locality offline).
- Points outside the NCT of Delhi boundary (1 km tolerance) are rejected with an explanation. If no stop is within the walking limit, the walk is widened to 1.5 km and then 2.5 km and the app says so.

## Why timetables, not new ML models, for metro and trains

Metro and suburban trains run to a fixed timetable on segregated track. Their travel time between two stations barely varies, and the timetable already encodes running time and dwell. Training a model would need observed trip times (for example GTFS-realtime vehicle positions or automatic fare collection logs). Those are not public for DMRC or Northern Railway, so a model would only learn to copy the timetable. Its errors would also be harder to explain than the published schedule.

The trained model earns its place on **buses in mixed traffic**, where the timetable is a poor guide. So the approved bus model is used **only where it is approved**: the Outer Ring Road eastbound segment (Chirag Delhi → Nehru Place, `ORR_CHIRAG_TO_NEHRU_PLACE_EB`). Everything else uses the timetable. A metro/rail delay model would make sense later, once real-time feeds exist.

### How the bus model is used (the governed path)

1. **Which model.** `advisor/bus_model.py` takes the first source that passes its checks (order set in `advisor_config.json`):
   - *Phase 3 registry champion* - `outputs/phase3/registry/model_versions.json` alias `champion` (v2 after the Phase 3 run). Accepted only if the hash-chained audit log verifies, the version is `approved` with a passed promotion gate, and the exported bundle's model sha256 equals the registry record.
   - *Deployed Docker API* - `POST http://127.0.0.1:8000/predict/bus` (live v1), if it is running.
   - *Phase 2 approved bundle* - `outputs/phase2_serving` (v1).
   Bundles are opened with the project's own `load_bundle` (scikit-learn version, feature schema and checksum checks); nothing is written.
2. **Same features as production.** The request is built exactly like `src/api/main.py` does it: segment, direction, segment length, the approved route id and the entry time, through `engineer_features(..., use_observed_history=False)` (`cold_start_v1`).
3. **Right input time.** The entry time is when the chosen bus reaches the segment's first stop, not the trip's start time.
4. **Right scope.** A bus leg uses the model only for the part of its stop sequence that runs eastbound between the two gates (stops in the corridor band from the west gate to the east gate). The prediction is for the full 2.63 km gate-to-gate segment, so it is scaled by the share of the segment the leg covers. The OTD routes that use it are 465, 465A, 511A, 764 and 774.
5. **Consistent journey.** If the model makes a bus slower than its timetable, later legs are re-timed (the next metro/bus is taken if the connection is missed).
6. **Parity check.** At start-up the adapter recomputes the v1 prediction for the request stored in `deploy/model-v1.json` (2019-07-08 17:10) and compares it with the recorded 6.320402 min. `scripts/advisor_check.py` reports it, and the "How it works" panel shows it with the predicted time through the day.
7. **Uncertainty.** The champion's holdout MAE on this segment (about 1.0 min for v2) is shown next to each ML estimate.

The approved model was trained on 2019 GPS traversals of OTD route id 90. Today's static GTFS renumbered routes, so the model is applied to the buses that physically run this segment; this is stated in the app and in each leg's note.

## How a journey is computed

1. **Places.** You choose a station or stop from the search, or type coordinates. A point outside the Delhi service area, or with no stop within the walking limit, is rejected with an explanation.
2. **Access/egress.** The advisor finds the stops within walking distance (default 1 km). Walking time is the straight-line distance × 1.3 at 4.5 km/h. With cabs allowed, it also tries a cab to or from the nearest metro and railway stations (up to 12 km), so a far-off start can join the metro by cab.
3. **Routing.** It runs RAPTOR (round-based public transit routing) over all three timetables, with walking transfers of up to 400 m between stops. Each round adds one vehicle, so the search returns the fastest journey for 1, 2, 3 … rides. It runs six mode profiles (all modes, metro only, bus only, bus+metro, rail+metro, rail+bus) so that cheap and fast alternatives both appear. A trip is boarded only if it is running that day and you can reach it in time after these buffers:

   | Situation | Buffer |
   |---|---|
   | Entering the metro from the street (security) | 5 min |
   | Changing metro lines | 4 min |
   | Boarding a train | 6 min |
   | Boarding a bus | 1 min |

   All buffers are configurable. You can restrict the modes (bus, metro, train, cab); at least one stays on.
4. **Bus model.** If a bus leg rides the ORR eastbound stretch, the model's prediction replaces the timetable time for that stretch, scaled to the part of the gate-to-gate segment covered. The later legs are then re-timed: if the model makes you miss a connection, the next departure is used.
5. **Fares.** Fares are worked out per leg and in total:
   - **Metro:** DMRC distance slabs. Consecutive metro rides with an in-station interchange count as one ticket. Sunday slabs apply on Sundays. The smart-card 10% discount is optional.
   - **Bus:** the official stage fare from the feed, falling back to the DTC non-AC slabs. Free if the pink-ticket option is on.
   - **Rail:** the unreserved ordinary fare, which is an assumption.
6. **Cabs and autos.**
   - **Time:** OSRM road routing on OpenStreetMap (the public demo server, used lightly) gives the free-flow driving time. It is multiplied by a Delhi traffic factor for the hour (×1.0 at night up to ×1.9 in the evening peak), and an assumed pickup wait of 7–10 minutes is added. If OSRM cannot be reached, the road distance is the straight line × 1.35 at an assumed 38 km/h free-flow speed, and the result says so.
   - **Fare:** the Delhi meter fares notified on 9 Jan 2023: AC taxi ₹40 for the first km then ₹20/km, non-AC ₹17/km, auto-rickshaw ₹30 for the first 1.5 km then ₹11/km, with 25% extra from 11 pm to 5 am. App cabs price dynamically, so cab fares are labelled indicative, and availability is never checked.
   - **Options:** a direct cab is kept for comparison when its estimated road distance is at least 1.5 km. Up to three cab options can appear, including cab + metro/train combinations. Over-budget cabs are still labelled as such.
7. **CO₂.** Distance × a per-passenger-km factor for each mode, compared with driving alone; cab legs use kg per vehicle-km ÷ occupancy. The factors are assumptions.
8. **Ranking.**
   - Options that are no better than another option on any criterion are dropped: arrival, fare, changes, CO₂ and walking.
   - The rest are scored by the chosen priority (balanced = affordability first).
   - Options within budget come first. If none fits, the cheapest is shown along with how much more it costs than the budget.
   - Each option is tagged (recommended / cheapest / fastest / fewest changes / lowest CO₂ / over budget) and gets plain-language reasons.

Every leg in the result says where its time came from: **Timetable**, **Bus model + timetable**, **Road route + traffic rule** (cab with OSRM), **Distance rule + traffic rule** (cab without OSRM) or **Rule-based** (walking).

## API

- `GET /api/health`: network size, bus-model status, sources, assumptions
- `GET /api/places?q=lajpat`: place search (localities, OSM places, stations; or `28.61, 77.21`)
- `GET /api/reverse?lat=28.61&lon=77.23`: name of a map point, its locality, nearest stop, inside-Delhi flag
- `GET /api/model?date=2026-11-23`: bus-model sources, parity check, predicted segment time through the day
- `GET /api/network`: metro line shapes and stations for the map
- `POST /api/plan`

```json
{"origin": {"lat": 28.6329, "lon": 77.2196, "label": "Rajiv Chowk"},
 "destination": {"lat": 28.5491, "lon": 77.2513, "label": "Nehru Place"},
 "depart": "2026-11-23T09:00", "budget_inr": 40, "priority": "balanced",
 "women_free_bus": false, "smart_card": false, "max_walk_m": 1000,
 "modes": ["bus", "metro", "rail", "cab"], "cab_type": "taxi_ac"}
```

`cab_type` is `taxi_ac`, `taxi_non_ac` or `auto`. Errors return `{"error": {"code", "message", "hint"}}` with status 422. The codes are `outside_delhi`, `no_stop_near_origin`, `no_stop_near_destination`, `no_connection` and `too_close`.

## Files

```
advisor/
  config/sources.json          pinned datasets (URL, commit, sha256)
  config/advisor_config.json   every assumption: walking, buffers, fares, CO2, geocoder, bus-model sources and corridor
  ingest.py                    raw feeds -> data/processed/advisor/network.npz + network_meta.json
  network.py, raptor.py        loader and router
  planner.py                   places, fares, CO2, bus-model hook, cab legs, ranking, explanations
  cab.py                       OSRM road routing (cached), traffic factor, pickup wait, meter fares
  bus_model.py                 governed model selection (registry champion / deployed API / approved bundle), parity check
  places.py                    Delhi boundary, ward localities, OSM geocoding (Photon/Nominatim) with cache
  server.py                    Starlette API + static web app (port 8070)
  web/                         React + Vite + Leaflet front end (keyless OpenStreetMap tiles and a local network view)
scripts/advisor_fetch_data.py, scripts/advisor_build_network.py, scripts/advisor_check.py
tests/test_advisor.py          routing, fares, budget, bus-model scope, API (on a tiny fixture network)
```

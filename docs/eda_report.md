# Exploratory Data Analysis Report
## AI-Powered Sustainable Transportation Advisor

**Dataset:** Delhi Bus AVL GPS Data — July 1, 2019  
**Records:** 1,977,922 GPS observations  
**Source:** Zenodo (DOI: 10.5281/zenodo.21738157)

---

## 1. Dataset Scale

| Metric | Value |
|--------|-------|
| Total GPS Records | 1,977,922 |
| Distinct Vehicles | 816 buses |
| Distinct Routes | 193 routes |
| Distinct Trips | 8,327 trips |
| Time Span | Full day (July 1, 2019) |
| Database Size | ~184 MB (SQLite) |

The data covers Delhi's entire public bus network for one complete day of operations.

---

## 2. Data Quality Assessment

### Duplicate Records
- **73,034 duplicate** `(vehicle_id, timestamp)` pairs found
- **Zero coordinate conflicts** among duplicates — safe for automatic deduplication
- After deduplication: **1,904,888 unique observations**

### Missing Values
- Core GPS fields (`vehicle_id`, `lat`, `lng`, `timestamp`) have **zero missing values**
- `trip_id` has some nulls (expected — buses between assigned trips)

### Coordinate Validity
- All GPS coordinates fall within expected Delhi boundaries (28.3°–28.9°N, 76.8°–77.5°E)
- No out-of-bounds anomalies detected

---

## 3. Temporal Patterns

### GPS Sampling Interval
- **Median interval: ~10 seconds** between consecutive pings per bus
- Route 90 buses have denser sampling than fleet average
- 22,828 gaps >5 minutes within same trip (indicate bus stops, terminal waits, or signal loss)

### Server Transmission Delay
- **Median delay: ~13 seconds** between onboard clock and server reception
- Maximum delay: up to **3 minutes**
- **Decision:** Use onboard `timestamp` (UTC epoch) for all trajectory calculations, not server `time`

---

## 4. Speed & Movement Characteristics

### Reported Speed
- Speed field is in **m/s** (multiply by 3.6 for km/h)
- Maximum recorded speed: **21 km/h** (speed field is capped — only 22 discrete values)
- **56% of pings** are at zero speed (buses stopped at signals, stations)

### Fleet-Wide GPS Jump Analysis
- Route 399 shows GPS jumps up to **338.5 km/h** implied speed (erroneous GPS readings)
- Route 90 shows **zero GPS jumps** — naturally cleaner corridor
- **Decision:** Apply 80 km/h speed threshold filter during data cleaning

---

## 5. Route Corridor Analysis

### Top Routes by Volume

| Route | GPS Pings | Buses | Trips |
|-------|-----------|-------|-------|
| Route 90 | Highest | 15+ | 40+ |
| Route 534 | High | 10+ | 30+ |
| Route 399 | High | 10+ | 30+ |

### Multi-Route Bus Behavior
- **94.6% of buses** operate on multiple routes during the day
- This is expected for Delhi's operational model (buses reassigned between shifts)

### Selected Corridors
1. **Route 90/83** — Outer Ring Road (ORR), East-West paired directions
2. **Route 398/399** — MB Road, East-West paired directions

These corridors were selected for:
- High GPS ping density → more training samples
- Clear linear geometry → well-defined spatial gates
- Paired directions → both eastbound and westbound traversals

---

## 6. Key Decisions for ML Pipeline

| EDA Finding | Pipeline Decision |
|-------------|------------------|
| ~2M records, 816 buses | Sufficient data for ML training |
| 73K safe duplicates | Deduplicate in preprocessing |
| 10s sampling interval | Dense enough for trajectory reconstruction |
| Server delay up to 3 min | Use onboard timestamp only |
| 21 km/h speed cap | Speed is approximate; use as feature, not target |
| GPS jumps on some routes | Apply 80 km/h implied-speed filter |
| Route 90 cleanest corridor | Primary prediction target |
| 94.6% multi-route buses | Track by vehicle_id, not route assignment |

# Label Construction Summary
## How We Built Ground-Truth Travel Times

### The Problem
GPS pings are individual location snapshots. We need to measure **actual travel times**
between defined road segments to train our prediction model.

### Our Approach: Spatial Gate Method

```
   ENTRY GATE                              EXIT GATE
   (77.218°E)                              (77.245°E)
       |                                       |
       |    ══════ Road Segment ══════         |
       |    🚌→  →  →  →  →  →  →  🚌→       |
       |                                       |
   Bus crosses                           Bus crosses
   = START time                          = END time

   Travel Time = END - START
```

### What Are Spatial Gates?
We placed virtual "checkpoints" at specific longitude coordinates on the road.
When a bus's GPS trail crosses these points, we record the timestamp.

### Corridors Selected

| Corridor | Road | Entry Gate | Exit Gate |
|----------|------|-----------|-----------|
| ORR Eastbound | Outer Ring Road | 77.218°E | 77.245°E |
| ORR Westbound | Outer Ring Road | 77.245°E | 77.218°E |
| MB Eastbound | MB Road | 77.200°E | 77.230°E |
| MB Westbound | MB Road | 77.230°E | 77.200°E |

### Historical July 1 results (not regenerated during the November 9 audit)

| Metric | Value |
|--------|-------|
| 🚌 **Total Traversals** | 152 |
| 🚌 **Unique Buses** | 57 |
| ⏱️ **Avg Travel Time** | 8.29 minutes (historical report) |
| ⏱️ **Range** | 4.12–19.85 minutes (historical report) |

### Quality Controls
- ❌ Removed GPS jumps (>80 km/h implied speed)
- Split trajectories at gaps >300 seconds; reject traversal gaps >180 seconds and crossing-ping gaps >60 seconds.
- ✅ Used linear interpolation for precise gate-crossing times
- ✅ Each traversal verified through continuous GPS trail

Numeric interpolation resolution does not prove sub-second real-world accuracy. Current duration bounds are 1–45 minutes with average speed at most 70 km/h. The [label report](../label_construction_report.md) retains the original extraction tables; the approved Phase 2 API covers only Route 90 eastbound.

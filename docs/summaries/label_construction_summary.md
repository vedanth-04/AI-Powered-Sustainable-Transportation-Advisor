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

### Results

| Metric | Value |
|--------|-------|
| 🚌 **Total Traversals** | 152 |
| 🚌 **Unique Buses** | 57 |
| ⏱️ **Avg Travel Time** | ~6.5 minutes |
| ⏱️ **Range** | 2 – 15 minutes |

### Quality Controls
- ❌ Removed GPS jumps (>80 km/h implied speed)
- ❌ Removed signal gaps (>5 min between pings)
- ✅ Used linear interpolation for precise gate-crossing times
- ✅ Each traversal verified through continuous GPS trail

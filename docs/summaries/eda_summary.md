# EDA Summary
## Delhi Bus GPS Data — Quick Overview

### What is the Data?
GPS tracking data from **816 Delhi public buses** on **July 1, 2019**.  
Each bus sends a GPS ping every **~10 seconds** with its location, speed, route, and timestamp.

### By the Numbers

| | |
|---|---|
| 📊 **Total Records** | 1,977,922 GPS pings |
| 🚌 **Buses Tracked** | 816 vehicles |
| 🛣️ **Routes Covered** | 193 routes |
| 📏 **Database Size** | ~184 MB |

### Data Quality ✅
- **Zero missing values** in GPS coordinates and timestamps
- **73K duplicate records** safely removed (no data conflicts)
- All coordinates verified within Delhi city boundaries

### Key Insights
1. **Sampling Rate:** GPS pings arrive every ~10 seconds — dense enough for trajectory analysis
2. **Speed Cap:** The reported speed maxes out at 21 km/h (sensor limitation), but GPS displacement gives true speed
3. **Route 90** (Outer Ring Road) selected as primary corridor — highest data volume and cleanest GPS signals
4. **94.6% of buses** serve multiple routes per day — typical for Delhi operations

### What This Means for Our Model
- ✅ Sufficient data volume for machine learning
- ✅ Clean, well-structured GPS data
- ✅ Two clear road corridors identified for travel-time prediction

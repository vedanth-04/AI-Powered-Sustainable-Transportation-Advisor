# Feature Engineering Summary
## What Features Does Our Model Use?

### Prediction Scenario
> *"A bus is about to enter a road segment. Based on what we know RIGHT NOW, 
> how long will it take to cross?"*

### Feature Categories

#### 1. 🕐 Time-of-Day Features
| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| Hour (sin/cos) | Cyclical encoding of hour | Rush hour vs. off-peak |
| Rush Hour Flag | Morning (8-10), Evening (5-8) | Traffic congestion patterns |

#### 2. 📊 Historical Traffic Features
| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| Median travel time (last 1h) | What recent buses experienced | Current traffic conditions |
| Std deviation (last 1h) | How variable recent times are | Traffic predictability |
| Count (last 1h) | How many buses crossed recently | Data reliability |

> **Key Safeguard:** We ONLY use data from buses that **already finished** their trip 
> before the current bus enters. This prevents data leakage (using future information).

#### 3. 🚌 Approach Speed
| Feature | Description | Why It Matters |
|---------|-------------|----------------|
| Speed at entry | Bus speed when entering segment | Current flow speed |

### Total Features: 24 columns

### Preventing Data Leakage
```
Timeline:  ──────────────────────────────→
                    ↑                ↑
           Previous buses      Current bus
           FINISHED here      ENTERS here
                    
           ✅ Can use          🎯 Predicting
           their data          this bus's time
```

We strictly ensure no future information leaks into predictions — 
a critical requirement for valid machine learning models.

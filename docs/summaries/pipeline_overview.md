# Project Pipeline Overview
## AI-Powered Sustainable Transportation Advisor

### Problem Statement
> *Can we predict how long a Delhi public bus will take to travel a road segment, 
> using real-time GPS data and historical patterns?*

### Why This Matters 🌿
- **Passengers** get accurate arrival time estimates
- **City planners** can identify congestion bottlenecks
- **Sustainability** — optimized routes reduce fuel waste and emissions

---

### Pipeline Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐
│   Raw GPS Data   │───▶│   Data Cleaning   │───▶│ Label Construction│
│   (2M records)   │    │   & Validation    │    │  (Travel Times)   │
└─────────────────┘    └──────────────────┘    └───────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐    ┌──────────────────┐    ┌───────────────────┐
│  Model Training  │◀──│    Feature        │◀──│  152 Ground-Truth  │
│  & Evaluation    │    │   Engineering     │    │   Traversals      │
└─────────────────┘    └──────────────────┘    └───────────────────┘
         │
         ▼
┌─────────────────┐
│  MLflow Registry │
│  Best Model: GB  │
│  MAE: 37 seconds │
└─────────────────┘
```

---

### End-to-End Results

| Stage | Input | Output |
|-------|-------|--------|
| **Data Audit** | Raw SQLite DB (184 MB) | Verified 2M clean GPS records |
| **EDA** | GPS records | Identified Route 90 as best corridor |
| **Label Construction** | Cleaned trajectories | 152 ground-truth traversals |
| **Feature Engineering** | Traversals + history | 24 predictive features |
| **Model Training** | Feature matrix | 3 models compared |
| **Best Model** | Gradient Boosting | **MAE: 37 seconds, R²: 0.85** |

---

### Technologies Used

| Category | Tools |
|----------|-------|
| **Language** | Python 3.9 |
| **Data** | SQLite, Pandas, NumPy |
| **ML Models** | Scikit-learn (Random Forest, Gradient Boosting) |
| **Experiment Tracking** | MLflow |
| **Version Control** | Git, GitHub |
| **Data Versioning** | DVC |
| **Visualization** | Matplotlib, Seaborn |
| **Testing** | pytest (25 tests, all passing) |

# Model Results Summary
## Travel Time Prediction Performance

### Models Compared

We trained and compared **3 models** to predict bus travel time across Delhi road segments:

| Model | Description |
|-------|-------------|
| Historical Median | Simple baseline — predicts the median of recent travel times |
| Random Forest | Ensemble of decision trees — handles complex patterns |
| **Gradient Boosting** | Sequential tree ensemble — builds on errors of previous trees |

### Performance Comparison

| Model | MAE (minutes) | RMSE (minutes) | R² Score |
|-------|:---:|:---:|:---:|
| Historical Median | 2.44 | 3.12 | 0.089 |
| Random Forest | 0.75 | 1.05 | 0.812 |
| **Gradient Boosting** ⭐ | **0.62** | **0.87** | **0.850** |

### What Do These Metrics Mean?

- **MAE (Mean Absolute Error):** On average, our best model's prediction is off by only **37 seconds**
- **RMSE (Root Mean Square Error):** Penalizes large errors more — our model scores **0.87 minutes**
- **R² Score:** Our model explains **85% of the variation** in travel times

### Visual Results

The model's predictions closely follow actual travel times:

```
Actual:     ████████████████████  (6.5 min)
Predicted:  ███████████████████   (6.1 min)  ← Only 0.4 min off!
```

### Winner: Gradient Boosting Regressor ⭐

✅ Best accuracy across all metrics  
✅ Robust to outliers  
✅ Registered in MLflow Model Registry as `BusTravelTimePredictor` v1  
✅ All experiments tracked and reproducible via MLflow  

### MLflow Experiment Tracking
All model training runs are logged in **MLflow** with:
- Hyperparameters
- Performance metrics (MAE, RMSE, R²)
- Trained model artifacts
- The best model is registered for deployment

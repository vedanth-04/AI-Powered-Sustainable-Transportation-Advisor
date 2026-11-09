# Model results: distinguish the experiments

The implemented models are a training-set segment median, Random Forest and scikit-learn Gradient Boosting. XGBoost appears in the Phase 1 proposal but is not implemented.

| Experiment | Model / MAE (minutes) | Interpretation |
|---|---|---|
| Corrected Phase 1, Oct 16; 38 holdout rows | RF 1.8694; GB 1.9427; median 2.4412 | One-day retrospective comparison after removing leakage; RF lowest test MAE |
| Phase 2 cold start; 102 validation rows | GB 2.4739; RF 2.4924; median 3.2355 | GB selected using validation MAE |
| Phase 2; 127 test rows | GB 3.6226; median 4.2702 | Historical evaluation of selected candidate |
| Approved Route 90 subset; 36 test rows | GB 1.1661; median 1.3032 | Narrow historical serving scope |

Sources: [corrected Phase 1 CSV](../results/2026-10-16-corrected/model_comparison.csv), [Phase 2 quality snapshot](../results/phase2-v1/quality_report.json). The old 0.62-minute/37-second claim is superseded and must not be presented as current accuracy. MAE is average absolute error; RMSE weighs larger errors more. A single predicted duration is neither metric.

On November 9 this laptop served the approved Gradient Boosting v1 image and returned **6.320402254818158 minutes** for the documented request. Model hash, cold-start policy and healthy container were verified. [Laptop record](../results/2026-11-09-validation/summary.json).

MLflow records and release image have separate identities. The original model is `BusTravelTimePredictor/1`, run `66c819ceb83740c18d05800213524441`; version 1 in a temporary test registry is a different model identity. Real-data training was not rerun during the November 9 documentation audit.

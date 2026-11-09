# Feature engineering summary

Predict at segment entry, before the outcome is known. [Shared feature code](../../src/features/build_features.py) emits **12 model inputs**:

- Categorical: `segment_id`, `direction`, `route_id`, `rush_hour_cat`.
- Numeric: `segment_length_km`, `entry_hour`, `minute_of_day`, `sin_time`, `cos_time`, `hist_segment_median_tt`, `hist_recent_60m_mean_tt`, `hist_completed_count`.

The 24-column historical CSV included metadata and the target; it did not mean 24 predictor inputs. `corridor_name`, exit time, travel-time target and completed-trip speed are excluded. The removed `approach_speed_kmh` alias copied target-derived speed and must not be described as measured pre-entry speed.

Phase 1 observed-history experiments used same-segment traversals completed by the request time: a median over all eligible history, a mean over the last 60 minutes and total eligible count. There is no history-standard-deviation feature.

The approved Phase 2 model uses **cold_start_v1** for fitting, evaluation and inference: both history durations equal `(segment_length_km / 22) * 60`, count is zero. Route IDs stay strings; time features are derived in IST; the API resolves direction and length from the catalog. Tests compare names, order, dtypes, values, encoded features and predictions. See the [full feature specification](../feature_engineering_report.md) and [requirement audit](../phase2_submission_checklist.md).

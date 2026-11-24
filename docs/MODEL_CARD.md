# Model card: BusTravelTimePredictor

| | |
|---|---|
| Task | Supervised regression: riding time in minutes for a bus crossing a verified Delhi road segment |
| Algorithm | scikit-learn `GradientBoostingRegressor` (100 trees, depth 4, learning rate 0.05, subsample 0.8, seed 42) inside a one-hot + scaling pipeline |
| Features (`cold_start_v1`) | segment, direction, route, rush-hour category, segment length, entry hour, minute of day, sin/cos of time, and three history features fixed by segment length (no live history at serving time) |
| Versions | **v1** trained on 1–3 July 2019 (Phase 2 approved) · **v2** retrained on 1–5 July after a drift alarm (Phase 3 champion) · **v3** rejected candidate (corrupted training batch) |
| Authoritative numbers | `outputs/phase3/registry/lifecycle_report.json`; committed summary in `docs/results/phase3/phase3_summary.json` |

## Intended use

- Estimate the in-vehicle riding time on one of four verified segments (Outer Ring Road Chirag Delhi ↔ Nehru Place, Mehrauli–Badarpur Road Saket ↔ Khanpur) as one input to a journey planner that a person reviews.
- Deployed API scope: **Route 90, Outer Ring Road eastbound** only. Other inputs return HTTP 422.

## Out of scope

- Other roads, routes or cities; bus *waiting* time; metro, train or cab legs.
- Present-day Delhi traffic: the model has only seen July 2019.
- Any judgement about individual vehicles or drivers.
- Safety-critical timing (for example emergency services).

## Data

Delhi bus vehicle-location archive (July 2019, Zenodo DOI 10.5281/zenodo.21738157), used under the Delhi Open Transit Data terms. Labels are derived from ordered entry/exit gate crossings, not from timetables. There are 637 validated traversals over five service days. Splits are by date: 1–3 July train, 5 July validation, 8 July test and promotion holdout.

## Performance (holdout: 8 July 2019, 127 trips)

| Version | MAE (min) | RMSE (min) | Notes |
|---|---:|---:|---|
| v1 (Phase 2 approved) | 3.62 | 6.32 | Validation MAE 2.47. Route 90 eastbound subset MAE 1.17 |
| **v2 (Phase 3 champion)** | **3.39** | **6.08** | −6.5% MAE vs v1; better on all four segments |
| v3 (rejected) | 3.56 | 6.19 | Failed data validation; 5% worse than v2; ORR eastbound +17% |

Error by segment for v2: MB Road westbound 6.14 min, MB Road eastbound 4.17, ORR eastbound 1.03, ORR westbound 0.68.

Source: release-environment run of 21 November 2026 (approved v1 artifact, Python 3.12.14, scikit-learn 1.5.2), recorded in `docs/results/phase3/phase3_summary.json`.

## Known weaknesses

- **Systematic under-prediction on later days.** On 8 July v1 under-predicts by about 3 minutes on average, and by about 6.5 minutes on Mehrauli–Badarpur westbound. Retraining on more recent days reduces but does not remove this. Without live history, the model cannot see same-day congestion.
- **Heavy tails.** A few trips take 25–40 minutes; RMSE is roughly twice MAE.
- **Small sample.** Five days of data. The confidence in any single number is limited.
- **Feed artifacts.** The source archive documents timezone corrections and stale observations. Training data passes validation, but the replay shows what a timezone fault would do.

## Ethical and governance notes

The model uses no personal data of travellers and no vehicle identifiers. Its outputs are advisory. Monitoring runs per segment, so one corridor cannot degrade unnoticed behind a good average. Promotion requires that no segment gets more than 10% worse. See [PHASE3_GOVERNANCE.md](PHASE3_GOVERNANCE.md).

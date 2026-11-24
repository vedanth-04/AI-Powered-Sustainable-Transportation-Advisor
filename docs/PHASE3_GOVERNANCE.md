# Phase 3 Governance: what we control, how, and why

This page covers the governance that applies to the Sustainable Transportation Advisor's bus riding-time model. It also explains why each control fits the project. Every control below is backed by code or a record in this repository; the dashboard's **Governance** page shows its live evidence status.

## 1. What is being governed, and how risky is it?

| Question | Answer for this project | Consequence for governance |
|---|---|---|
| What does the model decide? | It estimates riding minutes for a bus segment. A journey planner uses the estimate to rank options; a person chooses. | Advisory, not automated decision-making about people. Human choice stays in the loop. |
| Whose data is used? | Historical 2019 GPS positions of public buses (vehicle registration, coordinates, timestamps). No passenger, fare or rider records. | No personal data of travellers today. Vehicle IDs could indirectly point to drivers, so we never analyse individual vehicles or drivers. |
| What harm can an error cause? | A traveller misses a connection or picks a slower option. No safety, credit, health or legal effect. | Low to medium operational risk. Controls focus on accuracy, transparency and fast recovery, not on heavyweight approval boards. |
| Where does it run? | Locally (Docker on a team laptop) as a historical demonstration. API scope: Route 90 on the Outer Ring Road eastbound segment only. | Scope is enforced in code: any other route or segment returns HTTP 422. |

**Justification:** governance should be proportionate. A five-person student team with an advisory model and no personal data needs reproducibility, traceability, rollback and honest reporting. It does not need the formal sign-off layers of a credit-scoring or medical model. Each control below is there because a specific failure is plausible for *this* system.

## 2. Roles (fill in your team's names)

| Role | Responsibility | Acts in |
|---|---|---|
| Data owner | Source terms, data validation rules, quarantining bad batches | `config/phase3/promotion_policy.json` → `data_validation` |
| Model owner | Training, candidate evaluation, model card | `src/versioning/lifecycle.py`, `docs/MODEL_CARD.md` |
| Release approver (a different person from the model owner) | Reviews the lifecycle report before any image is published | `deploy/release-approvals/` (Phase 2 workflow) |
| Monitoring owner | Reads alerts, follows the runbook, opens retraining | Dashboard → Drift monitoring; `monitoring_policy.json` → `runbook` |
| Governance reviewer | Checks the audit chain and this page each phase | Dashboard → Governance; `audit_log.jsonl` |

The actor on every promotion, rejection and rollback is recorded automatically (`--actor`, `MLOPS_ACTOR` or the OS user).

**Justification:** separating *model owner* from *release approver* is the smallest arrangement that prevents someone from approving their own model. The Phase 2 release workflow already enforces it with a checked-in approval record and main-branch CI.

## 3. Controls across the lifecycle

### 3.1 Data governance

| Control | Implementation | Why it is needed here |
|---|---|---|
| Source and terms recorded | `docs/reference/schema_audit_report.md`; Zenodo DOI and archive member hashes in `sources.json` | The Zenodo deposit does not relicense the data. Use stays under the Delhi Open Transit Data terms, so provenance must be explicit. |
| Data versioning | DVC pointer `data/raw/2019-07-01.db.dvc`, `dvc.yaml`/`dvc.lock`; each model version stores the sha256 of its exact training rows | A model can only be reproduced or audited if its exact training rows are known. |
| Validation before every retrain | `validate_training_data`: required columns, no missing values, 1–45 min durations, exit − entry = label, service hours 05–23 IST, registered segment/route pairs, no duplicates | The archive's publisher documents timezone corrections and stale observations. Our replay showed that a timezone fault silently shifts hour features. |
| Quarantine | A candidate trained on a batch that fails validation is recorded as `rejected` and can never become champion (v3) | A bad batch must leave a trace without ever reaching serving. |
| Minimisation | The model uses no vehicle ID. Replay events and the dashboard contain no vehicle IDs. API logs never store request bodies | Vehicle IDs are not needed for the prediction. Leaving them out removes the driver-monitoring risk at no cost. |

### 3.2 Model governance and versioning

| Control | Implementation | Why it is needed here |
|---|---|---|
| Version ledger | `outputs/phase3/registry/model_versions.json`: data window, rows hash, code commit, hyperparameters, feature-schema hash, runtime, artifact hash, holdout metrics, reason and trigger | Every served prediction must be traceable to the exact model and data that produced it. |
| MLflow mirror | Same versions, tags and `champion`/`previous` aliases in a *separate* Phase 3 MLflow store | The team already uses MLflow for Phase 2. The Phase 2 registry and live v1 are never modified. |
| Candidate, not replacement | Retraining creates `candidate`. Only `approved` versions can take the `champion` alias (enforced in `Ledger.promote`) | The project guide states that retraining produces a candidate, not an automatic improvement. |
| Promotion gate | `config/phase3/promotion_policy.json`: data validation passed; valid predictions; ≥3% lower MAE than champion; beats retrained median baseline; no segment worse by >10%; same feature schema; identical predictions after save/reload | See § 4 for each threshold's justification. |
| Same-holdout comparison | Champion, candidate and baseline are all scored on 8 July | Otherwise an "improvement" may only reflect an easier test day. |
| Model card | `docs/MODEL_CARD.md` | States intended use, out-of-scope use and known weaknesses for anyone who reuses the model. |

### 3.3 Deployment governance

| Control | Implementation | Why it is needed here |
|---|---|---|
| Immutable release | Phase 2 image pinned by digest (`deploy/model-v1.json`); bundle hash checked at load (`src/api/bundle.py`) | What was approved is exactly what runs. |
| Scope enforcement | API rejects routes/segments outside the approved scope (422) | The model has only been evaluated on its corridors; silent extrapolation would be untested. |
| CI on two platforms | `.github/workflows/ci.yml` on Windows and Linux, including the Phase 3 tests | The team develops on Windows while the container runs Linux. |
| Human release step | The v2 bundle is exported locally. Publishing a v2 image still requires the existing approval record and release workflow | Monitoring and retraining are automated; exposing users to a new model is a deliberate, reviewed act. |
| Rollback ready | `previous` alias always set; the lifecycle runs a real rollback drill (roll back, verify hash, predict, restore) and logs it | Recovery must be proven before it is needed. |

### 3.4 Monitoring governance

| Control | Implementation | Why it is needed here |
|---|---|---|
| Four monitoring layers | Data quality (per request), input drift, prediction drift and delayed-label performance | Each layer catches a failure the others miss. In the replay, the road-works scenario was invisible to input drift and was caught only by performance monitoring. |
| Calibrated thresholds | Bootstrap thresholds at the window's own size (95% warn, 99% alert); CUSUM thresholds from a block bootstrap at ≤5% family-wise false alarms | With 15–60 requests per window, fixed textbook PSI cut-offs would raise false alarms. The reference day itself produced no alerts after calibration. |
| Per-segment monitoring | A detector per segment plus one overall | Averages hide failures. On 8 July the overall MAE looked moderate while the Mehrauli–Badarpur westbound segment's error nearly doubled. |
| Runbook | `monitoring_policy.json` → `runbook` | It records the agreed response to each alert type. Only performance alarms open retraining; input drift alone triggers investigation. |
| Honest labelling | Every injected event is flagged (`injected`, `injection`). Reports state "historical replay" | Injected scenarios must never be presented as real-world findings. |

### 3.5 Accountability and audit

| Control | Implementation | Why it is needed here |
|---|---|---|
| Append-only audit log | `audit_log.jsonl`: every register, status change, promotion and rollback, with actor, time, reason, before/after | A ledger shows the current state; the audit log shows how it got there. |
| Tamper evidence | Each entry stores the sha256 of the previous entry; `verify_audit_chain` recomputes the chain (tested: editing one entry breaks it) | Accidental or deliberate edits become detectable without needing a database server. |
| Evidence summary | `python -m scripts.run_phase3 --write-evidence` → `docs/results/phase3/phase3_summary.json` (no local paths) | The same pattern as Phase 2's sanitized validation record, so results can be committed and reviewed. |

## 4. Why these specific thresholds

| Setting | Value | Justification |
|---|---|---|
| Minimum improvement to promote | 3% lower MAE | Below this, the difference is within run-to-run noise on a 127-trip holdout. Swapping models has a cost (a new image and review), so the gain should be visible. |
| Maximum segment regression | +10% | A better average must not be bought by making one corridor worse. This is the fairness-across-corridors rule. |
| Beat the median baseline | required | A model that cannot beat "typical time for this segment" adds complexity without value (project guide's selection gate). |
| CUSUM slack | 0.5 × expected error | It ignores small fluctuations and reacts to a sustained ≥50% error increase, which matters to a traveller choosing connections. |
| Expected error by segment *and* time of day | factors from the approved validation day | Midday errors are naturally larger than dawn errors. Without this, every congested afternoon would raise an alarm. |
| Data-quality alert | >5% failing requests over the last 20 | A single malformed request is a warning. A sustained rate means a broken feed, caught 12 minutes after the first bad request in the replay. |
| Retraining window | complete labelled days only | Partial days over-represent some hours and would bias the time-of-day features. |

## 5. Alignment with Indian frameworks

**India AI Governance Guidelines (MeitY, November 2025).** These guidelines organise responsible AI around seven principles ("sutras"): Trust, People First, Innovation over Restraint, Fairness & Equity, Accountability, Understandable by Design, and Safety, Resilience & Sustainability. Our mapping:

| Sutra | How this project applies it |
|---|---|
| Trust | Hash-pinned artifacts, reproducible pipeline and honest "historical replay" labelling |
| People First | Advisory output only; the traveller decides. No personal data is collected |
| Innovation over Restraint | Proportionate controls (§ 1) instead of approval layers the risk level does not justify |
| Fairness & Equity | Per-segment monitoring and the no-segment-regression gate, so no corridor is served worse to improve the average |
| Accountability | Named roles, actor on every change, tamper-evident audit log |
| Understandable by Design | Model card, gate checks in plain language, version diffs, dashboard explanations |
| Safety, Resilience & Sustainability | Drift detection, quarantine, rollback drill and scope limits |

**Digital Personal Data Protection Act, 2023.** The DPDP Rules, 2025 were notified in November 2025 with an 18-month phased rollout. Today the project processes no personal data of travellers, so the Act's obligations do not bite. That changes when the planned journey advisor goes live, because origin, destination and travel time are personal data. Before that step, the team must add a privacy notice and consent, purpose limitation, a retention limit for request logs, and access controls. The current design already avoids logging request bodies. This is a design note, not legal advice.

**Source data terms.** Delhi's portal states that using its datasets means accepting the Open Transit Data Terms and Conditions. Our use is research and education. We do not redistribute raw data (it stays out of Git under DVC), and we do no individual tracking.

## 6. Incident response (what happens when an alert fires)

1. **Data-quality alert:** quarantine the batch (exclude it from training windows), notify the data owner, and fix the feed. Drift statistics are not trusted until the quality rate is back to normal.
2. **Input or prediction drift only:** the monitoring owner investigates the request mix. No retraining. In the demand-shift scenario, overall error actually *fell* while inputs drifted.
3. **Performance alarm:** open a retraining candidate on complete labelled days. The candidate goes through the gate; the champion keeps serving meanwhile.
4. **Bad release in production:** `Ledger.rollback` moves `champion` back to `previous`. Redeploy the matching image with the Phase 2 `deploy_api` rollback, then record the incident.

## 7. Known limitations (residual risk we accept and disclose)

- The evidence is a replay of two 2019 days. Current Delhi accuracy is unknown without newer labelled trips.
- Bootstrap calibration assumes the reference days are representative; one validation day is a small reference.
- The CUSUM block bootstrap reduces, but does not remove, the effect of correlated errors during congestion.
- The audit log is tamper-*evident*, not tamper-*proof*: someone with write access could rewrite the whole chain. Committing the evidence summary to Git adds an external anchor.
- MLflow mirroring depends on the local environment. If it fails, the failure is recorded and the ledger stays authoritative.

**Sources:** [MeitY India AI Governance Guidelines (PIB release)](https://negd.gov.in/wp-content/uploads/2025/11/Press-Release_Press-Information-Bureau3.pdf) · [DPDP Rules 2025 (PIB backgrounder)](https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf) · [Delhi Open Transit Data — About](https://otd.delhi.gov.in/about)

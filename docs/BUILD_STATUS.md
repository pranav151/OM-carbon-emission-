# First working build — 26 October 2026

**Historical v0.1 build record.** Superseded for current monthly reporting and UI by `OUTCOMES.md`, `ALGORITHMS.md` and the v0.2 README. The numbers below describe the earlier seven-day experiment, not the current three-month dashboard.

## Delivered

Local dashboard running at `http://127.0.0.1:8501` when the Streamlit process is active. Source code, pinned dependencies, source checksums, download/preparation scripts, model formulation, provenance register, independent tests and reproducible exports are included.

The following flows have been exercised:

- Research archive → strict parser → benchmark/illustrative scenario → joint optimiser → independent evaluator → CSV/JSON.
- M5 daily sales → time-ordered forecasting study → selected forecasting method → inventory-routing plan.
- Historical replay → actual sales proxy → shortages and end inventory → replan.
- UI scenario changes → stale-result notice → regeneration → validated current results.

## Verification

30 tests pass across planning, forecasting, simulation and dashboard integration. Checks include a manually calculated route cost/emissions example, shortest tours checked against brute force, infeasible carbon budgets, a binding carbon cap that forces a cleaner/more expensive vehicle, storage before consumption, capacity, supply, MOQ, pack multiples, duplicate visits, terminal stocks, temporal leakage and explicit unserved demand.

Four downloaded benchmark cases solved to optimality and passed independent validation:

| Instance | Outlets | Periods | Objective (cost units) | Gap |
|---|---:|---:|---:|---:|
| L3/abs1n5.dat | 5 | 3 | 1213.00 | 0% |
| L3/abs2n5.dat | 5 | 3 | 967.04 | 0% |
| H3/abs1n5.dat | 5 | 3 | 1870.88 | 0% |
| L6/abs1n10.dat | 10 | 6 | 4073.19 | 0% |

These are results under the documented implementation conventions, not claims to reproduce the full 2025 paper. Reproduce with `.venv/bin/python scripts/check_instances.py`; detailed results are in `results/instance_checks.csv`.

## First forecasting result

Fixed SKU `HOUSEHOLD_1_001`, five stores, 1,913 daily observations per store. Final 21-day model-selection, 21-day calibration and 21-day test windows are disjoint. Three-day rolling forecasts. Random forest was chosen using validation MAE.

| Method | Test MAE (units) | Test RMSE (units) |
|---|---:|---:|
| Seasonal naive | 0.7810 | 1.1792 |
| Moving average | 0.6417 | 0.8210 |
| Random forest | 0.6376 | 0.8249 |

Random forest slightly improves MAE relative to the moving average but has slightly worse RMSE. Sales are low-volume and intermittent; WAPE exceeds 100% for all methods in this small test. This is not evidence of generally accurate or superior ML forecasting. Full metrics and predictions are in `results/forecast/`.

## First operational replay

Seven held-out days, same starting inventory, physical assumptions, calibration buffer and three-day planning horizon. Execute the first day, then replan. No carbon cap is imposed in this forecast-method comparison.

| Method | Operating cost units | Transport CO₂ kg | Fill rate | Unmet units |
|---|---:|---:|---:|---:|
| Seasonal naive | 222.51 | 49.21 | 85% | 3 |
| Moving average | 234.60 | 52.31 | 100% | 0 |
| Random forest | 234.96 | 52.31 | 100% | 0 |
| Short-horizon perfect information | 202.01 | 45.29 | 100% | 0 |

**ML does not reduce emissions relative to the moving-average baseline in this replay.** The lower-emissions seasonal plan under-serves demand, so it is not a successful improvement. End inventories differ and are exported. The perfect-information result is a reference for the same short lookahead, not a proven lower bound across the entire seven-day problem.

In the initial five-outlet illustrative benchmark, cost-focused and minimum-emissions solutions have the same emissions. The dashboard reports coincident endpoints rather than manufacturing intermediate trade-off points.

## Remaining research work

- Full-text audit of the main paper's Section 4 / Table 5 remains incomplete because direct publisher access failed. Current numerical transport inputs are explicitly assumed.
- Test more products, forecast origins and operating scenarios before making a general ML or carbon-savings claim. Intermittent-demand methods and prediction-interval coverage evaluation are useful next candidates.
- Calibrate fleet, geography, fuel factors and inventory settings if a practical industrial application is required.
- The UI currently uses point forecasts for prospective planning; the saved replay uses the documented common residual buffer. Formal stochastic/robust optimisation is not implemented.
- No upload workflow, production authentication, live ERP integration, street routing or automatic retraining is included in this first local version.
- Ten-outlet/six-period capability has been checked on one instance; this does not establish broad scalability.
- Raw dataset redistribution rights are not assumed; raw and derived data remain excluded from Git.

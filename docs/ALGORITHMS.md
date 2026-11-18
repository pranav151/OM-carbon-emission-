### 1. Forecasting algorithms

Ten fixed candidate configurations are compared using chronological validation RMSE. No random train/test split is used. All ML models use up to 730 past days per store and predict three future days recursively.

| Algorithm | Exact configuration |
|---|---|
| Seasonal naïve | Observation seven days earlier; recursive beyond seven days |
| Moving average | Previous 28 observed days; constant rate across the forecast horizon |
| Croston–SBA | α=0.10; initialise size at first positive observation, interval at its 1-based position; update size/interval only on positive days; forecast `(1−α/2) × size / interval` |
| TSB | Size α=0.10 on positive days; occurrence probability β=0.05 every day; same first-positive initialisation; forecast `probability × size` |
| Random forest | 80 trees, seed 42, one worker, depth 12, minimum leaf size 5 |
| Regularised random forest | 80 trees, seed 42, depth 8, minimum leaf size 30 |
| Poisson histogram gradient boosting | Poisson loss, log-link, learning rate 0.05, 100 iterations, 15 leaves, minimum leaf size 30, L2=10, no early stopping, seed 42 |
| Regularised Poisson boosting | Same loss/rate/L2; 60 iterations, 7 leaves, minimum leaf size 50 |
| Poisson regression | StandardScaler fitted on training data only; Poisson log-link, α=0.1, max_iter=300, tolerance 1e−7 |
| Regularised Poisson regression | Same pipeline, α=1.0 |

Predictors: fixed outlet indicators; day of week; month; lags 1, 7, 14 and 28; past 7/28-day means; past-28-day population standard deviation; past-28-day positive-sales share. Every rolling statistic ends before the target date. Future recursive features use predictions, not future actual observations. An all-zero ML training target returns zero predictions explicitly.

**Selection window:** 9 October–3 December 2015, rolling non-overlapping three-day forecasts. **Calibration:** 4–31 December 2015. **Reporting:** 1 January–31 March 2016. The full reporting window is retrospective and partially overlaps an earlier prototype test; it is not a newly blind holdout. Candidates and selection rules are fixed before each comparison run; reporting scores never choose the model.

RMSE selects a conditional-mean forecast and avoids choosing an always-zero prediction solely because MAE can favour it on mostly-zero observations. This does not guarantee better inventory performance. MAE, RMSE and bias are reported, followed by a separate operational simulation.

### 2. Safety stock and operating assumptions

For the moving-average baseline, selected ML model and overall validation winner, compute three-day cumulative underprediction on the calibration window. For each outlet, take the nonnegative 95th percentile for each method, then the maximum across these methods and round upward. This common buffer is used for every operational policy. It is an empirical heuristic; 95th percentile does **not** establish 95% realised service.

Expected demand remains fractional. Shipments are whole product units (`pack_size=1`). Customer capacity and initial inventory depend only on history before the replay; daily depot supply is `max(1, ceil(sum of prior-56-day outlet means)))`, fixed for all policies. Customer and depot holding rates are 0.1 and 0.01 cost units/unit/day. Initial stock, supply, fleet and storage are identical across comparisons.

Fuel consumption remains an explicit assumption: 0.10 and 0.20 L/km. Diesel combustion factor **2.66 kg CO₂/L** is drawn from Mundim et al. (2025), Table 5. Coordinates scaled by 0.05 km/unit are illustrative, not actual store geography. No emissions from warehouses, upstream fuel or products are included.

### 3. Integrated optimisation

**Held–Karp dynamic programming** computes a shortest depot-return tour for each customer subset: 31 subsets for five outlets. For the fixed, distance-only consumption/cost model, a longer tour visiting the same subset cannot improve either objective.

**Pyomo MILP + HiGHS branch-and-bound/cut solver:** select complete tours, vehicle assignments, integer delivered quantities and closing stock jointly. Constraints enforce customer/depot balances, storage before consumption, available supply, vehicle capacity, one visit/customer/day, one route/vehicle/day, minimum/terminal inventory and optional MOQ/pack sizes. Complete tours guarantee route connectivity.

Cost = customer holding + depot holding + distance-based transport + dispatch charges. Fuel expense is already included in distance cost and is not added twice.

`CO₂ = sum(route_km × vehicle_L_per_km × kg_CO₂_per_L)`

The cost plan minimises operating cost, then emissions among solutions within 1e−6 cost units of its proven optimum. The carbon plan finds the cost-focused and minimum-emissions endpoints for the current state. When they differ, it sets `cap = low_emissions + 0.5 × (cost_plan_emissions − low_emissions)` and minimises cost under that cap. This is a **rolling three-day** constraint, not a monthly cap. Equal endpoints reuse the cost plan. Infeasible or unvalidated plans cannot enter the monthly ledger.

### 4. Rolling execution and outcomes

Execute only day one, apply observed sales, count unmet units as lost sales, carry inventory forward, and solve again. All 91 daily decisions are generated without future sales in the forecasting inputs. Stock is never reset at month boundaries. Every input, full horizon plan and independent validation is saved in the policy audit files.

The independent evaluator reconstructs inventory, vehicle loads, route distances, costs and emissions from the schedule without reading solver expressions. The reporting ledger sums only executed routes and realised holding costs.

```python
carbon_saved_kg = baseline_emissions_kg - candidate_emissions_kg
cost_saved = baseline_cost - candidate_cost
reduction_pct = 100 * (baseline - candidate) / baseline
fill_rate = served_units / observed_sales_units
service_qualified = fill_rate >= max(0.95, baseline_fill_rate)
```

Zero baseline → unavailable percentage, not zero or infinity. Aggregate percentages are computed after summing underlying quantities. Negative savings mean an increase and remain visible. End inventories and service outcomes are reported because lower cost/emissions alone do not demonstrate improvement.

### Implementation references

- Forecasts: `src/green_inventory/forecasting.py`
- Monthly experiment and ledger: `src/green_inventory/sustainability.py`
- Formulation and tours: `src/green_inventory/optimisation.py`
- Independent validation: `src/green_inventory/evaluation.py`
- Scikit-learn [Poisson boosting](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) and [Poisson regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.PoissonRegressor.html)

# Carbon Operations: evaluated dashboard

The app uses `outputs/research_database/sustainable_inventory.sqlite`. Its fingerprint must match the evaluation summary before results can display. The old M5 and three-day prototypes are preserved separately in `legacy_app.py` and do not feed the main dashboard.

## Interpretation

The twelve reporting months are June 2017–May 2018 in a synthetic integration scenario. VTT and UC Riverside supply real source patterns. ORNL and MultiPACK remain available as separate evidence tables; they do not train or calibrate the thermal controller in this evaluation. Company-level post-intervention measurements do not exist here. These numbers are conditional benchmark potential under the stated assumptions and perfect information, not expected field performance or a measured reduction.

## Implemented optimisation

1. **Fuel-aware 2-opt.** Preserve each truck's assigned stops and reverse subsequences only within consecutive stops of the same type. Check load evolution, capacity, route time, cost and fuel. Use first improvement, at most 100 passes per source case/truck. The source-row-order route is the reconstructed baseline. Evaluate chosen paths at each day's generated load multiplier and fall back if cost or fuel increases. This is a heuristic and does not certify a globally optimal route.
2. **Delivery/cooling connection.** Recompute hourly door events from changed truck return times; preserve quantities, dispatch times and supplier deliveries. Changes in door heat enter the cooling model in the corresponding hour.
3. **Temperature-constrained LP.** SciPy `linprog(method='highs')` solves a 24-hour plan with 24 compressor-power decisions and 25 temperature states per zone. Minimise electricity CO2 subject to thermal balances, power limits, temperature bounds, baseline electricity-cost cap, and identical initial/final baseline temperatures. Fans, lighting and defrost energy remain fixed. Two zones give 98 variables. Daily problems are solved independently, with equal endpoint temperatures providing continuity.

```
T[h+1] = T[h] + (Q[h] - COP[h] * P[h] * 1 hour) / C
electricity[h] = P[h] * 1 hour + auxiliaries[h]
minimise sum(electricity[h] * grid_carbon[h])
subject to sum(electricity[h] * tariff[h]) <= baseline electricity cost
```

The heat input is synthetic and calibrated to a replayed load shape. It does not change with zone temperature, and COP varies with assumed ambient temperature rather than evaporating temperature. These simplifications, loose synthetic equipment constraints and perfect foresight can overstate practical flexibility. No compressor cycling limits, minimum run-times, food-core temperatures or demand charges are validated.

The route search and cooling LP are staged, not a globally optimal integrated inventory-routing MILP. No demand/load forecasting model feeds this benchmark. Forecast-error performance must be evaluated separately before calling this an operational decision system.

## Four comparable policies

- Baseline: source-row-order routes and constant-target cooling.
- Transport only: 2-opt routes, updated receiving heat, constant-target cooling.
- Cold storage only: original routes, cooling LP.
- Combined: 2-opt routes, updated receiving heat, cooling LP.

All four serve identical orders with identical stock, replenishment, supplier trips, leakage and spoilage. Their costs and emissions remain in the denominator. Inventory optimisation and maintenance savings are not claimed. The default inventory baseline has no spoilage or stock shortages.

## Metrics and audit

Carbon reduction = 100 × (baseline emissions − selected emissions) / baseline emissions. The annual percentage is recalculated from annual totals. Positive cost savings equal baseline minus selected operating costs. Contribution improvement equals those savings because revenue and COGS are fixed; it is not net profit. Currency is fictional CU. Implementation/capital costs are excluded.

The footprint includes electricity and diesel combustion CO2 plus assumed R744 leakage. It omits CH4/N2O, upstream fuel, capital equipment and full product lifecycle emissions. This is explicitly a partial CO2e boundary. Zero leakage changes or fixed inventory components are not credited as savings.

Independent checks reconstruct thermal residuals, inspect all temperature and power bounds, confirm initial/final temperatures, compare stop sets and load capacity, and reconcile the reproduced baseline with the database. Tests also reconcile monthly totals and percentages and compare recorded routes with their saved road matrices. Solver success alone is not accepted as an audit.

Rebuild: `PYTHONPATH=src .venv/bin/python -m green_inventory.research_evaluation`.
Run the dashboard: `.venv/bin/streamlit run app.py --server.port 8501`.

Read `docs/RESEARCH_DATABASE.md` for all sources, licences, missing-data handling and synthetic parameter definitions.

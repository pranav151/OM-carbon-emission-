# Carbon-first sustainable inventory optimization

## Objective

Minimize operational greenhouse-gas emissions by jointly choosing replenishment dates, quantities, vehicle assignments and delivery/pickup routes, while meeting demand and maintaining an acceptable operating budget. Measure cost savings and, where revenue and other costs are held constant, the resulting profit improvement.

Fuel/electricity bills and vehicle operating costs are actual economic categories. Carbon taxes, allowances and internal carbon prices are separate policy scenarios; do not treat every tonne avoided as cash saved. Profit is not identifiable from emissions alone.

## Recommended evidence base

Use the **NCST/UC Riverside logistics cases plus EPA emissions factors**, with a separately labelled synthetic inventory extension. This is a stronger carbon/transport foundation than sales-only M5 or FreshRetailNet. The sources are listed in `data/research/carbon_inventory/README.md` and the original bytes have been downloaded there.

| Component | Evidence class | Intended use |
|---|---|---|
| Published NCST deliveries, pickups, truck assignments and locations | Real-operation-derived research cases | Fixed daily routing benchmark |
| OpenRouteService distance/time matrices supplied with the cases | Source-generated network estimates | Route feasibility and activity estimates |
| EPA fuel and electricity factors | Official reference values | Convert estimated energy/fuel into emissions |
| SmartWay 2022 carrier performance ranges | Aggregated public benchmark | Sensitivity checks for freight emission intensity |
| Daily demand across 180 scenario days, inventory, capacities, lead times and unavailable costs | Proposed synthetic/assumed inputs | Multi-period inventory-routing experiments |
| Fuel, electricity, CO2/CO2e and savings calculated by our model | Estimated outputs | Compare policies on identical inputs |

The downloaded NCST cases contain 47, 58, 71 and 90 customer stops. They represent four dispatch problem instances derived from typical one-day historical movements, not a 6-month observed inventory series. A 180-day extension would be a simulation only. Keep the original daily benchmarks separately visible so the simulation does not replace the strongest observed evidence.

There is no single file containing all required inventory and measured carbon variables in the sources verified so far. This bundle supports an academic optimization study; it does not establish actual field-deployed emissions savings.

## Real operations-management concepts and algorithms

1. **Inventory balance and dynamic lot sizing.** Track closing stock = opening stock + receipts − fulfilled demand. Decide whether consolidating orders saves transport emissions enough to offset additional storage energy and holding cost. Enforce storage limits and comparable ending stocks so a policy cannot appear better by simply emptying the system.
2. **Reorder points and safety stock.** Use periodic order-up-to and `(s,S)` replenishment as understandable baselines. Demand/lead-time uncertainty determines safety stock; measure service and shortages explicitly.
3. **Inventory-routing problem (IRP).** Jointly choose delivery day, order quantity and route. This keeps inventory decisions central to the project.
4. **Capacitated vehicle routing with backhauls and time windows.** Respect vehicle load, delivery/pickup compatibility, service durations and workday limits. Combine pickups with deliveries to reduce empty travel when feasible.
5. **Multi-objective optimization using the epsilon-constraint method.** Minimize total emissions subject to a cost budget and service requirements; sweep budgets to expose the cost–carbon trade-off. With a budget equal to a feasible reference policy's cost, seek lower emissions without higher modeled operating cost. A further cost-minimization pass breaks carbon ties within a declared tolerance. Cost reduction is tested, not guaranteed.
6. **Mixed-integer linear programming (MILP).** Use an arc-based formulation and HiGHS on smaller instances to obtain reference solutions and solver bounds. A nonlinear load/speed energy model needs a documented linearization or fixed arc coefficients before calling the formulation MILP. The current app's subset tour enumeration is unsuitable for all 90 stops.
7. **Adaptive Large Neighborhood Search (ALNS).** For larger cases, repeatedly remove and reinsert visits, move replenishments between days, merge/split feasible deliveries, and improve route order. Adapt operator selection using solution quality. Reject infeasible final plans; benchmark solution gaps against MILP where tractable.
8. **Rolling-horizon planning.** Replan daily over a shorter look-ahead window using only information available at that time. Evaluate on the full scenario horizon with identical demand realizations for all policies.

Our proposed contribution is an **inventory-aware, carbon-first extension of ALNS** that scores delivery-date changes using both transport and storage consequences. This is a project method to implement and test, not a claim of a globally new algorithm.

## Emissions and cost model

For a defined operational boundary:

`total emissions = diesel combustion emissions + purchased electricity emissions for trucks + warehouse electricity emissions`

`diesel emissions = modeled fuel use × compatible fuel emission factor`

`electricity emissions = metered-side modeled kWh × appropriate regional grid factor`

Use a documented fuel/energy model with route distance, load and speed where justified. Convert all physical units explicitly. The original CSV weight/service headers are unit-incomplete; preserve them and document/resolve interpretation before producing load-based carbon results. Account for charging losses consistently. Vehicle manufacture, upstream fuel production and product embodied carbon are outside the initial operational boundary unless added consistently to every policy.

CO2-only factors yield CO2, not automatically CO2e. To report CO2e, include CH4/N2O with declared global-warming potentials and a consistent boundary. Do not add SmartWay distance-based emissions on top of fuel-based emissions for the same activity. SmartWay is an alternative estimation/benchmark method.

Warehouse base electricity that does not change with the inventory policy cannot be claimed as a saving. Any occupancy-dependent energy estimate must be separated from fixed building loads and tested over plausible assumptions.

Costs include energy, dispatch/vehicle use, labor where modeled, inventory holding and shortage consequences. Include vehicle purchase/lease/charging infrastructure assumptions before claiming that switching to electric vehicles improves profit. First compare policies under the same fleet to isolate operational improvements.

## Role of ML

ML may estimate future demand when real longitudinal demand data exists. These four daily cases cannot establish a credible trained demand-forecasting model. Synthetic demand can test how the optimizer behaves under forecast errors, but successful prediction of generated patterns is not proof of real forecasting accuracy. Keep any real-retail forecasting experiment separate from the NCST company; they cannot be joined as observations of the same business.

The essential intelligence here is constrained optimization and uncertainty handling. Adding ML does not replace the inventory, energy or routing model.

## Evaluation and honest claims

- Stage 1: validate units, stop/site mapping, capacities and feasible route reconstruction. Reproduce a daily NCST benchmark where possible. If historical stop order cannot be verified, label a reconstructed route as a reconstruction.
- Stage 2: compare periodic replenishment, `(s,S)` plus conventional routing, cost-only joint optimization, and the carbon-first joint method under the same multi-period scenarios and constraints.
- Stage 3: evaluate multiple fixed random seeds, low/medium/high variability, fuel/grid intensity, load/energy parameters, holding costs and service targets. Publish mean and spread; do not select only improving seeds.
- Report total emissions, emissions per fulfilled unit, operating cost, cost reduction, service/fill rate, shortages, average inventory, trips, distance, empty distance and vehicle utilization. Compute monthly reduction from monthly totals, not an average of daily percentages.
- `emissions reduction % = 100 × (reference emissions − candidate emissions) / reference emissions`, when reference emissions are positive. Use the same formula for cost savings.
- A negative reduction is a deterioration and remains visible. A policy failing service/capacity constraints is not an admissible improvement.
- Preserve labels: original observation, provider-derived estimate, external reference factor, assumption, generated scenario and calculated output. Compute synthetic percentages only after declaring whether the denominator is fields, rows or populated input cells; also report the critical assumptions separately.
- Comparing against a published paper requires matching its instances, objective, constraints, units and accounting boundary. The NCST study reports energy reductions; our carbon/inventory objective is different. Do not claim to outperform the authors from an unmatched comparison.

## Research basis

- NCST report, *Developing an Efficient Dispatching Strategy to Support Commercial Fleet Electrification* (2024): MILP and ALNS for energy-efficient dispatching with backhauls and time constraints. https://rosap.ntl.bts.gov/view/dot/73490/dot_73490_DS1.pdf
- Cheng et al. (2016), *Multi-period inventory routing problem under carbon emission regulations*: joint inventory, transport and emissions modeling. https://doi.org/10.1016/j.ijpe.2016.09.001
- Govindan et al. (2023), *A location-inventory-routing problem to design a circular closed-loop supply chain network with carbon tax policy for achieving circular economy*: bi-objective MILP, uncertainty scenarios and augmented epsilon-constraint optimization. https://doi.org/10.1016/j.ijpe.2023.108771
- EPA GHG Emission Factors Hub: https://www.epa.gov/climateleadership/ghg-emission-factors-hub
- EPA SmartWay Carrier Performance Ranking: https://www.epa.gov/smartway/smartway-carrier-performance-ranking

## Current implementation status

Updated 27 October 2026: the first refrigeration-and-delivery experiment is implemented on the new Cold-chain lab and Cold-chain data pages. It uses MultiPACK measured low-temperature rack profiles and NCST road matrices, with explicit thermal/fuel/cost assumptions. Its daily thermal-inventory MILP and restricted 2-opt route choices are documented in COLD_CHAIN_METHOD.md. The product-replenishment and ALNS extensions above remain proposed work. Earlier M5 results are preserved on the original pages. New results are modeled counterfactuals, not deployed savings.

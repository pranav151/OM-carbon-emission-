# Combined refrigeration and delivery experiment

## Question answered

Under explicitly stated thermal, fuel and cost assumptions, can a selected delivery network and a measured refrigeration load profile be served with lower modeled operational CO2? The experiment compares baseline, transport-only, cold-storage-only and combined decisions. It is a research counterfactual, not measured evidence of a company's achieved savings.

## Sources and reporting period

- MultiPACK field measurements, two Italian supermarkets: https://doi.org/10.18710/T5OHPR
- NCST freight cases derived from real California operations: https://doi.org/10.6086/D11974; downloaded 2023 release: https://zenodo.org/records/8117782
- EPA 2025 GHG Emission Factors Hub: https://www.epa.gov/climateleadership/ghg-emission-factors-hub

Six refrigeration profiles are available for inspection. Optimisation uses the three Rome profiles, which contain the required outside-temperature channel. The January records are dated **2020**, despite the filename saying 2019. Reported days are 12 August 2019, 11 September 2019 and 13 January 2020. They are not continuous monthly observations. Each is paired with the same selected freight case in a separate hypothetical replay; stops served across replays are not unique customers across three real days.

## Scope and linkage

Electricity covers the low-temperature compressor rack plus an explicitly synthetic docking heat load. Freight covers diesel combustion at a constant assumed litres/km rate. Other refrigeration/HVAC loads, vehicle refrigeration, refrigerant leakage, product embodied emissions, upstream fuel, infrastructure and retrofit capital costs are excluded. Values are CO2, not full CO2e. Cost is illustrative cost units (CU), not audited accounts or realised profit.

NCST goods are not identified as refrigerated. Pairing these shipments with a refrigeration facility is a modeled application. A source-aware daily ledger joins policies and profiles by scenario identity; hourly and shipment tables remain separate to avoid double-counting.

## Exact algorithms implemented

**Routing: constrained 2-opt local search.** For each source truck, reconstruct order using CSV row order. Reverse a contiguous stop segment only if all stops in that segment have the same delivery/pickup type. Accept a reversal when road distance decreases and both total route duration and peak load do not exceed that truck's reconstructed baseline. Repeat until no improving move exists. Preserve every stop, assigned truck, quantity and delivery/pickup block. Route duration uses provided road-time matrices plus source service durations interpreted as minutes. Load uses source weight interpreted as pounds. These are relative checks; actual fleet capacity, shift compliance and historical sequence are not certified. No global route-optimality claim is made.

**Refrigeration: thermal-inventory scheduling.** For each hour t, estimate an exogenous coefficient of performance:

`COP[t] = eta × (T_evaporator + 273.15) / (T_outside[t] + condenser_approach − T_evaporator)`

This is an assumed Carnot-based proxy, not fitted or validated performance of the transcritical CO2 plant. Observed low-temperature rack power supplies an inferred heat-load proxy:

`Q[t] = observed_hour_mean_power[t] × COP[t] × 1 hour`

The flexible thermal store is a hypothetical retrofit or validated-equivalent thermal flexibility, not measured installed capacity. Thermal-inventory balance is:

`S[t] = (1 − loss) × S[t−1] + COP[t] × electric_kWh[t] − Q[t] − docking_heat[t]`

with nonnegative power, a common power ceiling, `0 ≤ S[t] ≤ buffer_capacity`, and zero initial and final thermal inventory. The power ceiling is an assumed equipment rating: the greater of the baseline and all-2-opt direct-cooling hourly peaks, multiplied by configured headroom. It is common across policies and is not a measured nameplate rating. Docking adds configured kWh thermal per truck at its modeled return hour. This addition is the same assumed receiving activity across policies, not a claim that it appears in the Italian measurements.

**Combined scheduling: mixed-integer linear programming (Pyomo + HiGHS).** For each truck choose one of two candidate orders: reconstructed baseline or 2-opt. Binary route choices determine distance and return-hour cooling loads. Continuous power and thermal-inventory decisions satisfy the balance. Minimize electricity CO2 plus transport combustion CO2, subject to total operating cost no greater than the modeled baseline. COP is fixed per hour so the optimisation is linear; route choices make it mixed integer. This is a restricted candidate-route problem, not a full global inventory-routing solve.

**Four comparisons:** baseline fixes reconstructed routes and zero buffer; transport-only fixes 2-opt routes and zero buffer; cold-storage-only fixes reconstructed routes and optimises the thermal buffer; combined chooses routes and the cooling schedule together. Transport-only is reported even if its cost increases. Storage and combined policies enforce the baseline cost cap.

**Accounting:** `transport CO2 = km × assumed L/km × 10.21 / 3.785411784`. Electricity CO2 equals kWh × a fixed scenario grid factor. Default CAMX factor converts EPA's 436.655 lb/MWh by multiplying by 0.45359237/1000. This is a hypothetical virtual-site reference, not actual Italian emissions. Electricity costs use 0.20 CU/kWh and distance costs 1 CU/km by default; distance cost includes assumed operating costs rather than adding a duplicate fuel bill. The grid factor is constant, so carbon savings require lower energy or distance, not simply cheaper hours.

## What the OM concepts mean here

- Thermal inventory balance and capacity-constrained scheduling decide when to generate cooling.
- Vehicle routing with delivery/pickup blocks decides stop order.
- A shared operating-cost cap expresses a constrained carbon-versus-cost choice.
- Fixed start/end buffer levels prevent apparent savings from ending with less stored cooling.
- A separate audit checks thermal residuals, bounds, final stock and the cost cap. Routing checks preserve every source stop and relative time/load limits.

The present implementation does **not** optimise product replenishment quantities, shelf life, safety stock or multi-period stock levels. Product-inventory data is still absent. It is the first integrated refrigeration-and-delivery experiment inside the broader inventory project. No newly invented algorithm or optimal ML model is claimed. Perfect knowledge of each day's profile makes this a planning benchmark; operational forecasts and model-predictive control would require additional chronological data and validation.

## Interpreting outcomes

Reduction is `100 × (baseline − candidate) / baseline` for positive baselines. Overall percentages are calculated from totals, never by averaging daily percentages. The individual refrigeration contribution is displayed even if very small or zero. There is no hardcoded savings percentage.

The default 4-kWh-thermal buffer has a 1% hourly loss and a 25% power headroom assumption. Its economic feasibility requires separate capital/maintenance analysis. Food/product temperatures are not modeled, so thermal-balance feasibility is not evidence of safe deployment. A real pilot needs product-temperature limits, validated thermal capacity/COP, equipment constraints, room data and metered before/after verification under comparable loads.

For a scientific paper comparison, match objectives, units, constraints and data versions before claiming superiority. Published reductions are not this system's measured outcomes.

## Reproduce

Run `scripts/fetch_cold_storage.py` to retrieve and checksum-verify the seven public text files. Run `PYTHONPATH=src .venv/bin/python scripts/build_cold_chain.py` for the default scenario. Outputs include original-record transformations, hourly balances, candidate/selected routes, an integrated daily ledger and the settings manifest. The dashboard can run all four NCST cases and export each active scenario.

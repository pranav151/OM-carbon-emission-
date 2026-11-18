# Dashboard page guide

Use the sidebar to move between six pages. Each page includes a short explanation and an expandable guide. The charts and cards show a historical simulation, not live company operations.

## Overview

Your sustainability command centre. Connect transport emissions, operating cost and customer service in one view.

- **What it depicts:** The selected policy against the same baseline, across your chosen months.
- **What you can do:** Choose a planning approach and reporting months. Read the four headline measures, then explore the trends.
- **How to interpret it:** Positive savings mean reductions. Check service first: lower emissions are not a win if deliveries leave demand unmet.

- **Transport emissions:** Total simulated combustion CO₂ for the selected period. The baseline appears below the value.
- **Savings and increases:** The difference between the baseline and the selected policy. Labels change to “Additional” when the candidate performs worse.
- **Demand fulfilment:** Served units divided by observed sales. The check requires at least 95% and no worse service than the baseline.
- **Monthly and cumulative charts:** Bars compare the same months. The cumulative line adds daily carbon differences; below zero means additional emissions.

## Monthly savings

Trace cost and carbon outcomes month by month, with service and inventory alongside the financial picture.

- **What it depicts:** Signed monthly savings, cost components, unmet demand and stock carried into the next month.
- **What you can do:** Filter the months, inspect the scorecard and cost breakdown, then download the monthly results or daily ledger.
- **How to interpret it:** A negative reduction is an increase. Costs use scenario units (CU), not rupees or dollars.

- **Monthly scorecard:** Absolute differences and percentage reductions use baseline minus candidate. Service is reported for both policies.
- **Cost composition:** Transport, outlet holding and depot holding costs explain the operating-cost total. Shortage penalties are excluded.
- **Closing inventory:** Stock remaining at month end carries forward. Different final stock levels can explain part of a cost difference.
- **Exports:** Monthly results provide the summary; the daily ledger supplies the individual observations behind it.

## Model intelligence

Explore the evidence behind model selection, from intermittent-demand baselines to regularised machine learning.

- **What it depicts:** Ten forecasting configurations evaluated on the same chronological validation window.
- **What you can do:** Compare validation errors, select an outlet and model, then inspect its forecast against observed sales.
- **How to interpret it:** Lower RMSE is better on this window. The best ML model can still trail a statistical method; prediction accuracy does not guarantee savings.

- **Selection and reporting:** Validation determines the selected model. Calibration sets safety buffers. Reporting evaluates later outcomes without reselecting the winner.
- **RMSE and MAE:** RMSE penalises large misses more strongly. MAE is average absolute error; mostly-zero demand can reward near-zero forecasts.
- **Forecast comparison:** Observed sales are the recorded units, not necessarily unconstrained demand. Forecasts use information available before each forecast origin.
- **Best overall versus selected ML:** The overall winner can be TSB or another statistical method. Selected ML is the best candidate within the six ML configurations.

## Delivery planner

Explore how forecasts, stock limits and carbon constraints shape a feasible replenishment plan.

- **What it depicts:** A three-day plan: shipment quantities, vehicle routes, inventory movements, cost and emissions.
- **What you can do:** Choose a scenario, adjust operating assumptions, and generate a plan. Select a route day to inspect the network.
- **How to interpret it:** The network is illustrative, not a road map. These prospective settings do not rewrite the saved monthly experiment.

- **Plan settings:** Forecast model, holding costs, storage, pack size and minimum shipments change the planning inputs.
- **Carbon cap:** Limits total planning-horizon transport emissions. A cap that is too strict can make the scenario infeasible.
- **Route diagram:** Nodes are the depot and outlets; coloured paths show routes for the selected day, including return travel.
- **Independent audit:** The solver proposes a plan. A separate evaluator checks inventories, capacities, fleet, costs and emissions before displaying it as valid.

## Transformed data

Inspect the exact daily sales records and historical features that feed the forecasting pipeline.

- **What it depicts:** 9,565 outlet-day records: original sales, calendar fields, lagged observations and rolling statistics.
- **What you can do:** Filter outlets and periods, reveal all 27 columns, or download the complete transformed CSV.
- **How to interpret it:** Lag and rolling features use earlier days only. Early missing values stay blank; zeros remain genuine zero-sales observations.

- **One row, one outlet-day:** The fixed household SKU is reshaped from daily source columns into a chronological table for five stores.
- **Feature construction:** Calendar fields describe the forecast date. Lag and rolling statistics only use preceding sales observations.
- **Phase and readiness:** Phase marks training, validation, calibration, evaluation or later records. Features-ready requires 28 earlier observations.
- **Download behaviour:** The CSV download includes the complete dataset, regardless of preview filters. The table is an inspection view, not a data editor.

## Research & algorithms

Follow the research foundations, exact computational methods and boundaries behind every result.

- **What it depicts:** Published sources, implemented equations, model settings and the limits of the current experiment.
- **What you can do:** Use the tabs to explore papers, exact algorithms, and outcomes. Follow source links for the original research.
- **How to interpret it:** Research motivates the methods; published savings are not our results. This is transport combustion CO₂, not a full corporate carbon inventory.

- **Research foundation:** Inventory-routing and intermittent-demand papers motivate the decision model and forecasting baselines.
- **Exact algorithms:** Documents feature definitions, model parameters, time windows, routing enumeration, MILP constraints and replay accounting.
- **Outcomes and boundaries:** Reports measured simulation results alongside data, geography, emissions-scope and service limitations.
- **Sustainable development:** SDGs 12 and 13 provide context for resource use and climate decisions. The prototype does not certify progress against UN indicators.

## Visual interactions

Hover over chart points for exact values. Use the chart toolbar to zoom, reset or export an image. On small screens, expand the sidebar using the top-left arrow. The layout stacks automatically; animated effects respect your operating system’s reduced-motion preference.

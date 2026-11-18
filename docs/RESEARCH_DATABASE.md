# Sustainable inventory research database

This database supports research into joint transport, refrigerated inventory and energy management. It contains **real source records and a separate synthetic integration scenario**. It is not a company's operational database, a live feed, a validated digital twin, or evidence of achieved savings.

## Open the data

- `outputs/research_database/sustainable_inventory.sqlite`: relational database with primary keys, foreign keys and an `optimization_hourly` view.
- `outputs/research_database/csv/`: complete exports of every analysis/scenario table, readable in a spreadsheet application. These exports are not truncated previews.
- `outputs/research_database/validation_report.json`: coverage, checks, missing-data handling and a precisely scoped composition calculation.
- `outputs/research_database/scenario_config.json`: editable scenario assumptions used for this build.
- `outputs/research_database/csv/field_dictionary.csv`: field types, units, origins and populated-cell counts.
- `outputs/research_database/csv/optimization_factors.csv`: ten factors, candidate OM algorithms, decisions, constraints and evidence limitations.
- `outputs/research_database/csv/source_files.csv`: original-file paths and SHA-256 checksums.

The compact review ZIP contains the database, exports, configuration and documentation. The separate full source ZIP preserves the original downloaded files, including **all original ORNL measurement columns at their original sampling frequency**. SQLite contains selected ORNL channels aggregated to one-minute means, not all raw ORNL channels. MultiPACK's SQL table also contains selected standardized fields; all original columns remain in its source files.

## What is real

| Source | Evidence and use | Important boundary |
|---|---|---|
| [VTT](https://doi.org/10.17632/myyf72mpw9.1) | Four complete electricity files: two stores at 15-minute and hourly resolution. Original values, missing cells and source rows retained. | The two resolutions overlap; never add both. Source headers do not explicitly state units or time zones. |
| [ORNL](https://doi.org/10.6084/m9.figshare.13232627) | Five baseline and six fault experimental CSVs, and provider processing code (archived, never executed). Full download matches repository MD5. | Real laboratory experiments, not a year of warehouse operation. The paper counts a reused baseline twice; repository contains eleven distinct measurement CSVs. |
| [MultiPACK](https://doi.org/10.18710/T5OHPR) | Six original field-measurement files with source documentation. | Two supermarkets and six sampled site-days, not continuous months. January filenames say 2019 but timestamps are January 2020. |
| [UC Riverside](https://zenodo.org/records/8117782) | Four daily cases based on real operations; original stop records and provider-generated road matrices. | Not confirmed refrigerated freight. Matrices are calculations, not GPS observations. Distances are metres and durations seconds in raw files. |
| [EPA Hub](https://www.epa.gov/climateleadership/ghg-emission-factors-hub) | Complete 2025 workbook; diesel factor 10.21 kg CO2/US gallon is used, converted to kg CO2/litre. | Combustion CO2 only in this implementation; no CH4, N2O or upstream fuel impact. |
| [EPA SmartWay](https://www.epa.gov/smartway/smartway-carrier-performance-ranking) | Complete archived carrier-data workbook for 2022. | Reference material only. Not treated as exact fuel logs of UC Riverside vehicles. |
| [Fingrid](https://data.fingrid.fi/en/datasets/265) | Source registered for future replacement of synthetic grid signals. | **Not downloaded:** API returned HTTP 401. No data from Fingrid are represented as measured in the database. |

VTT has 73,702 rows across its four overlapping files. Store 1 spans 2017-10-20 to 2018-06-08; store 2 spans 2017-05-17 to 2018-06-04. These date spans include missing values. MultiPACK contributes 8,634 selected-field records. Exact ORNL raw counts and file dates are in `source_coverage`.

## Integration and synthetic additions

The scenario uses 365 days from **2017-06-01 through 2018-05-31**, two fictional temperature zones and three fictional products. These are twelve simulated months, not twelve months of observed joint supply-chain operations. Dates are naive scenario labels with 24 hours per day, not a verified time-zone alignment of Finland and California.

The original sources have no shared company, facility, product or shipment key. They are therefore stored in separate source tables. Only the synthetic layer introduces shared `date`, `timestamp`, `trip_id`, `product_id` and `zone_id` keys. Orders link to the source node through `source_node_key`; hourly inputs link to VTT through `source_record_id`.

1. **Electricity replay.** Use only store 2's hourly `refrigeration` channel. Preserve the original value in `source_power_value`, including nulls. An unverified scenario conversion of **1 source unit = 1 kW** and a scale factor of 4 define a virtual facility; this does not establish the real store's kWh or carbon footprint. Missing hours use at most six hours of forward fill, then the median of up to 28 earlier observations for the same hour, then an explicit fallback. Each method is recorded. No future values fill earlier gaps.
2. **Demand and routes.** Cycle the four provider cases through the scenario calendar. Interpret source weights as pounds and service durations as minutes as explicit assumptions. Rescale mass by 0.65 and seeded daily variation (normal mean 1, standard deviation 0.08, clipped to 0.7–1.3); this makes the virtual loads feasible within the assumed 30,000 kg trucks. Original source weights stay unchanged. Allocate delivery mass to three products in fixed shares. Pickup mass represents hypothetical return freight/packaging and is not added to saleable product inventory.
3. **Inventory.** Initial stock is 150,000 kg allocated by product shares. A periodic-review baseline targets three days of trailing demand, with a two-day supplier lead time. FEFO depletes earliest-expiring lots. Expired stock is disposed of. Emergency receipts are explicitly recorded and charged; they are not free service-level improvements. Pending orders after the scenario end remain in `pipeline_closing_kg`.
4. **Inbound transport.** Daily supplier loads use the ceiling of receipt mass divided by 20,000 kg per trip. Distance, duration, fuel and reefer operation are synthetic parameters; these costs and emissions are included in daily totals. Supplier routing is not borrowed from unrelated observed deliveries.
5. **Cold storage.** Chilled/frozen zones split the replayed load 35%/65%. Incoming-stock heat depends on receipt mass, assumed specific heat and temperature difference. Dispatch, return and supplier events add door heat. Fans, lights and four defrost events per day add electrical demand and internal heat. The baseline holds the assumed target temperature through an idealised hourly thermal balance.
6. **Signals and finance.** Ambient temperature, grid carbon intensity, electricity tariffs, diesel price, selling/purchasing prices, holding cost and penalties are synthetic. The scenario uses fictional currency units (CU), not reported company money. No grid API is live. Prices and carbon intensity have different daily patterns, so saving money does not automatically minimise carbon.
7. **Leakage and spoilage.** R744 charge and annual leakage are assumptions. Leakage is an annual allocation, not hourly leak detection. Spoilage embodied emissions are separately identified and excluded from the operational footprint to avoid silent scope changes. No food safety, microbial shelf-life or refrigerant leakage model has been validated.

All parameter values are exposed in `scenario_parameters`, `cold_zones`, `products`, `vehicles` and `suppliers`. Hard-coded zone/product design values in the builder are also materialised in these tables. Rebuild after changing the configuration or builder; editing a CSV alone does not recompute other tables.

## Connections and equations

`source nodes → scenario orders → inventory/replenishment → inbound trips and incoming cooling load`

`source road matrices → scenario truck stops → fuel, duration and door events`

`source electricity shape + incoming heat + door events + auxiliaries → zone cooling demand`

`zone demand + carbon intensity + tariffs → electricity carbon and cost`

The baseline equations are:

```
closing_stock = opening_stock + receipts - shipped - spoilage
next_temperature = temperature + (total_heat - COP * compressor_kW * hours) / thermal_capacity
electricity_kWh = compressor_kW * hours + fan_kWh + lighting_kWh + defrost_kWh
truck_litres = sum(leg_km * (empty_L_per_km + full_load_increment * load/capacity))
               + service_hours * idle_L_per_hour + trip_hours * reefer_L_per_hour
transport_CO2 = fuel_litres * (10.21 / 3.785411784)
electricity_CO2 = sum(hourly_kWh * hourly_grid_factor)
partial_operational_CO2e = outbound_and_return_CO2 + inbound_CO2 + electricity_CO2 + refrigerant_CO2e
expanded_footprint = partial_operational_CO2e + spoilage_embodied_CO2e
modelled_contribution = sales_revenue - shipped_COGS - spoilage_writeoff - operating_cost
```

CO2 is being used as a partial greenhouse-gas inventory; `partial_scope` in column names is intentional. Carbon cost is zero by default, because avoided emissions do not automatically imply a carbon tax or cash saving. Modelled contribution excludes rent, capital costs, fixed salaries and taxes and must not be called net company profit. Procurement cash outflow is reported separately from COGS to avoid charging stock purchases and sales consumption twice.

The replayed refrigeration load defines the synthetic background heat. It is not an independently identified thermal model, and its fitted baseline temperature is not a measured temperature. Door, incoming-product and auxiliary heat are additional virtual loads; this is not a decomposition of the actual VTT store's electricity consumption.

## What the optimisation can test later

The database prepares inputs for route sequencing, dispatch timing, replenishment and consolidation, FEFO, thermal scheduling, tariff/carbon trade-offs, auxiliary scheduling, condition-based maintenance, leakage scenarios, and demand/load forecasting. It does not implement or validate all those algorithms. `optimization_factors` identifies the candidate OM methods and each data limitation.

The intended objective is to minimise emissions subject to cost and service constraints. A fair comparison must use the same orders, baseline and carbon boundary. Preserve terminal usable stock and thermal state; otherwise a solver can appear to save energy merely by leaving a warm room or empty warehouse. Changes to receipt/dispatch schedules must recompute product and door heat. Future realised data must not be exposed to a causal controller; a perfect-information solution is only a benchmark.

No ML is trained in this build. For the fixed calendar, `hourly_inputs.evaluation_split` marks June–January as training, February–March as validation, and April–May as testing. This does not mean every month has complete measurements. When forecasting real load, prefer observed VTT targets and report missingness; forecasts of generated product demand measure performance on a synthetic scenario. For ORNL, split by whole experiment, not random adjacent seconds. File role is not a verified time-resolved fault-onset/severity label.

## Credibility and percentage of synthetic data

All source-file observations are retained without generated replacement values. Standardised/aggregated source tables are derived, and their raw originals remain available. Every row in the combined operational scenario belongs to a **synthetic integration**, even if some values were replayed from real records.

There is no meaningful universal percentage obtained by adding millions of laboratory sensor cells to a few synthetic business fields. The report instead gives:

- per-source counts and date coverage;
- the count of replayed versus imputed hourly load inputs;
- an explicit non-null **numeric-cell composition** across five named scenario tables, with metadata excluded.

The last percentage is a documented dataset-composition statistic, not a measure of realism, accuracy or validation. The source replay/imputation column remains a separate mixed category. Use the raw source provenance and the scenario composition together when explaining the work academically.

No optimisation results, reduction percentages or measured savings are manufactured. `baseline_monthly` has twelve baseline rows; savings should be calculated only after a feasible optimiser is evaluated. Simulated savings must be labelled estimated potential. A real operational claim needs deployment and a suitably adjusted measurement baseline.

## Rebuild and query

Run from the project directory:

```sh
.venv/bin/python scripts/fetch_combined_sources.py
.venv/bin/python scripts/build_research_database.py
.venv/bin/python -m pytest tests/test_research_database.py -q
.venv/bin/python scripts/package_research_database.py
```

The earlier MultiPACK/NCST/EPA fetch scripts supply those already-downloaded sources. The builder creates a temporary SQLite file and publishes it only after validation. CSV exports are intended for inspection; SQLite is the relational source of truth. Example SQL is included in `queries.sql` in the output package. Database keys enforce relationships. Further checks cover mass balance, capacity, thermal/electrical accounting, source checksums, and monthly reconciliation.

Original VTT data are CC BY-NC 3.0; ORNL data are CC BY 4.0; preserve source licensing and attribution. This package does not relicense third-party source data.

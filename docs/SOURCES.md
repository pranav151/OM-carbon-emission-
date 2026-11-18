# Source audit and references

Audited for this build on 26 October 2026. Downloaded files and SHA-256 hashes are recorded in `data_manifest.json`.

## Inventory benchmark — downloaded and parsed

- Authors' repository: https://github.com/ariannesilvamundim/RAIRO-OR
- Archive: https://raw.githubusercontent.com/ariannesilvamundim/RAIRO-OR/main/instances.zip
- Selected member: `instances/archetti2007/L3/abs1n5.dat`.
- Archive format document: `instances/archetti2007/readme.doc`, inspected locally with macOS `textutil`. Embedded distance equation is not preserved in plain-text conversion; the text explicitly mentions nearest-integer rounding. Euclidean-distance conventions were reconciled with DIMACS. See the exact implemented convention in the assumptions register.
- DIMACS reference: https://dimacs.rutgers.edu/programs/implementation-challenges/vehicle-routing/implementation-challenge-vehicle-routing/inventory-routing

The archive supplies numerical inventory, capacity, coordinates and constant consumption/supply. It does not supply the historical demand needed for ML. The repository's `Full.csv` is not used as inventory/sales history. No explicit dataset reuse licence was found in the repository listing/README; raw files are retained locally and excluded from Git.

## Main research reference — author full text inspected in v0.2

Mundim, A. A. S., Santos, M. O., & Morabito, R. (2025). *Sustainable solutions analysis of a bi-objective green inventory routing problem with heterogeneous fleet and different types of fuels.* RAIRO–Operations Research, 59, 549–578. https://doi.org/10.1051/ro/2024162

Accessible listing: https://www.researchgate.net/publication/383196437_Sustainable_solutions_analysis_of_a_bi-objective_green_inventory_routing_problem_with_heterogeneous_fleet_and_different_types_of_fuels

Direct publisher access failed in the first build. During v0.2, the accessible author full-text listing exposed Section 4, Sections 5.1/5.3 and Table 5. The monthly replay imports only Table 5's diesel factor (2.66 kg CO₂/L). Other physical inputs remain assumptions. No published outcomes or complete paper formulation are claimed to be reproduced. The fixed-consumption equation is simpler than the paper's full vehicular equation. See `RESEARCH_REVIEW.md` for the updated audit and additional sustainable-operations references.

## Forecast data — M5, downloaded and extracted

- Organisers' repository and guide: https://github.com/Mcompetitions/M5-methods
- Original competition description: https://www.kaggle.com/competitions/m5-forecasting-accuracy/data
- Competition rules: https://www.kaggle.com/competitions/m5-forecasting-accuracy/rules
- Download mirror: https://zenodo.org/records/10203108
- Files: `sales_train_validation.csv` and `calendar.csv`.

M5 provides daily unit sales per product/store and a calendar. The local extraction preserves one fixed household SKU at five stores, with no manufactured demand. Inventory, network and fleet data are not present and are therefore supplied as independent scenario assumptions. The original source says data are subject to competition rules; this project retains raw data locally for academic work and does not grant redistribution/commercial rights. The mirrored files are not treated as a separate unrestricted licence.

UCI Online Retail II was considered but not used: its transaction/customer structure is less directly aligned to same-product store-level daily forecasting. No UCI data are downloaded or mixed into results.

## Software and methodological references

- Pyomo / HiGHS interface: https://pyomo.readthedocs.io/en/stable/api/pyomo.contrib.appsi.solvers.highs.Highs.html
- HiGHS: https://highs.dev/
- scikit-learn time-series splitting: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Streamlit: https://docs.streamlit.io/

The project implements explicit chronological origins rather than randomly splitting time series. Code and local tests are the source of truth for implementation details. Scientific conclusions require broader experiments than the first demo run.

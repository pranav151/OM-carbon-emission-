# Carbon Operations — Sustainable Inventory

The current dashboard compares truck routing and cold-storage scheduling using a traceable hybrid research database. It covers 365 scenario days, June 2017–May 2018, with two temperature zones. It is a conditional, perfect-information simulation benchmark, not measured company performance or a forecast of deployment savings.

## Open the dashboard

```sh
.venv/bin/streamlit run app.py --server.port 8501
```

Open http://127.0.0.1:8501/. Use the sidebar arrow if navigation is collapsed on a narrow screen.

| Page | What it shows |
| --- | --- |
| Impact overview | Annual or selected-period savings, carbon contributions and four comparable policies |
| Monthly outcomes | Monthly carbon, operating costs, percentage reductions and complete CSV exports |
| Cold storage | Hourly compressor schedules, temperature bounds, heat inputs, synthetic tariffs and grid signals |
| Transport & logistics | Original and selected stop sequences, load paths, road-matrix distances and fuel |
| Inventory & service | Demand, replenishment, FEFO stock balance and service; fixed across comparisons |
| Data & methods | Complete database tables, source links, synthetic composition, exact algorithms and audits |

The interface includes responsive glass panels, animated decoration, interactive Plotly charts, period/policy controls and reduced-motion support.

## Verified default benchmark

| Measure | Baseline | Combined | Reduction |
| --- | ---: | ---: | ---: |
| Partial-scope carbon (t CO2e) | 571.43 | 519.99 | 9.00% |
| Operating cost (fictional CU) | 794,591.84 | 760,427.73 | 4.30% |

These are model estimates conditional on synthetic operating parameters, grid carbon, tariffs and thermal flexibility. Actual field savings are unknown. The baseline routes are reconstructed from source row order. The cooling optimiser has perfect information; no ML forecast feeds this evaluation. Inventory optimisation, spoilage reductions and net profit are not claimed.

## Data and methods

VTT electricity records and UC Riverside freight cases supply real source patterns. ORNL laboratory measurements and MultiPACK field measurements remain separately inspectable; they do not calibrate this evaluation's thermal model. The sources concern unrelated sites/dates and are joined through a declared synthetic scenario, not represented as one real company's records.

- `outputs/research_database/sustainable_inventory.sqlite`: 31 relational tables, field dictionary and provenance.
- `outputs/research_database/csv/`: complete transformed tables.
- `outputs/research_database_review.zip`: database, CSVs and documentation.
- `outputs/research_database_original_sources.zip`: original downloaded files.
- `outputs/research_results/`: daily, monthly, hourly, route and feasibility results.
- [Dataset methodology](docs/RESEARCH_DATABASE.md) and [dashboard algorithms and limitations](docs/RESEARCH_DASHBOARD.md).

Routing uses fuel-aware first-improvement 2-opt within same-type stop blocks. Cooling uses SciPy HiGHS linear programming with thermal balances, temperature/power bounds, baseline electricity-cost caps and equal terminal temperatures. Routing updates receiving heat before cooling is solved. This staged procedure is not a globally optimal joint inventory-routing model.

## Rebuild and validate

With the original source files in place:

```sh
.venv/bin/python scripts/build_research_database.py
PYTHONPATH=src .venv/bin/python -m green_inventory.research_evaluation
PYTHONPATH=src .venv/bin/python -m pytest tests/test_research_database.py tests/test_research_evaluation.py tests/test_app.py -q
.venv/bin/python scripts/package_research_database.py
```

The dashboard verifies the database fingerprint and refuses mismatched or failed evaluation results. Fifteen checks cover database integrity, source hashes, inventory continuity, fuel/thermal accounting, route matrices, aggregate reconciliation, constraint behavior and all six pages.

Earlier M5 and three-day prototypes are preserved in `legacy_app.py`. Their historical documentation is in [LEGACY_README.md](docs/LEGACY_README.md); they do not feed the current dashboard.

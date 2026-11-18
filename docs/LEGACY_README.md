# Legacy Green Inventory Planner (superseded dashboard)

A local sustainability analytics application connecting daily sales forecasts with integrated inventory and carbon-aware delivery planning. One product, five outlets, one depot; rolling three-day plans evaluated over January–March 2016. Python 3.11, Pyomo/HiGHS, scikit-learn, Streamlit and Plotly.

The v0.2 dashboard reports real simulated monthly outcomes, including negative savings and service failures. See `docs/OUTCOMES.md` for results and `docs/ALGORITHMS.md` for the exact methods. The inspectable transformed dataset is `outputs/transformed_demand.csv` (9,565 rows × 27 columns).

## Start the application

From this project directory:

```sh
.venv/bin/streamlit run app.py
```

Open http://127.0.0.1:8501. Overview and Monthly savings show verified historical simulation results. Model intelligence compares ten forecasting configurations. Delivery planner exposes interactive stock, fleet and carbon planning; click **Generate delivery plan** after settings change. Transformed data previews/downloads the CSV. Research & algorithms explains the methods, references and limitations.

The interface uses a dark liquid-glass visual theme, animated network artwork, responsive panels and matching interactive charts. Every screen has a “What you see / What you can do / How to read it” explanation and an expandable page guide. See `docs/DASHBOARD_GUIDE.md` for the full walkthrough. Reduced-motion preferences disable decorative animation.

## Fresh installation

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
.venv/bin/python scripts/download_data.py
PYTHONPATH=src .venv/bin/python -m green_inventory.cli prepare-sales
LOKY_MAX_CPU_COUNT=1 .venv/bin/python scripts/run_monthly.py
.venv/bin/python -m pytest -q
.venv/bin/streamlit run app.py
```

Alternatively, install the project with `uv pip install --python .venv/bin/python -e '.[test]'` from `pyproject.toml`. The full transitive environment used in development is pinned in `requirements.lock.txt`.

The downloader verifies SHA-256 hashes and leaves original files unchanged. M5 sales are about 120 MB. `--benchmark-only` skips M5. Source datasets and derived sales remain local and are excluded from Git; see reuse notes in `docs/SOURCES.md` before redistribution.

## Reproduce experiments

```sh
PYTHONPATH=src .venv/bin/python -m green_inventory.cli audit
PYTHONPATH=src .venv/bin/python -m green_inventory.cli benchmark
PYTHONPATH=src .venv/bin/python -m green_inventory.cli compare
PYTHONPATH=src .venv/bin/python -m green_inventory.cli forecast
PYTHONPATH=src .venv/bin/python -m green_inventory.cli simulate --days 7 --time-limit 10
.venv/bin/python scripts/check_instances.py
LOKY_MAX_CPU_COUNT=1 .venv/bin/python scripts/run_monthly.py
```

Outputs are saved under `results/`. `results/sustainability/` contains the v0.2 model study, 273 daily policy decisions, monthly/daily ledgers, inventory execution, routes and every full planning audit. Its completed study manifest is written only after all three policies finish. The expanded reporting window is retrospective and partially overlaps the earlier v0.1 evaluation; it is not a newly blind test.

## What is implemented

- Strict parser for the authors' five-outlet Archetti archive, including its different header/depot numbering.
- Fixed SKU `HOUSEHOLD_1_001` from M5; five alphabetical store IDs, 1,913 observed daily sales records per store. No fabricated history or upsampling.
- Ten configurations: seasonal naïve, moving average, Croston–SBA, TSB and standard/regularised variants of random forest, Poisson boosting and Poisson regression. The monthly study selects by validation RMSE, calibrates a common buffer separately, then reports three months of outcomes.
- Exact small-instance inventory-routing MILP using shortest tours for all customer subsets. Joint delivery quantities, dates and vehicle selection. Depot and outlet balances, pre-consumption storage, fleet limits, optional MOQ/pack sizes, and terminal inventory.
- Cost minimisation, emissions minimisation, secondary tie-breaking and feasible carbon-cap comparisons. The cap sweep appears only when the endpoints differ.
- Greedy stock-coverage baseline with explicit failure reporting.
- Independent feasibility/cost/emissions evaluator; never reads solver objective expressions.
- Rolling historical simulation: execute one period, apply observed sales, record shortages, replan.
- Six redesigned dashboard screens, monthly percentage/absolute reductions, cumulative emissions difference, service qualification, cost components, CSV/JSON exports and traceable data provenance.

## Interpretation boundaries

1. **Benchmark mode** uses coordinate-distance/cost units and does not claim physical CO₂. Its default minimum-stock terminal policy is explicit; it is not a reproduction claim for the whole research paper.
2. **Illustrative mode** uses declared distance, fleet, fuel and cost assumptions. These are not verified industrial parameters.
3. **M5 mode** forecasts real observed sales, then maps stores to a separate illustrative network. The geographic coordinates, fleet, capacities and stock are not Walmart operational records.
4. Observed sales can be censored by unknown stockouts; unconstrained demand is unavailable. Simulated shortages are against observed sales as a demand proxy.
5. Forecast coverage is not an actual-service guarantee. Empirical residual buffers do not establish a nominal 90% service level.
6. Simulation operating cost excludes a shortage penalty; unmet units/fill rate and end stock must be assessed alongside cost and emissions. A policy serving less demand is not automatically better.
7. Exact subset-route enumeration supports at most 10 customers. Larger networks, load-dependent emissions, travel times, multiple products and production deployment are outside this prototype.
8. The dashboard reads saved monthly experiments; changing prospective planner settings does not silently rewrite historical results. Re-run `scripts/run_monthly.py` to rebuild them. The old CLI forecast/simulate commands preserve the first prototype workflow; current monthly results use the new script.

See `docs/ARCHITECTURE.md`, `docs/FORMULATION.md`, `docs/ASSUMPTIONS.md`, `docs/SOURCES.md` and `docs/BUILD_STATUS.md`.


## Integrated refrigeration and delivery experiment (27 October 2026)

The default dashboard now opens **Cold-chain lab**. **Cold-chain data** exposes 8,634 measured records from six MultiPACK site profiles. The new model pairs three Rome profiles with a selected NCST freight case in a hypothetical scenario. It uses Pyomo/HiGHS thermal-buffer scheduling and 2-opt route candidates, with separately labelled measured inputs and assumed operating parameters. These results are modeled counterfactuals, not achieved company savings. Original M5 pages and results remain available.

Method and limitations: `docs/COLD_CHAIN_METHOD.md`. Source provenance: `data/research/cold_storage/README.md`. Reproduce the default study with `PYTHONPATH=src .venv/bin/python scripts/build_cold_chain.py`; outputs are in `outputs/cold_chain/`.

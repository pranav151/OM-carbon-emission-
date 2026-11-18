# Transformed demand CSV

Deliverable: `outputs/transformed_demand.csv`. 9,565 records, 27 columns, 1,913 dates, five stores. Total observed sales = 3,016 product units. Source SKU is fixed at `HOUSEHOLD_1_001`; stores are CA_1, CA_2, CA_3, CA_4, TX_1. Date range: 29 January 2011–24 April 2016.

Source: M5 `sales_train_validation.csv` joined to `calendar.csv`, downloaded from https://zenodo.org/records/10203108. Original organisers: https://github.com/Mcompetitions/M5-methods. Dataset terms remain those of the M5 competition. The CSV is a local academic derivative, not a grant of redistribution rights.

| Column | Meaning / unit |
|---|---|
| date | ISO date, original M5 calendar |
| product_id | Original product identifier |
| outlet | Original store identifier |
| store_index | Alphabetical outlet position 0–4 |
| observed_sales_units | Original daily product-unit sales, unchanged |
| day_of_week | Monday=0 through Sunday=6 |
| month_number | Calendar month 1–12 |
| lag_1, lag_7, lag_14, lag_28 | Sales at the corresponding earlier date |
| past_7_day_mean, past_28_day_mean | Arithmetic mean of earlier observed days; excludes current day |
| past_28_day_std | Earlier 28-day population standard deviation, ddof=0 |
| past_28_day_nonzero_share | Share of preceding 28 days with positive observed sales |
| outlet_onehot_0 … outlet_onehot_9 | Fixed model encoding; columns 5–9 are zero in the five-outlet case |
| phase | training / validation / calibration / evaluation / after_evaluation |
| features_ready | Whether the full 28-day prior context exists |

First 28 days/store produce 140 rows with incomplete lag history. Missing feature values remain blank; they are not zero-filled. Observed sales are complete. Phase labels document reporting boundaries, not a promise that every historical row is used for every fit: model training uses a sliding maximum of 730 days at each origin.

The target remains observed sales, not inferred unconstrained demand. No imputed promotions, weather, routes or stock levels are added to this CSV. Scenario assumptions are maintained separately.

Rebuild with the bundled Python runtime and `.artifact-build/prepare_data.py`, followed by the bundled Node runtime and `.artifact-build/export_csv.mjs`. The latter authors and inspects the typed data with Artifact Tool before serializing the CSV.

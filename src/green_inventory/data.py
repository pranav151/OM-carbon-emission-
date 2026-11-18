"""Strict benchmark parsing and historical sales extraction; no fabricated history."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import math
import pandas as pd
from .schema import Customer, Vehicle, Scenario

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_URL = "https://github.com/ariannesilvamundim/RAIRO-OR"
INSTANCE = "instances/archetti2007/L3/abs1n5.dat"


def parse_archetti(text: str, name: str = INSTANCE) -> Scenario:
    rows = [r.split() for r in text.splitlines() if r.strip()]
    if len(rows[0]) != 3:
        raise ValueError("Expected the observed 3-field Archetti header, not the DIMACS format")
    count, horizon, capacity = map(int, rows[0])
    # Archive README calls n retailers, but actual files include the depot in n.
    if len(rows) != count + 1 or len(rows[1]) != 6:
        raise ValueError("Header count must equal depot plus customer rows")
    depot = list(map(float, rows[1]))
    if depot[0] != 1:
        raise ValueError("This archive variant uses depot ID 1")
    customers = []
    for row in rows[2:]:
        if len(row) != 8:
            raise ValueError("Expected 8 fields in each customer record")
        node, x, y, initial, upper, lower, demand, holding = map(float, row)
        if not node.is_integer() or node <= 1:
            raise ValueError("Invalid source customer ID")
        customers.append(Customer(str(int(node)), x, y, initial, upper, lower,
                                  holding, [demand] * horizon, lower))
    s = Scenario(name, customers, [Vehicle("V1", capacity, 1.0)],
                 [depot[4]] * horizon, depot[3], depot[5], (depot[1], depot[2]),
                 mode="benchmark", round_distances=True, distance_unit="coordinate unit",
                 provenance={
                     "source": BENCHMARK_URL, "member": name,
                     "inventory_and_demand": {"origin": "benchmark", "unit": "product units", "source": name},
                     "coordinates": {"origin": "benchmark", "unit": "unspecified coordinate units", "source": name},
                     "holding_costs": {"origin": "benchmark", "unit": "cost units / product unit / period", "source": name},
                     "vehicle_capacity": {"origin": "benchmark", "unit": "product units", "source": "header C"},
                     "fleet": {"origin": "scenario assumption", "value": "one vehicle; header has no fleet count"},
                     "distance_cost": {"origin": "documented convention", "value": "nearest-integer Euclidean; 1 cost unit / coordinate-distance unit", "source": "archive readme.doc + DIMACS"},
                     "terminal": {"origin": "scenario assumption", "value": "customer minimum; depot 0"},
                     "timing": {"origin": "documented convention", "value": "supply and delivery before consumption; end-period holding cost"},
                     "format_reconciliation": "Actual n includes depot; README mentions absent np. Strictly check actual row count.",
                     "license": "No explicit repository dataset licence found; raw data excluded from Git.",
                 })
    s.validate()
    return s


def load_benchmark(member=INSTANCE):
    archive = ROOT / "data/raw/rairo/instances.zip"
    with ZipFile(archive) as z:
        return parse_archetti(z.read(member).decode(), member)


def illustrative_benchmark():
    s = load_benchmark()
    config = json.loads((ROOT / "configs/illustrative.json").read_text())
    s.mode = "illustrative"
    s.name = "Five-outlet benchmark · illustrative transport"
    s.distance_scale = config["km_per_coordinate_unit"]
    s.distance_unit = "km"
    s.round_distances = False
    s.vehicles = [Vehicle(**v) for v in config["vehicles"]]
    s.provenance["transport"] = config
    s.validate()
    return s


def prepare_m5(item="HOUSEHOLD_1_001", stores=5):
    """Fixed SKU; alphabetical store selection, independent of future sales values."""
    raw = ROOT / "data/raw/m5"
    selected = []
    for chunk in pd.read_csv(raw / "sales_train_validation.csv", chunksize=1000):
        selected.append(chunk[chunk.item_id.eq(item)])
    rows = pd.concat(selected)
    if rows.empty:
        raise ValueError(f"Item not present: {item}")
    ids = sorted(rows.store_id.unique())[:stores]
    rows = rows[rows.store_id.isin(ids)]
    calendar = pd.read_csv(raw / "calendar.csv", usecols=["d", "date"])
    day_cols = [c for c in rows if c.startswith("d_")]
    long = rows.melt(id_vars=["item_id", "store_id"], value_vars=day_cols,
                     var_name="d", value_name="sales").merge(calendar, on="d", validate="many_to_one")
    wide = long.pivot(index="date", columns="store_id", values="sales").sort_index()
    wide.index = pd.to_datetime(wide.index)
    wide = validate_history(wide)
    output = ROOT / "data/processed"
    output.mkdir(parents=True, exist_ok=True)
    wide.to_csv(output / "m5_history.csv", index_label="date")
    meta = {
        "dataset": "M5 daily unit sales", "item": item, "stores": ids,
        "selection": "SKU fixed before modelling; first five alphabetical store IDs",
        "source": "https://github.com/Mcompetitions/M5-methods",
        "download_mirror": "https://zenodo.org/records/10203108",
        "license": "Subject to M5 competition rules; local academic use, no raw redistribution",
        "target": "Observed unit sales, NOT unconstrained demand; no stock-availability records",
        "transformations": "One fixed non-food SKU, no rescaling, no imputation; original sales retained",
        "network": "Independent illustrative network; not real Walmart routes or inventory",
        "rows": len(wide), "start": str(wide.index.min().date()), "end": str(wide.index.max().date()),
    }
    (output / "m5_metadata.json").write_text(json.dumps(meta, indent=2))
    return wide


def validate_history(df):
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if df.empty or df.index.has_duplicates or df.columns.has_duplicates:
        raise ValueError("History must have unique dates and outlet columns")
    df = df.sort_index().astype(float)
    expected = pd.date_range(df.index[0], df.index[-1], freq="D")
    if not df.index.equals(expected):
        raise ValueError("Daily history has gaps; supply explicit observed zero-sales days")
    if df.isna().any().any() or not df.map(math.isfinite).all().all() or (df < 0).any().any():
        raise ValueError("Sales must be finite, nonnegative and complete")
    if len(df.columns) > 10:
        raise ValueError("At most 10 outlets supported")
    return df


def load_history():
    return validate_history(pd.read_csv(ROOT / "data/processed/m5_history.csv", index_col="date", parse_dates=True))


def historical_scenario(history, prediction, buffer=None):
    """All physical assumptions depend only on past sales or fixed configuration."""
    history = validate_history(history)
    if list(history.columns) != list(prediction.columns) or prediction.index.min() <= history.index.max():
        raise ValueError("Forecast must follow history and use the same outlets")
    base = illustrative_benchmark()
    buffer = buffer if buffer is not None else pd.Series(0.0, index=history.columns)
    customers = []
    for index, name in enumerate(history.columns):
        c = base.customers[index % len(base.customers)]
        mean = float(history[name].tail(56).mean())
        peak = float(history[name].tail(180).max())
        capacity = max(10.0, math.ceil(7 * mean), math.ceil(3 * peak))
        initial = min(capacity, math.ceil(2 * mean))
        demand = [float(math.ceil(max(0.0, x))) for x in prediction[name]]
        customers.append(Customer(name, c.x, c.y, initial, capacity, float(buffer[name]),
                                  0.1, demand, float(buffer[name])))
    scale = max(20, math.ceil(sum(history.tail(56).mean()) * 3))
    s = Scenario("M5 forecast · illustrative network", customers,
                 [Vehicle("Compact", scale, 1.0, 0.10, 2.68, 2.0),
                  Vehicle("Truck", 2 * scale, 1.5, 0.20, 2.68, 3.0)],
                 [float(3 * scale)] * len(prediction), float(3 * scale), 0.01,
                 base.depot_xy, distance_scale=0.05,
                 provenance={
                     "sales": {"origin": "M5 observed input", "unit": "units/day", "source": "data/processed/m5_metadata.json"},
                     "demand": {"origin": "model output", "unit": "units/day", "value": "nonnegative forecast rounded upward"},
                     "physical_scenario": {"origin": "scenario assumption", "source": "docs/ASSUMPTIONS.md",
                        "value": "Archetti coordinates × 0.05 km; stores mapped alphabetically, not real locations"},
                     "inventory": {"origin": "scenario assumption", "unit": "units", "value": "capacity=max(10,7×past56 mean,3×past180 max); initial=2×past56 mean"},
                     "fleet": {"origin": "scenario assumption", "value": "Q=max(20,3×past56 total mean); vehicle capacities Q,2Q; daily depot supply 3Q"},
                     "holding": {"origin": "scenario assumption", "unit": "cost units/unit/day", "value": "outlet 0.1; depot 0.01"},
                     "transport": {"origin": "scenario assumption", "unit": "km, L/km, kgCO2/L, cost units", "value": "vehicles 0.10/0.20 L/km; 2.68 kgCO2/L; distance costs 1/1.5; dispatch 2/3, inclusive of fuel"},
                     "buffer": {"origin": "calibration output", "value": buffer.to_dict(), "unit": "units", "note": "empirical one-sided residual buffer; no service guarantee"},
                     "terminal": {"origin": "scenario assumption", "value": "outlet buffer; depot 0"},
                 })
    s.validate()
    return s


def manifest():
    result = []
    for p in sorted((ROOT / "data/raw").rglob("*")):
        if p.is_file():
            result.append({"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                           "sha256": hashlib.file_digest(p.open("rb"), "sha256").hexdigest()})
    (ROOT / "docs/data_manifest.json").write_text(json.dumps(result, indent=2))
    return result

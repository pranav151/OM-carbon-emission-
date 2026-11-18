"""Reproducible multi-month forecast selection and service-aware sustainability ledger."""
from copy import deepcopy
from pathlib import Path
from math import ceil
import hashlib
import json
import numpy as np
import pandas as pd
from .data import ROOT, load_history, historical_scenario
from .forecasting import MODELS, ML_MODELS, LABELS, forecast, backtest, accuracy
from .optimisation import solve, has_solution
from .evaluation import evaluate

OUT = ROOT / "results/sustainability"
START = pd.Timestamp("2016-01-01")
END = pd.Timestamp("2016-03-31")
HORIZON = 3
VERSION = "monthly-v2-fractional-demand-integer-deliveries"


def study(history):
    """Selection Oct 2015–Nov 2015; calibration Dec 2015; reporting Jan–Mar 2016."""
    start = history.index.get_loc(START)
    cal_start = start - 28
    val_start = cal_start - 56
    end = history.index.get_loc(END) + 1
    OUT.mkdir(parents=True, exist_ok=True)
    validation = []
    for model in MODELS:
        print(f"Validation: {model}", flush=True)
        validation.append(backtest(history, model, val_start, cal_start, HORIZON, HORIZON))
    val = pd.concat(validation, ignore_index=True)
    metrics = {m: accuracy(val[val.model.eq(m)]) for m in MODELS}
    # Choose expected-demand predictors using RMSE, avoiding a zero-favouring MAE-only choice.
    selected = min(MODELS, key=lambda m: metrics[m]["rmse"])
    selected_ml = min(ML_MODELS, key=lambda m: metrics[m]["rmse"])
    cal = pd.concat([backtest(history, m, cal_start, start, HORIZON, HORIZON)
                     for m in sorted(set(["moving_average", selected_ml, selected]))], ignore_index=True)
    cal["underprediction"] = cal.actual - cal.prediction
    # Same common buffer for all policies; calibrated before the reporting window.
    cumulative = cal.groupby(["model", "origin", "outlet"]).underprediction.sum().reset_index()
    buffers = cumulative.groupby(["model", "outlet"]).underprediction.quantile(0.95).clip(lower=0).unstack(0).max(axis=1).apply(np.ceil)
    test = []
    for model in MODELS:
        print(f"Reporting-window forecasts: {model}", flush=True)
        test.append(backtest(history, model, start, end, HORIZON, HORIZON))
    test = pd.concat(test, ignore_index=True)
    summary = {"version": VERSION, "selected_overall": selected, "selected_ml": selected_ml,
               "selection_metric": "Validation RMSE; test results never select the winner",
               "validation": metrics, "test": {m: accuracy(test[test.model.eq(m)]) for m in MODELS},
               "buffer": buffers.to_dict(), "horizon": HORIZON,
               "validation_start": str(history.index[val_start].date()), "validation_end": str(history.index[cal_start-1].date()),
               "calibration_start": str(history.index[cal_start].date()), "calibration_end": str(history.index[start-1].date()),
               "report_start": str(START.date()), "report_end": str(END.date()),
               "test_window_note": "Expanded retrospective evaluation; overlaps dates examined in v0.1. No claim of a newly blind test or causal impact.",
               "history_sha256": hashlib.sha256(history.to_csv().encode()).hexdigest()}
    for name, data in [("validation", val), ("calibration", cal), ("forecast_test", test)]:
        data.to_csv(OUT / f"{name}.csv", index=False)
    (OUT / "study.json").write_text(json.dumps(summary, indent=2))
    return summary


def monthly_scenario(history, prediction, buffer):
    s = historical_scenario(history, prediction)
    s.name = "M5 monthly sustainability replay"
    s.pack_size = 1.0
    # Expected daily demand can be fractional; dispatches remain whole product units.
    for c in s.customers:
        c.demand = prediction[c.id].astype(float).tolist()
        c.minimum = c.terminal = float(buffer[c.id])
    # Fixed past-derived supply, not a truckload added every day regardless of demand.
    supply = float(max(1, ceil(history.tail(56).mean().sum())))
    s.supply = [supply] * len(prediction)
    for v in s.vehicles:
        v.kg_co2_per_l = 2.66  # Table 5, Mundim et al.; diesel combustion CO2, not CO2e.
    s.provenance["monthly_revision"] = {
        "version": VERSION, "supply": supply, "supply_origin": "ceil(sum of trailing 56-day means), fixed at replay start",
        "demand": "fractional expected demand; pack size 1 enforces whole-unit deliveries",
        "buffer": buffer.to_dict(), "buffer_method": "shared maximum across baseline/selected model 95th percentile cumulative calibration underprediction",
        "emission_factor": {"value": 2.66, "unit": "kg CO2/L diesel", "origin": "published paper parameter",
                            "source": "Mundim et al. (2025), Table 5; https://doi.org/10.1051/ro/2024162"},
        "fuel_consumption": "0.10 and 0.20 L/km remain illustrative assumptions, not paper values",
    }
    s.validate()
    return s


def percent_reduction(baseline, candidate):
    return 100.0 * (baseline - candidate) / baseline if baseline > 0 else None


def simulate_months(history, summary, policy, progress=None):
    model = "moving_average" if policy == "baseline" else summary["selected_ml"]
    start, end = history.index.get_loc(START), history.index.get_loc(END) + 1
    buffer = pd.Series(summary["buffer"]).reindex(history.columns)
    initial_pred = forecast(history.iloc[:start], HORIZON, "moving_average")
    template = monthly_scenario(history.iloc[:start], initial_pred, buffer)
    stocks = {c.id: c.initial for c in template.customers}
    depot = template.depot_initial
    records, stock_rows, route_rows, plan_audit = [], [], [], []
    cache = OUT / "forecast_cache"
    cache.mkdir(exist_ok=True)
    for t in range(start, end):
        date = history.index[t]
        key = f"{model}_{date.date()}_{summary['history_sha256'][:12]}_{VERSION}.json"
        cached = cache / key
        if cached.exists():
            pred = pd.DataFrame(json.loads(cached.read_text()), index=pd.date_range(date, periods=HORIZON))
        else:
            pred = forecast(history.iloc[:t], HORIZON, model)
            cached.write_text(json.dumps({c: pred[c].tolist() for c in pred}))
        s = deepcopy(template)
        s.depot_initial = depot
        for c in s.customers:
            c.initial = stocks[c.id]
            c.demand = pred[c.id].tolist()
        cost_plan = solve(s, time_limit=5, tie_break=True)
        chosen = cost_plan
        solve_count = 1
        cap = None
        if has_solution(cost_plan) and policy == "carbon_aware":
            minimum = solve(s, objective="emissions", time_limit=5)
            solve_count += 1
            if has_solution(minimum):
                low_e = evaluate(s, minimum)["metrics"]["emissions_kg"]
                cost_e = evaluate(s, cost_plan)["metrics"]["emissions_kg"]
                if low_e < cost_e - 1e-5:
                    cap = low_e + 0.5 * (cost_e - low_e)
                    s.carbon_cap = cap
                    chosen = solve(s, time_limit=5)
                    solve_count += 1
        if not has_solution(chosen):
            return {"status": "planning_failed", "policy": policy, "failed_date": str(date.date()),
                    "solver_status": chosen.status, "records": records,
                    "note": "Incomplete run; no monthly savings calculated"}
        report = evaluate(s, chosen)
        if not report["valid"]:
            raise RuntimeError(report["violations"])
        quantities = {c.id: 0.0 for c in s.customers}
        for r in chosen.routes:
            if r.day == 0:
                for customer, qty in r.quantities.items():
                    quantities[customer] += qty
        depot += s.supply[0] - sum(quantities.values())
        unmet = actual_total = holding = 0.0
        for c in s.customers:
            actual = float(history.iloc[t][c.id])
            opening = stocks[c.id]
            available = opening + quantities[c.id]
            shortage = max(0.0, actual - available)
            if shortage < 1e-6:
                shortage = 0.0
            stocks[c.id] = max(0.0, available - actual)
            holding += stocks[c.id] * c.holding
            unmet += shortage
            actual_total += actual
            stock_rows.append({"date": str(date.date()), "policy": policy, "outlet": c.id,
                "opening_stock": opening, "forecast": float(pred.iloc[0][c.id]), "delivery": quantities[c.id],
                "actual_sales": actual, "unmet_units": shortage, "closing_stock": stocks[c.id]})
        executed = [r for r in report["routes"] if r["day"] == 1]
        for r in executed:
            route_rows.append({"date": str(date.date()), "policy": policy, **r})
        transport = sum(r["transport_cost"] for r in executed)
        co2 = sum(r["emissions_kg"] for r in executed)
        record = {"date": str(date.date()), "month": str(date.to_period("M")), "policy": policy, "model": model,
            "actual_units": actual_total, "unmet_units": unmet, "served_units": actual_total - unmet,
            "transport_cost": transport, "outlet_holding_cost": holding, "depot_holding_cost": depot * s.depot_holding,
            "cost": transport + holding + depot * s.depot_holding, "emissions_kg": co2,
            "distance_km": sum(r["distance"] for r in executed), "routes": len(executed),
            "closing_outlet_stock": sum(stocks.values()), "closing_depot_stock": depot,
            "solver_status": chosen.status, "gap": chosen.gap, "carbon_cap_horizon": cap, "solve_count": solve_count}
        records.append(record)
        # Keep every full planning input, chosen schedule and validation outcome auditable.
        plan_audit.append({"date": str(date.date()), "scenario": s.to_dict(), "plan": chosen.to_dict(), "validation": report})
        if (t-start) % 15 == 0:
            print(f"{policy}: {date.date()} ({t-start+1}/{end-start})", flush=True)
            if progress:
                progress(t-start+1, end-start)
    audit_path = OUT / f"{policy}_plans.json"
    audit_path.write_text(json.dumps(plan_audit, allow_nan=False))
    return {"status": "complete", "policy": policy, "model": model, "records": records,
            "stocks": stock_rows, "routes": route_rows, "initial_scenario": template.to_dict(),
            "terminal_stock": stocks, "depot_terminal_stock": depot}


def monthly_ledger(daily):
    if daily.duplicated(["date", "policy"]).any():
        raise ValueError("Duplicate daily policy records")
    date_sets = daily.groupby("policy").date.apply(lambda x: frozenset(x))
    if len(set(date_sets)) > 1:
        raise ValueError("Policies must cover identical dates")
    add = ["actual_units", "unmet_units", "served_units", "transport_cost", "outlet_holding_cost",
           "depot_holding_cost", "cost", "emissions_kg", "distance_km", "routes"]
    monthly = daily.groupby(["month", "policy"])[add].sum().reset_index()
    ending = daily.sort_values("date").groupby(["month", "policy"])[["closing_outlet_stock", "closing_depot_stock"]].last().reset_index()
    monthly = monthly.merge(ending, on=["month", "policy"], validate="one_to_one")
    monthly["fill_rate"] = np.where(monthly.actual_units > 0, monthly.served_units / monthly.actual_units, 1.0)
    base = monthly[monthly.policy.eq("baseline")].set_index("month")
    rows = []
    for _, row in monthly.iterrows():
        b = base.loc[row["month"]]
        row = row.to_dict()
        row.update({"baseline_cost": float(b.cost), "baseline_emissions_kg": float(b.emissions_kg),
                    "cost_saved": float(b.cost - row["cost"]), "carbon_saved_kg": float(b.emissions_kg - row["emissions_kg"]),
                    "cost_reduction_pct": percent_reduction(b.cost, row["cost"]),
                    "carbon_reduction_pct": percent_reduction(b.emissions_kg, row["emissions_kg"]),
                    "baseline_fill_rate": float(b.fill_rate),
                    "service_qualified": bool(row["fill_rate"] >= max(0.95, b.fill_rate) - 1e-8)})
        rows.append(row)
    return pd.DataFrame(rows)


def run(reuse_study=False):
    history = load_history()
    summary = json.loads((OUT / "study.json").read_text()) if reuse_study else study(history)
    reports = {}
    for policy in ["baseline", "selected_ml", "carbon_aware"]:
        reports[policy] = simulate_months(history, summary, policy)
        (OUT / f"{policy}.json").write_text(json.dumps(reports[policy], indent=2, allow_nan=False))
        if reports[policy]["status"] != "complete":
            raise RuntimeError(f"Incomplete {policy}: {reports[policy].get('failed_date')}")
    daily = pd.DataFrame([r for report in reports.values() for r in report["records"]])
    monthly = monthly_ledger(daily)
    daily.to_csv(OUT / "daily_results.csv", index=False)
    monthly.to_csv(OUT / "monthly_results.csv", index=False)
    pd.DataFrame([r for report in reports.values() for r in report["stocks"]]).to_csv(OUT / "inventory_execution.csv", index=False)
    pd.DataFrame([r for report in reports.values() for r in report["routes"]]).to_csv(OUT / "executed_routes.csv", index=False)
    (OUT / "completed_study.json").write_text(json.dumps(summary, indent=2))
    print(monthly[["month", "policy", "cost", "emissions_kg", "cost_reduction_pct", "carbon_reduction_pct", "fill_rate"]].to_string(index=False), flush=True)
    return summary, monthly

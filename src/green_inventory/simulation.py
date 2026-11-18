"""Rolling execution against observed sales; shortages remain visible as lost sales."""
from copy import deepcopy
from math import ceil
import pandas as pd
from .data import historical_scenario
from .forecasting import forecast
from .optimisation import solve, has_solution
from .evaluation import evaluate


def simulate(history, start, days=7, horizon=3, model="seasonal_naive", buffer=None, time_limit=10):
    if start < 90 or start + days + horizon - 1 > len(history):
        raise ValueError("Simulation needs past history and complete actual evaluation horizons")
    columns = history.columns
    # Identical physical assumptions and initial stocks for every forecast policy.
    initial_prediction = forecast(history.iloc[:start], horizon, "seasonal_naive")
    template = historical_scenario(history.iloc[:start], initial_prediction, buffer)
    stocks = {c.id: c.initial for c in template.customers}
    depot_stock = template.depot_initial
    records, stock_records = [], []
    for t in range(start, start + days):
        pred = (history.iloc[t:t + horizon].copy() if model == "perfect_information"
                else forecast(history.iloc[:t], horizon, model))
        s = deepcopy(template)
        for c in s.customers:
            c.initial = stocks[c.id]
            c.demand = pred[c.id].apply(lambda x: float(ceil(x))).tolist()
        s.depot_initial = depot_stock
        p = solve(s, time_limit=time_limit, tie_break=False)
        if not has_solution(p):
            return {"status": "planning_failed", "failed_date": str(history.index[t].date()),
                    "solver_status": p.status, "records": records,
                    "note": "Incomplete policies excluded from savings comparisons"}
        checked = evaluate(s, p)
        if not checked["valid"]:
            raise RuntimeError("Invalid plan rejected before simulated execution")
        deliveries = {c: 0.0 for c in columns}
        for r in p.routes:
            if r.day == 0:
                for c, q in r.quantities.items():
                    deliveries[c] += q
        depot_stock += s.supply[0] - sum(deliveries.values())
        unmet = demand_total = holding = 0.0
        for c in s.customers:
            actual = float(history.iloc[t][c.id])
            available = stocks[c.id] + deliveries[c.id]
            shortage = max(0.0, actual - available)
            if shortage < 1e-7:
                shortage = 0.0
            stocks[c.id] = max(0.0, available - actual)
            unmet += shortage
            demand_total += actual
            holding += stocks[c.id] * c.holding
            stock_records.append({"date": str(history.index[t].date()), "outlet": c.id,
                                  "actual_sales_proxy": actual, "delivery": deliveries[c.id],
                                  "unmet_units": shortage, "closing_stock": stocks[c.id]})
        executed_routes = [r for r in checked["routes"] if r["day"] == 1]
        transport = sum(r["transport_cost"] for r in executed_routes)
        emissions = sum(r["emissions_kg"] for r in executed_routes)
        records.append({"date": str(history.index[t].date()), "model": model,
                        "actual_units": demand_total, "unmet_units": unmet,
                        "cost": transport + holding + depot_stock * s.depot_holding,
                        "emissions_kg": emissions, "routes": len(executed_routes),
                        "runtime": p.runtime, "gap": p.gap})
    frame = pd.DataFrame(records)
    actual_total = float(frame.actual_units.sum())
    return {"status": "complete", "model": model, "records": records, "stock_records": stock_records,
            "metrics": {"operating_cost": float(frame.cost.sum()), "emissions_kg": float(frame.emissions_kg.sum()),
                        "unmet_units": float(frame.unmet_units.sum()),
                        "fill_rate": 1 - float(frame.unmet_units.sum()) / actual_total if actual_total else 1.0,
                        "routes": int(frame.routes.sum())},
            "terminal_stock": stocks, "depot_terminal_stock": depot_stock,
            "boundary": "Lost-sales simulation using observed sales as demand proxy; no emergency deliveries or shortage penalty. Cost is conditional on service performance. Perfect information covers the same short horizon, not a global bound."}

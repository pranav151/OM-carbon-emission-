"""Exact subset-route MILP for small, fixed-consumption inventory-routing problems.

One shortest tour per customer subset is sufficient because both transportation
cost and emissions are nonnegative linear functions of distance per vehicle.
Held–Karp builds all subset tours; route selection and quantities are optimized
jointly. Connected depot tours are guaranteed by construction, without subtours.
"""
import math
import time
import numpy as np
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from .schema import Scenario, Route, Plan
from .evaluation import evaluate


def route_catalog(s):
    n = len(s.customers)
    points = [s.depot_xy] + [(c.x, c.y) for c in s.customers]
    d = np.zeros((n + 1, n + 1))
    for i in range(n + 1):
        for j in range(n + 1):
            length = math.dist(points[i], points[j])
            d[i, j] = (math.floor(length + 0.5) if s.round_distances else length) * s.distance_scale
    dp = {}
    tours = []
    for mask in range(1, 1 << n):
        members = [i for i in range(n) if mask & (1 << i)]
        for end in members:
            prev = mask ^ (1 << end)
            if not prev:
                dp[mask, end] = (d[0, end + 1], [end])
            else:
                best = min((dp[prev, j][0] + d[j + 1, end + 1], dp[prev, j][1] + [end])
                           for j in members if j != end)
                dp[mask, end] = best
        distance, order = min((dp[mask, j][0] + d[j + 1, 0], dp[mask, j][1]) for j in members)
        tours.append({"members": members, "order": order, "distance": float(distance)})
    return tours


def solve(s: Scenario, objective="cost", time_limit=30.0, tie_break=True) -> Plan:
    s.validate()
    if objective not in {"cost", "emissions"}:
        raise ValueError("Unknown objective")
    if objective == "emissions" and s.mode == "benchmark":
        raise ValueError("Physical emissions require an illustrative scenario with declared units")
    start = time.perf_counter()
    tours = route_catalog(s)
    n, k, h = len(s.customers), len(s.vehicles), s.horizon
    m = pyo.ConcreteModel()
    m.I = pyo.RangeSet(0, n - 1)
    m.K = pyo.RangeSet(0, k - 1)
    m.T = pyo.RangeSet(0, h - 1)
    m.R = pyo.RangeSet(0, len(tours) - 1)
    m.z = pyo.Var(m.R, m.K, m.T, domain=pyo.Binary)
    m.q = pyo.Var(m.I, m.K, m.T, domain=pyo.NonNegativeReals)
    m.stock = pyo.Var(m.I, m.T, domain=pyo.NonNegativeReals)
    m.depot = pyo.Var(m.T, domain=pyo.NonNegativeReals)
    if s.pack_size:
        m.packs = pyo.Var(m.I, m.K, m.T, domain=pyo.NonNegativeIntegers)
    containing = {i: [r for r, tour in enumerate(tours) if i in tour["members"]] for i in m.I}
    m.constraints = pyo.ConstraintList()
    for t in m.T:
        depot_open = s.depot_initial if t == 0 else m.depot[t - 1]
        m.constraints.add(m.depot[t] == depot_open + s.supply[t] - sum(m.q[i, v, t] for i in m.I for v in m.K))
        for i in m.I:
            c = s.customers[i]
            opening = c.initial if t == 0 else m.stock[i, t - 1]
            delivered = sum(m.q[i, v, t] for v in m.K)
            m.constraints.add(m.stock[i, t] == opening + delivered - c.demand[t])
            m.constraints.add(opening + delivered <= c.capacity)
            m.constraints.add(m.stock[i, t] >= c.minimum)
            m.constraints.add(sum(m.z[r, v, t] for r in containing[i] for v in m.K) <= 1)
            for v in m.K:
                visit = sum(m.z[r, v, t] for r in containing[i])
                m.constraints.add(m.q[i, v, t] <= min(c.capacity, s.vehicles[v].capacity) * visit)
                if s.moq:
                    m.constraints.add(m.q[i, v, t] >= s.moq * visit)
                if s.pack_size:
                    m.constraints.add(m.q[i, v, t] == s.pack_size * m.packs[i, v, t])
        for v in m.K:
            active = sum(m.z[r, v, t] for r in m.R)
            m.constraints.add(active <= 1)
            m.constraints.add(sum(m.q[i, v, t] for i in m.I) <= s.vehicles[v].capacity * active)
    for i in m.I:
        m.constraints.add(m.stock[i, h - 1] >= s.customers[i].terminal)
    m.constraints.add(m.depot[h - 1] >= s.depot_terminal)
    m.cost = pyo.Expression(expr=sum(s.customers[i].holding * m.stock[i, t] for i in m.I for t in m.T)
        + sum(s.depot_holding * m.depot[t] for t in m.T)
        + sum((tours[r]["distance"] * s.vehicles[v].cost_per_distance + s.vehicles[v].dispatch_cost)
              * m.z[r, v, t] for r in m.R for v in m.K for t in m.T))
    m.emissions = pyo.Expression(expr=sum(tours[r]["distance"] * s.vehicles[v].fuel_l_per_km
        * s.vehicles[v].kg_co2_per_l * m.z[r, v, t] for r in m.R for v in m.K for t in m.T))
    if s.carbon_cap is not None:
        m.constraints.add(m.emissions <= s.carbon_cap)
    primary = m.cost if objective == "cost" else m.emissions
    secondary = m.emissions if objective == "cost" else m.cost
    m.obj = pyo.Objective(expr=primary)
    solver = Highs()
    solver.config.time_limit = float(time_limit)
    solver.config.load_solution = False
    solver.highs_options["mip_rel_gap"] = 0.0
    solver.highs_options["threads"] = 1
    solver.highs_options["random_seed"] = 42
    result = solver.solve(m)
    status = result.termination_condition.name
    bound = result.best_objective_bound
    incumbent = result.best_feasible_objective
    metadata = {"objective_kind": objective, "scenario_hash": s.fingerprint(), "route_columns": len(tours),
                "tie_break": "not run", "primary_status": status}
    if incumbent is None or not math.isfinite(incumbent):
        return Plan(objective, [], status, time.perf_counter() - start,
                    float(bound) if bound is not None and math.isfinite(bound) else None,
                    metadata=metadata)
    result.solution_loader.load_vars()
    primary_opt = float(pyo.value(primary))
    saved = [(v, v.value) for v in m.component_data_objects(pyo.Var)]
    if tie_break and status == "optimal" and s.mode != "benchmark":
        tolerance = 1e-6
        m.constraints.add(primary <= primary_opt + tolerance)
        m.obj.set_value(secondary)
        remaining = max(0.01, time_limit - (time.perf_counter() - start))
        solver.config.time_limit = remaining
        second = solver.solve(m)
        metadata["tie_break"] = second.termination_condition.name
        if second.best_feasible_objective is not None and math.isfinite(second.best_feasible_objective):
            second.solution_loader.load_vars()
        else:
            for var, val in saved:
                var.set_value(val)
    routes = []
    for t in m.T:
        for v in m.K:
            for r in m.R:
                if pyo.value(m.z[r, v, t]) > 0.5:
                    stops = [s.customers[i].id for i in tours[r]["order"]]
                    quantities = {s.customers[i].id: max(0.0, float(pyo.value(m.q[i, v, t]))) for i in tours[r]["members"]}
                    routes.append(Route(t, s.vehicles[v].id, stops, quantities))
    final_primary = float(pyo.value(primary))
    bound = float(bound) if bound is not None and math.isfinite(bound) else None
    gap = max(0.0, final_primary - bound) / max(abs(final_primary), 1e-9) if bound is not None else None
    plan = Plan(objective, routes, status, time.perf_counter() - start, bound, gap, final_primary, metadata)
    report = evaluate(s, plan)
    metadata["validation"] = "passed" if report["valid"] else "failed"
    if not report["valid"]:
        plan.status = "validation_failed"
        metadata["violations"] = report["violations"]
    expected = report["metrics"]["total_cost" if objective == "cost" else "emissions_kg"]
    if abs(expected - final_primary) > 1e-4:
        plan.status = "validation_failed"
        metadata["objective_mismatch"] = [expected, final_primary]
    return plan


def has_solution(plan):
    return plan.objective is not None and plan.status != "validation_failed"

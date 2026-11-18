"""Transparent greedy baseline and comparable carbon-cap experiments."""
from copy import deepcopy
from math import ceil, dist
from .schema import Plan, Route
from .evaluation import evaluate
from .optimisation import solve, has_solution


def baseline(s, coverage=2):
    s.validate()
    stock = {c.id: c.initial for c in s.customers}
    depot = s.depot_initial
    routes = []
    for t in range(s.horizon):
        depot += s.supply[t]
        required = []
        for c in s.customers:
            floor = max(c.minimum, c.terminal if t == s.horizon - 1 else c.minimum)
            if stock[c.id] < c.demand[t] + floor - 1e-8:
                target = min(c.capacity, sum(c.demand[t:min(s.horizon, t + coverage)]) + floor)
                q = max(s.moq, target - stock[c.id])
                if s.pack_size:
                    q = ceil(q / s.pack_size) * s.pack_size
                required.append((c, q))
        unserved = list(required)
        for v in sorted(s.vehicles, key=lambda v: v.cost_per_distance):
            stops, quantities = [], {}
            remaining = v.capacity
            pos = s.depot_xy
            while unserved:
                fitting = [(c, q) for c, q in unserved if q <= remaining + 1e-8 and q <= depot + 1e-8 and stock[c.id] + q <= c.capacity + 1e-8]
                if not fitting:
                    break
                c, q = min(fitting, key=lambda cq: dist(pos, (cq[0].x, cq[0].y)))
                stops.append(c.id)
                quantities[c.id] = q
                stock[c.id] += q
                remaining -= q
                depot -= q
                pos = (c.x, c.y)
                unserved.remove((c, q))
            if stops:
                routes.append(Route(t, v.id, stops, quantities))
        if unserved:
            return Plan("rule_based", routes, "heuristic_failed", metadata={"reason": "Greedy coverage target could not fit available storage, stock or fleet"})
        for c in s.customers:
            stock[c.id] -= c.demand[t]
    p = Plan("rule_based", routes)
    r = evaluate(s, p)
    p.status = "feasible" if r["valid"] else "heuristic_failed"
    p.metadata = {"coverage_days": coverage, "validation": r["violations"], "scenario_hash": s.fingerprint()}
    if r["valid"]:
        p.objective = r["metrics"]["total_cost"]
    return p


def compare(s, caps=3, time_limit=20):
    unrestricted = deepcopy(s)
    unrestricted.carbon_cap = None
    results = []
    for p in [baseline(unrestricted), solve(unrestricted, time_limit=time_limit)]:
        results.append((deepcopy(unrestricted), p))
    if s.mode == "benchmark":
        return results
    low = solve(unrestricted, "emissions", time_limit=time_limit)
    results.append((deepcopy(unrestricted), low))
    cost = results[1][1]
    if has_solution(low) and has_solution(cost):
        e_min = evaluate(unrestricted, low)["metrics"]["emissions_kg"]
        e_cost = evaluate(unrestricted, cost)["metrics"]["emissions_kg"]
        if e_cost > e_min + 1e-5:
            for j in range(1, caps + 1):
                capped = deepcopy(unrestricted)
                capped.carbon_cap = e_min + (e_cost - e_min) * j / (caps + 1)
                p = solve(capped, time_limit=time_limit)
                p.policy = f"carbon_cap_{capped.carbon_cap:.3f}"
                results.append((capped, p))
    return results

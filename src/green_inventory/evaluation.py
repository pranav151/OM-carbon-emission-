"""Independent schedule evaluation: never reads optimizer variables or expressions."""
from math import hypot, floor, isfinite
from .schema import Scenario, Plan

TOL = 1e-5


def evaluate(s: Scenario, plan: Plan) -> dict:
    s.validate()
    errors = []
    customers = {c.id: c for c in s.customers}
    vehicles = {v.id: v for v in s.vehicles}
    locations = {c.id: (c.x, c.y) for c in s.customers} | {"DEPOT": s.depot_xy}
    delivery = {(c.id, t): 0.0 for c in s.customers for t in range(s.horizon)}
    assignment = {}
    visited = set()
    used = set()
    total_distance = transport = emissions = total_capacity = total_load = 0.0
    route_rows = []
    for r in plan.routes:
        if r.day not in range(s.horizon) or r.vehicle not in vehicles:
            errors.append("Unknown vehicle or invalid route day")
            continue
        key = (r.day, r.vehicle)
        if key in used:
            errors.append(f"Multiple routes for {key}")
        used.add(key)
        if not r.stops or len(set(r.stops)) != len(r.stops) or any(i not in customers for i in r.stops):
            errors.append(f"Invalid route stops: {key}")
            continue
        if set(r.quantities) - set(r.stops):
            errors.append(f"Delivery without visit: {key}")
        v = vehicles[r.vehicle]
        load = 0.0
        for i in r.stops:
            if (i, r.day) in visited:
                errors.append(f"Multiple visits to {i} on day {r.day}")
            visited.add((i, r.day))
            q = r.quantities.get(i, 0.0)
            if not isfinite(q) or q < -TOL:
                errors.append(f"Invalid quantity: {i}")
                continue
            if q > TOL and q + TOL < s.moq:
                errors.append(f"MOQ violated: {i}")
            if s.pack_size and abs(q / s.pack_size - round(q / s.pack_size)) > TOL:
                errors.append(f"Pack size violated: {i}")
            load += q
            delivery[i, r.day] += q
            assignment[i, r.day] = r.vehicle
        if load > v.capacity + TOL:
            errors.append(f"Vehicle capacity exceeded: {key}")
        route_distance = 0.0
        nodes = ["DEPOT", *r.stops, "DEPOT"]
        for a, b in zip(nodes, nodes[1:]):
            x, y = locations[a]
            xx, yy = locations[b]
            d = hypot(x - xx, y - yy)
            route_distance += (floor(d + 0.5) if s.round_distances else d) * s.distance_scale
        cost = route_distance * v.cost_per_distance + v.dispatch_cost
        co2 = route_distance * v.fuel_l_per_km * v.kg_co2_per_l
        transport += cost
        emissions += co2
        total_distance += route_distance
        total_load += load
        total_capacity += v.capacity
        route_rows.append({"day": r.day + 1, "vehicle": r.vehicle,
                           "route": " → ".join(nodes), "distance": route_distance,
                           "load": load, "capacity": v.capacity, "transport_cost": cost,
                           "emissions_kg": co2 if s.mode != "benchmark" else None})
    stock = {c.id: c.initial for c in s.customers}
    depot = s.depot_initial
    rows = []
    depot_rows = []
    holding = depot_holding = 0.0
    peak = 0.0
    for t in range(s.horizon):
        opening_depot = depot
        sent = sum(delivery[c.id, t] for c in s.customers)
        depot += s.supply[t] - sent
        if depot < -TOL:
            errors.append(f"Depot shortage on day {t + 1}")
        depot_holding += depot * s.depot_holding
        depot_rows.append({"day": t + 1, "opening": opening_depot, "supply": s.supply[t], "dispatch": sent, "closing": depot})
        for c in s.customers:
            opening = stock[c.id]
            q = delivery[c.id, t]
            pre_demand = opening + q
            closing = pre_demand - c.demand[t]
            if pre_demand > c.capacity + TOL:
                errors.append(f"Storage exceeded before consumption: {c.id}, day {t + 1}")
            if closing < c.minimum - TOL:
                errors.append(f"Minimum stock/stockout: {c.id}, day {t + 1}")
            stock[c.id] = closing
            holding += closing * c.holding
            peak = max(peak, pre_demand)
            rows.append({"day": t + 1, "customer": c.id, "opening": opening,
                         "delivery": q, "demand": c.demand[t], "closing": closing,
                         "capacity": c.capacity, "vehicle": assignment.get((c.id, t), "—")})
    for c in s.customers:
        if stock[c.id] < c.terminal - TOL:
            errors.append(f"Terminal stock violated: {c.id}")
    if depot < s.depot_terminal - TOL:
        errors.append("Depot terminal stock violated")
    if s.carbon_cap is not None and emissions > s.carbon_cap + TOL:
        errors.append("Carbon cap exceeded")
    return {"valid": not errors, "violations": errors, "inventory": rows, "depot": depot_rows,
            "routes": route_rows, "metrics": {
                "total_cost": holding + depot_holding + transport,
                "customer_holding_cost": holding, "depot_holding_cost": depot_holding,
                "transport_cost": transport, "emissions_kg": emissions if s.mode != "benchmark" else None,
                "distance": total_distance, "route_count": len(plan.routes),
                "delivery_count": sum(q > TOL for q in delivery.values()),
                "average_closing_inventory": sum(r["closing"] for r in rows) / len(rows),
                "peak_customer_inventory": peak,
                "capacity_utilisation": total_load / total_capacity if total_capacity else 0.0}}

from copy import deepcopy
from itertools import permutations
import math
import pytest
from green_inventory.schema import Customer, Vehicle, Scenario, Plan, Route
from green_inventory.data import load_benchmark, parse_archetti
from green_inventory.evaluation import evaluate
from green_inventory.optimisation import solve, route_catalog, has_solution
from green_inventory.policies import baseline


def tiny():
    return Scenario("hand calculation", [Customer("A", 3, 4, 0, 10, 0, 2, [4, 4])],
                    [Vehicle("V", 10, 1, 0.1, 2, 3)], [0, 0], 8, 0.5, (0, 0))


def test_hand_calculated_schedule():
    s = tiny()
    p = Plan("manual", [Route(0, "V", ["A"], {"A": 8})])
    r = evaluate(s, p)
    assert r["valid"]
    assert r["metrics"]["total_cost"] == pytest.approx(21)  # 10 travel + 3 dispatch + 8 holding
    assert r["metrics"]["emissions_kg"] == pytest.approx(2)  # includes return leg
    assert [row["closing"] for row in r["inventory"]] == [4, 0]


def test_optimizer_matches_enumerated_hand_options():
    s = tiny()
    candidates = [Plan("all early", [Route(0, "V", ["A"], {"A": 8})]),
                  Plan("two trips", [Route(0, "V", ["A"], {"A": 4}), Route(1, "V", ["A"], {"A": 4})])]
    expected = min(evaluate(s, p)["metrics"]["total_cost"] for p in candidates)
    p = solve(s)
    assert p.status == "optimal"
    assert p.objective == pytest.approx(expected, abs=1e-5)
    assert evaluate(s, p)["valid"]


def test_capacity_checked_before_consumption():
    s = tiny()
    s.customers[0].initial = 5
    s.customers[0].demand = [8, 0]
    p = Plan("bad", [Route(0, "V", ["A"], {"A": 8})])
    assert any("before consumption" in e for e in evaluate(s, p)["violations"])


@pytest.mark.parametrize("mutation, text", [
    (lambda s: setattr(s.vehicles[0], "capacity", 5), "Vehicle capacity"),
    (lambda s: setattr(s, "depot_initial", 1), "Depot shortage"),
    (lambda s: setattr(s, "carbon_cap", 1), "Carbon cap"),
    (lambda s: setattr(s, "pack_size", 3), "Pack size"),
    (lambda s: setattr(s, "moq", 9), "MOQ"),
    (lambda s: setattr(s.customers[0], "terminal", 1), "Terminal stock"),
])
def test_independent_validator_rejects_violations(mutation, text):
    s = tiny()
    mutation(s)
    r = evaluate(s, Plan("bad", [Route(0, "V", ["A"], {"A": 8})]))
    assert not r["valid"]
    assert any(text in e for e in r["violations"])


def test_duplicate_visits_and_unknown_delivery():
    s = tiny()
    p = Plan("bad", [Route(0, "V", ["A"], {"A": 4, "ghost": 2}), Route(0, "V", ["A"], {"A": 4})])
    errors = evaluate(s, p)["violations"]
    assert any("Multiple routes" in e for e in errors)
    assert any("Multiple visits" in e for e in errors)
    assert any("without visit" in e for e in errors)


def test_infeasible_carbon_cap_is_not_an_empty_success():
    s = tiny()
    s.carbon_cap = 0
    p = solve(s)
    assert p.status == "infeasible"
    assert not has_solution(p)


def test_pack_size_and_terminal_feasibility():
    s = tiny()
    s.pack_size = 3
    s.depot_initial = 9
    s.customers[0].terminal = 1
    p = solve(s)
    assert has_solution(p)
    assert sum(q for r in p.routes for q in r.quantities.values()) == pytest.approx(9)
    assert evaluate(s, p)["valid"]


def test_zero_demand_valid_zero_route_plan():
    s = tiny()
    s.customers[0].demand = [0, 0]
    p = solve(s)
    assert has_solution(p) and p.routes == []
    assert evaluate(s, p)["valid"]


def test_archive_fields_and_node_count():
    s = load_benchmark()
    assert len(s.customers) == 5 and s.horizon == 3
    assert s.depot_initial == 510 and s.supply == [193] * 3
    assert s.customers[0].id == "2"
    assert s.customers[0].demand == [65] * 3
    assert s.vehicles[0].capacity == 289
    with pytest.raises(ValueError):
        parse_archetti("6 3 289 2\n1 0 0 100 20 .03")


def test_route_catalog_matches_brute_force():
    s = tiny()
    s.customers.extend([Customer("B", 4, 0, 0, 10, 0, 1, [1, 1]), Customer("C", -2, 3, 0, 10, 0, 1, [1, 1])])
    for route in route_catalog(s):
        values = []
        for order in permutations(route["members"]):
            points = [s.depot_xy] + [(s.customers[i].x, s.customers[i].y) for i in order] + [s.depot_xy]
            values.append(sum(math.dist(a, b) for a, b in zip(points, points[1:])))
        assert route["distance"] == pytest.approx(min(values))


def test_heuristic_failure_not_reported_as_feasible():
    s = tiny()
    s.vehicles[0].capacity = 5
    assert baseline(s, coverage=2).status == "heuristic_failed"
    assert has_solution(solve(s))  # feasible alternative exists despite greedy failure


def test_nonfinite_input_rejected():
    s = tiny()
    s.supply[0] = float("nan")
    with pytest.raises(ValueError):
        s.validate()


def test_binding_carbon_cap_selects_cleaner_more_expensive_vehicle():
    s = tiny()
    s.supply = [0]
    s.customers[0].demand = [4]
    s.depot_initial = 4
    s.vehicles.append(Vehicle("Clean", 10, 2, 0.02, 2, 3))
    cheap = solve(s)
    cheap_report = evaluate(s, cheap)
    assert cheap_report["metrics"]["emissions_kg"] == pytest.approx(2)
    s.carbon_cap = 0.5
    clean = solve(s)
    clean_report = evaluate(s, clean)
    assert clean_report["valid"]
    assert clean_report["metrics"]["emissions_kg"] == pytest.approx(0.4)
    assert clean_report["metrics"]["total_cost"] > cheap_report["metrics"]["total_cost"]
    assert clean.routes[0].vehicle == "Clean"

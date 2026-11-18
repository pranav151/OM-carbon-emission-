"""Shared contracts. Units and provenance travel with every scenario."""
from dataclasses import dataclass, field, asdict
from math import isfinite
import hashlib
import json


@dataclass
class Customer:
    id: str
    x: float
    y: float
    initial: float
    capacity: float
    minimum: float
    holding: float
    demand: list[float]
    terminal: float = 0.0


@dataclass
class Vehicle:
    id: str
    capacity: float
    cost_per_distance: float
    fuel_l_per_km: float = 0.0
    kg_co2_per_l: float = 0.0
    dispatch_cost: float = 0.0


@dataclass
class Scenario:
    name: str
    customers: list[Customer]
    vehicles: list[Vehicle]
    supply: list[float]
    depot_initial: float
    depot_holding: float
    depot_xy: tuple[float, float]
    mode: str = "illustrative"
    distance_scale: float = 1.0
    round_distances: bool = False
    distance_unit: str = "km"
    carbon_cap: float | None = None
    moq: float = 0.0
    pack_size: float = 0.0
    depot_terminal: float = 0.0
    provenance: dict = field(default_factory=dict)

    @property
    def horizon(self):
        return len(self.supply)

    def validate(self):
        def nonnegative(values, label):
            if any(not isfinite(v) or v < 0 for v in values):
                raise ValueError(f"{label} must be finite and nonnegative")
        if not self.customers or not self.vehicles or not self.supply:
            raise ValueError("Customers, vehicles and planning periods are required")
        if len(self.customers) > 10:
            raise ValueError("This exact route-enumeration prototype supports at most 10 outlets")
        if len({c.id for c in self.customers}) != len(self.customers):
            raise ValueError("Duplicate customer ID")
        if len({v.id for v in self.vehicles}) != len(self.vehicles):
            raise ValueError("Duplicate vehicle ID")
        if "DEPOT" in {c.id for c in self.customers}:
            raise ValueError("DEPOT is a reserved ID")
        nonnegative([*self.supply, self.depot_initial, self.depot_holding,
                     self.moq, self.pack_size, self.depot_terminal], "Scenario inputs")
        if not isfinite(self.distance_scale) or self.distance_scale <= 0:
            raise ValueError("Distance scale must be positive")
        if not all(isfinite(v) for v in self.depot_xy):
            raise ValueError("Depot coordinates must be finite")
        if self.carbon_cap is not None:
            nonnegative([self.carbon_cap], "Carbon cap")
        for c in self.customers:
            nonnegative([c.initial, c.capacity, c.minimum, c.holding, c.terminal, *c.demand], c.id)
            if len(c.demand) != self.horizon:
                raise ValueError(f"Demand horizon mismatch: {c.id}")
            if not all(isfinite(v) for v in [c.x, c.y]):
                raise ValueError("Customer coordinates must be finite")
            if c.initial > c.capacity or max(c.minimum, c.terminal) > c.capacity:
                raise ValueError(f"Inventory bounds invalid: {c.id}")
        for v in self.vehicles:
            nonnegative([v.capacity, v.cost_per_distance, v.fuel_l_per_km,
                         v.kg_co2_per_l, v.dispatch_cost], v.id)
            if v.capacity <= 0:
                raise ValueError("Vehicle capacity must be positive")
        if self.mode == "benchmark" and (self.distance_unit != "coordinate unit" or self.carbon_cap is not None):
            raise ValueError("Benchmark mode has no physical emissions or carbon cap")
        if self.mode not in {"benchmark", "illustrative"}:
            raise ValueError("Unknown mode")

    def to_dict(self):
        return asdict(self)

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class Route:
    day: int
    vehicle: str
    stops: list[str]  # excludes the implicit start/end depot
    quantities: dict[str, float]


@dataclass
class Plan:
    policy: str
    routes: list[Route]
    status: str = "feasible"
    runtime: float = 0.0
    bound: float | None = None
    gap: float | None = None
    objective: float | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

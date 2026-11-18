# Assumptions register

The entries below describe the original benchmark and v0.1 scenarios. The v0.2 monthly experiment overrides expected-demand rounding, depot supply, safety-buffer calibration and the diesel factor as documented in `ALGORITHMS.md`. Its complete input scenarios are exported in `results/sustainability/*_plans.json`. All policies within each experiment use the same physical assumptions.

## Original benchmark

Source: `instances/archetti2007/L3/abs1n5.dat` within the authors' archive. Values remain unchanged.

| Field | Value / rule | Origin / unit |
|---|---|---|
| Header | 6 nodes including depot, 3 periods, vehicle capacity 289 | Original input; product units |
| Depot ID | 1, normalised internally to a dedicated depot object | Original input |
| Depot stock / supply | 510 initially; 193 each period | Original input; product units |
| Customer IDs | 2–6 | Original input |
| Demand / stock / capacity / holding | Parsed directly from each row | Original input; cost units, product units |
| Fleet count | One vehicle in benchmark convention mode | Explicit scenario assumption; absent from header |
| Coordinate units | Unspecified; do not interpret as km | Original input limitation |
| Distance | Nearest-integer Euclidean | Archive README rounding convention reconciled with DIMACS |
| Terminal stock | Customer minimum; depot ≥ 0 | Explicit scenario choice, same across policies |
| Timing | Supply and delivery before consumption; end-period holding cost | Adopted documented convention |

The archive README describes a four-token header (`n H C np`) but does not define np, and calls n the number of retailers. The actual file has three tokens and five customer rows plus the depot. The parser requires the observed three-token layout and verifies that n counts all node rows; it does not blindly accept the README wording.

## Illustrative transport

All values in `configs/illustrative.json` are assumptions, not imported paper estimates:

- 0.05 km per coordinate unit; unrounded Euclidean distances.
- Vehicle capacities 150 and 289 product units.
- Fuel consumption 0.10 and 0.20 L/km; illustrative combustion factor 2.68 kg CO₂/L for both.
- Distance costs 1.0 and 1.5 cost units/km, inclusive of fuel; dispatch costs 2 and 3.
- Fixed consumption, independent of load; all depot-return travel included.

## M5 illustrative network

The SKU `HOUSEHOLD_1_001` is fixed before model evaluation. Stores are the first five alphabetical IDs: CA_1, CA_2, CA_3, CA_4, TX_1. There is no future-volume-based selection, synthetic redistribution of aggregate sales, invented history, or scaling of observed sales.

Observed unit sales serve as a demand proxy. There is no source stock availability, so lost sales before observation cannot be recovered. Day-zero sales may reflect no sales or availability issues; we preserve them rather than reinterpret them.

Physical network is separate: these stores are mapped in order to the five Archetti coordinate positions solely for simulation. This is not a geographically valid route across California and Texas.

Physical parameters use only history before the first decision:

- Outlet storage = max(10, ceil(7 × past-56-day mean), ceil(3 × past-180-day maximum)).
- Initial stock = min(storage, ceil(2 × past-56-day mean)).
- Q = max(20, ceil(3 × sum of outlet past-56-day means)); vehicle capacities Q and 2Q.
- Initial depot stock and each day's supply = 3Q.
- Outlet holding 0.1 and depot holding 0.01 cost units / unit / period.
- Transport consumption, emissions factor and distance-cost assumptions match the illustrative transport units above.
- Forecasts are nonnegative and rounded upward to whole units before planning. Model accuracy is reported on the unrounded forecasts.
- In historical simulation, the common empirical buffer is imposed as minimum closing stock and terminal target. It is calibrated before the test window and shared across forecast methods to isolate their demand-input differences.
- No shortage penalty or emergency shipment is hidden in cost. Unmet observed demand is lost sales and explicitly counted. Compare fill rate and terminal stock before interpreting cost/carbon differences.
- Inventory/supply/capacity assumptions stay fixed during each rolling comparison; they do not adapt to future actual values.

Dashboard modifications are recorded under `dashboard_overrides`. No explicit physical calibration or actual savings claim is made.

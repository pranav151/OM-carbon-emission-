# Inventory-routing model

Let customers be i, vehicles k, periods t and precomputed complete depot tours r. A_ir is 1 if r visits i. D_r is its distance. Each tour already includes its return leg.

Variables:

- z_rkt ∈ {0,1}: vehicle k operates tour r in period t.
- q_ikt ≥ 0: units delivered to customer i by vehicle k in period t.
- I_it ≥ 0 and S_t ≥ 0: customer and depot closing stock.
- Optional p_ikt nonnegative integer: pack counts.

Constraints:

1. I_it = I_i,t−1 + Σ_k q_ikt − demand_it.
2. I_i,t−1 + Σ_k q_ikt ≤ storage_i (before consumption).
3. I_it ≥ minimum_i; I_i,T ≥ terminal_i.
4. S_t = S_t−1 + supply_t − Σ_ik q_ikt; S_T ≥ depot_terminal.
5. Σ_r z_rkt ≤ 1 for each vehicle and period.
6. Σ_rk A_ir z_rkt ≤ 1 for each customer and period.
7. q_ikt ≤ min(storage_i, capacity_k) Σ_r A_ir z_rkt.
8. Σ_i q_ikt ≤ capacity_k Σ_r z_rkt.
9. Optional MOQ: q_ikt ≥ MOQ Σ_r A_ir z_rkt.
10. Optional packs: q_ikt = pack_size × p_ikt.

With nonnegative distance costs and complete subset enumeration, removing a zero-delivery visit cannot worsen the solution, so linking MOQ to visits does not exclude a better executable plan in this model.

Cost = Σ_it holding_i I_it + Σ_t depot_holding S_t + Σ_rkt (distance_cost_k D_r + dispatch_cost_k) z_rkt.

CO₂ = Σ_rkt D_r × fuel_l_per_km_k × kg_co2_per_l_k × z_rkt.

The transport distance charge includes fuel; no additional fuel expense is added. Inventory costs use closing stock. No warehouse energy, manufacturing emissions or upstream fuel emissions are included.

Primary objectives are either minimum cost or minimum CO₂. Carbon-constrained runs add CO₂ ≤ cap. Where the primary solve is optimal, a second solve minimises the other objective while keeping the primary within 1e−6 absolute units of its optimum. The second-stage status is exported separately; primary bounds/gaps stay associated with the primary objective.

Infeasible runs or runs without an incumbent have no objective and cannot enter the valid-plan comparison. Time-limited incumbents can be displayed only after independent validation, with their status and gap. Secondary solves share the configured time budget where possible (minimum solver invocation allowance 0.01 seconds).

Benchmark distances use nearest-integer Euclidean lengths. Illustrative distances use unrounded Euclidean lengths multiplied by a declared km scale. These modes are not numerically comparable without acknowledging the change of units and fleet.

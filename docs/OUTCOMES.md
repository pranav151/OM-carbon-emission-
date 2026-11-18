# Monthly sustainability outcomes — v0.2

Selected ML: **Poisson regression (α=1.0)**. Validation RMSE 0.69210, a 1.91% improvement over the original random-forest configuration in the same validation window.
Overall validation winner: **TSB intermittent demand**, RMSE 0.67982. Choosing an ML candidate does not mean it beats every statistical baseline.

Forecast selection: 9 Oct–3 Dec 2015. Calibration: 4–31 Dec 2015. Operational replay: 1 Jan–31 Mar 2016. Ten candidate configurations; model choice uses validation only. Reporting is retrospective and partially overlaps the v0.1 experiment.

## Outcomes relative to moving-average forecasting + cost optimisation

| Month | CO₂ avoided (kg) | Carbon reduction | Cost saved (CU) | Cost reduction | Candidate fill rate | Service-qualified |
|---|---:|---:|---:|---:|---:|---|
| 2016-01 | 0.966 | 0.81% | 0.461 | 0.09% | 100.00% | Yes |
| 2016-02 | -18.085 | -12.42% | -76.858 | -12.14% | 89.83% | No |
| 2016-03 | -13.753 | -8.41% | -51.604 | -7.29% | 93.15% | No |

Quarter: candidate 459.290 kg CO₂ versus baseline 428.417; reduction -7.21%. Candidate cost 1999.013 CU versus 1871.011; reduction -6.84%. Both policies serve 94.09% of the 186 observed units, with 11 unmet units.

**There is no overall cost or carbon saving in this experiment.** January has a small improvement; February and March show increases. Aggregate service is below the stated 95% threshold, so this is not an adoption-ready replenishment policy. The dashboard exposes these results rather than manufacturing positive savings.

The cost-focused and carbon-focused daily endpoints coincide throughout this small replay. Consequently, the carbon-aware and selected-ML policy results are identical; the carbon constraint provides no additional benefit here. This may change under other documented fleet/capacity settings, but such results are not assumed.

## Audit and interpretation

- 273 executed daily policy decisions, all chosen plans reported optimal and passed independent validation.
- Three full calendar months, five stores, one fixed household SKU. No fabricated months or rescaled sales.
- Positive savings represent reductions; negative savings represent increases. Aggregate percentages use totals, not averages of percentages.
- Same initial inventory, capacity, supply, fleet and pre-period buffer across policies. Realised inventory carries forward; terminal stocks can differ.
- Diesel factor 2.66 kg CO₂/L is from Mundim et al., Table 5. Consumption, network and cost parameters remain illustrative.
- No shortage penalty, emergency delivery, upstream fuel, warehouse energy or offsets are included.
- CSV: `outputs/transformed_demand.csv`, 9,565 × 27, preserves 3,016 original product units. Missing early lag values remain blank.
- Exact configurations and formulas: `docs/ALGORITHMS.md`. Research citations: `docs/RESEARCH_REVIEW.md`.

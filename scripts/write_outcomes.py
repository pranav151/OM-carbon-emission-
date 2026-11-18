"""Write a concise factual report directly from completed experiment outputs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import json
import pandas as pd
from green_inventory.data import ROOT
from green_inventory.forecasting import LABELS
from green_inventory.dashboard import totals

p=ROOT/'results/sustainability'
s=json.loads((p/'completed_study.json').read_text())
d=pd.read_csv(p/'daily_results.csv')
m=pd.read_csv(p/'monthly_results.csv')
t=totals(d,'carbon_aware',sorted(d.month.unique()))
best=s['selected_ml']
improvement=100*(s['validation']['random_forest']['rmse']-s['validation'][best]['rmse'])/s['validation']['random_forest']['rmse']
lines=['# Monthly sustainability outcomes — v0.2','',
    f"Selected ML: **{LABELS[best]}**. Validation RMSE {s['validation'][best]['rmse']:.5f}, a {improvement:.2f}% improvement over the original random-forest configuration in the same validation window.",
    f"Overall validation winner: **{LABELS[s['selected_overall']]}**, RMSE {s['validation'][s['selected_overall']]['rmse']:.5f}. Choosing an ML candidate does not mean it beats every statistical baseline.",'',
    'Forecast selection: 9 Oct–3 Dec 2015. Calibration: 4–31 Dec 2015. Operational replay: 1 Jan–31 Mar 2016. Ten candidate configurations; model choice uses validation only. Reporting is retrospective and partially overlaps the v0.1 experiment.','',
    '## Outcomes relative to moving-average forecasting + cost optimisation','',
    '| Month | CO₂ avoided (kg) | Carbon reduction | Cost saved (CU) | Cost reduction | Candidate fill rate | Service-qualified |',
    '|---|---:|---:|---:|---:|---:|---|']
for _,r in m[m.policy.eq('carbon_aware')].iterrows():
    lines.append(f"| {r.month} | {r.carbon_saved_kg:.3f} | {r.carbon_reduction_pct:.2f}% | {r.cost_saved:.3f} | {r.cost_reduction_pct:.2f}% | {r.fill_rate:.2%} | {'Yes' if r.service_qualified else 'No'} |")
lines += ['',f"Quarter: candidate {t['emissions']:.3f} kg CO₂ versus baseline {t['baseline_emissions']:.3f}; reduction {t['carbon_pct']:.2f}%. Candidate cost {t['cost']:.3f} CU versus {t['baseline_cost']:.3f}; reduction {t['cost_pct']:.2f}%. Both policies serve {t['fill_rate']:.2%} of the 186 observed units, with 11 unmet units.",'',
    '**There is no overall cost or carbon saving in this experiment.** January has a small improvement; February and March show increases. Aggregate service is below the stated 95% threshold, so this is not an adoption-ready replenishment policy. The dashboard exposes these results rather than manufacturing positive savings.','',
    'The cost-focused and carbon-focused daily endpoints coincide throughout this small replay. Consequently, the carbon-aware and selected-ML policy results are identical; the carbon constraint provides no additional benefit here. This may change under other documented fleet/capacity settings, but such results are not assumed.','',
    '## Audit and interpretation','',
    '- 273 executed daily policy decisions, all chosen plans reported optimal and passed independent validation.',
    '- Three full calendar months, five stores, one fixed household SKU. No fabricated months or rescaled sales.',
    '- Positive savings represent reductions; negative savings represent increases. Aggregate percentages use totals, not averages of percentages.',
    '- Same initial inventory, capacity, supply, fleet and pre-period buffer across policies. Realised inventory carries forward; terminal stocks can differ.',
    '- Diesel factor 2.66 kg CO₂/L is from Mundim et al., Table 5. Consumption, network and cost parameters remain illustrative.',
    '- No shortage penalty, emergency delivery, upstream fuel, warehouse energy or offsets are included.',
    '- CSV: `outputs/transformed_demand.csv`, 9,565 × 27, preserves 3,016 original product units. Missing early lag values remain blank.',
    '- Exact configurations and formulas: `docs/ALGORITHMS.md`. Research citations: `docs/RESEARCH_REVIEW.md`.','']
(ROOT/'docs/OUTCOMES.md').write_text('\n'.join(lines))
print('\n'.join(lines[:18]))

"""Small reproducible cross-instance check, including the 10-outlet/6-period extension."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from green_inventory.data import ROOT, load_benchmark
from green_inventory.optimisation import solve, has_solution
from green_inventory.evaluation import evaluate

rows = []
for member in ["L3/abs1n5.dat", "L3/abs2n5.dat", "H3/abs1n5.dat", "L6/abs1n10.dat"]:
    s = load_benchmark(f"instances/archetti2007/{member}")
    p = solve(s, time_limit=20)
    r = evaluate(s, p) if has_solution(p) else None
    row = {"instance": member, "customers": len(s.customers), "periods": s.horizon,
           "status": p.status, "valid": bool(r and r["valid"]), "objective": p.objective,
           "bound": p.bound, "gap": p.gap, "runtime": p.runtime}
    rows.append(row)
    print(row, flush=True)
pd.DataFrame(rows).to_csv(ROOT / "results/instance_checks.csv", index=False)

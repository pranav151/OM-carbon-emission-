import argparse
import json
from pathlib import Path
import pandas as pd
from .data import ROOT, load_benchmark, illustrative_benchmark, prepare_m5, load_history, manifest
from .evaluation import evaluate
from .policies import compare
from .optimisation import has_solution
from .forecasting import run_study, forecast
from .simulation import simulate


def export_plan(s, p, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    report = evaluate(s, p) if has_solution(p) else None
    payload = {"scenario": s.to_dict(), "plan": p.to_dict(), "evaluation": report}
    (folder / "run.json").write_text(json.dumps(payload, indent=2, allow_nan=False))
    if report:
        for name in ["inventory", "routes", "depot"]:
            pd.DataFrame(report[name]).to_csv(folder / f"{name}.csv", index=False)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["audit", "benchmark", "compare", "prepare-sales", "forecast", "simulate"])
    parser.add_argument("--time-limit", type=float, default=20)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    if args.command == "audit":
        print(json.dumps(manifest(), indent=2))
    elif args.command == "prepare-sales":
        df = prepare_m5()
        print(df.describe().to_string())
    elif args.command in {"benchmark", "compare"}:
        s = load_benchmark() if args.command == "benchmark" else illustrative_benchmark()
        rows = []
        for index, (scenario, plan) in enumerate(compare(s, time_limit=args.time_limit)):
            payload = export_plan(scenario, plan, out / args.command / str(index))
            metrics = payload["evaluation"]["metrics"] if payload["evaluation"] else {}
            rows.append({"policy": plan.policy, "status": plan.status, "gap": plan.gap, **metrics})
        df = pd.DataFrame(rows)
        df.to_csv(out / f"{args.command}_summary.csv", index=False)
        print(df.to_string(index=False))
    elif args.command == "forecast":
        history = load_history()
        study = run_study(history)
        folder = out / "forecast"
        folder.mkdir(exist_ok=True)
        for name in ["validation", "calibration", "test"]:
            getattr(study, name).to_csv(folder / f"{name}.csv", index=False)
        summary = {"selected": study.selected, "validation": study.validation_metrics,
                   "test": study.test_metrics, "buffer": study.buffer.to_dict(),
                   "test_start": study.test_start, "horizon": study.horizon}
        (folder / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
        forecast(history, 3, study.selected).to_csv(folder / "next_forecast.csv", index_label="date")
        print(json.dumps(summary, indent=2))
    elif args.command == "simulate":
        history = load_history()
        summary = json.loads((out / "forecast/summary.json").read_text())
        buffer = pd.Series(summary["buffer"]).reindex(history.columns)
        reports = {}
        for model in ["seasonal_naive", "moving_average", "random_forest", "perfect_information"]:
            print(f"Simulating {model}", flush=True)
            reports[model] = simulate(history, summary["test_start"], days=args.days,
                                      model=model, buffer=buffer, time_limit=args.time_limit)
        (out / "simulation.json").write_text(json.dumps(reports, indent=2, allow_nan=False))
        print(json.dumps({m: r.get("metrics", r.get("solver_status")) for m, r in reports.items()}, indent=2))


if __name__ == "__main__":
    main()

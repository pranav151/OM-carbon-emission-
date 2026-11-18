"""Read-only validation of downloaded public inputs; writes an audit JSON."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/research/carbon_inventory"
EXPECTED_MD5 = {
    "BETVRPB1.csv": "2243f43167d4168a19870605e8a8b39c",
    "BETVRPB1_dist.csv": "b5d234f38027461c9bad6978d2f43d06",
    "BETVRPB1_time.csv": "3632463586c842cba79e28c5aaf93b0e",
    "BETVRPB2.csv": "c56d5383c045ad5d6b78e3143a656413",
    "BETVRPB2_dist.csv": "42f1bdf7a10a8f021d18e1c7b5a69986",
    "BETVRPB2_time.csv": "bde57eb10c87122138f179e10eea3593",
    "BETVRPB3.csv": "68b4cf79fdce8c75116629360347203b",
    "BETVRPB3_dist.csv": "f71feef7c821804a13d4eb07d43311c1",
    "BETVRPB3_time.csv": "24104d17e6d5c6dcfeb986493178fc2a",
    "BETVRPB4.csv": "134e0d00382aecb77b7edcd2dbf237cf",
    "BETVRPB4_dist.csv": "70a3ed2b66cff99ff8a9ed2d70f77922",
    "BETVRPB4_time.csv": "c0b587550de8312bc73ec2c5625fb0cf",
    "README.md": "84c4c7c4df1180762387c585bbad9774",
}


def main():
    folder = DATA / "ncst_2023_v1"
    checksum_matches = {
        name: hashlib.md5((folder / name).read_bytes()).hexdigest() == expected
        for name, expected in EXPECTED_MD5.items()
    }
    cases = []
    for case_id in range(1, 5):
        with (folder / f"BETVRPB{case_id}.csv").open() as stream:
            records = list(csv.DictReader(stream))
        nodes = [row for row in records if row["id"].isdigit()]
        ids = [int(row["id"]) for row in nodes]
        matrices = {}
        for kind in ("dist", "time"):
            with (folder / f"BETVRPB{case_id}_{kind}.csv").open() as stream:
                rows = list(csv.reader(stream))
            header = [int(x) for x in rows[0]]
            values = [[float(x) for x in row] for row in rows[1:]]
            matrices[kind] = {
                "header_ids_match_nodes": header == ids,
                "square_and_matches_nodes": len(values) == len(nodes) and all(len(row) == len(nodes) for row in values),
                "all_finite_nonnegative": all(math.isfinite(x) and x >= 0 for row in values for x in row),
                "diagonal_zero": all(values[i][i] == 0 for i in range(len(nodes))),
            }
        cases.append({
            "case": case_id, "nodes_including_depot": len(nodes), "customer_stops": len(nodes)-1,
            "deliveries": sum(row["stop_type"] == "Delivery" for row in nodes),
            "pickups": sum(row["stop_type"] == "Pickup" for row in nodes),
            "historical_tractor_ids": len({row["Tractor id0"] for row in nodes if row["id"] != "0"}),
            "node_ids_contiguous": ids == list(range(len(nodes))),
            "matrix_checks": matrices,
        })
    manifest = json.loads((DATA / "download_manifest.json").read_text())
    sha_matches = {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() == item["sha256"] for name, item in manifest.items()}
    passed = all(checksum_matches.values()) and all(sha_matches.values()) and all(
        case["node_ids_contiguous"] and all(all(checks.values()) for checks in case["matrix_checks"].values()) for case in cases
    )
    audit = {
        "passed": passed,
        "source_checksum_page": "https://zenodo.org/records/8117782",
        "published_md5_matches": checksum_matches, "download_sha256_matches": sha_matches,
        "cases": cases,
        "notes": [
            "The provider README example says 47 nodes; case 1 actually has 48 nodes including depot, consistent with the paper's 47 customers.",
            "Matrix first rows are numeric column headers, not observations.",
            "Distance units are meters and travel-time units seconds, per source README.",
            "Weight and service-duration column headers omit units. The report uses pounds for cargo and an 8-hour window; any conversion must document its interpretation before modeling.",
            "Four constructed dispatch instances based on typical one-day real movements, not a daily inventory time series or measured fuel/emissions logs.",
            "No new synthetic demand, forecasts, optimization results, or savings have been produced by this audit.",
        ],
    }
    (DATA / "validation.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({"passed": passed, "verified_ncst_files": len(checksum_matches), "verified_downloads": len(sha_matches), "customer_stops_by_case": [case["customer_stops"] for case in cases]}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

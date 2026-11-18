"""Fetch published research inputs without changing the application dataset."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data/research/carbon_inventory"
FILES = {
    "ncst/BETVRPB1_dist.csv": "https://datadryad.org/downloads/file_stream/2811003",
    "ncst/BETVRPB1_time.csv": "https://datadryad.org/downloads/file_stream/2811004",
    "ncst/BETVRPB1.csv": "https://datadryad.org/downloads/file_stream/2811020",
    "ncst/BETVRPB2_dist.csv": "https://datadryad.org/downloads/file_stream/2811005",
    "ncst/BETVRPB2_time.csv": "https://datadryad.org/downloads/file_stream/2811009",
    "ncst/BETVRPB2.csv": "https://datadryad.org/downloads/file_stream/2811021",
    "ncst/BETVRPB3_dist.csv": "https://datadryad.org/downloads/file_stream/2811007",
    "ncst/BETVRPB3_time.csv": "https://datadryad.org/downloads/file_stream/2811013",
    "ncst/BETVRPB3.csv": "https://datadryad.org/downloads/file_stream/2811022",
    "ncst/BETVRPB4_dist.csv": "https://datadryad.org/downloads/file_stream/2811011",
    "ncst/BETVRPB4_time.csv": "https://datadryad.org/downloads/file_stream/2811010",
    "ncst/BETVRPB4.csv": "https://datadryad.org/downloads/file_stream/2811023",
    "ncst/README.md": "https://datadryad.org/downloads/file_stream/2811025",
    "epa/ghg-emission-factors-hub-2025.xlsx": "https://www.epa.gov/system/files/other-files/2025-01/ghg-emission-factors-hub-2025.xlsx",
    "epa/carrierPerfDataEPA.xlsx": "https://app4.erg.com/SmartWayEPA/Portal/carrierData/carrierPerfDataEPA.xlsx",
}
# Dryad's 2024 file endpoint returned HTTP 403. Fetch its public 2023 v1
# Zenodo mirror instead; do not label these files as the revised 2024 release.
FILES = {
    (name.replace("ncst/", "ncst_2023_v1/") if name.startswith("ncst/") else name):
    (f"https://zenodo.org/records/8117782/files/{Path(name).name}?download=1" if name.startswith("ncst/") else url)
    for name, url in FILES.items()
}
# The current SmartWay workbook endpoint timed out. Preserve the explicit
# data year of EPA's accessible archived file; never call it current data.
FILES.pop("epa/carrierPerfDataEPA.xlsx")
FILES["epa/carrierperfdataepa_dy2022.xlsx"] = "https://www.epa.gov/system/files/documents/2024-07/carrierperfdataepa_dy2022.xlsx"


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest_path = ROOT / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name, url in FILES.items():
        path = ROOT / name
        if path.exists() and name in manifest:
            print(f"Already downloaded: {name}", flush=True)
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Academic carbon-inventory research (public dataset download)"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read()
                content_type = response.headers.get("Content-Type", "")
                resolved_url = response.url
            if "text/html" in content_type or (name.endswith(".xlsx") and not payload.startswith(b"PK")):
                raise ValueError(f"Unexpected file response: {content_type}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            manifest[name] = {
                "source_url": url, "resolved_url": resolved_url,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                "content_type": content_type,
                "transformation": "None: original bytes preserved",
            }
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            print(f"Downloaded {name}: {len(payload)} bytes", flush=True)
        except Exception as exc:
            print(f"FAILED {name}: {exc}", flush=True)


if __name__ == "__main__":
    main()

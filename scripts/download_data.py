"""Reproducibly fetch the sources used in this prototype. Run with Python 3.11+."""
import argparse
import hashlib
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ("rairo/instances.zip", "https://raw.githubusercontent.com/ariannesilvamundim/RAIRO-OR/main/instances.zip", "eac804aa022c5825f55b01e5b3df4d962f5ce869e1f25071d09e8cd5b3bc1e36"),
    ("rairo/README.md", "https://raw.githubusercontent.com/ariannesilvamundim/RAIRO-OR/main/README.md", "97db5a1a4ce45518c5de5c5f45ab618abebe0de9d68d5e5e5ea37f6c6711c68b"),
    ("m5/sales_train_validation.csv", "https://zenodo.org/records/10203108/files/sales_train_validation.csv", "f368e66ed1dbecb48b2cc8fc589bf68b3deddbbb36bf5c88b4d6d0a09b9b6724"),
    ("m5/calendar.csv", "https://zenodo.org/records/10203108/files/calendar.csv", "d12b5914ef03e66649adf5dd9e996e6602251c22b7a6af8f1f7e3aa12f8860f5"),
]


def checksum(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-only", action="store_true")
    args = parser.parse_args()
    for name, url, expected in FILES:
        if args.benchmark_only and name.startswith("m5/"):
            continue
        path = ROOT / "data/raw" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if checksum(path) != expected:
                raise RuntimeError(f"Existing file differs from pinned source: {path}. Inspect it before replacing it.")
            print(f"Verified {name}", flush=True)
            continue
        partial = path.with_suffix(path.suffix + ".part")
        print(f"Downloading {url}", flush=True)
        with urllib.request.urlopen(url, timeout=120) as source, partial.open("wb") as dest:
            while block := source.read(1024 * 1024):
                dest.write(block)
        if checksum(partial) != expected:
            raise RuntimeError(f"Source checksum mismatch: {name}; partial file retained for inspection")
        partial.rename(path)
    archive = ROOT / "data/raw/rairo/instances.zip"
    with zipfile.ZipFile(archive) as z:
        doc = ROOT / "data/raw/rairo/readme.doc"
        if not doc.exists():
            doc.write_bytes(z.read("instances/archetti2007/readme.doc"))
    print("Raw files verified. Sources and reuse boundaries: docs/SOURCES.md")


if __name__ == "__main__":
    main()

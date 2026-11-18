import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from green_inventory.sustainability import run

run(reuse_study="--reuse-study" in sys.argv)

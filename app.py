"""Run .venv/bin/streamlit run app.py for the combined research dashboard."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from green_inventory.research_dashboard import render
render()

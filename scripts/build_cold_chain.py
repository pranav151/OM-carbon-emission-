"""Reproduce the default integrated study without modifying prior M5 results."""
from green_inventory.cold_chain import export_study

if __name__=='__main__':
    daily=export_study()
    print(daily[['source_date','policy','total_co2_kg','carbon_reduction_pct','cost_reduction_pct']].round(5).to_string(index=False))

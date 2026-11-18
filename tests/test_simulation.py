import pandas as pd
from green_inventory.simulation import simulate


def shock_history():
    # Deliberate synthetic shock for validation only, never an experiment dataset.
    frame = pd.DataFrame({"A": [0.0] * 100}, index=pd.date_range("2020-01-01", periods=100))
    frame.iloc[95, 0] = 10
    return frame


def test_unanticipated_demand_is_recorded_as_unmet_not_free_delivery():
    report = simulate(shock_history(), 95, days=1, model="seasonal_naive")
    assert report["status"] == "complete"
    assert report["metrics"]["unmet_units"] == 10
    assert report["metrics"]["fill_rate"] == 0
    assert report["metrics"]["emissions_kg"] == 0


def test_perfect_information_reference_can_plan_for_same_shock():
    report = simulate(shock_history(), 95, days=1, model="perfect_information")
    assert report["status"] == "complete"
    assert report["metrics"]["unmet_units"] == 0
    assert report["metrics"]["fill_rate"] == 1
    assert report["metrics"]["emissions_kg"] > 0

import numpy as np
import pandas as pd
import pytest
from green_inventory.data import validate_history, historical_scenario
from green_inventory.forecasting import forecast, backtest, accuracy, run_study


def history(n=160):
    # Synthetic fixture ONLY for testing; never presented as historical evidence.
    dates = pd.date_range("2020-01-01", periods=n)
    return pd.DataFrame({"A": np.arange(n) % 7 + 1., "B": (np.arange(n) % 7 + 1.) * 2}, index=dates)


def test_seasonal_forecast_on_exact_weekly_cycle():
    df = history()
    pred = forecast(df.iloc[:140], 14)
    np.testing.assert_array_equal(pred.values, df.iloc[140:154].values)


@pytest.mark.parametrize("model", ["seasonal_naive", "moving_average", "random_forest"])
def test_backtest_predictions_do_not_depend_on_future(model):
    df = history()
    a = backtest(df, model, 130, 133)
    changed = df.copy()
    changed.iloc[130:] = 9999
    b = backtest(changed, model, 130, 133)
    np.testing.assert_array_equal(a.prediction.values, b.prediction.values)
    assert not a.actual.equals(b.actual)


def test_model_selection_and_buffer_ignore_test_values():
    df = history(180)
    a = run_study(df, window=6)
    changed = df.copy()
    changed.iloc[-6:] = 500
    b = run_study(changed, window=6)
    assert a.selected == b.selected
    assert a.validation_metrics == b.validation_metrics
    pd.testing.assert_series_equal(a.buffer, b.buffer)
    assert a.test_metrics != b.test_metrics


def test_missing_days_and_negative_sales_fail():
    with pytest.raises(ValueError, match="gaps"):
        validate_history(history().drop(history().index[5]))
    df = history()
    df.iloc[0, 0] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        validate_history(df)


def test_zero_denominator_accuracy_is_explicit():
    m = accuracy(pd.DataFrame({"actual": [0, 0], "prediction": [0, 1]}))
    assert m["wape"] is None and m["mae"] == 0.5


def test_physical_assumptions_do_not_use_future_actuals():
    df = history()
    pred = forecast(df, 3)
    s = historical_scenario(df, pred)
    assert s.customers[0].initial == 8
    assert s.customers[0].demand == np.ceil(pred.A).tolist()
    assert s.provenance["physical_scenario"]["origin"] == "scenario assumption"

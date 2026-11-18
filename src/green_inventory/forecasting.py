"""Time-ordered model selection; recursive forecasts use no future observations."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from .data import validate_history

MODELS = ("seasonal_naive", "moving_average", "croston_sba", "tsb", "random_forest", "poisson_boosting", "poisson_glm",
          "random_forest_regularised", "poisson_boosting_regularised", "poisson_glm_regularised")
ML_MODELS = tuple(m for m in MODELS if m.startswith(("random_forest", "poisson_")))
LABELS = {"seasonal_naive": "Seasonal naïve", "moving_average": "28-day moving average",
          "croston_sba": "Croston–SBA", "tsb": "TSB intermittent demand", "random_forest": "Random forest",
          "poisson_boosting": "Poisson gradient boosting", "poisson_glm": "Poisson regression (α=0.1)",
          "random_forest_regularised": "Random forest · stronger regularisation",
          "poisson_boosting_regularised": "Poisson boosting · stronger regularisation",
          "poisson_glm_regularised": "Poisson regression (α=1.0)"}


def intermittent(values, method, alpha=0.1, beta=0.05):
    """SBA / TSB with first-positive initialization, only observed history updates."""
    positive = np.flatnonzero(np.asarray(values) > 0)
    if not len(positive):
        return 0.0
    first = int(positive[0])
    size, interval, elapsed = float(values[first]), float(first + 1), 1
    probability = 1.0 / interval
    for value in values[first + 1:]:
        if method == "tsb":
            probability += beta * (float(value > 0) - probability)
        if value > 0:
            size += alpha * (value - size)
            interval += alpha * (elapsed - interval)
            elapsed = 1
        else:
            elapsed += 1
    return float(size * probability if method == "tsb" else (1 - alpha / 2) * size / interval)


def _features(values, date, store):
    return [float(store == j) for j in range(10)] + [date.day_of_week, date.month, values[-1], values[-7], values[-14],
            values[-28], np.mean(values[-7:]), np.mean(values[-28:]), np.std(values[-28:]),
            np.mean(np.asarray(values[-28:]) > 0)]


def forecast(history, horizon=3, model="seasonal_naive"):
    history = validate_history(history)
    if len(history) < 56 or horizon < 1:
        raise ValueError("At least 56 daily observations and a positive horizon are required")
    if model not in MODELS:
        raise ValueError(f"Unknown forecasting model: {model}")
    # Training window fixed in advance; targets are strictly before forecast origin.
    history = history.tail(730)
    fitted = None
    if model in ML_MODELS:
        x, y = [], []
        for j, col in enumerate(history):
            vals = history[col].to_numpy()
            for t in range(28, len(vals)):
                x.append(_features(vals[:t], history.index[t], j))
                y.append(vals[t])
        regularised = model.endswith("_regularised")
        if model.startswith("random_forest"):
            fitted = RandomForestRegressor(n_estimators=80, min_samples_leaf=30 if regularised else 5,
                                            max_depth=8 if regularised else 12, random_state=42, n_jobs=1)
        elif model.startswith("poisson_boosting"):
            fitted = HistGradientBoostingRegressor(loss="poisson", max_iter=60 if regularised else 100, learning_rate=0.05,
                max_leaf_nodes=7 if regularised else 15, min_samples_leaf=50 if regularised else 30,
                l2_regularization=10, early_stopping=False, random_state=42)
        else:
            fitted = make_pipeline(StandardScaler(), PoissonRegressor(alpha=1.0 if regularised else 0.1, max_iter=300, tol=1e-7))
        if sum(y) > 0:
            with threadpool_limits(limits=1):
                fitted.fit(x, y)
        else:
            fitted = None
    dates = pd.date_range(history.index[-1] + pd.Timedelta(days=1), periods=horizon)
    result = pd.DataFrame(index=dates, columns=history.columns, dtype=float)
    for j, col in enumerate(history):
        values = history[col].tolist()
        intermittent_rate = intermittent(values, model) if model in {"croston_sba", "tsb"} else None
        moving_rate = float(np.mean(values[-28:]))
        for date in dates:
            if model == "seasonal_naive":
                p = values[-7]
            elif model == "moving_average":
                p = moving_rate
            elif intermittent_rate is not None:
                p = intermittent_rate
            else:
                with threadpool_limits(limits=1):
                    p = float(fitted.predict([_features(values, date, j)])[0]) if fitted is not None else 0.0
            p = max(0.0, p)
            result.loc[date, col] = p
            values.append(p)
    return result


def backtest(history, model, start, stop, horizon=3, step=3):
    history = validate_history(history)
    records = []
    if start < 56 or stop > len(history) or stop <= start:
        raise ValueError("Invalid time-ordered evaluation window")
    for origin in range(start, stop, step):
        length = min(horizon, stop - origin)
        pred = forecast(history.iloc[:origin], length, model)
        actual = history.iloc[origin:origin + length]
        for ahead, date in enumerate(pred.index, start=1):
            for col in history:
                records.append({"model": model, "origin": str(history.index[origin].date()),
                                "date": str(date.date()), "outlet": col, "ahead": ahead,
                                "actual": float(actual.loc[date, col]), "prediction": float(pred.loc[date, col])})
    return pd.DataFrame(records)


def accuracy(records):
    error = records.prediction - records.actual
    denominator = float(records.actual.abs().sum())
    return {"mae": float(error.abs().mean()), "rmse": float(np.sqrt(np.mean(error**2))),
            "bias": float(error.mean()), "wape": float(error.abs().sum() / denominator) if denominator else None,
            "observations": len(records)}


@dataclass
class ForecastStudy:
    selected: str
    validation_metrics: dict
    test_metrics: dict
    buffer: pd.Series
    validation: pd.DataFrame
    calibration: pd.DataFrame
    test: pd.DataFrame
    test_start: int
    horizon: int


def run_study(history, horizon=3, window=21):
    """Disjoint chronological validation, calibration and untouched test windows.

    Choose by validation MAE; calibrate chosen model on the next window; evaluate
    all candidates on the last window. Model choice never uses test errors.
    """
    history = validate_history(history)
    if len(history) < 90 + 3 * window:
        raise ValueError("At least 90 training days plus three evaluation windows required")
    start = len(history) - 3 * window
    val = pd.concat([backtest(history, model, start, start + window, horizon, horizon)
                     for model in MODELS], ignore_index=True)
    metrics = {model: accuracy(val[val.model.eq(model)]) for model in MODELS}
    selected = min(MODELS, key=lambda m: metrics[m]["mae"])
    cal = backtest(history, selected, start + window, start + 2 * window, horizon, horizon)
    # This is an empirical buffer, not a calibrated service-level guarantee.
    cal["underprediction"] = cal.actual - cal.prediction
    buffer = cal.groupby("outlet").underprediction.quantile(0.9).clip(lower=0).apply(np.ceil)
    buffer = buffer.reindex(history.columns)
    test_start = start + 2 * window
    test = pd.concat([backtest(history, model, test_start, len(history), horizon, horizon)
                      for model in MODELS], ignore_index=True)
    test_metrics = {model: accuracy(test[test.model.eq(model)]) for model in MODELS}
    return ForecastStudy(selected, metrics, test_metrics, buffer, val, cal, test, test_start, horizon)

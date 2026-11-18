"""Independent accounting and physical checks for published benchmark results."""
import json
import sqlite3
import numpy as np
import pandas as pd
import pytest
from green_inventory.research_evaluation import DB, OUT, cooling_lp


def source(name):
    with sqlite3.connect(DB) as connection:
        return pd.read_sql_query(f'SELECT * FROM {name}', connection)


def test_baseline_and_monthly_reconciliation():
    daily = pd.read_csv(OUT / 'daily_results.csv')
    monthly = pd.read_csv(OUT / 'monthly_results.csv')
    baseline = daily[daily.policy.eq('baseline')].set_index('date')
    original = source('baseline_daily').set_index('date').loc[baseline.index]
    assert np.allclose(baseline.total_kgco2e, original.operational_kgco2e_partial_scope)
    assert np.allclose(baseline.operating_cost_cu, original.operating_cost_cu)
    assert len(monthly) == 48
    for row in monthly.itertuples():
        part = daily[daily.month.eq(row.month) & daily.policy.eq(row.policy)]
        assert np.isclose(row.total_kgco2e, part.total_kgco2e.sum())
        assert np.isclose(row.operating_cost_cu, part.operating_cost_cu.sum())
        assert np.isclose(row.carbon_reduction_pct, 100*part.carbon_saved_kg.sum()/part.baseline_total_kgco2e.sum())
        assert np.isclose(row.cost_reduction_pct, 100*part.cost_saved_cu.sum()/part.baseline_operating_cost_cu.sum())
    report = json.loads((OUT / 'summary.json').read_text())
    assert all(report['checks'].values())


def test_every_route_against_saved_road_matrix():
    routes = pd.read_csv(OUT / 'selected_routes.csv')
    edges = source('logistics_edges').set_index(['from_node_key', 'to_node_key'])
    for row in routes.itertuples():
        order = json.loads(row.selected_order)
        assert sorted(order) == sorted(json.loads(row.original_order))
        sequence = [0] + order + [0]
        distance = sum(edges.loc[(f'{row.case_id}:{a}', f'{row.case_id}:{b}'), 'distance_km'] for a,b in zip(sequence,sequence[1:]))
        assert np.isclose(distance, row.distance_km)
        assert np.isclose(row.total_litres, row.traction_litres+row.idle_litres+row.reefer_litres)


def test_all_hourly_physics_and_emissions():
    h = pd.read_csv(OUT / 'hourly_results.csv').merge(source('cold_zones'), on='zone_id', suffixes=('', '_zone'))
    assert np.allclose(h.temperature_end_c-h.temperature_start_c, (h.total_heat_kwh_th-h.cop*h.power_kw)/h.thermal_capacity_kwh_per_c)
    assert h.temperature_end_c.ge(h.temperature_min_c-1e-6).all()
    assert h.temperature_end_c.le(h.temperature_max_c+1e-6).all()
    assert h.power_kw.between(-1e-6,h.max_power_kw+1e-6).all()
    assert np.allclose(h.energy_kwh, h.power_kw+h.auxiliary_energy_kwh)
    assert np.allclose(h.storage_kgco2,h.energy_kwh*h.grid_kgco2_per_kwh)
    for _,part in h.groupby(['policy','zone_id']):
        part = part.sort_values('timestamp')
        assert np.allclose(part.temperature_start_c.iloc[1:],part.temperature_end_c.iloc[:-1])


def test_fixed_temperature_removes_storage_flexibility():
    h = pd.read_csv(OUT / 'hourly_results.csv')
    h = h[h.policy.eq('baseline') & h.date.eq(h.date.min())]
    zones = source('cold_zones')
    zones['temperature_min_c'] = zones.baseline_setpoint_c
    zones['temperature_max_c'] = zones.baseline_setpoint_c
    solved = cooling_lp(h,zones,h.electricity_cost_cu.sum()+1e-6)
    assert np.allclose(solved.power_kw,solved.total_heat_kwh_th/solved.cop)
    with pytest.raises(RuntimeError,match='infeasible/failed'):
        cooling_lp(h,zones,0)

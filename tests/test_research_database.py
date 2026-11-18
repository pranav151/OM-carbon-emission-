"""Integration checks on published dataset artifacts, including source lineage."""
from pathlib import Path
import hashlib
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/research_database'


@pytest.fixture(scope='module')
def db():
    p=OUT/'sustainable_inventory.sqlite'
    assert p.exists(), 'Build the research database first'
    connection=sqlite3.connect(f'file:{p}?mode=ro',uri=True)
    yield connection
    connection.close()


def test_relations_and_integrity(db):
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_source_hashes_match_repository_manifests():
    base=ROOT/'data/research/combined_sources'
    for entry in json.loads((base/'vtt_files2.txt').read_text()):
        assert hashlib.sha256((base/'vtt'/entry['filename']).read_bytes()).hexdigest()==entry['content_details']['sha256_hash']
    for entry in json.loads((base/'ornl_metadata.json').read_text())['files']:
        assert hashlib.md5((base/'ornl'/entry['name']).read_bytes()).hexdigest()==entry['computed_md5']


def test_replay_keeps_missing_values_visible_and_has_real_lineage(db):
    d=pd.read_sql_query('''SELECT h.source_power_value,h.profile_method,v.refrigeration
        FROM hourly_inputs h JOIN vtt_power_observations v ON v.record_id=h.source_record_id''',db)
    assert np.allclose(d.source_power_value,d.refrigeration,equal_nan=True)
    assert d.source_power_value.isna().any()
    assert d.loc[d.source_power_value.isna(),'profile_method'].str.startswith(('imputed_','synthetic_')).all()
    assert db.execute('SELECT count(*) FROM hourly_inputs').fetchone()[0]==8760


def test_inventory_continuity_expiry_and_costs(db):
    d=pd.read_sql_query('SELECT * FROM inventory_daily ORDER BY product_id,date',db)
    assert np.allclose(d.opening_kg+d.receipts_kg-d.shipped_kg-d.spoilage_kg,d.closing_kg)
    for _,g in d.groupby('product_id'):
        assert np.allclose(g.opening_kg.iloc[1:],g.closing_kg.iloc[:-1])
    assert (d[['closing_kg','receipts_kg','spoilage_kg','shortage_kg']].to_numpy()>=-1e-7).all()
    assert np.allclose(d.demand_kg,d.shipped_kg+d.shortage_kg)
    actual=pd.read_sql_query('SELECT date,product_id,sum(demand_kg) AS quantity FROM orders GROUP BY date,product_id',db)
    joined=d.merge(actual,on=['date','product_id'])
    assert np.allclose(joined.demand_kg,joined.quantity)


def test_truck_load_paths_and_fuel_accounting(db):
    t=pd.read_sql_query('SELECT * FROM baseline_trips',db)
    s=pd.read_sql_query('SELECT * FROM baseline_stops',db)
    delta=np.where(s.stop_type.eq('Pickup'),s.quantity_kg,-s.quantity_kg)
    assert np.allclose(s.load_before_kg+delta,s.load_after_kg)
    assert (s.load_after_kg>=-1e-6).all()
    assert t.capacity_feasible.all() and t.time_feasible.all()
    assert np.allclose(t.traction_litres+t.idle_litres+t.reefer_litres,t.total_litres)
    assert np.allclose(t.transport_kgco2,t.total_litres*(10.21/3.785411784))


def test_thermal_and_electricity_accounting(db):
    d=pd.read_sql_query('''SELECT c.*,h.grid_kgco2_per_kwh,h.electricity_cu_per_kwh,z.temperature_min_c,z.temperature_max_c
        FROM cold_storage_hourly c JOIN hourly_inputs h USING(timestamp) JOIN cold_zones z USING(zone_id)''',db)
    assert np.allclose(d.total_heat_kwh_th,d.background_heat_kwh_th+d.product_heat_kwh_th+d.door_heat_kwh_th+d.auxiliary_energy_kwh)
    assert np.allclose(d.total_heat_kwh_th,d.cop*d.baseline_power_kw)
    assert np.allclose(d.baseline_energy_kwh,d.baseline_power_kw+d.auxiliary_energy_kwh)
    assert np.allclose(d.baseline_storage_kgco2,d.baseline_energy_kwh*d.grid_kgco2_per_kwh)
    assert np.allclose(d.baseline_electricity_cost_cu,d.baseline_energy_kwh*d.electricity_cu_per_kwh)
    assert d.baseline_temperature_c.between(d.temperature_min_c,d.temperature_max_c).all()
    assert d.power_feasible.all()


def test_carbon_boundary_and_monthly_totals(db):
    d=pd.read_sql_query('SELECT * FROM baseline_daily',db)
    m=pd.read_sql_query('SELECT * FROM baseline_monthly',db)
    assert len(m)==12
    assert np.allclose(d.operational_kgco2e_partial_scope,d.transport_kgco2+d.inbound_kgco2+d.baseline_storage_kgco2+d.refrigerant_leak_kgco2e)
    assert np.allclose(d.expanded_kgco2e_with_spoilage,d.operational_kgco2e_partial_scope+d.spoilage_embodied_kgco2e)
    for col in ['operating_cost_cu','operational_kgco2e_partial_scope','modelled_contribution_cu','baseline_energy_kwh']:
        assert np.isclose(d[col].sum(),m[col].sum())
    assert m.observed_days.sum()==0


def test_complete_documentation_and_no_fabricated_savings(db):
    catalog=pd.read_sql_query('SELECT * FROM table_catalog',db)
    fields=pd.read_sql_query('SELECT * FROM field_dictionary',db)
    for t in catalog.table_name:
        assert t in set(fields.table_name)
    assert len(db.execute('SELECT * FROM optimization_factors').fetchall())==10
    report=json.loads((OUT/'validation_report.json').read_text())
    assert all(report['checks'].values())
    assert report['savings_status']=='not evaluated; database and feasible baseline only'
    assert np.isclose(sum(x['percent'] for x in report['composition']['by_category'].values()),100)

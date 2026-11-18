from dataclasses import replace
import json
import numpy as np
import pytest
from green_inventory.cold_chain import Settings, load_cold_measurements, hourly_profiles, route_candidates, solve_day, load_freight, route_metrics


def test_source_dates_units_and_quality():
    m=load_cold_measurements()
    assert len(m)==8634
    assert len(m.source_file.unique())==6
    january=m[m.source_file.str.contains('January')]
    assert set(january.timestamp.dt.year)=={2020}
    assert set(m[m.site.eq('Rome')].lt_power_unit_source)=={'W'}
    assert set(m[m.site.eq('Trento')].lt_power_unit_source)=={'kW'}
    assert m[m.quality_flag.eq('negative_power_preserved')].lt_power_kw.lt(0).all()
    assert m[m.site.eq('Trento')].ambient_c.isna().all()
    p=hourly_profiles(m)
    assert len(p)==72
    assert p.samples.sum()==4319


@pytest.mark.parametrize('case',[1,2,3,4])
def test_every_route_retains_stops_and_relative_constraints(case):
    r=route_candidates(case,Settings())
    n,d,t=load_freight(case)
    all_stops=[]
    for _,g in r.groupby('truck'):
        a,b=g.set_index('option').loc[0],g.set_index('option').loc[1]
        old,new=json.loads(a.stop_sequence),json.loads(b.stop_sequence)
        assert sorted(old)==sorted(new)
        assert list(n.loc[old,'stop_type'])==list(n.loc[new,'stop_type'])
        assert b.distance_km<=a.distance_km+1e-8
        assert b.duration_h<=a.duration_h+1e-8
        assert b.peak_load_source_units<=a.peak_load_source_units+1e-8
        assert route_metrics(new,n,d,t)[0]==pytest.approx(b.distance_km)
        all_stops.extend(new)
    assert sorted(all_stops)==list(range(1,len(n)))


def test_zero_buffer_has_no_cooling_savings_and_balances_close():
    s=replace(Settings(),buffer_kwh_th=0,dock_heat_kwh_th_per_truck=0)
    p=hourly_profiles(load_cold_measurements()).query('source_date == "2019-08-12"')
    routes=route_candidates(1,s)
    base,hb,_=solve_day(p,routes,s,'baseline')
    cold,hc,_=solve_day(p,routes,s,'storage')
    assert cold['refrigeration_kwh']==pytest.approx(base['refrigeration_kwh'])
    np.testing.assert_allclose(hc.modeled_electricity_kwh,hc.observed_lt_power_kw,atol=1e-7)
    assert hc.modeled_buffer_kwh_th.abs().max()<1e-7


def test_combined_cost_cap_full_cooling_and_accounting():
    s=Settings()
    p=hourly_profiles(load_cold_measurements()).query('source_date == "2020-01-13"')
    routes=route_candidates(1,s)
    base,_,_=solve_day(p,routes,s,'baseline')
    result,h,r=solve_day(p,routes,s,'combined')
    assert result['total_cost_cu']<=base['total_cost_cu']+1e-5
    assert result['total_co2_kg']<=base['total_co2_kg']+1e-5
    assert result['served_stops']==base['served_stops']==47
    assert result['total_co2_kg']==pytest.approx(result['cold_co2_kg']+result['transport_co2_kg'])
    assert result['refrigeration_kwh']==pytest.approx(h.modeled_electricity_kwh.sum())
    assert result['distance_km']==pytest.approx(r.distance_km.sum())
    assert h.modeled_buffer_kwh_th.iloc[-1]==pytest.approx(0,abs=1e-7)
    # Independent heat balance: generation = demand + storage losses.
    generated=(h.inferred_cop*h.modeled_electricity_kwh).sum()
    demand=(h.inferred_heat_load_kwh_th+h.synthetic_dock_heat_kwh_th).sum()
    loss=s.hourly_loss*h.modeled_buffer_kwh_th.iloc[:-1].sum()
    assert generated==pytest.approx(demand+loss,abs=1e-6)


def test_rejects_invalid_assumptions():
    with pytest.raises(ValueError):replace(Settings(),buffer_kwh_th=-1).validate()
    with pytest.raises(ValueError):replace(Settings(),hourly_loss=1).validate()

import json
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from green_inventory.sustainability import monthly_ledger, percent_reduction
from green_inventory.dashboard import totals
from green_inventory.forecasting import intermittent, forecast, ML_MODELS

ROOT=Path(__file__).resolve().parents[1]

def fixture_ledger():
    rows=[]
    for date, month, cost, co2 in [('2020-01-31','2020-01',100.,10.),('2020-02-01','2020-02',200.,20.)]:
        for policy,mult in [('baseline',1.),('candidate',1.2)]:
            rows.append(dict(date=date,month=month,policy=policy,cost=cost*mult,emissions_kg=co2*mult,
                actual_units=10.,served_units=9.,unmet_units=1.,transport_cost=cost*mult,
                outlet_holding_cost=0.,depot_holding_cost=0.,distance_km=5.,routes=1,
                closing_outlet_stock=2.,closing_depot_stock=3.))
    return pd.DataFrame(rows)

def test_increases_remain_negative_savings_and_zero_baseline_unavailable():
    assert percent_reduction(100,120)==-20
    assert percent_reduction(0,10) is None
    m=monthly_ledger(fixture_ledger())
    c=m[m.policy.eq('candidate')]
    assert (c.cost_saved<0).all() and (c.carbon_reduction_pct<0).all()
    assert not c.service_qualified.any()

def test_aggregate_percentage_uses_totals():
    d=fixture_ledger()
    d.loc[d.policy.eq('candidate') & d.month.eq('2020-02'),'emissions_kg']=10.
    t=totals(d,'candidate',['2020-01','2020-02'])
    assert t['carbon_pct']==pytest.approx(100*(30-22)/30)

def test_mismatched_or_duplicate_dates_rejected():
    d=fixture_ledger()
    with pytest.raises(ValueError,match='identical'):
        monthly_ledger(d.iloc[:-1])
    with pytest.raises(ValueError,match='Duplicate'):
        monthly_ledger(pd.concat([d,d.iloc[:1]]))

def test_tsb_decays_after_zero_sales_and_sba_does_not():
    values=[2.,0.,0.,2.,0.]
    assert intermittent(values+[0.]*20,'tsb')<intermittent(values,'tsb')
    assert intermittent(values+[0.]*20,'croston_sba')==intermittent(values,'croston_sba')
    assert intermittent([0.]*30,'tsb')==0

@pytest.mark.parametrize('model',ML_MODELS)
def test_nonnegative_models_support_all_zero_history(model):
    frame=pd.DataFrame({'A':np.zeros(90)},index=pd.date_range('2020-01-01',periods=90))
    assert (forecast(frame,3,model).values==0).all()

@pytest.mark.skipif(not (ROOT/'outputs/transformed_demand.csv').exists(),reason='Export transformed data first')
def test_transformed_data_preserves_sales_and_lags():
    data=pd.read_csv(ROOT/'outputs/transformed_demand.csv')
    raw=pd.read_csv(ROOT/'data/processed/m5_history.csv',index_col='date')
    assert len(data)==9565 and data.observed_sales_units.sum()==raw.sum().sum()
    for outlet,frame in data.groupby('outlet'):
        f=frame.sort_values('date')
        np.testing.assert_allclose(f.lag_1.iloc[1:],f.observed_sales_units.iloc[:-1])
        np.testing.assert_allclose(f.past_28_day_mean.iloc[28:],f.observed_sales_units.shift(1).rolling(28).mean().iloc[28:])
        assert f.features_ready.sum()==len(f)-28

@pytest.mark.skipif(not (ROOT/'results/sustainability/completed_study.json').exists(),reason='Run monthly study first')
def test_saved_study_selected_on_validation_and_months_reconcile():
    p=ROOT/'results/sustainability'
    study=json.loads((p/'completed_study.json').read_text())
    assert study['selected_ml']==min(ML_MODELS,key=lambda m:study['validation'][m]['rmse'])
    daily=pd.read_csv(p/'daily_results.csv')
    saved=pd.read_csv(p/'monthly_results.csv')
    rebuilt=monthly_ledger(daily)
    pd.testing.assert_frame_equal(saved,rebuilt,check_dtype=False,atol=1e-8,rtol=1e-8)
    assert daily.groupby('policy').size().eq(91).all()
    assert daily.solver_status.eq('optimal').all()

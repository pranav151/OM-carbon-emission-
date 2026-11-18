"""Exercise the six research pages and reporting controls."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def app():
    return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60).run()


def test_every_research_page_renders():
    view = app()
    assert not view.exception
    for page in ['Monthly outcomes', 'Cold storage', 'Transport & logistics',
                 'Inventory & service', 'Data & methods']:
        view.sidebar.radio[0].set_value(page).run()
        assert not view.exception, page


def test_baseline_and_month_filter():
    view = app()
    view.sidebar.selectbox[0].set_value('baseline').run()
    assert not view.exception
    assert any('0.00%' in item.value for item in view.markdown)
    view.sidebar.multiselect[0].set_value(['2018-04'])
    view.sidebar.radio[0].set_value('Monthly outcomes').run()
    assert not view.exception
    assert len(view.dataframe[0].value) == 1
    assert view.dataframe[0].value.iloc[0]['carbon_reduction_pct'] == 0
    view.sidebar.multiselect[0].set_value([]).run()
    assert not view.exception
    assert any('Select at least one' in item.value for item in view.info)


def test_storage_policy_does_not_claim_route_changes():
    view = app()
    view.sidebar.selectbox[0].set_value('storage')
    view.sidebar.radio[0].set_value('Transport & logistics').run()
    assert not view.exception
    frame = view.dataframe[0].value
    assert frame.iloc[0]['distance_km'] == frame.iloc[1]['distance_km']
    assert frame.iloc[0]['total_litres'] == frame.iloc[1]['total_litres']

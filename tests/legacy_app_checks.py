from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_pages_and_stale_settings():
    app = AppTest.from_file(str(ROOT / "legacy_app.py"), default_timeout=30).run()
    assert not app.exception
    for page in ["Monthly savings", "Model intelligence", "Transformed data", "Research & algorithms", "Delivery planner"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    app.slider[0].set_value(2.0).run()
    assert any("Settings changed" in w.value for w in app.warning)
    app.button[0].click().run()
    assert not app.exception
    assert not any("Settings changed" in w.value for w in app.warning)


@pytest.mark.skipif(not (ROOT / "data/processed/m5_history.csv").exists(), reason="Prepare M5 sales first")
def test_forecast_to_plan_connection():
    app = AppTest.from_file(str(ROOT / "legacy_app.py"), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Delivery planner").run()
    app.button[0].click().run()
    assert not app.exception
    assert any("Independently validated" in s.value for s in app.success)
    app.sidebar.radio[0].set_value("Model intelligence").run()
    assert not app.exception
    assert len(app.dataframe) >= 1


def test_cold_chain_zero_buffer_and_source_explorer():
    app=AppTest.from_file(str(ROOT/'legacy_app.py'),default_timeout=45).run()
    assert not app.exception
    assert app.sidebar.radio[0].value=='Cold-chain lab'
    assert len(app.tabs)==5
    app.slider[0].set_value(0.0)
    app.button[0].click().run()
    assert not app.exception
    _,settings,result=app.session_state['cold_run']
    assert settings.buffer_kwh_th==0
    daily=result[0]
    baseline=daily[daily.policy.eq('baseline')].set_index('source_date')
    cold=daily[daily.policy.eq('storage')].set_index('source_date')
    assert (baseline.refrigeration_kwh-cold.refrigeration_kwh).abs().max()<1e-6
    app.sidebar.radio[0].set_value('Cold-chain data').run()
    assert not app.exception
    assert app.metric[0].value=='8,634'
    app.selectbox[0].set_value('Trento').run()
    assert not app.exception

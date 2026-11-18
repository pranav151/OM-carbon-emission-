"""UI for a traceable cross-source refrigeration and delivery experiment."""
from dataclasses import asdict, replace
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from .cold_chain import (Settings, POLICIES, ROOT, COLD, FREIGHT, run_study, load_cold_measurements, hourly_profiles, load_freight)
from .dashboard import card, chart_style, GREEN, BLUE


@st.cache_data(show_spinner=False)
def cached_study(case, settings, engine_revision=2):
    return run_study(case,settings)


def hero(data=False):
    title='Follow the evidence.' if data else 'Cold storage. Deliveries.<br><span>One carbon decision.</span>'
    description='Open original records, inspect transformations, and trace the scenario connection.' if data else 'Measured refrigeration profiles meet real-operation-derived delivery cases in a transparent optimisation experiment.'
    st.markdown(f'<section class="hero"><div><div class="eyebrow">GREEN INVENTORY / COLD-CHAIN RESEARCH</div><h1>{title}</h1><p>{description}</p><div class="hero-tags"><span class="pill">MEASURED INPUTS</span><span class="pill">MODELED OUTCOMES</span></div></div></section>',unsafe_allow_html=True)
    st.info('Research simulation · Italian refrigeration profiles + California delivery cases. The businesses and dates are unrelated. Savings below are calculated counterfactuals, not measured reductions after deployment.')


def csv_download(label,frame,name):
    st.download_button(label,frame.to_csv(index=False),name,'text/csv',key=f'cold_{name}')


def render_lab():
    hero()
    with st.expander('How this page works',expanded=False):
        st.write('Choose a delivery case and thermal-buffer assumptions, then run the scenario. Compare transport-only, cold-storage-only and combined decisions. Every scenario fulfils the same stops and cooling-load proxy. Cost is in illustrative cost units (CU), not company accounts.')
        st.write('The refrigeration model covers the low-temperature compressor rack only. Other refrigeration/HVAC, refrigerant leakage, vehicle cooling, product spoilage, upstream emissions and retrofit capital costs are excluded.')
    with st.form('cold_scenario'):
        a,b,c=st.columns(3)
        with a:
            case=st.selectbox('Delivery case',[1,2,3,4],format_func=lambda n:f'NCST {n} · {[47,58,71,90][n-1]} customer stops')
            capacity=st.slider('Assumed thermal buffer (kWh thermal)',0.0,40.0,4.0,1.0,help='An assumed thermal store or validated equivalent flexibility; not a measured property of these facilities.')
        with b:
            loss=st.slider('Assumed buffer loss (% per hour)',0.0,5.0,1.0,0.25)
            docking=st.slider('Added docking heat per truck (kWh thermal)',0.0,10.0,2.0,0.5,help='Synthetic receiving load added to the same measured refrigeration profile. It links return routes to cooling demand.')
        with c:
            grid=st.number_input('Scenario electricity factor (kg CO₂/kWh)',0.0,2.0,float(Settings().grid_kg_co2_per_kwh),0.01,format='%.5f',help='Default is EPA 2025 Hub CAMX CO₂ factor converted from lb/MWh. Applied as a virtual-site factor, not Italian historical emissions.')
            fuel=st.number_input('Assumed diesel consumption (L/km)',0.01,2.0,0.30,0.01)
        run=st.form_submit_button('Run combined scenario',type='primary')
    settings=replace(Settings(),buffer_kwh_th=capacity,hourly_loss=loss/100,dock_heat_kwh_th_per_truck=docking,grid_kg_co2_per_kwh=grid,diesel_litres_per_km=fuel)
    if run or 'cold_run' not in st.session_state or st.session_state.get('cold_engine_revision')!=2:
        with st.spinner('Solving cooling schedules and route choices, then checking balances…'):
            result=cached_study(case,settings,2)
        st.session_state.cold_run=(case,settings,result)
        st.session_state.cold_engine_revision=2
    used_case,used_settings,(daily,hourly,candidates,chosen,measurements)=st.session_state.cold_run
    if (case,settings)!=(used_case,used_settings):
        st.warning('Settings changed. Run the scenario to update results and exports.')
    st.caption(f'Active results: NCST {used_case} · {used_settings.buffer_kwh_th:g} kWh thermal buffer · 3 sampled Rome profiles · all settings travel with the CSV export.')
    comparison, cooling, routing, ledger, method=st.tabs(['Combined impact','Cold storage','Deliveries','Connected dataset','Methods & assumptions'])
    with comparison:
        totals=daily.groupby('policy').sum(numeric_only=True)
        base=totals.loc['baseline'];opt=totals.loc['combined']
        reduction=100*(base.total_co2_kg-opt.total_co2_kg)/base.total_co2_kg if base.total_co2_kg else None
        cols=st.columns(4)
        with cols[0]:card('Modeled combined CO₂',f'{opt.total_co2_kg:,.2f} kg',f'Baseline {base.total_co2_kg:,.2f} kg · three scenario replays')
        with cols[1]:card('Modeled CO₂ avoided',f'{base.total_co2_kg-opt.total_co2_kg:,.2f} kg','Zero baseline: percentage unavailable' if reduction is None else f'{reduction:.3f}% reduction within this model','positive')
        with cols[2]:card('Operating cost saved',f'{base.total_cost_cu-opt.total_cost_cu:,.2f} CU','Illustrative costs; excludes capital investment','positive')
        with cols[3]:card('Thermal balance residual',f'{daily.thermal_balance_max_error.max():.1e}',f'{int(opt.served_stops)} stop services across three replays · no stops dropped')
        c1,c2=st.columns(2)
        with c1,st.container(border=True):
            st.subheader('Which intervention makes the difference?')
            fig=go.Figure()
            for key,label,color in [('transport_co2_kg','Transport',BLUE),('cold_co2_kg','Low-temperature rack + docking',GREEN)]:
                fig.add_bar(x=[POLICIES[p] for p in POLICIES],y=[totals.loc[p,key] for p in POLICIES],name=label,marker_color=color)
            fig.update_layout(barmode='stack',yaxis_title='Modeled kg CO₂ · three replays')
            st.plotly_chart(chart_style(fig,370),width='stretch')
        with c2,st.container(border=True):
            st.subheader('Separate the sources of savings')
            transport_saved=base.transport_co2_kg-opt.transport_co2_kg
            cold_saved=base.cold_co2_kg-opt.cold_co2_kg
            fig=go.Figure(go.Bar(x=['Transport','Cold storage'],y=[transport_saved,cold_saved],marker_color=[BLUE,GREEN],text=[f'{transport_saved:.3f}',f'{cold_saved:.3f}'],textposition='outside'))
            fig.update_layout(yaxis_title='Modeled kg CO₂ avoided')
            st.plotly_chart(chart_style(fig,370),width='stretch')
            st.caption(f'Cold-storage contribution: {cold_saved:.4f} kg CO₂. Small or zero savings are retained; the optimiser does not target a predetermined percentage.')
        st.subheader('Sample-day scorecard')
        st.caption('These are three sampled profiles from Aug/Sep 2019 and Jan 2020. They are not full monthly results or a continuous six-month history.')
        score=daily[daily.policy.eq('combined')][['source_date','refrigeration_kwh','distance_km','total_co2_kg','carbon_saved','carbon_reduction_pct','cost_saved','cost_reduction_pct','audit_passed']]
        st.dataframe(score.round(5),hide_index=True,width='stretch')
        csv_download('Download complete combined comparison',daily,'integrated_daily.csv')
    with cooling:
        st.subheader('The refrigeration experiment')
        st.write('Real input: Rome low-temperature compressor power and outside temperature. Model: an assumed thermal buffer shifts cooling between hours with different estimated efficiency. Product temperature is not measured by this experiment, so it cannot certify safe setpoints.')
        date=st.selectbox('Sample profile',sorted(hourly.source_date.unique()),key='cold_day')
        h=hourly[hourly.source_date.eq(date)]
        a,b=st.columns(2)
        with a,st.container(border=True):
            fig=go.Figure()
            observed=h[h.policy.eq('baseline')]
            fig.add_scatter(x=observed.hour,y=observed.observed_lt_power_kw,name='Measured profile, hour means',line=dict(color='#9bb7cc',dash='dot'))
            for p in ('baseline','storage','combined'):
                rows=h[h.policy.eq(p)]
                fig.add_scatter(x=rows.hour,y=rows.modeled_electricity_kwh,name=POLICIES[p])
            fig.update_layout(xaxis_title='Hour in replay',yaxis_title='kWh in 1-hour modeled interval')
            st.plotly_chart(chart_style(fig,380),width='stretch')
        with b,st.container(border=True):
            rows=h[h.policy.eq('combined')]
            fig=go.Figure(go.Scatter(x=rows.hour,y=rows.modeled_buffer_kwh_th,fill='tozeroy',line=dict(color=GREEN),name='Thermal inventory'))
            fig.add_hline(y=used_settings.buffer_kwh_th,line_dash='dot',annotation_text='Assumed capacity')
            fig.update_layout(xaxis_title='Hour in replay',yaxis_title='Stored cooling (kWh thermal)')
            st.plotly_chart(chart_style(fig,380),width='stretch')
        ds=daily[daily.source_date.eq(date)].set_index('policy')
        bq,oq=ds.loc['baseline','refrigeration_kwh'],ds.loc['storage','refrigeration_kwh']
        st.metric('Cold-storage-only electricity reduction',f'{bq-oq:.4f} kWh',f'{100*(bq-oq)/bq:.4f}% of the modeled cooling baseline')
        st.caption('No blanket efficiency discount is applied. Savings follow the solved hourly balance, assumed COP, power limit and buffer losses. The measured input profile alone cannot identify a causal energy model.')
        if abs(100*(bq-oq)/bq)<1:
            st.info('The nominal cooling improvement is below 1% in this run. With an uncalibrated thermal model, this does not establish a practically meaningful refrigeration saving.')
        st.dataframe(h[h.policy.eq('combined')][['hour','samples','observed_lt_power_kw','ambient_c','inferred_cop','inferred_heat_load_kwh_th','synthetic_dock_heat_kwh_th','modeled_electricity_kwh','modeled_buffer_kwh_th']].round(5),hide_index=True,width='stretch')
        csv_download('Download all hourly calculations',hourly,'integrated_hourly.csv')
    with routing:
        st.subheader('Every stop retained, fewer road kilometres')
        st.caption('Original truck assignments are retained. Baseline order is reconstructed from source-row order; improved order uses 2-opt within delivery/pickup blocks. Reported duration/load checks are relative to the reconstructed baseline, not actual vehicle-capacity certification.')
        truck=st.selectbox('Truck',sorted(candidates.truck.unique()),key='cold_truck')
        nodes,_,_=load_freight(used_case)
        fig=go.Figure()
        for option,label,color in [(0,'Reconstructed baseline',BLUE),(1,'2-opt candidate',GREEN)]:
            r=candidates[(candidates.truck==truck)&(candidates.option==option)].iloc[0]
            order=[0]+json.loads(r.stop_sequence)+[0]
            loc=nodes.loc[order]
            fig.add_scatter(x=loc.longitude,y=loc.latitude,mode='lines+markers',name=label,line=dict(color=color),text=loc.index.astype(str))
        fig.update_layout(xaxis_title='Longitude',yaxis_title='Latitude')
        st.plotly_chart(chart_style(fig,420),width='stretch')
        st.caption('Lines connect stops schematically. Optimisation uses the supplied road-distance matrix, not these straight lines.')
        st.dataframe(candidates[['truck','option','distance_km','duration_h','peak_load_source_units','return_hour','stops']].round(3),hide_index=True,width='stretch')
        csv_download('Download route candidates',candidates,'route_candidates.csv')
    with ledger:
        st.subheader('One analysis dataset, traceable source records')
        st.write('One row represents one policy × refrigeration profile × delivery case. Source IDs and original dates are preserved. The mapping is a scenario relationship—not an observed company join. Hourly refrigeration and stop-level routes remain separate tables to prevent duplicated energy totals.')
        st.dataframe(daily,hide_index=True,width='stretch')
        csv_download('Download active scenario settings',pd.DataFrame([asdict(used_settings)]),'active_scenario_settings.csv')
        st.link_button('Open MultiPACK source', 'https://doi.org/10.18710/T5OHPR')
        st.link_button('Open NCST source', 'https://zenodo.org/records/8117782')
    with method:
        st.markdown((ROOT/'docs/COLD_CHAIN_METHOD.md').read_text())
        st.json(asdict(used_settings))


def render_data():
    hero(data=True)
    measured=load_cold_measurements()
    tabs=st.tabs(['Measured refrigeration','Original files','Data quality & provenance'])
    with tabs[0]:
        a,b,c=st.columns(3)
        a.metric('Measured records',f'{len(measured):,}')
        b.metric('Field sites','2')
        c.metric('Sampled site profiles','6')
        site=st.selectbox('Refrigeration site',['Rome','Trento'])
        available=measured[measured.site.eq(site)].source_file.unique()
        file=st.selectbox('Source file',available)
        shown=measured[measured.source_file.eq(file)]
        st.caption(f'Original timestamp range: {shown.timestamp.min()} to {shown.timestamp.max()}. Refrigeration-system sensors do not establish food temperature.')
        fig=px.line(shown,x='timestamp',y='lt_power_kw',labels={'lt_power_kw':'Low-temperature rack power (kW)'})
        st.plotly_chart(chart_style(fig,340),width='stretch')
        st.dataframe(shown,hide_index=True,width='stretch')
        csv_download('Download all transformed refrigeration records',measured,'cold_measurements.csv')
    with tabs[1]:
        st.write('Original text files are preserved byte for byte. Rome power is supplied in W; Trento power is supplied in kW. The download manifest records source checksums.')
        path=st.selectbox('Original MultiPACK file',sorted(p.name for p in COLD.glob('*.txt')))
        st.download_button('Download original text file',(COLD/path).read_bytes(),path,key='cold_original')
        case=st.selectbox('Original delivery case',[1,2,3,4],key='cold_data_case')
        original=pd.read_csv(FREIGHT/f'BETVRPB{case}.csv')
        st.dataframe(original,hide_index=True,width='stretch')
        st.download_button('Download original delivery CSV',(FREIGHT/f'BETVRPB{case}.csv').read_bytes(),f'BETVRPB{case}.csv','text/csv')
        st.link_button('Full public refrigeration repository','https://doi.org/10.18710/T5OHPR')
    with tabs[2]:
        st.markdown((ROOT/'data/research/cold_storage/README.md').read_text())
        coverage=measured.groupby(['site','source_file']).agg(records=('timestamp','size'),first_timestamp=('timestamp','min'),last_timestamp=('timestamp','max'),negative_lt_readings=('lt_power_kw',lambda x:int((x<0).sum()))).reset_index()
        st.dataframe(coverage,hide_index=True,width='stretch')
        st.write('No synthetic rows are added to the measured-record table. Model inputs such as COP, buffer size, docking heat, costs and cross-source mapping are assumptions. A single “percentage real” would hide these critical assumptions.')

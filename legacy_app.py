"""Archived earlier M5 and three-day prototypes. Main dashboard is app.py."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
import json
from copy import deepcopy
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from green_inventory.data import ROOT,load_history,load_benchmark,illustrative_benchmark
from green_inventory.forecasting import MODELS,ML_MODELS,LABELS,forecast
from green_inventory.optimisation import solve,has_solution
from green_inventory.evaluation import evaluate
from green_inventory.sustainability import OUT,monthly_scenario
from green_inventory.dashboard import card,totals,chart_style,month_chart,route_chart,POLICIES,GREEN,reduction_chart,ranking_chart

from green_inventory.presentation import apply_theme,page_intro,footer

st.set_page_config(page_title='Green Inventory | Sustainability analytics',page_icon='🌿',layout='wide',initial_sidebar_state='expanded')
apply_theme()

@st.cache_data(show_spinner=False)
def predict(h,m):return forecast(h,3,m)

@st.cache_data(show_spinner=False)
def plan_for(s):
    p=solve(s,time_limit=20)
    return p,evaluate(s,p) if has_solution(p) else None

def download(label,df,name):st.download_button(label,df.to_csv(index=False),name,'text/csv')

with st.sidebar:
    st.markdown('<div class="brand"><div class="brand-icon">◈</div><div><div class="brand-name">Green Inventory</div><div class="brand-sub">SUSTAINABILITY INTELLIGENCE</div></div></div><div class="side-label">YOUR WORKSPACE</div>',unsafe_allow_html=True)
    page=st.radio('Workspace',['Cold-chain lab','Cold-chain data','Overview','Monthly savings','Model intelligence','Delivery planner','Transformed data','Research & algorithms'],label_visibility='collapsed')
    if page.startswith('Cold-chain'):
        st.markdown('<div class="side-note"><strong><span class="status-dot"></span>Integrated carbon study</strong><p>MultiPACK refrigeration<br>NCST delivery operations<br>Measured inputs · modeled savings</p></div>',unsafe_allow_html=True)
        st.caption('New cold-chain study. Other pages retain the earlier M5 sales experiment.')
    else:
        st.markdown('<div class="side-note"><strong><span class="status-dot"></span>Earlier M5 experiment</strong><p>01 product · 05 outlets<br>M5 historical unit sales<br>Jan–Mar 2016 replay</p></div>',unsafe_allow_html=True)
        st.caption('Transport combustion CO₂ only. Illustrative network and fleet. Cost units, not currency.')
if page.startswith('Cold-chain'):
    from green_inventory.cold_chain_dashboard import render_lab, render_data
    if page=='Cold-chain lab':render_lab()
    else:render_data()
    st.caption('GREEN INVENTORY · Cross-source research scenario · Calculated counterfactuals, not deployed savings')
    st.stop()
page_intro(page)
ready=(OUT/'completed_study.json').exists() and (OUT/'monthly_results.csv').exists()
summary=json.loads((OUT/'completed_study.json').read_text()) if ready else None
history=load_history()
if ready:
    daily=pd.read_csv(OUT/'daily_results.csv')
    monthly=pd.read_csv(OUT/'monthly_results.csv')

if page in ['Overview','Monthly savings']:
    if not ready:st.info('The expanded monthly study is running. Results appear after every policy finishes.');st.stop()
    a,b,c=st.columns([2,2,1])
    with a:policy=st.selectbox('Planning approach',['carbon_aware','selected_ml'],format_func=lambda p:POLICIES[p])
    with b:months=st.multiselect('Reporting months',sorted(daily.month.unique()),default=sorted(daily.month.unique()))
    with c:st.caption('Comparison baseline');st.markdown('**Moving average + optimiser**')
    if not months:st.info('Choose at least one reporting month.');st.stop()
    st.caption('Historical replay · Jan–Mar 2016 · Same product, fleet, initial stock and operating rules. Values below are simulated outcomes.')
    t=totals(daily,policy,months)
    cols=st.columns(4)
    cp,kp=t['carbon_pct'],t['cost_pct']
    with cols[0]:card('Transport emissions',f"{t['emissions']:,.1f} kg",f"Baseline: {t['baseline_emissions']:,.1f} kg CO₂")
    with cols[1]:card('CO₂ avoided' if t['carbon_saved']>=0 else 'Additional CO₂',f"{abs(t['carbon_saved']):,.1f} kg",'Zero baseline: percentage unavailable' if cp is None else f"{abs(cp):.1f}% {'reduction' if cp>=0 else 'increase'} vs baseline",'positive' if t['carbon_saved']>=0 else 'negative')
    with cols[2]:card('Operating cost saved' if t['cost_saved']>=0 else 'Additional operating cost',f"{abs(t['cost_saved']):,.2f} CU",'Zero baseline: percentage unavailable' if kp is None else f"{abs(kp):.1f}% {'reduction' if kp>=0 else 'increase'} vs baseline",'positive' if t['cost_saved']>=0 else 'negative')
    with cols[3]:card('Demand fulfilment',f"{t['fill_rate']:.1%}",f"Baseline: {t['baseline_fill_rate']:.1%} · Unmet: {t['unmet']:.0f} units",'positive' if t['qualified'] else 'negative')
    if t['qualified']:
        st.markdown(f'<div class="insight"><b>Service check passed for the selected period.</b> The plan serves at least 95% of observed demand and matches or exceeds the baseline. {t["routes"]} vehicle routes cover {t["distance"]:,.0f} km.</div>',unsafe_allow_html=True)
    else:st.warning('Service check not met. This plan is not recommended as a successful sustainability improvement: it falls below 95% fulfilment or below baseline service. Review monthly outcomes before adopting it.')
    if page=='Overview':
        l,r=st.columns(2)
        with l,st.container(border=True):
            st.subheader('Carbon emissions by month')
            st.caption('Lower bars mean less transport combustion CO₂.')
            st.plotly_chart(month_chart(monthly,policy,months,'emissions_kg','kg CO₂'),width='stretch')
        with r,st.container(border=True):
            st.subheader('Operating cost by month')
            st.caption('Transport and inventory holding costs, in scenario units.')
            st.plotly_chart(month_chart(monthly,policy,months,'cost','Cost units'),width='stretch')
        l,r=st.columns([1.5,1])
        with l,st.container(border=True):
            st.subheader('Cumulative carbon difference')
            st.caption('Above zero: CO₂ avoided. Below zero: additional CO₂.')
            pivot=daily[daily.month.isin(months)].pivot(index='date',columns='policy',values='emissions_kg')
            diff=(pivot.baseline-pivot[policy]).cumsum()
            fig=go.Figure(go.Scatter(x=diff.index,y=diff.values,fill='tozeroy',line=dict(color=GREEN,width=3),name='CO₂ avoided'))
            fig.add_hline(y=0,line_dash='dot',line_color='#8ba9bd')
            fig.update_yaxes(title='Cumulative kg CO₂ avoided')
            st.plotly_chart(chart_style(fig,300),width='stretch')
        with r,st.container(border=True):
            st.subheader('Model & operating context')
            st.write(f"**Selected ML:** {LABELS[summary['selected_ml']]}")
            st.write(f"**Best validation method overall:** {LABELS[summary['selected_overall']]}")
            st.write('**Horizon:** 3 days; replan daily')
            st.write('**Baseline:** trailing 28-day mean')
            st.write('**Safety stock:** common pre-period buffer')
            st.write(f"**Selected plan cost:** {t['cost']:,.2f} CU")
            st.caption('CU = cost units. Positive savings mean improvement; negative means an increase. No shortage penalty is included in cost.')
    st.subheader('Monthly scorecard')
    score=monthly[monthly.month.isin(months)&monthly.policy.eq(policy)][['month','carbon_saved_kg','carbon_reduction_pct','cost_saved','cost_reduction_pct','fill_rate','baseline_fill_rate','service_qualified']].copy()
    score.columns=['Month','CO₂ avoided (kg)','CO₂ reduction (%)','Cost saved (CU)','Cost reduction (%)','Fill rate','Baseline fill rate','Service check']
    st.dataframe(score.round(4),hide_index=True,width='stretch',column_config={
        'CO₂ avoided (kg)':st.column_config.NumberColumn(format='%.2f'),'CO₂ reduction (%)':st.column_config.NumberColumn(format='%.1f%%'),
        'Cost saved (CU)':st.column_config.NumberColumn(format='%.2f'),'Cost reduction (%)':st.column_config.NumberColumn(format='%.1f%%'),
        'Fill rate':st.column_config.NumberColumn(format='percent'),'Baseline fill rate':st.column_config.NumberColumn(format='percent')})
    if page=='Monthly savings':
        with st.container(border=True):
            st.subheader('The reduction picture')
            st.caption('Right of zero is an improvement; left of zero is an increase. Carbon and cost share the same percentage scale.')
            st.plotly_chart(reduction_chart(monthly,policy,months),width='stretch')
        st.subheader('Where the cost comes from')
        data=monthly[monthly.month.isin(months)&monthly.policy.isin(['baseline',policy])].copy()
        data['approach']=data.policy.map(POLICIES)
        long=data.melt(id_vars=['month','approach'],value_vars=['transport_cost','outlet_holding_cost','depot_holding_cost'],var_name='Component',value_name='Cost units')
        long['Component']=long['Component'].map({'transport_cost':'Transport','outlet_holding_cost':'Outlet holding','depot_holding_cost':'Depot holding'})
        fig=px.bar(long,x='month',y='Cost units',color='Component',facet_row='approach',color_discrete_sequence=[GREEN,'#80b7ff','#a999ec'])
        fig.for_each_annotation(lambda a:a.update(text=a.text.split('=')[-1]))
        chart_style(fig,540)
        fig.update_layout(legend=dict(y=1.1,title_text=''))
        st.plotly_chart(fig,width='stretch')
        st.subheader('Service and month-end inventory')
        st.dataframe(data[['month','approach','actual_units','served_units','unmet_units','routes','closing_outlet_stock','closing_depot_stock']].round(3),hide_index=True,width='stretch')
    l,r=st.columns(2)
    with l:download('Download monthly results',monthly[monthly.month.isin(months)],'monthly_sustainability_results.csv')
    with r:download('Download daily audit ledger',daily[daily.month.isin(months)],'daily_sustainability_ledger.csv')
    with st.expander('How savings are calculated'):
        st.latex(r'\text{Reduction (\%)}=100\times\frac{\text{Baseline}-\text{Candidate}}{\text{Baseline}}')
        st.write('Totals use summed cost/emissions, not an average of monthly percentages. A zero baseline gives an unavailable percentage. Months are full calendar months. Stock carries forward across days and months; it is not reset. Final stocks can differ and are reported. Service qualification requires ≥95% fill rate and no lower service than baseline.')
        st.caption(summary['test_window_note'])

elif page=='Model intelligence':
    if not ready:st.info('Model evaluation is running.');st.stop()
    c1,c2,c3=st.columns(3)
    with c1:card('Zero-sales observations',f'{history.eq(0).mean().mean():.1%}','Intermittent demand across five stores')
    with c2:card('Best overall validation method',LABELS[summary['selected_overall']],'Selected on validation RMSE')
    with c3:card('Selected ML model',LABELS[summary['selected_ml']],'Best of six ML configurations')
    st.subheader('Model comparison')
    rows=[]
    for model,metrics in summary['validation'].items():
        rows.append({'Method':LABELS[model],'Family':'ML' if model in ML_MODELS else 'Statistical',
            'Validation RMSE':metrics['rmse'],'Validation MAE':metrics['mae'],'Reporting RMSE':summary['test'][model]['rmse'],
            'Reporting MAE':summary['test'][model]['mae'],'Selected ML':model==summary['selected_ml'],'Overall winner':model==summary['selected_overall']})
    leaderboard=pd.DataFrame(rows).sort_values('Validation RMSE')
    with st.container(border=True):
        st.caption('VALIDATION LEADERBOARD · LOWER ERROR IS BETTER')
        st.plotly_chart(ranking_chart(leaderboard),width='stretch')
    st.dataframe(leaderboard.round(4),hide_index=True,width='stretch')
    st.caption(f"Selection: {summary['validation_start']} to {summary['validation_end']}. Calibration: {summary['calibration_start']} to {summary['calibration_end']}. Reporting: {summary['report_start']} to {summary['report_end']}. Reporting results do not reselect the winner.")
    l,r=st.columns(2)
    with l:outlet=st.selectbox('Outlet',history.columns)
    with r:model=st.selectbox('Forecast method',list(summary['validation']),index=list(summary['validation']).index(summary['selected_ml']),format_func=lambda m:LABELS[m])
    test=pd.read_csv(OUT/'forecast_test.csv',parse_dates=['date'])
    part=test[test.outlet.eq(outlet)&test.model.eq(model)].sort_values('date')
    fig=go.Figure()
    fig.add_scatter(x=part.date,y=part.actual,name='Observed sales',line=dict(color='#acbac3',width=2))
    fig.add_scatter(x=part.date,y=part.prediction,name='Rolling forecast',line=dict(color=GREEN,width=2))
    fig.update_yaxes(title='Product units / day')
    st.plotly_chart(chart_style(fig,380),width='stretch')
    download('Download model evaluation',leaderboard,'model_comparison.csv')
    with st.expander('Why these models, and why not just choose the lowest MAE?'):
        st.write('TSB and Croston–SBA handle intermittent positive-sales events. Poisson models predict nonnegative expected counts. Regularisation reduces flexibility on sparse data. RMSE evaluates conditional-mean forecasts; MAE alone can favour near-zero forecasts on mostly-zero series. Operational value is checked separately through fulfilment, inventory, cost and emissions.')

elif page=='Transformed data':
    path=ROOT/'outputs/transformed_demand.csv'
    if not path.exists():st.info('CSV export is being prepared.');st.stop()
    df=pd.read_csv(path)
    cols=st.columns(4)
    with cols[0]:card('Daily outlet records',f'{len(df):,}','One row per date and outlet')
    with cols[1]:card('Variables',str(len(df.columns)),'Sales, calendar, lags and model features')
    with cols[2]:card('Observed units',f'{df.observed_sales_units.sum():,.0f}','Reconciled to the source extract')
    with cols[3]:card('Historical coverage','1,913 days','29 Jan 2011 – 24 Apr 2016')
    st.write('')
    st.download_button('Download transformed dataset · CSV',path.read_bytes(),'transformed_demand.csv','text/csv',type='primary')
    a,b=st.columns(2)
    with a:outlets=st.multiselect('Outlets',sorted(df.outlet.unique()),default=sorted(df.outlet.unique()))
    with b:phases=st.multiselect('Period',list(df.phase.unique()),default=['evaluation'])
    view=df[df.outlet.isin(outlets)&df.phase.isin(phases)]
    all_cols=st.toggle('Show all 27 columns')
    columns=['date','outlet','observed_sales_units','day_of_week','lag_1','lag_7','past_7_day_mean','past_28_day_mean','phase','features_ready']
    st.dataframe(view if all_cols else view[columns],hide_index=True,width='stretch',height=440)
    st.caption(f'{len(view):,} rows in this view. Download includes all 9,565 rows. The first 28 days per store have unavailable lag features, left blank rather than fabricated.')
    with st.expander('Transformation and field definitions',expanded=True):
        st.markdown('1. Select fixed SKU `HOUSEHOLD_1_001` and five alphabetical store IDs.\n2. Unpivot the original daily columns and join the M5 date calendar.\n3. Preserve original sales and zeros without scaling.\n4. Build lag and rolling features from **strictly earlier days**.\n5. Add calendar fields, outlet indicators and chronological phase labels.')
        st.dataframe(pd.DataFrame([
            ['observed_sales_units','Original target sales; never a same-day predictor'],['lag_1 / 7 / 14 / 28','Sales on the indicated earlier date'],
            ['past_7_day_mean / past_28_day_mean','Mean ending on the previous day'],['past_28_day_std','Previous 28 days; population standard deviation'],
            ['past_28_day_nonzero_share','Fraction of preceding 28 days with positive sales'],['outlet_onehot_0 … 9','Fixed outlet encoding; last five unused here'],
            ['phase','Training / validation / calibration / evaluation / after_evaluation'],['features_ready','At least 28 earlier observations exist']],columns=['Field','Meaning']),hide_index=True,width='stretch')

elif page=='Delivery planner':
    left,right=st.columns([1,2])
    with left,st.container(border=True):
        st.subheader('Plan settings')
        source=st.selectbox('Scenario',['Forecast-driven M5','Benchmark + illustrative fleet','Original benchmark conventions'])
        default=summary['selected_ml'] if ready else 'random_forest'
        model=st.selectbox('Forecast model',list(MODELS),index=list(MODELS).index(default),format_func=lambda m:LABELS[m],disabled=source!='Forecast-driven M5')
        with st.expander('Operating assumptions'):
            hold=st.slider('Holding-cost multiplier',.1,5.,1.,.1)
            capacity=st.slider('Storage multiplier',.5,2.,1.,.1)
            pack=st.number_input('Pack size',min_value=0,value=1)
            moq=st.number_input('Minimum shipment',min_value=0,value=0)
        capped=st.checkbox('Limit planning-horizon emissions',disabled=source=='Original benchmark conventions')
        cap=st.number_input('Carbon cap (kg CO₂)',min_value=0.,value=20.,disabled=not capped)
        generate=st.button('Generate delivery plan',type='primary',width='stretch')
    try:
        if source=='Forecast-driven M5':
            pred=predict(history,model)
            buffer=pd.Series(summary['buffer']).reindex(history.columns) if ready else pd.Series(0.,index=history.columns)
            s=monthly_scenario(history,pred,buffer)
        else:s=load_benchmark() if source=='Original benchmark conventions' else illustrative_benchmark()
        for c in s.customers:c.holding*=hold;c.capacity*=capacity
        s.pack_size=float(pack);s.moq=float(moq)
        s.carbon_cap=float(cap) if capped and s.mode!='benchmark' else None
        s.provenance['dashboard_overrides']={'holding_multiplier':hold,'storage_multiplier':capacity,'pack_size':pack,'moq':moq,'carbon_cap':s.carbon_cap}
        s.validate()
    except ValueError as exc:st.error(str(exc));st.stop()
    if generate or 'planner_v2' not in st.session_state:
        with st.spinner('Solving and independently validating…'):p,r=plan_for(s)
        st.session_state.planner_v2=(s.fingerprint(),deepcopy(s),p,r)
    fingerprint,active,p,r=st.session_state.planner_v2
    with right:
        if fingerprint!=s.fingerprint():st.warning('Settings changed. Generate a new plan; displayed results use the prior settings.')
        if not r or not r['valid']:st.error(f'No validated plan: {p.status}. Adjust constraints and rerun.')
        else:
            st.success(f'Independently validated · {p.status} · {p.runtime:.2f}s · primary gap {p.gap:.4%}')
            a,b,c=st.columns(3)
            with a:card('Plan cost',f"{r['metrics']['total_cost']:.2f} CU",'Inventory + transportation')
            with b:card('Transport CO₂','Not calibrated' if r['metrics']['emissions_kg'] is None else f"{r['metrics']['emissions_kg']:.2f} kg",'Planning horizon')
            with c:card('Vehicle routes',str(r['metrics']['route_count']),'Return to depot included')
            day=st.selectbox('Route day',range(active.horizon),format_func=lambda d:f'Day {d+1}')
            st.plotly_chart(route_chart(active,p,day),width='stretch')
    if r and r['valid']:
        t1,t2,t3=st.tabs(['Delivery schedule','Vehicle routes','Assumptions & audit'])
        with t1:
            df=pd.DataFrame(r['inventory']);st.dataframe(df.round(3),hide_index=True,width='stretch')
            download('Download replenishment schedule',df,'replenishment_schedule.csv')
        with t2:st.dataframe(pd.DataFrame(r['routes']).round(3),hide_index=True,width='stretch')
        with t3:
            st.json(active.provenance)
            st.download_button('Download complete plan',json.dumps({'scenario':active.to_dict(),'plan':p.to_dict(),'evaluation':r},indent=2),'planning_run.json','application/json')
        st.caption('Illustrative coordinate network, not street routing. This forecast follows the historical endpoint in April 2016, not today. Planner settings do not alter the saved monthly experiment.')

elif page=='Research & algorithms':
    research,algorithms,outcomes=st.tabs(['Research foundation','Exact algorithms','Outcomes & boundaries'])
    with research:
        st.subheader('Sustainable operations research')
        st.markdown('''**Mundim, Santos & Morabito (2025)** — [Bi-objective green inventory routing](https://doi.org/10.1051/ro/2024162). Supports joint inventory/routing and emissions-constrained cost planning. Table 5 supplies the monthly replay's diesel factor **2.66 kg CO₂/L**. Our fixed-consumption model is simpler; paper savings are not copied into our outcomes.

**Benjaafar, Li & Daskin (2013)** — [Carbon Footprint and the Management of Supply Chains](https://doi.org/10.1109/TASE.2012.2203304). Supports linking carbon parameters to operational decisions and testing cost–emissions trade-offs. Their full collaboration and regulatory models are not implemented.

**Teunter, Syntetos & Babai (2011)** — [Intermittent demand: Linking forecasting to inventory obsolescence](https://doi.org/10.1016/j.ejor.2011.05.018). Basis for separate demand-size and occurrence-probability updates in TSB.

**Syntetos & Boylan (2005)** — [The accuracy of intermittent demand estimates](https://doi.org/10.1016/j.ijforecast.2004.10.001). Basis for the bias-adjusted Croston–SBA benchmark.
''')
        a,b=st.columns(2)
        with a,st.container(border=True):
            st.subheader('SDG 12 · Responsible consumption')
            st.write('Inventory, delivery consolidation and resource-use visibility. A research motivation, not a measurement of the UN material-footprint indicator.')
            st.link_button('Read UN Goal 12','https://sdgs.un.org/goals/goal12')
        with b,st.container(border=True):
            st.subheader('SDG 13 · Climate action')
            st.write('Transport CO₂ and the cost of reducing it enter operating decisions. No certification, carbon-credit or measured corporate-impact claim.')
            st.link_button('Read UN Goal 13','https://sdgs.un.org/goals/goal13')
    with algorithms:
        st.markdown((ROOT/'docs/ALGORITHMS.md').read_text())
    with outcomes:
        if ready:
            st.write(f"Validation-selected ML: **{LABELS[summary['selected_ml']]}**. Best overall: **{LABELS[summary['selected_overall']]}**.")
            st.dataframe(monthly[['month','policy','cost_reduction_pct','carbon_reduction_pct','fill_rate','service_qualified']].round(4),hide_index=True,width='stretch')
        st.write('One sparse SKU, five stores and an illustrative physical network. Observed sales may understate unconstrained demand. Reporting is retrospective and partially overlaps the earlier prototype evaluation. Inventory and fuel-consumption parameters are not calibrated company records.')
        st.write('Transport combustion CO₂ is not a full corporate CO₂-equivalent inventory. No warehouse electricity, refrigeration, upstream fuel, product embodied emissions or offsets are included. Cost excludes shortage penalties. Month-end stock differences remain visible.')
        st.markdown('[M5 organisers](https://github.com/Mcompetitions/M5-methods) · [Pyomo / HiGHS](https://pyomo.readthedocs.io/en/stable/api/pyomo.contrib.appsi.solvers.highs.Highs.html) · [Poisson boosting documentation](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)')

footer()

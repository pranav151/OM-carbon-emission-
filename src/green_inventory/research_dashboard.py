"""Dashboard for the hybrid research database and audited scenario benchmark."""
import hashlib
import json
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from .dashboard import card,chart_style,GREEN,BLUE
from .presentation import apply_theme
from .research_evaluation import ROOT,DB,OUT,POLICIES

PAGES={
 'Impact overview':('01','Less carbon.<br><span>Every saving, accounted for.</span>','Compare transport and refrigeration interventions against the same operating baseline. All outcomes are conditional simulation estimates.'),
 'Monthly outcomes':('02','Twelve months.<br><span>A clear view of the difference.</span>','Track absolute and percentage reductions by month. Each period uses its matching baseline.'),
 'Cold storage':('03','Move the cooling.<br><span>Keep temperatures in bounds.</span>','Inspect compressor schedules, electricity signals and zone temperatures. These are synthetic thermal-model outputs, not measured product temperatures.'),
 'Transport & logistics':('04','Every stop served.<br><span>Less fuel along the way.</span>','Inspect route sequences, truck loads and fuel components. The route search keeps the same trucks, customers and delivered quantities.'),
 'Inventory & service':('05','Protect the service.<br><span>Follow the stock.</span>','Inspect demand, replenishment, stock continuity and expiry. Inventory is identical across policies so it cannot manufacture savings.'),
 'Data & methods':('06','Know the evidence.<br><span>Trace every assumption.</span>','Explore the database, original research sources, exact algorithms and independent checks behind the comparison.')}

@st.cache_data(show_spinner=False)
def results(db_mtime,result_mtime):
    report=json.loads((OUT/'summary.json').read_text())
    if hashlib.sha256(DB.read_bytes()).hexdigest()!=report['database_sha256']:
        raise ValueError('The database changed. Rebuild the evaluation before reporting results.')
    if not all(report['checks'].values()):raise ValueError('Results failed their feasibility audit')
    return report,{n:pd.read_csv(OUT/(n+'.csv')) for n in ['daily_results','monthly_results','hourly_results','selected_routes','selected_stops','feasibility_audit']}

@st.cache_data(show_spinner=False)
def query(sql,mtime):
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:return pd.read_sql_query(sql,c)

def table(name):
    return query('SELECT * FROM "'+name.replace('"','""')+'"',DB.stat().st_mtime_ns)

def download(df,name,label='Download CSV'):
    st.download_button(label,df.to_csv(index=False),name+'.csv','text/csv',key='download_'+name)

def plot(fig,height=350):
    st.plotly_chart(chart_style(fig,height),width='stretch',config={'displaylogo':False})

def compare(data,metric,title):
    fig=go.Figure()
    for p in data.policy.unique():
        s=data[data.policy.eq(p)]
        fig.add_bar(x=s.month,y=s[metric],name=POLICIES[p],marker_color='#536d84' if p=='baseline' else GREEN)
    fig.update_layout(barmode='group',yaxis_title=title,bargap=.28)
    return fig

def total_metrics(daily,policy):
    totals=daily.groupby('policy').sum(numeric_only=True);b=totals.loc['baseline'];s=totals.loc[policy]
    return b,s,100*(b.total_kgco2e-s.total_kgco2e)/b.total_kgco2e,100*(b.operating_cost_cu-s.operating_cost_cu)/b.operating_cost_cu

def hero(page,carbon_pct):
    number,title,desc=PAGES[page]
    st.markdown(f'''<section class="hero research-hero"><div><div class="eyebrow">CARBON OPERATIONS / {number} / RESEARCH EDITION</div><h1>{title}</h1><p>{desc}</p><div class="hero-tags"><span class="pill">12 MONTH HISTORICAL SCENARIO</span><span class="pill">TRANSPORT + COLD STORAGE</span></div></div><div class="impact-orbit"><div class="impact-core"><span>MODELLED REDUCTION</span><strong>{carbon_pct:.2f}%</strong><small>selected policy & period · partial CO₂e</small></div><i></i><b></b></div></section>''',unsafe_allow_html=True)
    st.markdown('<div class="evidence-bar"><span>◉ HYBRID RESEARCH DATA</span>Real source records + synthetic operations · Perfect-information benchmark · CU = fictional cost units</div>',unsafe_allow_html=True)

def headline(b,s,carbon_pct,cost_pct):
    a,c,d,e=st.columns(4)
    with a:card('Carbon avoided · model estimate',f'{(b.total_kgco2e-s.total_kgco2e)/1000:,.2f} t',f'{carbon_pct:.2f}% reduction · baseline {b.total_kgco2e/1000:,.2f} t','positive')
    with c:card('Operating cost saved',f'{b.operating_cost_cu-s.operating_cost_cu:,.0f} CU',f'{cost_pct:.2f}% reduction · excludes implementation cost','positive')
    with d:card('Cold-storage carbon avoided',f'{(b.storage_kgco2-s.storage_kgco2)/1000:,.2f} t',f'{100*(b.storage_kgco2-s.storage_kgco2)/b.storage_kgco2:.2f}% of storage CO₂','positive')
    with e:card('Service & constraints','Checks passed','Same delivered mass · temperature bounds met','positive')

def overview(daily,monthly,policy):
    b,s,cp,kp=total_metrics(daily,policy);headline(b,s,cp,kp)
    left,right=st.columns([1.5,1])
    with left,st.container(border=True):
        st.subheader('Carbon across the year')
        plot(compare(monthly[monthly.policy.isin(['baseline',policy])],'total_kgco2e','Modelled kg CO₂e · partial scope'),360)
    with right,st.container(border=True):
        st.subheader('Where the avoided carbon comes from')
        fig=go.Figure(go.Waterfall(x=['Baseline','Truck routes','Cold storage','Selected plan'],y=[b.total_kgco2e/1000,(s.transport_kgco2-b.transport_kgco2)/1000,(s.storage_kgco2-b.storage_kgco2)/1000,0],measure=['absolute','relative','relative','total'],decreasing={'marker':{'color':GREEN}},totals={'marker':{'color':BLUE}},connector={'line':{'color':'#477080'}}))
        fig.update_layout(yaxis_title='Tonnes CO₂e',showlegend=False);plot(fig,360)
        st.caption('Inbound transport and refrigerant leakage are included in totals and unchanged between policies.')
    left,right=st.columns([1.5,1])
    with left,st.container(border=True):
        st.subheader('Cumulative avoided carbon')
        q=daily[daily.policy.eq(policy)].sort_values('date');fig=go.Figure(go.Scatter(x=q.date,y=q.carbon_saved_kg.cumsum()/1000,fill='tozeroy',line={'color':GREEN,'width':3},name='Avoided CO₂e'))
        fig.update_layout(yaxis_title='Tonnes CO₂e avoided');plot(fig,300)
    with right,st.container(border=True):
        st.subheader('The operating trade-off')
        st.metric('Truck distance saved',f'{b.distance_km-s.distance_km:,.0f} km')
        st.metric('Electricity change',f'{s.energy_kwh-b.energy_kwh:+,.0f} kWh')
        st.caption('Moving electricity use to lower-carbon hours can reduce emissions without reducing kWh. Energy and emissions are reported separately.')
        st.metric('Modelled contribution increase',f'{s.contribution_cu-b.contribution_cu:,.0f} CU')
        st.caption('Sales and COGS are fixed. This equals operating savings; it is not net company profit.')
    st.subheader('Compare the interventions');rows=[]
    for p in POLICIES:
        _,v,pc,pk=total_metrics(daily,p)
        rows.append({'Intervention':POLICIES[p],'Carbon (t CO₂e)':v.total_kgco2e/1000,'Reduction (%)':pc,'Operating cost (CU)':v.operating_cost_cu,'Cost reduction (%)':pk})
    st.dataframe(pd.DataFrame(rows).round(3),hide_index=True,width='stretch')

def monthly_page(daily,monthly,policy):
    b,s,cp,kp=total_metrics(daily,policy);headline(b,s,cp,kp)
    pair=monthly[monthly.policy.isin(['baseline',policy])];l,r=st.columns(2)
    with l,st.container(border=True):st.subheader('Monthly carbon');plot(compare(pair,'total_kgco2e','kg CO₂e'))
    with r,st.container(border=True):st.subheader('Monthly operating cost');plot(compare(pair,'operating_cost_cu','CU'))
    selected=monthly[monthly.policy.eq(policy)];st.subheader('Reduction percentages')
    long=selected.melt(id_vars='month',value_vars=['carbon_reduction_pct','cost_reduction_pct'],var_name='Measure',value_name='Reduction (%)')
    long.Measure=long.Measure.map({'carbon_reduction_pct':'Carbon','cost_reduction_pct':'Operating cost'})
    plot(px.bar(long,x='month',y='Reduction (%)',color='Measure',barmode='group',color_discrete_sequence=[GREEN,BLUE]),300)
    st.subheader('Monthly scorecard')
    cols=['month','total_kgco2e','baseline_total_kgco2e','carbon_saved_kg','carbon_reduction_pct','operating_cost_cu','cost_saved_cu','cost_reduction_pct','energy_kwh']
    st.dataframe(selected[cols].round(3),hide_index=True,width='stretch')
    download(monthly,'monthly_comparison','Download all four policies for selected months');download(daily,'daily_comparison','Download the daily audit ledger')
    st.caption('Reduction = 100 × (baseline − candidate) / baseline. Annual percentages are recalculated from totals, never averaged.')

def cooling_page(hourly,daily,policy):
    b,s,cp,kp=total_metrics(daily,policy);a,c,d=st.columns(3)
    a.metric('Storage CO₂ reduction',f'{100*(b.storage_kgco2-s.storage_kgco2)/b.storage_kgco2:.2f}%')
    c.metric('Electricity cost saved',f'{b.electricity_cost_cu-s.electricity_cost_cu:,.2f} CU');d.metric('Temperature violations','0','Within synthetic zone bounds',delta_color='off')
    l,r=st.columns(2);day=l.selectbox('Inspect a day',sorted(hourly.date.unique()),key='cool_day');zone=r.selectbox('Temperature zone',['chilled','frozen'])
    part=hourly[hourly.date.eq(day)&hourly.zone_id.eq(zone)&hourly.policy.isin(['baseline',policy])].copy();l,r=st.columns(2)
    with l,st.container(border=True):
        st.subheader('Compressor power');plot(px.line(part,x='hour',y='power_kw',color='policy',labels={'power_kw':'Compressor kW','hour':'Hour'}))
    with r,st.container(border=True):
        st.subheader('Temperature trajectory');fig=px.line(part,x='hour',y='temperature_end_c',color='policy',labels={'temperature_end_c':'End-of-hour temperature (°C)'})
        z=table('cold_zones').set_index('zone_id').loc[zone]
        fig.add_hrect(y0=z.temperature_min_c,y1=z.temperature_max_c,fillcolor='#62edc6',opacity=.08,line_width=0)
        fig.add_hline(y=z.temperature_min_c,line_dash='dot');fig.add_hline(y=z.temperature_max_c,line_dash='dot')
        fig.update_yaxes(range=[z.temperature_min_c-1,z.temperature_max_c+1]);plot(fig)
        st.caption('Each day starts and ends at the baseline target. This is an assumed zone state, not measured food-core temperature.')
    st.subheader('Signals used by the optimiser');sig=part[part.policy.eq(policy)].sort_values('hour');l,r=st.columns(2)
    with l:plot(px.line(sig,x='hour',y='grid_kgco2_per_kwh',labels={'grid_kgco2_per_kwh':'Synthetic kg CO₂/kWh'}),250)
    with r:plot(px.line(sig,x='hour',y='electricity_cu_per_kwh',labels={'electricity_cu_per_kwh':'Synthetic CU/kWh'}),250)
    st.subheader('Heat entering the room')
    heat=sig.melt(id_vars='hour',value_vars=['background_heat_kwh_th','product_heat_kwh_th','door_heat_kwh_th','auxiliary_energy_kwh'],var_name='Heat source',value_name='kWh thermal')
    plot(px.bar(heat,x='hour',y='kWh thermal',color='Heat source'),300)
    with st.expander('Inspect the complete selected-day records'):st.dataframe(part.round(4),hide_index=True,width='stretch')
    download(part,'cold_storage_day','Download this day, both policies')

def transport_page(data,daily,policy,months):
    b,s,_,_=total_metrics(daily,policy);a,c,d=st.columns(3)
    a.metric('Transport CO₂ reduction',f'{100*(b.transport_kgco2-s.transport_kgco2)/b.transport_kgco2:.2f}%');c.metric('Diesel avoided',f'{b.fuel_litres-s.fuel_litres:,.0f} L');d.metric('Truck kilometres avoided',f'{b.distance_km-s.distance_km:,.0f} km')
    routes=data['selected_routes'];routes=routes[routes.date.str[:7].isin(months)];l,r=st.columns(2)
    day=l.selectbox('Delivery day',sorted(routes.date.unique()));one=routes[routes.date.eq(day)];truck=r.selectbox('Truck',one.vehicle_id.tolist())
    row=one[one.vehicle_id.eq(truck)].iloc[0];nodes=table('logistics_nodes');nodes=nodes[nodes.case_id.eq(row.case_id)].set_index('node_id')
    fig=go.Figure();use_selected=policy in ('transport','combined')
    for label,col,color in [('Baseline','original_order','#7c92a6'),('Selected plan','selected_order' if use_selected else 'original_order',GREEN)]:
        seq=[0]+json.loads(row[col])+[0];loc=nodes.loc[seq]
        fig.add_scatter(x=loc.longitude,y=loc.latitude,mode='lines+markers',name=label,line={'color':color,'width':2},text=loc.city)
    fig.add_scatter(x=[nodes.loc[0,'longitude']],y=[nodes.loc[0,'latitude']],mode='markers',name='Depot',marker={'size':17,'symbol':'diamond','color':'#ffc594'})
    fig.update_layout(xaxis_title='Longitude',yaxis_title='Latitude');fig.update_yaxes(scaleanchor='x',scaleratio=1);plot(fig,440)
    st.caption('Schematic stop connections; routing uses provider road-distance matrices. Baseline order is reconstructed from source rows. California routing is hypothetically connected to a Finnish load profile.')
    base=table('baseline_trips');br=base[base.trip_id.eq(row.trip_id)].iloc[0];selected=row if use_selected else br
    comparison=pd.DataFrame([{'Plan':label,**{k:rec[k] for k in ['distance_km','total_litres','return_h','peak_load_kg','transport_kgco2','transport_cost_cu']}} for label,rec in [('Baseline',br),('Selected',selected)]])
    st.dataframe(comparison.round(3),hide_index=True,width='stretch')
    stops=data['selected_stops'] if use_selected else table('baseline_stops');shown=stops[stops.trip_id.eq(row.trip_id)]
    st.subheader('Stop sequence and load');st.dataframe(shown.round(3),hide_index=True,width='stretch')
    download(routes,'route_candidates','Download optimised route candidates for selected months')

def inventory_page(months):
    inv=table('inventory_daily');inv=inv[inv.date.str[:7].isin(months)];p=st.selectbox('Product',inv.product_id.unique());sub=inv[inv.product_id.eq(p)].copy();a,b,c=st.columns(3)
    a.metric('Fulfilment',f'{100*inv.shipped_kg.sum()/inv.demand_kg.sum():.2f}%');b.metric('Spoilage',f'{inv.spoilage_kg.sum():,.1f} kg');c.metric('Emergency receipts',f'{inv.emergency_receipts_kg.sum():,.1f} kg')
    fig=go.Figure();fig.add_scatter(x=sub.date,y=sub.closing_kg,name='Closing inventory',fill='tozeroy',line={'color':GREEN});fig.add_scatter(x=sub.date,y=sub.demand_kg,name='Daily demand',line={'color':BLUE});fig.update_layout(yaxis_title='kg');plot(fig,380)
    st.info('Inventory and replenishment are identical across the four comparisons. Their costs and inbound emissions are included. No inventory or spoilage savings are claimed.')
    st.subheader('Product-day balance');st.dataframe(sub[['date','opening_kg','receipts_kg','demand_kg','shipped_kg','spoilage_kg','closing_kg','regular_order_placed_kg']].round(3),hide_index=True,width='stretch');download(inv,'inventory_ledger','Download inventory ledger for selected months')
    with st.expander('How the inventory baseline works'):st.write('Periodic review targets three days of trailing demand, with a two-day supplier lead time. First-expiry-first-out allocation uses generated product shelf lives. Stock carries across months. Supplier loads drive inbound transport and product cooling heat. These are synthetic records.')

def data_page(report):
    tabs=st.tabs(['Dataset explorer','Real vs synthetic','Algorithms & checks','Download study'])
    with tabs[0]:
        cat=table('table_catalog');names=cat.table_name.tolist();name=st.selectbox('Database table',names,index=names.index('hourly_inputs'));frame=table(name);a,b=st.columns(2);a.metric('Rows in complete table',f'{len(frame):,}');b.metric('Columns',len(frame.columns))
        page=st.number_input('Preview page (500 rows)',min_value=1,max_value=max(1,(len(frame)+499)//500),value=1,step=1)
        st.dataframe(frame.iloc[(page-1)*500:page*500],hide_index=True,width='stretch');st.caption('Preview is paginated. The download contains every row in the selected table.');download(frame,'database_'+name,'Download complete table CSV')
        with st.expander('Field dictionary for this table'):
            fields=table('field_dictionary');st.dataframe(fields[fields.table_name.eq(name)],hide_index=True,width='stretch')
    with tabs[1]:
        a,b,c=st.columns(3);a.metric('ORNL original rows','838,909');b.metric('VTT rows across 4 files','73,702');c.metric('Source load hours available','91.20%')
        st.warning('91.20% applies only to availability of the replayed electricity channel. The combined supply chain is synthetic. It is not 91.20% real company data.')
        st.write('Original measurements are preserved. Synthetic additions include orders, inventory, fuel response, thermal capacity, temperatures, weather, prices and grid-carbon signals. Sources represent unrelated sites and dates.')
        st.write('VTT power units are not explicit in downloaded headers. The scenario assumes one source unit equals one kW, then scales the profile by four. Fingrid data were not downloaded; grid intensity is synthetic.')
        st.dataframe(table('sources'),hide_index=True,width='stretch')
        for label,url in [('VTT electricity records','https://data.mendeley.com/datasets/myyf72mpw9/1'),('ORNL refrigeration experiments','https://doi.org/10.6084/m9.figshare.13232627'),('UC Riverside delivery cases','https://zenodo.org/records/8117782'),('MultiPACK field data','https://doi.org/10.18710/T5OHPR')]:st.link_button(label,url)
        with st.expander('Precisely scoped composition audit'):
            v=json.loads((ROOT/'outputs/research_database/validation_report.json').read_text());st.json(v['composition']);st.json(v['profile_methods'])
    with tabs[2]:
        st.subheader('Exact implemented algorithms')
        for text in report['algorithms']:st.write('• '+text)
        st.write('Route search runs first, then return times update door heat, then daily cooling LPs are solved. This is a staged comparison, not a globally optimal joint inventory-routing model.')
        st.info('The optimiser knows each day’s loads, tariffs and carbon. No ML forecast feeds these results. They are conditional benchmark potential, not guaranteed real-world savings.')
        st.write(report['fixed_factors']);st.write(report['scope'])
        st.dataframe(pd.DataFrame([{'Check':k.replace('_',' '),'Passed':v} for k,v in report['checks'].items()]),hide_index=True,width='stretch');st.dataframe(pd.read_csv(OUT/'feasibility_audit.csv'),hide_index=True,width='stretch')
        with st.expander('Factors prepared for future optimisation'):
            st.dataframe(table('optimization_factors'),hide_index=True,width='stretch');st.caption('The catalog describes prepared inputs. This dashboard currently optimises routing and compressor schedules only.')
        with st.expander('Equations and complete methodology'):st.markdown((ROOT/'docs/RESEARCH_DASHBOARD.md').read_text())
    with tabs[3]:
        st.download_button('Download research database (SQLite)',DB.read_bytes(),DB.name,'application/vnd.sqlite3')
        st.download_button('Download evaluation report',(OUT/'summary.json').read_bytes(),'evaluation_summary.json','application/json')
        st.download_button('Download active assumptions',(ROOT/'outputs/research_database/scenario_config.json').read_bytes(),'scenario_config.json','application/json')
        for file in ['daily_results.csv','monthly_results.csv','hourly_results.csv','selected_routes.csv']:st.download_button('Download '+file.replace('_',' '),(OUT/file).read_bytes(),file,'text/csv',key='full_'+file)

def render():
    st.set_page_config(page_title='Carbon Operations | Sustainable Inventory',page_icon='🌿',layout='wide',initial_sidebar_state='expanded')
    apply_theme();st.markdown('<style>'+(ROOT/'assets/research_dashboard.css').read_text()+'</style>',unsafe_allow_html=True)
    if not (OUT/'summary.json').exists():st.info('The audited evaluation is being prepared. Results appear when all checks pass.');st.stop()
    try:report,data=results(DB.stat().st_mtime_ns,(OUT/'summary.json').stat().st_mtime_ns)
    except ValueError as exc:st.error(str(exc));st.stop()
    with st.sidebar:
        st.markdown('<div class="brand"><div class="brand-icon">◈</div><div><div class="brand-name">Carbon Operations</div><div class="brand-sub">SUSTAINABLE INVENTORY</div></div></div><div class="side-label">RESEARCH WORKSPACE</div>',unsafe_allow_html=True)
        page=st.radio('Workspace',list(PAGES),label_visibility='collapsed')
        st.markdown('<div class="side-label" style="margin-top:24px">COMPARE AN INTERVENTION</div>',unsafe_allow_html=True)
        policy=st.selectbox('Intervention',list(POLICIES),index=3,format_func=lambda p:POLICIES[p])
        allmonths=sorted(data['monthly_results'].month.unique());months=st.multiselect('Reporting months',allmonths,default=allmonths)
        st.markdown('<div class="side-note"><strong><span class="status-dot"></span>Audited simulation</strong><p>Jun 2017 — May 2018<br>365 scenario days · 2 cold zones<br>Real sources + explicit assumptions</p></div>',unsafe_allow_html=True)
        st.caption('Historical scenario. Not live company performance. Version: virtual_cold_chain_v1.')
    if not months:st.info('Select at least one reporting month.');st.stop()
    daily=data['daily_results'];daily=daily[daily.month.isin(months)];monthly=data['monthly_results'];monthly=monthly[monthly.month.isin(months)]
    _,_,pct,_=total_metrics(daily,policy);hero(page,pct)
    if page=='Impact overview':overview(daily,monthly,policy)
    elif page=='Monthly outcomes':monthly_page(daily,monthly,policy)
    elif page=='Cold storage':
        h=data['hourly_results'];cooling_page(h[h.date.str[:7].isin(months)],daily,policy)
    elif page=='Transport & logistics':transport_page(data,daily,policy,months)
    elif page=='Inventory & service':inventory_page(months)
    else:data_page(report)
    st.markdown('<div class="footer-note"><span>CARBON OPERATIONS · REPRODUCIBLE RESEARCH</span><span>Conditional estimates · Partial emissions scope · No measured deployment savings</span></div>',unsafe_allow_html=True)

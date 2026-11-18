"""Build an auditable SQLite research database and CSV exports, not a dashboard.

Raw observations are never joined across unrelated sites. A separate seeded
virtual scenario replays source patterns and adds declared synthetic variables.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import json
import sqlite3
import sys
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from green_inventory.cold_chain import load_cold_measurements, load_freight

BASE = ROOT / 'data/research/combined_sources'
OUT = ROOT / 'outputs/research_database'
RAW = ROOT / 'data/research'
CONFIG = ROOT / 'configs/research_database.json'
LB_TO_KG = 0.45359237
DIESEL_CO2_KG_PER_L = 10.21 / 3.785411784


def hashfile(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(1024 * 1024):
            h.update(b)
    return h.hexdigest()


def validate_config(c):
    if pd.Timestamp(c['end_date']) < pd.Timestamp(c['start_date']):
        raise ValueError('end_date must follow start_date')
    for k, v in c.items():
        if isinstance(v, (int, float)) and (not np.isfinite(v) or v < 0):
            raise ValueError(f'Invalid nonnegative parameter {k}')
    for k in ('source_profile_scale','vtt_source_unit_to_kw_assumption','truck_capacity_kg','warehouse_capacity_kg'):
        if c[k] <= 0:
            raise ValueError(f'{k} must be positive')
    if not isinstance(c['supplier_lead_days'], int) or c['supplier_lead_days'] < 1:
        raise ValueError('supplier_lead_days must be a positive integer')
    if c['annual_refrigerant_leak_fraction'] > 1:
        raise ValueError('Invalid leak fraction')


class Database:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.catalog = []
        self.fields = []

    def write(self, name, frame, grain, provenance, units=None, descriptions=None, keys=None, refs=None):
        """Write tables with actual key/FK constraints and per-column provenance."""
        units, descriptions, keys, refs = units or {}, descriptions or {}, keys or [], refs or {}
        kinds = provenance if isinstance(provenance, dict) else {c: provenance for c in frame}
        definitions = []
        for col in frame:
            t = 'INTEGER' if pd.api.types.is_integer_dtype(frame[col]) else 'REAL' if pd.api.types.is_numeric_dtype(frame[col]) else 'TEXT'
            definitions.append(f'"{col}" {t}' + (' NOT NULL' if col in keys else ''))
            self.fields.append(dict(table_name=name, column_name=col, sql_type=t,
                unit=units.get(col, infer_unit(col)), provenance=kinds.get(col, 'derived'),
                description=descriptions.get(col, col.replace('_',' ')),
                nonnull_cells=int(frame[col].notna().sum())))
        if keys:
            definitions.append('PRIMARY KEY (' + ','.join(f'"{k}"' for k in keys) + ')')
        for col, (target, target_col) in refs.items():
            definitions.append(f'FOREIGN KEY("{col}") REFERENCES "{target}"("{target_col}")')
        self.connection.execute(f'CREATE TABLE "{name}" ({",".join(definitions)})')
        frame.to_sql(name, self.connection, if_exists='append', index=False, chunksize=2000)
        frame.to_csv(OUT / 'csv' / f'{name}.csv', index=False)
        self.catalog.append(dict(table_name=name, rows=len(frame), columns=len(frame.columns),grain=grain,
            provenance='mixed; see field_dictionary' if isinstance(provenance,dict) else provenance,
            csv_file=f'csv/{name}.csv'))


def infer_unit(col):
    exact={'cop':'kWh thermal/kWh electric','profile_fraction':'fraction','demand_share':'fraction',
           'source_power_value':'original source power unit; not verified kW',
           'profile_value_used':'original source power unit; may be imputed',
           'source_row':'one-based physical source row','source_row_first':'first source row in minute',
           'source_row_last':'last source row in minute','samples':'sample count',
           'thermal_capacity_kwh_per_c':'kWh thermal/degC',
           'operational_kgco2e_partial_scope':'kg CO2e; electricity/fuel CO2 and R744 only',
           'expanded_kgco2e_with_spoilage':'kg CO2e; partial operational plus assumed spoiled-product footprint',
           'capacity_feasible':'boolean 0/1','time_feasible':'boolean 0/1','power_feasible':'boolean 0/1'}
    if col in exact:return exact[col]
    for end,unit in [('_cu_per_kwh','CU/kWh'),('_cu_per_litre','CU/L'),('_cu_per_kg','CU/kg'),
                     ('_kgco2_per_kwh','kg CO2/kWh'),('_l_per_km','L/km'),('_l_per_h','L/h'),
                     ('_kj_kg_k','kJ/(kg K)'),('_days','days'),('_minutes','minutes')]:
        if col.endswith(end):return unit
    for end, unit in [('_kgco2e','kg CO2e (specified scope)'),('_kgco2','kg CO2'),('_kwh_th','kWh thermal'),
                      ('_kwh','kWh electric'),('_kw','kW'),('_kg','kg'),('_litres','L'),('_cu','CU'),
                      ('_km','km'),('_h','h'),('_c','degC')]:
        if col.endswith(end): return unit
    return 'see description/source'


def decision_catalog(db):
    rows=[
        ['route_sequence','Vehicle routing with backhauls; MILP or ALNS','logistics_nodes; logistics_edges; baseline_stops','Stop sequence, truck assignment','All stops served once; load evolves at pickups/deliveries; truck capacity and working window','Provider road matrix; reconstructed baseline order; synthetic fleet/fuel response'],
        ['dispatch_time','Appointment and dock scheduling','baseline_trips; baseline_stops; cold_storage_hourly','Departure and loading times','Do not violate customer windows or dispatch-before-receipt; include refrigeration runtime','Broad synthetic windows; dock congestion capacity not measured'],
        ['replenishment','Periodic review order-up-to policy; inventory-routing optimisation','orders; receipts; inventory_daily; suppliers; inbound_transport','Order quantity, order date, shipment consolidation','Lead time, capacity, demand fulfilment, supplier truck capacities, terminal stock','Demand, product allocation, initial stocks and supplier records synthetic'],
        ['perishable_inventory','FEFO and age-indexed inventory balance','products; inventory_batches; inventory_daily','Batch allocation, replenishment timing','Respect expiry, no negative inventory; preserve service and terminal stock','Shelf life assumptions; microbial spoilage kinetics not modelled'],
        ['cooling_schedule','Thermal-balance model predictive control; linear/MILP dispatch','hourly_inputs; cold_zones; cold_storage_hourly; optimization_hourly','Compressor power, temperature trajectory','Temperature bounds, compressor capacity, thermal balance, initial and terminal temperature','Synthetic thermal model; no validated plant or product core temperatures'],
        ['energy_tariff_and_carbon','Constrained multi-objective scheduling','hourly_inputs; reference_factors; baseline_daily','Choose feasible operating periods','Minimise partial-scope emissions subject to cost <= baseline; report Pareto alternatives','Grid and tariff curves synthetic; price-carbon relationship deliberately different'],
        ['defrost_lighting_fans','Preventive maintenance and equipment scheduling','cold_zones; cold_storage_hourly','Defrost timing and permissible auxiliary schedules','Keep required defrost energy/count; enforce realistic equipment constraints before control tests','Synthetic auxiliary energy and heat; equipment rules not validated'],
        ['fault_detection','Condition-based maintenance; experiment-grouped ML evaluation','ornl_minute_measurements; source_coverage','Fault alert or maintenance recommendation','Keep each physical experiment in one data partition; align operating conditions','Six real fault experiments; phase/severity labels are not automatically assigned to every row'],
        ['refrigerant_leakage','Maintenance and refrigerant accounting','scenario_parameters; baseline_daily','Leak-prevention scenario or refrigerant alternative','Do not infer leak rate from electricity alone','Charge/leak rate synthetic; R744 GWP convention 1; no measured leak logs'],
        ['demand_and_load_forecasting','Seasonal naive versus tree models; chronological evaluation','vtt_power_observations; hourly_inputs; orders','Forecast demand and cooling load','Past-only features; hold out future months; report scenario demand as synthetic','No ML selected/trained by this database build; avoid claiming best model prematurely'],
    ]
    d=pd.DataFrame(rows,columns=['factor_id','om_concept_or_candidate_algorithm','input_tables','decision_variables','required_constraints','evidence_limit'])
    d['implementation_status']='data prepared; optimizer/ML not implemented in this database build'
    db.write('optimization_factors',d,'one optimisation factor','metadata',keys=['factor_id'])
    constraints=pd.DataFrame([
        ['emissions_objective','Minimise operational_kgco2e_partial_scope; show spoilage-extended footprint separately'],
        ['cost_cap','Optimised operating cost <= matched baseline; include inbound freight, emergency fees and maintenance cost when relevant'],
        ['service','Same orders and at least baseline fulfilment; report on-time delivery, shortages and temperature violations'],
        ['terminal_stock','Final usable inventory by product >= matched baseline; account for initial stock and pending replenishment'],
        ['terminal_temperature','Final zone temperatures <= baseline target; prevent credit for leaving the store warmer'],
        ['thermal_balance','T_next=T+(Q_heat-COP*P*delta_t)/C; include door, receipt and auxiliary heat consistently'],
        ['decision_dependent_heat','Recompute door heat and product cooling when dispatch/receipt quantities or times change'],
        ['forecast_information','Future realised demand/grid not available to controller; perfect-information run is an upper-bound benchmark only'],
        ['accounting_boundary','Diesel combustion CO2 + electricity CO2 + R744 leakage CO2e; excludes upstream fuel, CH4/N2O, capital equipment and unmodelled product footprint'],
        ['claims','Savings from this scenario are estimated; no real deployment, live company connection or measured reduction exists'],
    ],columns=['constraint_id','requirement'])
    db.write('planning_constraints',constraints,'one evaluation requirement','metadata',keys=['constraint_id'])


def source_tables(db):
    sources = pd.DataFrame([
        ['vtt','VTT Finnish grocery-store power','https://doi.org/10.17632/myyf72mpw9.1','CC BY-NC 3.0','real field measurements','Historical, not live; source power unit/timezone not declared in CSV headers.'],
        ['ornl','ORNL refrigeration baseline and fault experiments','https://doi.org/10.6084/m9.figshare.13232627','CC BY 4.0','real laboratory measurements','Separate experimental tests; fault files include operating phases, not every row necessarily active fault.'],
        ['multipack','MultiPACK integrated refrigeration','https://doi.org/10.18710/T5OHPR','CC0','real field measurements','Six sampled site-days; CO2 is refrigerant; integrated system includes HVAC.'],
        ['ncst','UC Riverside truck dispatch cases v1','https://zenodo.org/records/8117782','See original repository terms','research cases from real operations','Four daily instances; road matrices calculated by provider. Not confirmed refrigerated freight.'],
        ['epa_hub','EPA emission factors hub 2025','https://www.epa.gov/climateleadership/ghg-emission-factors-hub','US government reference','published reference','Diesel 10.21 kg CO2 per US gallon; excludes CH4/N2O and fuel upstream emissions in this scenario.'],
        ['epa_smartway','EPA SmartWay carrier data year 2022','https://www.epa.gov/smartway/smartway-carrier-performance-ranking','US government reference','published reference','Archived carrier bands; included for benchmarking, not assigned to unrelated trucks.'],
        ['fingrid','Fingrid electricity consumption carbon intensity','https://data.fingrid.fi/en/datasets/265','CC BY','not downloaded','Endpoint returned HTTP 401; no real grid-intensity time series included.'],
        ['scenario','Virtual combined cold chain v1','configs/research_database.json','Project synthetic scenario','synthetic scenario','Unrelated sources are explicitly replayed, never claimed as one company.'],
    ],columns=['source_id','title','url','license','evidence_type','limitation'])
    db.write('sources',sources,'one source','metadata',keys=['source_id'])
    files = []
    folders = [('vtt',BASE/'vtt'),('ornl',BASE/'ornl'),('multipack',RAW/'cold_storage/multipack'),('ncst',RAW/'carbon_inventory/ncst_2023_v1')]
    for sid, folder in folders:
        for p in sorted(folder.iterdir()):
            if p.suffix not in ('.csv','.txt','.py','.md'): continue
            files.append(dict(file_id=f'{sid}/{p.name}',source_id=sid,path=str(p.relative_to(ROOT)),
                              bytes=p.stat().st_size,sha256=hashfile(p),transformation='original bytes retained'))
    for sid, name in [('epa_hub','ghg-emission-factors-hub-2025.xlsx'),('epa_smartway','carrierperfdataepa_dy2022.xlsx')]:
        p=RAW/'carbon_inventory/epa'/name
        files.append(dict(file_id=f'{sid}/{name}',source_id=sid,path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,
                          sha256=hashfile(p),transformation='original workbook; full sheets retained'))
    db.write('source_files',pd.DataFrame(files),'one original file','metadata',keys=['file_id'],refs={'source_id':('sources','source_id')})
    factors = pd.DataFrame([
        dict(factor_id='epa_diesel_co2',source_id='epa_hub',value=10.21,unit='kg CO2/US gallon',scope='combustion CO2 only',locator='2025 Hub, Table 2 Mobile Combustion, Diesel Fuel'),
        dict(factor_id='diesel_co2_per_l',source_id='epa_hub',value=DIESEL_CO2_KG_PER_L,unit='kg CO2/L',scope='10.21 / 3.785411784; no upstream/CH4/N2O',locator='unit conversion'),
    ])
    db.write('reference_factors',factors,'one factor','published_reference',keys=['factor_id'],refs={'source_id':('sources','source_id')})
    return files


def import_real_data(db):
    vtt=[];summary=[]
    for path in sorted((BASE/'vtt').glob('*.csv')):
        d=pd.read_csv(path); store=int(path.stem.split('_')[1]); minutes=int(path.stem.split('_')[2])
        d.insert(0,'record_id',[f'vtt/{path.name}:{i}' for i in range(2,len(d)+2)])
        d.insert(1,'file_id',f'vtt/{path.name}');d.insert(2,'source_row',np.arange(2,len(d)+2))
        d.insert(3,'store_id',store);d.insert(4,'interval_minutes',minutes)
        d['quality_flag']=np.where(d.iloc[:,6:].isna().any(axis=1),'source_has_missing','observed')
        vtt.append(d)
        summary.append(dict(source_id='vtt',file=path.name,records=len(d),start=d.Time.min(),end=d.Time.max(),
                            note='Original numeric units; overlapping hourly/15min versions must not be summed'))
    vtt=pd.concat(vtt,ignore_index=True)
    vp={c:'measured_field' for c in vtt};vp.update({c:'metadata' for c in ['record_id','file_id','source_row','store_id','interval_minutes','quality_flag']})
    db.write('vtt_power_observations',vtt,'source file × timestamp; alternatives at 15/60min',vp,
             units={c:'source power unit not explicitly declared' for c in ['refrigeration','machines','freezers','refrigerators','total','hvac','sub1','sub2','store1','store2','cellar','fuel_station']},
             keys=['record_id'],refs={'file_id':('source_files','file_id')})
    cold=load_cold_measurements();cold.insert(0,'record_id',cold.source_file+':'+cold.source_row.astype(str))
    cold['file_id']='multipack/'+cold.source_file
    cp={c:'derived_from_measurements' for c in cold};cp.update({c:'metadata' for c in ['record_id','file_id','source_file','source_row','quality_flag','provenance','source_doi','site','lt_power_unit_source']})
    db.write('multipack_measurements',cold,'original source row, selected standardized fields',cp,keys=['record_id'],refs={'file_id':('source_files','file_id')})
    for name,g in cold.groupby('source_file'):
        summary.append(dict(source_id='multipack',file=name,records=len(g),start=str(g.timestamp.min()),end=str(g.timestamp.max()),note='One sampled site profile; date parsed from records, not filename'))
    # Full ORNL source files remain in the source archive. In SQLite use 1-minute
    # means of selected meaningful channels with counts and source-row lineage.
    cols=['Timestamp','W_MT-COMP1','W_MT-COMP2','W_MT-COMP3','W_LT-COMP1','W_LT-COMP2','W-CONDENSOR',
          'T-GC-Fan2-In','T-LTcase-Sup','T-LTcase-Ret','T-MTCase-Sup','T-MTCase-Ret']
    frames=[]
    pairs={'Fault1_DisplayCaseDoorOpen.csv':'BaselineTestA.csv','Fault2_IceAccumulation.csv':'BaselineTestB.csv',
           'Fault3_EvapValveFailure.csv':'BaselineTestC.csv','Fault4_MTEvapFanFailure.csv':'BaselineTestD.csv',
           'Fault5_CondAPBlock.csv':'BaselineTestE.csv','Fault6_MTEvapAPBlock.csv':'BaselineTestA.csv'}
    for path in sorted((BASE/'ornl').glob('*.csv')):
        print('Processing',path.name,flush=True)
        d=pd.read_csv(path,usecols=cols); d['source_row']=np.arange(2,len(d)+2)
        d['timestamp']=pd.to_datetime(d.Timestamp,format='mixed',dayfirst=False)
        d['minute']=d.timestamp.dt.floor('min')
        numeric=d[cols[1:]].copy(); invalid=numeric.abs()>10000
        numeric=numeric.mask(invalid) # source sentinel-like values retained in originals
        numeric['minute']=d.minute
        m=numeric.groupby('minute').mean()
        m['samples']=d.groupby('minute').size();m['source_row_first']=d.groupby('minute').source_row.min()
        m['source_row_last']=d.groupby('minute').source_row.max()
        m['invalid_channel_samples']=invalid.sum(axis=1).groupby(d.minute).sum()
        m['file_id']=f'ornl/{path.name}';m['test_id']=path.stem
        m['test_role']='baseline_experiment' if path.name.startswith('Baseline') else 'fault_experiment'
        m['paired_baseline_file']=pairs.get(path.name,path.name)
        m=m.reset_index().rename(columns={'minute':'source_minute'})
        m.insert(0,'record_id',path.stem+':'+m.source_minute.astype(str))
        m['temperature_unit']='F per provider DataProcess.py'
        m['power_unit']='source unit; conversion not used for scenario'
        frames.append(m)
        summary.append(dict(source_id='ornl',file=path.name,records=len(d),start=str(d.timestamp.min()),end=str(d.timestamp.max()),note='Real experiment; minute means in database; all raw columns in archive'))
    ornl=pd.concat(frames,ignore_index=True)
    op={c:'metadata' for c in ornl};op.update({c:'derived_from_measurements' for c in cols[1:]})
    db.write('ornl_minute_measurements',ornl,'experiment × source minute',op,
             keys=['record_id'],refs={'file_id':('source_files','file_id')})
    nodes=[];edges=[];cases={}
    for case in range(1,5):
        n,dist,dur=load_freight(case);cases[case]=(n,dist,dur)
        summary.append(dict(source_id='ncst',file=f'BETVRPB{case}.csv',records=len(n),start=None,end=None,note='Nodes including depot; one constructed daily case; no calendar date assigned by provider'))
        for id,r in n.iterrows():
            nodes.append(dict(node_key=f'{case}:{id}',case_id=case,node_id=id,source_file=f'BETVRPB{case}.csv',
                source_row=id+2,tractor_id=int(r['Tractor id0']),stop_type=r.stop_type,longitude=r.longitude,latitude=r.latitude,
                service_duration_source=r['Stop Duration'],weight_source=r.weight,city=str(r.city_name).strip()))
        for i in n.index:
            for j in n.index:
                edges.append(dict(edge_id=f'{case}:{i}:{j}',case_id=case,from_node_key=f'{case}:{i}',to_node_key=f'{case}:{j}',distance_km=dist[i,j],travel_h=dur[i,j]))
    npv={c:'provider_case_from_real_operations' for c in pd.DataFrame(nodes)}
    for c in ['node_key','case_id','node_id','source_file','source_row']:npv[c]='metadata'
    db.write('logistics_nodes',pd.DataFrame(nodes),'case × node',npv,keys=['node_key'])
    db.write('logistics_edges',pd.DataFrame(edges),'case × ordered node pair','provider_calculated_road_network',keys=['edge_id'],refs={'from_node_key':('logistics_nodes','node_key'),'to_node_key':('logistics_nodes','node_key')})
    db.write('source_coverage',pd.DataFrame(summary),'source file','metadata')
    return vtt,cases,summary


def scenario_tables(db,c,vtt,cases):
    rng=np.random.default_rng(c['seed']);sid=c['scenario_id']
    dates=pd.date_range(c['start_date'],c['end_date'],freq='D');hours=pd.date_range(dates[0],dates[-1]+pd.Timedelta(hours=23),freq='h')
    db.write('scenarios',pd.DataFrame([dict(scenario_id=sid,seed=c['seed'],start_date=str(dates[0].date()),end_date=str(dates[-1].date()),
             status='synthetic integration; no measured intervention',currency='CU',geography='virtual; US routing plus transplanted Finnish load shape',
             time_basis='naive 24-hour scenario days; not UTC or verified Finnish local-time alignment')]),'one scenario','metadata',keys=['scenario_id'])
    params=[]
    for k,v in c.items():
        params.append(dict(parameter=k,value=json.dumps(v),provenance='configuration' if k in ['scenario_id','seed','start_date','end_date','notes'] else 'synthetic_assumption',
                           description='Editable design assumption; see README and config. Not inferred from observations.'))
    db.write('scenario_parameters',pd.DataFrame(params),'one editable input','synthetic_assumption',keys=['parameter'])
    zones=pd.DataFrame([
        dict(zone_id='chilled',scenario_id=sid,temperature_min_c=2.,temperature_max_c=5.,baseline_setpoint_c=3.,profile_fraction=.35,cop_reference=3.,thermal_capacity_kwh_per_c=160.,
             max_power_kw=250.,storage_capacity_kg=c['warehouse_capacity_kg']*.35,initial_temperature_c=3.,fan_kw=3.,lighting_kw=2.,defrost_kwh_per_event=.5),
        dict(zone_id='frozen',scenario_id=sid,temperature_min_c=-23.,temperature_max_c=-18.,baseline_setpoint_c=-20.,profile_fraction=.65,cop_reference=1.6,thermal_capacity_kwh_per_c=240.,
             max_power_kw=450.,storage_capacity_kg=c['warehouse_capacity_kg']*.65,initial_temperature_c=-20.,fan_kw=5.,lighting_kw=3.,defrost_kwh_per_event=2.)])
    db.write('cold_zones',zones,'one virtual zone','synthetic_assumption',keys=['zone_id'],refs={'scenario_id':('scenarios','scenario_id')})
    products=pd.DataFrame([
        dict(product_id='CHILL_A',zone_id='chilled',demand_share=.35,shelf_life_days=7,incoming_temperature_c=8.,specific_heat_kj_kg_k=3.5,purchase_cu_per_kg=2.,sale_cu_per_kg=2.8),
        dict(product_id='FROZEN_A',zone_id='frozen',demand_share=.40,shelf_life_days=60,incoming_temperature_c=-15.,specific_heat_kj_kg_k=1.8,purchase_cu_per_kg=3.,sale_cu_per_kg=4.),
        dict(product_id='FROZEN_B',zone_id='frozen',demand_share=.25,shelf_life_days=90,incoming_temperature_c=-15.,specific_heat_kj_kg_k=1.8,purchase_cu_per_kg=4.,sale_cu_per_kg=5.2)])
    db.write('products',products,'one virtual product','synthetic_assumption',keys=['product_id'],refs={'zone_id':('cold_zones','zone_id')})
    fleet=pd.DataFrame([dict(vehicle_id=f'truck_{i}',capacity_kg=c['truck_capacity_kg'],temperature_mode='multi-temperature assumed',
                            idle_l_per_h=c['truck_idle_l_per_h'],reefer_l_per_h=c['truck_reefer_l_per_h'],empty_l_per_km=c['truck_empty_l_per_km'],
                            full_load_increment_l_per_km=c['truck_full_load_increment_l_per_km'],available_start_h=0.,available_end_h=24.) for i in range(1,51)])
    db.write('vehicles',fleet,'one hypothetical truck','synthetic_assumption',keys=['vehicle_id'])
    orders=[];trips=[];stops=[];daily_cases=[]
    for di,date in enumerate(dates):
        case=di%4+1;n,dist,dur=cases[case];day=str(date.date())
        # Shared daily factor changes the total but not the provider routing topology.
        scale=c['source_weight_scale']*float(np.clip(rng.normal(1.,.08),.7,1.3))
        daily_cases.append(dict(date=day,case_id=case,quantity_multiplier=scale,assignment='synthetic cyclic replay'))
        for truck,g in n[n.index!=0].groupby('Tractor id0'):
            truck=int(truck);trip=f'{day}/truck_{truck}';seq=[0]+list(g.index)+[0]
            startload=float(g[g.stop_type=='Delivery'].weight.sum()*LB_TO_KG*scale)
            load=startload;km=0.;drive=0.;fuel=0.;clock=4.;peak=load
            for step,(a,b) in enumerate(zip(seq,seq[1:])):
                legkm=float(dist[a,b]);legh=float(dur[a,b]);km+=legkm;drive+=legh
                fuel+=legkm*(c['truck_empty_l_per_km']+c['truck_full_load_increment_l_per_km']*load/c['truck_capacity_kg'])
                clock+=legh
                if b==0:continue
                r=n.loc[b];mass=float(r.weight*LB_TO_KG*scale);service=float(r['Stop Duration']/60)
                before=load;load+=mass if r.stop_type=='Pickup' else -mass;peak=max(peak,load)
                stop_id=f'{trip}/{b}'
                stops.append(dict(stop_id=stop_id,trip_id=trip,node_key=f'{case}:{b}',sequence=step+1,arrival_h=clock,
                    departure_h=clock+service,service_h=service,stop_type=r.stop_type,quantity_kg=mass,load_before_kg=before,load_after_kg=load,
                    window_open_h=0.,window_close_h=24.,window_provenance='synthetic broad feasibility window'))
                if r.stop_type=='Delivery':
                    for p in products.itertuples():
                        orders.append(dict(order_id=f'{stop_id}/{p.product_id}',date=day,trip_id=trip,stop_id=stop_id,product_id=p.product_id,
                            source_node_key=f'{case}:{b}',demand_kg=mass*p.demand_share,customer_window_start_h=0.,customer_window_end_h=24.,
                            provenance='synthetic product allocation of rescaled provider-case weight'))
                clock+=service
            service=float(g['Stop Duration'].sum()/60);idle=service*c['truck_idle_l_per_h'];reefer=(drive+service)*c['truck_reefer_l_per_h']
            litres=fuel+idle+reefer
            trips.append(dict(trip_id=trip,date=day,vehicle_id=f'truck_{truck}',case_id=case,baseline_policy='source-row-order reconstruction; not observed GPS route',
                departure_h=4.,return_h=clock,distance_km=km,drive_h=drive,service_h=service,initial_load_kg=startload,peak_load_kg=peak,
                traction_litres=fuel,idle_litres=idle,reefer_litres=reefer,total_litres=litres,
                transport_kgco2=litres*DIESEL_CO2_KG_PER_L,
                transport_cost_cu=litres*c['diesel_cu_per_litre']+(drive+service)*c['driver_cu_per_h']+km*c['vehicle_nonfuel_cu_per_km']+c['dispatch_fixed_cu_per_truck'],
                quantity_multiplier=scale,capacity_feasible=int(peak<=c['truck_capacity_kg']),time_feasible=int(clock<=24)))
    trips=pd.DataFrame(trips);stops=pd.DataFrame(stops);orders=pd.DataFrame(orders)
    db.write('scenario_days',pd.DataFrame(daily_cases),'one synthetic day','synthetic_replay',keys=['date'])
    db.write('baseline_trips',trips,'scenario day × assigned truck','synthetic_model',keys=['trip_id'],refs={'vehicle_id':('vehicles','vehicle_id')})
    db.write('baseline_stops',stops,'trip × customer stop','synthetic_model',keys=['stop_id'],refs={'trip_id':('baseline_trips','trip_id'),'node_key':('logistics_nodes','node_key')})
    db.write('orders',orders,'day × delivery stop × product','synthetic_model',keys=['order_id'],refs={'trip_id':('baseline_trips','trip_id'),'stop_id':('baseline_stops','stop_id'),'product_id':('products','product_id')})
    # Causal inventory baseline: past realized demand drives regular orders;
    # shortages trigger separately costed emergency receipts. FEFO lots expire.
    demand=orders.groupby(['date','product_id']).demand_kg.sum();inventory=[];receipts=[];batches=[]
    for p in products.itertuples():
        initial=150000.*p.demand_share;lots=[[-1,initial,p.shelf_life_days-1]];pending=defaultdict(float);past=[]
        batches.append(dict(batch_id=f'{p.product_id}/initial',product_id=p.product_id,receipt_date=str(dates[0].date()),expiry_date=str((dates[0]+pd.Timedelta(days=p.shelf_life_days-1)).date()),quantity_kg=initial,kind='initial assumed stock'))
        for di,date in enumerate(dates):
            day=str(date.date());opening=sum(x[1] for x in lots);spoil=sum(x[1] for x in lots if x[2]<di);lots=[x for x in lots if x[2]>=di]
            regular=pending.pop(di,0.);need=float(demand.get((day,p.product_id),0.))
            emergency=max(0.,need-(opening-spoil+regular));receive=regular+emergency
            if receive>0:
                lots.append([di,receive,di+p.shelf_life_days-1])
                batch=f'{p.product_id}/{day}'
                batches.append(dict(batch_id=batch,product_id=p.product_id,receipt_date=day,expiry_date=str((date+pd.Timedelta(days=p.shelf_life_days-1)).date()),quantity_kg=receive,kind='generated replenishment'))
                receipts.append(dict(receipt_id=batch,batch_id=batch,product_id=p.product_id,date=day,receipt_hour=2,regular_kg=regular,emergency_kg=emergency,quantity_kg=receive))
            remaining=need
            for lot in sorted(lots,key=lambda x:x[2]):
                take=min(lot[1],remaining);lot[1]-=take;remaining-=take
            lots=[x for x in lots if x[1]>1e-8];closing=sum(x[1] for x in lots)
            history_mean=float(np.mean(past[-7:])) if past else initial/3.
            target=c['target_inventory_days']*history_mean
            placed=max(0.,target-closing-sum(pending.values()));pending[di+c['supplier_lead_days']]+=placed
            past.append(need)
            inventory.append(dict(inventory_id=f'{day}/{p.product_id}',date=day,product_id=p.product_id,opening_kg=opening,receipts_kg=receive,
                regular_receipts_kg=regular,emergency_receipts_kg=emergency,demand_kg=need,shipped_kg=need-remaining,shortage_kg=remaining,
                spoilage_kg=spoil,closing_kg=closing,regular_order_placed_kg=placed,pipeline_closing_kg=sum(pending.values()),
                receipt_purchase_cu=receive*p.purchase_cu_per_kg,shipped_cogs_cu=(need-remaining)*p.purchase_cu_per_kg,
                revenue_cu=(need-remaining)*p.sale_cu_per_kg,spoilage_writeoff_cu=spoil*p.purchase_cu_per_kg,
                holding_cu=(opening+closing)/2*c['holding_cu_per_kg_day'],disposal_cu=spoil*c['disposal_cu_per_kg'],
                shortage_penalty_cu=remaining*c['shortage_penalty_cu_per_kg'],emergency_fee_cu=emergency*c['emergency_receipt_cu_per_kg'],
                spoilage_embodied_kgco2e=spoil*c['spoilage_embodied_kgco2e_per_kg']))
    inventory=pd.DataFrame(inventory);receipts=pd.DataFrame(receipts)
    db.write('inventory_batches',pd.DataFrame(batches),'generated replenishment batch','synthetic_model',keys=['batch_id'],refs={'product_id':('products','product_id')})
    db.write('receipts',receipts,'day × product receipt','synthetic_model',keys=['receipt_id'],refs={'batch_id':('inventory_batches','batch_id'),'product_id':('products','product_id')})
    db.write('inventory_daily',inventory,'day × product','synthetic_model',keys=['inventory_id'],refs={'product_id':('products','product_id')})
    suppliers=pd.DataFrame([dict(supplier_id='supplier_1',lead_days=c['supplier_lead_days'],roundtrip_km=c['supplier_roundtrip_km'],
                                capacity_per_trip_kg=c['supplier_truck_capacity_kg'],trip_hours=c['supplier_trip_hours'])])
    db.write('suppliers',suppliers,'one virtual supplier','synthetic_assumption',keys=['supplier_id'])
    inbound=[]
    for date,total in receipts.groupby('date').quantity_kg.sum().items():
        count=int(np.ceil(total/c['supplier_truck_capacity_kg']))
        fuel=count*(c['supplier_roundtrip_km']*c['supplier_fuel_l_per_km']+c['supplier_trip_hours']*c['truck_reefer_l_per_h'])
        inbound.append(dict(inbound_id=date+'/supplier_1',date=date,supplier_id='supplier_1',receipt_kg=total,trips=count,
                            inbound_distance_km=count*c['supplier_roundtrip_km'],inbound_litres=fuel,inbound_kgco2=fuel*DIESEL_CO2_KG_PER_L,
                            inbound_cost_cu=fuel*c['diesel_cu_per_litre']+count*(c['supplier_trip_hours']*c['driver_cu_per_h']+c['supplier_roundtrip_km']*c['vehicle_nonfuel_cu_per_km']+c['dispatch_fixed_cu_per_truck'])))
    inbound=pd.DataFrame(inbound)
    db.write('inbound_transport',inbound,'supplier × receipt day','synthetic_model',keys=['inbound_id'],refs={'supplier_id':('suppliers','supplier_id')})
    # Use hourly store 2 only. Do not merge two temporal resolutions or sites.
    source=vtt[(vtt.store_id==2)&(vtt.interval_minutes==60)].copy();source['dt']=pd.to_datetime(source.Time)
    source=source.set_index('dt');past_by_hour=defaultdict(list);last=None;last_time=None
    # Warm-up uses records strictly earlier than scenario start, no future fills.
    for t,r in source.loc[source.index<hours[0]].sort_index().iterrows():
        if pd.notna(r.refrigeration) and r.refrigeration>=0:
            past_by_hour[t.hour].append(float(r.refrigeration));last=float(r.refrigeration);last_time=t
    signals=[];thermal=[]
    rec_by_zone=receipts.merge(products[['product_id','zone_id','incoming_temperature_c','specific_heat_kj_kg_k']],on='product_id')
    for t in hours:
        day=str(t.date());r=source.loc[t] if t in source.index else None
        observed=float(r.refrigeration) if r is not None and pd.notna(r.refrigeration) else np.nan
        if np.isfinite(observed) and observed>=0:
            value=observed;method='source_observation_replayed';last=value;last_time=t;past_by_hour[t.hour].append(value)
        elif last is not None and (t-last_time).total_seconds()<=6*3600:
            value=last;method='imputed_forward_fill_max_6h'
        elif past_by_hour[t.hour]:
            value=float(np.median(past_by_hour[t.hour][-28:]));method='imputed_past_same_hour_median'
        else:
            value=c['missing_profile_fallback_kw']/c['vtt_source_unit_to_kw_assumption'];method='synthetic_fallback'
        hour=t.hour;doy=t.day_of_year
        ambient=15+10*np.sin(2*np.pi*(doy-110)/365)+4*np.sin(2*np.pi*(hour-9)/24)
        grid=max(.03,c['grid_mean_kgco2_per_kwh']*(1+.30*np.cos(2*np.pi*(hour-19)/24))+.015*np.sin(2*np.pi*doy/365))
        tariff=c['electricity_base_cu_per_kwh']*(1.5 if 16<=hour<21 else .75 if hour<6 else 1.)
        signals.append(dict(timestamp=str(t),date=day,hour=hour,ambient_c=ambient,grid_kgco2_per_kwh=grid,electricity_cu_per_kwh=tariff,
            diesel_cu_per_litre=c['diesel_cu_per_litre'],source_power_value=observed,profile_value_used=value,
            source_record_id=r.record_id if r is not None else None,profile_method=method,
            source_unit_conversion='ASSUMPTION: 1 source unit = 1 kW',
            evaluation_split='train' if t<pd.Timestamp('2018-02-01') else 'validation' if t<pd.Timestamp('2018-04-01') else 'test',
            provenance='synthetic signals + source replay; no live Fingrid data'))
        dailytrip=trips[trips.date==day]
        events=(len(dailytrip) if hour==4 else 0)+int((dailytrip.return_h.astype(int)==hour).sum())
        day_receipts=rec_by_zone[rec_by_zone.date==day] if hour==2 else rec_by_zone.iloc[:0]
        if hour==2:events+=int(inbound.loc[inbound.date==day,'trips'].sum())
        for z in zones.itertuples():
            cop=max(.8,z.cop_reference/(1+.015*max(0.,ambient-15)))
            basepower=value*c['vtt_source_unit_to_kw_assumption']*c['source_profile_scale']*z.profile_fraction
            qbackground=basepower*cop
            zr=day_receipts[day_receipts.zone_id==z.zone_id]
            qproduct=float((zr.quantity_kg*zr.specific_heat_kj_kg_k*(zr.incoming_temperature_c-z.baseline_setpoint_c)/3600).sum())
            qdoor=events*c['door_heat_kwh_th_per_event']*z.profile_fraction
            lighting=z.lighting_kw if 4<=hour<20 else 0.
            defrost=z.defrost_kwh_per_event if hour in (0,6,12,18) else 0.
            auxiliary=z.fan_kw+lighting+defrost
            # Synthetic assumption: auxiliary electricity becomes heat in zone.
            qtotal=qbackground+qproduct+qdoor+auxiliary;power=qtotal/cop;energy=power+auxiliary
            thermal.append(dict(thermal_id=f'{t}/{z.zone_id}',timestamp=str(t),date=day,zone_id=z.zone_id,
                background_heat_kwh_th=qbackground,product_heat_kwh_th=qproduct,door_heat_kwh_th=qdoor,total_heat_kwh_th=qtotal,
                door_events=events,cop=cop,fan_energy_kwh=z.fan_kw,lighting_energy_kwh=lighting,defrost_energy_kwh=defrost,
                auxiliary_energy_kwh=auxiliary,baseline_power_kw=power,baseline_energy_kwh=energy,
                baseline_temperature_c=z.baseline_setpoint_c,baseline_end_temperature_c=z.baseline_setpoint_c,
                baseline_storage_kgco2=energy*grid,baseline_electricity_cost_cu=energy*tariff,power_feasible=int(power<=z.max_power_kw),
                thermal_model='T_next=T+(Q_background+Q_product+Q_door+Q_aux-COP*P*1h)/C; synthetic load calibrated to replay'))
    signals=pd.DataFrame(signals);thermal=pd.DataFrame(thermal)
    sp={col:'synthetic_assumption' for col in signals}
    for col in ['timestamp','date','hour','source_record_id','profile_method','source_unit_conversion','provenance','evaluation_split']:sp[col]='metadata'
    sp['source_power_value']='measured_field_replayed';sp['profile_value_used']='mixed_replay_or_imputation'
    db.write('hourly_inputs',signals,'scenario hour',sp,keys=['timestamp'],refs={'source_record_id':('vtt_power_observations','record_id')})
    db.write('cold_storage_hourly',thermal,'scenario hour × cold zone','synthetic_model',keys=['thermal_id'],refs={'timestamp':('hourly_inputs','timestamp'),'zone_id':('cold_zones','zone_id')})
    day=thermal.groupby('date')[['baseline_energy_kwh','baseline_storage_kgco2','baseline_electricity_cost_cu']].sum()
    day=day.join(trips.groupby('date')[['distance_km','total_litres','transport_kgco2','transport_cost_cu']].sum())
    day=day.join(inbound.groupby('date')[['inbound_distance_km','inbound_litres','inbound_kgco2','inbound_cost_cu']].sum()).fillna(0.)
    invcols=['revenue_cu','shipped_cogs_cu','receipt_purchase_cu','holding_cu','spoilage_writeoff_cu','disposal_cu','shortage_penalty_cu','emergency_fee_cu','spoilage_embodied_kgco2e','shipped_kg','spoilage_kg']
    day=day.join(inventory.groupby('date')[invcols].sum())
    day['refrigerant_leak_kgco2e']=c['refrigerant_charge_kg']*c['annual_refrigerant_leak_fraction']*c['refrigerant_gwp100']/365
    day['operational_kgco2e_partial_scope']=day.baseline_storage_kgco2+day.transport_kgco2+day.inbound_kgco2+day.refrigerant_leak_kgco2e
    day['expanded_kgco2e_with_spoilage']=day.operational_kgco2e_partial_scope+day.spoilage_embodied_kgco2e
    day['carbon_cost_cu']=day.operational_kgco2e_partial_scope/1000*c['carbon_price_cu_per_tonne']
    costcols=['baseline_electricity_cost_cu','transport_cost_cu','inbound_cost_cu','holding_cu','disposal_cu','shortage_penalty_cu','emergency_fee_cu','carbon_cost_cu']
    day['operating_cost_cu']=day[costcols].sum(axis=1)
    day['modelled_contribution_cu']=day.revenue_cu-day.shipped_cogs_cu-day.spoilage_writeoff_cu-day.operating_cost_cu
    day=day.reset_index();day['provenance']='synthetic baseline; not optimized or measured savings'
    db.write('baseline_daily',day,'scenario day','synthetic_model',keys=['date'])
    monthly=day.copy();monthly['month']=monthly.date.str[:7]
    monthly=monthly.groupby('month')[day.select_dtypes('number').columns].sum().reset_index()
    monthly['observed_days']=0;monthly['scenario_days']=day.groupby(day.date.str[:7]).size().to_numpy()
    monthly['result_status']='baseline only; reduction percentages not computed'
    db.write('baseline_monthly',monthly,'scenario month','synthetic_model',keys=['month'])
    return signals,thermal,trips,inventory,day,monthly


def main():
    c=json.loads(CONFIG.read_text());validate_config(c)
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'csv').mkdir(exist_ok=True)
    temporary=OUT/'sustainable_inventory.building.sqlite'
    if temporary.exists(): temporary.unlink()
    db=Database(temporary)
    source_files=source_tables(db);vtt,cases,coverage=import_real_data(db)
    signals,thermal,trips,inventory,daily,monthly=scenario_tables(db,c,vtt,cases)
    decision_catalog(db)
    catalog=pd.DataFrame(db.catalog);fields=pd.DataFrame(db.fields)
    db.write('table_catalog',catalog,'one table','metadata',keys=['table_name'])
    db.write('field_dictionary',fields,'one table column','metadata')
    db.connection.executescript('''
    CREATE VIEW optimization_hourly AS
      SELECT h.*,z.zone_id,z.temperature_min_c,z.temperature_max_c,z.max_power_kw,z.thermal_capacity_kwh_per_c,
             c.total_heat_kwh_th,c.cop,c.baseline_power_kw,c.baseline_temperature_c
      FROM hourly_inputs h JOIN cold_storage_hourly c USING(timestamp) JOIN cold_zones z USING(zone_id);
    CREATE INDEX idx_orders_date_product ON orders(date,product_id);
    CREATE INDEX idx_stops_trip_sequence ON baseline_stops(trip_id,sequence);
    CREATE INDEX idx_cold_date_zone ON cold_storage_hourly(date,zone_id);
    ''')
    # Reconcile before publishing, with no fabricated savings targets.
    checks={
        'sqlite_integrity':db.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok',
        'foreign_keys':not db.connection.execute('PRAGMA foreign_key_check').fetchall(),
        'inventory_mass_balance':bool(np.allclose(inventory.opening_kg+inventory.receipts_kg-inventory.shipped_kg-inventory.spoilage_kg,inventory.closing_kg,atol=1e-7)),
        'no_negative_inventory':bool((inventory.closing_kg>=-1e-7).all()),
        'warehouse_capacity':bool(inventory.groupby('date').closing_kg.sum().le(c['warehouse_capacity_kg']).all()),
        'truck_capacity_feasible':bool(trips.capacity_feasible.all()),
        'truck_time_feasible':bool(trips.time_feasible.all()),
        'cold_power_feasible':bool(thermal.power_feasible.all()),
        'thermal_energy_balance':bool(np.allclose(thermal.total_heat_kwh_th,thermal.cop*thermal.baseline_power_kw)),
        'monthly_reconciles':bool(np.isclose(monthly.operational_kgco2e_partial_scope.sum(),daily.operational_kgco2e_partial_scope.sum())),
        'one_hourly_input_per_hour':len(signals)==len(pd.date_range(c['start_date'],c['end_date']+' 23:00:00',freq='h')),
        'no_missing_scenario_power':bool(np.isfinite(thermal.baseline_power_kw).all()),
    }
    if not all(checks.values()):
        raise ValueError(f'Database validation failed: {checks}')
    # Measure composition over non-null analytical cells, not inflated raw row counts.
    scope=['hourly_inputs','cold_storage_hourly','orders','baseline_trips','inventory_daily']
    selected=fields[fields.table_name.isin(scope)&~fields.provenance.eq('metadata')&fields.sql_type.isin(['REAL','INTEGER'])]
    composition=selected.groupby('provenance').nonnull_cells.sum().to_dict();den=sum(composition.values())
    metrics={'scenario_id':c['scenario_id'],'scenario_months':len(monthly),'scenario_days':len(daily),
             'tables':db.catalog,'checks':checks,'source_coverage':coverage,
             'profile_methods':signals.profile_method.value_counts().to_dict(),
             'composition':{'scope_tables':scope,'denominator':'non-null numeric analytical cells; metadata excluded; no claims about physical reality from row fractions',
                            'nonnull_cells':den,'by_category':{k:{'cells':int(v),'percent':100*v/den} for k,v in composition.items()}},
             'fingrid_status':'not downloaded; HTTP 401; synthetic grid profile is active',
             'savings_status':'not evaluated; database and feasible baseline only',
             'build_utc':datetime.now(timezone.utc).isoformat()}
    (OUT/'validation_report.json').write_text(json.dumps(metrics,indent=2))
    db.connection.commit();db.connection.close()
    temporary.replace(OUT/'sustainable_inventory.sqlite')
    (OUT/'scenario_config.json').write_text(CONFIG.read_text())
    print(json.dumps({k:v for k,v in metrics.items() if k not in ['tables','source_coverage']},indent=2),flush=True)


if __name__=='__main__':main()

"""Audited, perfect-information scenario benchmarks for the research database.

Fuel-aware, block-preserving 2-opt + daily temperature-constrained linear
programs. These are conditional model estimates, never deployed savings.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import linprog

ROOT=Path(__file__).resolve().parents[2]
DB=ROOT/'outputs/research_database/sustainable_inventory.sqlite'
OUT=ROOT/'outputs/research_results'
POLICIES={'baseline':'Baseline','transport':'Transport only','storage':'Cold storage only','combined':'Combined'}
EF=10.21/3.785411784


def load_tables():
    with sqlite3.connect(f'file:{DB}?mode=ro',uri=True) as c:
        return {t:pd.read_sql_query(f'SELECT * FROM "{t}"',c) for t in [
            'baseline_daily','baseline_trips','baseline_stops','logistics_nodes','logistics_edges',
            'cold_storage_hourly','hourly_inputs','cold_zones','inventory_daily','orders']}


def route_values(order,nodes,dist,duration,scale,c):
    load=sum(float(nodes.loc[i,'weight_source'])*.45359237*scale for i in order if nodes.loc[i,'stop_type']=='Delivery')
    initial=load;peak=load;km=drive=traction=service=0.;clock=4.;visits=[]
    seq=[0]+list(order)+[0]
    for a,b in zip(seq,seq[1:]):
        d=float(dist[a,b]);h=float(duration[a,b]);km+=d;drive+=h;clock+=h
        traction+=d*(c['truck_empty_l_per_km']+c['truck_full_load_increment_l_per_km']*load/c['truck_capacity_kg'])
        if b:
            r=nodes.loc[b];mass=r.weight_source*.45359237*scale
            before=load;load+=mass if r.stop_type=='Pickup' else -mass;peak=max(peak,load)
            if load < -1e-6:raise ValueError('Negative route load')
            h=r.service_duration_source/60;service+=h
            visits.append(dict(node_id=int(b),arrival_h=clock,departure_h=clock+h,load_before_kg=before,load_after_kg=load))
            clock+=h
    idle=service*c['truck_idle_l_per_h'];reefer=(drive+service)*c['truck_reefer_l_per_h'];fuel=traction+idle+reefer
    return dict(distance_km=km,drive_h=drive,service_h=service,return_h=clock,initial_load_kg=initial,peak_load_kg=peak,
                traction_litres=traction,idle_litres=idle,reefer_litres=reefer,total_litres=fuel,transport_kgco2=fuel*EF,
                transport_cost_cu=fuel*c['diesel_cu_per_litre']+(drive+service)*c['driver_cu_per_h']+km*c['vehicle_nonfuel_cu_per_km']+c['dispatch_fixed_cu_per_truck'],visits=visits)


def optimise_routes(t,c):
    routes=[];stops=[];candidate_cache={}
    for case,group in t['logistics_nodes'].groupby('case_id'):
        n=group.set_index('node_id');e=t['logistics_edges'].query('case_id==@case').copy()
        e['i']=e.from_node_key.str.split(':').str[-1].astype(int);e['j']=e.to_node_key.str.split(':').str[-1].astype(int)
        d=e.pivot(index='i',columns='j',values='distance_km').to_numpy();h=e.pivot(index='i',columns='j',values='travel_h').to_numpy()
        for truck,g in n[n.index!=0].groupby('tractor_id'):
            original=list(g.sort_index().index);best=original[:]
            baseline=route_values(original,n,d,h,c['source_weight_scale'],c);current=baseline
            # First-improvement 2-opt within a same-type block preserves the
            # source pickup/delivery precedence. This is a heuristic, not proof
            # of global VRP optimality.
            for _ in range(100):
                found=False
                for i in range(len(best)-1):
                    for j in range(i+1,len(best)):
                        if n.loc[best[i:j+1],'stop_type'].nunique()!=1:continue
                        proposal=best[:i]+best[i:j+1][::-1]+best[j+1:]
                        m=route_values(proposal,n,d,h,c['source_weight_scale'],c)
                        if (m['transport_kgco2']<current['transport_kgco2']-1e-7 and
                            m['transport_cost_cu']<=baseline['transport_cost_cu']+1e-7 and
                            m['return_h']<=baseline['return_h']+1e-7 and
                            m['peak_load_kg']<=baseline['peak_load_kg']+1e-7):
                            best,current,found=proposal,m,True;break
                    if found:break
                if not found:break
            candidate_cache[(case,int(truck))]=(original,best,n,d,h)
    for b in t['baseline_trips'].itertuples():
        truck=int(b.vehicle_id.split('_')[-1]);original,best,n,d,h=candidate_cache[(b.case_id,truck)]
        base=route_values(original,n,d,h,b.quantity_multiplier,c)
        m=route_values(best,n,d,h,b.quantity_multiplier,c)
        if m['transport_kgco2']>base['transport_kgco2']+1e-7 or m['transport_cost_cu']>base['transport_cost_cu']+1e-7:
            best=original;m=base
        assert abs(base['total_litres']-b.total_litres)<1e-7
        visits=m.pop('visits')
        routes.append(dict(trip_id=b.trip_id,date=b.date,vehicle_id=b.vehicle_id,case_id=b.case_id,
                           original_order=json.dumps(original),selected_order=json.dumps(best),**m))
        for seq,s in enumerate(visits,1):stops.append(dict(trip_id=b.trip_id,date=b.date,sequence=seq,case_id=b.case_id,**s))
    return pd.DataFrame(routes),pd.DataFrame(stops)


def cooling_lp(h,z,cost_cap,capacity_scale=1.):
    """24 power variables + 25 temperature states per zone; exact end state."""
    groups=[h[h.zone_id.eq(zone.zone_id)].sort_values('timestamp').reset_index(drop=True) for zone in z.itertuples()]
    nz=len(z);nvars=49*nz;objective=np.zeros(nvars);cost=np.zeros(nvars);bounds=[];eq=[];rhs=[]
    for zi,(zone,g) in enumerate(zip(z.itertuples(),groups)):
        if len(g)!=24:raise ValueError('LP requires 24 hourly intervals per zone')
        offset=49*zi;capacity=zone.thermal_capacity_kwh_per_c*capacity_scale
        objective[offset:offset+24]=g.grid_kgco2_per_kwh.to_numpy();cost[offset:offset+24]=g.electricity_cu_per_kwh.to_numpy()
        bounds.extend([(0,zone.max_power_kw)]*24)
        bounds.extend([(zone.baseline_setpoint_c,zone.baseline_setpoint_c)]+[(zone.temperature_min_c,zone.temperature_max_c)]*23+[(zone.baseline_setpoint_c,zone.baseline_setpoint_c)])
        for hour in range(24):
            row=np.zeros(nvars);row[offset+hour]=g.cop.iloc[hour]/capacity
            row[offset+24+hour]=-1;row[offset+25+hour]=1
            eq.append(row);rhs.append(g.total_heat_kwh_th.iloc[hour]/capacity)
    auxcost=sum((g.auxiliary_energy_kwh*g.electricity_cu_per_kwh).sum() for g in groups)
    solved=linprog(objective,A_ub=cost.reshape(1,-1),b_ub=[cost_cap-auxcost],A_eq=np.array(eq),b_eq=np.array(rhs),bounds=bounds,method='highs')
    if not solved.success:raise RuntimeError(f'Cooling LP infeasible/failed: {solved.message}')
    result=[]
    for zi,(zone,g) in enumerate(zip(z.itertuples(),groups)):
        o=49*zi;g=g.copy();g['power_kw']=solved.x[o:o+24];g['temperature_start_c']=solved.x[o+24:o+48];g['temperature_end_c']=solved.x[o+25:o+49]
        g['thermal_capacity_kwh_per_c']=zone.thermal_capacity_kwh_per_c*capacity_scale
        result.append(g)
    return pd.concat(result,ignore_index=True)


def audit_hourly(h,z):
    limits=z.set_index('zone_id');max_res=0.;violations=0;terminal=0.
    for (day,zone),g in h.groupby(['date','zone_id']):
        g=g.sort_values('timestamp');p=limits.loc[zone]
        residual=g.temperature_end_c-g.temperature_start_c-(g.total_heat_kwh_th-g.cop*g.power_kw)/g.thermal_capacity_kwh_per_c
        max_res=max(max_res,float(residual.abs().max()))
        violations+=int(((g.temperature_end_c<p.temperature_min_c-1e-6)|(g.temperature_end_c>p.temperature_max_c+1e-6)|(g.power_kw< -1e-6)|(g.power_kw>p.max_power_kw+1e-6)).sum())
        terminal=max(terminal,abs(g.temperature_start_c.iloc[0]-p.baseline_setpoint_c),abs(g.temperature_end_c.iloc[-1]-p.baseline_setpoint_c))
        if not np.allclose(g.temperature_start_c.iloc[1:],g.temperature_end_c.iloc[:-1],atol=1e-6):raise ValueError('Discontinuous temperatures')
    return dict(thermal_residual_c=max_res,temperature_or_power_violations=violations,terminal_temperature_error_c=terminal)


def evaluate(capacity_scale=1.,tables=None,routes=None):
    t=tables or load_tables();c=json.loads((ROOT/'outputs/research_database/scenario_config.json').read_text())
    if routes is None:routes,stops=optimise_routes(t,c)
    else:stops=None
    z=t['cold_zones'];inputs=t['hourly_inputs'];base=t['baseline_daily'].set_index('date')
    cold=t['cold_storage_hourly'].merge(inputs[['timestamp','hour','grid_kgco2_per_kwh','electricity_cu_per_kwh']],on='timestamp',validate='many_to_one')
    hourly=[];daily=[];audits=[]
    base_groups={d:g for d,g in t['baseline_trips'].groupby('date')};route_groups={d:g for d,g in routes.groupby('date')}
    for date,original in cold.groupby('date',sort=True):
        b=base.loc[date];original=original.copy();changed=original.copy()
        # Exactly the same number of return events, with their new return times.
        old=base_groups[date].return_h.astype(int).value_counts();new=route_groups[date].return_h.astype(int).value_counts()
        delta={hour:int(new.get(hour,0)-old.get(hour,0)) for hour in range(24)}
        changed['door_events']=changed.door_events+changed.hour.map(delta)
        changed['door_heat_kwh_th']=changed.door_heat_kwh_th+changed.hour.map(delta)*c['door_heat_kwh_th_per_event']*changed.zone_id.map(z.set_index('zone_id').profile_fraction)
        changed['total_heat_kwh_th']=changed.background_heat_kwh_th+changed.product_heat_kwh_th+changed.door_heat_kwh_th+changed.auxiliary_energy_kwh
        for policy in POLICIES:
            g=(changed if policy in ('transport','combined') else original).copy()
            if policy in ('storage','combined'):
                g=cooling_lp(g,z,b.baseline_electricity_cost_cu,capacity_scale)
            else:
                g['power_kw']=g.total_heat_kwh_th/g.cop
                g['temperature_start_c']=g.zone_id.map(z.set_index('zone_id').baseline_setpoint_c)
                g['temperature_end_c']=g.temperature_start_c
                g['thermal_capacity_kwh_per_c']=g.zone_id.map(z.set_index('zone_id').thermal_capacity_kwh_per_c)*capacity_scale
            g['policy']=policy;g['energy_kwh']=g.power_kw+g.auxiliary_energy_kwh
            g['storage_kgco2']=g.energy_kwh*g.grid_kgco2_per_kwh;g['electricity_cost_cu']=g.energy_kwh*g.electricity_cu_per_kwh
            hourly.append(g)
            r=route_groups[date] if policy in ('transport','combined') else base_groups[date]
            transit=r.transport_kgco2.sum();tcost=r.transport_cost_cu.sum()
            electricity=g.electricity_cost_cu.sum();storage=g.storage_kgco2.sum()
            emissions=transit+b.inbound_kgco2+storage+b.refrigerant_leak_kgco2e
            operating=b.operating_cost_cu-b.transport_cost_cu-b.baseline_electricity_cost_cu-b.carbon_cost_cu+tcost+electricity+emissions/1000*c['carbon_price_cu_per_tonne']
            daily.append(dict(date=date,month=date[:7],policy=policy,transport_kgco2=transit,inbound_kgco2=b.inbound_kgco2,storage_kgco2=storage,
                refrigerant_kgco2e=b.refrigerant_leak_kgco2e,total_kgco2e=emissions,operating_cost_cu=operating,
                electricity_cost_cu=electricity,transport_cost_cu=tcost,energy_kwh=g.energy_kwh.sum(),distance_km=r.distance_km.sum(),fuel_litres=r.total_litres.sum(),
                shipped_kg=b.shipped_kg,spoilage_kg=b.spoilage_kg,contribution_cu=b.modelled_contribution_cu+b.operating_cost_cu-operating,
                inbound_cost_cu=b.inbound_cost_cu,other_operating_cost_cu=operating-tcost-electricity-b.inbound_cost_cu,
                evidence='perfect-information synthetic benchmark'))
    daily=pd.DataFrame(daily);hourly=pd.concat(hourly,ignore_index=True)
    for policy,g in hourly.groupby('policy'):
        audits.append(dict(policy=policy,**audit_hourly(g,z)))
    audit=pd.DataFrame(audits)
    for field in ['total_kgco2e','operating_cost_cu','energy_kwh','distance_km']:
        reference=daily[daily.policy.eq('baseline')].set_index('date')[field]
        daily['baseline_'+field]=daily.date.map(reference)
    daily['carbon_saved_kg']=daily.baseline_total_kgco2e-daily.total_kgco2e
    daily['cost_saved_cu']=daily.baseline_operating_cost_cu-daily.operating_cost_cu
    daily['carbon_reduction_pct']=100*daily.carbon_saved_kg/daily.baseline_total_kgco2e
    daily['cost_reduction_pct']=100*daily.cost_saved_cu/daily.baseline_operating_cost_cu
    monthly=daily.groupby(['month','policy']).sum(numeric_only=True).reset_index()
    # Recalculate rates from totals. Never sum or average percentage reductions.
    monthly['carbon_reduction_pct']=100*monthly.carbon_saved_kg/monthly.baseline_total_kgco2e
    monthly['cost_reduction_pct']=100*monthly.cost_saved_cu/monthly.baseline_operating_cost_cu
    return daily,monthly,hourly,routes,stops,audit


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    t=load_tables();c=json.loads((ROOT/'outputs/research_database/scenario_config.json').read_text())
    routes,stops=optimise_routes(t,c);print('Routes evaluated',len(routes),flush=True)
    daily,monthly,hourly,routes,_,audit=evaluate(tables=t,routes=routes)
    baseline=daily.query("policy=='baseline'").set_index('date');original=t['baseline_daily'].set_index('date')
    checks=dict(baseline_carbon_matches_database=bool(np.allclose(baseline.total_kgco2e,original.operational_kgco2e_partial_scope)),
        baseline_cost_matches_database=bool(np.allclose(baseline.operating_cost_cu,original.operating_cost_cu)),
        thermal_balance=bool(audit.thermal_residual_c.max()<1e-6),temperature_bounds=bool(audit.temperature_or_power_violations.sum()==0),
        equal_terminal_temperatures=bool(audit.terminal_temperature_error_c.max()<1e-6),
        same_stops=all(sorted(json.loads(r.original_order))==sorted(json.loads(r.selected_order)) for r in routes.itertuples()),
        capacity=bool(routes.peak_load_kg.le(c['truck_capacity_kg']+1e-6).all()),truck_windows=bool(routes.return_h.le(24).all()),
        same_inventory_and_service=bool(daily.groupby('date').shipped_kg.nunique().max()==1),
        combined_cost_nonincreasing=bool(daily.query("policy=='combined'").cost_saved_cu.ge(-1e-5).all()),
        combined_carbon_nonincreasing=bool(daily.query("policy=='combined'").carbon_saved_kg.ge(-1e-5).all()))
    if not all(checks.values()):raise ValueError(checks)
    for name,data in [('daily_results',daily),('monthly_results',monthly),('hourly_results',hourly),('selected_routes',routes),('selected_stops',stops),('feasibility_audit',audit)]:data.to_csv(OUT/(name+'.csv'),index=False)
    totals=daily.groupby('policy').sum(numeric_only=True)
    headline={}
    for policy in POLICIES:
        row=totals.loc[policy];headline[policy]={k:float(row[k]) for k in ['total_kgco2e','operating_cost_cu','carbon_saved_kg','cost_saved_cu','storage_kgco2','transport_kgco2','energy_kwh','distance_km']}
        headline[policy]['carbon_reduction_pct']=100*row.carbon_saved_kg/row.baseline_total_kgco2e
        headline[policy]['cost_reduction_pct']=100*row.cost_saved_cu/row.baseline_operating_cost_cu
    report=dict(status='validated conditional scenario benchmark',database_sha256=hashlib.sha256(DB.read_bytes()).hexdigest(),
        built_utc=datetime.now(timezone.utc).isoformat(),checks=checks,headline=headline,days=365,months=12,
        algorithms=['Fuel-aware first-improvement 2-opt within same-type stop blocks, fixed truck assignments','Daily linear programming via SciPy HiGHS; two zones, temperature balance, power bounds, electricity-cost cap, identical terminal temperatures'],
        evidence='Perfect information about daily heat load, carbon and tariffs. Synthetic integration, not an operational forecast or measured reduction.',
        fixed_factors='Orders, inventory, replenishment, supplier trips, leakage, fans/lights/defrost and spoilage fixed across policies. Only routing and compressor schedules optimised.',
        scope='Electricity and diesel combustion CO2 plus assumed R744 leakage; partial GHG inventory. CU is fictional; capital/implementation costs excluded.')
    (OUT/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()

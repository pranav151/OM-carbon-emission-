"""Measured refrigeration inputs and an explicitly hypothetical combined scenario.

The optimisation is a daily, perfect-information MILP. It does not infer product
temperature or claim deployed savings. Original source files remain untouched.
"""
from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json
import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs

ROOT = Path(__file__).resolve().parents[2]
COLD = ROOT / 'data/research/cold_storage/multipack'
FREIGHT = ROOT / 'data/research/carbon_inventory/ncst_2023_v1'
OUT = ROOT / 'outputs/cold_chain'
COLD_DOI = 'https://doi.org/10.18710/T5OHPR'
FREIGHT_DOI = 'https://doi.org/10.6086/D11974'
POLICIES = {'baseline': 'Baseline', 'transport': 'Transport only', 'storage': 'Cold storage only', 'combined': 'Combined optimisation'}


@dataclass(frozen=True)
class Settings:
    buffer_kwh_th: float = 4.0
    hourly_loss: float = 0.01
    power_headroom: float = 1.25
    carnot_efficiency: float = 0.35
    evaporator_c: float = -30.0
    condenser_approach_c: float = 10.0
    dock_heat_kwh_th_per_truck: float = 2.0
    grid_kg_co2_per_kwh: float = 436.655 * 0.45359237 / 1000
    diesel_litres_per_km: float = 0.30
    electricity_cu_per_kwh: float = 0.20
    transport_cu_per_km: float = 1.0
    departure_hour: int = 6

    def validate(self):
        if not all(np.isfinite(v) for v in asdict(self).values()):
            raise ValueError('Settings must be finite')
        if self.buffer_kwh_th < 0 or not 0 <= self.hourly_loss < 1 or self.power_headroom < 1:
            raise ValueError('Invalid storage capacity, loss or power headroom')
        if not 0 < self.carnot_efficiency <= 1 or self.evaporator_c <= -273.15:
            raise ValueError('Invalid thermodynamic assumptions')
        if any(v < 0 for k, v in asdict(self).items() if k in ('dock_heat_kwh_th_per_truck', 'grid_kg_co2_per_kwh', 'diesel_litres_per_km', 'electricity_cu_per_kwh', 'transport_cu_per_km')):
            raise ValueError('Factors and costs must be nonnegative')


def load_cold_measurements():
    """Parse six original UTF-16 TSV files; preserve raw negative readings."""
    records = []
    for path in sorted(COLD.glob('*Research*.txt')):
        rows = list(csv.reader(path.read_text(encoding='utf-16').splitlines(), delimiter='\t'))
        rome = 'Roma' in path.name
        for source_row, row in enumerate(rows[2:], 3):
            if not row or not row[0].strip():
                continue
            date = pd.to_datetime(row[0].split()[0], dayfirst=True)
            timestamp = date + pd.to_timedelta(row[1])
            # Row 2 of each file specifies W in Rome and kW in Trento.
            lt = float(row[12]) / 1000 if rome else float(row[18])
            records.append(dict(source_file=path.name, source_row=source_row,
                site='Rome' if rome else 'Trento', timestamp=timestamp,
                lt_power_kw=lt, lt_power_unit_source=rows[1][12 if rome else 18],
                ambient_c=float(row[23]) if rome else np.nan,
                integrated_system_power_kw=float(row[15])/1000 if rome else np.nan,
                quality_flag='negative_power_preserved' if lt < 0 else 'source_observation',
                source_doi=COLD_DOI, provenance='measured_field_record'))
    if not records:
        raise FileNotFoundError('Download MultiPACK inputs before opening the cold-chain study')
    return pd.DataFrame(records)


def hourly_profiles(measurements):
    """Hour-of-day means, explicitly a 24-hour replay, not gap-free metering."""
    selected = measurements[measurements.site.eq('Rome')].copy()
    selected['hour'] = selected.timestamp.dt.hour
    h = selected.groupby(['source_file', 'hour']).agg(
        observed_lt_power_kw=('lt_power_kw','mean'), ambient_c=('ambient_c','mean'),
        samples=('lt_power_kw','size'), source_start=('timestamp','min'), source_end=('timestamp','max')).reset_index()
    for _, day in h.groupby('source_file'):
        if list(day.hour) != list(range(24)) or day.observed_lt_power_kw.isna().any() or (day.observed_lt_power_kw < 0).any():
            raise ValueError('A complete nonnegative 24-hour profile is required; no silent filling')
    h['source_date'] = h.source_file.map(selected.groupby('source_file').timestamp.min().dt.date.astype(str))
    h['cold_source_doi'] = COLD_DOI
    return h


def load_freight(case):
    if case not in (1,2,3,4):
        raise ValueError('Unknown NCST case')
    raw = pd.read_csv(FREIGHT / f'BETVRPB{case}.csv')
    nodes = raw[raw.id.astype(str).str.fullmatch(r'\d+')].copy()
    nodes['id'] = nodes.id.astype(int)
    for c in ('Tractor id0','Stop Duration','weight','latitude','longitude'):
        nodes[c] = pd.to_numeric(nodes[c])
    nodes = nodes.set_index('id')
    distance = pd.read_csv(FREIGHT / f'BETVRPB{case}_dist.csv').to_numpy(dtype=float) / 1000
    duration = pd.read_csv(FREIGHT / f'BETVRPB{case}_time.csv').to_numpy(dtype=float) / 3600
    if distance.shape != (len(nodes), len(nodes)):
        raise ValueError('Freight nodes and distance matrix do not align')
    return nodes, distance, duration


def route_metrics(order, nodes, distance, duration):
    seq = [0] + list(order) + [0]
    km = sum(distance[a,b] for a,b in zip(seq,seq[1:]))
    # Assumed minutes and pounds, based on the report; source headers omit units.
    hours = sum(duration[a,b] for a,b in zip(seq,seq[1:])) + nodes.loc[order,'Stop Duration'].sum()/60
    load = nodes.loc[order].query("stop_type == 'Delivery'").weight.sum()
    peak = load
    for node in order:
        load += nodes.loc[node,'weight'] * (1 if nodes.loc[node,'stop_type']=='Pickup' else -1)
        peak = max(peak,load)
        if load < -1e-6:
            raise ValueError('Negative reconstructed vehicle load')
    return float(km), float(hours), float(peak)


def route_candidates(case, settings):
    """2-opt within same-type blocks, fixed vehicle assignment and stops.

    Candidate duration and peak load cannot exceed reconstructed baseline.
    These are relative checks, not certification of an actual fleet's limits.
    """
    nodes, distance, duration = load_freight(case)
    rows = []
    for truck, group in nodes[nodes.index != 0].groupby('Tractor id0'):
        original = list(group.index)
        base = route_metrics(original,nodes,distance,duration)
        best, metrics = original[:], base
        changed = True
        while changed:
            changed = False
            for i in range(len(best)-1):
                for j in range(i+1,len(best)):
                    if nodes.loc[best[i:j+1],'stop_type'].nunique() != 1:
                        continue
                    proposal = best[:i] + best[i:j+1][::-1] + best[j+1:]
                    m = route_metrics(proposal,nodes,distance,duration)
                    if m[0] < metrics[0]-1e-7 and m[1] <= base[1]+1e-7 and m[2] <= base[2]+1e-7:
                        best, metrics, changed = proposal, m, True
                        break
                if changed:
                    break
        for option, order, m in ((0,original,base),(1,best,metrics)):
            arrival = settings.departure_hour + m[1]
            if arrival >= 24:
                raise ValueError('Route returns after the 24-hour scenario; use an earlier departure')
            rows.append(dict(case=case, truck=int(truck), option=option, distance_km=m[0],
                duration_h=m[1], peak_load_source_units=m[2], return_hour=int(arrival),
                stops=len(order), stop_sequence=json.dumps(order), freight_source_doi=FREIGHT_DOI,
                route_provenance='source-row-order reconstruction' if option==0 else '2-opt model output'))
    return pd.DataFrame(rows)


def solve_day(profile, routes, settings, policy):
    """Choose routes and thermal dispatch with a baseline operating-cost cap."""
    settings.validate()
    if policy not in POLICIES:
        raise ValueError('Unknown policy')
    p = profile.sort_values('hour').reset_index(drop=True)
    if len(p) != 24:
        raise ValueError('Expected 24 hours')
    observed = p.observed_lt_power_kw.to_numpy()
    lift = p.ambient_c.to_numpy()+settings.condenser_approach_c-settings.evaporator_c
    if (lift <= 0).any():
        raise ValueError('Nonpositive temperature lift')
    cop = settings.carnot_efficiency*(settings.evaporator_c+273.15)/lift
    q = observed*cop  # inferred heat load, not a measured cooling load
    trucks = sorted(routes.truck.unique().tolist())
    lookup = routes.set_index(['truck','option'])
    base_routes = routes[routes.option.eq(0)]
    heat = settings.dock_heat_kwh_th_per_truck
    base_dock = np.array([heat*sum(base_routes.return_hour.eq(t)) for t in range(24)])
    base_power = observed + base_dock/cop
    # Applies only to modeled low-temperature rack plus synthetic docking load.
    improved_routes = routes[routes.option.eq(1)]
    improved_dock = np.array([heat*sum(improved_routes.return_hour.eq(t)) for t in range(24)])
    improved_direct_power = observed + improved_dock/cop
    # Common assumed equipment rating that can serve both fixed-route plans.
    power_cap = float(max(base_power.max(), improved_direct_power.max())*settings.power_headroom)
    diesel_factor = settings.diesel_litres_per_km*10.21/3.785411784
    base_distance = base_routes.distance_km.sum()
    base_cost = float(base_power.sum()*settings.electricity_cu_per_kwh + base_distance*settings.transport_cu_per_km)
    m = pyo.ConcreteModel()
    m.T = pyo.RangeSet(0,23)
    m.K = pyo.Set(initialize=trucks)
    m.O = pyo.Set(initialize=[0,1])
    m.y = pyo.Var(m.K,m.O,domain=pyo.Binary)
    m.power = pyo.Var(m.T,bounds=(0,power_cap))
    capacity = settings.buffer_kwh_th if policy in ('storage','combined') else 0.0
    m.buffer = pyo.Var(m.T,bounds=(0,capacity))
    m.choose = pyo.Constraint(m.K,rule=lambda m,k: sum(m.y[k,o] for o in m.O)==1)
    if policy != 'combined':
        choice = 1 if policy=='transport' else 0
        for k in trucks:
            m.y[k,choice].fix(1);m.y[k,1-choice].fix(0)
    def balance(m,t):
        previous = m.buffer[t-1] if t else 0.0
        dock = heat*sum(m.y[k,o] for k in trucks for o in (0,1) if lookup.loc[(k,o),'return_hour']==t)
        return m.buffer[t] == (1-settings.hourly_loss)*previous + cop[t]*m.power[t] - q[t] - dock
    m.balance = pyo.Constraint(m.T,rule=balance)
    m.end = pyo.Constraint(expr=m.buffer[23]==0)
    distance_expr = sum(float(lookup.loc[(k,o),'distance_km'])*m.y[k,o] for k in trucks for o in (0,1))
    cost_expr = sum(m.power[t]*settings.electricity_cu_per_kwh for t in range(24)) + distance_expr*settings.transport_cu_per_km
    # Independent transport ablation is reported even if operating cost rises.
    if policy in ('storage','combined'):
        m.budget = pyo.Constraint(expr=cost_expr <= base_cost+1e-7)
    m.objective = pyo.Objective(expr=sum(m.power[t]*settings.grid_kg_co2_per_kwh for t in range(24)) + distance_expr*diesel_factor)
    solver = Highs();solver.config.time_limit=15
    solver.solve(m)
    power = np.array([pyo.value(m.power[t]) for t in range(24)])
    buffer = np.array([pyo.value(m.buffer[t]) for t in range(24)])
    chosen = pd.DataFrame([lookup.loc[(k,int(pyo.value(m.y[k,1])>.5))].to_dict() | {'truck':k,'option':int(pyo.value(m.y[k,1])>.5)} for k in trucks])
    dock = np.array([heat*sum(chosen.return_hour.eq(t)) for t in range(24)])
    residual = buffer-(1-settings.hourly_loss)*np.r_[0,buffer[:-1]]-cop*power+q+dock
    km = chosen.distance_km.sum()
    cost = float(power.sum()*settings.electricity_cu_per_kwh + km*settings.transport_cu_per_km)
    if np.max(np.abs(residual))>1e-5 or buffer.min() < -1e-5 or buffer.max()>capacity+1e-5 or abs(buffer[-1])>1e-5 or power.min() < -1e-5 or power.max()>power_cap+1e-5:
        raise ValueError('Independent thermal-balance audit failed')
    if policy in ('storage','combined') and cost > base_cost+1e-5:
        raise ValueError('Independent budget audit failed')
    hourly = p.copy()
    hourly['policy'] = policy
    hourly['inferred_cop'] = cop
    hourly['inferred_heat_load_kwh_th'] = q
    hourly['synthetic_dock_heat_kwh_th'] = dock
    hourly['modeled_electricity_kwh'] = power
    hourly['modeled_buffer_kwh_th'] = buffer
    hourly['assumed_power_limit_kw'] = power_cap
    hourly['electricity_co2_kg'] = power*settings.grid_kg_co2_per_kwh
    hourly['balance_error_kwh_th'] = residual
    hourly['grid_factor_kg_co2_per_kwh'] = settings.grid_kg_co2_per_kwh
    hourly['result_provenance'] = 'hypothetical cross-source model output; not measured savings'
    row = dict(policy=policy, source_date=p.source_date.iloc[0], cold_source_file=p.source_file.iloc[0],
        case=int(routes.case.iloc[0]), source_samples=int(p.samples.sum()),
        observed_lt_profile_kwh=float(observed.sum()), refrigeration_kwh=float(power.sum()),
        cold_co2_kg=float(power.sum()*settings.grid_kg_co2_per_kwh),
        distance_km=float(km), transport_co2_kg=float(km*diesel_factor),
        total_co2_kg=float(power.sum()*settings.grid_kg_co2_per_kwh+km*diesel_factor),
        electricity_cost_cu=float(power.sum()*settings.electricity_cu_per_kwh),
        transport_cost_cu=float(km*settings.transport_cu_per_km), total_cost_cu=cost,
        served_stops=int(chosen.stops.sum()), trucks=len(chosen), ending_buffer_kwh_th=float(buffer[-1]),
        thermal_balance_max_error=float(np.abs(residual).max()), audit_passed=True,
        cold_source_doi=COLD_DOI, freight_source_doi=FREIGHT_DOI,
        join_type='scenario mapping; unrelated businesses, dates and geographies',
        result_type='modeled counterfactual', settings_json=json.dumps(asdict(settings),sort_keys=True))
    return row,hourly,chosen


def run_study(case=1, settings=Settings()):
    measurements = load_cold_measurements()
    profiles = hourly_profiles(measurements)
    routes = route_candidates(case,settings)
    daily,hourly,selected = [],[],[]
    for source,profile in profiles.groupby('source_file'):
        for policy in POLICIES:
            row,h,r = solve_day(profile,routes,settings,policy)
            daily.append(row);h['case']=case;hourly.append(h)
            r['source_date']=row['source_date'];r['policy']=policy;selected.append(r)
    daily = pd.DataFrame(daily).sort_values(['source_date','policy'])
    bases = daily[daily.policy.eq('baseline')].set_index('source_date')
    for key,label in [('total_co2_kg','carbon'),('total_cost_cu','cost')]:
        baseline = daily.source_date.map(bases[key])
        daily[f'{label}_saved'] = baseline-daily[key]
        daily[f'{label}_reduction_pct'] = np.where(baseline>0,100*(baseline-daily[key])/baseline,np.nan)
    return daily,pd.concat(hourly,ignore_index=True),routes,pd.concat(selected,ignore_index=True),measurements


def export_study(case=1, settings=Settings()):
    daily,hourly,routes,selected,measurements=run_study(case,settings)
    OUT.mkdir(parents=True,exist_ok=True)
    for name,frame in [('integrated_daily',daily),('integrated_hourly',hourly),('route_candidates',routes),('selected_routes',selected),('cold_measurements',measurements)]:
        frame.to_csv(OUT/f'{name}.csv',index=False)
    (OUT/'study_manifest.json').write_text(json.dumps(dict(case=case,settings=asdict(settings),
        measured_rows=len(measurements),source_files=6,optimized_profile_count=3,
        source_dates=sorted(daily.source_date.unique()),
        results='Modeled counterfactuals, not deployed savings',
        scope='Low-temperature rack electricity + modeled diesel combustion; synthetic docking load',
        excluded='Other refrigeration/HVAC, refrigerant leakage, upstream/lifecycle emissions, retrofit capital cost, product spoilage',
        algorithms=['2-opt within same-type stop blocks','Pyomo/HiGHS MILP, thermal-inventory balance, route-choice binary, baseline cost cap']),indent=2))
    return daily

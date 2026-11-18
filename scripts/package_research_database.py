"""Publish compact review files and an independent, complete source archive."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/research_database'


def main():
    c=sqlite3.connect(f'file:{OUT / "sustainable_inventory.sqlite"}?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    source_files=[dict(r) for r in c.execute('SELECT * FROM source_files')]
    schema=';\n\n'.join(r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"))+';\n'
    (OUT/'schema.sql').write_text(schema)
    shutil.copyfile(ROOT/'docs/RESEARCH_DATABASE.md',OUT/'README.md')
    (OUT/'queries.sql').write_text('''-- Inspect source evidence and synthetic assumptions.
SELECT source_id,title,evidence_type,limitation FROM sources;
SELECT * FROM optimization_factors;
SELECT * FROM scenario_parameters;
-- Twelve baseline months: these are scenario values, not measured savings.
SELECT month,scenario_days,baseline_energy_kwh,transport_kgco2,inbound_kgco2,
       baseline_storage_kgco2,operational_kgco2e_partial_scope,operating_cost_cu
FROM baseline_monthly ORDER BY month;
-- Trace every load hour back to a source record, preserving missingness.
SELECT h.timestamp,h.profile_method,h.source_power_value,h.profile_value_used,
       v.file_id,v.source_row,v.refrigeration
FROM hourly_inputs h LEFT JOIN vtt_power_observations v
  ON h.source_record_id=v.record_id ORDER BY h.timestamp;
-- Trace generated orders to real-operation-derived stop cases.
SELECT o.order_id,o.demand_kg,n.case_id,n.node_id,n.weight_source,n.city
FROM orders o JOIN logistics_nodes n ON o.source_node_key=n.node_key LIMIT 100;
-- Optimisation-ready hourly joins (temperature/capacity and carbon/cost).
SELECT * FROM optimization_hourly WHERE date='2018-04-01';
''')
    c.close()
    archives=[]
    small=ROOT/'outputs/research_database_review.zip'
    with zipfile.ZipFile(small,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and p.suffix not in ('.log',) and '.building.' not in p.name:
                z.write(p,str(p.relative_to(OUT)))
    archives.append(small)
    full=ROOT/'outputs/research_database_original_sources.zip'
    with zipfile.ZipFile(full,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for entry in source_files:
            p=ROOT/entry['path']
            z.write(p,entry['path'])
        for p in sorted((ROOT/'data/research/combined_sources').glob('*manifest.json')):
            z.write(p,str(p.relative_to(ROOT)))
        for p in [ROOT/'data/research/combined_sources/ornl_metadata.json',ROOT/'data/research/combined_sources/vtt_files2.txt',OUT/'csv/source_files.csv',OUT/'README.md']:
            z.write(p,str(p.relative_to(ROOT)))
    archives.append(full)
    result=[]
    for p in archives:
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
            count=len(z.namelist())
        result.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,files=count,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        print(result[-1],flush=True)
    (OUT/'package_checksums.json').write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()

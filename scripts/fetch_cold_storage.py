"""Download published MultiPACK text data, preserving bytes and source checksums."""
from pathlib import Path
import datetime
import hashlib
import json
import urllib.request

folder=Path(__file__).resolve().parents[1]/'data/research/cold_storage/multipack'
folder.mkdir(parents=True,exist_ok=True)
url='https://dataverse.no/api/datasets/:persistentId/?persistentId=doi:10.18710/T5OHPR'
with urllib.request.urlopen(url,timeout=45) as response:
    metadata=json.load(response)
(folder/'metadata.json').write_text(json.dumps(metadata,indent=2))
manifest=[]
for entry in metadata['data']['latestVersion']['files']:
    f=entry['dataFile'];name=f['filename']
    if not name.endswith('.txt'):continue
    source=f"https://dataverse.no/api/access/datafile/{f['id']}"
    destination=folder/name
    if destination.exists():
        payload=destination.read_bytes()
    else:
        with urllib.request.urlopen(source,timeout=45) as response:payload=response.read()
    if hashlib.md5(payload).hexdigest()!=f['checksum']['value']:
        raise ValueError(f'Checksum mismatch: {name}')
    destination.write_bytes(payload)
    manifest.append(dict(file=name,url=source,md5=f['checksum']['value'],sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload),verified_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print(f'Verified {name}',flush=True)
(folder/'download_manifest.json').write_text(json.dumps(manifest,indent=2))

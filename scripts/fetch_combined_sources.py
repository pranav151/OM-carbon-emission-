"""Download public ORNL files byte-for-byte; never execute provider code."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/research/combined_sources'


def download(entry):
    destination = BASE / 'ornl' / entry['name']
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = entry['computed_md5']
    if not destination.exists() or hashlib.md5(destination.read_bytes()).hexdigest() != expected:
        temporary = destination.with_suffix(destination.suffix + '.part')
        with urllib.request.urlopen(entry['download_url'], timeout=90) as response, temporary.open('wb') as f:
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
        assert hashlib.md5(temporary.read_bytes()).hexdigest() == expected, entry['name']
        temporary.replace(destination)
    payload = destination.read_bytes()
    print('Verified', destination.name, len(payload), flush=True)
    return dict(source_id='ornl', path=str(destination.relative_to(ROOT)),
                url=entry['download_url'], md5=expected,
                sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
                retrieved_at_utc=datetime.now(timezone.utc).isoformat())


if __name__ == '__main__':
    BASE.mkdir(parents=True,exist_ok=True)
    metadata_path=BASE/'ornl_metadata.json'
    if not metadata_path.exists():
        with urllib.request.urlopen('https://api.figshare.com/v2/articles/13232627',timeout=45) as response:
            metadata_path.write_bytes(response.read())
    vtt_metadata=BASE/'vtt_files2.txt'
    if not vtt_metadata.exists():
        req=urllib.request.Request('https://data.mendeley.com/public-api/datasets/myyf72mpw9/files?folder_id=root&version=1',headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=45) as response:vtt_metadata.write_bytes(response.read())
    vtt_manifest=[]
    for entry in json.loads(vtt_metadata.read_text()):
        detail=entry['content_details'];p=BASE/'vtt'/entry['filename'];p.parent.mkdir(exist_ok=True)
        if not p.exists():
            req=urllib.request.Request(detail['download_url'],headers={'User-Agent':'Mozilla/5.0','Referer':'https://data.mendeley.com/datasets/myyf72mpw9/1','Accept':'*/*'})
            with urllib.request.urlopen(req,timeout=60) as response:p.write_bytes(response.read())
        payload=p.read_bytes();assert hashlib.sha256(payload).hexdigest()==detail['sha256_hash'],p
        vtt_manifest.append(dict(source_id='vtt',path=str(p.relative_to(ROOT)),url=detail['download_url'],sha256=detail['sha256_hash'],bytes=len(payload),retrieved_at_utc=datetime.now(timezone.utc).isoformat()))
        print('Verified',p.name,flush=True)
    (BASE/'vtt_manifest.json').write_text(json.dumps(vtt_manifest,indent=2))
    metadata = json.loads((BASE / 'ornl_metadata.json').read_text())
    with ThreadPoolExecutor(max_workers=3) as pool:
        manifest = list(pool.map(download, metadata['files']))
    (BASE / 'ornl_manifest.json').write_text(json.dumps(manifest, indent=2))

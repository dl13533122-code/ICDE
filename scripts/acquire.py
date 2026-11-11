"""Atomic streamed primary-source retrieval with durable success/failure provenance."""
import argparse, datetime, hashlib, json, pathlib, subprocess, time

def acquire(url, target, landing=None, license_status='consult landing', expected_bytes=None):
    p = pathlib.Path(target); p.parent.mkdir(parents=True, exist_ok=True)
    metadata = {'source_landing_url': landing or url, 'download_url': url, 'retrieval_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'license_status': license_status, 'expected_bytes': expected_bytes, 'path': str(p)}
    if p.exists():
        metadata['already_present'] = True
    else:
        tmp = pathlib.Path(str(p) + '.part'); headers = pathlib.Path(str(p) + '.headers')
        cmd = ['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2', '--connect-timeout', '15', '--max-time', '600', '--continue-at', '-', '--dump-header', str(headers), '--output', str(tmp), url]
        r = subprocess.run(cmd, capture_output=True, text=True)
        metadata.update(command=cmd, exit_status=r.returncode, stderr=r.stderr)
        if r.returncode == 0:
            if expected_bytes is not None and tmp.stat().st_size != expected_bytes:
                metadata['error'] = 'length mismatch'
            elif p.suffix == '.pdf' and not tmp.open('rb').read(5).startswith(b'%PDF'):
                metadata['error'] = 'not a PDF'
            else: tmp.rename(p)
        else: metadata['error'] = 'retrieval failed'
        metadata['headers_path'] = str(headers)
    if p.exists():
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
        metadata.update(observed_bytes=p.stat().st_size, sha256=h.hexdigest(), status='OBSERVED')
    else: metadata.update(status='BLOCKED', partial_bytes=pathlib.Path(str(p)+'.part').stat().st_size if pathlib.Path(str(p)+'.part').exists() else 0)
    pathlib.Path(str(p)+'.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps(metadata), flush=True)
    return metadata

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('target');p.add_argument('--landing');p.add_argument('--license', default='consult landing');p.add_argument('--expected-bytes',type=int);a=p.parse_args()
    acquire(a.url,a.target,a.landing,a.license,a.expected_bytes)

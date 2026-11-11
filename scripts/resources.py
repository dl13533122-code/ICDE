"""Read-only local/explicit-alias inventory, never a host scan."""
import argparse, datetime, json, os, pathlib, subprocess

def snapshot():
    result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'hostname': os.uname().nodename}
    for name, command in {
        'cpu': ['lscpu', '-J'], 'load': ['uptime'], 'ram': ['free', '-b'],
        'disk': ['df', '-B1', '.'], 'identity': ['cat', '/etc/machine-id'],
        'gpu': ['nvidia-smi', '--query-gpu=name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'],
        'cgroup': ['cat', '/proc/self/cgroup'],
    }.items():
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=15)
            result[name] = {'command': command, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}
        except (OSError, subprocess.TimeoutExpired) as e:
            result[name] = {'command': command, 'error': str(e)}
    import hashlib
    result['physical_identity_sha256'] = hashlib.sha256(result['identity']['stdout'].encode()).hexdigest()
    del result['identity']
    result['limits'] = {}
    bases = ['/sys/fs/cgroup', '/sys/fs/cgroup/system.slice/server-history-codex.service']
    for line in result.get('cgroup', {}).get('stdout', '').splitlines():
        if line.startswith('0::'):
            current = pathlib.Path('/sys/fs/cgroup') / line[3:].lstrip('/')
            while str(current).startswith('/sys/fs/cgroup'):
                bases.append(str(current))
                if str(current) == '/sys/fs/cgroup': break
                current = current.parent
    for base in dict.fromkeys(bases):
        for name in ['memory.max', 'memory.current', 'memory.events', 'cpu.max']:
            p = pathlib.Path(base) / name
            result['limits'][str(p)] = p.read_text().strip() if p.exists() else 'UNAVAILABLE'
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output'); p.add_argument('--alias', choices=['fy1', 'desktop125', 'dgx-theta', 'dgx-spark-ebaf'])
    args = p.parse_args()
    if args.alias:
        source = pathlib.Path(__file__).read_text()
        command = ['ssh', '-F', '/home/fu/.ssh/config', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1', args.alias, 'python3 -']
        r = subprocess.run(command, input=source, text=True, capture_output=True, timeout=45)
        out = {'alias': args.alias, 'command': command, 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
    else:
        out = snapshot()
    data = json.dumps(out, indent=2) + '\n'
    if args.output: pathlib.Path(args.output).write_text(data)
    else: print(data)

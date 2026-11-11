"""Count SSH ciphertext on the existing alias route; never store payloads.

desktop125 uses the same hostname/port resolved by standard authenticated SSH.
Its configuration must have no proxy; metering cannot bypass one. The old fy1
mode remains available for historical driver compatibility only.
"""
import json, os, pathlib, signal, socket, subprocess, sys, threading


def standard_endpoint(alias):
    if alias != 'desktop125':
        raise ValueError('unapproved direct-meter alias')
    p = subprocess.run(['ssh', '-F', '/home/fu/.ssh/config', '-G', alias],
                       capture_output=True, text=True, check=True)
    values = dict(line.split(' ', 1) for line in p.stdout.splitlines() if ' ' in line)
    if values.get('proxycommand', 'none') != 'none' or values.get('proxyjump', 'none') != 'none':
        raise ValueError('configured proxy present; direct metering refused')
    return values['hostname'], int(values['port'])


def main():
    output = pathlib.Path(sys.argv[1])
    alias = sys.argv[2] if len(sys.argv) > 2 else 'fy1'
    child = None
    if alias == 'desktop125':
        host, port = standard_endpoint(alias)
        transport = socket.create_connection((host, port), timeout=10)
        transport.settimeout(None)
        reader = transport.fileno()
        send_bytes = transport.sendall
        close_write = lambda: transport.shutdown(socket.SHUT_WR)
        route = dict(alias=alias, hostname=host, port=port,
                     route='standard alias endpoint; configured proxy absent')
    elif alias == 'fy1':
        child = subprocess.Popen(['/home/fu/.local/bin/ssh-mesh-proxy', 'fy1', '22'],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr)
        reader = child.stdout.fileno()
        def send_bytes(b):
            child.stdin.write(b); child.stdin.flush()
        close_write = child.stdin.close
        route = dict(alias=alias, route='historical configured ssh-mesh-proxy')
    else:
        raise ValueError('unapproved meter alias')
    counts = dict(ssh_ciphertext_tx_bytes=0, ssh_ciphertext_rx_bytes=0)
    lock = threading.Lock()
    finalized = threading.Event()

    def persist(status):
        with lock:
            if finalized.is_set():
                return
            value = dict(counts, status=status, route=route,
                         scope='outer SSH ciphertext payload, both directions; excludes TCP/IP/L2',
                         cutoff='completed trials and positively owned cleanup; before transport shutdown'
                         if status == 'OBSERVED' else None)
            tmp = pathlib.Path(str(output)+'.tmp')
            tmp.write_text(json.dumps(value))
            os.replace(tmp, output)
            if status == 'OBSERVED':
                finalized.set()

    persist('IN_PROGRESS')
    pathlib.Path(str(output)+'.owner.json').write_text(json.dumps(dict(
        relay_pid=os.getpid(), proxy_child_pid=child.pid if child else None, output=str(output), route=route)))

    def finish(signum, frame):
        persist('OBSERVED')
        if child and child.poll() is None:
            child.terminate()
        elif not child:
            transport.close()

    signal.signal(signal.SIGTERM, finish)

    def finalize_request():
        while not finalized.is_set():
            if pathlib.Path(str(output)+'.finalize_request').exists():
                persist('OBSERVED'); return
            finalized.wait(.05)

    def send():
        try:
            while True:
                b = os.read(0, 65536)
                if not b:
                    break
                send_bytes(b)
                with lock:
                    if not finalized.is_set():
                        counts['ssh_ciphertext_tx_bytes'] += len(b)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                close_write()
            except OSError:
                pass

    threading.Thread(target=finalize_request, daemon=True).start()
    sender = threading.Thread(target=send, daemon=True); sender.start()
    try:
        while True:
            b = os.read(reader, 65536)
            if not b:
                break
            with lock:
                if not finalized.is_set():
                    counts['ssh_ciphertext_rx_bytes'] += len(b)
            persist('IN_PROGRESS')
            off = 0
            while off < len(b):
                off += os.write(1, b[off:])
    except OSError:
        if not finalized.is_set():
            raise
    finally:
        persist('OBSERVED')
        if child:
            child.wait(timeout=10)
        else:
            transport.close()


if __name__ == '__main__':
    main()

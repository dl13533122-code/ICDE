#!/usr/bin/env python3
"""Fu-only one-use control of the accepted publication overlay and FY plots.

The reviewed worker performs all summary arithmetic and rendering on FY. Fu
only binds sources/inputs, transfers the four-file input archive, observes the
frozen bounded wrapper and collects thirteen explicitly allowed output files.
All previous summaries, figures and experimental records remain unchanged.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tarfile
import time

HELPER_SHA = '0037b8b3efd58749665f5f8e7c06a81ef4baf7a331efebadec21f7625b430b49'
TRANSPORT_SHA = '0ac3ceab0cb085a61646a6d8afc334fd8b1b7bc1f19da11fee4ebe352f3d053e'
BASE_SUMMARY_SHA = '189fe0b955942b1ec2fec04d60f83764cef83904ee1d1c7eb37cb925a4c3021d'
OVERLAY_SHA = 'dcf757918a86e82f5af50f9076c179fe99228cb07ea64730a88ca2a8b4ede50b'
PLOT_SHA = '6cdfebf0a65feaeb4b1ce00a58262522137a0368bb32218c72c09755460afccd'
SUMMARIZER_SHA = '3a62acc0ef47293ace98f40ea122a1bf4572cc2e19ebfa5f247215935fe201e2'
MANIFEST_SHA = '9224428df5063d6d5fc13be6b4578318e5a4fbedbb56122492168f65a13181d4'
FY = '/home/fy/icde02_revision_20261110'
ROOT = FY + '/publication20261110'
IDS = ('C-n1024-range-s1301-r0', 'C-n1024-mixed-s1301-r0')
NAMES = ('activation', 'local_gap', 'scale', 'grouping', 'finite_utility')
OUTPUTS = {'analysis/summary.json', 'publication_receipt.json', 'figures/figure_manifest.json'} | {
    'figures/' + name + '.' + extension for name in NAMES for extension in ('pdf', 'png')}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def checked_helpers(post):
    transport = post / 'plot_refresh_v2.py'; helper = post / 'postprocess_dispatch.py'
    if sha(transport) != TRANSPORT_SHA or sha(helper) != HELPER_SHA:
        raise ValueError('Reviewed transport/helper source differs')
    spec = importlib.util.spec_from_file_location('checked_publication_transport', transport)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if sha(Path(module.ctl.__file__)) != HELPER_SHA: raise ValueError('Imported helper source differs')
    return module, module.ctl


LAUNCH = r'''import hashlib,json,os,pathlib,subprocess,sys,time
p=pathlib.Path(sys.argv[1]);base=pathlib.Path(sys.argv[2]);intent=json.loads(sys.argv[3])
def sha(q):
 h=hashlib.sha256()
 with q.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
bound=((base/'analysis20261110/output/analysis/summary.json','base_summary_sha256'),
 (base/'analysis20261110/scripts/summarize_results.py','summary_script_sha256'),
 (p/'publish_results_v3.py','worker_sha256'),(p/'plot_results_v3.py','plot_sha256'),
 (p/'inputs.tar','input_archive_sha256'),(base/'FROZEN_MANIFEST.json','manifest_sha256'),
 (base/'revision_src/bounded_exec.py','wrapper_sha256'),(base/'SCIENCE_DEADLINE.json','deadline_sha256'))
for path,key in bound:
 if path.is_symlink() or sha(path)!=intent[key]:raise ValueError('Bound source/input differs: '+key)
timing=json.loads((base/'SCIENCE_DEADLINE.json').read_text())
if timing['science_budget_seconds']!=43200 or timing['deadline_epoch']!=intent['deadline_epoch'] or timing['deadline_epoch']-timing['first_validation_dispatch_epoch']!=43200:raise ValueError('Original deadline differs')
if time.time()>=timing['deadline_epoch']:raise TimeoutError('Unchanged scientific deadline reached')
env=dict(os.environ)
for key in ('ICDE_THREADS','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):env[key]='8'
py=str(base/'venv/bin/python');command=[py,str(base/'revision_src/bounded_exec.py'),'--rss-gib','16','--reserve-gib','2','--deadline-file',str(base/'SCIENCE_DEADLINE.json'),'--receipt',str(p/'receipt.json'),'--',py,str(p/'publish_results_v3.py'),'--root',str(p),'--base',str(base)]
with (p/'launch_intent.json').open('x') as f:json.dump(dict(intent,command=command),f,sort_keys=True);f.flush();os.fsync(f.fileno())
with (p/'worker.log').open('xb',buffering=0) as log:
 child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
 owner={'pid':child.pid,'start_ticks':None}
 try:owner['start_ticks']=int((pathlib.Path('/proc')/str(child.pid)/'stat').read_text().rsplit(') ',1)[1].split()[19])
 except FileNotFoundError:pass
 with (p/'pid.json').open('x') as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
 print(json.dumps(owner))
'''


COLLECTION = r'''import hashlib,json,pathlib,sys,tarfile
p=pathlib.Path(sys.argv[1]);base=pathlib.Path(sys.argv[2]);intent=json.loads((p/'launch_intent.json').read_text());out=p/'output'
def sha(q):
 h=hashlib.sha256()
 with q.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
owner=json.loads((p/'pid.json').read_text());ticks=owner.get('start_ticks')
if ticks is None:raise ValueError('Wrapper process ownership was not recorded')
try:
 fields=(pathlib.Path('/proc')/str(owner['pid'])/'stat').read_text().rsplit(') ',1)[1].split()
 if int(fields[19])==ticks and fields[0]!='Z':raise ValueError('Owned bounded wrapper remains live')
except FileNotFoundError:pass
receipt=json.loads((p/'receipt.json').read_text())
if receipt.get('exit_code')!=0 or receipt.get('termination_reason') is not None or receipt.get('owned_group_cleanup',{}).get('drained') is not True:raise ValueError('Publication did not close successfully')
for q,key in ((base/'analysis20261110/output/analysis/summary.json','base_summary_sha256'),
 (base/'analysis20261110/scripts/summarize_results.py','summary_script_sha256'),
 (p/'publish_results_v3.py','worker_sha256'),(p/'plot_results_v3.py','plot_sha256'),
 (p/'inputs.tar','input_archive_sha256'),(base/'FROZEN_MANIFEST.json','manifest_sha256'),
 (base/'SCIENCE_DEADLINE.json','deadline_sha256'),(base/'revision_src/bounded_exec.py','wrapper_sha256')):
 if sha(q)!=intent[key]:raise ValueError('Source/input changed during publication: '+key)
for name,digest in intent['input_files_sha256'].items():
 if sha(p/'inputs'/name)!=digest:raise ValueError('Worker input differs: '+name)
names={'activation','local_gap','scale','grouping','finite_utility'}
allowed={'analysis/summary.json','publication_receipt.json','figures/figure_manifest.json'}|{'figures/'+n+'.'+e for n in names for e in ('pdf','png')}
if {str(q.relative_to(out)) for q in out.rglob('*') if q.is_file()}!=allowed or any(q.is_symlink() for q in out.rglob('*')):raise ValueError('Unexpected publication output')
publication=json.loads((out/'publication_receipt.json').read_text())
if publication.get('state')!='COMPLETED' or publication.get('new_optimizer_or_trial_runs')!=0:raise ValueError('Unexpected publication scope or state')
for key in ('base_summary_sha256','overlay_sha256','acceptance_sha256','worker_sha256','plot_sha256','summary_script_sha256','deadline_epoch'):
 if publication[key]!=intent[key]:raise ValueError('Publication receipt binding differs: '+key)
if publication['finished_epoch']>intent['deadline_epoch'] or publication['summary_sha256']!=sha(out/'analysis/summary.json'):raise ValueError('Publication summary/deadline differs')
if len(publication['cases'])!=2 or {r['case_id'] for r in publication['cases']}!={'C-n1024-range-s1301-r0','C-n1024-mixed-s1301-r0'}:raise ValueError('Publication case denominator differs')
manifest=json.loads((out/'figures/figure_manifest.json').read_text())
if manifest['summary_sha256']!=publication['summary_sha256'] or manifest['script_sha256']!=intent['plot_sha256']:raise ValueError('Figure source/input binding differs')
if len(manifest['figures'])!=5 or {f['figure'] for f in manifest['figures']}!=names:raise ValueError('Figure set differs')
for figure in manifest['figures']:
 expected={figure['figure']+'.pdf',figure['figure']+'.png'};seen=set()
 if len(figure['files'])!=2:raise ValueError('Figure formats incomplete')
 for item in figure['files']:
  q=pathlib.Path(item['path'])
  if q.parent!=out/'figures' or q.name not in expected or q.is_symlink() or sha(q)!=item['sha256']:raise ValueError('Figure file binding differs')
  seen.add(q.name)
 if seen!=expected:raise ValueError('Figure format set differs')
files={name:sha(out/name) for name in sorted(allowed)};archive=p/'output.tar'
with tarfile.open(archive) as package:
 members=package.getmembers()
 if len(members)!=len(allowed) or {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise ValueError('Output archive allowlist differs')
 for member in members:
  h=hashlib.sha256()
  with package.extractfile(member) as f:
   for b in iter(lambda:f.read(1048576),b''):h.update(b)
  if h.hexdigest()!=files[member.name]:raise ValueError('Archive member differs from checked output')
print(json.dumps(dict(archive=str(archive),archive_sha256=sha(archive),output_files_sha256=files,
 receipt=receipt,receipt_sha256=sha(p/'receipt.json'),publication_receipt=publication)))
'''


def run(revision, worker_sha, acceptance_sha, checked, ctl):
    post = revision / 'postprocess'; destination = revision / 'publication_v3_collected'
    worker = post / 'publish_results_v3.py'; plot = post / 'plot_results_v3.py'
    acceptance_path = post / 'uniform_precision_acceptance.json'
    overlay_root = revision / 'uniform_precision4096'
    for path in (destination, revision / 'analysis_v3', revision / 'figures_revision_v3',
                 post / 'publication_refresh_output.tar', post / 'publication_refresh_inputs.tar',
                 post / 'publication_receipt_v3.json'):
        if path.exists(): raise FileExistsError('Version-three destination exists; reconcile: ' + str(path))
    for path, expected in ((worker, worker_sha), (plot, PLOT_SHA), (acceptance_path, acceptance_sha),
                           (overlay_root / 'overlay.pending.json', OVERLAY_SHA),
                           (revision / 'analysis/summary.json', BASE_SUMMARY_SHA),
                           (post / 'summarize_results.py', SUMMARIZER_SHA),
                           (revision / 'FROZEN_MANIFEST.json', MANIFEST_SHA)):
        if path.is_symlink() or sha(path) != expected: raise ValueError('Local source/input differs: ' + str(path))
    timing_path = revision / 'SCIENCE_DEADLINE.json'; timing = read(timing_path); deadline = timing['deadline_epoch']
    if (timing['science_budget_seconds'] != 43200 or deadline - timing['first_validation_dispatch_epoch'] != 43200
            or time.time() >= deadline): raise ValueError('Original 12-hour deadline differs or expired')
    manifest = read(revision / 'FROZEN_MANIFEST.json'); wrapper_sha = sha(revision / 'src/bounded_exec.py')
    if wrapper_sha != manifest['source_sha256']['revision_src/bounded_exec.py']: raise ValueError('Frozen wrapper differs')
    acceptance = read(acceptance_path)
    if (acceptance['status'] != 'ACCEPTED' or acceptance['overlay_sha256'] != OVERLAY_SHA
            or acceptance['manifest_file_sha256'] != MANIFEST_SHA
            or acceptance['deadline_sha256'] != sha(timing_path)
            or len(acceptance['cases']) != 2 or {r['case_id'] for r in acceptance['cases']} != set(IDS)):
        raise ValueError('Independent acceptance does not bind the exact experiment and two cases')
    inputs = {'overlay.pending.json': overlay_root / 'overlay.pending.json',
              'uniform_precision_acceptance.json': acceptance_path}
    for case_id in IDS:
        accepted = next(row for row in acceptance['cases'] if row['case_id'] == case_id)
        candidate = overlay_root / case_id / 'candidate.json'
        if accepted['accepted'] is not True or candidate.is_symlink() or sha(candidate) != accepted['candidate_sha256']:
            raise ValueError('Accepted candidate file differs: ' + case_id)
        inputs['cases/' + case_id + '/candidate.json'] = candidate
    input_hashes = {name: sha(path) for name, path in inputs.items()}
    archive = post / 'publication_refresh_inputs.tar'
    with tarfile.open(archive, 'x') as package:
        for name in sorted(inputs): package.add(inputs[name], arcname=name, recursive=False)
    if any(sha(path) != input_hashes[name] for name, path in inputs.items()): raise ValueError('Inputs changed during packaging')
    intent = dict(base_summary_sha256=BASE_SUMMARY_SHA, overlay_sha256=OVERLAY_SHA,
        acceptance_sha256=acceptance_sha, worker_sha256=worker_sha, plot_sha256=PLOT_SHA,
        summary_script_sha256=SUMMARIZER_SHA, manifest_sha256=MANIFEST_SHA,
        deadline_sha256=sha(timing_path), deadline_epoch=deadline, wrapper_sha256=wrapper_sha,
        input_archive_sha256=sha(archive), input_files_sha256=input_hashes,
        controller_sha256=sha(__file__), transport_sha256=TRANSPORT_SHA,
        helper_sha256=HELPER_SHA, remote_root=ROOT, remote_base=FY,
        thread_limit=8, resident_limit_gib=16, reserve_gib=2, new_optimizer_or_trial_runs=0)
    ctl.write(post / 'publication_refresh_bindings.json', intent, exclusive=True)
    transport = checked.Transport(post / 'publication_refresh_transport')
    transport.remote('fy', ['python3', '-c', 'import pathlib,sys;pathlib.Path(sys.argv[1]).mkdir(parents=True,exist_ok=False)', ROOT])
    for source, name in ((worker, 'publish_results_v3.py'), (plot, 'plot_results_v3.py'), (archive, 'inputs.tar')):
        transport.copy('fy', source, ROOT + '/' + name)
    try:
        response = transport.remote('fy', [FY + '/venv/bin/python', '-c', LAUNCH, ROOT, FY,
                                            json.dumps(intent, separators=(',', ':'))])
        ctl.write(post / 'publication_refresh_launch.json', json.loads(response.stdout), exclusive=True)
    except checked.AccessRefusal: raise
    except Exception as error:
        ctl.write(post / 'publication_refresh_launch_uncertain.json',
                  dict(error=str(error), remote_root=ROOT, automatic_relaunch=False), exclusive=True)
    failures = inactive = 0; receipt = None; snapshot = None
    while time.time() < deadline + 600:
        try:
            snapshot = json.loads(transport.remote('fy', ['python3', '-c', checked.SNAPSHOT, ROOT], timeout=30).stdout)
            failures = 0; ctl.write(post / 'publication_refresh_remote_status.json', snapshot)
            receipt = snapshot.get('receipt')
            if receipt is not None and snapshot.get('owner_alive') is False: break
            inactive = inactive + 1 if snapshot.get('owner') is None or snapshot.get('owner_alive') is False else 0
            if inactive >= 3: raise ctl.Unconfirmed('Publication ownership requires reconciliation', remote_root=ROOT, snapshot=snapshot)
        except (checked.AccessRefusal, ctl.Unconfirmed): raise
        except Exception as error:
            failures += 1
            if failures >= 3: raise ctl.Unconfirmed('FY connection lost; the existing bounded worker may continue', remote_root=ROOT, error=str(error)) from error
        time.sleep(5)
    if (receipt is None or snapshot.get('owner_alive') is not False
            or receipt.get('owned_group_cleanup', {}).get('drained') is not True):
        raise ctl.Unconfirmed('Publication terminal ownership unresolved', remote_root=ROOT, snapshot=snapshot)
    ctl.write(post / 'publication_refresh_bounded_receipt.json', receipt, exclusive=True)
    if receipt.get('exit_code') != 0 or receipt.get('termination_reason') is not None:
        raise RuntimeError('Bounded publication failed; its receipt and FY worker.log remain available')
    try:
        packed = json.loads(transport.remote('fy', ['python3', '-c', COLLECTION, ROOT, FY], timeout=120).stdout)
        if packed['archive'] != ROOT + '/output.tar' or packed['receipt'] != receipt or set(packed['output_files_sha256']) != OUTPUTS:
            raise ValueError('Publication package path, receipt or allowlist differs')
        output_archive = post / 'publication_refresh_output.tar'
        transport.copy('fy', output_archive, packed['archive'], receive=True)
        if sha(output_archive) != packed['archive_sha256']: raise ValueError('Collected archive hash differs')
        with tarfile.open(output_archive) as package:
            members = package.getmembers()
            if len(members) != len(OUTPUTS) or {m.name for m in members} != OUTPUTS or any(not m.isfile() for m in members):
                raise ValueError('Collected archive allowlist differs')
        ctl.unpack(output_archive, destination)
        for name, expected in packed['output_files_sha256'].items():
            if sha(destination / name) != expected: raise ValueError('Collected output file hash differs: ' + name)
        if read(destination / 'publication_receipt.json') != packed['publication_receipt']:
            raise ValueError('Collected publication receipt differs')
        (destination / 'analysis').rename(revision / 'analysis_v3')
        (destination / 'figures').rename(revision / 'figures_revision_v3')
        (destination / 'publication_receipt.json').rename(post / 'publication_receipt_v3.json')
        ctl.write(post / 'publication_refresh_collection.json', packed, exclusive=True)
    except checked.AccessRefusal: raise
    except Exception as error:
        raise ctl.Unconfirmed('Publication completed; version-three collection requires reconciliation', remote_root=ROOT, error=str(error)) from error
    return dict(analysis=str(revision / 'analysis_v3'), figures=str(revision / 'figures_revision_v3'),
        publication_receipt=str(post / 'publication_receipt_v3.json'),
        summary_sha256=packed['publication_receipt']['summary_sha256'], archive_sha256=packed['archive_sha256'],
        overlay_sha256=OVERLAY_SHA, acceptance_sha256=acceptance_sha, worker_sha256=worker_sha,
        ownership_drained=True, new_optimizer_or_trial_runs=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--worker-sha256', required=True); parser.add_argument('--acceptance-sha256', required=True)
    args = parser.parse_args(); revision = args.project.resolve() / 'revision_20261110'; post = revision / 'postprocess'
    for value in (args.worker_sha256, args.acceptance_sha256):
        if not re.fullmatch('[0-9a-f]{64}', value): raise ValueError('Explicit reviewed SHA256 values are required')
    checked, ctl = checked_helpers(post); status_path = post / 'PUBLICATION_REFRESH_STATUS.json'
    if status_path.exists(): raise FileExistsError('Publication status exists; reconcile, never relaunch')
    ctl.write(post / 'PUBLICATION_REFRESH_INTENT.json', dict(started_epoch=time.time(),
        controller_sha256=sha(__file__), worker_sha256=args.worker_sha256,
        acceptance_sha256=args.acceptance_sha256, plot_sha256=PLOT_SHA, remote_root=ROOT), exclusive=True)
    try:
        result = run(revision, args.worker_sha256, args.acceptance_sha256, checked, ctl)
        state = dict(state='COMPLETED', result=result, ownership_drained=True); code = 0
    except checked.AccessRefusal as error:
        state = dict(state='ACCESS_REFUSED', error=str(error), access_refusal=error.details,
                     further_remote_action=False, automatic_relaunch=False); code = 3
    except ctl.Unconfirmed as error:
        state = dict(state='UNCONFIRMED', error=str(error), details=error.details, automatic_relaunch=False); code = 2
    except Exception as error:
        state = dict(state='FAILED', error=type(error).__name__ + ': ' + str(error), automatic_relaunch=False); code = 1
    state['finished_epoch'] = time.time(); ctl.write(status_path, state)
    print(json.dumps(state, sort_keys=True), flush=True); return code


if __name__ == '__main__': sys.exit(main())

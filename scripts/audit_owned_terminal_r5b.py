"""Read-only terminal check for exact manifest identities of this continuation."""
import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TASK='6fa343b11cbf4f1686f225de6f0a43b1'
TAG='intel_certified_partition_finite_r5b'
LOCAL=Path('/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/peers')/TAG
REMOTE='/home/fy1/icde_fuyue_20261005/02_decentralized_private_aggregation'
owner=json.loads((ROOT/'governance/.executor.lock/owner.json').read_text())
assert owner['task_id']==TASK
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def matching(tokens,paths):return any(p.encode() in tokens for p in paths)
local_registered=[]
paths=[]
for ready in sorted((ROOT/f'experiments/protocol/{TAG}/internal').glob('*/output/ready.json')):
    d=json.loads(ready.read_text());cred=str(LOCAL/str(d['id']));paths.append(cred)
    local_registered.append({'ready':str(ready.relative_to(ROOT)), 'sha256':sha(ready),
                             'registered_pid':d['pid'],'exact_credentials':cred})
relay=LOCAL/'ssh_wire.json.owner.json'
relay_info=json.loads(relay.read_text())
paths.append(str(LOCAL/'ssh_byte_meter.py'))
local_live=[]
for p in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        args=p.read_bytes().split(b'\0')
        if matching(args,paths):local_live.append({'pid':int(p.parent.name),'argv':[x.decode(errors='replace') for x in args if x]})
    except (OSError,ProcessLookupError):pass
remote_script='''import json,pathlib
root=pathlib.Path(REMOTE)
base=root/'protocol'/TAG
registered=[];identities=[]
for ready in sorted(base.glob('*/output/ready.json')):
 d=json.loads(ready.read_text());cred=str(ready.parent.parent);identities.append(cred.encode());registered.append({'path':str(ready),'registered_pid':d['pid'],'exact_credentials':cred})
jobs=[]
doppio=root/'Doppio_main_r5b_828d2a6ad2d9'
for name in ['r5b_execution.json','r5b_repair_execution.json']:
 p=doppio/name;d=json.loads(p.read_text());assert d['task_id']==TASK
 identities.append(d['script'].encode());jobs.append(d)
live=[]
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(bytes([0]))
  if any(x in args for x in identities):live.append({'pid':int(p.parent.name),'argv':[x.decode(errors='replace') for x in args if x]})
 except (OSError,ProcessLookupError):pass
print(json.dumps({'registered_peers':registered,'registered_Doppio_jobs':jobs,'exact_identity_live':live,'read_only':True}))
'''
remote_script='REMOTE='+repr(REMOTE)+'\nTAG='+repr(TAG)+'\nTASK='+repr(TASK)+'\n'+remote_script
command=['ssh','-F','/home/fu/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=10','fy1','python3 -']
r=subprocess.run(command,input=remote_script,text=True,capture_output=True,timeout=40)
assert r.returncode==0,(r.returncode,r.stderr)
remote=json.loads(r.stdout)
assert len(remote['registered_peers'])==50
assert all(x['active_child'] is None and x['finished_utc'] for x in remote['registered_Doppio_jobs'])
db=sqlite3.connect('file:/home/fu/.local/state/server-history-codex/jobs.sqlite?mode=ro',uri=True)
db.row_factory=sqlite3.Row
rows=[dict(x) for x in db.execute('select id,request_id,cwd,status,session_id,model,reasoning_effort,resume_pending,finished_at from jobs where cwd=?',(str(ROOT),))]
db.close()
active=[x for x in rows if x['status'] in ['running','queued','pending','starting'] or x['resume_pending']]
assert len(active)==1 and active[0]['id']==TASK,active
assert active[0]['session_id']==owner['thread_id']
assert active[0]['model']=='gpt-6.1-sol' and active[0]['reasoning_effort']=='xhigh'
assert not local_live and not remote['exact_identity_live']
out={'utc':datetime.now(timezone.utc).isoformat(),'task_id':TASK,'read_only':True,
     'manifest':f'experiments/protocol/{TAG}/manifest.json','manifest_sha256':sha(ROOT/f'experiments/protocol/{TAG}/manifest.json'),
     'local_registered':local_registered,'relay_identity':relay_info,'relay_identity_sha256':sha(relay),
     'local_exact_identity_live':local_live,'remote_command':command,'remote_script':remote_script,
     'remote':remote,'remote_returncode':r.returncode,'same_project_active_tasks':active,
     'ownership_rule':'exact registered credential/script argv; PID alone is never ownership; no process was stopped by this audit',
     'owned_science_commands_terminal':True,'other_project_queries':False}
(ROOT/'evidence/final_owned_terminal_audit_r5b.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'local_peers':len(local_registered),'remote_peers':len(remote['registered_peers']),
                  'Doppio_wrappers':len(remote['registered_Doppio_jobs']),'live_exact_matches':0,
                  'owned_science_commands_terminal':True,'same_project_writers':[x['id'] for x in active]}))

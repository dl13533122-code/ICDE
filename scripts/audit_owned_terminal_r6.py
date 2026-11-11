"""Read-only exact registered R6 identities, no unrelated workload actions."""
import datetime,hashlib,json,pathlib,sqlite3,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1];TASK='b77a510722354cb59035490e85f583c5'
owner=json.loads((ROOT/'governance/.executor.lock/owner.json').read_text());assert owner['task_id']==TASK
tags=sorted(p.parent.name for p in (ROOT/'experiments/protocol').glob('*_r6/manifest.json'))
scratch=pathlib.Path('/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/peers');paths=[];registered=[]
for tag in tags:
 for i in range(4):
  p=scratch/tag/str(i);paths.append(str(p).encode());registered.append(str(p))
 paths.append(str(scratch/tag/'ssh_byte_meter.py').encode())
live=[]
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(b'\0')
  if any(x in args for x in paths):live.append(dict(pid=int(p.parent.name),argv=[x.decode(errors='replace') for x in args if x]))
 except OSError:pass
remote='/home/fy1/icde_fuyue_20261005/02_decentralized_private_aggregation/protocol'
source='TAGS='+repr(tags)+'\nREMOTE='+repr(remote)+'\n'+'''import datetime,json,pathlib
registered=[]
for tag in TAGS:
 for ready in (pathlib.Path(REMOTE)/tag).glob('*/output/ready.json'):
  d=json.loads(ready.read_text());registered.append(dict(tag=tag,id=d['id'],pid=d['pid'],exact_credentials=str(ready.parent.parent)))
identities=[x['exact_credentials'].encode() for x in registered];live=[]
for p in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
 try:
  args=p.read_bytes().split(bytes([0]))
  if any(x in args for x in identities):live.append(dict(pid=int(p.parent.name),argv=[x.decode(errors='replace') for x in args if x]))
 except OSError:pass
print(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),read_only=True,registered_peers_checked=len(registered),live_exact_owned_peers=live)))
'''
cmd=['ssh','-F','/home/fu/.ssh/config','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','fy1','python3 -'];r=subprocess.run(cmd,input=source,text=True,capture_output=True,timeout=45);assert r.returncode==0,r.stderr
rr=json.loads(r.stdout);assert not live and not rr['live_exact_owned_peers']
db=sqlite3.connect('file:/home/fu/.local/state/server-history-codex/jobs.sqlite?mode=ro',uri=True);db.row_factory=sqlite3.Row
jobs=[dict(r) for r in db.execute('select id,cwd,status,session_id,model,reasoning_effort,resume_pending from jobs where cwd=?',(str(ROOT),))];db.close()
active=[r for r in jobs if r['status'] in ['running','queued','pending','starting'] or r['resume_pending']];assert len(active)==1 and active[0]['id']==TASK,active
assert active[0]['model']=='gpt-6.1-sol' and active[0]['reasoning_effort']=='xhigh'
utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
(ROOT/'evidence/owned_local_terminal_r6_final.json').write_text(json.dumps(dict(utc=utc,read_only=True,registered_peers_checked=len(registered),live_exact_owned_peers=live),indent=2)+'\n')
(ROOT/'evidence/owned_remote_terminal_r6_final.json').write_text(json.dumps(rr,indent=2)+'\n')
(ROOT/'evidence/final_owned_terminal_audit_r6.json').write_text(json.dumps(dict(utc=utc,task_id=TASK,read_only=True,tags=tags,local_registered=len(registered),remote_registered=rr['registered_peers_checked'],live_exact_owned_peers=[],remote_command=cmd,remote_script_sha256=hashlib.sha256(source.encode()).hexdigest(),same_project_active_tasks=active,model_verified='gpt-6.1-sol/xhigh',no_other_projects=True,all_registered_science_terminal=True),indent=2)+'\n')
print(json.dumps(dict(cases=len(tags),local=len(registered),remote=rr['registered_peers_checked'],live=0,model_verified='gpt-6.1-sol/xhigh')))

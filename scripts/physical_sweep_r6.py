"""Only newly affected frozen two-host cases. Shared-memory bounded peers."""
import datetime,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
for dataset in ['electricity','intel']:
 for method in ['b5','b6','independent','signature','unaware','sdp']:
  tag=dataset+'_'+method+'_r6';base=pathlib.Path('experiments/protocol')/tag
  if (base/'manifest.json').exists():continue
  if base.exists():raise RuntimeError('prior failure preserved; explicit retry tag/config required '+tag)
  for host in ['local','fy1']:
   cmd=[sys.executable,'scripts/resources.py','--output','evidence/resources_'+host+'_before_'+tag+'.json']
   if host!='local':cmd+=['--alias',host]
   subprocess.run(cmd,check=True)
  cg=pathlib.Path('/sys/fs/cgroup/system.slice/server-history-codex.service')
  stat={l.split()[0]:int(l.split()[1]) for l in (cg/'memory.stat').read_text().splitlines()}
  maxmem=int((cg/'memory.max').read_text());used=int((cg/'memory.current').read_text());reclaim=stat.get('inactive_file',0)
  # Four lightweight local peers + controller; retain >1GiB working-set headroom.
  if maxmem-used+reclaim<1024**3:raise MemoryError('shared cgroup working-set headroom <1GiB')
  cmd=[sys.executable,'scripts/protocol_run.py',tag,'experiments/protocol_config_'+tag+'.json','10']
  with pathlib.Path('evidence/protocol_'+tag+'.log').open('w') as log:
   r=subprocess.run(cmd,stdout=log,stderr=log,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
  if r.returncode:raise RuntimeError('failed run preserved '+tag)
  print(json.dumps({'completed':tag,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd}),flush=True)

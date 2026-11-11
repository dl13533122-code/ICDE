"""Sequential full370 affected physical executions; independent capacity checks."""
import argparse,datetime,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
p=argparse.ArgumentParser();p.add_argument('--methods',nargs='+',default=['b5','b6','independent','signature','sdp','unaware','cap','shift']);args=p.parse_args()
for method in args.methods:
 tag='electricity_full_'+method+'_r6';cfg=pathlib.Path('experiments/protocol_config_'+tag+'.json');base=pathlib.Path('experiments/protocol')/tag
 if not cfg.exists():raise RuntimeError('missing planned config; no silent method substitution '+tag)
 if (base/'manifest.json').exists():continue
 if base.exists():raise RuntimeError('preserve prior failure; new explicit retry tag required '+tag)
 for host in ['local','fy1']:
  cmd=[sys.executable,'scripts/resources.py','--output','evidence/resources_'+host+'_before_'+tag+'.json']
  if host!='local':cmd+=['--alias',host]
  subprocess.run(cmd,check=True)
 cg=pathlib.Path('/sys/fs/cgroup/system.slice/server-history-codex.service');stat={l.split()[0]:int(l.split()[1]) for l in (cg/'memory.stat').read_text().splitlines()}
 if int((cg/'memory.max').read_text())-int((cg/'memory.current').read_text())+stat.get('inactive_file',0)<1024**3:raise MemoryError('shared local cgroup working-set headroom<1GiB')
 with pathlib.Path('evidence/protocol_'+tag+'.log').open('w') as log:
  cmd=[sys.executable,'scripts/protocol_run.py',tag,str(cfg),'10'];p=subprocess.run(cmd,stdout=log,stderr=log,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
 if p.returncode:raise RuntimeError('failed full case retained '+tag)
 print(json.dumps(dict(completed=tag,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd)),flush=True)

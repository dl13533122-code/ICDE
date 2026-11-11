"""Complete scale points whose inherited host-link counters never finalized."""
import datetime,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
for n in [8,64,128,256]:
    tag=f'partition_scale_n{n}_r3'
    base=pathlib.Path('experiments/protocol')/tag
    if (base/'manifest.json').exists():continue
    if base.exists():raise RuntimeError('preserve failed run and choose a new tag: '+tag)
    for alias in ['local','fy1']:
        cmd=[sys.executable,'scripts/resources.py','--output',f'evidence/resources_{alias}_before_{tag}.json']
        if alias!='local':cmd+=['--alias',alias]
        subprocess.run(cmd,check=True)
    config=f'experiments/protocol_config_{tag}.json'
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
    prep=[sys.executable,'scripts/prepare_protocol.py','--n',str(n),'--noise-kind','certified-partition',
          '--epochs','12','--retry-after-abort','--output',config]
    with pathlib.Path(f'evidence/prepare_{tag}.log').open('w') as out:
        subprocess.run(prep,env=env,stdout=out,stderr=out,check=True)
    run=[sys.executable,'scripts/protocol_run.py',tag,config,'5']
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with pathlib.Path(f'evidence/protocol_{tag}.log').open('w') as out:
        subprocess.run(run,env=env,stdout=out,stderr=out,check=True)
    print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'completed':tag,'n':n,'trials':10,'command':run}),flush=True)

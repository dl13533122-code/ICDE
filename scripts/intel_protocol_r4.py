"""Only affected Intel two-host comparisons, full 54-sensor public roster."""
import datetime,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
METHODS=['independent','signature-cycle','robust-fixed-sdp','certified-partition','unaware-cycle']
for method in METHODS:
    tag='intel_'+method.replace('-','_')+'_n54_r4';base=pathlib.Path('experiments/protocol')/tag
    if base.exists():raise RuntimeError('preserve prior run; no implicit rerun '+tag)
    records={}
    for alias in ['local','fy1']:
        name='evidence/resources_'+alias+'_before_'+tag+'.json';cmd=[sys.executable,'scripts/resources.py','--output',name]
        if alias!='local':cmd+=['--alias',alias]
        subprocess.run(cmd,check=True);records[alias]=name
    local=json.loads(pathlib.Path(records['local']).read_text());limits=local['limits']
    memmax=int(limits['/sys/fs/cgroup/system.slice/server-history-codex.service/memory.max']);current=int(limits['/sys/fs/cgroup/system.slice/server-history-codex.service/memory.current'])
    if memmax-current<1024**3:raise MemoryError('less than 1GiB shared cgroup headroom; no peers started')
    rr=json.loads(pathlib.Path(records['fy1']).read_text());assert rr['returncode']==0
    remote=json.loads(rr['stdout'])
    if remote['physical_identity_sha256']==local['physical_identity_sha256']:raise ValueError('requires two physical hosts')
    config='experiments/protocol_config_'+tag+'.json';env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
    prep=[sys.executable,'scripts/prepare_protocol.py','--n','54','--noise-kind',method,'--dataset','intel','--epochs','22','--retry-after-abort','--numerical-rescale','--output',config]
    with pathlib.Path('evidence/prepare_'+tag+'.log').open('w') as f:subprocess.run(prep,env=env,stdout=f,stderr=f,check=True)
    cfg=json.loads(pathlib.Path(config).read_text());cfg['host_identity_evidence']=list(records.values());pathlib.Path(config).write_text(json.dumps(cfg,indent=2)+'\n')
    run=[sys.executable,'scripts/protocol_run.py',tag,config,'10'];env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with pathlib.Path('evidence/protocol_'+tag+'.log').open('w') as f:subprocess.run(run,env=env,stdout=f,stderr=f,check=True)
    print(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),completed=tag,n=54,trials=20,command=run)),flush=True)

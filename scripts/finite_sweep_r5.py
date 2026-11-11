"""Matched subset only: four existing layouts, two hosts, new finite backend."""
import datetime,json,os,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
inputs={('electricity','independent'):'experiments/protocol_config_matched_independent_n32_r3.json',('electricity','robust_fixed_sdp'):'experiments/protocol_config_matched_robust_sdp_n32_r3.json',('electricity','signature_cycle'):'experiments/protocol_config_matched_correlated_n32_r3.json',('electricity','certified_partition'):'experiments/protocol_config_matched_partition_n32_r3.json'}
for method in ['independent','robust_fixed_sdp','signature_cycle','certified_partition']:inputs['intel',method]='experiments/protocol_config_intel_'+method+'_n54_r4.json'
for (dataset,method),inp in inputs.items():
    tag=dataset+'_'+method+'_finite_r5'+('_retry1' if dataset=='electricity' and method=='independent' else '');config='experiments/protocol_config_'+tag+'.json';base=pathlib.Path('experiments/protocol')/tag
    if base.exists():
        if (base/'manifest.json').exists():continue
        raise RuntimeError('failed prior run preserved; use a new explicit tag '+tag)
    records={}
    for alias in ['local','fy1']:
        name='evidence/resources_'+alias+'_before_'+tag+'.json';cmd=[sys.executable,'scripts/resources.py','--output',name]
        if alias!='local':cmd+=['--alias',alias]
        subprocess.run(cmd,check=True);records[alias]=name
    local=json.loads(pathlib.Path(records['local']).read_text());limits=local['limits']
    if int(limits['/sys/fs/cgroup/system.slice/server-history-codex.service/memory.max'])-int(limits['/sys/fs/cgroup/system.slice/server-history-codex.service/memory.current'])<1024**3:raise MemoryError('shared cgroup <1GiB nominal headroom')
    rr=json.loads(pathlib.Path(records['fy1']).read_text());assert rr['returncode']==0
    remote=json.loads(rr['stdout']);assert remote['physical_identity_sha256']!=local['physical_identity_sha256']
    env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with pathlib.Path('evidence/prepare_'+tag+'.log').open('w') as f:subprocess.run([sys.executable,'scripts/finite_prepare_r5.py',inp,config],env=env,stdout=f,stderr=f,check=True)
    cfg=json.loads(pathlib.Path(config).read_text());cfg['host_identity_evidence']=list(records.values());cfg['local_peer_count']=min(4,cfg['local_peer_count']);pathlib.Path(config).write_text(json.dumps(cfg,indent=2)+'\n')
    run=[sys.executable,'scripts/protocol_run.py',tag,config,'10']
    with pathlib.Path('evidence/protocol_'+tag+'.log').open('w') as f:subprocess.run(run,env=env,stdout=f,stderr=f,check=True)
    print(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),completed=tag,command=run)),flush=True)

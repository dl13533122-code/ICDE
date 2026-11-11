"""Sequential matched two-host protocol comparisons; no concurrent port owners."""
import datetime,json,os,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1];os.chdir(ROOT)
jobs=[
 ('matched_independent_n32_r3',32,'independent','electricity','metadata',[]),
 ('matched_correlated_n32_r3',32,'signature-cycle','electricity','metadata',[]),
 ('matched_robust_sdp_n32_r3',32,'robust-fixed-sdp','electricity','metadata',[]),
 ('matched_partition_n32_r3',32,'certified-partition','electricity','metadata',[]),
 ('bad_order_partition_n32_r3',32,'certified-partition','electricity','interleaved',[]),
 ('matched_unaware_n32_r3_retry',32,'unaware-cycle','electricity','metadata',['--numerical-rescale']),
 ('intel_partition_n16_r3',16,'certified-partition','intel','metadata',[]),
 ('impaired_partition_n16_r3',16,'certified-partition','electricity','metadata',['--delay-ms','2','--rate-bytes-s','100000','--hotspot']),
 ('near_partition_n32_r3_retry',32,'certified-partition','electricity','metadata',['--near']),
 ('shift_partition_n32_r3',32,'certified-partition','electricity','metadata',['--workload-shift']),
]
for tag,n,method,dataset,order,extra in jobs:
    base=pathlib.Path('experiments/protocol')/tag
    if (base/'manifest.json').exists():continue
    if base.exists():raise RuntimeError('preserve failed run and choose a new explicit tag: '+tag)
    for alias in ['local','fy1']:
        cmd=[sys.executable,'scripts/resources.py','--output','evidence/resources_'+alias+'_before_'+tag+'.json']
        if alias!='local':cmd+=['--alias',alias]
        subprocess.run(cmd,check=True)
    config='experiments/protocol_config_'+tag+'.json'
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
    prep=[sys.executable,'scripts/prepare_protocol.py','--n',str(n),'--noise-kind',method,'--dataset',dataset,
          '--order',order,'--epochs','22','--retry-after-abort','--output',config,*extra]
    with pathlib.Path('evidence/prepare_'+tag+'.log').open('w') as f:subprocess.run(prep,env=env,stdout=f,stderr=f,check=True)
    run=[sys.executable,'scripts/protocol_run.py',tag,config,'10']
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    with pathlib.Path('evidence/protocol_'+tag+'.log').open('w') as f:subprocess.run(run,env=env,stdout=f,stderr=f,check=True)
    print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':tag,'n':n,'trials':20,'command':run}),flush=True)

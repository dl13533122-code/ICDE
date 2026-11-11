"""Orchestrate two-host test peers via authorized SSH tunnels, no secret export."""
import concurrent.futures, hashlib, json, math, os, pathlib, resource, signal, socket, subprocess, sys, time, shlex
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from src.protocol import credentials,context,rpc,blank,weighted_reports,wire_fraction
from src.release_gate import validate_peer_config

SSH=['ssh','-F','/home/fu/.ssh/config','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-o','ControlMaster=auto','-o','ControlPersist=60','-o','ControlPath=/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/fy1-control']
REMOTE='/home/fy1/icde_fuyue_20261005/02_decentralized_private_aggregation'
REMOTE_ALIAS='fy1'
REMOTE_PYTHON=REMOTE+'/.venv/bin/python'
SSH_DEFAULT=tuple(SSH)

def command(cmd,**kwargs):
    for attempt in range(2):
        p=subprocess.run(cmd,capture_output=True,text=True,**kwargs)
        if p.returncode==0:break
        if p.returncode!=255 or not any(x in p.stderr for x in ['Connection closed','Connection timed out','Connection reset']):break
        if attempt==0:time.sleep(1)
    if p.returncode:raise RuntimeError(str(cmd)+': '+p.stderr)
    return p.stdout

def arithmetic_check(answers,reports,W,d=1):
    expected=[weighted_reports(row,reports,d) for row in W]
    flat=lambda v: [v] if d==1 else v
    errors=[abs(x-y) for j,v in enumerate(expected) for x,y in zip(flat(answers[j]),flat(v))]
    magnitude=max(math.fsum(abs(c*x) for c,v in zip(row,reports) for x in flat(v)) for row in W)
    bound=max(1e-8,128*sys.float_info.epsilon*magnitude)
    error=max(errors)
    if error>bound:raise ValueError('aggregation mismatch')
    return error,bound


def case_attempt_count(cfg, repetitions):
    attempts=len(cfg.get('routing_modes',['sharing','no_sharing']))*repetitions+1+int(cfg.get('retry_after_abort',False))
    limit=cfg['accountant']['max_release_epochs']
    if attempts>limit:raise ValueError('run exceeds declared full prepared-attempt composition')
    scope=cfg.get('privacy_scope')
    if scope=='cumulative_protected_release_history':
        if cfg['prior_related_attempts']+attempts>limit:
            raise ValueError('cumulative history exceeds 22 attempts; refused before sampling; host/process/tag cannot reset budget')
    elif scope is not None:
        if scope!='single_benchmark_case_transcript':raise ValueError('unknown privacy scope')
        if cfg.get('fixture_sensitivity_semantics')!='public_research_benchmark_fixture':raise ValueError('fresh independently scoped fixture not authorized')
        if repetitions!=10 or cfg['routing_modes']!=['sharing'] or not cfg.get('retry_after_abort') or attempts!=12:raise ValueError('matched case requires exactly 10 ordinary + exposed abort + fresh retry')
        if cfg['prior_related_attempts']!=12 or cfg['new_prepared_attempts']!=12 or cfg['related_two_batch_attempts']!=24:raise ValueError('inconsistent related-batch provenance')
        if cfg.get('combined_history_epsilon1_delta1e-6_claim') is not False or cfg.get('production_cross_restart_accountant_certified') is not False:raise ValueError('unsupported combined-history privacy claim')
    return attempts

def run(tag,config_path='experiments/protocol_config.json',repetitions=20):
    global SSH, REMOTE, REMOTE_ALIAS, REMOTE_PYTHON
    SSH=list(SSH_DEFAULT)
    run_started=time.perf_counter();run_cpu_started=time.process_time();run_start_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
    base=pathlib.Path('experiments/protocol')/tag;base.mkdir(parents=True,exist_ok=False)
    internal=base/'internal';internal.mkdir();cfg=json.loads(pathlib.Path(config_path).read_text());common=cfg.get('peer_common',{});cfg['peers']=[dict(common,**p) for p in cfg['peers']];n=len(cfg['peers']);split=int(cfg.get('local_peer_count',min(8,n//2) if n>64 else n//2));offset=31800;addresses={str(i):['127.0.0.1',offset+i] for i in range(n)}
    case_attempt_count(cfg,repetitions)
    remote=cfg.get('remote_environment')
    if remote:
        if remote['alias']!='desktop125' or remote['root']!='/home/fy/icde_fuyue_20261013/02_decentralized_private_aggregation' or remote['python']!=remote['root']+'/.venv/bin/python':raise ValueError('unapproved remote execution identity')
        REMOTE_ALIAS,REMOTE,REMOTE_PYTHON=remote['alias'],remote['root'],remote['python']
        owner=json.loads(pathlib.Path('governance/.executor.lock/owner.json').read_text())
        if owner['task_id']!=cfg['task_id'] or owner['thread_id']!=os.environ.get('CODEX_THREAD_ID'):raise ValueError('project lock ownership mismatch')
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:8])
    soft,hard=resource.getrlimit(resource.RLIMIT_NOFILE);desired=min(hard,max(soft,4*n+256))
    resource.setrlimit(resource.RLIMIT_NOFILE,(desired,hard))
    (base/'process_resource_limits.json').write_text(json.dumps({'nofile_soft_before':soft,'nofile_soft_for_this_process_and_children':desired,'nofile_hard_unchanged':hard,'reason':'one listening descriptor per SSH forward plus bounded active RPCs; process-only unprivileged limit, no runner/system settings modified'},indent=2)+'\n')
    if not cfg['certificate']['passed']:raise ValueError('uncertified graph refused')
    case_attempt_count(cfg,repetitions)
    if cfg.get('finite_proof'):
        from src.finite_reports import public_bound,public_preflight
        from src.release_gate import rigorous_finite_certificate
        params=cfg['peer_common']['finite_parameters']
        if any(p.get('finite_parameters')!=params for p in cfg['peers']):raise ValueError('mixed numerical protocol refused')
        proof=public_bound(cfg['peers'],params,epsilon=cfg['accountant']['eps_total_bound'],attempts=cfg['accountant']['max_release_epochs'],delta_total=cfg['accountant']['delta'])
        if not proof['passed'] or proof['beta_upper_exact']!=cfg['finite_proof']['beta_upper_exact']:raise ValueError('stale or invalid public bound')
        (base/'finite_arithmetic_preflight.json').write_text(json.dumps(public_preflight(cfg['peers'],params),indent=2)+'\n')
        rigorous=rigorous_finite_certificate(cfg['peers']);(base/'rigorous_fresh_certificate.json').write_text(json.dumps(rigorous,indent=2)+'\n')
    fresh_certificate=validate_peer_config(cfg['peers'],cfg.get('noise_blocks'));(base/'fresh_certificate.json').write_text(json.dumps(fresh_certificate,indent=2)+'\n')
    scratch=pathlib.Path('/home/fu/.local/state/server-history-codex/tmp/B-fuyue-20261005-v1/peers')/tag;scratch.mkdir(parents=True)
    for j,value in enumerate(SSH):
        if value.startswith('ControlPath='):SSH[j]='ControlPath=/tmp/icdeB-'+hashlib.sha256((os.environ.get('CODEX_THREAD_ID','')+tag).encode()).hexdigest()[:12]
    meter=pathlib.Path('scripts/ssh_byte_meter.py').read_bytes();(scratch/'ssh_byte_meter.py').write_bytes(meter)
    SSH.extend(['-o','ProxyCommand='+sys.executable+' '+str(scratch/'ssh_byte_meter.py')+' '+str(scratch/'ssh_wire.json')+' '+REMOTE_ALIAS])
    public_preflight_seconds=time.perf_counter()-run_started
    provisioning_started=time.perf_counter()
    control_pem=credentials(scratch/'control','control');pub=base/'public';pub.mkdir();local=[];tunnel=None;certs=[]
    source=pathlib.Path('src/protocol.py').read_bytes()
    (scratch/'finite_reports.py').write_bytes(pathlib.Path('src/finite_reports.py').read_bytes())
    if b'\0' in source:raise ValueError('source read corruption refused')
    (scratch/'protocol.py').write_bytes(source)
    remote_path=REMOTE+'/protocol/'+tag
    if cfg.get('remote_environment'):
        check='import pathlib,json; root=pathlib.Path('+repr(REMOTE)+'); assert json.loads((root/"governance/.executor.lock/owner.json").read_text())["task_id"]=='+repr(cfg['task_id'])+'; print("owned remote project lock verified")'
        command(SSH+[REMOTE_ALIAS,'python3 -'],input=check,timeout=20)
    command(SSH+[REMOTE_ALIAS,'mkdir -p '+REMOTE+'/protocol && mkdir '+remote_path])
    try:
        batch=cfg.get('batch_remote',False)
        remote_source=remote_path+'/protocol.py' if batch else REMOTE+'/src/protocol.py'
        if batch:
            command(SSH+[REMOTE_ALIAS,'cat > '+remote_source],input=source.decode())
            command(SSH+[REMOTE_ALIAS,'cat > '+remote_path+'/finite_reports.py'],input=pathlib.Path('src/finite_reports.py').read_text())
            remote_data={'common':dict(common,addresses=addresses),'peers':[{k:v for k,v in p.items() if k not in common} for p in cfg['peers'][split:]]}
            command(SSH+[REMOTE_ALIAS,'cat > '+remote_path+'/peers.json'],input=json.dumps(remote_data))
            provision='import pathlib,json,runpy\nns=runpy.run_path('+repr(remote_source)+')\nroot=pathlib.Path('+repr(remote_path)+')\ncerts={};data=json.loads((root/"peers.json").read_text())\nfor pp in data["peers"]:\n peer=dict(data["common"],**pp);p=root/str(peer["id"]);p.mkdir();(p/"config.json").write_text(json.dumps(peer));certs[peer["id"]]=ns["credentials"](p,peer["id"]).decode()\nprint(json.dumps(certs))\n'
            remote_certs=json.loads(command(SSH+[REMOTE_ALIAS,shlex.quote(REMOTE_PYTHON)+' -'],input=provision,timeout=120))
        # Each peer holds only its own newly generated private key. Copy public certificates only.
        for i in range(n):
            peer=dict(cfg['peers'][i],addresses=addresses)
            p=internal/str(i);p.mkdir();(p/'config.json').write_text(json.dumps(peer))
            if i<split:
                pp=scratch/str(i);pp.mkdir();(pp/'config.json').write_text(json.dumps(peer));cert=credentials(pp,i);certs.append(cert.decode());(pub/f'{i}.pem').write_bytes(cert)
            else:
                if batch:cert=remote_certs[str(i)]
                else:
                    command(SSH+[REMOTE_ALIAS,f'mkdir {remote_path}/{i} && cd {REMOTE} && {REMOTE_PYTHON} src/protocol.py --credentials {remote_path}/{i} --identity {i}'])
                    cert=command(SSH+[REMOTE_ALIAS,'cat '+remote_path+'/'+str(i)+'/public.pem'])
                    command(SSH+[REMOTE_ALIAS,'cat > '+remote_path+'/'+str(i)+'/config.json'],input=json.dumps(peer))
                certs.append(cert);(pub/f'{i}.pem').write_text(cert)
        trust=''.join(certs)+control_pem.decode();(pub/'trust.pem').write_text(trust);(scratch/'trust.pem').write_text(trust)
        command(SSH+[REMOTE_ALIAS,'cat > '+remote_path+'/trust.pem'],input=trust)
        tunnel_args=[]
        for i in range(n):tunnel_args+=['-R' if i<split else '-L',f'127.0.0.1:{offset+i}:127.0.0.1:{offset+i}']
        tlog=(base/'tunnel.log').open('w');tunnel=subprocess.Popen(SSH+['-o','ExitOnForwardFailure=yes',*tunnel_args,'-N',REMOTE_ALIAS],stdout=tlog,stderr=tlog)
        time.sleep(1)
        (base/'tunnel_command.json').write_text(json.dumps({'command':SSH+['-o','ExitOnForwardFailure=yes',*tunnel_args,'-N',REMOTE_ALIAS],'initial_exit_status':tunnel.poll()}))
        if tunnel.poll() not in (None,0):raise RuntimeError('forwarding refused; see tunnel.log')
        for i in range(n):
            if i<split:
                log=(internal/str(i)/'process.log').open('w');p=subprocess.Popen([sys.executable,str(scratch/'protocol.py'),'--credentials',str(scratch/str(i)),'--config',str(scratch/str(i)/'config.json'),'--trust',str(scratch/'trust.pem'),'--out',str(internal/str(i)/'output')],stdout=log,stderr=log,env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'));local.append(p)
            elif not batch:
                launcher='import subprocess,os,json\nos.chdir('+repr(REMOTE)+')\nos.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:8])\nf=open('+repr(remote_path+'/'+str(i)+'/process.log')+',"w")\np=subprocess.Popen('+repr([REMOTE_PYTHON,'src/protocol.py','--credentials',remote_path+'/'+str(i),'--config',remote_path+'/'+str(i)+'/config.json','--trust',remote_path+'/trust.pem','--out',remote_path+'/'+str(i)+'/output'])+',stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True,close_fds=True)\nprint(json.dumps({"owned_pid":p.pid}))\n'
                command(SSH+[REMOTE_ALIAS,'python3 -'],input=launcher,timeout=15)
        if batch:
            launcher='import subprocess,os,json,pathlib\nos.chdir('+repr(REMOTE)+')\nos.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:8])\nroot=pathlib.Path('+repr(remote_path)+')\npids=[]\nfor i in range('+str(split)+','+str(n)+'):\n p=root/str(i);f=(p/"process.log").open("w");proc=subprocess.Popen(['+repr(REMOTE_PYTHON)+','+repr(remote_source)+',"--credentials",str(p),"--config",str(p/"config.json"),"--trust",str(root/"trust.pem"),"--out",str(p/"output")],stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True,close_fds=True,env=dict(os.environ,OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1"));pids.append(proc.pid);f.close()\n(root/"owned_pids.json").write_text(json.dumps(pids));print(json.dumps({"owned_pid_count":len(pids)}))\n'
            command(SSH+[REMOTE_ALIAS,'python3 -'],input=launcher,timeout=120)
        ctx=context(scratch/'control',str(scratch/'trust.pem'));metrics=blank()
        if len(ctx.get_ca_certs())!=n+1:raise ValueError('incomplete TLS trust store refused')
        def call(i,msg):
            if cfg.get('physical_frames') and msg['op']!='metrics':
                response=cfg['physical_control_response_bytes'][i] if msg['op']=='aggregate' and msg.get('mode')=='query' else 1024 if msg['op']=='report' else 256
                msg=dict(msg,_frame_request=512,_frame_response=response)
            return rpc(ctx,addresses[str(i)],msg,metrics,i)
        # Only bounded readiness retries, no host scan.
        for i in range(n):
            for attempt in range(10):
                try:call(i,{'op':'metrics'});break
                except (ConnectionError,OSError,EOFError):time.sleep(.5)
            else:raise RuntimeError('peer did not start '+str(i))
        def allcall(msg,ids=range(n)):
            def event(status):
                if msg['op']=='prepare':
                    with (base/'attempt_events.jsonl').open('a') as f:f.write(json.dumps({'epoch':msg['epoch'],'status':status,'scope':'this case only; receipts are not a persistent privacy accountant','utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})+'\n')
            event('PREPARE_DISPATCH')
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(lambda i:call(i,msg),ids))
            except BaseException:
                event('PREPARE_FAILED_OR_PARTIAL');raise
            event('PREPARED_ALL')
            return result
        initial=allcall({'op':'metrics'})
        if cfg.get('remote_environment'):
            expected=cfg['remote_environment']
            for i,receipt in enumerate(initial):
                rt=receipt['runtime_identity']
                if rt['machine_id_sha256']!=cfg['physical_machine_ids'][0 if i<split else 1]:raise ValueError('peer physical host identity mismatch')
                if rt['protocol_sha256']!=hashlib.sha256(source).hexdigest() or rt['finite_reports_sha256']!=hashlib.sha256(pathlib.Path('src/finite_reports.py').read_bytes()).hexdigest():raise ValueError('peer runtime source mismatch')
                if rt['input_sha256']!=hashlib.sha256(json.dumps(cfg['peers'][i]['s'],sort_keys=True,separators=(',',':')).encode()).hexdigest():raise ValueError('peer input mismatch')
                if rt['W_sha256']!=hashlib.sha256(json.dumps(cfg['peers'][i]['W'],sort_keys=True,separators=(',',':')).encode()).hexdigest():raise ValueError('peer workload mismatch')
                if receipt['prepared_attempts']!=0 or receipt['rho_spent']!=0 or receipt['history']:raise ValueError('case starts with unexpected prior in-process expenditure')
                if i>=split and rt['python']!=expected['python']:raise ValueError('remote peer python identity mismatch')
        (base/'initial_peer_runtime_receipts.json').write_text(json.dumps(initial,indent=2)+'\n')
        print(json.dumps({'tag':tag,'stage':'before_sampling','runtime_inputs_hosts_verified':bool(cfg.get('remote_environment')),'peers':n}),flush=True)
        provisioning_seconds=time.perf_counter()-provisioning_started
        trials=[]
        def wire_snapshot():
            p=scratch/'ssh_wire.json'
            return json.loads(p.read_text()) if p.exists() else None
        for mode in cfg.get('routing_modes',['sharing','no_sharing']):
            for repetition in range(repetitions):
                epoch=f'{tag}-{mode}-{repetition}';wire_before=wire_snapshot();trial_cpu_start=time.process_time();t=time.perf_counter();before=allcall({'op':'metrics'})
                controller_before=json.loads(json.dumps(metrics))
                stage_cpu0=time.process_time();allcall({'op':'prepare','epoch':epoch});t1=time.perf_counter();stage_cpu1=time.process_time();allcall({'op':'setup'});t2=time.perf_counter();stage_cpu2=time.process_time();released=allcall({'op':'release'});t3=time.perf_counter();stage_cpu3=time.process_time()
                if any(r.get('status')=='ABORT' for r in released):
                    allcall({'op':'abort'})
                    trials.append({'mode':mode,'repetition':repetition,'epoch':epoch,'status':'ABORT','seconds':{'online_total':t3-t}})
                    (base/'results_partial.json').write_text(json.dumps(trials,indent=2,default=wire_fraction)+'\n')
                    continue
                if mode=='sharing':allcall({'op':'aggregate','mode':'sharing'})
                answers=allcall({'op':'aggregate','mode':'query','sharing':mode=='sharing'});t4=time.perf_counter();stage_cpu4=time.process_time()
                reports=allcall({'op':'report'});allcall({'op':'finish'});after=allcall({'op':'metrics'})
                ans={int(k):v for d in answers for k,v in d['answers'].items()};z=[d['z'] for d in reports]
                arithmetic_error,arithmetic_bound=arithmetic_check(ans,z,cfg['peers'][0]['W'],cfg.get('report_dimension',1))
                trials.append({'mode':mode,'repetition':repetition,'epoch':epoch,'seconds':{'coordination':t1-t,'setup':t2-t1,'release':t3-t2,'query':t4-t3,'online_total':t4-t},'before':before,'after':after,'answers':ans,'public_reports':z,'arithmetic_max_error':arithmetic_error})
                trials[-1]['arithmetic_absolute_bound']=arithmetic_bound
                trials[-1]['controller_cpu_seconds']=time.process_time()-trial_cpu_start
                trials[-1]['controller_stage_cpu_seconds']={'coordination':stage_cpu1-stage_cpu0,'setup':stage_cpu2-stage_cpu1,'release':stage_cpu3-stage_cpu2,'query':stage_cpu4-stage_cpu3}
                if cfg.get('physical_frames'):
                    trials[-1]['controller_before']=controller_before
                    trials[-1]['controller_after']=json.loads(json.dumps(metrics))
                    modeled={};nodes=[]
                    for b,a in zip(before,after):
                        totals={k:0 for k in ['application_tx_bytes','application_rx_bytes','tls_tx_bytes','tls_rx_bytes']}
                        for op in ['mask','report','partial']:
                            bm=b['metrics'].get('by_op',{}).get(op,{});am=a['metrics'].get('by_op',{}).get(op,{})
                            for k in totals:totals[k]+=am.get(k,0)-bm.get(k,0)
                        # Includes final controller report collection; tracked in l0.
                        nodes.append(totals);h=a['hostname'];modeled[h]=modeled.get(h,0)+totals['application_tx_bytes']+totals['application_rx_bytes']
                    trials[-1]['fixed_frame_node_metrics']=nodes
                    trials[-1]['fixed_frame_host_application_bytes']=modeled
                trials[-1]['ssh_host_link_payload_before']=wire_before;trials[-1]['ssh_host_link_payload_after']=wire_snapshot()
                rss=0
                for proc in local:
                    for line in pathlib.Path(f'/proc/{proc.pid}/status').read_text().splitlines():
                        if line.startswith('VmRSS:'):rss+=int(line.split()[1])*1024
                for line in pathlib.Path('/proc/self/status').read_text().splitlines():
                    if line.startswith('VmRSS:'):rss+=int(line.split()[1])*1024
                trials[-1]['local_aggregate_current_rss_bytes']=rss
                if rss>2*1024**3:raise MemoryError('project local peer+controller RSS exceeds initial 2GiB; checkpoint and shrink local mapping')
                (base/'results_partial.json').write_text(json.dumps(trials,indent=2,default=wire_fraction)+'\n')
                print(json.dumps({'tag':tag,'ordinary_completed':len(trials),'prepared_attempts':len(trials)}),flush=True)
        # Data-independent exposure test: some reports visible, abort, charge their releases, fresh retry.
        abort_wire_before=wire_snapshot();abort_controller_before=json.loads(json.dumps(metrics));abort_before=allcall({'op':'metrics'});abort_started=time.perf_counter();abort_cpu_started=time.process_time()
        allcall({'op':'prepare','epoch':tag+'-dropout'});allcall({'op':'setup'});allcall({'op':'release'},range(split));allcall({'op':'abort'});abort_seconds=time.perf_counter()-abort_started;dropout=allcall({'op':'metrics'});abort_wire_after=wire_snapshot();abort_controller_after=json.loads(json.dumps(metrics));abort_cpu_seconds=time.process_time()-abort_cpu_started
        (base/'exposed_abort_receipt.json').write_text(json.dumps({'before':abort_before,'after':dropout,'controller_before':abort_controller_before,'controller_after':abort_controller_after,'ssh_before':abort_wire_before,'ssh_after':abort_wire_after,'wall_seconds':abort_seconds,'controller_cpu_seconds':abort_cpu_seconds},indent=2)+'\n')
        print(json.dumps({'tag':tag,'stage':'exposed_abort_complete','prepared_attempts':len(trials)+1}),flush=True)
        # Repeat epoch is refused on every participant and no failed query is returned.
        refused=[]
        for i in range(n):
            try:call(i,{'op':'prepare','epoch':tag+'-dropout'});refused.append(False)
            except RuntimeError:refused.append(True)
        if not all(refused):raise ValueError('epoch reuse was allowed')
        retry=None
        if cfg.get('retry_after_abort',False):
            retry_wire_before=wire_snapshot();retry_before=allcall({'op':'metrics'});retry_controller_before=json.loads(json.dumps(metrics));retry_started=time.perf_counter();retry_cpu_started=time.process_time()
            retry_epoch=tag+'-fresh-retry';allcall({'op':'prepare','epoch':retry_epoch});allcall({'op':'setup'});allcall({'op':'release'})
            allcall({'op':'aggregate','mode':'sharing'});answers=allcall({'op':'aggregate','mode':'query','sharing':True});reports=allcall({'op':'report'});allcall({'op':'finish'})
            z=[p['z'] for p in reports];ans={int(k):v for p in answers for k,v in p['answers'].items()}
            error,_=arithmetic_check(ans,z,cfg['peers'][0]['W'],cfg.get('report_dimension',1))
            retry={'epoch':retry_epoch,'public_reports':z,'answers':ans,'arithmetic_max_error':error,'metrics':allcall({'op':'metrics'}),'status':'OBSERVED','freshness_scope':'new epoch and regenerated OS-random Gaussian masks/local noise; report difference is diagnostic, not a privacy proof'}
            retry['wall_seconds']=time.perf_counter()-retry_started
            retry.update(before=retry_before,controller_before=retry_controller_before,controller_after=json.loads(json.dumps(metrics)),ssh_host_link_payload_before=retry_wire_before,ssh_host_link_payload_after=wire_snapshot(),controller_cpu_seconds=time.process_time()-retry_cpu_started)
        if retry:(base/'fresh_retry_receipt.json').write_text(json.dumps(retry,indent=2,default=wire_fraction)+'\n')
        public_config={k:v for k,v in cfg.items() if k!='peers'};public_config['peers']=[{k:v for k,v in p.items() if k!='s' and k not in common} for p in cfg['peers']];(pub/'config.json').write_text(json.dumps(public_config,indent=2))
        manifest={'tag':tag,'status':'OBSERVED','deployment':str(n)+' independent peer processes on two distinct physical hosts; TLS RPC inside bidirectional SSH forwarding','n':n,'host_identity_evidence':cfg.get('host_identity_evidence',['evidence/resources_local_initial.json','evidence/resources_fy1_initial.json']),'process_to_host':allcall({'op':'metrics'}),'trials':trials,'dropout':dropout,'epoch_reuse_refused':refused,'controller_metrics':metrics,'wire_accounting':'TLS ciphertext bytes incl handshakes at peer sockets; excludes TCP/IP and outer SSH ciphertext. SSH connection setup recorded as unmeasured overhead gate. Application bytes separately measured.','attacker_trace':'public noisy reports, public config and timings only. TLS private keys/local statistics/incident masks are internal; no masks or RNG seeds logged.','assumptions':['honest-but-curious f=1','trusted research test operator and host administrators outside peer adversary','finite precision Gaussian and TLS/OS RNG computational assumptions need web end-to-end review'],'public_config_path':str(pub/'config.json'),'internal_fixture_path':config_path}
        (base/'manifest.json').write_text(json.dumps(manifest,indent=2,default=wire_fraction)+'\n')
        manifest['fresh_retry_after_abort']=retry
        manifest['finite_backend']=cfg.get('finite_proof')
        if cfg.get('finite_proof'):manifest['assumptions']=['honest-but-curious fixed f=1, fixed roster before all attempts','ideal secure channels for statistical DP; TLS/OS CSPRNG computational advantage separate','hardware timing/cache side channels excluded; public operation/message schedule','exact rational report/aggregate wire; rigorous enclosures and bounded deterministic fallback']
        manifest['code_sha256']={p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['src/protocol.py','src/finite_reports.py','src/partition.py','src/release_gate.py','src/planner.py','scripts/protocol_run.py','scripts/ssh_byte_meter.py']}
        manifest['config_sha256']=hashlib.sha256(pathlib.Path(config_path).read_bytes()).hexdigest();manifest['command']=sys.argv
        manifest['additional_costs']={'one_time_provisioning_seconds':provisioning_seconds,'exposed_abort_seconds':abort_seconds,'abort_before':abort_before,'controller_process_cpu_seconds':time.process_time()-run_cpu_started,'wall_seconds_through_final_metrics':time.perf_counter()-run_started,'timing_scope':'wall/CPU through final metrics; cleanup after this manifest excluded; includes preflight, key creation, staging and process readiness'}
        manifest['run_start_utc']=run_start_utc
        manifest['run_end_utc']=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        manifest['public_preflight_seconds']=public_preflight_seconds
        manifest['execution_environment']=cfg.get('execution_environment','legacy_fu_fy1')
        for field in ['privacy_scope','fixture_sensitivity_semantics','prior_related_attempts','new_prepared_attempts','related_two_batch_attempts','combined_history_epsilon1_delta1e-6_claim','production_cross_restart_accountant_certified','prior_related_manifest','planning_labels','execution_identity_sha256','physical_machine_ids','remote_environment','task_id']:
            if field in cfg:manifest[field]=cfg[field]
        manifest['exposed_abort_receipt']={'before':abort_before,'after':dropout,'controller_before':abort_controller_before,'controller_after':abort_controller_after,'ssh_before':abort_wire_before,'ssh_after':abort_wire_after,'wall_seconds':abort_seconds,'controller_cpu_seconds':abort_cpu_seconds}
        manifest['initial_peer_runtime_path']=str(base/'initial_peer_runtime_receipts.json')
        manifest['scientific_acceptance']=False
        manifest['wire_accounting']='Measured per-peer TLS bytes and outer SSH ciphertext host-link payload including provisioning/coordination; trial snapshots include monitoring RPCs. TCP/IP/L2 headers and retransmissions unmeasured; logical overlay cost reported separately.'
        (base/'manifest.json').write_text(json.dumps(manifest,indent=2,default=wire_fraction)+'\n')
        allcall({'op':'stop'})
        for p in local:p.wait(timeout=10)
        print(json.dumps({'manifest':str(base/'manifest.json'),'trial_count':len(trials),'hosts':2}),flush=True)
    except BaseException as error:
        (base/'failure_receipt.json').write_text(json.dumps({'tag':tag,'error_type':type(error).__name__,'error':str(error),'traceback':__import__('traceback').format_exc(),'status':'BLOCKED','whole_case_missing':True,'privacy_scope':cfg.get('privacy_scope'),'sampling_attempt_dispatches':(base/'attempt_events.jsonl').read_text() if (base/'attempt_events.jsonl').exists() else '', 'utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()},indent=2)+'\n')
        raise
    finally:
        # Registered peer PIDs under THIS run only; verify exact credentials argument before stopping.
        cleanup='import pathlib,json,os,signal,time\nbase=pathlib.Path(REMOTE_PATH)\npids=set(json.loads((base/"owned_pids.json").read_text())) if (base/"owned_pids.json").exists() else set()\nfor ready in base.glob("*/output/ready.json"):\n pids.add(json.loads(ready.read_text())["pid"])\nfor pid in sorted(pids):\n proc=pathlib.Path(f"/proc/{pid}");owned=False;terminal=False;stopped=False\n try:\n  argv=(proc/"cmdline").read_bytes().split(bytes([0]))\n  if b"--credentials" in argv:\n   cred=argv[argv.index(b"--credentials")+1].decode();owned=pathlib.Path(cred).parent==base\n  state=(proc/"stat").read_text().split(") ",1)[1].split()[0]\n  if state=="Z" or not owned:terminal=True\n  else:\n   os.kill(pid,signal.SIGTERM);stopped=True\n   for _ in range(50):\n    if not proc.exists() or (proc/"stat").read_text().split(") ",1)[1].split()[0]=="Z":terminal=True;break\n    time.sleep(.1)\n except (FileNotFoundError,ProcessLookupError):terminal=True\n print(json.dumps({"pid":pid,"owned_at_cleanup":owned,"stopped_owned_pid":stopped,"owned_process_terminal":terminal}))\n'.replace('REMOTE_PATH',repr(remote_path))
        try:
            cleanup_output=command(SSH+[REMOTE_ALIAS,'python3 -'],input=cleanup,timeout=20);(base/'owned_cleanup.jsonl').write_text(cleanup_output)
        except Exception as e:(base/'cleanup_failure.txt').write_text(str(e))
        # Touch only PIDs created by this job; remote peers normally stop via RPC.
        for p in local:
            if p.poll() is None:p.terminate();p.wait(timeout=10)
        if tunnel and tunnel.poll() is None:tunnel.terminate();tunnel.wait(timeout=10)
        (scratch/'ssh_wire.json.finalize_request').write_text('completed trials and positively owned peer cleanup; finalize measured host-link payload before shutdown\n')
        for _ in range(40):
            if (scratch/'ssh_wire.json').exists() and json.loads((scratch/'ssh_wire.json').read_text()).get('status')=='OBSERVED':break
            time.sleep(.05)
        subprocess.run(SSH+['-O','exit',REMOTE_ALIAS],capture_output=True,timeout=15)
        owner_file=scratch/'ssh_wire.json.owner.json'
        if owner_file.exists():
            relay_pid=json.loads(owner_file.read_text())['relay_pid']
            try:
                argv=pathlib.Path(f'/proc/{relay_pid}/cmdline').read_bytes().split(bytes([0]))
                if str(scratch/'ssh_byte_meter.py').encode() in argv:os.kill(relay_pid,signal.SIGTERM)
            except (FileNotFoundError,ProcessLookupError):pass
        for _ in range(10):
            if (scratch/'ssh_wire.json').exists():break
            time.sleep(.1)
        if (scratch/'ssh_wire.json').exists():(base/'ssh_wire.json').write_bytes((scratch/'ssh_wire.json').read_bytes())
        remote_receipts=[json.loads(line) for line in (base/'owned_cleanup.jsonl').read_text().splitlines()] if (base/'owned_cleanup.jsonl').exists() else []
        all_terminal=bool(remote_receipts) and all(p['owned_process_terminal'] for p in remote_receipts) and all(p.poll() is not None for p in local) and (tunnel is None or tunnel.poll() is not None)
        receipt={'owned_workers_terminal':all_terminal,'remote_process_receipts':remote_receipts,'local_returncodes':[p.returncode for p in local],'tunnel_returncode':None if tunnel is None else tunnel.returncode,'whole_driver_wall_seconds':time.perf_counter()-run_started,'whole_driver_cpu_seconds':time.process_time()-run_cpu_started,'scope':'including preflight/provisioning/ordinary/abort/retry/owned cleanup; software installation and public planning recorded separately'}
        (base/'owned_terminal_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if cfg.get('remote_environment') and not all_terminal:raise RuntimeError('owned worker termination not fully verified; retain own locks')

if __name__=='__main__':run(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else 'experiments/protocol_config.json',int(sys.argv[3]) if len(sys.argv)>3 else 20)

"""Independent peer services; OS randomness, pinned mutual TLS, charged epochs.

Research deployment: test operator provisions public certificates and per-peer
inputs. Test host administrators are outside the coalition threat model.
Gaussian finite precision/side channels remain a web proof obligation.
"""
import sys
import argparse, base64, concurrent.futures, datetime, hashlib, json, math, os, pathlib, resource, secrets, socket, ssl, struct, threading, time
from fractions import Fraction
try:
    from .finite_reports import draw, encode_report, DEFAULT as FINITE_DEFAULT
except ImportError:
    import sys
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
    from finite_reports import draw, encode_report, DEFAULT as FINITE_DEFAULT
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec

def wire_fraction(value):
    if isinstance(value,Fraction):
        return {'rational_fixed': [value.numerator.to_bytes(64,'big',signed=True).hex(),value.denominator.to_bytes(64,'big').hex()]}
    raise TypeError('unsupported wire type')

def read_fraction(value):
    if 'rational_fixed' in value:
        a,b=value['rational_fixed']
        if len(a)!=128 or len(b)!=128: raise ValueError('invalid public wire width')
        return Fraction(int.from_bytes(bytes.fromhex(a),'big',signed=True),int.from_bytes(bytes.fromhex(b),'big'))
    return value

def credentials(directory, identity):
    p=pathlib.Path(directory);p.mkdir(parents=True,exist_ok=True)
    key=p/'private.pem';cert=p/'public.pem'
    if key.exists():raise FileExistsError('never reuse test TLS private keys implicitly')
    k=ec.generate_private_key(ec.SECP256R1());name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,str(identity))]);now=datetime.datetime.now(datetime.timezone.utc)
    c=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=3)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True).sign(k,hashes.SHA256())
    key.write_bytes(k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));os.chmod(key,0o600);pem=c.public_bytes(serialization.Encoding.PEM);cert.write_bytes(pem)
    return pem

class Channel:
    """TLS MemoryBIO accounts actual encrypted records including handshakes.

    Counts exclude TCP/IP and outer SSH tunneling; manifests state both layers.
    """
    def __init__(self,sock,context,metrics,server=False):
        self.raw=sock;self.mi=ssl.MemoryBIO();self.mo=ssl.MemoryBIO();self.ssl=context.wrap_bio(self.mi,self.mo,server_side=server,server_hostname=None if server else 'peer');self.metrics=metrics;self.local=blank();self.buffer=b'';self.action(self.ssl.do_handshake)
    def flush(self):
        while self.mo.pending:
            b=self.mo.read();self.raw.sendall(b);self.metrics['tls_tx_bytes']+=len(b);self.local['tls_tx_bytes']+=len(b)
    def action(self,f):
        while True:
            try:r=f();self.flush();return r
            except ssl.SSLWantReadError:
                self.flush();b=self.raw.recv(65536)
                if not b:raise EOFError('closed TLS connection')
                self.metrics['tls_rx_bytes']+=len(b);self.local['tls_rx_bytes']+=len(b);self.mi.write(b)
            except ssl.SSLWantWriteError:self.flush()
    def send(self,obj,frame_bytes=None):
        b=json.dumps(obj,separators=(',',':'),default=wire_fraction).encode()+b'\n'
        if frame_bytes is not None:
            if len(b)>frame_bytes:raise ValueError('public fixed frame capacity exceeded')
            b=b[:-1]+b' '*(frame_bytes-len(b))+b'\n'
        self.metrics['application_tx_bytes']+=len(b);self.local['application_tx_bytes']+=len(b);off=0
        while off<len(b):off+=self.action(lambda:self.ssl.write(b[off:]))
    def receive(self):
        while b'\n' not in self.buffer:self.buffer+=self.action(lambda:self.ssl.read(65536))
        b,self.buffer=self.buffer.split(b'\n',1);self.metrics['application_rx_bytes']+=len(b)+1;self.local['application_rx_bytes']+=len(b)+1;return json.loads(b,object_hook=read_fraction)
    def identity(self):
        cert=x509.load_der_x509_certificate(self.ssl.getpeercert(binary_form=True));return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    def close(self,op=None):
        if op:
            bucket=self.metrics.setdefault('by_op',{}).setdefault(op,blank())
            for k in ['tls_tx_bytes','tls_rx_bytes','application_tx_bytes','application_rx_bytes']:bucket[k]+=self.local[k]
            bucket['rpc_calls']+=1
        self.raw.close()

def context(credentials_dir,trust,server=False):
    c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT);c.check_hostname=False;c.verify_mode=ssl.CERT_REQUIRED;c.minimum_version=ssl.TLSVersion.TLSv1_3
    c.load_cert_chain(str(pathlib.Path(credentials_dir)/'public.pem'),str(pathlib.Path(credentials_dir)/'private.pem'));c.load_verify_locations(cafile=trust);return c

def gaussian():
    u=(secrets.randbits(53)+.5)/2**53;v=(secrets.randbits(53)+.5)/2**53;return math.sqrt(-2*math.log(u))*math.cos(2*math.pi*v)

def blank():return dict(tls_tx_bytes=0,tls_rx_bytes=0,application_tx_bytes=0,application_rx_bytes=0,rpc_calls=0,peer_cpu_seconds=0.)

def rpc(ctx,address,msg,metrics,expected=None,delay_ms=0,rate_bytes_s=0):
    if delay_ms:time.sleep(delay_ms/1000)
    if rate_bytes_s:time.sleep(len(json.dumps(msg))/rate_bytes_s)
    s=socket.create_connection(tuple(address),timeout=20);s.settimeout(30);ch=Channel(s,ctx,metrics)
    if expected is not None and ch.identity()!=str(expected):ch.close();raise ValueError('unexpected pinned peer identity')
    ch.send(msg,msg.get('_frame_request'));r=ch.receive();ch.close(msg['op']);metrics['rpc_calls']+=1
    if 'error' in r:raise RuntimeError(r['error'])
    return r

def dimension(cfg):return cfg.get('report_dimension',1)
def sum_reports(values,d=1):
    values=list(values)
    summer=sum if values and isinstance(values[0] if d==1 else values[0][0],Fraction) else math.fsum
    return summer(values) if d==1 else [summer(v[j] for v in values) for j in range(d)]
def weighted_reports(row,values,d=1):
    return sum_reports((Fraction(c)*v if d==1 and isinstance(v,Fraction) else c*v if d==1 else [(Fraction(c) if isinstance(x,Fraction) else c)*x for x in v] for c,v in zip(row,values)),d)

class Peer:
    def __init__(self,cfg,credentials_dir,trust,out):
        self.cfg=cfg;self.i=cfg['id'];self.out=pathlib.Path(out);self.metrics=blank();self.client=context(credentials_dir,trust);self.server=context(credentials_dir,trust,True);self.lock=threading.RLock();self.epoch=None;self.masks={};self.z=None;self.exposed=False;self.rho_spent=0.;self.history=[];self.state='IDLE';self.partial={};self.phase={};self.cpu0=time.process_time();self.stop=False
        self.runtime_identity={'python':sys.executable,'python_version':sys.version,'machine_id_sha256':hashlib.sha256(pathlib.Path('/etc/machine-id').read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'finite_reports_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('finite_reports.py').read_bytes()).hexdigest(),'input_sha256':hashlib.sha256(json.dumps(cfg['s'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'W_sha256':hashlib.sha256(json.dumps(cfg['W'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'finite_parameters':cfg.get('finite_parameters'),'cpu_affinity':sorted(os.sched_getaffinity(0)),'rng':'fresh OS CSPRNG via secrets; no secret coins logged'}
    def call(self,j,msg):
        if self.cfg.get('physical_frames'):
            req,resp={'mask':(512,128),'report':(128,1024),'partial':(128,1024)}[msg['op']]
            msg=dict(msg,_frame_request=req,_frame_response=resp)
        return rpc(self.client,self.cfg['addresses'][str(j)],msg,self.metrics,j,self.cfg.get('delay_ms',0),self.cfg.get('rate_bytes_s',0))
    def dispatch(self,msg,caller):
        op=msg['op']
        if op=='mask':
            j=int(caller)
            with self.lock:
                if self.state!='PREPARED' or msg['epoch']!=self.epoch or j>=self.i or str(j) not in self.cfg['neighbors']:raise ValueError('mask rejected before freeze / wrong epoch / nonpeer')
                if j in self.masks:raise ValueError('duplicate mask refused')
                # Fixed-width hidden payload avoids leaking magnitude through TLS record length.
                finite=self.cfg.get('finite_parameters')
                encoded=base64.b64decode(msg['coins_b'] if finite else msg['mask_f64'],validate=True)
                d=dimension(self.cfg)
                if finite:
                    width=finite['b']//8
                    if finite['b']%8 or len(encoded)!=width*d: raise ValueError('invalid fixed-width coins')
                    self.masks[j]=[int.from_bytes(encoded[t*width:(t+1)*width],'big') for t in range(d)]
                    return {'ok':True}
                if len(encoded)!=8*d:raise ValueError('invalid fixed-width mask')
                value=struct.unpack('!'+str(d)+'d',encoded)
                if not all(math.isfinite(x) for x in value):raise ValueError('nonfinite mask rejected')
                self.masks[j]=-value[0] if d==1 else [-x for x in value]
            return {'ok':True}
        if caller!='control' and op not in ['report','partial']:raise ValueError('controller-only operation')
        if op=='prepare':
            with self.lock:
                if self.state not in ['IDLE','FINISHED','ABORTED']:raise ValueError('unsafe in-epoch membership/prepare')
                if msg['epoch'] in [h['epoch'] for h in self.history]:raise ValueError('epoch reused')
                if self.cfg.get('finite_parameters'):
                    count=getattr(self,'prepared_attempts',0)
                    limit=self.cfg.get('max_prepared_attempts',round(self.cfg['rho_total']/self.cfg['rho_per_release']))
                    if count>=limit:raise ValueError('public attempt count exhausted')
                    if self.rho_spent+self.cfg['rho_per_release']>self.cfg['rho_total']*(1+1e-12): raise ValueError('attempt budget exhausted')
                    self.rho_spent+=self.cfg['rho_per_release']
                    self.prepared_attempts=count+1
                self.epoch=msg['epoch'];self.masks={};self.z=None;self.exposed=False;self.partial={};self.state='PREPARED';self.phase={};self.started=time.perf_counter()
            return {'ok':True,'state':self.state}
        if op=='setup':
            if self.state!='PREPARED':raise ValueError('membership not frozen')
            t=time.perf_counter();cpu=time.process_time();before=self.metrics.copy()
            for j,w in self.cfg['neighbors'].items():
                j=int(j)
                if self.i<j:
                    d=dimension(self.cfg);finite=self.cfg.get('finite_parameters')
                    if finite:
                        coins=[draw(finite) for _ in range(d)];width=finite['b']//8
                        self.call(j,{'op':'mask','epoch':self.epoch,'coins_b':base64.b64encode(b''.join(k.to_bytes(width,'big') for k in coins)).decode()})
                        with self.lock:self.masks[j]=coins
                        continue
                    rv=[gaussian()*math.sqrt(w) for _ in range(d)];r=rv[0] if d==1 else rv
                    self.call(j,{'op':'mask','epoch':self.epoch,'mask_f64':base64.b64encode(struct.pack('!'+str(d)+'d',*rv)).decode()})
                    with self.lock:self.masks[j]=r
            self.phase['setup_seconds']=time.perf_counter()-t;self.phase['setup_cpu_seconds']=time.process_time()-cpu;self.phase['setup_tls_tx']=self.metrics['tls_tx_bytes']-before['tls_tx_bytes'];self.phase['setup_tls_rx']=self.metrics['tls_rx_bytes']-before['tls_rx_bytes']
            return {'ok':True}
        if op=='release':
            with self.lock:
                if self.state!='PREPARED' or len(self.masks)!=len(self.cfg['neighbors']):raise ValueError('incomplete setup refused before release')
                # Input belongs only to this participant; controller receives noisy reports only.
                finite=self.cfg.get('finite_parameters')
                if finite:
                    t=time.perf_counter();cpu=time.process_time();d=dimension(self.cfg);inputs=[self.cfg['s']] if d==1 else self.cfg['s'];indices=[]
                    for coordinate in range(d):
                        masks=[(coins[coordinate],self.cfg['neighbors'][str(j)],1 if self.i<j else -1) for j,coins in self.masks.items()]
                        indices.append(encode_report(Fraction(inputs[coordinate]),(draw(finite),self.cfg['a']),masks,finite))
                    self.phase['encoding_seconds']=time.perf_counter()-t;self.phase['encoding_cpu_seconds']=time.process_time()-cpu
                    if any(k is None for k in indices):
                        self.state='NUMERICAL_ABORT';self.z=None
                        return {'ok':False,'status':'ABORT'}
                    values=[Fraction(k,1<<finite['grid_bits']) for k in indices]
                    self.z=values[0] if d==1 else values;self.state='RELEASED';self.exposed=True
                    return {'ok':True,'status':'READY'}
                if self.rho_spent+self.cfg['rho_per_release']>self.cfg.get('rho_total',math.inf)*(1+1e-12):raise ValueError('total exposed-release budget exhausted')
                d=dimension(self.cfg);noise=[gaussian()*math.sqrt(self.cfg['a']) for _ in range(d)]
                self.z=sum_reports([self.cfg['s'],noise[0] if d==1 else noise,*self.masks.values()],d)
                self.state='RELEASED';self.exposed=True;self.rho_spent+=self.cfg['rho_per_release']
            return {'ok':True}
        if op=='report':
            if self.state not in ['RELEASED','FINISHED']:raise ValueError('no valid report')
            return {'epoch':self.epoch,'z':self.z}
        if op=='aggregate':
            if self.state!='RELEASED':raise ValueError('invalid aggregate state')
            t=time.perf_counter();cpu=time.process_time();mode=msg['mode'];answers={}
            if mode=='sharing':
                for group in self.cfg['groups']:
                    if group['leader']==self.i:
                        partial=sum_reports((self.z if j==self.i else self.call(j,{'op':'report'})['z'] for j in group['members']),dimension(self.cfg))
                        self.partial[str(group['id'])]=partial
                self.phase['group_seconds']=time.perf_counter()-t;self.phase['group_cpu_seconds']=time.process_time()-cpu
                return {'ok':True,'group_seconds':self.phase['group_seconds']}
            if mode=='query':
                shared=msg['sharing'];cached_reports={self.i:self.z};cached_groups=dict(self.partial)
                for qi,row in enumerate(self.cfg['W']):
                    if qi%self.cfg['n']!=self.i:continue
                    terms=[];d=dimension(self.cfg)
                    if shared:
                        for g in self.cfg['groups']:
                            coef=row[g['members'][0]]
                            if coef:
                                key=str(g['id'])
                                if key not in cached_groups:cached_groups[key]=self.call(g['leader'],{'op':'partial','group':g['id']})['value']
                                coef=Fraction(coef) if self.cfg.get('finite_parameters') else coef
                                terms.append(coef*cached_groups[key] if d==1 else [coef*x for x in cached_groups[key]])
                    else:
                        for j,coef in enumerate(row):
                            if coef:
                                if j not in cached_reports:cached_reports[j]=self.call(j,{'op':'report'})['z']
                                coef=Fraction(coef) if self.cfg.get('finite_parameters') else coef
                                terms.append(coef*cached_reports[j] if d==1 else [coef*x for x in cached_reports[j]])
                    answers[str(qi)]=sum_reports(terms,d) if terms else (0. if d==1 else [0.]*d)
                self.phase['query_seconds']=time.perf_counter()-t;self.phase['query_cpu_seconds']=time.process_time()-cpu
                self.phase['epoch_query_completion_seconds']=time.perf_counter()-self.started
                return {'answers':answers}
        if op=='partial':return {'value':self.partial[str(msg['group'])]}
        if op=='finish' or op=='abort':
            self.state='FINISHED' if op=='finish' else 'ABORTED';self.history.append({'epoch':self.epoch,'state':self.state,'exposed':self.exposed,'rho_spent_cumulative':self.rho_spent,'duration_seconds':time.perf_counter()-self.started});self.masks={};self.partial={}
            return {'ok':True,'state':self.state,'rho_spent':self.rho_spent}
        if op=='metrics':return {'id':self.i,'hostname':socket.gethostname(),'pid':os.getpid(),'metrics':dict(self.metrics,peer_cpu_seconds=time.process_time()-self.cpu0,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),'history':self.history,'phase':self.phase,'runtime_identity':self.runtime_identity,'prepared_attempts':getattr(self,'prepared_attempts',0),'rho_spent':self.rho_spent}
        if op=='stop':self.stop=True;return {'ok':True}
        raise ValueError('unknown action')
    def connection(self,s):
        ch=None;op=None
        try:
            ch=Channel(s,self.server,self.metrics,True);msg=ch.receive();op=msg['op'];caller=ch.identity()
            try:result=self.dispatch(msg,caller)
            except Exception as e:result={'error':str(e)}
            ch.send(result,msg.get('_frame_response'))
        except Exception as e:
            with (self.out/'errors.log').open('a') as f:f.write(str(e)+'\n')
        finally:
            if ch:ch.close(op)
            else:s.close()
    def serve(self):
        self.out.mkdir(parents=True,exist_ok=True);s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(tuple(self.cfg['addresses'][str(self.i)]));s.listen(64);s.settimeout(1)
        (self.out/'ready.json').write_text(json.dumps({'id':self.i,'pid':os.getpid(),'hostname':socket.gethostname()}))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            while not self.stop:
                try:c,a=s.accept();c.settimeout(30);pool.submit(self.connection,c)
                except socket.timeout:continue
        s.close();(self.out/'metrics_final.json').write_text(json.dumps(self.dispatch({'op':'metrics'},'control'),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--credentials');p.add_argument('--identity');p.add_argument('--config');p.add_argument('--trust');p.add_argument('--out');args=p.parse_args()
    if args.identity is not None:credentials(args.credentials,args.identity)
    else:Peer(json.loads(pathlib.Path(args.config).read_text()),args.credentials,args.trust,args.out).serve()

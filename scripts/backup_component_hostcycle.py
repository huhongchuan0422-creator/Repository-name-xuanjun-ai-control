"""Candidate generic artifact cycle, host-injected trust; not deployed.

Construction requires trusted host code and operator-controlled configuration.
No CLI entrypoint. Remote pushes are prohibited except explicit local fixture mode.
Host must authenticate/re-authorize each request and return authoritative policy;
this module cannot manufacture that authority and ships no such host adapter.
"""
import contextlib, datetime, fcntl, hashlib, json, math, os, pathlib, re, shutil, subprocess, tempfile, uuid
import backup

ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$')
HEX64=re.compile(r'^[0-9a-f]{64}$')
CATEGORIES=frozenset(('SOURCE','ARTIFACT','CONTEXT','INSTALL','CONFIG_REFERENCE','AUTH_ENTRY'))
BINDING=('backup_cycle_id','tenant_id','task_id','attempt_id','handoff_id','handoff_version','snapshot_digest','provider_ref','contract_id','contract_version','contract_sha256')

class HostContract:
    def resolve(self, request):
        """Trusted host only: reauthorize and return (binding, artifact_specs).

        artifact_specs are exact (category, root Path, relative_path) triples
        selected by the authoritative versioned task/role contract. No N/A is
        inferred. Roots and identities come from host config, not request JSON.
        Must raise on denied/unknown, stale or revoked authority. Abstract default.
        """
        raise PermissionError('trusted host not connected')

def _binding_ok(b):
    return (isinstance(b,dict) and set(b)==set(BINDING) and
        isinstance(b['backup_cycle_id'],str) and re.fullmatch(r'cy-[0-9a-f]{32}',b['backup_cycle_id']) and
        all(isinstance(b[k],str) and ID.fullmatch(b[k]) for k in ('tenant_id','task_id','attempt_id','handoff_id','provider_ref','contract_id')) and
        all(type(b[k]) is int and b[k]>0 for k in ('handoff_version','contract_version')) and
        all(isinstance(b[k],str) and HEX64.fullmatch(b[k]) for k in ('snapshot_digest','contract_sha256')))

def _rel(value):
    if not isinstance(value,str) or not value or value.startswith('/') or any(x in ('','.','..') for x in value.split('/')): raise ValueError('bad artifact path')
    return pathlib.PurePosixPath(value)

class BackupComponent:
    def __init__(self, home, remote, branch, host, *, fixture_push=False):
        if not isinstance(host,HostContract) or type(host) is HostContract: raise ValueError('trusted host required')
        self.home=pathlib.Path(home).resolve();self.remote=str(remote);self.branch=branch;self.host=host
        if not isinstance(branch,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_-]{0,150}',branch) or '..' in branch: raise ValueError('invalid branch')
        self.fixture_push=fixture_push is True
        if self.fixture_push:
            rp=pathlib.Path(self.remote).resolve(strict=True)
            # Test permission is constrained to local bare repo inside the same
            # private direct temporary root as home; no URL, production push.
            temp=pathlib.Path(tempfile.gettempdir()).resolve()
            if self.home.parent != rp.parent or self.home.parent.parent != temp or rp.name!='remote.git' or not (rp/'objects').is_dir() or not (rp/'HEAD').is_file(): raise ValueError('local fixture only')
            st=self.home.parent.stat()
            if st.st_uid!=os.geteuid() or st.st_mode & 0o077: raise ValueError('private fixture required')
        # Existing parent is required; do not recursively create an unsynced tree.
        self.home.mkdir(mode=0o700,exist_ok=True);self.sync_dir(self.home.parent)
        (self.home/'cycles').mkdir(mode=0o700,exist_ok=True);self.sync_dir(self.home)
    @contextlib.contextmanager
    def locked(self):
        with (self.home/'run.lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            yield
    def sync_dir(self,path):
        fd=os.open(str(path),os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
        try:os.fsync(fd)
        finally:os.close(fd)
    def write_durable(self,path,data):
        with open(str(path),'wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
    def unlink_durable(self,path):
        path.unlink();self.sync_dir(path.parent)
    def orphaned(self):
        # A missing marker must not silently legalize incomplete/invalid cycles.
        for p in (self.home/'cycles').iterdir():
            if not p.is_dir() or p.is_symlink():return True
            try:
                r=json.loads((p/'record.json').read_text())
                if (not re.fullmatch(r'cy-[0-9a-f]{32}',p.name) or r.get('cycle_id')!=p.name or r.get('state')!='verified' or not _binding_ok(r.get('binding')) or not isinstance(r.get('manifest_sha256'),str) or not HEX64.fullmatch(r['manifest_sha256']) or not isinstance(r.get('result'),str) or not re.fullmatch(r'[0-9a-f]{40}',r['result']) or type(r.get('cycle_at')) not in (int,float) or not math.isfinite(r['cycle_at'])):return True
            except Exception:return True
        return False
    def settlement(self):
        path=self.home/'settlement.json'
        if not path.exists():return None
        data=json.loads(path.read_text())
        if (not isinstance(data,dict) or set(data)!={'cycle_id','state'} or
            not isinstance(data['cycle_id'],str) or not re.fullmatch(r'cy-[0-9a-f]{32}',data['cycle_id']) or
            data['state'] not in ('pending','settled')):raise ValueError('invalid settlement')
        return data
    def atomic(self,path,obj):
        fd,tmp=tempfile.mkstemp(prefix='.checkpoint-',dir=str(path.parent))
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,'w') as f:
                json.dump(obj,f,sort_keys=True,separators=(',',':'));f.write('\n');f.flush();os.fsync(f.fileno())
            os.replace(tmp,str(path));self.sync_dir(path.parent)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    def git(self,repo,*args):
        if args[0]=='push' and not self.fixture_push: raise PermissionError('production push disabled')
        p=subprocess.run(['git','-C',str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,universal_newlines=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},timeout=120)
        if p.returncode:raise RuntimeError('git operation failed')
        return p.stdout.strip()
    def remote_tip(self,repo):
        text=self.git(repo,'ls-remote','--heads','origin','refs/heads/'+self.branch)
        return text.split()[0] if text else None
    def verify_remote(self,repo,tip,manifest):
        self.git(repo,'fetch','-q','origin','refs/heads/'+self.branch)
        if self.git(repo,'rev-parse','FETCH_HEAD')!=tip:raise RuntimeError('remote moved')
        backup.check_tree(repo,tip)
        data=subprocess.run(['git','-C',str(repo),'show',tip+':manifest.json'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=30).stdout
        if backup.digest(data)!=manifest:raise RuntimeError('remote manifest mismatch')
    def cyclepath(self,cycle):
        if not isinstance(cycle,str) or not re.fullmatch(r'cy-[0-9a-f]{32}',cycle):raise ValueError('bad cycle')
        return self.home/'cycles'/cycle
    def plan(self,request):
        binding,specs=self.host.resolve(request)
        if not _binding_ok(binding) or not isinstance(specs,(tuple,list)) or not specs:raise ValueError('invalid host contract')
        # Host supplies explicit applicable artifacts. Empty plan or unspecified
        # role categories are UNKNOWN, never inferred N/A.
        return dict(binding),tuple(specs)
    def prepare(self,request):
        binding,specs=self.plan(request)
        with self.locked():
            settlement=self.settlement()
            if (self.home/'active.json').exists() or (self.home/'pending.json').exists() or self.orphaned() or (settlement and settlement['state']!='settled'):raise RuntimeError('reconciliation required')
            if settlement:
                # Re-establish directory durability before trusting visible settlement.
                self.sync_dir(self.home);self.sync_dir(self.cyclepath(settlement['cycle_id']))
            # cycle comes only from the authenticated host reservation returned by
            # HostContract.resolve, not a requester's proposed ID.
            cycle=binding['backup_cycle_id'];p=self.cyclepath(cycle)
            if p.exists():raise RuntimeError('cycle already exists')
            # Reserve before any cycle data/snapshot; preserve marker on errors.
            self.atomic(self.home/'active.json',{'cycle_id':cycle})
            p.mkdir(mode=0o700);self.sync_dir(p.parent)
            self.atomic(p/'record.json',{'state':'preparing','cycle_id':cycle,'binding':binding})
            files=[];seen=set()
            for spec in specs:
                if not isinstance(spec,(list,tuple)) or len(spec)!=3:raise ValueError('invalid artifact spec')
                category,root,rel=spec
                if not isinstance(category,str) or category not in CATEGORIES:raise ValueError('invalid category')
                relpath=_rel(rel);root=pathlib.Path(root).resolve(strict=True);src=root.joinpath(*relpath.parts)
                if any(root.joinpath(*relpath.parts[:i]).is_symlink() for i in range(1,len(relpath.parts)+1)) or not src.is_file():raise ValueError('invalid artifact')
                data=src.read_bytes()
                if b'\x00' in data or any(backup.matched(n,pat,data) for n,pat in backup.PATTERNS):raise ValueError('sensitive or binary artifact refused')
                # Numeric internal paths avoid persisting user paths or categories as paths.
                name='artifact/%06d'%len(files)
                if (str(root),rel) in seen:raise ValueError('duplicate artifact')
                seen.add((str(root),rel));dst=p/'snapshot'/name;dst.parent.mkdir(parents=True,exist_ok=True);self.write_durable(dst,data)
                files.append({'category':category,'path':name,'sha256':backup.digest(data)})
            manifest={'version':1,'contract_sha256':binding['contract_sha256'],'artifacts':files}
            self.write_durable(p/'manifest.json',(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode())
            # Bytes first; then every new containing directory bottom-up.
            self.sync_dir(p/'snapshot'/'artifact');self.sync_dir(p/'snapshot');self.sync_dir(p)
            record={'state':'prepared','cycle_id':cycle,'binding':binding,'manifest_sha256':backup.digest((p/'manifest.json').read_bytes()),'cycle_at':datetime.datetime.now(datetime.timezone.utc).timestamp()}
            self.atomic(p/'record.json',record);return cycle
    def _publish(self, run, receipt, expected):
        pending_path=self.home/'pending.json'; baseline_path=self.home/'baseline.json'
        with tempfile.TemporaryDirectory(prefix='git-',dir=self.home) as tmp:
            repo=pathlib.Path(tmp); self.git(repo,'init','-q'); self.git(repo,'config','user.name','huhongchuan0422-creator'); self.git(repo,'config','user.email','332398908+huhongchuan0422-creator@users.noreply.github.com'); self.git(repo,'config','credential.helper','!gh auth git-credential'); self.git(repo,'remote','add','origin',self.remote)
            tip=self.remote_tip(repo)
            baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else None
            if pending_path.exists():
                pending=json.loads(pending_path.read_text())
                if tip==pending['expected']:
                    self.verify_remote(repo,tip,pending['manifest_sha256'])
                    baseline={'tip':tip,'manifest_sha256':pending['manifest_sha256']}
                    self.atomic(baseline_path,baseline); self.unlink_durable(pending_path)
                    receipt['reconciliation']='previous-push-arrived'
                elif tip==pending['base']:
                    if tip is not None and (not baseline or baseline['tip']!=tip): raise RuntimeError('pending base is not trusted baseline')
                    self.unlink_durable(pending_path); receipt['reconciliation']='previous-push-not-arrived'
                else: raise RuntimeError('pending push remote diverged; reconciliation required')
            if tip:
                if not baseline or baseline['tip']!=tip: raise RuntimeError('existing branch is not this task verified baseline')
                self.verify_remote(repo,tip,baseline['manifest_sha256'])
                self.git(repo,'checkout','-q','-b','snapshot','FETCH_HEAD')
            else:
                if baseline: raise RuntimeError('verified branch missing; reconcile before writing')
                if expected!=receipt['manifest_sha256']: raise RuntimeError('initial push requires matching reviewed manifest hash')
                self.git(repo,'checkout','-q','--orphan','snapshot')
            old=repo/'snapshot'
            if old.exists(): shutil.rmtree(old)
            shutil.copytree(run/'snapshot',old); shutil.copyfile(run/'manifest.json',repo/'manifest.json')
            self.git(repo,'add','-A','--','snapshot','manifest.json')
            diff=subprocess.run(['git','-C',str(repo),'diff','--cached','--quiet']).returncode
            if diff not in (0,1): raise RuntimeError('git diff failed')
            if not diff:
                receipt.update({'base':tip,'result':tip,'changed':False,'remote_verified':True}); return
            self.git(repo,'commit','-q','-m','Backup reviewed source snapshot'); result=self.git(repo,'rev-parse','HEAD')
            self.atomic(pending_path,{'base':tip,'expected':result,'manifest_sha256':receipt['manifest_sha256']})
            try:
                self.git(repo,'push','origin','HEAD:refs/heads/'+self.branch)
            except (Exception,subprocess.TimeoutExpired) as error:
                try:
                    current=self.remote_tip(repo)
                    receipt['push_failure_remote_state']='arrived' if current==result else ('not-arrived' if current==tip else 'diverged')
                except Exception: receipt['push_failure_remote_state']='unknown'
                raise RuntimeError('push failed or timed out; pending saved; reconcile before retry') from error
            readback=self.remote_tip(repo)
            if readback!=result: raise RuntimeError('remote SHA mismatch; pending retained')
            self.verify_remote(repo,result,receipt['manifest_sha256'])
            self.atomic(baseline_path,{'tip':result,'manifest_sha256':receipt['manifest_sha256']}); self.unlink_durable(pending_path)
            receipt.update({'base':tip,'result':result,'changed':True,'remote_verified':True})
    def _files(self,p):
        doc=json.loads((p/'manifest.json').read_text()); rows=doc.get('artifacts')
        if not isinstance(rows,list) or not rows:raise ValueError('bad manifest')
        expected={}
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'category','path','sha256'} or row['category'] not in CATEGORIES:raise ValueError('bad manifest')
            path=row['path'];sha=row['sha256']
            if not isinstance(path,str) or not re.fullmatch(r'artifact/[0-9]{6}',path) or path in expected or not isinstance(sha,str) or not HEX64.fullmatch(sha):raise ValueError('bad manifest')
            expected[path]=sha
        actual={}
        for f in (p/'snapshot').rglob('*'):
            if f.is_symlink():raise ValueError('symlink')
            if f.is_file():actual[f.relative_to(p/'snapshot').as_posix()]=backup.digest(f.read_bytes())
        if actual!=expected:raise ValueError('snapshot mismatch')
        return expected
    def _readback(self,p,record):
        files=self._files(p)
        if backup.digest((p/'manifest.json').read_bytes())!=record['manifest_sha256']:raise ValueError('manifest mismatch')
        with tempfile.TemporaryDirectory(prefix='readback-',dir=str(self.home)) as repo:
            self.git(repo,'init','-q');self.git(repo,'config','credential.helper','!gh auth git-credential');self.git(repo,'remote','add','origin',self.remote)
            if self.remote_tip(repo)!=record['result']:raise ValueError('remote moved')
            self.verify_remote(repo,record['result'],record['manifest_sha256'])
            entries=self.git(repo,'ls-tree','-r','--name-only',record['result']).splitlines()
            if set(entries)!={'manifest.json'}|{'snapshot/'+name for name in files}:raise ValueError('remote tree mismatch')
            for name,sha in files.items():
                data=subprocess.run(['git','-C',repo,'show',record['result']+':snapshot/'+name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,timeout=30).stdout
                if backup.digest(data)!=sha:raise ValueError('remote artifact mismatch')
            if self.remote_tip(repo)!=record['result']:raise ValueError('remote moved')
    def publish_candidate(self,request,cycle):
        if not self.fixture_push:raise PermissionError('production push disabled')
        binding,_=self.plan(request)
        with self.locked():
            p=self.cyclepath(cycle);r=json.loads((p/'record.json').read_text())
            if r.get('cycle_id')!=cycle or r.get('binding')!=binding or r.get('state') not in ('prepared','verified'):raise ValueError('cycle binding mismatch')
            if backup.digest((p/'manifest.json').read_bytes())!=r['manifest_sha256']:raise ValueError('manifest mismatch')
            self._files(p)
            active=self.home/'active.json';pending=self.home/'pending.json'
            if not active.exists() or json.loads(active.read_text())!={'cycle_id':cycle}:raise RuntimeError('reconciliation required')
            if r['state']=='verified':
                # Never repush or silently finish a verified/unknown cleanup.
                raise RuntimeError('settlement required')
            receipt={'manifest_sha256':r['manifest_sha256']}
            self._publish(p,receipt,r['manifest_sha256'])
            if receipt.get('remote_verified') is not True:raise RuntimeError('readback absent')
            r.update({'state':'verified','result':receipt['result']})
            self._readback(p,r)
            self.atomic(p/'record.json',r)
            # Durable pre-marker survives active unlink and failed home fsync.
            self.atomic(self.home/'settlement.json',{'cycle_id':cycle,'state':'pending'})
            self.unlink_durable(active)
    def reconcile_settlement(self,request,cycle):
        """Explicit same-cycle readback and settlement, never issues a push."""
        binding,_=self.plan(request)
        with self.locked():
            marker=self.settlement();active=self.home/'active.json'
            if marker and marker['state']=='pending' and marker['cycle_id']!=cycle:raise RuntimeError('unknown settlement')
            p=self.cyclepath(cycle);r=json.loads((p/'record.json').read_text())
            if r.get('cycle_id')!=cycle or r.get('state')!='verified' or r.get('binding')!=binding or (self.home/'pending.json').exists():raise RuntimeError('reconciliation required')
            if active.exists() and json.loads(active.read_text())!={'cycle_id':cycle}:raise RuntimeError('unknown active')
            if (not marker or marker['cycle_id']!=cycle) and not active.exists():raise RuntimeError('unknown settlement')
            self._readback(p,r)
            if not marker or marker['cycle_id']!=cycle:
                self.atomic(self.home/'settlement.json',{'cycle_id':cycle,'state':'pending'})
            if active.exists():self.unlink_durable(active)
            # Re-sync even when active is already absent: absence alone does not
            # prove a previous failed unlink-directory fsync reached the disk.
            self.sync_dir(self.home);self.sync_dir(p)
            try:
                self.atomic(self.home/'settlement.json',{'cycle_id':cycle,'state':'settled'})
            except Exception:
                # Preserve a visible pending state where possible; if the storage
                # refuses all writes, the filesystem cannot guarantee recovery.
                try:self.atomic(self.home/'settlement.json',{'cycle_id':cycle,'state':'pending'})
                except Exception:pass
                raise
    def checkpoint_status(self,request):
        """Read-only diagnosis; never removes or replays an unknown checkpoint."""
        try:
            binding,_=self.plan(request)
            with self.locked():
                active=self.home/'active.json';pending=self.home/'pending.json'
                marker=self.settlement()
                if marker and marker['state']=='pending':
                    rec=json.loads((self.cyclepath(marker['cycle_id'])/'record.json').read_text())
                    if rec.get('binding')!=binding or rec.get('state')!='verified':return {'state':'UNKNOWN_CHECKPOINT'}
                    return {'state':'SETTLEMENT_REQUIRED','cycle_id':marker['cycle_id']}
                if marker and marker['state']=='settled':
                    self.sync_dir(self.home);self.sync_dir(self.cyclepath(marker['cycle_id']))
                if not active.exists():return {'state':'UNKNOWN_PENDING' if pending.exists() else ('UNKNOWN_CHECKPOINT' if self.orphaned() else 'IDLE')}
                a=json.loads(active.read_text());cycle=a['cycle_id'];p=self.cyclepath(cycle)
                if set(a)!={'cycle_id'} or not (p/'record.json').exists():return {'state':'UNKNOWN_CHECKPOINT'}
                r=json.loads((p/'record.json').read_text())
                if r.get('cycle_id')!=cycle or r.get('binding')!=binding:return {'state':'UNKNOWN_CHECKPOINT'}
                if r.get('state')=='preparing':return {'state':'INTERRUPTED_PREPARATION','cycle_id':cycle}
                if r.get('state') in ('prepared','verified'):return {'state':'RECONCILIATION_REQUIRED','cycle_id':cycle}
                return {'state':'UNKNOWN_CHECKPOINT'}
        except Exception:return {'state':'UNKNOWN_CHECKPOINT'}
    def assess(self,request,cycle,manifest_sha256,now):
        """Read bound receipt only. Never returns COMPLETE or host authorization."""
        try:
            binding,_=self.plan(request)
            with self.locked():
                p=self.cyclepath(cycle);r=json.loads((p/'record.json').read_text())
                marker=self.settlement()
                if (self.home/'active.json').exists() or (self.home/'pending.json').exists() or (marker and marker['state']!='settled'):return None
                if marker:self.sync_dir(self.home)
                if r.get('state')!='verified' or r.get('cycle_id')!=cycle or r.get('binding')!=binding or r.get('manifest_sha256')!=manifest_sha256:return None
                age=now-r['cycle_at']
                if not 0<=age<=300:return None
                self._readback(p,r)
                categories=sorted(set(x['category'] for x in json.loads((p/'manifest.json').read_text())['artifacts']))
                return {'cycle_id':cycle,'manifest_sha256':r['manifest_sha256'],'result':r['result'],'cycle_at':r['cycle_at'],'artifact_categories':categories,'state':'ARTIFACT_READBACK'}
        except Exception:return None

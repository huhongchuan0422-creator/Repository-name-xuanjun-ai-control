#!/usr/bin/env python3
"""Explicit first-party source snapshot; publishing requires reviewed initial snapshot."""
import argparse, datetime, fcntl, hashlib, json, os, pathlib, re, shutil, subprocess, sys, tempfile, uuid
from handoff import envelope

HOME = pathlib.Path(__file__).resolve().parent
SOURCES = {
    'task-center': pathlib.Path('/home/xuanjun_dev/.openclaw/workspace-developer/project-task-center-blackbox'),
    'integration-tc-144a': pathlib.Path('/home/xuanjun_dev/.openclaw/workspace-developer/deliveries/task-delivery-ledger-354-20261116/integration-tc-144a'),
}
REMOTE = 'https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control.git'
BRANCH = 'backup/source-code-1889'
PATTERNS = [
    ('private-key', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----')),
    ('github-token', re.compile(rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b')),
    ('aws-key', re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')),
    ('credential-assignment', re.compile(rb'''(?i)["']?\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|secret)["']?\s*[:=]\s*["'][^"'\r\n]{8,}["']''')),
    ('bearer', re.compile(rb'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}')),
    ('credential-uri', re.compile(rb'(?i)\b(?:https?|postgres(?:ql)?|mysql|redis|mongodb(?:\+srv)?|amqp)://[^\s/@:]+:[^\s/@]+@')),
    ('email-unclassified', re.compile(rb'(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b')),
    ('phone-unclassified', re.compile(rb'(?<!\d)(?:\+86[ -]?)?1[3-9]\d{9}(?!\d)')),
]

def digest(data): return hashlib.sha256(data).hexdigest()
def matched(name, pattern, data):
    if name == 'email-unclassified':
        # Reserved documentation domains are not real contact data.
        return any(m.group().lower().split(b'@')[-1] not in (b'example.com',b'example.org',b'example.net',b'example.invalid') for m in pattern.finditer(data))
    return bool(pattern.search(data))
def atomic(path, obj):
    tmp=path.with_name(path.name+'.tmp'); tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n'); os.replace(tmp,path)
def git(repo, *args):
    p=subprocess.run(['git','-C',str(repo),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},timeout=120)
    if p.returncode: raise RuntimeError('git '+args[0]+' failed (exit '+str(p.returncode)+')')
    return p.stdout.strip()
def remote_tip(repo):
    text=git(repo,'ls-remote','--heads','origin','refs/heads/'+BRANCH)
    return text.split()[0] if text else None

def check_tree(repo, commit):
    entries=git(repo,'ls-tree','-r',commit).splitlines()
    if not entries: raise RuntimeError('empty remote tree')
    manifest=False
    for entry in entries:
        meta,path=entry.split('\t',1); mode,typ,_=meta.split()
        if mode != '100644' or typ != 'blob' or not (path=='manifest.json' or path.startswith('snapshot/')):
            raise RuntimeError('remote tree contains unexpected path or mode')
        if path=='manifest.json': manifest=True
    if not manifest: raise RuntimeError('remote manifest missing')

def verify_remote(repo, tip, expected_manifest):
    git(repo,'fetch','-q','origin','refs/heads/'+BRANCH)
    if git(repo,'rev-parse','FETCH_HEAD') != tip: raise RuntimeError('remote moved during readback')
    check_tree(repo,tip)
    data=subprocess.check_output(['git','-C',str(repo),'show',tip+':manifest.json'])
    if digest(data)!=expected_manifest: raise RuntimeError('remote manifest hash mismatch')

def snapshot(run):
    allow=json.loads((HOME/'allowlist.json').read_text())
    if set(allow)!=set(SOURCES): raise ValueError('unexpected source labels')
    dest=run/'snapshot'; dest.mkdir(); files=[]; skipped=[]
    for label,root in SOURCES.items():
        tracked=set(x.decode() for x in subprocess.check_output(['git','-C',str(root),'ls-files','-z','--','scripts/','tests/','demos/']).split(b'\0') if x)
        for kind in ('tracked','wip_untracked'):
          for rel in sorted(set(allow[label][kind])):
            p=pathlib.PurePosixPath(rel)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] not in ('scripts','tests','demos') or (kind=='tracked' and rel not in tracked):
                skipped.append({'source':label,'path':rel,'reason':'not-tracked-or-invalid'}); continue
            src=root.joinpath(*p.parts)
            try:
                if any(root.joinpath(*p.parts[:i]).is_symlink() for i in range(1,len(p.parts)+1)) or not src.is_file():
                    skipped.append({'source':label,'path':rel,'reason':'missing-or-symlink'}); continue
                data=src.read_bytes()
            except OSError:
                skipped.append({'source':label,'path':rel,'reason':'unreadable'}); continue
            reasons=[name for name,pattern in PATTERNS if matched(name,pattern,data)]
            if b'\x00' in data: reasons.append('binary')
            if reasons:
                skipped.append({'source':label,'path':rel,'reason':','.join(reasons)}); continue
            target=dest/label/rel; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
            files.append({'source':label,'path':rel,'sha256':digest(data)})
    if not files: raise RuntimeError('no eligible source files')
    manifest={'version':2,'files':files,'excluded':skipped,'coverage':'explicit allowlist; current tracked bytes plus individually listed untracked WIP; new paths not automatic','exclusions':['unlisted files','git history','bundles','memory','evidence','deliveries','logs','cache','node_modules','production configuration','credentials','customer data','private sources'],'note':'Limited pattern checks do not prove absence of secrets or customer data.'}
    (run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    return files,skipped

def publish(run, receipt, expected):
    pending_path=HOME/'pending.json'; baseline_path=HOME/'baseline.json'
    with tempfile.TemporaryDirectory(prefix='git-',dir=HOME) as tmp:
        repo=pathlib.Path(tmp); git(repo,'init','-q'); git(repo,'config','user.name','huhongchuan0422-creator'); git(repo,'config','user.email','332398908+huhongchuan0422-creator@users.noreply.github.com'); git(repo,'config','credential.helper','!gh auth git-credential'); git(repo,'remote','add','origin',REMOTE)
        tip=remote_tip(repo)
        baseline=json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        if pending_path.exists():
            pending=json.loads(pending_path.read_text())
            if tip==pending['expected']:
                verify_remote(repo,tip,pending['manifest_sha256'])
                baseline={'tip':tip,'manifest_sha256':pending['manifest_sha256']}
                atomic(baseline_path,baseline); pending_path.unlink()
                receipt['reconciliation']='previous-push-arrived'
            elif tip==pending['base']:
                if tip is not None and (not baseline or baseline['tip']!=tip): raise RuntimeError('pending base is not trusted baseline')
                pending_path.unlink(); receipt['reconciliation']='previous-push-not-arrived'
            else: raise RuntimeError('pending push remote diverged; reconciliation required')
        if tip:
            if not baseline or baseline['tip']!=tip: raise RuntimeError('existing branch is not this task verified baseline')
            verify_remote(repo,tip,baseline['manifest_sha256'])
            git(repo,'checkout','-q','-b','snapshot','FETCH_HEAD')
        else:
            if baseline: raise RuntimeError('verified branch missing; reconcile before writing')
            if expected!=receipt['manifest_sha256']: raise RuntimeError('initial push requires matching reviewed manifest hash')
            git(repo,'checkout','-q','--orphan','snapshot')
        old=repo/'snapshot'
        if old.exists(): shutil.rmtree(old)
        shutil.copytree(run/'snapshot',old); shutil.copyfile(run/'manifest.json',repo/'manifest.json')
        git(repo,'add','-A','--','snapshot','manifest.json')
        diff=subprocess.run(['git','-C',str(repo),'diff','--cached','--quiet']).returncode
        if diff not in (0,1): raise RuntimeError('git diff failed')
        if not diff:
            receipt.update({'base':tip,'result':tip,'changed':False,'remote_verified':True}); return
        git(repo,'commit','-q','-m','Backup reviewed source snapshot'); result=git(repo,'rev-parse','HEAD')
        atomic(pending_path,{'base':tip,'expected':result,'manifest_sha256':receipt['manifest_sha256']})
        try:
            git(repo,'push','origin','HEAD:refs/heads/'+BRANCH)
        except (Exception,subprocess.TimeoutExpired) as error:
            try:
                current=remote_tip(repo)
                receipt['push_failure_remote_state']='arrived' if current==result else ('not-arrived' if current==tip else 'diverged')
            except Exception: receipt['push_failure_remote_state']='unknown'
            raise RuntimeError('push failed or timed out; pending saved; reconcile before retry') from error
        readback=remote_tip(repo)
        if readback!=result: raise RuntimeError('remote SHA mismatch; pending retained')
        verify_remote(repo,result,receipt['manifest_sha256'])
        atomic(baseline_path,{'tip':result,'manifest_sha256':receipt['manifest_sha256']}); pending_path.unlink()
        receipt.update({'base':tip,'result':result,'changed':True,'remote_verified':True})

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--push',action='store_true'); parser.add_argument('--expected-manifest-sha256'); args=parser.parse_args()
    if args.push:
        print(json.dumps({'status':'blocked','reason':'candidate is not authorized to publish'})); return 1
    HOME.mkdir(mode=0o700,exist_ok=True)
    cycle_id=uuid.uuid4().hex
    receipt={'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'mode':'dry-run','source_status':'not_started','status':'incomplete', 'cycle_id':cycle_id}
    with open(HOME/'run.lock','a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status':'skipped','reason':'already-running'})); return 1
        pending=(HOME/'pending.json').exists()
        try:
            if pending:
                receipt['source_status']='reconciliation_required'
            else:
                run=pathlib.Path(tempfile.mkdtemp(prefix='snapshot-',dir=HOME)); os.chmod(run,0o700)
                files,skipped=snapshot(run)
                receipt.update({'source_status':'local_snapshot_only','files':len(files),
                    'excluded_count':len(skipped),'manifest_sha256':digest((run/'manifest.json').read_bytes())})
        except Exception:
            # Do not echo arbitrary exception text or filesystem contents.
            receipt['source_status']='failed'
        receipt['handoff']=envelope(cycle_id,receipt.get('manifest_sha256'),None,False,pending=pending)
        # One atomic record is both receipt and consumer-readable alert: no split commit.
        atomic(HOME/'candidate-cycle-latest.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False))
    return 1

if __name__=='__main__': sys.exit(main())

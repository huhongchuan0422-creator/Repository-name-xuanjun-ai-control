"""Read-only adapter for the existing 1889 producer; not a backup or scheduler."""
import datetime, fcntl, hashlib, json, os, pathlib, re, subprocess, tempfile

ORIGINAL = pathlib.Path('/home/xuanjun_dev/.openclaw/workspace-platform-engineer/deliveries/source-backup-1889')
REMOTE = 'https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control.git'
BRANCH = 'backup/source-code-1889'
SCRIPT_SHA = '215a49d28443514e6d5348ae09330f5ca66675c9de04ac41a16c5eb0ba34662f'
HEX40 = re.compile(r'^[0-9a-f]{40}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')

def _git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, timeout=30, universal_newlines=True,
                          env={**os.environ, "GIT_TERMINAL_PROMPT":"0"}).stdout.strip()

def _remote_verify(tip, manifest):
    with tempfile.TemporaryDirectory(prefix='source-evidence-') as tmp:
        _git(tmp, 'init', '-q')
        _git(tmp, 'config', 'credential.helper', '!gh auth git-credential')
        _git(tmp, 'remote', 'add', 'origin', REMOTE)
        line = _git(tmp, 'ls-remote', '--heads', 'origin', 'refs/heads/'+BRANCH)
        if line.split() != [tip, 'refs/heads/'+BRANCH]: return False
        _git(tmp, 'fetch', '-q', 'origin', 'refs/heads/'+BRANCH)
        if _git(tmp, 'rev-parse', 'FETCH_HEAD') != tip: return False
        entries = _git(tmp, 'ls-tree', '-r', tip).splitlines()
        seen = False
        for entry in entries:
            meta, path = entry.split('\t', 1)
            mode, kind, _ = meta.split()
            if mode != '100644' or kind != 'blob' or not (path == 'manifest.json' or path.startswith('snapshot/')): return False
            seen |= path == 'manifest.json'
        if not seen: return False
        data = subprocess.run(['git','-C',tmp,'show',tip+':manifest.json'],check=True,
                              stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30).stdout
        return hashlib.sha256(data).hexdigest() == manifest

def collect():
    """Fixed local producer plus remote readback; never takes caller evidence.

    Its timestamp is the producer's own cycle identity, not the candidate UUID.
    Source freshness is bounded, not proof of same-cycle full backup.
    """
    out = {'status': 'unknown', 'reason': 'unavailable'}
    try:
        if hashlib.sha256((ORIGINAL/'backup.py').read_bytes()).hexdigest() != SCRIPT_SHA:
            return {'status':'unknown','reason':'producer_version_mismatch'}
        # Match producer lock to avoid observing its pending/baseline transaction midway.
        with (ORIGINAL/'run.lock').open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            if (ORIGINAL/'pending.json').exists(): return {'status':'unknown','reason':'reconciliation_required'}
            latest=json.loads((ORIGINAL/'latest.json').read_text())
            baseline=json.loads((ORIGINAL/'baseline.json').read_text())
            raw_time=latest['time_utc']
            if not isinstance(raw_time,str) or not raw_time.endswith('+00:00'): return {'status':'unknown','reason':'invalid_receipt'}
            stamp=datetime.datetime.strptime(raw_time[:-6], '%Y-%m-%dT%H:%M:%S.%f').replace(tzinfo=datetime.timezone.utc)
            age=(datetime.datetime.now(datetime.timezone.utc)-stamp).total_seconds()
            if age < 0 or age > 300: return {'status':'unknown','reason':'expired'}
            tip=latest.get('result'); manifest=latest.get('manifest_sha256')
            if not isinstance(tip,str) or not HEX40.fullmatch(tip) or not isinstance(manifest,str) or not HEX64.fullmatch(manifest): return {'status':'unknown','reason':'invalid_receipt'}
            if latest.get('status') != 'ok' or latest.get('mode') != 'push' or latest.get('branch') != BRANCH or latest.get('remote_verified') is not True: return {'status':'unknown','reason':'invalid_receipt'}
            if baseline != {'tip':tip,'manifest_sha256':manifest}: return {'status':'unknown','reason':'baseline_mismatch'}
        if not _remote_verify(tip,manifest): return {'status':'unknown','reason':'remote_mismatch'}
        with (ORIGINAL/'run.lock').open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            if (ORIGINAL/'pending.json').exists() or json.loads((ORIGINAL/'latest.json').read_text()) != latest or json.loads((ORIGINAL/'baseline.json').read_text()) != baseline:
                return {'status':'unknown','reason':'producer_changed'}
            out={'status':'verified','producer_time_utc':stamp.isoformat(),'result':tip,'manifest_sha256':manifest,'producer_sha256':SCRIPT_SHA,'binding':'original_producer_cycle_not_candidate_snapshot'}
    except Exception:
        pass
    return out

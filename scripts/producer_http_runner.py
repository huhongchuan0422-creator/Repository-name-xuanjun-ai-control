"""Fixed offline producer HTTP observation. This module is not an MCP tool.

Test assets are pinned by the host-owned reference, not supplied by the model.
This function returns an observation, not canonical authority by itself.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tarfile
import tempfile
from producer_http_contract import REFERENCE_SHA256
from task_supervisor import Supervisor, canonical
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from reusable_scheduler_cli import demo_graph

IMAGE='sha256:896edfbcbf0c29ad15681617a8886cb9871b7f24c5fde4606114c8ee6bfe4c70'
KEY=b'0123456789abcdef0123456789abcdef'


def run_producer_http(source):
    """Compatibility API: return the original hash-only observation."""
    observation, _ = run_producer_http_with_artifact(source)
    return observation


def run_producer_http_with_artifact(source):
    """Return the observation and exact bounded stdout bytes; not an attestation."""
    if type(source) is not bytes or not 1 <= len(source) <= 131072:
        raise ValueError('BOUNDED_PRODUCER_SOURCE_REQUIRED')
    assets=Path(__file__).resolve().parents[1]/'producer-test-assets'
    try:
        reference=json.loads((assets/'test-reference.json').read_text())
        if hashlib.sha256(canonical(reference).encode()).hexdigest()!=REFERENCE_SHA256:
            raise ValueError('PRODUCER_TEST_REFERENCE_MISMATCH')
        manifest=(assets/'runtime-files.sha256').read_bytes()
        if hashlib.sha256(manifest).hexdigest()!=reference['runtime_files_sha256']:
            raise ValueError('PRODUCER_TEST_FILES_MISMATCH')
        controller=(assets/'controller.py').read_bytes()
        if hashlib.sha256(controller).hexdigest()!=reference['controller_sha256'] or reference['image']!=IMAGE:
            raise ValueError('PRODUCER_TEST_CONTROLLER_MISMATCH')
        files=[]
        prefixes=('deps/','base-scripts/')
        for row in manifest.decode('ascii').splitlines():
            digest,relative=row.split('  ',1)
            if not re.fullmatch('[0-9a-f]{64}',digest) or not relative.startswith(prefixes) or '/..' in relative:
                raise ValueError('PRODUCER_TEST_FILES_MISMATCH')
            path=assets/relative
            if path.is_symlink() or not path.is_file():raise ValueError('PRODUCER_TEST_FILES_MISMATCH')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('PRODUCER_TEST_FILES_MISMATCH')
            if relative.startswith(prefixes[0]):name=relative
            else:name='scripts/'+relative[len(prefixes[1]):]
            files.append((name,source if name=='scripts/task_center_app.py' else raw))
        if sum(name=='scripts/task_center_app.py' for name,_ in files)!=1:
            raise ValueError('PRODUCER_TEST_FILES_MISMATCH')
    except (OSError,ValueError,KeyError,UnicodeError):
        raise ValueError('PINNED_PRODUCER_TEST_UNAVAILABLE')
    with tempfile.TemporaryDirectory(prefix='producer-http-fixture-') as temp:
        db=os.path.join(temp,'fixture.sqlite');supervisor=Supervisor(db)
        try:
            auth=TestTenantAuthority(KEY);GatewayKernel(supervisor,auth).register_graph(auth.issue('tenant-a','seed'),demo_graph('tenant-a'))
            supervisor.db.execute("UPDATE tasks SET next_action='fixture-private-sentinel' WHERE task_id='demo-b'")
            supervisor.db.commit();supervisor.db.execute('PRAGMA wal_checkpoint(FULL)')
        finally:supervisor.close()
        with sqlite3.connect(db) as connection:connection.execute('PRAGMA journal_mode=DELETE')
        files.append(('fixture.sqlite',Path(db).read_bytes()))
        with tempfile.TemporaryFile() as payload:
            with tarfile.open(fileobj=payload,mode='w') as tar:
                for name,raw in files:
                    info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;tar.addfile(info,io.BytesIO(raw))
            payload.seek(0)
            cidfile=os.path.join(temp,'cid')
            cmd=['/usr/bin/docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL','--cap-add','SETUID','--cap-add','SETGID','--security-opt','no-new-privileges','--pids-limit','32','--memory','256m','--cpus','1','--tmpfs','/work:rw,nosuid,nodev,noexec,size=64m,mode=0755','--tmpfs','/libs:rw,exec,nosuid,nodev,size=32m,mode=0755','--cidfile',cidfile,'-i',IMAGE,'python','-I','-B','-c',controller.decode('utf-8')]
            try:
                with tempfile.TemporaryFile() as output:
                    p=subprocess.run(['/usr/bin/prlimit','--fsize=65536:65536','--']+cmd,stdin=payload,stdout=output,stderr=subprocess.DEVNULL,timeout=40,env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent'})
                    output.seek(0);out=output.read(1025)
            except subprocess.TimeoutExpired:
                if os.path.isfile(cidfile):
                    cid=Path(cidfile).read_text().strip()
                    if re.fullmatch('[0-9a-f]{64}',cid):subprocess.run(['/usr/bin/docker','rm','-f',cid],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
                raise ValueError('PRODUCER_HTTP_TEST_TIMEOUT')
            if p.returncode or len(out)>1024:raise ValueError('PRODUCER_HTTP_TEST_UNAVAILABLE')
            try:result=json.loads(out.decode('ascii'))
            except (ValueError,UnicodeError):raise ValueError('PRODUCER_HTTP_TEST_UNAVAILABLE')
            if not isinstance(result,dict) or set(result)!={'state','detail'}:raise ValueError('PRODUCER_HTTP_TEST_UNAVAILABLE')
            return ({'result':result,'artifact_sha256':hashlib.sha256(out).hexdigest(),
                     'test_reference_sha256':REFERENCE_SHA256,'source_sha256':hashlib.sha256(source).hexdigest()}, out)

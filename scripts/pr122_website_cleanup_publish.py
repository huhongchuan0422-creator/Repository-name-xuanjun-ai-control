"""Exact-site adapter for the original PR122 publisher; no installer fallback.

build only produces a candidate. prepare/activate/check require the frozen
package and archive SHA returned by build. UNKNOWN is never retried here.
"""
import argparse
import copy
import fcntl
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tarfile

BASE = Path('/var/www/wenwenwenyiyiyi.work')
OLD = 'pr122-navigation-integrated-20261110'
RID = 'pr122-website-cleanup-20261112-01'
STAGE = Path('/root') / RID
PUBLISHER = Path('/usr/local/libexec/pr122_website_release.py')
PUBLISHER_SHA = '7253f3b86a6ad17dadc85c26deda17a5ccaaa8f76c65da21572be39658993895'
ROUTES = Path('/etc/nginx/pr122-site-hub/locations.conf')
CAMPUS = Path('/home/admin/campus-official-20261111')
CAMPUS_MANIFEST_SHA = '2de442b6786b6368bd2d5de9e14ad88ad94c4f4e78576ad2e95ddab5630137ba'
CAMPUS_PACKAGE_SHA = '4197dd0299e9e2287883c5ddd0f7cd67173fe208d065be1c2221c8b4c5aed5ab'
CAMPUS_PREFIX = 'delivery/previews/smart-campus/v2-e96b6559/'
ROUTE_ADD = b'''\n# PR122 approved public task overview; original security policy reused.
location = /task-center { return 308 /task-center/; }
location = /task-center/ {
    include /etc/nginx/pr122-minimal-cutover/static-security.conf;
    try_files /task-center/index.html =404;
}
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def lock_original():
    p = Path('/var/lib/xuanjun-pr122-site-hub/transaction.lock')
    fd = os.open(p, os.O_RDWR | os.O_NOFOLLOW)
    s = os.fstat(fd)
    assert s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o600
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert (s.st_dev, s.st_ino) == (p.stat().st_dev, p.stat().st_ino)
    return fd


def build(pub):
    old = BASE / 'releases' / OLD
    assert (BASE / 'current').resolve() == old
    receipt_path = BASE / 'transactions' / (OLD + '.json')
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt['state'] == 'CHECKED'
    assert len(receipt['trusted_manifest']['files']) == 1349
    # The approved campus successor added exactly nine files after the original
    # CHECKED receipt. Bind its original package and per-file manifest, rather
    # than accepting a changed live tree or altering that historical receipt.
    campus_manifest = (CAMPUS/'MANIFEST.json').read_bytes()
    assert sha(campus_manifest) == CAMPUS_MANIFEST_SHA
    assert sha((CAMPUS/'package.tgz').read_bytes()) == CAMPUS_PACKAGE_SHA
    campus = json.loads(campus_manifest)['files']
    names = {'public/index.html'} | {
        'public/'+level+'/'+name for level in ['junior', 'senior']
        for name in ['index.html', 'atlas.css', 'atlas.js', 'data.js']}
    assert {n for n in campus if n.startswith('public/')} == names
    bound_manifest = copy.deepcopy(receipt['trusted_manifest'])
    for name in sorted(names):
        blob = (CAMPUS/name).read_bytes()
        assert sha(blob) == campus[name]
        bound_manifest['files'].append({'path': CAMPUS_PREFIX+name.removeprefix('public/'),
                                        'size': len(blob), 'sha256': campus[name]})
    assert len(bound_manifest['files']) == 1358
    with pub.Deadline(120) as deadline:
        with pub.lock(BASE, 5, deadline, 0):
            pub.verify_tree(old / 'public', bound_manifest, deadline, 0)
            data = {r['path']: (old / 'public' / r['path']).read_bytes()
                    for r in bound_manifest['files']}
            cleanup = load_module(STAGE / 'pr122_website_content_cleanup.py', 'cleanup_bound')
            selected = {n: data[n] for n in cleanup.PINS}
            changed = cleanup.transform(selected)
            assert 'task-center/index.html' not in data
            result = dict(data)
            for name, blob in changed.items():
                result[name] = blob
                if name in selected:
                    for alias, original in data.items():
                        if original == selected[name]:
                            result[alias] = blob
            assert set(data).issubset(result) and len(result) == 1359
            out = STAGE / 'candidate'
            out.mkdir(mode=0o700)
            bundle = out / 'bundle'
            bundle.mkdir(mode=0o700)
            archive = io.BytesIO()
            with gzip.GzipFile(fileobj=archive, mode='wb', mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode='w', format=tarfile.USTAR_FORMAT) as tar:
                    for name, blob in sorted(result.items()):
                        entry = tarfile.TarInfo('package/public/' + name)
                        entry.size = len(blob)
                        entry.mode = 0o644
                        entry.uid = entry.gid = entry.mtime = 0
                        tar.addfile(entry, io.BytesIO(blob))
            raw = archive.getvalue()
            (out / 'source.tar.gz').write_bytes(raw)
            rows = [{'path': n, 'size': len(b), 'sha256': sha(b), 'mode': '0644', 'uid': 0, 'gid': 0}
                    for n, b in sorted(result.items())]
            manifest = {'schema_version': 2, 'files': rows}
            pin = {'schema_version': 1, 'source_archive': 'source.tar.gz',
                   'source_archive_size': len(raw), 'source_archive_sha256': sha(raw),
                   'source_file_count': len(result), 'source_total_bytes': sum(map(len, result.values())),
                   'source_version': RID, 'overlay_baselines': {}}
            for name, value in [('candidate-manifest.json', manifest), ('source-pin.json', pin)]:
                (bundle / name).write_bytes(canonical(value))
            package = {'schema_version': 1, 'files': [
                {'path': n, 'size': (bundle/n).stat().st_size, 'sha256': sha((bundle/n).read_bytes())}
                for n in ['candidate-manifest.json', 'source-pin.json']]}
            (bundle / 'PACKAGE_MANIFEST.json').write_bytes(canonical(package))
            delta = {'state': 'BUILT_NOT_INSTALLED', 'baseline': OLD,
                     'baseline_receipt_sha256': sha(receipt_bytes),
                     'campus_manifest_sha256': CAMPUS_MANIFEST_SHA,
                     'campus_package_sha256': CAMPUS_PACKAGE_SHA,
                     'approved_supplement_file_count': 9,
                     'package_sha256': sha(canonical(package)), 'source_sha256': sha(raw),
                     'file_count': len(result), 'unchanged': sum(result[n] == b for n,b in data.items()),
                     'changed': [n for n,b in data.items() if result[n] != b],
                     'added': sorted(set(result) - set(data)), 'deleted': [],
                     'routes_before_sha256': sha(ROUTES.read_bytes())}
            (out / 'complete-diff.json').write_bytes(canonical(delta))
            (STAGE / 'routes.before').write_bytes(ROUTES.read_bytes())
            (STAGE / 'csp.before').write_bytes((old/'release-metadata/inline-csp.conf').read_bytes())
            pub.verify_tree(old/'public', bound_manifest, deadline, 0)
            assert receipt_path.read_bytes() == receipt_bytes
            assert (BASE/'current').resolve() == old
    print(json.dumps(delta, ensure_ascii=False))


def native(action, approved, source_sha):
    out = STAGE/'candidate'
    assert sha((out/'bundle/PACKAGE_MANIFEST.json').read_bytes()) == approved
    assert sha((out/'source.tar.gz').read_bytes()) == source_sha
    cmd = [sys.executable, str(PUBLISHER), action, '--webroot-base', str(BASE),
           '--transaction-id', RID, '--release-id', RID, '--bundle', str(out/'bundle'),
           '--source-archive', str(out/'source.tar.gz'), '--approved-package-manifest-sha256', approved]
    r = subprocess.run(cmd, capture_output=True, text=True)
    (STAGE/(action+'.stdout')).write_text(r.stdout)
    (STAGE/(action+'.stderr')).write_text(r.stderr)
    if r.returncode:
        print(r.stdout); print(r.stderr); raise SystemExit(r.returncode)
    value = json.loads(r.stdout)
    print(json.dumps({'action': action, 'state': value.get('state'), 'release_id': RID}))
    return value


def route_and_navigation():
    before = (STAGE/'routes.before').read_bytes()
    assert ROUTES.read_bytes() == before and b'location = /task-center' not in before
    with ROUTES.open('ab') as f:
        f.write(ROUTE_ADD); f.flush(); os.fsync(f.fileno())
    if subprocess.run(['nginx', '-t']).returncode:
        assert ROUTES.read_bytes() == before+ROUTE_ADD
        ROUTES.write_bytes(before)
        raise RuntimeError('TASK_ROUTE_CONFIG_TEST_FAILED_RESTORED')
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    sys.path.insert(0, '/usr/local/lib/xuanjun-showcase')
    from scripts import pr122_showcase_navigation as nav
    state = nav.manage('read')
    assert state['revision'] == 1
    items = copy.deepcopy(state['items'])
    target = next(x for x in items if x['id'] == 'task-dispatch')
    assert not target['visible'] and target['href'] in ['', '/']
    (STAGE/'navigation.before.json').write_bytes(canonical(state))
    items.remove(target)
    target.update(href='/task-center/', label='任务调度中心', visible=True)
    items.insert(next(i for i,x in enumerate(items) if x['id']=='home')+1, target)
    r = nav.manage('put', expected_revision=1, items=items)
    assert nav.manage('read')['items'] == items
    (STAGE/'navigation.receipt.json').write_bytes(canonical(r))
    print('NAVIGATION_UPDATED_HOME_THEN_TASK_CENTER')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['build', 'prepare', 'activate', 'check'])
    p.add_argument('--approved-package-sha256')
    p.add_argument('--source-sha256')
    a = p.parse_args()
    assert os.geteuid() == 0 and socket.gethostname().lower() == 'izvt5t8tlrm8oiz'
    assert sha(PUBLISHER.read_bytes()) == PUBLISHER_SHA
    fd = lock_original()
    try:
        if a.action == 'build':
            build(load_module(PUBLISHER, 'native_pr122'))
        else:
            assert a.approved_package_sha256 and a.source_sha256
            if a.action == 'activate':
                assert (BASE/'current').resolve() == BASE/'releases'/OLD
                assert (BASE/'releases'/RID/'release-metadata/inline-csp.conf').read_bytes() == (STAGE/'csp.before').read_bytes()
            native(a.action, a.approved_package_sha256, a.source_sha256)
            if a.action == 'prepare':
                assert (BASE/'releases'/RID/'release-metadata/inline-csp.conf').read_bytes() == (STAGE/'csp.before').read_bytes()
            if a.action == 'activate':
                route_and_navigation()
                native('check', a.approved_package_sha256, a.source_sha256)
    finally:
        os.close(fd)


if __name__ == '__main__':
    main()

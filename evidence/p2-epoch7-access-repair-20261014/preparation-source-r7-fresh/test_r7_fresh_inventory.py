"""Local-only R7 saved-to-fresh inventory boundary tests.

The fixture contains synthetic public unit text only. Three fixed logical
systemd roots are mapped to disposable directories beneath this checkout.
Only observed ownership is normalized; the authenticated DescriptorTree,
no-follow traversal, descriptor reads, xattrs and filesystem races are real.
No host collection, network request, production edit or approval is performed.
Run directly with Python -I -S -B or the local preparation test harness.
"""
import copy
import errno
import inspect
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import epoch7_prepare as p
import test_epoch7_topology_projection as topology_fixture
import test_epoch7_prepare_data_r7 as cache_fixture
import epoch7_topology_projection as topology


PUBLIC_UNIT = 'xuanjun-uk-openclaw.service'
PUBLIC_ROOT = '/etc/systemd/system/' + PUBLIC_UNIT + '.d'
PUBLIC_FILE = PUBLIC_ROOT + '/20-fixture-public.conf'
RAW_MARKER = 'SYNTHETIC_CONFIG_BYTES_STAY_INSIDE_THE_READER'
PUBLIC_RAW = ('# ' + RAW_MARKER + '\n[Service]\nType=simple\n'
              'User=xuanjun-gateway\nGroup=xuanjun-gateway\n'
              'SupplementaryGroups=xuanjun-ledger-client\n').encode('ascii')
PUBLIC_FIELDS = {'Type': ['simple'], 'User': ['xuanjun-gateway'],
                 'Group': ['xuanjun-gateway'],
                 'SupplementaryGroups': ['xuanjun-ledger-client']}
EMPTY_ROOTS = ('/etc/systemd/system/nginx.service.d',
               '/usr/lib/systemd/system/nginx.service.d')


def mapped_info(info):
    """Same portable ownership adapter as the frozen reader's filesystem tests."""
    values = {name: getattr(info, name) for name in dir(info)
              if name.startswith('st_')}
    values.update(st_uid=0, st_gid=0)
    return types.SimpleNamespace(**values)


def fixture_owners():
    return ((0, 0), (os.getuid(), os.getgid()))


def local_entry():
    """Preserve real protected-reader semantics, changing only fixture owners."""
    real = p.load_entry((cache_fixture.KIT / 'epoch7_recovery_entry.py').read_bytes())

    class Tree(object):
        def __init__(self, path):
            self.real = real.DescriptorTree(path, owners=fixture_owners())
            self.fd = self.real.fd
            self.closed = False

        @property
        def opened(self):
            # Include descriptors acquired by parent() after construction too.
            return [[fd, parent, name, logical,
                     tuple(list(before[:3]) + [0, 0] + list(before[5:]))]
                    for fd, parent, name, logical, before in self.real.opened]

        def parent(self, name):
            return self.real.parent(name)

        def read(self, *args, **kwargs):
            return self.real.read(*args, **kwargs)

        def _authority(self, *args, **kwargs):
            return mapped_info(self.real._authority(*args, **kwargs))

        def recheck(self):
            for fd, parent, name, unused_logical, before in self.opened:
                if real.stamp(self._authority(fd, True)) != before:
                    raise ValueError('FIXTURE_ANCESTRY_RACE')
                if parent is not None and real.stamp(mapped_info(
                        os.stat(name, dir_fd=parent, follow_symlinks=False))) != before:
                    raise ValueError('FIXTURE_PARENT_BINDING_RACE')

    proxy = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os)
                                    if not name.startswith('__')})
    proxy.stat = lambda *args, **kwargs: mapped_info(os.stat(*args, **kwargs))
    proxy.fstat = lambda *args, **kwargs: mapped_info(os.fstat(*args, **kwargs))
    return types.SimpleNamespace(DescriptorTree=Tree, stamp=real.stamp), proxy


def rebound(proof):
    """Keep synthetic section hashes coherent so tests reach the intended gate."""
    units = proof['dropins_section']['evidence']['units']
    dispatcher = units.get('xuanjun-development-dispatcher.service')
    if dispatcher is not None:
        proof['latecheck_section']['evidence']['provenance']['dropins_sha256'] = (
            topology.digest(topology.canonical(dispatcher)))
    for name in ('dropins', 'latecheck'):
        proof[name + '_section_sha256'] = topology.digest(
            topology.canonical(proof[name + '_section']))
    return proof


class FreshInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observation = topology_fixture.fixture()['observation']

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fresh-r7-local-', dir=str(HERE))
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.real_entry, self.proxy = local_entry()
        patch = mock.patch.object(p, 'os', self.proxy)
        patch.start()
        self.addCleanup(patch.stop)
        self.tree_requests = []
        for prefix in topology.DROPIN_ROOTS:
            self.physical(prefix).mkdir(parents=True, mode=0o755)
        for logical in EMPTY_ROOTS + (PUBLIC_ROOT,):
            self.physical(logical).mkdir(mode=0o755)
        self.physical(PUBLIC_FILE).write_bytes(PUBLIC_RAW)
        os.chmod(str(self.physical(PUBLIC_FILE)), 0o644)
        self.proof = self.saved_proof()
        self.entry = types.SimpleNamespace(DescriptorTree=self.mapped_tree,
                                           stamp=self.real_entry.stamp)
        self.reader = p.Gatherer(self.entry, time.monotonic() + 30)
        self.addCleanup(self.reader.close)

    def physical(self, logical):
        allowed = topology.DROPIN_ROOTS + ('/usr/lib/systemd',)
        if not any(logical == base or logical.startswith(base + '/') for base in allowed):
            raise AssertionError('FIXTURE_UNDECLARED_ROOT')
        return self.root / logical.lstrip('/')

    def mapped_tree(self, logical):
        self.tree_requests.append(logical)
        return self.real_entry.DescriptorTree(str(self.physical(logical)))

    def saved_proof(self, raw=PUBLIC_RAW, public_fields=PUBLIC_FIELDS):
        observation = copy.deepcopy(self.observation)
        units = observation['unit_metadata']['sections']['dropins']['evidence']['units']
        for unit, roots in units.items():
            for logical, row in roots.items():
                path = self.physical(logical)
                row.update(present=path.is_dir(), files={})
                if logical == PUBLIC_ROOT and path.is_dir():
                    metadata = dict(p.stamps(mapped_info(os.stat(str(self.physical(PUBLIC_FILE)),
                                                                 follow_symlinks=False))),
                                    kind='FILE', sha256=p.sha(raw))
                    row['files'][PUBLIC_FILE] = {'sha256': p.sha(raw), 'metadata': metadata,
                                                'public_service_fields': copy.deepcopy(public_fields)}
        observation['unit_metadata_sha256'] = topology.digest(
            topology.canonical(observation['unit_metadata']))
        return topology.project_saved_unit_dropins(observation)

    def capture(self, proof=None):
        return self.reader.saved_unit_dropins(self.proof if proof is None else proof, topology)

    def saved_file(self, proof=None):
        value = self.proof if proof is None else proof
        return value['dropins_section']['evidence']['units'][PUBLIC_UNIT][PUBLIC_ROOT]['files'][PUBLIC_FILE]

    def assert_rejected(self, callback):
        with self.assertRaises((ValueError, OSError)):
            callback()

    def test_exact_eleven_by_three_authority_preserves_saved_proof_without_raw_bytes(self):
        before = copy.deepcopy(self.proof)
        result = self.capture()
        self.assertEqual(self.proof, before)
        self.assertEqual(result['schema'], 1)
        self.assertEqual(result['kind'], 'FRESH_R7_UNIT_DROPIN_AUTHORITY')
        self.assertEqual(result['reread'], 'EXACT_PRE_POST_AND_FINAL')
        self.assertEqual(result['saved_unit_dropins_sha256'], topology.digest(topology.canonical(before)))
        self.assertEqual(set(result['units']), set(topology.DROPIN_UNITS))
        self.assertEqual(len(result['units']), 11)
        present = []
        absent = []
        for unit, roots in result['units'].items():
            self.assertEqual(set(roots), {base + '/' + unit + '.d' for base in topology.DROPIN_ROOTS})
            for logical, row in roots.items():
                self.assertEqual(row['parent_metadata'], p.stamps(mapped_info(
                    os.stat(str(self.physical(logical).parent)))))
                self.assertEqual(row['files'], before['dropins_section']['evidence']['units'][unit][logical]['files'])
                if row['present']:
                    present.append(logical)
                    self.assertEqual(row['metadata'], p.stamps(mapped_info(os.stat(str(self.physical(logical))))))
                else:
                    absent.append(logical)
                    self.assertIsNone(row['metadata'])
        self.assertEqual(set(present), set(EMPTY_ROOTS + (PUBLIC_ROOT,)))
        self.assertEqual(len(absent), 30)
        encoded = json.dumps(result, sort_keys=True)
        self.assertNotIn(RAW_MARKER, encoded)
        self.assertNotIn('[Service]', encoded)
        self.assertNotIn('"data"', encoded)
        self.assertNotIn('"raw"', encoded)
        self.reader.recheck()
        self.assertTrue(set(topology.DROPIN_ROOTS).issubset(set(self.tree_requests)))

    def test_repeated_stable_capture_and_recheck_are_exact(self):
        first = self.capture()
        self.assertEqual(self.capture(), first)
        self.reader.recheck()
        self.assertEqual(self.capture(), first)

    def test_all_thirty_three_absent_roots_are_explicit_and_rechecked(self):
        self.physical(PUBLIC_FILE).unlink()
        for logical in EMPTY_ROOTS + (PUBLIC_ROOT,):
            self.physical(logical).rmdir()
        proof = self.saved_proof()
        result = self.capture(proof)
        rows = [row for roots in result['units'].values() for row in roots.values()]
        self.assertEqual(len(rows), 33)
        self.assertTrue(all(row['present'] is False and row['metadata'] is None and
                            row['files'] == {} for row in rows))
        self.reader.recheck()

    def test_late_recheck_repeats_both_checks_for_all_eleven_by_three_roots(self):
        self.capture()
        roots_by_fd = {tree.fd: logical for logical, tree in self.reader.trees.items()}
        observed = []
        original = self.proxy.stat

        def record(path, *args, **kwargs):
            if isinstance(path, str) and path.endswith('.d'):
                observed.append(roots_by_fd[kwargs['dir_fd']] + '/' + path)
            return original(path, *args, **kwargs)

        with mock.patch.object(self.proxy, 'stat', side_effect=record):
            self.reader.recheck()
        expected = {root + '/' + unit + '.d' for root in topology.DROPIN_ROOTS
                    for unit in topology.DROPIN_UNITS}
        self.assertEqual(set(observed), expected)
        self.assertEqual(len(observed), 66)
        self.assertTrue(all(observed.count(path) == 2 for path in expected))

    def test_caller_mutations_cannot_change_captured_proof_or_authority(self):
        result = self.capture()
        expected = copy.deepcopy(result)
        result['units'].clear()
        self.proof['dropins_section']['evidence']['units'].clear()
        self.reader.recheck()
        self.assertEqual(self.reader.fresh_evidence, expected)
        self.assertEqual(set(self.reader.saved_proof['dropins_section']['evidence']['units']),
                         set(topology.DROPIN_UNITS))

    def test_close_includes_nested_descriptors_acquired_during_file_reads(self):
        self.capture()
        descriptors = {row[0] for tree in self.reader.trees.values() for row in tree.opened}
        nested = [row for tree in self.reader.trees.values() for row in tree.opened
                  if row[3].endswith(PUBLIC_UNIT + '.d')]
        self.assertEqual(len(nested), 1)
        self.reader.close()
        for fd in descriptors:
            with self.assertRaises(OSError) as caught: os.fstat(fd)
            self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_authenticated_saved_parser_survives_import_scope_for_fresh_final_recheck(self):
        # Isolate the authenticated import scope from this suite's public test
        # fixture aliases. Only our synthetic proof and disposable path enter.
        script = """import json,os,pathlib,sys,time,types
wrapper=pathlib.Path(%r)
p=types.ModuleType('fresh_wrapper_under_test');p.__file__=str(wrapper)
exec(compile(wrapper.read_bytes(),str(wrapper),'exec'),p.__dict__)
cache_fixture=types.SimpleNamespace(KIT=pathlib.Path(%r))
""" % (str(HERE / 'epoch7_prepare.py'), str(cache_fixture.KIT))
        script += '\n'.join(inspect.getsource(function) for function in
                            (mapped_info, fixture_owners, local_entry))
        script += """
request=json.loads(sys.stdin.read())
root=pathlib.Path(request['root']);saved=request['proof']
authenticated=p.load_entry((cache_fixture.KIT/'epoch7_recovery_entry.py').read_bytes())
kit=authenticated._verify(str(cache_fixture.KIT),p.KIT_SHA,fixture_owners())
local,proxy=local_entry()
def mapped_tree(logical):
    if not any(logical==base or logical.startswith(base+'/') for base in
               ('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')):
        raise AssertionError('FIXTURE_UNDECLARED_ROOT')
    return local.DescriptorTree(str(root/logical.lstrip('/')))
entry=types.SimpleNamespace(DescriptorTree=mapped_tree,stamp=local.stamp)
p.os=proxy
reader=p.Gatherer(entry,time.monotonic()+30)
try:
    with kit.imports():
        raw=(wrapper.parent/'epoch7_topology_projection.py').read_bytes()
        assert p.sha(raw)==p.PREPARATION_SOURCES['epoch7_topology_projection']
        top=types.ModuleType('authenticated_preparation_topology')
        top.__file__=str(wrapper.parent/'epoch7_topology_projection.py')
        exec(compile(raw,top.__file__,'exec'),top.__dict__)
        first=reader.saved_unit_dropins(saved,top)
        assert reader.saved_parser is sys.modules['unit_metadata'].service_fields
        parser=reader.saved_parser
    assert 'unit_metadata' not in sys.modules
    assert reader.saved_unit_dropins(saved,top)==first
    reader.recheck()
    assert reader.saved_parser is parser
    assert 'unit_metadata' not in sys.modules
    print('AUTHENTICATED_PARSER_RETAINED_FINAL_RECHECK_OK')
finally:
    reader.close()
"""
        request = json.dumps({'root': str(self.root), 'proof': self.proof}).encode('ascii')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', script],
                                input=request, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertEqual(result.stdout, b'AUTHENTICATED_PARSER_RETAINED_FINAL_RECHECK_OK\n')

    def test_missing_or_extra_unit_and_root_fail_before_filesystem_access(self):
        changes = [('missing_unit', unit) for unit in topology.DROPIN_UNITS]
        changes += [('missing_root', (unit, root)) for unit in topology.DROPIN_UNITS
                    for root in topology.DROPIN_ROOTS]
        changes += [('extra_unit', None), ('extra_root', None)]
        for kind, target in changes:
            proof = copy.deepcopy(self.proof)
            units = proof['dropins_section']['evidence']['units']
            if kind == 'missing_unit':
                del units[target]
            elif kind == 'missing_root':
                unit, root = target
                del units[unit][root + '/' + unit + '.d']
            elif kind == 'extra_unit':
                units['unexpected.service'] = {}
            else:
                units[PUBLIC_UNIT]['/opt/systemd/system/' + PUBLIC_UNIT + '.d'] = {'present': False, 'files': {}}
            rebound(proof)
            with self.subTest(kind=kind, target=target), \
                 mock.patch.object(self.reader, 'tree', side_effect=AssertionError('NO_TRAVERSAL')):
                with self.assertRaises(ValueError):
                    self.capture(proof)

    def test_saved_schema_digest_and_typed_presence_fail_before_filesystem_access(self):
        for kind in ('schema_one', 'schema_bool', 'extra_field', 'digest', 'presence_integer',
                     'metadata_in_saved_root', 'raw_bytes_claim'):
            proof = copy.deepcopy(self.proof)
            roots = proof['dropins_section']['evidence']['units'][PUBLIC_UNIT]
            if kind == 'schema_one': proof['schema'] = 1
            elif kind == 'schema_bool': proof['schema'] = True
            elif kind == 'extra_field': proof['fresh_authority'] = True
            elif kind == 'digest': proof['dropins_section_sha256'] = '0' * 64
            elif kind == 'presence_integer': roots[PUBLIC_ROOT]['present'] = 1
            elif kind == 'metadata_in_saved_root': roots[PUBLIC_ROOT]['metadata'] = {}
            else: proof['dropins_section']['evidence']['raw_unit_bytes_returned'] = True
            if kind != 'digest': rebound(proof)
            with self.subTest(kind=kind), \
                 mock.patch.object(self.reader, 'tree', side_effect=AssertionError('NO_TRAVERSAL')):
                with self.assertRaises(ValueError): self.capture(proof)

    def test_saved_socket_content_is_rejected_before_filesystem_access(self):
        for unit in topology.SOCKET_UNITS:
            proof = copy.deepcopy(self.proof)
            root = topology.DROPIN_ROOTS[0] + '/' + unit + '.d'
            proof['dropins_section']['evidence']['units'][unit][root] = {
                'present': True, 'files': {root + '/20-fixture.conf': copy.deepcopy(self.saved_file())}}
            rebound(proof)
            with self.subTest(unit=unit), \
                 mock.patch.object(self.reader, 'tree', side_effect=AssertionError('NO_TRAVERSAL')):
                with self.assertRaises(ValueError): self.capture(proof)

    def test_all_full_saved_file_stamp_fields_are_compared(self):
        for key in sorted(topology.META):
            proof = copy.deepcopy(self.proof)
            row = self.saved_file(proof)['metadata']
            row[key] = 0o640 if key == 'mode' else row[key] + 1
            rebound(proof)
            with self.subTest(field=key):
                self.assert_rejected(lambda: self.capture(proof))

    def test_saved_file_digest_and_safe_public_fields_are_compared(self):
        for kind in ('digest', 'public_fields'):
            proof = copy.deepcopy(self.proof)
            row = self.saved_file(proof)
            if kind == 'digest': row['sha256'] = row['metadata']['sha256'] = '0' * 64
            else: row['public_service_fields']['User'] = ['different-safe-user']
            rebound(proof)
            with self.subTest(kind=kind): self.assert_rejected(lambda: self.capture(proof))

    def test_saved_missing_or_extra_file_does_not_silently_project_current_files(self):
        for kind in ('missing', 'extra'):
            proof = copy.deepcopy(self.proof)
            files = proof['dropins_section']['evidence']['units'][PUBLIC_UNIT][PUBLIC_ROOT]['files']
            if kind == 'missing': files.clear()
            else: files[PUBLIC_ROOT + '/99-not-on-disk.conf'] = copy.deepcopy(files[PUBLIC_FILE])
            rebound(proof)
            with self.subTest(kind=kind): self.assert_rejected(lambda: self.capture(proof))

    def test_unexpected_live_file_refuses(self):
        self.physical(PUBLIC_ROOT + '/99-unreviewed.conf').write_bytes(b'[Service]\nUser=nobody\n')
        self.assert_rejected(self.capture)

    def test_non_conf_live_entry_refuses(self):
        self.physical(PUBLIC_ROOT + '/unreviewed.txt').write_bytes(b'fixture only\n')
        self.assert_rejected(self.capture)

    def test_unsupported_service_directive_refuses_even_with_matching_digest_and_metadata(self):
        raw = PUBLIC_RAW + b'ExecStart=/usr/bin/false\n'
        self.physical(PUBLIC_FILE).write_bytes(raw)
        proof = self.saved_proof(raw=raw)
        self.assert_rejected(lambda: self.capture(proof))

    def test_same_byte_inode_replacement_is_rejected_before_capture(self):
        old = os.stat(str(self.physical(PUBLIC_FILE))).st_ino
        replacement = self.physical(PUBLIC_ROOT + '/.fixture-replacement')
        replacement.write_bytes(PUBLIC_RAW)
        os.chmod(str(replacement), 0o644)
        os.replace(str(replacement), str(self.physical(PUBLIC_FILE)))
        self.assertNotEqual(os.stat(str(self.physical(PUBLIC_FILE))).st_ino, old)
        self.assert_rejected(self.capture)

    def test_same_byte_inode_replacement_is_rejected_by_late_recheck(self):
        self.capture()
        replacement = self.physical(PUBLIC_ROOT + '/.fixture-replacement')
        replacement.write_bytes(PUBLIC_RAW)
        os.chmod(str(replacement), 0o644)
        os.replace(str(replacement), str(self.physical(PUBLIC_FILE)))
        self.assert_rejected(self.reader.recheck)

    def test_changed_file_content_is_rejected_by_late_recheck(self):
        self.capture()
        self.physical(PUBLIC_FILE).write_bytes(PUBLIC_RAW.replace(b'simple', b'notify'))
        self.assert_rejected(self.reader.recheck)

    def test_parent_drift_during_inventory_is_rejected(self):
        original = self.proxy.stat
        changed = [False]

        def change_parent(path, *args, **kwargs):
            if isinstance(path, str) and path.endswith('.d') and not changed[0]:
                changed[0] = True
                fd = os.open('fixture-parent-change', os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=kwargs['dir_fd'])
                os.close(fd)
            return original(path, *args, **kwargs)

        with mock.patch.object(self.proxy, 'stat', side_effect=change_parent):
            self.assert_rejected(self.capture)
        self.assertTrue(changed[0])

    def test_parent_drift_after_capture_is_rejected_by_late_recheck(self):
        self.capture()
        self.physical('/run/systemd/system/fixture-independent-change').write_bytes(b'public fixture\n')
        self.assert_rejected(self.reader.recheck)

    def test_present_empty_directory_metadata_drift_is_rejected(self):
        self.capture()
        os.chmod(str(self.physical(EMPTY_ROOTS[0])), 0o750)
        self.assert_rejected(self.reader.recheck)

    def test_present_empty_directory_replacement_is_rejected(self):
        self.capture()
        path = self.physical(EMPTY_ROOTS[0])
        os.rename(str(path), str(path) + '.old')
        os.mkdir(str(path), 0o755)
        self.assert_rejected(self.reader.recheck)

    def test_absence_change_between_protected_checks_is_rejected(self):
        original = self.proxy.stat
        changed = [False]

        def change_absence(path, *args, **kwargs):
            try:
                return original(path, *args, **kwargs)
            except FileNotFoundError:
                if isinstance(path, str) and path.endswith('.d') and not changed[0]:
                    changed[0] = True
                    os.mkdir(path, 0o755, dir_fd=kwargs['dir_fd'])
                raise

        with mock.patch.object(self.proxy, 'stat', side_effect=change_absence):
            self.assert_rejected(self.capture)
        self.assertTrue(changed[0])

    def test_absent_root_becoming_present_is_rejected_before_capture(self):
        self.physical('/run/systemd/system/nginx.service.d').mkdir(mode=0o755)
        self.assert_rejected(self.capture)

    def test_absent_root_becoming_present_is_rejected_by_late_recheck(self):
        self.capture()
        self.physical('/run/systemd/system/nginx.service.d').mkdir(mode=0o755)
        self.assert_rejected(self.reader.recheck)

    def test_present_empty_root_becoming_absent_is_rejected_before_capture(self):
        self.physical(EMPTY_ROOTS[0]).rmdir()
        self.assert_rejected(self.capture)

    def test_present_empty_root_becoming_absent_is_rejected_by_late_recheck(self):
        self.capture()
        self.physical(EMPTY_ROOTS[0]).rmdir()
        self.assert_rejected(self.reader.recheck)

    def test_dropin_directory_symlink_is_not_followed(self):
        path = self.physical(EMPTY_ROOTS[0])
        path.rmdir()
        os.symlink(str(self.physical(EMPTY_ROOTS[1])), str(path))
        self.assert_rejected(self.capture)

    def test_dropin_file_symlink_is_not_followed(self):
        path = self.physical(PUBLIC_FILE)
        target = self.root / 'synthetic-public-target'
        target.write_bytes(PUBLIC_RAW)
        path.unlink()
        os.symlink(str(target), str(path))
        self.assert_rejected(self.capture)

    def test_systemd_ancestor_symlink_is_not_followed(self):
        path = self.root / 'etc/systemd'
        target = self.root / 'fixture-systemd-real'
        os.rename(str(path), str(target))
        os.symlink(str(target), str(path))
        self.assert_rejected(self.capture)

    def test_writable_directory_metadata_is_rejected(self):
        os.chmod(str(self.physical(EMPTY_ROOTS[0])), 0o777)
        self.assert_rejected(self.capture)

    def test_writable_file_metadata_is_rejected(self):
        os.chmod(str(self.physical(PUBLIC_FILE)), 0o666)
        self.assert_rejected(self.capture)

    def test_multiple_file_links_are_rejected(self):
        os.link(str(self.physical(PUBLIC_FILE)), str(self.root / 'fixture-hard-link'))
        self.assert_rejected(self.capture)

    def test_nonregular_file_is_rejected_without_blocking(self):
        self.physical(PUBLIC_FILE).unlink()
        os.mkfifo(str(self.physical(PUBLIC_FILE)), 0o600)
        self.assert_rejected(self.capture)

    def test_unknown_or_present_xattrs_never_mean_absent(self):
        for kind in ('unknown', 'present'):
            kwargs = {'side_effect': OSError(errno.EACCES, 'fixture xattr unavailable')} if kind == 'unknown' else {'return_value': b'fixture'}
            with self.subTest(kind=kind), mock.patch.object(self.proxy, 'getxattr', **kwargs):
                self.assert_rejected(self.capture)

    def test_deadline_refuses_before_inventory_traversal(self):
        self.reader.end = 0
        with mock.patch.object(self.reader, 'tree', side_effect=AssertionError('NO_TRAVERSAL')):
            with self.assertRaisesRegex(ValueError, 'DEADLINE'): self.capture()


if __name__ == '__main__':
    unittest.main()

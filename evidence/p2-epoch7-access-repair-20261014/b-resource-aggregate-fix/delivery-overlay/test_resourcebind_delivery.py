"""Focused resource-bind delivery regressions using real pinned public bytes.

Only disposable local directories are written. Network, host identity and
preparation execution are mocked; no host collection or admission is claimed.
"""
import ast
import contextlib
import copy
import errno
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import time
import types
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASELINE = Path(os.environ.get('EPOCH7_RESOURCEBIND_DELIVERY_BASELINE',str(ROOT.parent/'b-release-parent-fix-candidate/delivery-candidate/baseline')))
ARCHIVE = Path(os.environ.get('EPOCH7_RESOURCEBIND_ARCHIVE',str(ROOT/'artifact'/'epoch7-kit-resourcebind.tar.gz')))
PREPARATION = Path(os.environ.get('EPOCH7_RESOURCEBIND_PREPARATION',str(ROOT/'preparation-overlay')))
ARCHIVE_SHA = '6244cca1b41037b7c240f71b93f867c5660a770d451c4a5a661b283f61ce819e'
ARCHIVE_BYTES = 1056853
MANIFEST_SHA = '6c269db1e20d3cab9877eaa6bde2240ad8a7ffaca3e183fd1180011a4e244030'
ENTRY_SHA = '071ed5ffc57956269fe8cfdbb9095e40414ded091bae888a3fe76dc9a64d70d5'
WRAPPER_SHA = '18d3c459bc14f4a3c00317c5a407d18178059209830763564dced41d9af945fd'
SOURCE_COMMIT = 'ef21ca95331769622c294c65bb60ec7ceed0c392'
SOURCE_TREE = '5a70c5627afe75fcd475c20e71ee9bfb0b6a156d'
KIT_LEAF = 'epoch7-recovery-candidate-r7-resourcebind'
PREP_LEAF = 'epoch7-preparation-candidate-r7-resourcebind'
OLD_KIT_LEAF = 'epoch7-recovery-candidate-r7'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load_module(HERE / 'epoch7_prepare_delivery.py', 'resourcebind_delivery_under_test')


def sources():
    return {name: (PREPARATION / name).read_bytes() for name in m.SOURCES}


def mapped(info):
    values = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
    values.update(st_uid=0, st_gid=0)
    return types.SimpleNamespace(**values)


def os_proxy():
    value = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os)
                                    if not name.startswith('__')})
    value.fstat = lambda fd: mapped(os.fstat(fd))
    value.stat = lambda *args, **kwargs: mapped(os.stat(*args, **kwargs))
    value.geteuid = lambda: 0
    value.getegid = lambda: 0
    return value


def completed_result():
    outputs = [{'path': m.CAND + '/' + prefix + pin[:16] + '.private.json',
                'sha256': pin, 'bytes': 100}
               for prefix, pin in (('epoch7-approved-plan-', '1' * 64),
                                   ('epoch7-resume-inputs-', '2' * 64),
                                   ('epoch7-review-packet-', '3' * 64))]
    return {'state': 'PREPARED_NOT_ADMITTED', 'outputs': outputs,
            'install_admission': 'NOT_GRANTED', 'production_resume': 'NOT_EXECUTED'}


def arguments():
    return ['--observation', m.OBSERVATION_PATH,
            '--observation-sha256', m.OBSERVATION_SHA256,
            '--topology-review-id', '123456789',
            '--retained-renewal-timer', 'enable-after-reviewed-checks']


class ArtifactFixtureTests(unittest.TestCase):
    def test_candidate_stays_unbound_until_both_publications_exist(self):
        for missing in ('PINS_BOUND', 'PUBLICATION_COMMIT', 'ARCHIVE_COMMIT'):
            with self.subTest(missing=missing), mock.patch.object(m, 'PINS_BOUND', True), \
                    mock.patch.object(m, 'PUBLICATION_COMMIT', 'a' * 40), \
                    mock.patch.object(m, 'ARCHIVE_COMMIT', 'b' * 40), \
                    mock.patch.object(m, missing, False if missing == 'PINS_BOUND' else None), \
                    mock.patch.object(m, 'fetch_sources') as source_fetch, \
                    mock.patch.object(m, 'fetch_archive') as archive_fetch, \
                    mock.patch.object(m, 'stage_compiler') as compiler_stage, \
                    mock.patch.object(m, 'deliver_status') as status:
                self.assertEqual(m.entrypoint(arguments()), 2)
            source_fetch.assert_not_called()
            archive_fetch.assert_not_called()
            compiler_stage.assert_not_called()
            self.assertEqual(status.call_args[0][0]['failure_label'], 'UNBOUND')

    def test_reviewed_baseline_bytes_are_unchanged(self):
        self.assertEqual(sha((BASELINE / 'epoch7_prepare_delivery.py').read_bytes()),
                         '087df34edd0e2568870ced2c53c9bb0c28ae900d0a4bf7ec8642d8db80a30313')
        self.assertEqual(sha((BASELINE / 'test_epoch7_prepare_delivery.py').read_bytes()),
                         '13f4cb0a85ee6a096a0f0a85026ad34d0f5288154f6ab56014bec52b2d405314')

    def test_real_archive_fixture_and_manifest_are_exact(self):
        raw = ARCHIVE.read_bytes()
        self.assertEqual((sha(raw), len(raw)), (ARCHIVE_SHA, ARCHIVE_BYTES))
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            members = archive.getmembers()
            self.assertEqual(len(members), 298)
            self.assertEqual(len({member.name for member in members}), 298)
            self.assertEqual(sum(member.isdir() for member in members), 42)
            files = {}
            for member in members:
                self.assertTrue(member.name == KIT_LEAF or member.name.startswith(KIT_LEAF + '/'))
                self.assertEqual((member.uid, member.gid, member.mtime, member.uname, member.gname),
                                 (0, 0, 0, '', ''))
                self.assertEqual(member.mode, 0o700 if member.isdir() else 0o444)
                self.assertFalse(member.pax_headers)
                if member.isfile():
                    files[member.name[len(KIT_LEAF) + 1:]] = archive.extractfile(member).read()
        self.assertEqual(len(files), 256)
        self.assertEqual((sha(files['recovery-kit-manifest.json']),
                          len(files['recovery-kit-manifest.json'])), (MANIFEST_SHA, 62561))
        self.assertEqual((sha(files['epoch7_recovery_entry.py']),
                          len(files['epoch7_recovery_entry.py'])), (ENTRY_SHA, 55774))
        manifest = json.loads(files['recovery-kit-manifest.json'].decode('ascii'))
        self.assertEqual((manifest['kit_source_commit'], manifest['kit_source_tree']),
                         (SOURCE_COMMIT, SOURCE_TREE))
        self.assertEqual(set(files), set(manifest['files']) | {'recovery-kit-manifest.json'})
        for name, pin in manifest['files'].items():
            self.assertEqual(sha(files[name]), pin, name)

    def test_pinned_wrapper_keeps_saved_a_and_compiler_roots_separate(self):
        cache = sources()
        self.assertEqual(m.validate_sources(cache), cache)
        self.assertEqual((sha(cache['epoch7_prepare.py']), len(cache['epoch7_prepare.py'])),
                         (WRAPPER_SHA, 55833))
        preparer = m.preparer(cache)
        self.assertEqual(preparer.KIT_ROOT, m.CAND + '/' + OLD_KIT_LEAF)
        self.assertEqual(preparer.COMPILER_KIT_ROOT, m.CAND + '/' + KIT_LEAF)
        self.assertEqual(preparer.PREP_ROOT, m.CAND + '/' + PREP_LEAF)
        self.assertEqual(m.PREP_ROOT, preparer.PREP_ROOT)
        self.assertEqual(preparer.COMPILER_KIT_SHA, MANIFEST_SHA)
        self.assertEqual(preparer.COMPILER_ENTRY_SHA, ENTRY_SHA)
        self.assertEqual(preparer.KIT_SHA, '7b926fda92065d9ff981bfeaad490d5568dd5901d2b1089d1f1dfac94eae8bb4')
        self.assertEqual(preparer.ENTRY_SHA, '1be06802e012b5747f837af02ff8746fec9864ef94715b561f67c39be95e0948')


class ArchiveDownloadTests(unittest.TestCase):
    def response(self):
        return types.SimpleNamespace(status=200,
            geturl=lambda: m.RAW_PREFIX + 'b' * 40 + '/' + m.ARCHIVE_PATH,
            headers={'Content-Length': str(ARCHIVE_BYTES)},
            read=mock.Mock(return_value=ARCHIVE.read_bytes()), close=mock.Mock())

    def fetch(self, response):
        opener = types.SimpleNamespace(open=mock.Mock(return_value=response))
        with mock.patch.object(m, 'PINS_BOUND', True), \
                mock.patch.object(m, 'PUBLICATION_COMMIT', 'a' * 40), \
                mock.patch.object(m, 'ARCHIVE_COMMIT', 'b' * 40), \
                mock.patch.object(m.urllib.request, 'build_opener', return_value=opener):
            raw = m.fetch_archive(time.monotonic() + 10)
        return raw, opener

    def test_one_exact_https_request_is_length_bounded_and_closed(self):
        response = self.response()
        raw, opener = self.fetch(response)
        self.assertEqual(raw, ARCHIVE.read_bytes())
        opener.open.assert_called_once()
        request = opener.open.call_args[0][0]
        self.assertEqual(request.full_url, m.RAW_PREFIX + 'b' * 40 + '/' + m.ARCHIVE_PATH)
        self.assertEqual(request.get_header('Accept-encoding'), 'identity')
        self.assertGreater(opener.open.call_args[1]['timeout'], 0)
        self.assertLessEqual(opener.open.call_args[1]['timeout'], 10)
        response.read.assert_called_once_with(ARCHIVE_BYTES + 1)
        response.close.assert_called_once_with()

    def test_altered_body_status_redirect_encoding_length_and_oversize_refuse(self):
        for change in ('body', 'status', 'redirect', 'encoding', 'length', 'oversize'):
            row = self.response()
            if change == 'body':
                row.read.return_value = b'x' + row.read.return_value[1:]
            elif change == 'status':
                row.status = 302
            elif change == 'redirect':
                row.geturl = lambda: 'https://unapproved.invalid/'
            elif change == 'encoding':
                row.headers['Content-Encoding'] = 'gzip'
            elif change == 'length':
                row.headers['Content-Length'] = str(ARCHIVE_BYTES - 1)
            else:
                row.read.return_value += b'x'
            with self.subTest(change=change), self.assertRaises(m.Hold):
                self.fetch(row)
            row.close.assert_called_once_with()

    def test_missing_publication_refuses_before_network(self):
        for name in ('PUBLICATION_COMMIT', 'ARCHIVE_COMMIT'):
            with self.subTest(name=name), mock.patch.object(m, 'PINS_BOUND', True), \
                    mock.patch.object(m, 'PUBLICATION_COMMIT', 'a' * 40), \
                    mock.patch.object(m, 'ARCHIVE_COMMIT', 'b' * 40), \
                    mock.patch.object(m, name, None), \
                    mock.patch.object(m.urllib.request, 'build_opener') as opener:
                with self.assertRaisesRegex(m.Hold, 'UNBOUND'):
                    m.fetch_archive(time.monotonic() + 10)
                opener.assert_not_called()

    def test_primary_download_error_survives_close_error_with_uncertainty(self):
        row = self.response()
        primary = OSError(errno.EIO, 'private-download-detail')
        row.read.side_effect = primary
        row.close.side_effect = OSError(errno.EIO, 'private-close-detail')
        with self.assertRaises(OSError) as caught:
            self.fetch(row)
        self.assertIs(caught.exception, primary)
        self.assertTrue(primary.delivery_cleanup_failed)

    def test_close_error_alone_refuses_success(self):
        row = self.response()
        row.close.side_effect = OSError(errno.EIO, 'private-close-detail')
        with self.assertRaises(m.CleanupError):
            self.fetch(row)


class CompilerInputTests(unittest.TestCase):
    def test_actual_archive_passes_real_parser_and_frozen_entry_validator(self):
        extractor, entry, files = m.compiler_inputs(ARCHIVE.read_bytes())
        self.assertEqual(extractor.ROOT_NAME, KIT_LEAF)
        self.assertEqual(entry.__file__, m.COMPILER_ROOT + '/epoch7_recovery_entry.py')
        self.assertEqual(len(files), 256)
        manifest = entry.validate_manifest(entry.decode(files['recovery-kit-manifest.json']))
        runtime = entry.validate_runtime(manifest, files)
        self.assertEqual(len(runtime['files']), 107)
        self.assertEqual((manifest['kit_source_commit'], manifest['kit_source_tree']),
                         (SOURCE_COMMIT, SOURCE_TREE))

    def test_altered_truncated_oversized_or_nonbytes_archive_refuses_before_exec(self):
        raw = ARCHIVE.read_bytes()
        for body in (b'x' + raw[1:], raw[:-1], raw + b'x', raw.decode('latin1')):
            with self.subTest(kind=type(body).__name__, size=len(body)), \
                    mock.patch.object(m.zlib, 'decompressobj') as decompress:
                with self.assertRaisesRegex(m.Hold, 'SOURCE_PIN'):
                    m.compiler_inputs(body)
                decompress.assert_not_called()

    def test_wrong_entry_manifest_source_tree_or_count_refuses(self):
        for name, value in (('COMPILER_ENTRY_SHA', '1' * 64),
                            ('COMPILER_MANIFEST_SHA', '1' * 64),
                            ('COMPILER_SOURCE', '1' * 40),
                            ('COMPILER_TREE', '1' * 40),
                            ('COMPILER_CACHE_COUNT', 252)):
            with self.subTest(name=name), mock.patch.object(m, name, value):
                with self.assertRaises(ValueError):
                    m.compiler_inputs(ARCHIVE.read_bytes())

    def test_wrong_embedded_extractor_pin_refuses_before_exec(self):
        with mock.patch.object(m, 'EXTRACTOR_SHA', '0' * 64):
            with self.assertRaisesRegex(m.Hold, 'EXTRACTOR_PIN'):
                m.compiler_inputs(ARCHIVE.read_bytes())

    def test_other_root_traversal_symlink_and_metadata_refuse_inside_parser(self):
        extractor, unused, unused2 = m.compiler_inputs(ARCHIVE.read_bytes())
        for change in ('root', 'traversal', 'symlink', 'metadata'):
            output = io.BytesIO()
            with tarfile.open(fileobj=io.BytesIO(ARCHIVE.read_bytes()), mode='r:gz') as source:
                with tarfile.open(fileobj=output, mode='w:gz', format=tarfile.USTAR_FORMAT) as dest:
                    for index, member in enumerate(source.getmembers()):
                        content = source.extractfile(member).read() if member.isfile() else b''
                        member = copy.copy(member)
                        if index == 1:
                            if change == 'root':
                                member.name = OLD_KIT_LEAF + '/epoch7_recovery_entry.py'
                            elif change == 'traversal':
                                member.name = KIT_LEAF + '/../escape.py'
                            elif change == 'symlink':
                                member.type, member.linkname, member.size = tarfile.SYMTYPE, '/outside', 0
                            else:
                                member.uname = 'root'
                        dest.addfile(member, io.BytesIO(content) if member.isfile() else None)
            raw = output.getvalue()
            with self.subTest(change=change), self.assertRaises(ValueError):
                extractor.inspect_archive(raw, sha(raw), ENTRY_SHA, MANIFEST_SHA)


class CompilerFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='resourcebind-delivery-', dir=str(HERE))
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.destination = self.parent / KIT_LEAF
        self.old = self.parent / OLD_KIT_LEAF
        self.proxy = os_proxy()
        for name, value in (('CAND', str(self.parent)),
                            ('COMPILER_ROOT', str(self.destination)),
                            ('KIT_ROOT', str(self.old)),
                            ('PREP_ROOT', str(self.parent / PREP_LEAF)), ('os', self.proxy)):
            patcher = mock.patch.object(m, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.raw = ARCHIVE.read_bytes()
        self.extractor, self.entry, self.files = m.compiler_inputs(self.raw)
        for module in (self.extractor, self.entry):
            patcher = mock.patch.object(module, 'os', self.proxy)
            patcher.start()
            self.addCleanup(patcher.stop)

    def stage(self):
        return m.stage_compiler(self.raw, self.extractor, self.entry, self.files,
                                time.monotonic() + 30)

    def snapshot(self, root):
        rows = {}
        for path in [root] + sorted(root.rglob('*')):
            rows[str(path)] = (m.stamp(os.stat(str(path), follow_symlinks=False)),
                               path.read_bytes() if path.is_file() else None)
        return rows

    def test_actual_new_extraction_full_inventory_bytes_and_modes_then_exact_reuse(self):
        first = self.stage()
        self.assertEqual(first, m.compiler_summary('EXTRACTED_AND_VERIFIED'))
        actual = {str(path.relative_to(self.destination)) for path in self.destination.rglob('*')
                  if path.is_file()}
        self.assertEqual(actual, set(self.files))
        for name, raw in self.files.items():
            path = self.destination / name
            self.assertEqual(path.read_bytes(), raw, name)
            self.assertEqual(stat.S_IMODE(os.stat(str(path)).st_mode), 0o444, name)
        for path in [self.destination] + [p for p in self.destination.rglob('*') if p.is_dir()]:
            self.assertEqual(stat.S_IMODE(os.stat(str(path)).st_mode), 0o700, str(path))
        before = self.snapshot(self.destination)
        with mock.patch.object(self.proxy, 'mkdir', side_effect=AssertionError('unexpected mkdir')), \
                mock.patch.object(self.proxy, 'write', side_effect=AssertionError('unexpected write')), \
                mock.patch.object(self.extractor, 'extract', side_effect=AssertionError('unexpected extract')):
            second = self.stage()
        self.assertEqual(second, m.compiler_summary('VERIFIED_EXISTING'))
        self.assertEqual(self.snapshot(self.destination), before)

    def test_saved_a_root_and_prior_preparation_roots_are_untouched(self):
        preserved = []
        for leaf in (OLD_KIT_LEAF, 'epoch7-preparation-candidate-r7-fresh',
                     'epoch7-preparation-candidate-r6'):
            path = self.parent / leaf
            path.mkdir(mode=0o700)
            (path / 'retained').write_bytes(b'original-public-test-evidence')
            os.chmod(str(path / 'retained'), 0o600)
            preserved.append((path, self.snapshot(path)))
        self.stage()
        for path, before in preserved:
            self.assertEqual(self.snapshot(path), before)

    def test_missing_compiler_does_not_reuse_old_a(self):
        self.old.mkdir(mode=0o700)
        (self.old / 'epoch7_recovery_entry.py').write_bytes(b'old-A-not-compiler')
        before = self.snapshot(self.old)
        result = self.stage()
        self.assertEqual(result['state'], 'EXTRACTED_AND_VERIFIED')
        self.assertEqual(self.snapshot(self.old), before)
        self.assertEqual((self.destination / 'epoch7_recovery_entry.py').read_bytes(),
                         self.files['epoch7_recovery_entry.py'])

    def test_existing_incomplete_directory_is_never_overwritten_or_completed(self):
        self.destination.mkdir(mode=0o700)
        marker = self.destination / 'retained'
        marker.write_bytes(b'partial-preexisting-content')
        before = self.snapshot(self.destination)
        with mock.patch.object(self.extractor, 'extract') as extract, \
                mock.patch.object(self.proxy, 'write', side_effect=AssertionError('no write')):
            with self.assertRaises((OSError, ValueError)) as caught:
                self.stage()
        extract.assert_not_called()
        self.assertEqual(self.snapshot(self.destination), before)
        self.assertEqual(caught.exception.compiler_staging['state'], 'VERIFY_EXISTING_FAILED')
        self.assertTrue(caught.exception.delivery_cleanup_failed)

    def test_existing_symlink_or_regular_file_is_never_replaced(self):
        for kind in ('symlink', 'file'):
            if kind == 'symlink':
                os.symlink(str(self.parent), str(self.destination))
            else:
                self.destination.write_bytes(b'preexisting-regular-file')
            before = os.lstat(str(self.destination))
            try:
                with self.subTest(kind=kind), mock.patch.object(self.extractor, 'extract') as extract:
                    with self.assertRaises((OSError, ValueError)) as caught:
                        self.stage()
                    extract.assert_not_called()
                self.assertEqual(os.lstat(str(self.destination)), before)
                self.assertEqual(caught.exception.compiler_staging['state'], 'VERIFY_EXISTING_FAILED')
            finally:
                os.unlink(str(self.destination))

    def test_existing_wrong_bytes_are_never_repaired(self):
        self.stage()
        path = self.destination / 'epoch7_recovery_entry.py'
        os.chmod(str(path), 0o600)
        path.write_bytes(b'x' + self.files[path.name][1:])
        os.chmod(str(path), 0o444)
        before = self.snapshot(self.destination)
        with mock.patch.object(self.extractor, 'extract') as extract:
            with self.assertRaises(ValueError) as caught:
                self.stage()
        extract.assert_not_called()
        self.assertEqual(self.snapshot(self.destination), before)
        self.assertEqual(caught.exception.compiler_staging['state'], 'VERIFY_EXISTING_FAILED')

    def test_extra_existing_file_and_hardlink_are_rejected(self):
        self.stage()
        extra = self.destination / 'unknown'
        extra.write_bytes(b'extra')
        with self.assertRaises(ValueError):
            self.stage()
        extra.unlink()
        os.link(str(self.destination / 'epoch7_recovery_entry.py'), str(self.parent / 'outside-link'))
        with self.assertRaises(ValueError):
            self.stage()

    def test_partial_write_is_retained_as_unverified_and_unknown(self):
        actual = self.proxy.write
        calls = []
        primary = OSError(errno.ENOSPC, 'private-disk-detail')

        def write(fd, raw):
            calls.append(fd)
            if len(calls) == 1:
                return actual(fd, raw[:1])
            raise primary

        with mock.patch.object(self.proxy, 'write', side_effect=write):
            with self.assertRaises(OSError) as caught:
                self.stage()
        self.assertIs(caught.exception, primary)
        self.assertEqual(primary.compiler_staging, m.compiler_summary('EXTRACTION_ATTEMPTED_NOT_VERIFIED'))
        self.assertTrue(primary.delivery_cleanup_failed)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual((self.destination / 'epoch7_recovery_entry.py').read_bytes(),
                         self.files['epoch7_recovery_entry.py'][:1])
        with mock.patch.object(self.extractor, 'extract') as extract:
            with self.assertRaises((OSError, ValueError)):
                self.stage()
        extract.assert_not_called()

    def test_partial_write_primary_survives_close_failure(self):
        actual_close = self.proxy.close
        primary = OSError(errno.ENOSPC, 'private-primary')
        failed = [False]

        def close(fd):
            is_file = stat.S_ISREG(os.fstat(fd).st_mode)
            actual_close(fd)
            if is_file and not failed[0]:
                failed[0] = True
                raise OSError(errno.EIO, 'private-cleanup')

        with mock.patch.object(self.proxy, 'write', side_effect=primary), \
                mock.patch.object(self.proxy, 'close', side_effect=close):
            with self.assertRaises(OSError) as caught:
                self.stage()
        self.assertIs(caught.exception, primary)
        self.assertTrue(failed[0])
        self.assertTrue(primary.delivery_cleanup_failed)
        self.assertEqual(primary.compiler_staging['state'], 'EXTRACTION_ATTEMPTED_NOT_VERIFIED')

    def test_extractor_cleanup_attempts_all_descriptors_preserving_primary(self):
        primary = ValueError('private-primary')
        with mock.patch.object(self.proxy, 'close', side_effect=OSError(errno.EIO, 'private-close')) as close:
            self.extractor.close_all([100, 101, 102], primary)
        self.assertEqual(close.call_args_list, [mock.call(102), mock.call(101), mock.call(100)])
        self.assertTrue(primary.delivery_cleanup_failed)

    def test_failed_verifier_reports_cleanup_uncertainty(self):
        primary = OSError(errno.EIO, 'private-verify-detail')
        with mock.patch.object(self.entry, 'verify_kit', side_effect=primary):
            with self.assertRaises(OSError) as caught:
                m.verify_compiler(self.entry, self.files, time.monotonic() + 10)
        self.assertIs(caught.exception, primary)
        self.assertTrue(primary.delivery_cleanup_failed)


class FlowTests(unittest.TestCase):
    def invoke(self, archive_error=None, input_error=None, compiler_error=None,
               preparation_error=None, after_source_error=None, after_kit_error=None,
               result=None, scope_error=None):
        events = []
        staged = {'state': 'STAGED_EXACT', 'path': m.PREP_ROOT,
                  'files': {name: {'sha256': pin, 'bytes': size}
                            for name, (pin, size) in m.SOURCES.items()},
                  'created_paths': [m.PREP_ROOT] + [m.PREP_ROOT + '/' + name
                                                  for name in sorted(m.SOURCES)]}
        compiler_staged = m.compiler_summary('EXTRACTED_AND_VERIFIED')

        @contextlib.contextmanager
        def scope(*args):
            yield time.monotonic() + 30
            if scope_error is not None:
                raise scope_error

        @contextlib.contextmanager
        def outer_scope(*args):
            yield time.monotonic() + 30

        class PrepareCleanupError(Exception):
            pass

        module = types.SimpleNamespace(CleanupError=PrepareCleanupError, PHASES=frozenset(),
                                       budget=scope)
        extractor, entry, files = m.compiler_inputs(ARCHIVE.read_bytes())

        def fetch_sources(end):
            events.append('download_sources')
            return sources()

        def fetch_archive(end):
            events.append('download_archive')
            if archive_error is not None:
                raise archive_error
            return b'archive fixture, compiler parser is mocked'

        def inputs(raw):
            events.append('authenticate_archive')
            if input_error is not None:
                raise input_error
            return extractor, entry, files

        def load(cache):
            events.append('load_preparer')
            return module

        def compiler(raw, received_extractor, received_entry, received_files, end):
            events.append('stage_compiler')
            self.assertIs(received_extractor, extractor)
            self.assertIs(received_entry, entry)
            self.assertIs(received_files, files)
            if compiler_error is not None:
                raise compiler_error
            return compiler_staged

        def stage(cache, end, allow_create=True):
            events.append('stage_preparation' if allow_create else 'verify_preparation')
            if not allow_create and after_source_error is not None:
                raise after_source_error
            return staged

        def prepare(args, end):
            events.append('prepare')
            if preparation_error is not None:
                raise preparation_error
            return completed_result() if result is None else result

        def verify(received_entry, received_files, end):
            events.append('verify_compiler')
            self.assertIs(received_entry, entry)
            self.assertIs(received_files, files)
            if after_kit_error is not None:
                raise after_kit_error

        module.run_preparation = mock.Mock(side_effect=prepare)
        with contextlib.ExitStack() as stack:
            replacements = {'PINS_BOUND': True, 'PUBLICATION_COMMIT': 'a' * 40,
                'ARCHIVE_COMMIT': 'b' * 40, 'fetch_sources': fetch_sources,
                'fetch_archive': fetch_archive, 'compiler_inputs': inputs, 'preparer': load,
                'stage_compiler': compiler, 'stage': stage, 'verify_compiler': verify,
                'budget': outer_scope}
            for name, value in replacements.items():
                stack.enter_context(mock.patch.object(m, name, value))
            stack.enter_context(mock.patch.object(m.os, 'geteuid', return_value=0))
            stack.enter_context(mock.patch.object(m.os, 'getegid', return_value=0))
            stack.enter_context(mock.patch.object(m.socket, 'gethostname', return_value=m.HOST))
            stack.enter_context(mock.patch.object(m.sys, 'flags', types.SimpleNamespace(isolated=1, no_site=1)))
            stack.enter_context(mock.patch.object(m.sys, 'dont_write_bytecode', True))
            delivered = stack.enter_context(mock.patch.object(m, 'deliver_status'))
            code = m.entrypoint(arguments())
        delivered.assert_called_once()
        return code, events, module, delivered.call_args[0][0], staged, compiler_staged

    def test_archive_is_verified_and_staged_before_same_prepare_call(self):
        code, events, module, status, staged, compiler_staged = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(events, ['download_sources', 'download_archive', 'authenticate_archive',
            'load_preparer', 'stage_compiler', 'stage_preparation', 'prepare',
            'verify_preparation', 'verify_compiler'])
        module.run_preparation.assert_called_once()
        args = module.run_preparation.call_args[0][0]
        self.assertEqual(vars(args), {'operation': 'prepare', 'observation': m.OBSERVATION_PATH,
            'observation_sha256': m.OBSERVATION_SHA256, 'topology_review_id': 123456789,
            'retained_renewal_timer': 'enable-after-reviewed-checks'})
        self.assertEqual(status['staging'], staged)
        self.assertEqual(status['compiler_staging'], compiler_staged)
        self.assertEqual(status['preparation']['outputs'], completed_result()['outputs'])
        self.assertEqual(status['install_admission'], 'NOT_GRANTED')
        self.assertEqual(status['production_resume'], 'NOT_EXECUTED')

    def test_archive_download_failure_cannot_load_stage_or_prepare(self):
        code, events, module, status, unused, unused2 = self.invoke(archive_error=m.Hold('SOURCE_PIN'))
        self.assertEqual(code, 2)
        self.assertEqual(events, ['download_sources', 'download_archive'])
        module.run_preparation.assert_not_called()
        self.assertEqual(status['created_paths'], [])
        self.assertIsNone(status['compiler_staging'])

    def test_archive_validation_failure_cannot_load_stage_or_prepare(self):
        code, events, module, status, unused, unused2 = self.invoke(input_error=m.Hold('COMPILER_SOURCE'))
        self.assertEqual(code, 2)
        self.assertEqual(events[-1], 'authenticate_archive')
        module.run_preparation.assert_not_called()
        self.assertEqual(status['created_paths'], [])

    def test_partial_extraction_retains_safe_unknown_without_preparation(self):
        primary = OSError(errno.ENOSPC, 'private-disk-detail')
        primary.compiler_staging = m.compiler_summary('EXTRACTION_ATTEMPTED_NOT_VERIFIED')
        primary.delivery_cleanup_failed = True
        code, events, module, status, unused, unused2 = self.invoke(compiler_error=primary)
        self.assertEqual(code, 2)
        self.assertEqual(events[-1], 'stage_compiler')
        module.run_preparation.assert_not_called()
        self.assertEqual(status['compiler_staging'], primary.compiler_staging)
        self.assertTrue(status['cleanup_unknown'])
        self.assertEqual(status['created_paths'], [])
        self.assertEqual(status['completed_outputs'], [])
        self.assertNotIn('private-disk-detail', repr(status))

    def test_failed_existing_verification_does_not_claim_extraction(self):
        primary = ValueError('untrusted-existing-detail')
        primary.compiler_staging = m.compiler_summary('VERIFY_EXISTING_FAILED')
        primary.delivery_cleanup_failed = True
        code, events, module, status, unused, unused2 = self.invoke(compiler_error=primary)
        self.assertEqual(code, 2)
        self.assertEqual(status['compiler_staging']['state'], 'VERIFY_EXISTING_FAILED')
        self.assertTrue(status['cleanup_unknown'])
        module.run_preparation.assert_not_called()
        self.assertNotIn('untrusted-existing-detail', repr(status))

    def test_preparation_failure_keeps_both_verified_staging_summaries(self):
        code, events, module, status, staged, compiler_staged = self.invoke(
            preparation_error=ValueError('private-preparation-detail'))
        self.assertEqual(code, 2)
        self.assertEqual(events[-1], 'prepare')
        self.assertEqual(status['staging'], staged)
        self.assertEqual(status['compiler_staging'], compiler_staged)
        self.assertEqual(status['created_paths'], staged['created_paths'])
        self.assertNotIn('private-preparation-detail', repr(status))

    def test_post_prepare_source_drift_retains_exact_three_output_metadata(self):
        code, events, module, status, staged, compiler_staged = self.invoke(
            after_source_error=m.Hold('FILE_BYTES'))
        self.assertEqual(code, 2)
        self.assertEqual(events[-1], 'verify_preparation')
        self.assertEqual(status['failure_label'], 'FILE_BYTES')
        self.assertEqual(status['completed_outputs'], completed_result()['outputs'])
        self.assertEqual(status['created_output_paths'], [row['path'] for row in completed_result()['outputs']])
        self.assertEqual(status['preparation_output_evidence'], 'RETAINED_BOUNDED_METADATA')
        self.assertNotIn('preparation', status)

    def test_post_prepare_kit_drift_retains_exact_three_output_metadata(self):
        code, events, module, status, staged, compiler_staged = self.invoke(
            after_kit_error=m.Hold('COMPILER_RECHECK'))
        self.assertEqual(code, 2)
        self.assertEqual(events[-1], 'verify_compiler')
        self.assertEqual(status['failure_label'], 'COMPILER_RECHECK')
        self.assertEqual(status['completed_outputs'], completed_result()['outputs'])
        self.assertEqual(status['created_output_paths'], [row['path'] for row in completed_result()['outputs']])
        self.assertEqual(status['compiler_staging'], compiler_staged)
        self.assertEqual(status['install_admission'], 'NOT_GRANTED')
        self.assertEqual(status['production_resume'], 'NOT_EXECUTED')

    def test_scope_cleanup_failure_keeps_three_completed_outputs_and_unknown(self):
        primary = m.CleanupError()
        code, events, module, status, staged, compiler_staged = self.invoke(scope_error=primary)
        self.assertEqual(code, 2)
        self.assertTrue(status['cleanup_unknown'])
        self.assertEqual(status['completed_outputs'], completed_result()['outputs'])
        self.assertEqual(status['staging'], staged)
        self.assertEqual(status['compiler_staging'], compiler_staged)

    def test_untrusted_output_metadata_is_redacted_and_marked_unknown(self):
        result = completed_result()
        result['outputs'][0]['path'] = '/private-unapproved-output'
        code, events, module, status, unused, unused2 = self.invoke(result=result)
        self.assertEqual(code, 2)
        self.assertEqual(status['completed_outputs'], [])
        self.assertEqual(status['created_output_paths'], [])
        self.assertEqual(status['preparation_output_evidence'], 'UNKNOWN')
        self.assertTrue(status['cleanup_unknown'])
        self.assertNotIn('/private-unapproved-output', repr(status))

    def test_untrusted_compiler_summary_is_redacted(self):
        primary = ValueError('private-extraction-detail')
        primary.compiler_staging = dict(m.compiler_summary('VERIFY_EXISTING_FAILED'),
                                        private='untrusted-private-content')
        code, events, module, status, unused, unused2 = self.invoke(compiler_error=primary)
        self.assertEqual(code, 2)
        self.assertIsNone(status['compiler_staging'])
        self.assertNotIn('untrusted-private-content', repr(status))


if __name__ == '__main__':
    unittest.main(verbosity=2)

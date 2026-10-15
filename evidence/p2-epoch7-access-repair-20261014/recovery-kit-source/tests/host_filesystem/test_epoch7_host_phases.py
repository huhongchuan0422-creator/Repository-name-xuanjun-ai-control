"""Local synthetic fixtures only; never a production admission or acceptance."""
import copy
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

import epoch7_delta as d
import epoch7_host_phases as h
import epoch7_protected_fs as fs
from test_epoch7_delta import fixture
from test_snapshot import native_transition_fixture,native_pin_context


class Authority(h.ClaimAuthority):
    def __init__(self):
        self.calls = []; self.fail = False; self.io = None
    def receipt(self):
        self.calls.append('receipt')
        if self.fail: raise ValueError('LOCK_LOST')
    def validate_outer(self, raw):
        value = json.loads(raw.decode())
        if value.get('name') != h.OUTER_NAME: raise ValueError('OUTER_NAME')
        return value
    def phase(self, phase):
        self.receipt(); self.calls.append(phase)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        base = str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent / 'fixtures')
        self.root = tempfile.mkdtemp(prefix='fs-', dir=base)
        os.chmod(self.root, 0o700)
        for path in (fs.TRANSACTION, '/etc/xuanjun-development', '/run'):
            os.makedirs(self.root + path, mode=0o700, exist_ok=True)
        self.authority = Authority()
        self.io = h.HostPhaseFilesystem(self.authority, self.root)
    def tearDown(self): shutil.rmtree(self.root)
    def put(self, path, raw, mode=0o600):
        with open(self.root + path, 'wb') as stream: stream.write(raw)
        os.chmod(self.root + path, mode)
    def test_outer_create_and_cas_continue_after_runtime_gate_disappears(self):
        raw = h.packed({'name': h.OUTER_NAME, 'state': 'INTENT'})
        self.io.create_exclusive(h.OUTER_NAME, raw, 0, 0, 0o600)
        before = self.io.read_journal(h.OUTER_NAME)
        self.io.gate = mock.Mock()
        self.io.gate.check.side_effect = RuntimeError('TLS_AND_RUNTIME_CHANGED')
        after = h.packed({'name': h.OUTER_NAME, 'state': 'HOLD'})
        self.io.replace_exact(h.OUTER_NAME, before, after, 0, 0, 0o600)
        self.assertEqual(self.io.read_journal(h.OUTER_NAME)['data'], after)
        self.io.gate.check.assert_not_called()
    def test_outer_cas_rejects_full_stamp_drift(self):
        raw = h.packed({'name': h.OUTER_NAME})
        self.io.create_exclusive(h.OUTER_NAME, raw, 0, 0, 0o600)
        before = self.io.read_journal(h.OUTER_NAME)
        os.utime(self.root + fs.TRANSACTION + '/' + h.OUTER_NAME, ns=(1, 1))
        with self.assertRaisesRegex(ValueError, 'FULL_CAS'):
            self.io.replace_exact(h.OUTER_NAME, before, raw, 0, 0, 0o600)
    def test_outer_duplicate_claim_never_overwrites(self):
        raw = h.packed({'name': h.OUTER_NAME})
        self.io.create_exclusive(h.OUTER_NAME, raw, 0, 0, 0o600)
        with self.assertRaises(FileExistsError):
            self.io.create_exclusive(h.OUTER_NAME, raw, 0, 0, 0o600)
    def test_outer_lock_failure_prevents_write(self):
        self.authority.fail = True
        with self.assertRaisesRegex(ValueError, 'LOCK_LOST'):
            self.io.create_exclusive(h.OUTER_NAME, h.packed({'name': h.OUTER_NAME}), 0, 0, 0o600)
        self.assertFalse(self.io.journal_exists(h.OUTER_NAME))
    def test_inner_journal_names_not_exposed(self):
        with self.assertRaisesRegex(ValueError, 'OUTER_ONLY'):
            self.io.journal_exists('epoch7-recovery-execution.json')
    def test_native_cas_archives_and_checks_complete_before(self):
        self.put(h.snap.NATIVE, b'old', 0o644)
        old, before = self.io.read_exact(h.snap.NATIVE)
        archive = self.io.archive_exact('rebind_prepared_epoch', 'epoch7-prior-native-binding.json', old)
        self.assertEqual(archive['sha256'], h.sha(old))
        after = self.io.replace_file_exact('rebind_prepared_epoch', h.snap.NATIVE,
            before, b'new', 0, 0, 0o644)
        self.assertEqual(after['sha256'], h.sha(b'new'))
        self.assertEqual(self.io.read_exact(fs.TRANSACTION + '/epoch7-prior-native-binding.json')[0], old)
    def test_native_stamp_drift_refused_even_with_same_bytes(self):
        self.put(h.snap.NATIVE, b'old', 0o644)
        old, before = self.io.read_exact(h.snap.NATIVE)
        os.utime(self.root + h.snap.NATIVE, ns=(1, 1))
        with self.assertRaisesRegex(ValueError, 'FULL_BEFORE_CAS'):
            self.io.replace_file_exact('rebind_prepared_epoch', h.snap.NATIVE, before, b'new', 0, 0, 0o644)
        self.assertEqual(self.io.read_exact(h.snap.NATIVE)[0], old)
    def test_unknown_effect_path_and_wrong_phase_refused(self):
        for phase, path in (('activate_new_services', h.snap.NATIVE),
                            ('rebind_prepared_epoch', '/etc/passwd')):
            with self.assertRaisesRegex(ValueError, 'EFFECT_SCOPE'):
                self.io.replace_file_exact(phase, path, {}, b'new', 0, 0, 0o644)
    def test_symlink_parent_refused(self):
        original = self.root + '/etc/xuanjun-development'
        os.rename(original, original + '-actual')
        os.symlink(original + '-actual', original)
        with self.assertRaises(OSError): self.io.read_exact(h.snap.NATIVE)
    def test_hardlink_target_refused(self):
        self.put(h.snap.NATIVE, b'old', 0o644)
        os.link(self.root + h.snap.NATIVE, self.root + h.snap.NATIVE + '.other')
        with self.assertRaisesRegex(ValueError, 'REGULAR_FILE_REQUIRED'):
            self.io.read_exact(h.snap.NATIVE)
    def test_archive_reuse_refused_and_never_truncated(self):
        self.io.archive_exact('rebind_prepared_epoch', 'epoch7-prior-native-binding.json', b'old')
        with self.assertRaises(FileExistsError):
            self.io.archive_exact('rebind_prepared_epoch', 'epoch7-prior-native-binding.json', b'new')
        self.assertEqual(self.io.read_exact(fs.TRANSACTION + '/epoch7-prior-native-binding.json')[0], b'old')
    def test_tls_candidate_is_exclusive_private(self):
        result = self.io.publish_tls_candidate(b'new')
        self.assertEqual((result['mode'], result['nlink']), (0o600, 1))
        with self.assertRaises(FileExistsError): self.io.publish_tls_candidate(b'new')


class Store(object):
    owner_uid = os.geteuid()
    def __init__(self, expected):
        self.current = copy.deepcopy(expected); self.rows = [({'descriptor': copy.deepcopy(expected)}, None)]
        self.fail = None
    def validate(self, value): return copy.deepcopy(value)
    def head(self, value): return d.digest(value)
    def _locked(self): return os.open('/dev/null', os.O_RDONLY)
    def _journal(self): return copy.deepcopy(self.rows)
    def _read_descriptor_unlocked(self): return copy.deepcopy(self.current)
    def _append(self, value, rows, proof):
        self.rows.append(({'descriptor': copy.deepcopy(value), 'proof': proof}, None))
        if self.fail == 'append': raise OSError('APPEND_UNCERTAIN')
    def _write_descriptor(self, value):
        if self.fail == 'write': raise KeyboardInterrupt()
        self.current = copy.deepcopy(value)


class NativeTransitionTests(unittest.TestCase):
    def setUp(self):
        self.raws=native_transition_fixture();self.pins=native_pin_context(self.raws)
        self.pins.start();self.addCleanup(self.pins.stop)
        self.proof=h.snap.validate_native_transition(*self.raws)
        paths=(h.snap.NATIVE,h.snap.NATIVE_PRIOR,h.snap.NATIVE_ORIGINAL,h.snap.NATIVE_ATTEMPT)
        self.records={path:{'kind':'FILE','sha256':h.sha(raw),'uid':0,'gid':0,
            'mode':0o644 if path==h.snap.NATIVE else 0o600,'dev':8,'ino':100+index,'nlink':1,
            'size':len(raw),'mtime_ns':11,'ctime_ns':12} for index,(path,raw) in enumerate(zip(paths,self.raws))}
        self.content=dict(zip(paths,self.raws));self.snapshot,self.candidate=fixture()
        self.candidate['manifest_sha256']=h.MANIFEST
        self.snapshot['receipts']['epoch5-prior-native-binding.json']=self.proof['before_sha256']
        self.snapshot['receipts']['epoch5-recovery-execution.json']=self.proof['attempt_sha256']
        self.snapshot['attempt']['sha256']=self.proof['attempt_sha256']
        self.retained={'files':copy.deepcopy(self.records),'native_binding_transition':copy.deepcopy(self.proof)}
        self.support=self.rebind_support()
    def rebind_support(self):
        self.snapshot['retained_resource_sha256']=d.digest(self.retained)
        return {'snapshot_sha256':d.digest(self.snapshot),'retained':self.retained}
    def core(self):
        before=self.raws[0];after=h.decode(before)
        bridge='/opt/xuanjun-control-releases/integration-'+h.MANIFEST[:16]+'/stage1/native_ledger_bridge.py'
        client=after['ledger']['config'];after['ledger'].update(bridge=bridge,files={bridge:h.BRIDGE_SHA256,
            client:self.candidate['targets'][client]['sha256']})
        tls={'release_sha256':h.MANIFEST,'fixture':'retained TLS identity'};tlsraw=h.packed(tls)
        self.candidate['targets']['/etc/xuanjun-development/tls-renewal.json']['sha256']=h.sha(tlsraw)
        self.snapshot['tls']['config_identity_sha256']=d.digest({'fixture':'retained TLS identity'})
        self.candidate['tls_config_identity_sha256']=self.snapshot['tls']['config_identity_sha256']
        context={'runtime_manifest_sha256':h.MANIFEST,'snapshot_sha256':d.digest(self.snapshot)}
        context['context_sha256']='c'*64
        context['delta_sha256']=d.digest(d.build_delta(self.snapshot,context['snapshot_sha256'],self.candidate))
        io=mock.Mock(spec=h.HostPhaseFilesystem);io.authority=mock.Mock()
        io.authority.binding={'approval_body_sha256':'a'*64}
        io.read_exact.side_effect=lambda path:(self.content[path],copy.deepcopy(self.records[path]))
        io.archive_exact.return_value={'sha256':h.sha(before)}
        io.replace_file_exact.return_value={'sha256':h.sha(h.packed(after))};io.publish_tls_candidate.return_value={}
        store=mock.Mock(spec=h.BoundedActivationStore);store.head.side_effect=d.digest
        artifact={'source_commit':h.SOURCE,'source_tree':h.SOURCE_TREE,'manifest_sha256':h.MANIFEST,
                  'releases':'/opt/xuanjun-control-releases'}
        value=h.CoreHostPhases(io,store,mock.Mock(),context,'b'*64,self.snapshot,self.candidate,
            before,h.packed(after),self.records[h.snap.NATIVE],tlsraw,mock.Mock(spec=h.FrozenBoundedInstaller),
            artifact,native_transition=self.proof,native_proof_metadata=self.records)
        return value,context,io
    def test_retained_proof_binds_current_and_all_private_metadata(self):
        proof,rows=h.retained_native_transition(self.snapshot,self.support,self.raws[0])
        self.assertEqual(proof,self.proof);self.assertEqual(rows,self.records)
        rows[h.snap.NATIVE]['ino']+=1;self.assertNotEqual(rows,self.records)
    def test_self_hashed_forged_proof_or_private_record_rejected(self):
        for change in ('proof','mode','hash','receipt'):
            original=copy.deepcopy((self.retained,self.snapshot))
            if change=='proof':self.retained['native_binding_transition']['original_preserved']=False
            elif change=='mode':self.retained['files'][h.snap.NATIVE_ATTEMPT]['mode']=0o644
            elif change=='hash':self.retained['files'][h.snap.NATIVE_PRIOR]['sha256']='0'*64
            else:self.snapshot['receipts']['epoch5-recovery-execution.json']='0'*64
            with self.subTest(change=change),self.assertRaises(ValueError):
                h.retained_native_transition(self.snapshot,self.rebind_support(),self.raws[0])
            self.retained,self.snapshot=original
    def test_current_prior_and_attempt_bytes_are_not_interchangeable(self):
        for raw in self.raws[1:]:
            with self.assertRaises(ValueError):h.retained_native_transition(self.snapshot,self.support,raw)
    def test_phase_rechecks_real_transition_before_effect_and_after_archive(self):
        core,context,io=self.core()
        with mock.patch.object(h,'rebind_prepared_epoch7',return_value=self.candidate['activation']),\
             mock.patch.object(h.snap,'validate_native_transition',wraps=h.snap.validate_native_transition) as validate:
            core.rebind_prepared_epoch(context,mock.Mock())
        self.assertEqual(validate.call_count,2);io.replace_file_exact.assert_called_once()
        self.assertEqual(io.archive_exact.call_args[0][2],self.raws[0])
    def test_phase_constructor_requires_central_proof_and_exact_private_authority(self):
        for kind in ('proof','metadata','current'):
            oldproof,oldrecords=copy.deepcopy(self.proof),copy.deepcopy(self.records)
            if kind=='proof':self.proof['approval_id']+=1
            elif kind=='metadata':self.records[h.snap.NATIVE_ORIGINAL]['mode']=0o644
            else:self.records[h.snap.NATIVE]['gid']=1002
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.core()
            self.proof,self.records=oldproof,oldrecords
    def test_proof_stamp_drift_stops_before_activation_or_archive(self):
        core,context,io=self.core();self.records[h.snap.NATIVE_ATTEMPT]['ctime_ns']+=1
        with mock.patch.object(h,'rebind_prepared_epoch7') as activate,self.assertRaisesRegex(ValueError,'FULL_STAMP'):
            core.rebind_prepared_epoch(context,mock.Mock())
        activate.assert_not_called();io.archive_exact.assert_not_called();io.replace_file_exact.assert_not_called()
    def test_current_race_during_proof_read_stops_before_activation(self):
        core,context,io=self.core();read=io.read_exact.side_effect
        def changed(path):
            result=read(path)
            if path==h.snap.NATIVE_ATTEMPT:self.records[h.snap.NATIVE]['ctime_ns']+=1
            return result
        io.read_exact.side_effect=changed
        with mock.patch.object(h,'rebind_prepared_epoch7') as activate,self.assertRaisesRegex(ValueError,'NATIVE_PROOF_READ_RACE'):
            core.rebind_prepared_epoch(context,mock.Mock())
        activate.assert_not_called();io.archive_exact.assert_not_called()
    def test_proof_bytes_or_archive_time_drift_stops_native_cas(self):
        for late in (False,True):
            core,context,io=self.core();old=self.content[h.snap.NATIVE_PRIOR]
            def changed(*unused):
                self.content[h.snap.NATIVE_PRIOR]=old+b' ';return {'sha256':h.sha(self.raws[0])}
            if late:io.archive_exact.side_effect=changed
            else:changed()
            with mock.patch.object(h,'rebind_prepared_epoch7',return_value=self.candidate['activation']),\
                 self.subTest(late=late),self.assertRaises(ValueError):core.rebind_prepared_epoch(context,mock.Mock())
            io.replace_file_exact.assert_not_called();self.content[h.snap.NATIVE_PRIOR]=old


class ActivationTests(unittest.TestCase):
    def setUp(self):
        s, c = fixture(); self.old, self.new = s['activation'], c['activation']
        self.new['release_sha256'] = h.MANIFEST
        self.new['binary_sha256'] = h.d.NEW_BINARY
        self.store = Store(self.old)
        self.proof = {k: d.digest(k) for k in ('approval_body_sha256', 'snapshot_sha256', 'recovery_plan_sha256')}
        self.proof.update(controller_transition_sha256=h.d.digest(h.d.controller_transition(self.old,self.new)),old_descriptor_sha256=self.store.head(self.old), new_descriptor_sha256=self.store.head(self.new),
                          all_writers_excluded=True, install_lock_held=True, retained_resources_verified=True)
    def run_rebind(self): return h.rebind_prepared_epoch7(self.store, self.old, self.new, self.proof)
    def test_exact_rebind_preserves_canonical_identity(self):
        self.assertEqual(self.run_rebind(), self.new)
        proof = self.store.rows[-1][0]['proof']
        self.assertEqual(proof['previous_epoch'], 7)
        self.assertFalse(proof['writer_admission'])
    def test_old_epoch5_or_active_transition_refused(self):
        for field, value in (('epoch', 5), ('state', 'ACTIVE')):
            old = copy.deepcopy(self.old); self.old[field] = value
            with self.assertRaises(ValueError): self.run_rebind()
            self.old = old
        self.assertEqual(len(self.store.rows), 1)
    def test_identity_change_refused_before_append(self):
        self.new['db_path'] = '/tmp/other.sqlite'
        with self.assertRaisesRegex(ValueError, 'CANONICAL'): self.run_rebind()
        self.assertEqual(len(self.store.rows), 1)
    def test_stale_descriptor_refused(self):
        self.store.current['state'] = 'FENCED'
        with self.assertRaisesRegex(ValueError, 'STALE_HEAD'): self.run_rebind()
    def test_append_uncertain_does_not_republish_or_retry(self):
        self.store.fail = 'append'
        with self.assertRaises(OSError): self.run_rebind()
        self.assertEqual(self.store.current, self.old)
        self.store.fail = None
        with self.assertRaisesRegex(ValueError, 'STALE_HEAD'): self.run_rebind()
    def test_publish_interrupt_preserves_advanced_journal(self):
        self.store.fail = 'write'
        with self.assertRaises(KeyboardInterrupt): self.run_rebind()
        self.assertEqual(self.store.rows[-1][0]['descriptor'], self.new)
        self.assertEqual(self.store.current, self.old)
    def test_false_or_unknown_proof_refused(self):
        self.proof['all_writers_excluded'] = 1
        with self.assertRaisesRegex(ValueError, 'PROOF_BINDING'): self.run_rebind()


class TLSTests(unittest.TestCase):
    def setUp(self):
        self.config = {'release_sha256': d.OLD_MANIFEST, 'transaction_id': d.TX, 'root': h.snap.TLS}
        self.old = {'config': self.config, 'state': h.READY, 'certificate_sha256': d.digest('cert'),
                    'fingerprint': d.digest('tree'), 'history': {'issuance_replayed': False}}
        self.raw = h.packed(self.old)
        self.expected = {'journal_sha256': h.sha(self.raw), 'state': h.READY,
            'certificate_sha256': self.old['certificate_sha256'], 'tree_fingerprint_sha256': self.old['fingerprint'],
            'config_identity_sha256': d.digest({k: v for k, v in self.config.items() if k != 'release_sha256'})}
        self.new = dict(self.config, release_sha256=h.MANIFEST)
    def test_transform_changes_only_release_config(self):
        after = h.decode(h.tls_metadata_candidate(self.raw, h.packed(self.new), self.expected))
        expected = copy.deepcopy(self.old); expected['config'] = self.new
        self.assertEqual(after, expected)
        self.assertEqual(h.decode(self.raw), self.old)
    def test_hold_not_eligible_for_issuance_or_dryrun_fallback(self):
        self.old['state'] = 'HOLD'; self.raw = h.packed(self.old)
        self.expected['journal_sha256'] = h.sha(self.raw)
        with self.assertRaisesRegex(ValueError, 'READY_TLS'): h.tls_metadata_candidate(self.raw, h.packed(self.new), self.expected)
    def test_other_config_change_refused(self):
        self.new['root'] = '/tmp/other'
        with self.assertRaisesRegex(ValueError, 'IDENTITY_CHANGED'): h.tls_metadata_candidate(self.raw, h.packed(self.new), self.expected)
    def test_certificate_drift_refused(self):
        self.expected['certificate_sha256'] = d.digest('different')
        with self.assertRaisesRegex(ValueError, 'READY_TLS'): h.tls_metadata_candidate(self.raw, h.packed(self.new), self.expected)
    def test_duplicate_json_fields_refused(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            h.tls_metadata_candidate(b'{"state":"READY","state":"HOLD"}', h.packed(self.new), self.expected)
    def test_no_tls_call_or_generic_runtime_import(self):
        source = pathlib.Path(h.__file__).read_text()
        for forbidden in ('import p2_tls_lifecycle', 'import epoch5_retained_runtime',
                          'import epoch5_retained_tls', '.communicate('):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__': unittest.main()

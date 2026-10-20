"""I1 synthetic GitHub + temporary root identities. Never a real approval."""
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('i1installer', ROOT/'deploy/pr122-r4-controlled-install/controlled_install.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)
G = INSTALL.approval_module()


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest('Isolated root identity required')
        self.temp = tempfile.TemporaryDirectory(prefix='i1-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.base.chmod(0o700)
        self.anchor = self.base/'install-admission.json'
        self.registry = self.base/'consumed'
        self.own = self.base/'installer.py'
        self.own.write_bytes((ROOT/G.INSTALLER_PATH).read_bytes())
        self.own.chmod(0o400)
        self.now = 1700000000
        self.identifier = 123456
        self.value = dict(schema_version=1, kind='PR122_R4_ACTION_APPROVAL',
            decision='APPROVED_EXACT_ONE_ATTEMPT', reviewer_role='INDEPENDENT_AUDITOR',
            repository=G.REPO, pr_number=122, host=G.HOST, action='install', max_attempts=1,
            source_commit='a'*40, source_tree='b'*40,
            installer_sha256=hashlib.sha256(self.own.read_bytes()).hexdigest(),
            binding_sha256='', artifact_id=12345, artifact_zip_sha256='c'*64,
            artifact_tar_sha256='d'*64, expected_source_sha256=G.SOURCE_SHA,
            result_source_sha256=G.CANDIDATE_SHA, helper_sha256=G.HELPER_SHA,
            allowed_effects=G.EFFECTS['install'], negative_post_requests_max=4,
            issued_at=self.now, expires_at=self.now+3600, approval_nonce='e'*32)
        self.binding = json.dumps({'files': {G.INSTALLER_PATH:self.value['installer_sha256']}}).encode()
        self.value['binding_sha256'] = hashlib.sha256(self.binding).hexdigest()
        self.pin = dict(schema_version=1, action='install', approval_comment_id=self.identifier,
            approval_body_sha256='', owner_attests_independent_review=True,
            owner_confirms_backend_outage=False)
        self.comment = dict(id=self.identifier,
            issue_url='https://api.github.com/repos/'+G.REPO+'/issues/122',
            user={'id':G.AUTHOR_ID}, performed_via_github_app={'id':G.APP_ID},
            created_at=datetime.fromtimestamp(self.now, timezone.utc).isoformat().replace('+00:00','Z'))
        self.commit = {'sha':'a'*40,'tree':{'sha':'b'*40}}
        self.artifact = dict(id=12345, expired=False, digest='sha256:'+'c'*64,
            workflow_run=dict(head_sha='a'*40,repository_id=1413132159,head_repository_id=1413132159))
        self.entries = {G.INSTALLER_PATH:self.own.read_bytes(), G.BINDING_PATH:self.binding}
        self.hostpatch = mock.patch.object(G.os, 'uname', return_value=types.SimpleNamespace(nodename=G.HOST))
        self.hostpatch.start()
        self.addCleanup(self.hostpatch.stop)
        self.publish()

    def publish(self, body=None):
        self.comment['body'] = body if body is not None else G.BEGIN+json.dumps(self.value,sort_keys=True)+G.END
        self.pin['approval_body_sha256'] = hashlib.sha256(self.comment['body'].encode()).hexdigest()
        self.write_pin()

    def write_pin(self):
        self.anchor.write_text(json.dumps(self.pin))
        self.anchor.chmod(0o600)

    def fetch(self, path):
        prefix = '/repos/'+G.REPO
        if path == prefix+'/issues/comments/'+str(self.identifier): return self.comment
        if path == prefix+'/git/commits/'+'a'*40: return self.commit
        if path == prefix+'/actions/artifacts/12345': return self.artifact
        for name, data in self.entries.items():
            if path == prefix+'/contents/'+name+'?ref='+'a'*40:
                return dict(type='file',path=name,encoding='base64',content=base64.b64encode(data).decode())
        raise AssertionError('Unexpected synthetic URL '+path)

    def gate(self, action='install'):
        return G.Gate(action,self.own,anchor=self.anchor,registry=self.registry,fetch=self.fetch,clock=lambda:self.now)

    def deny(self, message=None):
        with self.assertRaises((ValueError,OSError,AssertionError)) as context:
            self.gate().validate()
        if message: self.assertIn(message,str(context.exception))
        self.assertFalse(self.registry.exists())

    def test_valid_exact_ticket_consumes_once(self):
        ticket=self.gate().validate()
        self.assertIn('NOT_CRYPTOGRAPHIC',ticket.snapshot()['trust_boundary'])
        G.require_ticket(ticket,'install')
        ticket.consume()
        self.assertEqual(len(list(self.registry.iterdir())),1)
        self.assertEqual(next(self.registry.iterdir()).stat().st_mode & 0o777,0o600)
        with self.assertRaises(ValueError): ticket.consume()
        with self.assertRaisesRegex(ValueError,'ALREADY_CONSUMED'): self.gate().validate()

    def test_missing_owner_pin_no_state(self):
        self.anchor.unlink(); self.deny()
    def test_shared_github_identity_is_not_owner_attestation(self):
        self.pin['owner_attests_independent_review']=False;self.write_pin();self.deny('OWNER_PIN')
    def test_developer_comment_changed_without_owner_pin(self):
        self.comment['body']+=' forged';self.deny('BODY_MISMATCH')
    def test_old_source_only_pass_has_no_action_approval(self):
        self.publish('AUDIT_PASS_WITH_SCOPE_LIMITS: source only');self.deny('EXPLICIT_ACTION')
    def test_foreign_comment_provenance(self):
        self.comment['issue_url']+='0';self.deny('PROVENANCE')
    def test_expired_approval(self):
        self.value['expires_at']=self.now;self.publish();self.deny('EXPIRED')
    def test_future_approval(self):
        self.value['issued_at']=self.now+1;self.publish();self.deny('EXPIRED')
    def test_lifetime_over_one_day(self):
        self.value['expires_at']=self.now+86401;self.publish();self.deny('EXPIRED')
    def test_wrong_host(self):
        self.value['host']='other';self.publish();self.deny('SCOPE')
    def test_wrong_action(self):
        self.value['action']='rollback-offline';self.publish();self.deny('SCOPE')
    def test_added_effect(self):
        self.value['allowed_effects']=self.value['allowed_effects']+['dns_change'];self.publish();self.deny('SCOPE')
    def test_wrong_source_version(self):
        self.value['expected_source_sha256']='f'*64;self.publish();self.deny('SOURCE_OR_ACTION')
    def test_installer_local_drift(self):
        self.own.chmod(0o600);self.own.write_bytes(b'foreign');self.own.chmod(0o400);self.deny('INSTALLER_HASH')
    def test_commit_tree_drift(self):
        self.commit['tree']['sha']='f'*40;self.deny('COMMIT_TREE')
    def test_commit_installer_drift(self):
        self.entries[G.INSTALLER_PATH]=b'foreign';self.deny('COMMIT_BYTES')
    def test_binding_drift(self):
        self.entries[G.BINDING_PATH]=b'{}';self.deny('MANIFEST')
    def test_zip_digest_mismatch(self):
        self.artifact['digest']='sha256:'+'f'*64;self.deny('ARTIFACT')
    def test_artifact_other_commit(self):
        self.artifact['workflow_run']['head_sha']='f'*40;self.deny('ARTIFACT')
    def test_artifact_expired(self):
        self.artifact['expired']=True;self.deny('ARTIFACT')
    def test_duplicate_approval_json(self):
        text=json.dumps(self.value).replace('"schema_version": 1','"schema_version": 1, "schema_version": 1')
        self.publish(G.BEGIN+text+G.END);self.deny('DUPLICATE')
    def test_pin_wrong_mode(self):
        self.anchor.chmod(0o644);self.deny('IDENTITY')
    def test_pin_symlink(self):
        saved=self.base/'pin-saved';self.anchor.rename(saved);self.anchor.symlink_to(saved);self.deny()
    def test_installer_wrong_mode(self):
        self.own.chmod(0o600);self.deny('IDENTITY')
    def test_install_cannot_include_outage_consent(self):
        self.pin['owner_confirms_backend_outage']=True;self.write_pin();self.deny('OWNER_PIN')
    def test_ticket_age_expires_before_mutation(self):
        ticket=self.gate().validate();self.now+=31
        with self.assertRaises(ValueError):ticket.consume()
        self.assertFalse(self.registry.exists())
    def test_pin_changed_after_validation(self):
        ticket=self.gate().validate();self.pin['approval_body_sha256']='f'*64;self.write_pin()
        with self.assertRaisesRegex(ValueError,'PIN_CHANGED'):ticket.consume()
        self.assertFalse(self.registry.exists())
    def test_installer_changed_after_validation(self):
        ticket=self.gate().validate();self.own.chmod(0o600);self.own.write_bytes(b'changed');self.own.chmod(0o400)
        with self.assertRaisesRegex(ValueError,'DRIFT'):ticket.consume()
        self.assertFalse(self.registry.exists())
    def test_approval_edited_or_revoked_before_consumption(self):
        ticket=self.gate().validate();self.comment['body']='REVOKED'
        with self.assertRaisesRegex(ValueError,'CHANGED_BEFORE'):ticket.consume()
        self.assertFalse(self.registry.exists())
    def test_two_validated_tickets_only_one_consumes(self):
        first=self.gate().validate();second=self.gate().validate();first.consume()
        with self.assertRaises(ValueError):second.consume()
        self.assertEqual(len(list(self.registry.iterdir())),1)
    def test_plaintext_boolean_or_dictionary_is_not_ticket(self):
        for fake in (None,True,{'approved':True},mock.Mock()):
            with self.subTest(fake=type(fake).__name__):
                with self.assertRaisesRegex(ValueError,'EXACT_INDEPENDENT'):G.require_ticket(fake,'install')
    def test_ticket_action_cannot_be_reused_for_rollback(self):
        ticket=self.gate().validate()
        with self.assertRaises(ValueError):G.require_ticket(ticket,'rollback-offline')
        self.assertFalse(self.registry.exists())
    def test_rollback_requires_separate_owner_outage_confirmation(self):
        self.value.update(action='rollback-offline',allowed_effects=G.EFFECTS['rollback-offline'],negative_post_requests_max=0,
            expected_source_sha256=G.CANDIDATE_SHA,result_source_sha256=G.SOURCE_SHA)
        self.pin['action']='rollback-offline';self.publish()
        with self.assertRaisesRegex(ValueError,'OWNER_PIN'):self.gate('rollback-offline').validate()
        self.pin['owner_confirms_backend_outage']=True;self.write_pin()
        ticket=self.gate('rollback-offline').validate()
        self.assertEqual(ticket.snapshot()['negative_post_requests_max'],0)
        self.assertFalse(self.registry.exists())
    def test_cli_denies_before_engine_or_lock(self):
        with mock.patch.object(INSTALL.sys,'argv',['installer.py','--install']),mock.patch.object(G.Gate,'validate',side_effect=ValueError('NO_APPROVAL')),mock.patch.object(INSTALL,'load_engine') as engine,mock.patch.object(INSTALL,'lock_file') as lock:
            with self.assertRaisesRegex(ValueError,'NO_APPROVAL'):INSTALL.main()
            engine.assert_not_called();lock.assert_not_called()
    def test_direct_install_denies_before_state_or_service(self):
        engine=mock.Mock();op=INSTALL.Operation(engine,root=self.base/'state',source=self.base/'source',summary=self.base/'receipt')
        with self.assertRaisesRegex(ValueError,'EXACT_INDEPENDENT'):op.install()
        self.assertFalse((self.base/'state').exists());engine.assert_not_called()
    def test_cross_process_atomic_consumption(self):
        import multiprocessing
        context=multiprocessing.get_context('fork')
        start=context.Event();results=context.Queue()
        self.registry.mkdir(mode=0o700)
        def worker():
            ticket=self.gate().validate()
            results.put('ready')
            start.wait(5)
            try:
                ticket.consume();results.put('consumed')
            except (ValueError,OSError):results.put('denied')
        processes=[context.Process(target=worker) for _ in range(2)]
        for process in processes:process.start()
        self.assertEqual([results.get(timeout=3),results.get(timeout=3)],['ready','ready'])
        start.set()
        for process in processes:process.join(5)
        for process in processes:
            if process.is_alive():process.terminate();process.join();self.fail('bounded race timed out')
            self.assertEqual(process.exitcode,0)
        self.assertEqual(sorted([results.get(timeout=2),results.get(timeout=2)]),['consumed','denied'])
        self.assertEqual(len(list(self.registry.iterdir())),1)
    def test_partial_marker_failure_preserves_spent_authority(self):
        ticket=self.gate().validate()
        with mock.patch.object(G.os,'fsync',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):ticket.consume()
        self.assertTrue(ticket._marker.exists())
        with self.assertRaisesRegex(ValueError,'ALREADY_CONSUMED'):self.gate().validate()
    def test_network_failure_fails_closed_without_state(self):
        gate=self.gate();gate.fetch=mock.Mock(side_effect=TimeoutError('synthetic GitHub timeout'))
        with self.assertRaises(TimeoutError):gate.validate()
        self.assertFalse(self.registry.exists())
    def test_actual_wrong_machine_denied_before_fetch(self):
        gate=self.gate();gate.fetch=mock.Mock()
        with mock.patch.object(G.os,'uname',return_value=types.SimpleNamespace(nodename='other')):
            with self.assertRaisesRegex(ValueError,'APPROVED_HOST'):gate.validate()
        gate.fetch.assert_not_called()
        self.assertFalse(self.registry.exists())
    def test_no_real_admission_or_receipt_generator(self):
        self.assertFalse(hasattr(G,'create_approval'))
        self.assertNotIn('grant.json',G.github_json.__code__.co_consts)
        self.assertEqual(hashlib.sha256(base64.b64decode(INSTALL.GATE_B64,validate=True)).hexdigest(),INSTALL.GATE_SHA256)
        self.assertEqual(base64.b64decode(INSTALL.GATE_B64),(ROOT/'deploy/pr122-r4-controlled-install/approval_gate.py').read_bytes())

if __name__ == '__main__': unittest.main()

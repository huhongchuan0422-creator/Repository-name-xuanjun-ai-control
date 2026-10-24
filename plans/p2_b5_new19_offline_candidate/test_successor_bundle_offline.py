import json
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'reused-6825'),str(ROOT/'successor_controller'),
              str(ROOT/'new19-source')]

import pr17_b5_successor_binder as binder
import pr17_b5_successor_review as c53
from pr17_b5_successor_authority import prepare_maintenance_candidate, ExistingRequestAuthority
from pr17_b5_successor_backend import R2HostBackend
from pr17_b5_successor_fixed_io import FixedR2IO


class SyntheticSixSlotTests(unittest.TestCase):
    """Synthetic baseline bypasses only old real-byte fingerprint, not source pins."""
    def setUp(self):
        self.spec=binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        manifest=(ROOT/'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
        listing=json.loads((ROOT/'SOURCE_MANIFEST.json').read_bytes())
        self.source={x['release_path']:(ROOT/x['bundle_path']).read_bytes()
                     for x in listing['files'] if x['release_path'] is not None}
        self.source[binder.MANIFEST_PATH]=manifest
        self.baselines={
            c53.CONFIGS[0]:c53.canon(dict(executor_sha256=binder.E78_PIN,
                allowed_actor_ids=[332398908],github_token_ref='/fixture/ref',
                github_token_owner=1003,credentials_ref='/fixture/credentials',
                state_root='/var/lib/xuanjun-cloud-connection',poll_seconds=30)),
            c53.CONFIGS[1]:c53.canon(dict(schema=1,enabled=True,hostname=binder.HOST,
                client_secret_ref='/etc/fixture-secret',settings=dict(
                    issuer='fixture-issuer',endpoint='fixture-endpoint',client_id='fixture',
                    audience='fixture',subjects={binder.ACTOR:{'projects':[]}}))),
            c53.CONFIGS[2]:('OAUTH_CONFIG_SHA256='+binder.RESOURCE_SHA+'\n'
                'OAUTH_SOURCE_MANIFEST_SHA256='+binder.E78_MANIFEST+'\n'
                'SSL_CERT_FILE='+binder.CERT+'\n').encode('ascii'),
            binder.BIND:b'{}',binder.CUSTODY:b'{}',binder.CATALOG:b'{}'}

    def make(self):
        # Original real baseline hashes are unavailable in this workspace;
        # this explicit fixture cannot be used for a production candidate.
        def fixture_only(*_):
            env,order=c53.env_read(self.baselines[c53.CONFIGS[2]])
            return (copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[0]])),
                    copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[1]])),
                    env,order)
        with patch.object(c53,'verify_observed_bytes',fixture_only):
            result=c53.make_bundle(self.spec,self.baselines,self.source,
                batch_id='isolated-unit-batch-20261024',approval_ref='fixture-only',
                window_start=1792830000)
            self.assertTrue(c53.validate_bundle(self.spec,result,
                verified_baselines=self.baselines,verified_source_blobs=self.source))
        return result

    def test_new_pin_manifest_six_slots_and_nineteen(self):
        result=self.make()
        self.assertEqual(set(result['files']),set(c53.CONFIGS+c53.SLOTS))
        self.assertEqual(len(result['requests']),19)
        self.assertEqual(json.loads(result['files'][c53.CONFIGS[0]])['executor_sha256'],
                         binder.CODEPIN)
        self.assertIn(binder.MANIFEST.encode(),result['files'][c53.CONFIGS[2]])
        self.assertFalse(result['authority_verified'])
        self.assertFalse(result['submitted'])

    def test_wrong_source_fails_even_synthetic_baseline(self):
        self.source['production/cloud_connection/queue.py']+=b'changed'
        with self.assertRaisesRegex(binder.Hold,'SOURCE_BYTES_CHANGED'):
            self.make()

    def test_actual_preparation_factory_reads_complete_deliverable_without_action(self):
        # The baseline fingerprint is an explicit fixture. The source loader,
        # adapter, backend, authority and transaction constructors are real.
        # No grant, witness, host command, or original HTTP call is fabricated.
        class RecordedBaselineIO(FixedR2IO):
            def __init__(self, spec, baselines):
                super().__init__(spec)
                self.baselines=baselines
            def read(self, path):
                self._path(path)
                return self.baselines[path], ('fixture',path)
        def private_bytes(path, limit, contents=False):
            self.assertIn(path,self.baselines)
            self.assertLessEqual(len(self.baselines[path]),limit)
            return self.baselines[path] if contents else ('fixture',path)
        def fixture_only(*_):
            env,order=c53.env_read(self.baselines[c53.CONFIGS[2]])
            return (copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[0]])),
                    copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[1]])),env,order)
        with patch.object(c53,'verify_observed_bytes',fixture_only):
            tx=prepare_maintenance_candidate(
                spec_raw=(ROOT/'SUCCESSOR_SPEC.json').read_bytes(),
                source_root=str(ROOT/'new19-source'),
                legacy_io=RecordedBaselineIO(self.spec,self.baselines),
                private_bytes=private_bytes,
                batch_id='c53-recovery-draft',
                approval_ref='fixture-only',window_start=1792830000,
                attempt_id='isolated-attempt')
        self.assertIs(type(tx.b),R2HostBackend)
        self.assertIs(type(tx.b.authority),ExistingRequestAuthority)
        self.assertEqual(len(tx.bundle['requests']),19)
        self.assertEqual(tx.b.source_blobs[binder.MANIFEST_PATH],
                         (ROOT/'RUNTIME_SOURCE_MANIFEST.json').read_bytes())
        self.assertFalse(tx.b.reserved)
        self.assertFalse(tx.b.worker_stopped)

    def test_preparation_factory_rejects_batch_that_changes_fixed_request_ids(self):
        class RecordedBaselineIO(FixedR2IO):
            def read(self, path):
                self._path(path)
                return self_outer.baselines[path], ('fixture',path)
        self_outer=self
        def private_bytes(path, limit, contents=False):
            return self.baselines[path] if contents else ('fixture',path)
        def fixture_only(*_):
            env,order=c53.env_read(self.baselines[c53.CONFIGS[2]])
            return (copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[0]])),
                    copy.deepcopy(json.loads(self.baselines[c53.CONFIGS[1]])),env,order)
        with patch.object(c53,'verify_observed_bytes',fixture_only):
            with self.assertRaisesRegex(Exception,'ORIGINAL_AUTHORITY_CATALOG_REQUEST_MISMATCH'):
                prepare_maintenance_candidate(
                    spec_raw=(ROOT/'SUCCESSOR_SPEC.json').read_bytes(),
                    source_root=str(ROOT/'new19-source'),
                    legacy_io=RecordedBaselineIO(self.spec),
                    private_bytes=private_bytes,
                    batch_id='different-fixed-batch',approval_ref='fixture-only',
                    window_start=1792830000,attempt_id='isolated-attempt')


if __name__=='__main__':
    unittest.main()

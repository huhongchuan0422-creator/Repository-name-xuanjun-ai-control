"""Synthetic protected-reader fixtures: never a production approval source."""
import json
from pathlib import Path
import sys
import os
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT/'reused-6825'), str(ROOT/'successor_controller')]
import pr17_b5_successor_review as c53
from pr17_b5_successor_release_gate import ExternalReleaseGate
from pr17_b5_successor_backend import R2HostBackend
from pr17_b5_successor_witness import (SuccessorEvidenceStore, JOB, COMMIT,
                                        PROJECT, RECIPIENT, SUBJECT)


def fixture_gate(spec, phase='publish'):
    paths = [*sorted((ROOT/'successor_controller').glob('*.py')),
             *(ROOT/name for name in ('successor_contract.py',
                                        'successor_source_loader.py',
                                        'successor_analyst_read.py'))]
    sources = {str(path.relative_to(ROOT)):path.read_bytes() for path in paths}
    rows=[{'path':path,'bytes':len(raw),'sha256':c53.sha(raw)}
          for path,raw in sorted(sources.items())]
    manifest = c53.canon({'schema':'PR17_B5_SUCCESSOR_CONTROLLER_SOURCE_V1',
                          'files':rows})
    binder = c53.canon({'schema':'PR17_B5_SUCCESSOR_EXTERNAL_BINDER_V1',
        'state':'SOURCE_IDENTITY_ONLY_NOT_INSTALL_ADMISSION',
        'controller_commit':'a'*40,
        'controller_manifest_sha256':c53.sha(manifest),
        'controller_code_pin_sha256':c53.sha(c53.canon(sorted(
            (r['path'],r['bytes'],r['sha256']) for r in rows))),
        'successor_spec_sha256':c53.binder.SPEC_SHA256,
        'runtime_release_commit':c53.COMMIT,
        'runtime_manifest_sha256':c53.MANIFEST,
        'runtime_code_pin_sha256':c53.PIN,
        'job':spec['fixed_paths']['job_proposed'],
        'project':c53.PROJ,'recipient':c53.RECIP,
        'target_release':spec['fixed_paths']['target_release']})
    old=[base+'/releases/e78bd7749414d1637012f57b65d2019955282fc3'
         for base in c53.BASES]
    current=dict(zip(c53.BASES, spec['fixed_paths']['target_release']
                     if phase in ('start','recover') else old))
    listed=json.loads((ROOT/'SOURCE_MANIFEST.json').read_bytes())
    runtime={x['release_path']:(ROOT/x['bundle_path']).read_bytes()
             for x in listed['files'] if x['release_path'] is not None}
    runtime[c53.binder.MANIFEST_PATH]=(ROOT/'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
    return ExternalReleaseGate(approved_sha256=c53.sha(binder),
        read_binder=lambda:binder, read_manifest=lambda:manifest,
        read_source=lambda name:sources[name],read_current=lambda:current,
        read_installed_runtime=lambda base,name:runtime[name])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.spec=c53.binder.verify_spec_bytes((ROOT/'SUCCESSOR_SPEC.json').read_bytes())

    def test_all_four_phases_reread_exact_source(self):
        for phase in ('preflight','publish','start','recover'):
            gate=fixture_gate(self.spec,phase)
            self.assertEqual(gate.check(phase,self.spec),'a'*40)

    def test_registered_release_reread_and_revocation(self):
        with tempfile.TemporaryDirectory() as parent:
            root=Path(parent)/'evidence';root.mkdir(mode=0o700)
            (root/'register.lock').write_bytes(b'')
            os.chmod(root/'register.lock',0o600)
            store=SuccessorEvidenceStore(str(root),enabled=True,
                          test_only=True,clock=lambda:1001)
            binding=dict(batch='batch1',job=JOB,attempt='attempt1',
                ids=self.spec['batch']['draft_request_ids'],catalog_sha256='a'*64,
                recipient=RECIPIENT,project=PROJECT,subject=SUBJECT,commit=COMMIT,
                valid_from=1000,valid_until=4600)
            fixture=fixture_gate(self.spec)
            raw=fixture.read_binder();record=json.loads(raw)
            fields=('controller_commit','controller_manifest_sha256',
                'controller_code_pin_sha256','successor_spec_sha256',
                'runtime_manifest_sha256','runtime_code_pin_sha256',
                'target_release')
            payload={key:record[key] for key in fields}
            payload.update(binder_sha256=c53.sha(raw),catalog_sha256='a'*64)
            store.register_exact(binding,'release',source_id='original-version',
                source_raw=b'original reviewed version',
                witness_identity='uk-coordinator',payload=payload)
            gate=ExternalReleaseGate.from_registered(store,binding,
                read_binder=fixture.read_binder,
                read_manifest=fixture.read_manifest,
                read_source=fixture.read_source,
                read_current=fixture.read_current,
                read_installed_runtime=fixture.read_installed_runtime)
            self.assertEqual(gate.check('publish',self.spec),'a'*40)
            store.revoke_exact(binding,'review-withdrawn')
            with self.assertRaisesRegex(Exception,'SUCCESSOR_EVIDENCE_REVOKED'):
                gate.check('publish',self.spec)

    def test_repository_binder_matches_actual_frozen_controller_bytes(self):
        # The digest is computed here only as a fixture. Production must read
        # its approved digest from a separate protected authority record.
        raw=(ROOT/'EXTERNAL_SUCCESSOR_DEPLOYMENT_BINDER.json').read_bytes()
        manifest=(ROOT/'SUCCESSOR_CONTROLLER_SOURCE_MANIFEST.json').read_bytes()
        old={base:base+'/releases/e78bd7749414d1637012f57b65d2019955282fc3'
             for base in c53.BASES}
        listed=json.loads((ROOT/'SOURCE_MANIFEST.json').read_bytes())
        runtime={x['release_path']:(ROOT/x['bundle_path']).read_bytes()
                 for x in listed['files'] if x['release_path'] is not None}
        runtime[c53.binder.MANIFEST_PATH]=(ROOT/'RUNTIME_SOURCE_MANIFEST.json').read_bytes()
        current=dict(old)
        gate=ExternalReleaseGate(approved_sha256=c53.sha(raw),
            read_binder=lambda:raw,read_manifest=lambda:manifest,
            read_source=lambda name:(ROOT/name).read_bytes(),
            read_current=lambda:current,
            read_installed_runtime=lambda base,name:runtime[name])
        for phase in ('preflight','publish','start','recover'):
            if phase=='start':
                current.update(zip(c53.BASES,self.spec['fixed_paths']['target_release']))
            self.assertEqual(gate.check(phase,self.spec),
                             '98c2353863889fd6052d88760ae03a05c997ae12')

    def test_binder_wrong_spec_or_current_rejected(self):
        gate=fixture_gate(self.spec,'publish')
        gate.read_current=lambda:{base:'wrong' for base in c53.BASES}
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_CURRENT_RELEASE_CHANGED'):
            gate.check('publish',self.spec)
        gate=fixture_gate(self.spec,'publish')
        raw=gate.read_binder().replace(b'"successor_spec_sha256":"',
                                       b'"successor_spec_sha256":"f')
        gate.read_binder=lambda:raw
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_BINDER_APPROVED_BYTES_CHANGED'):
            gate.check('publish',self.spec)

    def test_one_changed_source_rejected(self):
        gate=fixture_gate(self.spec)
        original=gate.read_source
        gate.read_source=lambda name:(original(name)+b'altered' if name.endswith('successor_review.py')
                                      else original(name))
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_CONTROLLER_BYTES_CHANGED'):
            gate.check('publish',self.spec)

    def test_changed_installed_runtime_refuses_start(self):
        gate=fixture_gate(self.spec,'start')
        original=gate.read_installed_runtime
        gate.read_installed_runtime=lambda base,name:(original(base,name)+b'altered'
            if base==c53.BASES[1] and name==self.spec['source']['source_records'][0]['path']
            else original(base,name))
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_INSTALLED_RUNTIME_BYTES_CHANGED'):
            gate.check('start',self.spec)

    def test_start_checks_current_before_command(self):
        class IO:
            calls=[]
            def command(self,*args):self.calls.append(args)
        backend=object.__new__(R2HostBackend)
        backend.spec=self.spec;backend.legacy=IO();backend.tried_start=True
        backend.release_gate=fixture_gate(self.spec,'publish')
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_CURRENT_RELEASE_CHANGED'):
            backend.start_worker_bounded()
        self.assertEqual(backend.legacy.calls,[])
        backend.release_gate=fixture_gate(self.spec,'start')
        backend.start_worker_bounded()
        self.assertEqual(len(backend.legacy.calls),1)

    def test_recovery_checks_binder_before_journal_read(self):
        class IO:
            def read(self,*args):raise AssertionError('JOURNAL_READ_BEFORE_BINDER')
        backend=object.__new__(R2HostBackend)
        backend.spec=self.spec;backend.legacy=IO()
        backend.release_gate=fixture_gate(self.spec,'publish')
        with self.assertRaisesRegex(c53.Hold,'EXTERNAL_CURRENT_RELEASE_CHANGED'):
            backend.recover_intake_readonly({'requests':[{}]*19})


if __name__=='__main__':unittest.main()

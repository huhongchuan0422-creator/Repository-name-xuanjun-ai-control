"""Durable diagnostics on the current repository's exact Host/API/store closure.

All accounts, source callbacks and inference results are synthetic. Host owner
queue, ASGI app, dependency pins and encrypted SQLite storage are original code.
No vendor, credential, production database or live endpoint is used.
"""
import asyncio
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from scripts import community_ocr_host as host
from scripts import community_license_inference as inference
from scripts.community_mini_merchant import MiniMerchant
from test_community_ocr_bridge import load_pinned


class DurableFailure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dependency, cls.api = load_pinned()

    @classmethod
    def tearDownClass(cls):
        cls.dependency.cleanup()

    @contextlib.contextmanager
    def fixture(self, mode='infer'):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            key = Fernet.generate_key()
            path = str(Path(directory) / 'synthetic.sqlite')
            store = self.api.SecureSQLiteJobStore(path, key)
            raw = b'\x89PNG\r\n\x1a\nSYNTHETIC_ONLY'
            source = dict(subject='PRIVATE_OWNER', tenant_id='community-applicant:PRIVATE_OWNER',
                onboarding_application_id='PRIVATE_APP', application_revision=2, wechat_version=1,
                attachment_id='PRIVATE_ATTACHMENT', document_sha256=hashlib.sha256(raw).hexdigest(),
                document_type='business_license', data=raw, mime='image/png')
            merchant = MiniMerchant.__new__(MiniMerchant)
            merchant.identity = types.SimpleNamespace(applicant_context=lambda token:
                (calls.append('auth'), ('PRIVATE_OWNER' if token == 'PRIVATE_TOKEN' else 'OTHER_OWNER', 'PRIVATE_CSRF'))[1])
            merchant.onboarding = types.SimpleNamespace(wechat_applyment=None,
                _load=lambda *args: (calls.append('authorize'), ('PRIVATE_OWNER', {}, dict(status='DRAFT', revision=2)))[1])
            merchant.ocr_source = lambda *a, **kw: (calls.append('source'), dict(source))[1]
            update = store.update
            def updated(job_id, **changes):
                calls.append('update:' + changes['status'])
                if mode == 'save_both' or mode == 'save_before' and changes['status'] == 'needs_review':
                    raise RuntimeError('PRIVATE_SAVE_ERROR')
                result = update(job_id, **changes)
                if mode == 'save_after' and changes['status'] == 'needs_review':
                    raise RuntimeError('PRIVATE_AFTER_COMMIT')
                return result
            store.update = updated
            def infer(*args, **kwargs):
                calls.append('infer')
                if mode == 'infer':
                    raise RuntimeError('PRIVATE_PROVIDER_ERROR')
                if mode == 'process_missing':
                    return {'provider': 'synthetic'}
                if mode == 'process_type':
                    return None
                return {'fields': {'company_name': {'value': 'SYNTHETIC_ONLY'}}}
            with patch.object(inference, 'run_license_layout_ocr', infer):
                service = host.HostOcr(merchant, '', self.api, store, applicant_mode=True)
            requests = []
            actual = service.app
            async def app(scope, receive, send):
                requests.append(scope['path'])
                await actual(scope, receive, send)
            service.app = app
            fx = types.SimpleNamespace(service=service, store=store, source=source, merchant=merchant,
                calls=calls, requests=requests, path=path, key=key)
            try:
                yield fx
            finally:
                service.close()

    def submit(self, fx):
        return fx.service.dispatch('PRIVATE_TOKEN', '', dict(action='submit', application='PRIVATE_APP',
            document_type='business_license', idempotency_key='SYNTHETIC_FIXED_KEY_001'))['result']

    def read(self, fx, job_id, token='PRIVATE_TOKEN'):
        return fx.service.dispatch(token, '', dict(action='read', application='PRIVATE_APP', job_id=job_id))['result']

    def test_all_failure_phases_are_durable_sanitized_and_same_id(self):
        for mode, phase in [('infer','INFERENCE_FAILED'), ('process_missing','RESULT_PROCESSING_FAILED'),
                            ('process_type','RESULT_PROCESSING_FAILED'), ('save_before','RESULT_PERSISTENCE_FAILED'),
                            ('save_after','RESULT_PERSISTENCE_FAILED')]:
            with self.subTest(mode=mode), self.fixture(mode) as fx, self.assertLogs(host._LOG, 'WARNING') as logs:
                first = self.submit(fx)
                diagnostic = first['ocr_diagnostic']
                self.assertEqual(set(diagnostic), {'version','diagnostic_id','stage','reason','retryable','request_retained'})
                self.assertEqual((diagnostic['stage'], diagnostic['reason']), ('EXECUTION',phase))
                self.assertIs(diagnostic['retryable'],False)
                self.assertIs(diagnostic['request_retained'],True)
                self.assertRegex(diagnostic['diagnostic_id'], '^[0-9a-f]{32}$')
                self.assertEqual(self.read(fx,first['job_id'])['ocr_diagnostic'],diagnostic)
                self.assertEqual(self.read(fx,first['job_id'])['ocr_diagnostic'],diagnostic)
                stored = fx.store.get(first['job_id'],fx.source['tenant_id'])
                self.assertEqual(stored['status'],'failed')
                self.assertEqual(stored['error_code'],'OCR_INFERENCE_FAILED')
                self.assertEqual(stored['warnings'],['OCR_INFERENCE_FAILED'])
                reopened = self.api.SecureSQLiteJobStore(fx.path,fx.key)
                self.assertEqual(reopened.get(first['job_id'],fx.source['tenant_id'])['ocr_diagnostic'],diagnostic)
                self.assertNotIn(diagnostic['diagnostic_id'].encode(),Path(fx.path).read_bytes())
                self.assertEqual(fx.calls.count('infer'),1)
                self.assertEqual(len(fx.requests),3)
                self.assertIsNone(host.current_diagnostic())
            self.assertNotIn('PRIVATE_',repr(logs.output))
            self.assertTrue(any(phase in row and diagnostic['diagnostic_id'] in row for row in logs.output))

    def test_failed_job_write_failure_keeps_live_error_and_cannot_claim_durability(self):
        with self.fixture('save_both') as fx:
            with self.assertRaisesRegex(RuntimeError,'PRIVATE_SAVE_ERROR') as raised:
                self.submit(fx)
            diagnostic = host.safe_failure_diagnostic(raised.exception.ocr_diagnostic)
            self.assertEqual(diagnostic['reason'],'RESULT_PERSISTENCE_FAILED')
            self.assertEqual(fx.calls.count('infer'),1)
            with fx.store._connect() as db:
                job_id=db.execute('SELECT job_id FROM ocr_jobs').fetchone()[0]
            stored=fx.store.get(job_id,fx.source['tenant_id'])
            self.assertEqual(stored['status'],'processing')
            self.assertNotIn('ocr_diagnostic',stored)

    def test_success_and_legacy_rows_do_not_gain_diagnostic(self):
        with self.fixture('success') as fx:
            first=self.submit(fx)
            self.assertNotIn('ocr_diagnostic',first)
            self.assertNotIn('ocr_diagnostic',self.read(fx,first['job_id']))
            self.assertEqual(fx.calls.count('infer'),1)
        with self.fixture() as fx:
            first=self.submit(fx)
            fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:(row.pop('ocr_diagnostic'),row)[1])
            self.assertNotIn('ocr_diagnostic',self.read(fx,first['job_id']))
            self.assertEqual(fx.calls.count('infer'),1)

    def test_unauthorized_read_cannot_release_historical_id(self):
        for mutation in ('owner','attachment'):
            with self.subTest(mutation=mutation),self.fixture() as fx:
                first=self.submit(fx)
                if mutation=='attachment':fx.source['attachment_id']='CHANGED'
                with self.assertRaises(PermissionError) as raised:
                    self.read(fx,first['job_id'],'OTHER_TOKEN' if mutation=='owner' else 'PRIVATE_TOKEN')
                self.assertNotEqual(raised.exception.ocr_diagnostic['diagnostic_id'],first['ocr_diagnostic']['diagnostic_id'])
                self.assertEqual(fx.calls.count('infer'),1)

    def test_only_valid_failed_metadata_is_public(self):
        with self.fixture() as fx:
            first=self.submit(fx);valid=first['ocr_diagnostic']
            invalid=[None,{},dict(valid,diagnostic_id='PRIVATE_SECRET'),dict(valid,stage='ADMISSION'),
                dict(valid,reason='PRIVATE_PROVIDER_ERROR'),dict(valid,retryable=True),dict(valid,request_retained=False),
                dict(valid,reason=[]),dict(valid,stage={})]
            for value in invalid:
                with self.subTest(value=value):
                    fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:(row.update(ocr_diagnostic=value),row)[1])
                    self.assertNotIn('ocr_diagnostic',self.read(fx,first['job_id']))
            fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:(row.update(ocr_diagnostic=dict(valid,raw='PRIVATE_SECRET')),row)[1])
            self.assertEqual(self.read(fx,first['job_id'])['ocr_diagnostic'],valid)
            fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:(row.update(status='needs_review'),row)[1])
            self.assertNotIn('ocr_diagnostic',self.read(fx,first['job_id']))

    def recovery_case(self, locator_kind, mutation):
        with self.fixture() as fx:
            first=self.submit(fx)
            original=fx.store.get(first['job_id'],fx.source['tenant_id'])
            if mutation=='legacy':
                fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:(row.pop('ocr_diagnostic'),row)[1])
                original=fx.store.get(first['job_id'],fx.source['tenant_id'])
            locator={'job_id':first['job_id']} if locator_kind=='job' else {'original_key':'SYNTHETIC_FIXED_KEY_001'} if locator_kind=='key' else {'current_material':True}
            params=dict(action='recover_view',application='PRIVATE_APP',document_type='business_license',locator=locator,recovery_key='SYNTHETIC_RECOVERY_KEY_001')
            actual=fx.service.app;contexts=[];expected_original=[original]
            async def app(scope,receive,send):
                await actual(scope,receive,send)
                contexts.append(host.current_diagnostic())
                for name,value in {'attachment':('attachment_id','CHANGED'),'digest':('document_sha256','0'*64),
                    'revision':('application_revision',3),'provider':('wechat_version',3),
                    'provider_type':('wechat_version',True),'provider_float':('wechat_version',1.0)}.items():
                    if mutation==name:fx.source[value[0]]=value[1]
                if mutation=='session':fx.merchant.identity.applicant_context=lambda *a:(_ for _ in ()).throw(PermissionError('AUTHENTICATION_FAILED'))
                if mutation=='authorization':fx.merchant.onboarding._load=lambda *a:('PRIVATE_OWNER',{},dict(status='SUBMITTED',revision=2))
                if mutation=='source_error':fx.merchant.ocr_source=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('PRIVATE'))
                if mutation=='lookup_error':fx.store.resolve_material_recovery_job=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('PRIVATE'))
                if mutation=='different_job':fx.store.resolve_material_recovery_job=lambda *a,**kw:{'job_id':'different'}
                if mutation=='ambiguous':
                    clone=dict(original,job_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
                    with fx.store._connect() as db:
                        row=db.execute('SELECT * FROM ocr_jobs WHERE job_id=?',(original['job_id'],)).fetchone()
                        cols=list(row.keys());values=[row[k] for k in cols]
                        values[cols.index('job_id')]=clone['job_id']
                        values[cols.index('idem_key')]=fx.store._index(fx.source['tenant_id']+'/synthetic-other-key')
                        values[cols.index('ciphertext')]=fx.store._seal(clone)
                        db.execute('INSERT INTO ocr_jobs ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',values)
                if mutation=='deleted_job':
                    fx.store.delete(first['job_id'],fx.source['tenant_id'])
                    expected_original[0]=None
                if mutation=='job_status':
                    fx.store.update(first['job_id'],status='processing')
                    expected_original[0]=fx.store.get(first['job_id'],fx.source['tenant_id'])
                if mutation=='job_diagnostic':
                    fx.store._modify(first['job_id'],fx.source['tenant_id'],lambda row:
                        (row.update(ocr_diagnostic=dict(first['ocr_diagnostic'],diagnostic_id='a'*32)),row)[1])
                    expected_original[0]=fx.store.get(first['job_id'],fx.source['tenant_id'])
                if mutation=='job_lookup_error':
                    fx.store.resolve_recovery_job=lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('PRIVATE'))
                if mutation=='inflight':await asyncio.sleep(.08)
            fx.service.app=app
            if mutation=='inflight':fx.service.owner.timeout=.03
            with self.assertRaises(PermissionError) as raised:
                fx.service.dispatch('PRIVATE_TOKEN','',params)
            if str(raised.exception)=='OCR_REQUEST_PENDING':
                self.assertEqual(mutation,'inflight');time.sleep(.1)
                with self.assertRaises(PermissionError) as raised:
                    fx.service.dispatch('PRIVATE_TOKEN','',params)
            diagnostic=raised.exception.ocr_diagnostic
            retained=diagnostic['diagnostic_id']==first['ocr_diagnostic']['diagnostic_id']
            self.assertEqual(retained,mutation in ('none','inflight'))
            if mutation not in ('session','authorization'):
                self.assertEqual(str(raised.exception),'OCR_RECOVERY_RESULT_NOT_READY')
            self.assertEqual(fx.store.get(first['job_id'],fx.source['tenant_id']),expected_original[0])
            self.assertEqual(fx.calls.count('infer'),1)
            self.assertEqual(len(fx.requests),2)
            self.assertTrue(all(c.recovery_failure is None for c in contexts))
            self.assertIsNone(host.current_diagnostic())

    def test_recovery_rechecks_all_original_boundaries_and_original_inflight(self):
        cases=[(locator,mutation) for locator in ('job','key','material') for mutation in
            ('none','attachment','digest','revision','provider','provider_type','provider_float',
             'session','authorization','source_error','inflight','legacy','deleted_job','job_status','job_diagnostic','job_lookup_error')]
        cases += [('material',mutation) for mutation in ('lookup_error','ambiguous','different_job')]
        for locator,mutation in cases:
            with self.subTest(locator=locator,mutation=mutation):self.recovery_case(locator,mutation)

    def test_patch_reconstructs_exact_api_and_store_from_pinned_original(self):
        import os
        lock=json.loads(Path('scripts/community_ocr_dependency.json').read_text())
        source=os.environ.get('COMMUNITY_TEST_PINNED_OCR_DIR')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=root/'services/ocr_engine';target.mkdir(parents=True)
            for name,digest in lock['upstream_files'].items():
                raw=(Path(source)/name).read_bytes() if source else subprocess.check_output(['git','show',lock['source_sha']+':services/ocr_engine/'+name])
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
                (target/name).write_bytes(raw)
            patch_path=Path(lock['local_successor']['patch_path']).resolve()
            self.assertEqual(hashlib.sha256(patch_path.read_bytes()).hexdigest(),lock['local_successor']['patch_sha256'])
            subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(patch_path)],cwd=root,check=True,capture_output=True)
            for name,digest in lock['files'].items():self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(inference.BANK_CARD_RUNTIME_FILES,lock['files'])
            self.assertEqual(inference.UPSTREAM_FILES,lock['upstream_files'])

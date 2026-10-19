"""Original exception and conservative transaction diagnostics; no file cleanup."""
import json
import unittest
from unittest.mock import patch
import test_community_merchant_onboarding as fixtures

class ConnectionFailure:
    def __init__(self,db,*,rollback_error=None,commit_mode=None):
        self.db=db;self.rollback_error=rollback_error;self.commit_mode=commit_mode
    def __getattr__(self,name):return getattr(self.db,name)
    def rollback(self):
        if self.rollback_error:raise self.rollback_error
        return self.db.rollback()
    def commit(self):
        if self.commit_mode=='after':self.db.commit()
        if self.commit_mode in ('before','after'):raise OSError('synthetic commit uncertainty')
        return self.db.commit()

class OnboardingFailureDiagnostics(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.MerchantAdmissionJourney();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.c=self.f.fx.center;self.db=self.c.db
    def files(self):return {p.name:p.read_bytes() for p in self.c.objects.iterdir()}
    def diagnostics(self,error):
        value=error.onboarding_failure
        self.assertEqual(set(value),{'database','commit_attempted','rollback','object_write','filesystem_cleanup'})
        self.assertEqual(value['filesystem_cleanup'],'NOT_ATTEMPTED')
        # Only fixed enums/booleans, never source error text, IDs, paths or materials.
        self.assertNotIn('synthetic',json.dumps(value));self.assertNotIn('o_',json.dumps(value))
        return value
    def test_rollback_failure_cannot_replace_original_upload_error(self):
        app=self.f.draft();primary=OSError('synthetic primary audit failure')
        self.c.db=ConnectionFailure(self.db,rollback_error=RuntimeError('synthetic rollback failure'))
        try:
            with patch.object(self.c,'audit',side_effect=primary):
                with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
            self.assertIs(raised.exception,primary)
            info=self.diagnostics(primary);self.assertEqual(info['database'],'UNKNOWN');self.assertEqual(info['rollback'],'FAILED')
            self.assertEqual(info['object_write'],'RETURNED');self.assertEqual(len(self.files()),1)
        finally:self.c.db=self.db;self.db.rollback()
    def test_precommit_audit_failure_retains_encrypted_object_and_confirms_only_database_rollback(self):
        app=self.f.draft();primary=OSError('synthetic private audit detail')
        with patch.object(self.c,'audit',side_effect=primary):
            with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
        self.assertIs(raised.exception,primary);info=self.diagnostics(primary)
        self.assertEqual(info,dict(database='ROLLED_BACK_BEFORE_COMMIT',commit_attempted=False,rollback='COMPLETED',object_write='RETURNED',filesystem_cleanup='NOT_ATTEMPTED'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM objects').fetchone()[0],0)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['revision'],app['revision'])
        self.assertEqual(len(self.files()),1)
        self.assertNotIn(b'fixture private',next(iter(self.files().values())))
    def commit_failure(self,mode):
        app=self.f.draft();self.c.db=ConnectionFailure(self.db,commit_mode=mode)
        try:
            with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
            info=self.diagnostics(raised.exception)
            self.assertEqual(info['database'],'UNKNOWN');self.assertTrue(info['commit_attempted'])
            self.assertEqual(info['object_write'],'RETURNED');self.assertEqual(len(self.files()),1)
            self.assertEqual(self.db.execute('SELECT count(*) FROM objects').fetchone()[0],int(mode=='after'))
            self.assertEqual(info['rollback'],'UNCONFIRMED' if mode=='after' else 'COMPLETED')
        finally:self.c.db=self.db;self.db.rollback()
    def test_commit_before_effect_error_remains_unknown_and_preserves_file(self):self.commit_failure('before')
    def test_commit_after_effect_error_remains_unknown_and_preserves_referenced_file(self):self.commit_failure('after')
    def test_history_failure_does_not_delete_new_or_previous_objects(self):
        app=self.f.upload(self.f.draft(),'business_license');before=self.files();primary=ValueError('synthetic history failure')
        with patch('scripts.community_onboarding_history.append',side_effect=primary):
            with self.assertRaises(ValueError) as raised:self.f.upload(app,'business_license',b'%PDF-fixture replacement')
        self.assertIs(raised.exception,primary);self.assertEqual(self.diagnostics(primary)['database'],'ROLLED_BACK_BEFORE_COMMIT')
        after=self.files();self.assertEqual(len(after),len(before)+1)
        for name,value in before.items():self.assertEqual(after[name],value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM objects').fetchone()[0],1)
    def test_partial_write_failure_is_not_reported_as_complete_or_deleted(self):
        from scripts.community_merchant_onboarding import secure_write
        app=self.f.draft();primary=OSError('synthetic incomplete file write')
        def fail(path,raw):secure_write(path,raw[:23]);raise primary
        with patch('scripts.community_merchant_onboarding.secure_write',side_effect=fail):
            with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
        self.assertIs(raised.exception,primary);self.assertEqual(self.diagnostics(primary)['object_write'],'ATTEMPTED')
        self.assertEqual([len(raw) for raw in self.files().values()],[23])
    def test_object_name_collision_preserves_preexisting_file(self):
        app=self.f.draft();name='o_'+'a'*32
        (self.c.objects/name).write_bytes(b'preexisting synthetic object');before=self.files()
        with patch('scripts.community_merchant_onboarding.secrets.token_hex',return_value='a'*32):
            with self.assertRaises(FileExistsError) as raised:self.f.upload(app,'business_license')
        info=self.diagnostics(raised.exception);self.assertEqual(info['object_write'],'ATTEMPTED');self.assertEqual(self.files(),before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM objects').fetchone()[0],0)
    def test_scan_failure_never_claims_file_creation(self):
        app=self.f.draft();self.c.scanner=lambda raw:False
        with self.assertRaises(PermissionError) as raised:self.f.upload(app,'business_license')
        self.assertEqual(self.diagnostics(raised.exception)['object_write'],'NOT_STARTED');self.assertEqual(self.files(),{})
    def test_diagnostic_sink_failure_does_not_replace_original_error(self):
        class NoteFailure(OSError):
            def add_note(self,note):raise RuntimeError('synthetic diagnostic failure')
        app=self.f.draft();primary=NoteFailure('synthetic original error')
        with patch.object(self.c,'audit',side_effect=primary):
            with self.assertRaises(NoteFailure) as raised:self.f.upload(app,'business_license')
        self.assertIs(raised.exception,primary);self.assertEqual(len(self.files()),1)
    def test_rollback_that_leaves_transaction_open_is_not_confirmed(self):
        app=self.f.draft();primary=OSError('synthetic original error')
        proxy=ConnectionFailure(self.db);proxy.rollback=lambda:None;self.c.db=proxy
        try:
            with patch.object(self.c,'audit',side_effect=primary):
                with self.assertRaises(OSError):self.f.upload(app,'business_license')
            info=self.diagnostics(primary);self.assertEqual(info['rollback'],'UNCONFIRMED');self.assertEqual(info['database'],'UNKNOWN')
        finally:self.c.db=self.db;self.db.rollback()
    def test_postcommit_response_failure_does_not_delete_or_relabel_committed_file(self):
        app=self.f.draft();primary=OSError('synthetic view failure')
        with patch.object(self.f.service,'_view',side_effect=primary):
            with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
        self.assertIs(raised.exception,primary);self.assertFalse(hasattr(primary,'onboarding_failure'))
        self.assertEqual(len(self.files()),1);self.assertEqual(self.db.execute('SELECT count(*) FROM objects').fetchone()[0],1)
        self.assertEqual(self.f.call('read',dict(application=app['application']))['revision'],app['revision']+1)
    def test_external_replacement_during_failure_is_preserved_without_unlink(self):
        app=self.f.draft();primary=OSError('synthetic downstream failure')
        def replaced(*args):
            name=next(self.c.objects.iterdir());name.rename(name.with_suffix('.retained'))
            name.write_bytes(b'unrelated synthetic replacement')
            raise primary
        with patch('scripts.community_onboarding_history.append',side_effect=replaced),patch('os.unlink',side_effect=AssertionError('NO_PATH_DELETION')):
            with self.assertRaises(OSError) as raised:self.f.upload(app,'business_license')
        self.assertIs(raised.exception,primary);self.assertEqual(self.diagnostics(primary)['filesystem_cleanup'],'NOT_ATTEMPTED')
        self.assertEqual(len(self.files()),2);self.assertIn(b'unrelated synthetic replacement',self.files().values())

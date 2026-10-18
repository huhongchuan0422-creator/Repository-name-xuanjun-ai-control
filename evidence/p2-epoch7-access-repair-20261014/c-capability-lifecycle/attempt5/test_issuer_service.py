"""Real service/SQLite/signature coupling; host facts explicitly synthetic."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE/'runtime'),str(HERE/'original'),str(HERE)]
from authority_store import AuthorityStore
from issuer_service import IssuerService
from receipt_provider import ReceiptProvider,Hold,digest
from test_authority_store import grant
import test_receipt_provider as provider_fixtures

class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):provider_fixtures.ProviderTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();os.chmod(self.folder.name,0o700)
        self.store=AuthorityStore(str(Path(self.folder.name)/'issuer.db'),initialize=True,clock=lambda:100)
        self.g=grant();self.store.register(self.g)
        self.principal={'actor_id':self.g['actor_id'],'host':self.g['target_host'],'writer_id':'trusted-fixture-writer'}
        self.change=lambda result:None
        signer=lambda raw:subprocess.check_output(['openssl','dgst','-sha256','-sign',self.key],input=raw)
        self.service=IssuerService(self.store,self.host,signer,'TEST_ONLY')
        self.provider=ReceiptProvider(lambda request:self.service.handle(request,self.principal),
                                      self.modulus,65537,'TEST_ONLY',clock=lambda:101)
    def tearDown(self):self.store.close();self.folder.cleanup()
    def host(self,g,aid,op,payload):
        result={'status':'AUTHORIZED','policy':'P2_ATTEMPT5_V1'}
        receipt={'grant_sha256':digest(g),'attempt_id':aid,'operation':op,'payload_sha256':digest(payload),
                 'run_id':'TEST_RUN','job_id':'TEST_JOB','invoke_id':'TEST_INVOKE',
                 'backup_sha256':'a'*64,'checkpoint_sha256':'b'*64,'log_sha256':'c'*64,'result':result}
        self.change(receipt);return receipt
    def consume(self):return self.provider.request(self.g,'attempt1','consume_attempt',
                {'ordinal':1,'command_sha256':'a'*64,'ledger_sha256':'b'*64})
    def test_real_service_signed_consumption(self):
        self.assertEqual(self.consume()['status'],'CONSUMED')
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_rpc_retry_idempotent_consumption(self):
        self.consume();self.consume()
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],1)
    def test_wrong_authenticated_principal_refused(self):
        self.principal['host']='OTHER'
        with self.assertRaises(Hold):self.consume()
        self.assertEqual(self.store.db.execute('SELECT consumed FROM grants').fetchone()[0],0)
    def test_missing_real_transaction_ids_refused(self):
        self.consume();self.change=lambda receipt:receipt.update(invoke_id='')
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','authorize_first_admission')
    def test_wrong_host_readback_binding_refused(self):
        self.consume();self.change=lambda receipt:receipt.update(payload_sha256='f'*64)
        with self.assertRaises(Hold):self.provider.request(self.g,'attempt1','authorize_first_admission')
    def test_no_unsigned_or_unclaimed_admission(self):
        with self.assertRaises(Hold):self.provider.request(self.g,'not_consumed','authorize_first_admission')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0],0)
if __name__=='__main__':unittest.main()

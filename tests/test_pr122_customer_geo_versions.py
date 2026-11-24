"""Only the new canonical-version delta, reusing original synthetic fixtures."""
import json
import unittest
from tests import test_pr122_customer_geo as base
from tests import pr122_customer_change_fixture as source
from scripts.pr122_customer_core import canonical,digest,Denied,Unavailable
from scripts.pr122_customer_change_authority import import_snapshot
from scripts.pr122_customer_geo import import_authority

class VersionTests(unittest.TestCase):
 imported=base.GeoTests.imported
 grant=base.GeoTests.grant
 admit=base.GeoTests.admit
 factory=base.GeoTests.factory
 wire=base.GeoTests.wire
 def setUp(self):
  base.GeoTests.setUp(self)
  self.document_id='synthetic-geo-accepted-version'
 def seed(self,kind='ACCEPTED_VERSION',revision=1,documents=None):
  return source.seed(self,revision=revision,documents=documents if documents is not None else [source.doc(self,kind=kind,document_id=self.document_id)])
 def version(self):return self.c.geo.snapshot(self.owner,self.scope)['versions']
 def test_exact_signed_binding_required_not_newest_document_heuristic(self):
  self.seed();self.admit()
  self.assertEqual(self.version()['reason'],'VERSION_DOCUMENT_BINDING_REQUIRED')
  self.assertFalse(self.c.geo.snapshot(self.owner,self.scope)['actions']['APPROVE_VERSION'])
 def test_original_import_factory_http_snapshot_hit_without_new_ledger(self):
  self.seed();self.admit(version_document_id=self.document_id)
  before=self.c.db.execute('SELECT count(*) FROM change_authority_history').fetchone()[0]
  status,result=self.wire('geo/snapshot',self.scope)
  self.assertEqual(status,200);v=result['versions'];self.assertEqual(v['status'],'READY')
  self.assertEqual(v['current_version'],1);self.assertEqual(v['confirmation_state'],'APPROVED')
  self.assertEqual(v['source']['document_id'],self.document_id);self.assertEqual(v['source']['authority_revision'],1)
  self.assertEqual(v['publication_status'],'UNKNOWN');self.assertEqual(v['comments_status'],'NOT_CONNECTED')
  self.assertNotIn('text',v);self.assertNotIn('confirmed_by',v);self.assertNotIn('https://contracts.',json.dumps(v))
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM change_authority_history').fetchone()[0],before)
  self.assertFalse(result['actions']['APPROVE_VERSION'])
  with self.assertRaises(Unavailable):self.c.geo.command(self.owner,{**self.cmd,'type':'APPROVE_VERSION'})
  self.e2e_snapshot=result
 def test_client_and_unsigned_binding_cannot_choose_version_source(self):
  self.seed();grant=self.grant();grant['payload']['version_document_id']=self.document_id
  with self.assertRaises(Denied):import_authority(self.c,grant,self.auth)
  self.admit(version_document_id=self.document_id)
  self.assertEqual(self.wire('geo/snapshot',{**self.scope,'version_document_id':'attacker'})[0],400)
 def test_source_removal_does_not_reuse_history_or_other_document(self):
  self.seed();self.admit(version_document_id=self.document_id);self.assertEqual(self.version()['status'],'READY')
  self.seed(revision=2,documents=[source.doc(self,kind='ACCEPTED_VERSION',document_id='different-document')])
  self.assertEqual(self.version()['reason'],'BOUND_VERSION_DOCUMENT_NOT_IN_CURRENT_SOURCE')
 def test_absent_source_blocks_only_version_not_brand_or_entitlement(self):
  self.admit(version_document_id=self.document_id)
  self.assertEqual(self.version()['reason'],'CHANGE_AUTHORITY_NOT_CONNECTED')
  self.assertEqual(self.c.geo.command(self.owner,self.cmd)['state'],'SUCCEEDED')
 def test_expired_source_blocks_only_version(self):
  envelope=source.snapshot(self,documents=[source.doc(self,kind='ACCEPTED_VERSION',document_id=self.document_id)])
  envelope['payload']['expires']=self.now+10
  import hashlib,hmac
  envelope['signature']=hmac.new(self.auth,canonical(envelope['payload']),hashlib.sha256).hexdigest()
  import_snapshot(self.c,envelope,self.auth);self.admit(version_document_id=self.document_id);self.now+=11
  snap=self.c.geo.snapshot(self.owner,self.scope);self.assertEqual(snap['versions']['reason'],'CHANGE_AUTHORITY_EXPIRED')
  self.assertTrue(snap['entitlement']['enabled']);self.assertEqual(self.c.geo.command(self.owner,self.cmd)['state'],'SUCCEEDED')
 def test_current_project_revision_and_accepted_kind_rechecked(self):
  self.seed(kind='CONTRACT');self.admit(version_document_id=self.document_id)
  with self.assertRaisesRegex(Denied,'GEO_ACCEPTED_VERSION_REQUIRED'):self.version()
  self.seed(revision=2);self.assertEqual(self.version()['status'],'READY')
  self.imported(2,[self.p])
  with self.assertRaisesRegex(Denied,'GEO_VERSION_SOURCE_BINDING'):self.version()
 def test_other_project_document_rejected_even_if_signed_and_explicitly_named(self):
  self.imported(2,[self.p,{**self.p,'id':'project-b','tenant':'tenant-b','customer':'customer-b','owner_email':'other@example.com'}])
  entry=source.doc(self,kind='ACCEPTED_VERSION',document_id=self.document_id)
  doc=json.loads(entry['document_utf8']);doc.update(project='project-b',confirmed_by=self.other)
  entry['document_utf8']=canonical(doc).decode();entry['document_sha256']=digest(entry['document_utf8'].encode())
  entry['version_sha256']=digest(canonical({'document_sha256':entry['document_sha256'],'version':1,'project':'project-b','contract_ref':'contract-a'}))
  self.seed(documents=[entry]);self.admit(version_document_id=self.document_id)
  with self.assertRaisesRegex(Denied,'GEO_VERSION_SOURCE_BINDING'):self.version()

if __name__=='__main__':unittest.main()

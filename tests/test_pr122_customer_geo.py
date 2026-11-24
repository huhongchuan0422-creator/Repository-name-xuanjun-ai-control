"""Synthetic original-Center fixture; no real users, grants, network or commands."""
import base64
import hashlib
import hmac
import io
import json
import os
import sqlite3
import unittest
from unittest.mock import patch
from tests import test_pr122_customer_center as original
from scripts import pr122_customer_geo as geo, pr122_customer_ops as ops, pr122_customer_http as http
from scripts.pr122_customer_core import Center, Denied, Conflict, Unavailable, canonical
CONNECT=sqlite3.connect

class Wire:
 def __init__(self,data):self.input=io.BytesIO(data);self.output=io.BytesIO()
 def makefile(self,*args,**kwargs):return self.input
 def sendall(self,body):self.output.write(body)
 def settimeout(self,t):pass

class GeoTests(unittest.TestCase):
 imported=original.CustomerTests.imported
 def setUp(self):
  self.addCleanup(patch.stopall)
  # Existing Python3.6 host needs only pathlib->fspath sqlite compatibility.
  patch('sqlite3.connect',side_effect=lambda p,*a,**kw:CONNECT(os.fspath(p),*a,**kw)).start()
  original.CustomerTests.setUp(self)
  geo.install(self.c)
  self.scope={'project_id':'project-a','tenant_id':'tenant-a','customer_id':'customer-a'}
  self.cmd={'type':'SAVE_BRAND','project_id':'project-a','tenant_id':'tenant-a','idempotency_key':'synthetic-command-1','form':{'name':'合成品牌','website':'https://example.invalid'}}
 def grant(self,**changes):
  data={**self.scope,'revision':1,'enabled':True,'plan':'synthetic-only','valid_until':self.now+1800,'quota':10,'remaining':10,'source_ref':'synthetic-order-1',**changes}
  return {'payload':data,'signature':hmac.new(self.auth,canonical(data),hashlib.sha256).hexdigest()}
 def admit(self,**changes):return geo.import_authority(self.c,self.grant(**changes),self.auth)
 def factory(self):
  config={'keys':{'v1':base64.b64encode(self.key).decode()},'active_key':'v1','providers':{}}
  with patch.object(ops,'ROOT',self.root),patch.object(ops,'Center',side_effect=lambda *a,**kw:Center(*a,clock=lambda:self.now,**kw)):
   return ops.factory(config)
 def wire(self,operation,body,csrf=True,token=True,origin=True,method='POST',profile='FULL'):
  raw=canonical(body);headers=['Host: wenwenwenyiyiyi.work','Content-Type: application/json','Content-Length: '+str(len(raw))]
  if origin:headers.append('Origin: https://wenwenwenyiyiyi.work')
  if token:headers.append('Cookie: '+http.COOKIE+'='+self.users['owner']['token'])
  if csrf:headers.append('X-CSRF-Token: '+self.users['owner']['csrf'])
  wire=Wire((method+' /customer/center/api/'+operation+' HTTP/1.1'+chr(13)+chr(10)+(chr(13)+chr(10)).join(headers)+chr(13)+chr(10)+chr(13)+chr(10)).encode()+raw)
  kw={} if profile=='FULL' else {'deployment_profile':profile}
  http.App(self.factory,ops.Providers({}),'https://wenwenwenyiyiyi.work','.',**kw).handler()(wire,('synthetic',0),object())
  head,body=wire.output.getvalue().split(bytes([13,10,13,10]),1)
  return int(head.split(b' ')[1]),json.loads(body) if body else None
 def test_no_grant_does_not_invent_entitlement_or_domain_facts(self):
  snap=self.c.geo.snapshot(self.owner,self.scope)
  self.assertFalse(snap['entitlement']['enabled']);self.assertFalse(any(snap['actions'].values()))
  self.assertEqual(snap['diagnosis'],{'status':'NOT_CONNECTED'});self.assertNotIn('brand',snap)
  with self.assertRaises(Denied):self.c.geo.command(self.owner,self.cmd)
 def test_signed_grant_scope_replay_and_expiry(self):
  bad=self.grant();bad['signature']='0'*64
  with self.assertRaises(Denied):geo.import_authority(self.c,bad,self.auth)
  with self.assertRaises(Denied):self.admit(customer_id='wrong-customer')
  with self.assertRaises(Denied):self.admit(valid_until=self.now)
  with self.assertRaises(ValueError):self.admit(remaining=11)
  self.admit()
  with self.assertRaises(Conflict):self.admit()
  snap=self.c.geo.snapshot(self.owner,self.scope)
  self.assertEqual([k for k,v in snap['actions'].items() if v],['SAVE_BRAND'])
  self.assertEqual(snap['usage']['source'],'synthetic-order-1');self.assertEqual(snap['usage']['used'],0)
 def test_local_command_persisted_and_idempotent_readback(self):
  self.admit();a=self.c.geo.command(self.owner,self.cmd);b=self.c.geo.command(self.owner,self.cmd)
  self.assertEqual(a,b);self.assertEqual(a['revision'],1)
  c=self.factory()
  try:self.assertEqual(c.geo.snapshot(self.owner,self.scope)['brand']['name'],'合成品牌')
  finally:c.db.close()
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM geo_commands').fetchone()[0],1)
  raw=(self.root/'center.sqlite').read_bytes()+(self.root/'center.sqlite-wal').read_bytes()
  self.assertNotIn('合成品牌'.encode(),raw);self.c.check_integrity()
 def test_same_key_changed_payload_conflicts(self):
  self.admit();self.c.geo.command(self.owner,self.cmd)
  with self.assertRaises(Conflict):self.c.geo.command(self.owner,{**self.cmd,'form':{'name':'different','website':''}})
  self.assertEqual(self.c.geo.snapshot(self.owner,self.scope)['brand']['revision'],1)
 def test_unknown_queries_without_retry_or_new_key(self):
  self.admit();digest=hashlib.sha256(canonical(self.cmd)).hexdigest()
  self.c.db.execute('INSERT INTO geo_commands VALUES(?,?,?,?,?,NULL)',('project-a',self.owner,self.cmd['idempotency_key'],digest,'UNKNOWN'))
  status,result=self.c.geo.handle(self.owner,'POST','geo/command',self.cmd)
  self.assertEqual(status,202);self.assertTrue(result['query_required'])
  self.assertEqual(self.c.geo.snapshot(self.owner,self.scope)['last_command']['state'],'UNKNOWN')
  with self.assertRaises(Conflict):self.c.geo.command(self.owner,{**self.cmd,'idempotency_key':'new-key'})
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM geo_brand').fetchone()[0],0)
 def test_tenant_customer_and_membership_not_client_assertions(self):
  self.admit()
  for body in ({**self.scope,'tenant_id':'tenant-b'},{**self.scope,'customer_id':'customer-b'}):
   with self.assertRaises(Denied):self.c.geo.snapshot(self.owner,body)
  with self.assertRaises(Denied):self.c.geo.snapshot(self.other,self.scope)
  with self.assertRaises(Denied):self.c.geo.command(self.owner,{**self.cmd,'tenant_id':'tenant-b'})
 def test_viewer_can_read_but_not_write(self):
  self.admit();self.c.db.execute("INSERT INTO members VALUES('project-a',?,'VIEWER',1)",(self.member,))
  self.assertFalse(self.c.geo.snapshot(self.member,self.scope)['actions']['SAVE_BRAND'])
  with self.assertRaises(Denied):self.c.geo.command(self.member,self.cmd)
 def test_revocation_and_expiry_checked_before_replay(self):
  self.admit();self.c.geo.command(self.owner,self.cmd);self.admit(revision=2,enabled=False)
  with self.assertRaises(Denied):self.c.geo.command(self.owner,self.cmd)
  self.admit(revision=3);self.now+=1801
  with self.assertRaises(Denied):self.c.geo.command(self.owner,self.cmd)
 def test_project_revocation_and_expiry_override_entitlement(self):
  self.admit();self.c.db.execute("UPDATE members SET active=0 WHERE user_id=?",(self.owner,))
  with self.assertRaises(Denied):self.c.geo.snapshot(self.owner,self.scope)
  self.c.db.execute("UPDATE members SET active=1 WHERE user_id=?",(self.owner,));self.now+=3601
  with self.assertRaises(Denied):self.c.geo.snapshot(self.owner,self.scope)
 def test_external_actions_do_not_create_fake_work(self):
  self.admit()
  for action in geo.ACTIONS:
   if action!='SAVE_BRAND':
    with self.assertRaises(Unavailable):self.c.geo.command(self.owner,{**self.cmd,'type':action})
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM geo_commands').fetchone()[0],0)
 def test_original_factory_full_handler_snapshot_command_and_readback(self):
  self.admit();status,snap=self.wire('geo/snapshot',self.scope);self.assertEqual(status,200);self.assertEqual(snap['tenant_id'],'tenant-a')
  status,res=self.wire('geo/command',self.cmd);self.assertEqual(status,200);self.assertEqual(res['state'],'SUCCEEDED')
  status,snap=self.wire('geo/snapshot',self.scope);self.assertEqual(snap['brand']['revision'],1)
 def test_original_handler_session_csrf_origin_and_login_only(self):
  self.admit()
  for kw in ({'csrf':False},{'token':False},{'origin':False},{'profile':'OFFICIAL_LOGIN_ONLY_V1'}):
   self.assertEqual(self.wire('geo/command',self.cmd,**kw)[0],403)
  self.assertEqual(self.wire('geo/snapshot',{},method='GET')[0],405)
  self.assertEqual(self.wire('geo/import-authority',self.grant())[0],404)
  status,me=self.wire('me',{},method='GET');self.assertEqual(status,200);self.assertEqual(me['projects'][0]['id'],'project-a')
 def test_strict_contract_and_atomic_audit_failure(self):
  self.admit()
  with self.assertRaises(ValueError):self.c.geo.snapshot(self.owner,{**self.scope,'entitlement':True})
  with self.assertRaises(ValueError):self.c.geo.command(self.owner,{k:v for k,v in self.cmd.items() if k!='idempotency_key'})
  with patch.object(self.c,'audit',side_effect=RuntimeError('synthetic-audit-failure')):
   with self.assertRaises(RuntimeError):self.c.geo.command(self.owner,self.cmd)
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM geo_brand').fetchone()[0],0)
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM geo_commands').fetchone()[0],0)

if __name__=='__main__':unittest.main()

import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from scripts.pr122_customer_core import Center,Denied,Conflict,Unavailable,canonical
from scripts.pr122_customer_ops import backup,restore
from scripts.pr122_customer_providers import Providers,drain_mail,enqueue,drain_message

class CustomerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'private';self.now=1792137000;self.key=b'k'*32;self.auth=b'a'*32
  self.c=Center(self.root,{'v1':self.key},'v1',clock=lambda:self.now,mail_ready=True,scanner=lambda raw:True)
  self.addCleanup(lambda:self.c.db.close());self.users={}
  for name in ('owner','reviewer','other','member'):
   addr=name+'@example.com';self.c.register(addr,'correct-password-123')
   r=self.c.db.execute('SELECT * FROM outbox ORDER BY rowid DESC LIMIT 1').fetchone();token=json.loads(self.c.decrypt(r['payload'],'outbox:'+r['id']))['token'];self.c.verify(token,'correct-password-123')
   self.users[name]=self.c.login(addr,'correct-password-123')
  self.q={'id':'license','title':'企业授权','purpose':'核实签约关系','required':True,'identity_requirements':'原签约代表','official_url':'https://www.gsxt.gov.cn/','instructions':'通过官方入口核实主体，再在项目私有入口提交证明。','minimum_permissions':'仅核验','fees':'UNKNOWN','verified_at':None,'formats':['application/pdf','image/png','image/jpeg'],'valid_until':None,'submission_type':'PRIVATE_DOCUMENT','category':'MATERIAL'}
  self.p={'id':'project-a','tenant':'tenant-a','customer':'customer-a','owner_email':'owner@example.com','contract_ref':'contract-a','order_ref':'order-a','verified_entity':True,'title':'社区分账项目','requirements':[dict(self.q),{**self.q,'id':'extra','title':'补充材料'}],'reviewer_emails':['reviewer@example.com']}
  self.imported(1,[self.p]);self.owner=self.users['owner']['user_id'];self.reviewer=self.users['reviewer']['user_id'];self.other=self.users['other']['user_id'];self.member=self.users['member']['user_id']
 def imported(self,revision,projects):
  p={'revision':revision,'expires':self.now+3600,'projects':projects};return self.c.import_authority({'payload':p,'signature':hmac.new(self.auth,canonical(p),hashlib.sha256).hexdigest()},self.auth)
 def save(self,item='license',rev=0):return self.c.save(self.owner,'project-a',item,rev,'DOCUMENT',b'%PDF-1.7\nfictional document\n%%EOF')
 def accept(self,item='license',rev=0):
  s=self.save(item,rev);r=self.c.transition(self.owner,'project-a',item,s['revision'],'submit');r=self.c.transition(self.reviewer,'project-a',item,r['revision'],'begin_review');return self.c.transition(self.reviewer,'project-a',item,r['revision'],'approve','checked supplied document')
 def test_authentication_session_csrf_logout(self):
  s=self.users['owner'];self.assertEqual(self.c.session(s['token'],s['csrf']),self.owner)
  with self.assertRaises(Denied):self.c.session(s['token'],'wrong')
  with self.assertRaises(Denied):self.c.login('owner@example.com','incorrect-password')
  self.c.logout(s['token'])
  with self.assertRaises(Denied):self.c.session(s['token'])
 def test_verification_reset_single_use_revoke_old_sessions(self):
  self.c.request_reset('owner@example.com');r=self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET'").fetchone();token=json.loads(self.c.decrypt(r['payload'],'outbox:'+r['id']))['token'];self.c.reset(token,'new-password-1234')
  with self.assertRaises(Denied):self.c.session(self.users['owner']['token'])
  with self.assertRaises(Denied):self.c.reset(token,'new-password-1234')
  self.assertTrue(self.c.login('owner@example.com','new-password-1234')['user_id'])
 def test_register_requires_real_config_and_never_returns_token(self):
  r=self.c.register('new@example.com','new-password-1234');self.assertEqual(set(r),{'status'})
  with self.assertRaises(Denied):self.c.login('new@example.com','new-password-1234')
  self.c.mail_ready=False
  with self.assertRaises(Unavailable):self.c.register('none@example.com','new-password-1234')
 def test_authority_signature_scope_replay_and_expiration(self):
  with self.assertRaises(Denied):self.c.import_authority({'payload':{},'signature':'f'*64},self.auth)
  with self.assertRaises(Conflict):self.imported(1,[self.p])
  with self.assertRaises(Denied):self.c.checklist(self.other,'project-a')
  self.now+=3601
  with self.assertRaises(Denied):self.c.checklist(self.owner,'project-a')
 def test_parallel_projects_no_cross_customer_access(self):
  p={**self.p,'id':'project-b','tenant':'tenant-b','customer':'customer-b','owner_email':'other@example.com'};self.imported(2,[self.p,p]);self.save()
  with self.assertRaises(Denied):self.c.checklist(self.owner,'project-b')
  oid=self.c.db.execute('SELECT id FROM objects').fetchone()[0]
  with self.assertRaises(Denied):self.c.download(self.other,'project-b',oid)
  with self.assertRaises(Denied):self.c.download(self.other,'project-a',oid)
 def test_versions_review_separation_and_incremental_preservation(self):
  r=self.accept();self.assertEqual(r['state'],'ACCEPTED');self.save('extra');old=r['accepted_revision'];self.save('license',r['revision']);d=self.c.checklist(self.owner,'project-a');self.assertEqual(d['items'][0]['accepted_revision'],old);self.assertEqual(len(d['items'][0]['versions']),5)
  with self.assertRaises(Conflict):self.save('license',r['revision'])
  r=self.c.transition(self.owner,'project-a','license',5,'submit')
  with self.assertRaises(Denied):self.c.transition(self.owner,'project-a','license',r['revision'],'begin_review')
  with self.assertRaises(Denied):self.c.save(self.reviewer,'project-a','extra',1,'DOCUMENT',b'%PDF-test')
 def test_correction_and_concurrent_review(self):
  s=self.save();r=self.c.transition(self.owner,'project-a','license',s['revision'],'submit');r=self.c.transition(self.reviewer,'project-a','license',r['revision'],'begin_review');r=self.c.transition(self.reviewer,'project-a','license',r['revision'],'request_changes','缺少授权签字');self.assertEqual(r['state'],'NEEDS_CORRECTION')
  with self.assertRaises(Conflict):self.c.transition(self.reviewer,'project-a','license',3,'approve','stale')
  r=self.save('license',r['revision']);self.assertEqual(r['state'],'PARTIAL')
 def test_member_invitation_bound_identity_revocation_every_access(self):
  token=self.c.invite(self.owner,'project-a','member@example.com','EDITOR')['invitation']
  with self.assertRaises(Denied):self.c.accept_invite(self.other,token)
  self.c.accept_invite(self.member,token)
  with self.assertRaises(Denied):self.c.accept_invite(self.member,token)
  self.c.checklist(self.member,'project-a');self.save();oid=self.c.db.execute('SELECT id FROM objects').fetchone()[0];self.c.download(self.member,'project-a',oid);self.c.revoke(self.owner,'project-a',self.member)
  self.c.session(self.users['member']['token']) # Account session does not restore revoked project rights.
  with self.assertRaises(Denied):self.c.download(self.member,'project-a',oid)
  with self.assertRaises(Denied):self.c.invite(self.owner,'project-a','reviewer@example.com','EDITOR')
 def test_private_internal_and_scan_unknown_never_download(self):
  internal={**self.q,'id':'internal','category':'INTERNAL'};self.imported(2,[{**self.p,'requirements':self.p['requirements']+[internal]}]);self.assertEqual(len(self.c.checklist(self.owner,'project-a')['items']),2)
  with self.assertRaises(Denied):self.c.save(self.owner,'project-a','internal',0,'DOCUMENT',b'%PDF-test')
  self.c.scanner=lambda b:None
  with self.assertRaises(Denied):self.save()
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM objects').fetchone()[0],0)
  self.c.scanner=None
  with self.assertRaises(Unavailable):self.save()
 def test_secretref_and_ordinary_secret_guard(self):
  with self.assertRaises(Denied):self.c.save(self.owner,'project-a','license',0,'DOCUMENT',b'%PDF-1.7\n-----BEGIN PRIVATE KEY-----')
  with self.assertRaises(Denied):self.c.save(self.owner,'project-a','license',0,'DOCUMENT',b'not allowed text')
  q={**self.q,'id':'secret','submission_type':'SECRETREF'};self.imported(2,[{**self.p,'requirements':[q]}])
  with self.assertRaises(Unavailable):self.c.save(self.owner,'project-a','secret',0,'SECRETREF','ref_safe')
  self.c.secretref=lambda *args:False
  with self.assertRaises(Denied):self.c.save(self.owner,'project-a','secret',0,'SECRETREF','ref_safe')
  self.c.secretref=lambda pid,item,kind,ref:pid=='project-a' and ref=='ref_safe';self.c.save(self.owner,'project-a','secret',0,'SECRETREF','ref_safe')
 def test_encryption_tamper_restart_and_audit(self):
  self.save();o=self.c.db.execute('SELECT * FROM objects').fetchone();raw=(self.c.objects/o['id']).read_bytes();self.assertNotIn(b'fictional document',raw);self.assertNotIn(b'owner@example.com',(self.root/'center.sqlite').read_bytes());self.c.check_integrity()
  c2=Center(self.root,{'v1':self.key},'v1',clock=lambda:self.now);self.addCleanup(c2.db.close);self.assertEqual(c2.download(self.owner,'project-a',o['id'])[1],'application/pdf')
  p=self.c.objects/o['id'];p.write_bytes(raw[:-5]+b'aaaaa')
  with self.assertRaises(Exception):self.c.download(self.owner,'project-a',o['id'])
 def test_channel_double_confirmation_project_explicit_and_replay(self):
  token=self.c.binding_challenge(self.owner,'project-a','TELEGRAM','123')['challenge']
  with self.assertRaises(Denied):self.c.channel_event('TELEGRAM','e0','999','/bind '+token)
  self.c.channel_event('TELEGRAM','e1','123','/bind '+token)
  with self.assertRaises(Denied):self.c.channel_event('TELEGRAM','e2','123','/project project-a hi')
  pending=self.c.pending_links(self.owner,'project-a')[0];self.c.confirm_link(self.owner,'project-a',pending['id']);r=self.c.channel_event('TELEGRAM','e3','123','/project project-a hello');self.assertEqual(r['status'],'ARCHIVED');self.assertTrue(self.c.channel_event('TELEGRAM','e3','123','/project project-a hello')['duplicate'])
  with self.assertRaises(Denied):self.c.channel_event('TELEGRAM','e4','123','plain text without project')
  self.c.unlink(self.owner,'project-a','TELEGRAM')
  with self.assertRaises(Denied):self.c.channel_event('TELEGRAM','e5','123','/project project-a hello')
 def test_provider_verification_freshness_and_false_client_claims(self):
  p=Providers({'telegram':{'webhook_secret':'w'*32}},clock=lambda:self.now);raw=canonical({'update_id':3,'message':{'from':{'id':123,'is_bot':False},'chat':{'type':'private','id':123},'date':self.now,'text':'hello'}})
  with self.assertRaises(Denied):p.telegram({},raw)
  self.assertEqual(p.telegram({'X-Telegram-Bot-Api-Secret-Token':'w'*32},raw)[1],'123')
  self.now+=301
  with self.assertRaises(Denied):p.telegram({'X-Telegram-Bot-Api-Secret-Token':'w'*32},raw)
  with self.assertRaises(Unavailable):p.feishu({},raw)
 def test_timeout_unknown_and_no_blind_resend(self):
  class P:
   calls=0
   def mail(s,*a):s.calls+=1;raise TimeoutError()
  p=P();r=drain_mail(self.c,p,'https://wenwenwenyiyiyi.work');self.assertEqual(r['status'],'UNKNOWN')
  # Only one selected record is UNKNOWN; future runs may process other PENDING
  # records, but must never retry this one.
  for _ in range(5):drain_mail(self.c,p,'https://wenwenwenyiyiyi.work')
  self.assertEqual(p.calls,4);self.assertEqual(self.c.db.execute("SELECT count(*) FROM outbox WHERE status='UNKNOWN'").fetchone()[0],4)
 def test_backup_restore_integrity_no_old_sessions_or_grants(self):
  self.accept();out=Path(self.tmp.name)/'backup.enc';r=backup(self.c,out,b'b'*32,'kms:backup-v1');self.assertFalse(r['contains_keys']);restored=Path(self.tmp.name)/'restore';v=restore(out,restored,b'b'*32,{'v1':self.key},'v1');self.assertEqual(v['restored'],'ISOLATED_MAINTENANCE')
  c2=Center(restored,{'v1':self.key},'v1',clock=lambda:self.now);self.addCleanup(c2.db.close);c2.check_integrity()
  with self.assertRaises(Unavailable):c2.session(self.users['owner']['token'])
  with self.assertRaises(Denied):c2.project(self.owner,'project-a')
  with self.assertRaises(Denied):restore(out,restored,b'b'*32,{'v1':self.key},'v1')
 def test_unknown_price_not_zero_and_requirement_history(self):
  self.accept();self.imported(2,[{**self.p,'requirements':[{**self.q,'id':'new','fees':'UNKNOWN'}]}]);self.assertEqual(self.c.checklist(self.owner,'project-a')['items'][0]['fees'],'UNKNOWN');self.assertEqual(self.c.db.execute('SELECT count(*) FROM project_history').fetchone()[0],2)
  oid=self.c.db.execute('SELECT id FROM objects').fetchone()[0];self.c.download(self.owner,'project-a',oid)
 def test_verification_pre_registration_password_cannot_survive(self):
  self.c.register('victim@example.com','attacker-password-123')
  self.c.register('victim@example.com','ignored-reregistration-password')
  rows=self.c.db.execute("SELECT * FROM outbox WHERE kind='VERIFY' ORDER BY rowid DESC LIMIT 2").fetchall()
  token=json.loads(self.c.decrypt(rows[0]['payload'],'outbox:'+rows[0]['id']))['token'];old=json.loads(self.c.decrypt(rows[1]['payload'],'outbox:'+rows[1]['id']))['token']
  with self.assertRaises(Denied):self.c.verify(old,'mailbox-owner-password')
  self.c.verify(token,'mailbox-owner-password')
  with self.assertRaises(Denied):self.c.login('victim@example.com','attacker-password-123')
  self.c.login('victim@example.com','mailbox-owner-password')
 def test_historical_internal_acl_survives_requirement_reclassification(self):
  internal={**self.q,'id':'internal','category':'INTERNAL'};self.imported(2,[{**self.p,'requirements':[internal]}]);self.c.save(self.reviewer,'project-a','internal',0,'DOCUMENT',b'%PDF-internal confidential')
  oid=self.c.db.execute('SELECT id FROM objects').fetchone()[0];self.imported(3,[{**self.p,'requirements':[{**internal,'category':'MATERIAL'}]}])
  with self.assertRaises(Denied):self.c.download(self.owner,'project-a',oid)
  self.assertEqual(self.c.checklist(self.owner,'project-a')['items'][0]['versions'],[])
  with self.assertRaises(Denied):self.c.transition(self.owner,'project-a','internal',1,'submit')
  self.c.download(self.reviewer,'project-a',oid)
 def test_expired_reset_and_invitation_tokens_fail_without_effects(self):
  self.c.request_reset('owner@example.com');r=self.c.db.execute("SELECT * FROM outbox WHERE kind='RESET'").fetchone();token=json.loads(self.c.decrypt(r['payload'],'outbox:'+r['id']))['token']
  invitation=self.c.invite(self.owner,'project-a','member@example.com','EDITOR')['invitation'];self.now+=601
  with self.assertRaises(Denied):self.c.reset(token,'new-password-1234')
  with self.assertRaises(Denied):self.c.accept_invite(self.member,invitation)
  self.assertEqual(self.c.session(self.users['owner']['token']),self.owner)
 def test_wrong_backup_key_or_tampered_backup_never_creates_restore(self):
  out=Path(self.tmp.name)/'backup-corruption.enc';backup(self.c,out,b'b'*32,'kms:test');target=Path(self.tmp.name)/'denied-restore'
  with self.assertRaises(Exception):restore(out,target,b'x'*32,{'v1':self.key},'v1')
  self.assertFalse(target.exists());raw=out.read_bytes();out.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
  with self.assertRaises(Exception):restore(out,target,b'b'*32,{'v1':self.key},'v1')
  self.assertFalse(target.exists())
 def test_expired_material_and_rate_limit_persisted(self):
  s=self.c.save(self.owner,'project-a','license',0,'DOCUMENT',b'%PDF-expiring',self.now+5);self.now+=6
  with self.assertRaises(Denied):self.c.transition(self.owner,'project-a','license',s['revision'],'submit')
  for _ in range(8):
   try:self.c.login('none@example.com','incorrect-password')
   except Denied:pass
  with self.assertRaisesRegex(Denied,'RATE_LIMIT'):self.c.login('none@example.com','incorrect-password')

if __name__=='__main__':unittest.main()

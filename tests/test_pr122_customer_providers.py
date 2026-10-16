import base64
import hashlib
import json
import os
import unittest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from scripts.pr122_customer_core import canonical,Denied,Unavailable
from scripts.pr122_customer_providers import Providers,enqueue,drain_message
from tests.test_pr122_customer_center import CustomerTests

class ProviderTests(CustomerTests):
 def signed(self,d):
  iv=b'i'*16;key=hashlib.sha256(b'encrypt-key').digest();pad=padding.PKCS7(128).padder();raw=pad.update(canonical(d))+pad.finalize();enc=Cipher(algorithms.AES(key),modes.CBC(iv)).encryptor();body=canonical({'encrypt':base64.b64encode(iv+enc.update(raw)+enc.finalize()).decode()});stamp=str(self.now);nonce='n'*16
  return {'X-Lark-Request-Timestamp':stamp,'X-Lark-Request-Nonce':nonce,'X-Lark-Signature':hashlib.sha256(stamp.encode()+nonce.encode()+b'encrypt-key'+body).hexdigest()},body
 def fs(self):return Providers({'feishu':{'encrypt_key':'encrypt-key','verification_token':'verification-token','app_id':'app-id'}},clock=lambda:self.now)
 def event(self):return {'header':{'app_id':'app-id','token':'verification-token','event_type':'im.message.receive_v1','event_id':'event_123','create_time':str(self.now*1000)},'event':{'sender':{'sender_type':'user','sender_id':{'open_id':'ou_user'}},'message':{'chat_type':'p2p','message_type':'text','content':json.dumps({'text':'hello'})}}}
 def test_feishu_real_algorithm_encrypted_verification_and_scope(self):
  headers,body=self.signed(self.event());self.assertEqual(self.fs().feishu(headers,body),('event_123','ou_user','hello'))
  with self.assertRaises(Denied):self.fs().feishu({**headers,'X-Lark-Signature':'0'*64},body)
  d=self.event();d['header']['app_id']='different';headers,body=self.signed(d)
  with self.assertRaises(Denied):self.fs().feishu(headers,body)
  d=self.event();d['event']['message']['chat_type']='group';headers,body=self.signed(d)
  with self.assertRaises(Denied):self.fs().feishu(headers,body)
 def test_feishu_url_challenge_expiry_plaintext_and_padding(self):
  headers,body=self.signed({'type':'url_verification','token':'verification-token','challenge':'challenge'});self.assertEqual(self.fs().feishu(headers,body),{'challenge':'challenge'})
  self.now+=301
  with self.assertRaises(Denied):self.fs().feishu(headers,body)
  with self.assertRaises(Denied):self.fs().feishu(headers,canonical(self.event()))
 def linked(self):
  t=self.c.binding_challenge(self.owner,'project-a','TELEGRAM','123')['challenge'];self.c.channel_event('TELEGRAM','bind1','123','/bind '+t);d=self.c.pending_links(self.owner,'project-a')[0];self.c.confirm_link(self.owner,'project-a',d['id'])
 def test_outbound_acceptance_not_delivery_and_timeout_no_retry(self):
  self.linked();enqueue(self.c,self.owner,'project-a','TELEGRAM','hello')
  calls=[]
  def post(url,body,headers=None):calls.append((url,body));return {'ok':True,'result':{'message_id':32}}
  p=Providers({'telegram':{'bot_token':'fake-fixture-token'}},post=post);self.assertEqual(drain_message(self.c,p)['status'],'ACCEPTED');self.assertEqual(len(calls),1);self.assertFalse(drain_message(self.c,p)['pending'])
  enqueue(self.c,self.owner,'project-a','TELEGRAM','second')
  def fail(*a):raise TimeoutError()
  p.post=fail;self.assertEqual(drain_message(self.c,p)['status'],'UNKNOWN');self.assertFalse(drain_message(self.c,p)['pending'])
 def test_unlink_or_revocation_blocks_queued_send(self):
  self.linked();enqueue(self.c,self.owner,'project-a','TELEGRAM','hello');self.c.unlink(self.owner,'project-a','TELEGRAM')
  with self.assertRaises(Denied):drain_message(self.c,Providers({}))
 def test_same_customer_multiple_projects_keeps_context_separate(self):
  p={**self.p,'id':'project-b'};self.imported(2,[self.p,p]);self.linked();t=self.c.binding_challenge(self.owner,'project-b','TELEGRAM','123')['challenge'];self.c.channel_event('TELEGRAM','bind2','123','/bind '+t);d=self.c.pending_links(self.owner,'project-b')[0];self.c.confirm_link(self.owner,'project-b',d['id']);self.c.channel_event('TELEGRAM','msgA','123','/project project-a A');self.c.channel_event('TELEGRAM','msgB','123','/project project-b B');self.assertEqual(self.c.messages(self.owner,'project-a')[0]['body'],'A');self.assertEqual(self.c.messages(self.owner,'project-b')[0]['body'],'B')
for name in list(CustomerTests.__dict__):
 if name.startswith('test_'):setattr(ProviderTests,name,None)
if __name__=='__main__':unittest.main()

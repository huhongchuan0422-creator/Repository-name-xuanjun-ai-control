import copy,json,unittest
import epoch7_approval as s
class Tests(unittest.TestCase):
 def setUp(self):
  self.wanted=s.expected('a'*64,'b'*64,'c'*64,'d'*64);self.id=7000000000
  self.comment={'id':self.id,'user':{'id':332398908,'login':'huhongchuan0422-creator'},
    'issue_url':'https://api.github.com/repos/'+s.REPO+'/issues/58','body':s.MARKER+json.dumps(self.wanted)}
 def run_check(self):return s.validate(json.dumps(self.comment).encode(),self.id,self.wanted)
 def test_exact(self):self.assertEqual(self.run_check()['approval'],self.wanted)
 def test_consumed(self):
  for i in s.CONSUMED:
   with self.assertRaises(ValueError):s.validate(b'{}',i,self.wanted)
 def test_wrong_author(self):
  self.comment['user']['id']=123
  with self.assertRaises(ValueError):self.run_check()
 def test_wrong_login(self):
  self.comment['user']['login']='other'
  with self.assertRaises(ValueError):self.run_check()
 def test_wrong_destination(self):
  self.comment['issue_url']=self.comment['issue_url'].replace('/58','/17')
  with self.assertRaises(ValueError):self.run_check()
 def test_wrong_version(self):
  v=copy.deepcopy(self.wanted);v['runtime_manifest_sha256']='e'*64;self.comment['body']=s.MARKER+json.dumps(v)
  with self.assertRaises(ValueError):self.run_check()
 def test_boolean_not_count(self):
  v=copy.deepcopy(self.wanted);v['authorized_attempts']=True;self.comment['body']=s.MARKER+json.dumps(v)
  with self.assertRaises(ValueError):self.run_check()
 def test_extra_scope(self):
  v=copy.deepcopy(self.wanted);v['retry']=True;self.comment['body']=s.MARKER+json.dumps(v)
  with self.assertRaises(ValueError):self.run_check()
 def test_old_marker(self):
  self.comment['body']='CHATGPT_NATIVE_TASK5_EXACT_HOLD_RECOVERY_ACCEPTANCE\n'+json.dumps(self.wanted)
  with self.assertRaises(ValueError):self.run_check()
 def test_duplicate_json(self):
  with self.assertRaisesRegex(ValueError,'DUPLICATE'):s.validate(b'{"id":1,"id":2}',self.id,self.wanted)
 def test_bound(self):
  with self.assertRaises(ValueError):s.validate(b'x'*65537,self.id,self.wanted)
 def test_bad_hash(self):
  with self.assertRaises(ValueError):s.expected('bad','b'*64,'c'*64,'d'*64)
 def test_redirect(self):
  with self.assertRaises(ValueError):s.NoRedirect().redirect_request(None,None,302,'',{},'http://other')
 def test_latest_consumed_v4_is_rejected(self):
  self.assertIn(6170703284,s.CONSUMED)
  with self.assertRaises(ValueError):s.validate(b'{}',6170703284,self.wanted)
 def test_exact_epoch7_to8(self):
  self.assertEqual(self.wanted['expected_epoch'],7)
  self.assertEqual(self.wanted['proposed_prepared_epoch'],8)
 def test_previous_epoch_fields_rejected(self):
  v=dict(self.wanted,expected_epoch=5,proposed_prepared_epoch=6)
  self.comment['body']=s.MARKER+json.dumps(v)
  with self.assertRaises(ValueError):self.run_check()
 def test_epoch5_marker_cannot_reuse_new_body(self):
  self.comment['body']=s.MARKER.replace('EPOCH7','EPOCH5')+json.dumps(self.wanted)
  with self.assertRaises(ValueError):self.run_check()
 def test_response_shape_fail_closed(self):
  for v in ([],None,{'user':[]},{'user':None}):
   with self.assertRaises(ValueError):s.validate(json.dumps(v).encode(),self.id,self.wanted)
if __name__=='__main__':unittest.main()

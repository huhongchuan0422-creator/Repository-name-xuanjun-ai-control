import hashlib,hmac,json,os,sqlite3,tempfile,unittest
from uk_owner_callback_core import apply,install_schema

class CallbackTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=os.path.join(self.tmp.name,'state.db')
  db=sqlite3.connect(self.path)
  db.executescript("CREATE TABLE tasks(id TEXT PRIMARY KEY,state TEXT,fence INTEGER,updated REAL);CREATE TABLE approvals(task_id TEXT PRIMARY KEY,decision TEXT,decided_at REAL);CREATE TABLE events(task_id TEXT,event TEXT,created REAL,details TEXT);")
  db.execute("INSERT INTO tasks VALUES('t','WAITING_HUMAN',2,0)")
  db.execute("INSERT INTO approvals VALUES('t','PENDING',NULL)")
  db.commit();db.close()
  install_schema(self.path)
  db=sqlite3.connect(self.path)
  db.execute("INSERT INTO owner_callback_requests VALUES('r','t',2,'123',5000,0)")
  db.commit();db.close()
  self.obj=dict(request_id='r',task_id='t',fence=2,owner_user_id='123',update_id=17,decision='APPROVE')
 def tearDown(self):self.tmp.cleanup()
 def call(self,auth='Bearer auth',signature=None,now=1000):
  raw=json.dumps(self.obj).encode();sig=hmac.new(b'key',raw,hashlib.sha256).hexdigest() if signature is None else signature
  return apply(self.path,raw,auth,sig,'auth',b'key','123',now=now)
 def test_approve_and_replay(self):
  self.assertTrue(self.call()['accepted'])
  with self.assertRaises((ValueError,sqlite3.IntegrityError)):self.call()
 def test_wrong_auth(self):
  with self.assertRaises(ValueError):self.call(auth='bad')
 def test_wrong_sig(self):
  with self.assertRaises(ValueError):self.call(signature='bad')
 def test_expired(self):
  with self.assertRaises(ValueError):self.call(now=6000)
 def test_bad_owner(self):
  self.obj['owner_user_id']='999'
  with self.assertRaises(ValueError):self.call()
 def test_stale_fence(self):
  self.obj['fence']=1
  with self.assertRaises(ValueError):self.call()
if __name__=='__main__':unittest.main()

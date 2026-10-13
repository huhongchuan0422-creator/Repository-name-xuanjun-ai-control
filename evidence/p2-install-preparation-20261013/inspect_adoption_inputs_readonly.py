import os,socket,sqlite3,json,hashlib,base64
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
root='/tmp/p2pkg-38420216343-1/xuanjun-p2-package'
for name in ('legacy_host_adapter.py','ledger_cutover_transaction.py','p2_install_entrypoint.py','ledger_backup.py'):
 with open(root+'/stage1/'+name,'rb') as f:r=f.read(131073)
 assert len(r)<=131072
 print('SOURCE_BYTES='+json.dumps({'name':name,'sha256':hashlib.sha256(r).hexdigest(),'base64':base64.b64encode(r).decode()},sort_keys=True))
p='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
assert not os.path.exists(p+'-wal') or os.stat(p+'-wal').st_size==0
def h(p):
 with open(p,'rb') as f:return hashlib.sha256(f.read()).hexdigest()
before=h(p);db=sqlite3.connect('file:'+p+'?mode=ro&immutable=1',uri=True);db.execute('PRAGMA query_only=ON')
def rows(table,fields):
 v=[]
 for raw in db.execute('SELECT '+','.join(fields)+' FROM '+table):
  item={}
  for key,x in zip(fields,raw):
   item[key]=hashlib.sha256(str(x).encode()).hexdigest() if x is not None and key in ('task_id','request_id','ack_message_id','telegram_message_id','owner_id','owner_chat') else x
  v.append(item)
 return v
data={'primary':rows('owner_notification_outbox',['task_id','fence','channel','state','ack_message_id','request_id']),'legacy':rows('xj_owner_notification_outbox',['task_id','fence','state','telegram_message_id']),'callbacks':rows('owner_callback_requests',['task_id','fence','request_id','expires_at','consumed'])}
db.close();assert before==h(p)
print('NOTIFICATION_REFERENCE_RECONCILIATION='+json.dumps(data,sort_keys=True))
print('IDENTIFIERS=SHA256; MESSAGE_CONTENT=NOT_READ; DB_UNCHANGED=YES; SEND=NO')

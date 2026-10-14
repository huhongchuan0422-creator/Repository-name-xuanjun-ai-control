"""Read only exact legacy schema metadata; no values or canonical writes."""
import hashlib,json,os,socket,sqlite3,stat
P='/home/xuanjun_dev/uk-stage1-minimal/state.sqlite'
def sha():
 fd=os.open(P,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  s=os.fstat(f.fileno());assert stat.S_ISREG(s.st_mode) and s.st_size==61440
  return hashlib.sha256(f.read(61441)).hexdigest()
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
before=sha();assert before=='a6b3847009ca7ee394772b7cf0144b90f82d1c68a3e9b4d3e9c4656f50c28d60'
for x in ('-wal','-journal'):assert not os.path.lexists(P+x) or os.stat(P+x).st_size==0
d=sqlite3.connect('file:'+P+'?mode=ro&immutable=1',uri=True);d.execute('PRAGMA query_only=ON')
result={}
for table in ('owner_callback_requests','owner_callback_replays'):
 result[table]={'columns':[{'name':r[1],'type':r[2],'notnull':r[3],'has_default':r[4] is not None,'pk':r[5]} for r in d.execute('PRAGMA table_info('+table+')')],'rows':d.execute('SELECT count(*) FROM '+table).fetchone()[0]}
d.close();assert before==sha()
print('EXACT_LEGACY_CALLBACK_SCHEMA='+json.dumps(result,sort_keys=True))

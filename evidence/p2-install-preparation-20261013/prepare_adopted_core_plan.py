import os,socket,json,hashlib,base64
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
ROOT='/tmp/p2-adoption-review-38431143591/xuanjun-p2-package'
with open(ROOT+'/deploy/integration-manifest.json','rb') as f:raw=f.read()
assert hashlib.sha256(raw).hexdigest()=='663ff2bd4bd0e4e9586cbc73357332a03557d529ed0f0b8a79ea93fed751a909'
manifest=json.loads(raw)
for rel in ('scripts/uk-p2-install.py','stage1/p2_fixed_host_runtime.py'):
 with open(ROOT+'/'+rel,'rb') as f:r=f.read(131073)
 assert len(r)<=131072 and hashlib.sha256(r).hexdigest()==manifest['files'][rel]
 print('CLI_WIRING_BYTES='+json.dumps({'path':rel,'base64':base64.b64encode(r).decode()}))
print('READ_ONLY=YES; INSTALL=NO')

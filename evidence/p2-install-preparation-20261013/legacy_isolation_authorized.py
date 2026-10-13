import os,socket,hashlib,base64
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
p='/tmp/p2pkg-38420216343-1/xuanjun-p2-package/stage1/legacy_host_adapter.py'
with open(p,'rb') as f:r=f.read(131073)
assert len(r)<=131072 and hashlib.sha256(r).hexdigest()=='07b212711446ed09f5759f8fddb1dfa33af84c49a9722bd3834e453ceef00fe5'
print('ADAPTER_BYTES_BASE64='+base64.b64encode(r).decode())
print('READ_ONLY=YES; STOP=NO')

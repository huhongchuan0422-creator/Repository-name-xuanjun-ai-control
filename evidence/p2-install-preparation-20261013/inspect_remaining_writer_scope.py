import os,socket,json,hashlib,base64,subprocess
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
root='/tmp/p2-adopted-plan-38432771093/xuanjun-p2-package'
with open(root+'/deploy/integration-manifest.json','rb') as f:m=f.read()
assert hashlib.sha256(m).hexdigest()=='508fcce851c7ea6e78efe28044871f44fff3e3dbfa8bffd94dffae2a2f89d3fd'
p=root+'/stage1/p2_fixed_host_runtime.py'
with open(p,'rb') as f:r=f.read(131073)
assert len(r)<=131072 and hashlib.sha256(r).hexdigest()==json.loads(m)['files']['stage1/p2_fixed_host_runtime.py']
print('AUXILIARY_RUNTIME_SOURCE_BASE64='+base64.b64encode(r).decode())
print('READ_ONLY=YES')

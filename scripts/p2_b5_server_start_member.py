"""One fixed server member from retained archive; UK candidate, not execution."""
import hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE_SHA='d1f27faec0ba63c083fa1211b13ffd1ad349648f257bccb0703727971f51f22d'
TARGET='dist/server-start-Bz-KV48j.mjs'
SIZE=382422
PIN='e3feab1b6f29558035cb7bb49d9d4e296f7f1ea4462c72a03c5912991f526e17'
def need(ok,code):
 if not ok:raise ValueError(code)
def analyze(rows,get,root,frontier,elf):
 # The inherited run() performs full strict tar/manifest/all-member validation first.
 row=rows.get(root+TARGET);need(row is not None,'SERVER_MEMBER_ABSENT')
 need(row['bytes']==SIZE and row['sha256']==PIN,'SERVER_MANIFEST_FIXED_PIN')
 raw=get(root+TARGET)
 need(len(raw)==SIZE and hashlib.sha256(raw).hexdigest()==PIN,'SERVER_CONTENT_SHA')
 report={'scope':'ISOLATED_TEST_ONLY_SINGLE_SERVER_START_MEMBER','dependency_closure':'UNKNOWN',
  'sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED',
  'owner_binding':'UNBOUND','selection':'EXACT_ONE_FIXED_MEMBER_NO_RECURSION',
  'selected':{TARGET:{'bytes':SIZE,'sha256':PIN,'source_member':root+TARGET,
   'binding':'FIXED_PIN_AND_FULL_MANIFEST_ALL_MEMBER_VERIFICATION'}}}
 return report,{TARGET:raw}
def load_base():
 raw=(HERE/'p2_b5_retained_materials.py').read_bytes()
 need(hashlib.sha256(raw).hexdigest()==BASE_SHA,'BASE_TOOL_SHA')
 module=types.ModuleType('b5_single_server_host');module.__file__=str(HERE/'p2_b5_retained_materials.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 module.analyze=analyze;module.OUTPUT='p2-b5-server-start-member-v1-20261021'
 return module
if __name__=='__main__':
 import sys,json
 try:sys.exit(load_base().main())
 except Exception as exc:
  print(json.dumps({'state':'HOLD_RETAIN_OUTPUT','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'sdk':'NOT_EXECUTED'}));sys.exit(2)

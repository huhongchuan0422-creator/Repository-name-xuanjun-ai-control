"""Three exact retained members only. Candidate; separate UK approval required."""
import hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE_SHA='d1f27faec0ba63c083fa1211b13ffd1ad349648f257bccb0703727971f51f22d'
TARGETS=('dist/run-BNH_gC9b.mjs','dist/message-handler-DKklmnFX.mjs','dist/ws-connection-CsJ9cE0L.mjs')
RUN_SHA='55673f688f7e455cd1bfdaf6a0f26270ff5e6565881403c1b066a82530ab810f'
def need(ok,code):
 if not ok:raise ValueError(code)
def analyze(rows,get,root,frontier,elf):
 # rows are returned only after the frozen full-manifest/full-archive verifier.
 expected={}
 for name in TARGETS:
  row=rows.get(root+name);need(row is not None,'EXACT_ANCHOR_ABSENT')
  need(0<row['bytes']<=2*1024*1024,'ANCHOR_SIZE_BOUND')
  expected[name]=row
 need(expected[TARGETS[0]]['bytes']==122958 and expected[TARGETS[0]]['sha256']==RUN_SHA,'RUN_FIXED_PIN')
 selected={}
 for name in TARGETS:
  raw=get(root+name);row=expected[name]
  need(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'ANCHOR_CONTENT_SHA')
  selected[name]=raw
 # Content stays data. No import, parser execution, dependency traversal or JS eval.
 return {'scope':'ISOLATED_TEST_ONLY_WS_ANCHOR_MATERIALS','dependency_closure':'UNKNOWN',
  'sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED',
  'dispatcher_binding':'UNBOUND','anchor_necessity':'UNKNOWN_PENDING_OFFLINE_CONTENT_ANALYSIS',
  'selection':'EXACT_THREE_MANIFEST_BOUND_MEMBERS_NO_RECURSION',
  'selected':{name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
   'source_member':root+name,'binding':'FULL_PINNED_MANIFEST_AND_ALL_MEMBER_VALIDATION'} for name,raw in sorted(selected.items())}},selected

def load_base():
 raw=(HERE/'p2_b5_retained_materials.py').read_bytes()
 need(hashlib.sha256(raw).hexdigest()==BASE_SHA,'BASE_TOOL_SHA')
 module=types.ModuleType('b5_ws_frozen_host');module.__file__=str(HERE/'p2_b5_retained_materials.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 module.analyze=analyze;module.OUTPUT='p2-b5-ws-anchors-v1-20261021'
 return module
if __name__=='__main__':
 import sys,json
 try:sys.exit(load_base().main())
 except Exception as exc:
  print(json.dumps({'state':'HOLD_RETAIN_OUTPUT','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'sdk':'NOT_EXECUTED'}));sys.exit(2)

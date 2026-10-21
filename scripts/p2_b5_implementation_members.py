"""Exactly two pinned assembly-analysis members; no SDK execution."""
import hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE_SHA='d1f27faec0ba63c083fa1211b13ffd1ad349648f257bccb0703727971f51f22d'
TARGETS={'dist/server-plugin-bootstrap-BF-wNIVo.mjs': {'bytes': 3726, 'sha256': 'd52477f026b0aeb3c2ee9baafc4a081506ac7a08bff645ec9850e19dd8483881'}, 'dist/server-startup-config-helpers-d2nPJiVj.mjs': {'bytes': 11278, 'sha256': 'd969dec157ce6a62f7c999d09e5682c9abfa0430b1fa7baeaa4106ceeb90fcde'}}
TOTAL=15004
def need(ok,code):
 if not ok:raise ValueError(code)
def analyze(rows,get,root,frontier,elf):
 need(len(TARGETS)==2 and sum(x['bytes'] for x in TARGETS.values())==TOTAL,'TWO_SELECTION_BOUND')
 for name,pin in sorted(TARGETS.items()):
  row=rows.get(root+name);need(row is not None,'TWO_MEMBER_ABSENT')
  need(row['bytes']==pin['bytes'] and row['sha256']==pin['sha256'],'TWO_MANIFEST_FIXED_PIN')
 selected={}
 for name,pin in sorted(TARGETS.items()):
  raw=get(root+name)
  need(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'TWO_CONTENT_SHA')
  selected[name]=raw
 report={'scope':'ISOLATED_TEST_ONLY_PUBLIC_ASSEMBLY_TWO_MEMBER_ANALYSIS','dependency_closure':'UNKNOWN',
  'sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED',
  'owner_binding':'UNBOUND','selection':'EXACT_TWO_FIXED_MEMBERS_NO_RECURSION',
  'selected':{n:dict(p,source_member=root+n,binding='FIXED_PIN_AND_FULL_MANIFEST_ALL_MEMBER_VERIFICATION') for n,p in sorted(TARGETS.items())}}
 return report,selected
def load_base():
 raw=(HERE/'p2_b5_retained_materials.py').read_bytes();need(hashlib.sha256(raw).hexdigest()==BASE_SHA,'BASE_TOOL_SHA')
 module=types.ModuleType('b5_two_analysis_host');module.__file__=str(HERE/'p2_b5_retained_materials.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 module.analyze=analyze;module.OUTPUT='p2-b5-implementation-pair-members-v1-20261021'
 return module
if __name__=='__main__':
 import sys,json
 try:sys.exit(load_base().main())
 except Exception as exc:
  print(json.dumps({'state':'HOLD_RETAIN_OUTPUT','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'sdk':'NOT_EXECUTED'}));sys.exit(2)

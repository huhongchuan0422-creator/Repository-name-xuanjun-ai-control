"""Exactly three pinned assembly-analysis members; no SDK execution."""
import hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE_SHA='d1f27faec0ba63c083fa1211b13ffd1ad349648f257bccb0703727971f51f22d'
TARGETS={'dist/server-startup-config-helpers-U6xkM_57.mjs': {'bytes': 137, 'sha256': '05234c987220249a923175b49d20d7edc5f49c091272fbdca2a2f151e9aae765'}, 'dist/server-startup-early-BLUjqlAE.mjs': {'bytes': 4816, 'sha256': '1d457bf7c8373bc3f37acaa9039b588efa4e24a46d9d3d15751d88d84fa3b551'}, 'dist/server-startup-post-attach-CsYAFanV.mjs': {'bytes': 53969, 'sha256': 'b62aa11d48ecedddf1b606f33114cdde8faf7fc193305eafddb918427024de22'}}
TOTAL=58922
def need(ok,code):
 if not ok:raise ValueError(code)
def analyze(rows,get,root,frontier,elf):
 need(len(TARGETS)==3 and sum(x['bytes'] for x in TARGETS.values())==TOTAL,'THREE_SELECTION_BOUND')
 for name,pin in sorted(TARGETS.items()):
  row=rows.get(root+name);need(row is not None,'THREE_MEMBER_ABSENT')
  need(row['bytes']==pin['bytes'] and row['sha256']==pin['sha256'],'THREE_MANIFEST_FIXED_PIN')
 selected={}
 for name,pin in sorted(TARGETS.items()):
  raw=get(root+name)
  need(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'THREE_CONTENT_SHA')
  selected[name]=raw
 report={'scope':'ISOLATED_TEST_ONLY_PUBLIC_ASSEMBLY_THREE_MEMBER_ANALYSIS','dependency_closure':'UNKNOWN',
  'sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED',
  'owner_binding':'UNBOUND','selection':'EXACT_THREE_FIXED_MEMBERS_NO_RECURSION',
  'selected':{n:dict(p,source_member=root+n,binding='FIXED_PIN_AND_FULL_MANIFEST_ALL_MEMBER_VERIFICATION') for n,p in sorted(TARGETS.items())}}
 return report,selected
def load_base():
 raw=(HERE/'p2_b5_retained_materials.py').read_bytes();need(hashlib.sha256(raw).hexdigest()==BASE_SHA,'BASE_TOOL_SHA')
 module=types.ModuleType('b5_three_analysis_host');module.__file__=str(HERE/'p2_b5_retained_materials.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 module.analyze=analyze;module.OUTPUT='p2-b5-native-startup-three-members-v1-20261021'
 return module
if __name__=='__main__':
 import sys,json
 try:sys.exit(load_base().main())
 except Exception as exc:
  print(json.dumps({'state':'HOLD_RETAIN_OUTPUT','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'sdk':'NOT_EXECUTED'}));sys.exit(2)

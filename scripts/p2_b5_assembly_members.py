"""Exactly four pinned assembly-analysis members; no SDK execution."""
import hashlib,types
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE_SHA='d1f27faec0ba63c083fa1211b13ffd1ad349648f257bccb0703727971f51f22d'
TARGETS={'dist/server-startup-plugins-Cajv-q3y.mjs': {'bytes': 12979, 'sha256': 'be588e2acbd30d55efb0c15a142354337dc220e107f2c00bda78067c07ec121f'}, 'dist/server-startup-config-Hx2M1x7s.mjs': {'bytes': 24633, 'sha256': 'c6c846ead6ec7b1eaf081530966d7b41a6363e8f05e6590daf2469fbc329ee97'}, 'dist/proxy-lifecycle-Dl57fEmL.mjs': {'bytes': 7794, 'sha256': 'de283d5f397582801b5f35b43ffbe17cb4f49e70c14233a7d6bac2ac3fb794f6'}, 'dist/url-protocol-OU3K-ySz.mjs': {'bytes': 823, 'sha256': '8ad6637ea5831197a0ec03be4ef69c44f08ea616e06ab39b960f0f49b76f196e'}}
TOTAL=46229
def need(ok,code):
 if not ok:raise ValueError(code)
def analyze(rows,get,root,frontier,elf):
 need(len(TARGETS)==4 and sum(x['bytes'] for x in TARGETS.values())==TOTAL,'FOUR_SELECTION_BOUND')
 for name,pin in sorted(TARGETS.items()):
  row=rows.get(root+name);need(row is not None,'FOUR_MEMBER_ABSENT')
  need(row['bytes']==pin['bytes'] and row['sha256']==pin['sha256'],'FOUR_MANIFEST_FIXED_PIN')
 selected={}
 for name,pin in sorted(TARGETS.items()):
  raw=get(root+name)
  need(len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'FOUR_CONTENT_SHA')
  selected[name]=raw
 report={'scope':'ISOLATED_TEST_ONLY_PUBLIC_ASSEMBLY_FOUR_MEMBER_ANALYSIS','dependency_closure':'UNKNOWN',
  'sdk':'NOT_EXECUTED','cp11':'NOT_EXECUTED','authenticated_dispatch':'NOT_EXECUTED',
  'owner_binding':'UNBOUND','selection':'EXACT_FOUR_FIXED_MEMBERS_NO_RECURSION',
  'selected':{n:dict(p,source_member=root+n,binding='FIXED_PIN_AND_FULL_MANIFEST_ALL_MEMBER_VERIFICATION') for n,p in sorted(TARGETS.items())}}
 return report,selected
def load_base():
 raw=(HERE/'p2_b5_retained_materials.py').read_bytes();need(hashlib.sha256(raw).hexdigest()==BASE_SHA,'BASE_TOOL_SHA')
 module=types.ModuleType('b5_four_analysis_host');module.__file__=str(HERE/'p2_b5_retained_materials.py')
 exec(compile(raw,module.__file__,'exec'),module.__dict__)
 module.analyze=analyze;module.OUTPUT='p2-b5-assembly-four-members-v1-20261021'
 return module
if __name__=='__main__':
 import sys,json
 try:sys.exit(load_base().main())
 except Exception as exc:
  print(json.dumps({'state':'HOLD_RETAIN_OUTPUT','error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'sdk':'NOT_EXECUTED'}));sys.exit(2)

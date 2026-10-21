from pathlib import Path,PurePosixPath
import re,json,hashlib,collections
roots=['dist/loader-runtime-load-DpgEqnzx.mjs','dist/registry-CAoo0u-p.mjs','dist/message-handler-DKklmnFX.mjs','dist/ws-connection-CsJ9cE0L.mjs','dist/server-ChnNHwLm.mjs','dist/server-start-Bz-KV48j.mjs','dist/server-shutdown-6hlRrMSx.mjs']
files={}
for d in ['b5-material-verified','b5-ws-verified']:
 for p in Path(d).rglob('*'):
  if p.is_file():files[p.relative_to(d).as_posix()]=p
pat=re.compile(r'^\s*(?:import\s+(?:[^;]*?\s+from\s+)?|export\s+[^;]*?\s+from\s+)[\"\']([^\"\']+)[\"\']\s*;?\s*$')
# Compiled fixed source uses one-line static module declarations; anything else
# beginning import/export-from is explicitly unresolved, never treated closed.
import os
if os.environ.get('B5_ROUTE')=='inspection':roots=roots[:2]
elif os.environ.get('B5_ROUTE')=='public_ws':roots=roots[1:4]
queue=collections.deque(roots);seen=set();missing={};packages={};unsupported=[];edges=[]
while queue:
 n=queue.popleft()
 if n in seen:continue
 seen.add(n)
 if n not in files:continue
 p=files[n];raw=p.read_bytes()
 if p.suffix not in ['.mjs','.js','.cjs']:continue
 for line,s in enumerate(raw.decode('utf8').splitlines(),1):
  m=pat.match(s)
  if not m:
   if re.match(r'^\s*(?:import\s+(?!\()|export\s+.*\bfrom\b)',s) and not s.lstrip().startswith('import.meta'):unsupported.append({'member':n,'line':line})
   continue
  spec=m.group(1);w={'parent':n,'line':line,'specifier':spec}
  if spec.startswith('node:'):continue
  if not spec.startswith('.'):
   packages.setdefault(spec,w);continue
  target=(PurePosixPath(n).parent/spec).as_posix()
  # Fixed observed specs do not use '..'. Never silently resolve escape.
  if '..' in PurePosixPath(target).parts:unsupported.append(w);continue
  edges.append((n,target))
  if target in files:queue.append(target)
  else:missing.setdefault(target,w)
record={'scope':'STATIC_EAGER_IMPORT_BOUNDARY_NOT_EXECUTION_CLOSURE','roots':roots,'received_members_visited':len(seen),'static_relative_edges':len(edges),'missing_eager_members':[{**v,'member':n,'present':False,'bytes':None,'sha256':None,'manifest_binding':'UNKNOWN_ROW_NOT_DELIVERED','reason':'Literal static dependency of a reachable received module; mandatory if this full entry route is imported'} for n,v in sorted(missing.items())],'bare_specifiers':[{'specifier':n,**v,'resolution':'UNKNOWN_NO_NODE_RESOLVER_EXECUTED'} for n,v in sorted(packages.items())],'unsupported_static_declarations':unsupported,'conditional_dynamic_resources':'NOT_CLOSED; excluded from required extraction list','sdk':'NOT_EXECUTED','candidate':'DRAFT_NOT_FROZEN_NO_ONSITE_ACTION'}
print(json.dumps(record,indent=2))
print(json.dumps({'visited':len(seen),'missing_eager':len(missing),'bare_specifiers':len(packages),'unsupported':len(unsupported),'roots':roots,'missing_first':list(sorted(missing))[:8]}))

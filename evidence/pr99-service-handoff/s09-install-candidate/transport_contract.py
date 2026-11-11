"""Redacted AST-only transport definitions, no module import or credentials."""
import ast,hashlib,json,os,re
from pathlib import Path
ROOT=Path('/opt/xuanjun-migration-s07/releases/domestic-r1/rootfs/opt/trading-system')
class Redact(ast.NodeTransformer):
 def visit_Constant(self,n):
  if isinstance(n.value,str) and not re.fullmatch(r'(?:127\.0\.0\.1|localhost|https?|https?://127\.0\.0\.1:[0-9]{2,5}|/[A-Za-z0-9_./-]{1,150})',n.value):
   return ast.copy_location(ast.Constant(value='STRING_WITHHELD'),n)
  return n

def main():
 assert os.geteuid()==0 and os.uname().nodename=='iZvt5t8tlrm8oiZ'
 rows=[]
 for name in ('ai_service/internal_provider_neutral_bridge.py','ai_service/telegram_customer_service_canary.py','ai_service/wecom_customer_service.py'):
  p=ROOT/name;assert not p.is_symlink();raw=p.read_bytes();assert len(raw)<150000
  tree=ast.parse(raw);selected=[]
  for node in tree.body:
   if isinstance(node,(ast.Import,ast.ImportFrom)) and 'bridge' in ast.unparse(node).lower():selected.append(node)
   elif isinstance(node,(ast.Assign,ast.AnnAssign)):
    # Global declarations can bind network defaults indirectly. All string
    # literals are redacted except literal loopback origins and safe paths.
    selected.append(node)
   elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and re.search(r'https|transport|bridge',node.name,re.I):selected.append(node)
   elif isinstance(node,ast.ClassDef):
    if node.name=='ProviderNeutralBridgeClient' or re.search(r'transport',node.name,re.I):selected.append(node)
    else:
     methods=[m for m in node.body if isinstance(m,ast.FunctionDef) and m.name in ('_default_bridge_client','_bridge_client')]
     if methods:selected.extend(methods)
  projected=ast.unparse(Redact().visit(ast.Module(body=selected,type_ignores=[])))
  rows.append({'source':name,'sha256':hashlib.sha256(raw).hexdigest(),'redacted_source_contract':projected})
 out={'status':'STATIC_BRIDGE_ROUTE_CONTRACT','hostname':os.uname().nodename,'uid':0,'attempt_nonce':ATTEMPT_NONCE,'rows':rows,'service_actions':0,'business_api_requests':0,'database_opened':False,'effective_runtime_endpoint_proven':False}
 encoded=json.dumps(out,sort_keys=True);assert len(encoded)<30000
 print(encoded,flush=True)
if __name__=='__main__':main()

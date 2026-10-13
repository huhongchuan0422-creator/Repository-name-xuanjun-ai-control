import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent
m_path=r/'deploy/integration-manifest.json';m=json.loads(m_path.read_text())
def load(rel):
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][rel]:raise ValueError('ADOPTION_INPUT_MANIFEST')
 return raw.decode()
a='stage1/legacy_host_adapter.py';s=load(a)
old="    def preflight(self, plan):\n        self._authority()"
new=old+"\n        if 'legacy_isolation' in plan:\n            from p2_legacy_adoption import bind\n            return bind(self,plan)"
if s.count(old)!=1:raise ValueError('ADOPTION_PREFLIGHT_ANCHOR')
s=s.replace(old,new)
old="    def stop_and_inhibit(self, bindings):\n        self._authority()"
new=old+"\n        if hasattr(self,'_adoption_plan'):\n            if bindings!=self._adoption_plan['legacy_bindings']:raise ValueError('ADOPTION_STOP_BINDINGS_CHANGED')\n            from p2_legacy_adoption import bind\n            bind(self,self._adoption_plan)\n            return # Existing isolated transaction: zero repeated systemd effects."
if s.count(old)!=1:raise ValueError('ADOPTION_STOP_ANCHOR')
s=s.replace(old,new)
b='stage1/ledger_cutover_transaction.py';t=load(b)
old="if not isinstance(plan, dict) or set(plan) != required or plan['schema'] != 1:"
new="if not isinstance(plan, dict) or set(plan) not in (required,required|{'legacy_isolation'}) or plan['schema'] != 1:"
if t.count(old)!=1:raise ValueError('ADOPTION_CUTOVER_ANCHOR')
t=t.replace(old,new)
texts={a:s,b:t,'stage1/p2_legacy_adoption.py':(here/'p2_legacy_adoption.py').read_text()}
for rel,text in texts.items():
 (r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
m_path.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
print('EXPLICIT_ISOLATION_ADOPTION_OVERLAY=PASS; INSTALL=NO')

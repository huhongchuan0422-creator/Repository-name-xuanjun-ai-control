import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent;mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
def load(p):
 raw=(r/p).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][p]:raise ValueError('AUX_INPUT_MANIFEST')
 return raw.decode()
a='stage1/p2_fixed_host_runtime.py';s=load(a)
def rep(old,new):
 global s
 if s.count(old)!=1:raise ValueError('AUX_ANCHOR_'+old[:60])
 s=s.replace(old,new)
rep('from p2_rpm_prerequisites import RpmPrerequisites',"from p2_rpm_prerequisites import RpmPrerequisites\nimport p2_auxiliary_isolation as Auxiliary")
rep("        self.prerequisites.preflight(runtime['prerequisites'])","        if 'legacy_cutover' in runtime or 'auxiliary_isolation' in runtime:\n            Auxiliary.verify(runtime.get('auxiliary_isolation'))\n        self.prerequisites.preflight(runtime['prerequisites'])")
rep("    def _binding(binding, release):","    def _binding(binding, release, auxiliary=None):")
rep("or not isinstance(target, str) or os.path.realpath(target) != target","or not isinstance(target, str) or (os.path.realpath(target) != target and not (auxiliary is not None and Auxiliary.is_mask(target)))")
# An allowed mask must have its exact receipt authenticated before binding.
rep("        for token, replacement in binding['replacements'].items():","        if Auxiliary.is_mask(target):Auxiliary.verify(auxiliary)\n        for token, replacement in binding['replacements'].items():")
if s.count('self._binding(binding, release)')!=2:raise ValueError('AUX_BINDING_CALLS')
s=s.replace('self._binding(binding, release)',"self._binding(binding, release, runtime.get('auxiliary_isolation'))")
rep("    def provision(self, release, runtime):\n        self._authority()","    def provision(self, release, runtime):\n        self._authority()\n        if 'legacy_cutover' in runtime or 'auxiliary_isolation' in runtime:\n            Auxiliary.verify(runtime.get('auxiliary_isolation'))")
rep("            if os.path.lexists(target):\n                old, info = _read_regular(target)","            if Auxiliary.is_mask(target):\n                backup=os.path.join(self.directory,'target-%03d.backup'%number)\n                previous=Auxiliary.mask_previous(runtime.get('auxiliary_isolation'),target,backup)\n            elif os.path.lexists(target):\n                old, info = _read_regular(target)")
rep("        packed = json.dumps(receipt, sort_keys=True,\n                            separators=(',', ':')).encode('utf-8')\n        reference =", "        if 'auxiliary_isolation' in runtime:receipt['auxiliary_isolation']=runtime['auxiliary_isolation']\n        packed = json.dumps(receipt, sort_keys=True,\n                            separators=(',', ':')).encode('utf-8')\n        reference =")
rep("        # Validate every backup and current target before any rollback effect.","        aux_snapshot=Auxiliary.verify(receipt['auxiliary_isolation'],masked=False) if 'auxiliary_isolation' in receipt else None\n        # Validate every backup and current target before any rollback effect.")
rep("            target = item['target']\n            if (","            target = item['target']\n            masked_previous=isinstance(item.get('previous'),dict) and item['previous'].get('masked') is True\n            if masked_previous and (not Auxiliary.scoped(target) or aux_snapshot is None or item['previous'].get('sha256')!=aux_snapshot['unit_hashes'][os.path.basename(target)] or (item['previous'].get('mode'),item['previous'].get('uid'),item['previous'].get('gid'))!=(0o644,0,0)):raise ValueError('AUX_ROLLBACK_MASK_BINDING')\n            if (")
rep("or os.path.realpath(target) != target or target in seen","or (os.path.realpath(target) != target and not (masked_previous and Auxiliary.is_mask(target))) or target in seen")
rep("            if os.path.lexists(target):\n                current, info = _read_regular(target)","            if masked_previous and Auxiliary.is_mask(target):\n                prepared.append((item,old));continue\n            if os.path.lexists(target):\n                current, info = _read_regular(target)")
rep("            else:\n                self._atomic_target(item['target'], old, previous['mode'],","            elif previous.get('masked') is True:\n                Auxiliary.restore_mask(item['target'])\n            else:\n                self._atomic_target(item['target'], old, previous['mode'],")
b='stage1/p2_install_entrypoint.py';t=load(b)
old="set(runtime)-{'legacy_cutover'}"
if t.count(old)!=1:raise ValueError('AUX_RUNTIME_SCHEMA')
t=t.replace(old,"set(runtime)-{'legacy_cutover','auxiliary_isolation'}")
anchor="    if 'bootstrap' in runtime:"
add="""    if 'legacy_cutover' in runtime and 'auxiliary_isolation' not in runtime:
        raise ValueError('AUXILIARY_ISOLATION_REQUIRED')
    if 'auxiliary_isolation' in runtime:
        ref=runtime['auxiliary_isolation']
        if not isinstance(ref,dict) or set(ref)!={'path','sha256','transaction_id'} or ref['transaction_id']!=plan['transaction_id']:
            raise ValueError('AUXILIARY_TRANSACTION_BINDING')
"""
if t.count(anchor)!=1:raise ValueError('AUX_PLAN_ANCHOR')
t=t.replace(anchor,add+anchor)
texts={a:s,b:t,'stage1/p2_auxiliary_isolation.py':(here/'p2_auxiliary_isolation.py').read_text()}
for p,text in texts.items():(r/p).write_text(text);m['files'][p]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,sort_keys=True,indent=2)+'\n');print('AUXILIARY_ADMISSION_MASKED_PROVISION_AND_MASK_ROLLBACK=PASS; INSTALL=NO')

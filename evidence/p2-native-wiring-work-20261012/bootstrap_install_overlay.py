"""Attach exact private bootstrap transaction to fixed-host provision/restore."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent
mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
pins={'stage1/p2_fixed_host_runtime.py':'00e65b2eaa934d75b21c8c3dc121afc5d4c1622865d73d7680421dab7485eb85',
 'stage1/p2_install_entrypoint.py':'7a0b270756899ab41e3c11ee50c738386ca542f227986067e149861922565fa4'}
texts={}
for rel,pin in pins.items():
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pin or m['files'][rel]!=pin:raise ValueError('BOOTSTRAP_BASE_HASH')
 texts[rel]=raw.decode()
def replace(rel,old,new):
 if texts[rel].count(old)!=1:raise ValueError('BOOTSTRAP_ANCHOR')
 texts[rel]=texts[rel].replace(old,new)
a='stage1/p2_fixed_host_runtime.py';b='stage1/p2_install_entrypoint.py'
replace(a,'from p2_prerequisites import Prerequisites','from p2_prerequisites import Prerequisites\nfrom p2_bootstrap_files import BootstrapFiles')
replace(a,"        self.prerequisites.preflight(runtime['prerequisites'])", "        self.prerequisites.preflight(runtime['prerequisites'])\n        BootstrapFiles(self.directory).prepare(runtime.get('bootstrap'),runtime['release_directory'])")
replace(a,"            if create_dropin_parent:self._create_dropin_parent()", "            BootstrapFiles(self.directory).apply(runtime.get('bootstrap'),runtime['release_directory'])\n            if create_dropin_parent:self._create_dropin_parent()")
replace(a,"        self._restore_boot()", "        BootstrapFiles(self.directory).rollback_rows()\n        self._restore_boot()")
replace(a,"        self.prerequisites.rollback(receipt['prerequisites'])", "        BootstrapFiles(self.directory).rollback()\n        self.prerequisites.rollback(receipt['prerequisites'])")
replace(b,"            or set(runtime) != {'release_directory', 'provisioning', 'services', 'prerequisites', 'plugin'}", "            or set(runtime) not in ({'release_directory','provisioning','services','prerequisites','plugin'},\n                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap'})")
replace(b,"    plugin=runtime['plugin']", "    if 'bootstrap' in runtime:\n        value=runtime['bootstrap']\n        if (not isinstance(value,dict) or set(value)!={'path','sha256'}\n                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')\n                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None):\n            raise ValueError('INVALID_BOOTSTRAP_REFERENCE')\n    plugin=runtime['plugin']")
if (r/'stage1/p2_bootstrap_files.py').exists():raise ValueError('BOOTSTRAP_MODULE_PRESENT')
texts['stage1/p2_bootstrap_files.py']=(here/'p2_bootstrap_files.py').read_text()
for rel,text in texts.items():(r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
print('BOOTSTRAP_FIXED_RUNTIME_APPLY_RESTORE_HOOKS=PASS; INSTALL=NO')

"""Connect typed publisher directory transaction to reviewed bootstrap lifecycle."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent;mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
paths=('stage1/p2_fixed_host_runtime.py','stage1/p2_install_entrypoint.py');texts={}
for rel in paths:
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][rel]:raise ValueError('PUBLISHER_INPUT_MANIFEST_HASH')
 texts[rel]=raw.decode()
def replace(rel,old,new):
 if texts[rel].count(old)!=1:raise ValueError('PUBLISHER_OVERLAY_ANCHOR')
 texts[rel]=texts[rel].replace(old,new)
a,b=paths
replace(a,'from p2_bootstrap_files import BootstrapFiles','from p2_bootstrap_files import BootstrapFiles\nfrom p2_publisher_bootstrap import PublisherBootstrap')
anchor="        BootstrapFiles(self.directory).prepare(runtime.get('bootstrap'),runtime['release_directory'])"
replace(a,anchor,anchor+"\n        PublisherBootstrap(self.directory).prepare(runtime.get('publisher'))")
anchor="            BootstrapFiles(self.directory).apply(runtime.get('bootstrap'),runtime['release_directory'])"
replace(a,anchor,anchor+"\n            PublisherBootstrap(self.directory).apply(runtime.get('publisher'))")
replace(a,"        BootstrapFiles(self.directory).rollback_rows()", "        BootstrapFiles(self.directory).rollback_rows()\n        PublisherBootstrap(self.directory).rollback_rows()")
replace(a,"        BootstrapFiles(self.directory).rollback()", "        PublisherBootstrap(self.directory).rollback()\n        BootstrapFiles(self.directory).rollback()")
replace(b,"{'release_directory','provisioning','services','prerequisites','plugin','bootstrap'})", "{'release_directory','provisioning','services','prerequisites','plugin','bootstrap'},\n                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher'})")
replace(b,"    plugin=runtime['plugin']", "    if 'publisher' in runtime:\n        value=runtime['publisher']\n        if (not isinstance(value,dict) or set(value)!={'path','sha256','source_commit','source_tree'}\n                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')\n                or not isinstance(value['sha256'],str) or re.fullmatch(r'[0-9a-f]{64}',value['sha256']) is None\n                or value['source_commit']!=plan['artifact']['source_commit']\n                or value['source_tree']!=plan['artifact']['source_tree']):\n            raise ValueError('INVALID_PUBLISHER_REFERENCE')\n    plugin=runtime['plugin']")
rel='stage1/p2_publisher_bootstrap.py'
if (r/rel).exists():raise ValueError('PUBLISHER_MODULE_PRESENT')
texts[rel]=(here/'p2_publisher_bootstrap.py').read_text()
for rel,text in texts.items():(r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');print('PUBLISHER_PROVISION_RESTORE_HOOKS=PASS; INSTALL=NO')

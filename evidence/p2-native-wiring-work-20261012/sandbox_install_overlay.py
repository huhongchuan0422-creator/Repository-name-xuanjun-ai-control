"""Apply protected sandbox policy while Gateway is stopped; restore exact old bytes."""
import hashlib,json,pathlib,sys
r=pathlib.Path(sys.argv[1]);here=pathlib.Path(__file__).resolve().parent;mp=r/'deploy/integration-manifest.json';m=json.loads(mp.read_text())
paths=('stage1/p2_fixed_host_runtime.py','stage1/p2_install_entrypoint.py');texts={}
for rel in paths:
 raw=(r/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=m['files'][rel]:raise ValueError('SANDBOX_INPUT_MANIFEST_HASH')
 texts[rel]=raw.decode()
def replace(rel,old,new):
 if texts[rel].count(old)!=1:raise ValueError('SANDBOX_OVERLAY_ANCHOR')
 texts[rel]=texts[rel].replace(old,new)
a,b=paths
replace(a,'from p2_publisher_bootstrap import PublisherBootstrap','from p2_publisher_bootstrap import PublisherBootstrap\nfrom p2_sandbox_profile import SandboxProfile')
anchor="        PublisherBootstrap(self.directory).prepare(runtime.get('publisher'))"
replace(a,anchor,anchor+"\n        SandboxProfile(self.directory).prepare(runtime.get('sandbox_policy'))")
replace(a,"        if result.returncode and not allow_failure:","        SandboxProfile(self.directory).capture()\n        if result.returncode and not allow_failure:")
replace(a,"        try:\n            self._openclaw(runtime,['plugins','install'", "        try:\n            SandboxProfile(self.directory).apply(runtime.get('sandbox_policy'))\n            self._openclaw(runtime,['plugins','install'")
replace(a,"        finally:\n            if restart:self._start_gateway()", "            SandboxProfile(self.directory).rollback()\n        except Exception:\n            raise\n        else:\n            if restart:self._start_gateway()")
replace(a,"        self._stop_gateway()\n        try:\n            if self._plugin_present(runtime):", "        SandboxProfile(self.directory).rollback_check()\n        self._stop_gateway()\n        try:\n            if self._plugin_present(runtime):")
replace(a,"        PublisherBootstrap(self.directory).rollback_rows()", "        PublisherBootstrap(self.directory).rollback_rows()\n        SandboxProfile(self.directory).rollback_check()")
replace(b,"{'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher'})", "{'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher'},\n                                    {'release_directory','provisioning','services','prerequisites','plugin','bootstrap','publisher','sandbox_policy'})")
replace(b,"    plugin=runtime['plugin']", "    if 'sandbox_policy' in runtime:\n        value=runtime['sandbox_policy']\n        if (not isinstance(value,dict) or set(value)!={'path','sha256','original_sha256'}\n                or not isinstance(value['path'],str) or not value['path'].startswith('/var/lib/xuanjun-p2-preparation/')\n                or any(not isinstance(value[k],str) or re.fullmatch(r'[0-9a-f]{64}',value[k]) is None for k in ('sha256','original_sha256'))):\n            raise ValueError('INVALID_SANDBOX_POLICY_REFERENCE')\n    plugin=runtime['plugin']")
rel='stage1/p2_sandbox_profile.py'
if (r/rel).exists():raise ValueError('SANDBOX_MODULE_PRESENT')
texts[rel]=(here/'p2_sandbox_profile.py').read_text()
for rel,text in texts.items():(r/rel).write_text(text);m['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');print('SANDBOX_PROFILE_APPLY_CAPTURE_RESTORE_HOOKS=PASS; INSTALL=NO')

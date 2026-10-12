from __future__ import print_function
import hashlib,json,pathlib,sys

def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:
        raise ValueError('C2_SOURCE_DRIFT:%s:%s'%(path.name,old[:48]))
    path.write_text(text.replace(old,new))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source=pathlib.Path(sys.argv[1]).resolve()
    stage1=source/'stage1';deploy=source/'deploy'
    binding=deploy/'p2-native-controller.binding.json.template'
    binding.write_text("""{
  "agentIds":{"workspace-write":"developer","read-only":"platform-engineer"},
  "engine":{"backend":"docker","binary":"/usr/bin/docker"},
  "ledger":{"python":"/usr/libexec/platform-python3.6","pythonSha256":"@@PYTHON_SHA256@@","bridge":"@@LEDGER_BRIDGE_PATH@@","config":"@@LEDGER_BRIDGE_CONFIG_PATH@@","files":{"@@LEDGER_BRIDGE_PATH@@":"@@LEDGER_BRIDGE_SHA256@@","@@LEDGER_BRIDGE_CONFIG_PATH@@":"@@LEDGER_BRIDGE_CONFIG_SHA256@@"}},
  "workspaceRoot":"@@WORKSPACE_ROOT@@",
  "contextPath":"@@SANDBOX_CONTEXT_PATH@@",
  "contextFiles":{
    "@@SANDBOX_CONTEXT_PATH@@":{"sha256":"@@SANDBOX_CONTEXT_SHA256@@","uid":1002},
    "@@SANDBOX_PREPARE_PATH@@":{"sha256":"@@SANDBOX_PREPARE_SHA256@@","uid":1002},
    "@@SUBAGENT_RUNTIME_PATH@@":{"sha256":"@@SUBAGENT_RUNTIME_SHA256@@","uid":1002},
    "@@BEFORE_TOOL_HOOK_PATH@@":{"sha256":"@@BEFORE_TOOL_HOOK_SHA256@@","uid":1002},
    "@@REQUEST_SCOPED_ERROR_PATH@@":{"sha256":"@@REQUEST_SCOPED_ERROR_SHA256@@","uid":1002}
  }
}
""")
    ledger_client=deploy/'p2-native-ledger-client.json.template'
    ledger_client.write_text("""{"socket_path":"/run/xuanjun-development/ledger.sock","server_uid":@@LEDGER_SERVER_UID@@}
""")
    dropin=deploy/'xuanjun-uk-openclaw-p2-docker.conf'
    dropin.write_text("""[Service]
# P2 grants Docker socket group access only to the Gateway service.
# xuanjun_dev is intentionally NOT added to the global docker supplementary group.
SupplementaryGroups=docker
""")
    entry=stage1/'p2_install_entrypoint.py'
    replace_once(entry,
"""    for name, expected_mode in (('auth', 'EXISTING_OAUTH_REFERENCE'),
                                ('tls', 'EXISTING_TLS_REFERENCE')):
        value = plan[name]
        if (not isinstance(value, dict)
                or set(value) != {'mode', 'references'}
                or value.get('mode') != expected_mode
                or not isinstance(value.get('references'), list)
                or not value['references']):
            raise ValueError('INVALID_' + name.upper() + '_REFERENCE_BINDING')
        seen = set()
        for reference in value['references']:
            if (not isinstance(reference, dict)
                    or set(reference) != {'path', 'sha256', 'owner_uid', 'mode'}
                    or not _canonical(reference.get('path'))
                    or reference['path'] in seen
                    or not SHA256.fullmatch(reference.get('sha256', ''))
                    or type(reference.get('owner_uid')) is not int
                    or type(reference.get('mode')) is not int
                    or reference['mode'] & 0o077):
                raise ValueError('INVALID_' + name.upper() + '_REFERENCE')
            seen.add(reference['path'])

    runtime = plan['runtime']
""",
"""    auth = plan['auth']
    if (not isinstance(auth, dict)
            or set(auth) != {'mode', 'references'}
            or auth.get('mode') != 'EXISTING_OAUTH_REFERENCE'
            or not isinstance(auth.get('references'), list)
            or not auth['references']):
        raise ValueError('INVALID_AUTH_REFERENCE_BINDING')
    seen = set()
    for reference in auth['references']:
        if (not isinstance(reference, dict)
                or set(reference) != {'path', 'sha256', 'owner_uid', 'mode'}
                or not _canonical(reference.get('path'))
                or reference['path'] in seen
                or not SHA256.fullmatch(reference.get('sha256', ''))
                or type(reference.get('owner_uid')) is not int
                or type(reference.get('mode')) is not int
                or reference['mode'] & 0o077):
            raise ValueError('INVALID_AUTH_REFERENCE')
        seen.add(reference['path'])

    runtime = plan['runtime']
""")
    replace_once(entry,
"""    if (not isinstance(runtime, dict)
            or set(runtime) != {'release_directory', 'provisioning', 'services', 'prerequisites'}
            or not isinstance(runtime.get('prerequisites'), dict)""",
"""    if (not isinstance(runtime, dict)
            or set(runtime) != {'release_directory', 'provisioning', 'services', 'prerequisites', 'plugin'}
            or not isinstance(runtime.get('prerequisites'), dict)""")
    replace_once(entry,
"""            or not isinstance(runtime.get('services'), list)
            or not runtime['services']):
        raise ValueError('INVALID_RUNTIME_BINDING')
    return True""",
"""            or not isinstance(runtime.get('services'), list)
            or not runtime['services']):
        raise ValueError('INVALID_RUNTIME_BINDING')
    plugin=runtime['plugin']
    plugin_keys={'id','source','binding_file','binding_sha256','ledger_client_config',
                 'ledger_client_sha256','gateway_service','openclaw_bin','service_user',
                 'docker_dropin'}
    if (not isinstance(plugin,dict) or set(plugin)!=plugin_keys
            or plugin.get('id')!='xuanjun-p2-native-controller'
            or plugin.get('source')!='plugins/p2-native-controller'
            or plugin.get('binding_file')!='/etc/xuanjun-development/p2-native-controller.binding.json'
            or not SHA256.fullmatch(plugin.get('binding_sha256',''))
            or plugin.get('ledger_client_config')!='/etc/xuanjun-development/p2-native-ledger-client.json'
            or not SHA256.fullmatch(plugin.get('ledger_client_sha256',''))
            or plugin.get('gateway_service')!='xuanjun-uk-openclaw.service'
            or plugin.get('openclaw_bin')!='/home/xuanjun_dev/.openclaw/bin/openclaw'
            or plugin.get('service_user')!='xuanjun_dev'
            or plugin.get('docker_dropin')!='/etc/systemd/system/xuanjun-uk-openclaw.service.d/20-p2-docker.conf'):
        raise ValueError('INVALID_P2_PLUGIN_BINDING')
    tls=plan['tls']
    nginx_required=any(isinstance(x,dict)
                       and isinstance(x.get('target'),str)
                       and x['target'].startswith('/etc/nginx/')
                       for x in runtime['provisioning'])
    expected_tls_mode='EXISTING_TLS_REFERENCE' if nginx_required else 'NOT_APPLICABLE_NO_NGINX'
    if (not isinstance(tls,dict) or set(tls)!={'mode','references'}
            or tls.get('mode')!=expected_tls_mode
            or not isinstance(tls.get('references'),list)
            or (nginx_required and not tls['references'])
            or (not nginx_required and tls['references'])):
        raise ValueError('INVALID_TLS_REFERENCE_BINDING')
    seen=set()
    for reference in tls['references']:
        if (not isinstance(reference,dict)
                or set(reference)!={'path','sha256','owner_uid','mode'}
                or not _canonical(reference.get('path'))
                or reference['path'] in seen
                or not SHA256.fullmatch(reference.get('sha256',''))
                or type(reference.get('owner_uid')) is not int
                or type(reference.get('mode')) is not int
                or reference['mode'] & 0o077):
            raise ValueError('INVALID_TLS_REFERENCE')
        seen.add(reference['path'])
    return True""")
    runtime=stage1/'p2_fixed_host_runtime.py'
    replace_once(runtime,
"""ALLOWED_TARGET_PREFIXES = (
    '/etc/xuanjun-development/',
    '/etc/systemd/system/',
    '/etc/nginx/conf.d/',
)
""",
"""ALLOWED_TARGET_PREFIXES = (
    '/etc/xuanjun-development/',
    '/etc/systemd/system/',
    '/etc/nginx/conf.d/',
)
GATEWAY_SERVICE='xuanjun-uk-openclaw.service'
P2_PLUGIN_ID='xuanjun-p2-native-controller'
P2_PLUGIN_CONFIG_PATH='plugins.entries.xuanjun-p2-native-controller.config'
""")
    replace_once(runtime,
"""    def _command(self, command):
        result = self.run(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('RUNTIME_COMMAND_FAILED')
""",
"""    def _command(self, command):
        result = self.run(command, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=45, check=False)
        if result.returncode:
            raise RuntimeError('RUNTIME_COMMAND_FAILED')

    def _openclaw(self,runtime,args,allow_failure=False,capture=False):
        plugin=runtime['plugin']
        command=['/usr/sbin/runuser','--user',plugin['service_user'],'--',
                 plugin['openclaw_bin']]+list(args)
        result=self.run(command,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
                        env={'HOME':'/home/xuanjun_dev','PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
                        timeout=60,check=False)
        if result.returncode and not allow_failure:
            raise RuntimeError('OPENCLAW_PLUGIN_COMMAND_FAILED')
        return result

    @staticmethod
    def _json_has_plugin(value,plugin_id):
        if isinstance(value,dict):
            if value.get('id')==plugin_id or value.get('pluginId')==plugin_id:return True
            return any(FixedHostRuntime._json_has_plugin(v,plugin_id) for v in value.values())
        if isinstance(value,list):
            return any(FixedHostRuntime._json_has_plugin(v,plugin_id) for v in value)
        return False

    def _plugin_present(self,runtime):
        result=self._openclaw(runtime,['plugins','list','--json'],capture=True)
        try:value=json.loads(result.stdout.decode('utf-8'))
        except Exception:raise ValueError('OPENCLAW_PLUGIN_INVENTORY_INVALID')
        return self._json_has_plugin(value,P2_PLUGIN_ID)

    def _stop_gateway(self):
        self._command(['/usr/bin/systemctl','stop',GATEWAY_SERVICE])
        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode==0:raise RuntimeError('GATEWAY_STOP_UNCONFIRMED')

    def _start_gateway(self):
        self._command(['/usr/bin/systemctl','start',GATEWAY_SERVICE])
        self._command(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE])

    def _install_plugin(self,release,runtime):
        plugin=runtime['plugin'];source=os.path.realpath(os.path.join(release,plugin['source']))
        if not source.startswith(release+'/') or not os.path.isdir(source):
            raise ValueError('P2_PLUGIN_SOURCE_REQUIRED')
        if self._plugin_present(runtime):raise ValueError('P2_PLUGIN_ALREADY_PRESENT')
        self._stop_gateway()
        try:
            self._openclaw(runtime,['plugins','install',source,'--force','--no-enable','--accept-capabilities'])
            config=json.dumps({'bindingFile':plugin['binding_file'],'bindingSha256':plugin['binding_sha256']},
                              sort_keys=True,separators=(',',':'))
            self._openclaw(runtime,['config','set',P2_PLUGIN_CONFIG_PATH,config,'--strict-json'])
            self._openclaw(runtime,['plugins','enable',P2_PLUGIN_ID,'--accept-capabilities'])
            self._openclaw(runtime,['config','validate','--json'])
            self._start_gateway()
            inspected=self._openclaw(runtime,['plugins','inspect',P2_PLUGIN_ID,'--runtime','--json'],capture=True)
            value=json.loads(inspected.stdout.decode('utf-8','replace'))
            packed=json.dumps(value,sort_keys=True,separators=(',',':'))
            if (not self._json_has_plugin(value,P2_PLUGIN_ID)
                    or 'xuanjun.execution.start' not in packed
                    or 'xuanjun.execution.inspect' not in packed):
                raise ValueError('P2_PLUGIN_RUNTIME_REGISTRATION_UNPROVEN')
        except Exception:
            try:self._rollback_plugin(runtime,restart=True)
            except Exception:pass
            raise

    def _rollback_plugin(self,runtime,restart):
        self._stop_gateway()
        try:
            if self._plugin_present(runtime):
                self._openclaw(runtime,['plugins','uninstall',P2_PLUGIN_ID,'--force'])
            self._openclaw(runtime,['config','unset',P2_PLUGIN_CONFIG_PATH],allow_failure=True)
            self._openclaw(runtime,['config','unset','plugins.entries.'+P2_PLUGIN_ID],allow_failure=True)
            self._openclaw(runtime,['config','validate','--json'])
        finally:
            if restart:self._start_gateway()
""")
    replace_once(runtime,
"""        self.prerequisites.preflight(runtime['prerequisites'])
        for reference in auth['references'] + tls['references']:
            self._reference(reference)
""",
"""        self.prerequisites.preflight(runtime['prerequisites'])
        plugin=runtime['plugin']
        if plugin['gateway_service']!=GATEWAY_SERVICE or plugin['id']!=P2_PLUGIN_ID:
            raise ValueError('P2_PLUGIN_POLICY')
        matches=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['binding_file']]
        clients=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['ledger_client_config']]
        dropins=[binding for binding in runtime['provisioning'] if binding.get('target')==plugin['docker_dropin']]
        if (len(matches)!=1 or matches[0].get('rendered_sha256')!=plugin['binding_sha256']
                or len(clients)!=1 or clients[0].get('rendered_sha256')!=plugin['ledger_client_sha256']
                or len(dropins)!=1):
            raise ValueError('P2_PLUGIN_PROVISIONING_BINDING')
        result=self.run(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=False)
        if result.returncode!=0:raise ValueError('GATEWAY_MUST_BE_ACTIVE_BEFORE_P2')
        if self._plugin_present(runtime):raise ValueError('P2_PLUGIN_ALREADY_PRESENT')
        for reference in auth['references'] + tls['references']:
            self._reference(reference)
""")
    replace_once(runtime,
"""        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True,
                   'prerequisites': runtime['prerequisites']}
""",
"""        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True,
                   'prerequisites': runtime['prerequisites'],
                   'plugin': {'id': P2_PLUGIN_ID, 'previous': 'ABSENT',
                              'gateway_service': GATEWAY_SERVICE}}
""")
    replace_once(runtime,
"""            self._command(['/usr/bin/systemctl', 'daemon-reload'])
            if any(item['target'].startswith('/etc/nginx/') for item in prepared):
                self._command(['/usr/sbin/nginx', '-t'])
            return reference
""",
"""            self._command(['/usr/bin/systemctl', 'daemon-reload'])
            if any(item['target'].startswith('/etc/nginx/') for item in prepared):
                self._command(['/usr/sbin/nginx', '-t'])
            self._install_plugin(release,runtime)
            return reference
""")
    replace_once(runtime,
"""        # Validate every backup and current target before any rollback effect.
        # A failed provision may leave either old or installed bytes in place.
        prepared = []
""",
"""        if receipt.get('plugin')!={'id':P2_PLUGIN_ID,'previous':'ABSENT',
                                   'gateway_service':GATEWAY_SERVICE}:
            raise ValueError('P2_PLUGIN_ROLLBACK_RECEIPT_MISMATCH')
        # Validate every backup and current target before any rollback effect.
        # A failed provision may leave either old or installed bytes in place.
        prepared = []
""")
    replace_once(runtime,
"""        self._command(['/usr/bin/systemctl', 'daemon-reload'])
        if any(item['target'].startswith('/etc/nginx/')
               for item in receipt['targets']):
            self._command(['/usr/sbin/nginx', '-t'])
            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])
        return {'restored': True, 'services_restarted': False}
""",
"""        self._command(['/usr/bin/systemctl', 'daemon-reload'])
        if any(item['target'].startswith('/etc/nginx/')
               for item in receipt['targets']):
            self._command(['/usr/sbin/nginx', '-t'])
            self._command(['/usr/bin/systemctl', 'reload', 'nginx.service'])
        self._start_gateway()
        return {'restored': True, 'services_restarted': False}
""")
    replace_once(runtime,
"""    def stop_new(self, runtime):
        self._authority()
        for service in STOP_SERVICES:
            self._command(['/usr/bin/systemctl', 'stop', service])
        return True
""",
"""    def stop_new(self, runtime):
        self._authority()
        for service in STOP_SERVICES:
            self._command(['/usr/bin/systemctl', 'stop', service])
        self._stop_gateway()
        return True
""")
    replace_once(runtime,
"""GATEWAY_SERVICE='xuanjun-uk-openclaw.service'
P2_PLUGIN_ID='xuanjun-p2-native-controller'
P2_PLUGIN_CONFIG_PATH='plugins.entries.xuanjun-p2-native-controller.config'
""",
"""GATEWAY_SERVICE='xuanjun-uk-openclaw.service'
GATEWAY_DROPIN_DIR='/etc/systemd/system/xuanjun-uk-openclaw.service.d'
P2_PLUGIN_ID='xuanjun-p2-native-controller'
P2_PLUGIN_CONFIG_PATH='plugins.entries.xuanjun-p2-native-controller.config'
""")
    replace_once(runtime,
"""    def _start_gateway(self):
        self._command(['/usr/bin/systemctl','start',GATEWAY_SERVICE])
        self._command(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE])

    def _install_plugin(self,release,runtime):
""",
"""    def _start_gateway(self):
        self._command(['/usr/bin/systemctl','start',GATEWAY_SERVICE])
        self._command(['/usr/bin/systemctl','is-active','--quiet',GATEWAY_SERVICE])

    @staticmethod
    def _dropin_parent_state():
        if os.path.lexists(GATEWAY_DROPIN_DIR):
            info=os.lstat(GATEWAY_DROPIN_DIR)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                    or stat.S_IMODE(info.st_mode)!=0o755):
                raise ValueError('UNSAFE_GATEWAY_DROPIN_DIRECTORY')
            return False
        return True

    @staticmethod
    def _create_dropin_parent():
        parent=os.path.dirname(GATEWAY_DROPIN_DIR)
        info=os.lstat(parent)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                or info.st_mode&0o022):
            raise ValueError('UNSAFE_SYSTEMD_DIRECTORY')
        os.mkdir(GATEWAY_DROPIN_DIR,0o755)
        os.chown(GATEWAY_DROPIN_DIR,0,0)
        os.chmod(GATEWAY_DROPIN_DIR,0o755)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    @staticmethod
    def _remove_created_dropin_parent():
        if not os.path.lexists(GATEWAY_DROPIN_DIR):return
        info=os.lstat(GATEWAY_DROPIN_DIR)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_gid!=0
                or stat.S_IMODE(info.st_mode)!=0o755 or os.listdir(GATEWAY_DROPIN_DIR)):
            raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED')
        os.rmdir(GATEWAY_DROPIN_DIR)
        parent=os.path.dirname(GATEWAY_DROPIN_DIR)
        fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)

    def _install_plugin(self,release,runtime):
""")
    replace_once(runtime,
"""        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True,
                   'prerequisites': runtime['prerequisites'],
                   'plugin': {'id': P2_PLUGIN_ID, 'previous': 'ABSENT',
                              'gateway_service': GATEWAY_SERVICE}}
""",
"""        create_dropin_parent=self._dropin_parent_state()
        receipt = {'schema': 1, 'targets': [dict(item, data=None) for item in prepared],
                   'services': list(ALLOWED_SERVICES), 'rollback_complete': True,
                   'prerequisites': runtime['prerequisites'],
                   'plugin': {'id': P2_PLUGIN_ID, 'previous': 'ABSENT',
                              'gateway_service': GATEWAY_SERVICE,
                              'dropin_parent_created': create_dropin_parent}}
""")
    replace_once(runtime,
"""            self.prerequisites.apply(runtime['prerequisites'])
            for item in prepared:
                self._atomic_target(item['target'], item['data'], item['mode'],
                                    item['uid'], item['gid'])
""",
"""            self.prerequisites.apply(runtime['prerequisites'])
            if create_dropin_parent:self._create_dropin_parent()
            for item in prepared:
                self._atomic_target(item['target'], item['data'], item['mode'],
                                    item['uid'], item['gid'])
""")
    replace_once(runtime,
"""        if receipt.get('plugin')!={'id':P2_PLUGIN_ID,'previous':'ABSENT',
                                   'gateway_service':GATEWAY_SERVICE}:
            raise ValueError('P2_PLUGIN_ROLLBACK_RECEIPT_MISMATCH')
""",
"""        plugin_receipt=receipt.get('plugin')
        if (not isinstance(plugin_receipt,dict)
                or set(plugin_receipt)!={'id','previous','gateway_service','dropin_parent_created'}
                or plugin_receipt.get('id')!=P2_PLUGIN_ID
                or plugin_receipt.get('previous')!='ABSENT'
                or plugin_receipt.get('gateway_service')!=GATEWAY_SERVICE
                or type(plugin_receipt.get('dropin_parent_created')) is not bool):
            raise ValueError('P2_PLUGIN_ROLLBACK_RECEIPT_MISMATCH')
""")
    replace_once(runtime,
"""            prepared.append((item, old))
        for item, old in prepared:
""",
"""            prepared.append((item, old))
        if plugin_receipt['dropin_parent_created']:
            if not os.path.lexists(GATEWAY_DROPIN_DIR):
                raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_MISSING')
            dropin_parent=os.lstat(GATEWAY_DROPIN_DIR)
            if (not stat.S_ISDIR(dropin_parent.st_mode) or dropin_parent.st_uid!=0
                    or dropin_parent.st_gid!=0 or stat.S_IMODE(dropin_parent.st_mode)!=0o755):
                raise ValueError('HOLD_GATEWAY_DROPIN_DIRECTORY_CHANGED')
        # All receipt, backup, target and service-drop-in evidence has passed.
        # External rollback effects may start only after this point.
        self._rollback_plugin({'plugin': {'id':P2_PLUGIN_ID,'service_user':'xuanjun_dev',
            'openclaw_bin':'/home/xuanjun_dev/.openclaw/bin/openclaw'}},restart=False)
        for item, old in prepared:
""")
    replace_once(runtime,
"""        self.prerequisites.rollback(receipt['prerequisites'])
        self._command(['/usr/bin/systemctl', 'daemon-reload'])
""",
"""        if plugin_receipt['dropin_parent_created']:
            self._remove_created_dropin_parent()
        self.prerequisites.rollback(receipt['prerequisites'])
        self._command(['/usr/bin/systemctl', 'daemon-reload'])
""")
    installer=source/'scripts'/'uk-integration-install.py'
    replace_once(installer,
"""    required={'schema','source_repository','source_commit','source_tree',
              'runtime_manifest_path','runtime_manifest_sha256','runtime_files',
              'verifier_path','verifier_sha256','oauth_content_included',
              'tls_private_key_included','new_paid_api_usage'}
""",
"""    required={'schema','source_repository','source_commit','source_tree',
              'runtime_manifest_path','runtime_manifest_sha256','runtime_files',
              'verifier_path','verifier_sha256','oauth_content_included',
              'tls_private_key_included','new_paid_api_usage','operations','rollback_map'}
""")
    replace_once(installer,
"""    if (not isinstance(value,dict) or set(value)!=required
            or value.get('schema')!=1
            or value.get('source_repository')!='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
""",
"""    expected_operations={
        'verify_only':['scripts/uk-p2-install.py','--operation','verify-only'],
        'install':['scripts/uk-p2-install.py','--operation','install'],
        'rollback':['scripts/uk-p2-install.py','--operation','rollback']}
    expected_rollback=[
        'ACTIVATION_FENCED_EPOCH','NEW_RUNTIME_STOPPED','PROVISIONING_RESTORED',
        'LEGACY_FILES_RESTORED_NOT_RESTARTED',
        'RECONCILE_DATABASE_AND_EPOCH_BEFORE_ANY_RESTART']
    if (not isinstance(value,dict) or set(value)!=required
            or value.get('schema')!=2
            or value.get('source_repository')!='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
""")
    replace_once(installer,
"""            or value.get('new_paid_api_usage')!='NONE'
            or not isinstance(verifier,str) or verifier.startswith('/')
""",
"""            or value.get('new_paid_api_usage')!='NONE'
            or value.get('operations')!=expected_operations
            or value.get('rollback_map')!=expected_rollback
            or not isinstance(verifier,str) or verifier.startswith('/')
""")
    manifest=deploy/'integration-manifest.json';value=json.loads(manifest.read_text());files=value['files']
    authorized=set(files)
    c2_paths=[entry,runtime,installer,binding,ledger_client,dropin]
    for name in ('native_pipeline_runtime.py','native_gateway_controller.py',
                 'native_github_notifier.py','native_ledger_bridge.py',
                 'native_ledger_operations.py','native_peer_identity.py',
                 'task_supervisor_inventory_adapter.py'):
        path=stage1/name
        if not path.is_file():
            raise ValueError('P2_NATIVE_RUNTIME_FILE_MISSING:'+name)
        c2_paths.append(path)
    plugin=source/'plugins'/'p2-native-controller'
    c2_paths.extend(path for path in sorted(plugin.iterdir()) if path.is_file())
    for item in c2_paths:
        relative=item.relative_to(source).as_posix()
        if relative not in files:
            files[relative]=sha(item)
            authorized.add(relative)
    # All prior changes came from the pinned old artifact + fuzz=0 native patch +
    # exact follow-up/C2 replacements. Rebind every already-authorized runtime
    # path to its final bytes; never discover or admit unrelated files here.
    for relative in sorted(authorized):
        item=source/relative
        if not item.is_file() or item.is_symlink():
            raise ValueError('C2_MANIFEST_FILE_MISSING_OR_UNSAFE:'+relative)
        files[relative]=sha(item)
    manifest.write_text(json.dumps(value,sort_keys=True,indent=2,separators=(',', ': '))+'\n')
    print('P2_C2_INSTALL_OVERLAY_APPLIED')

if __name__=='__main__':main()

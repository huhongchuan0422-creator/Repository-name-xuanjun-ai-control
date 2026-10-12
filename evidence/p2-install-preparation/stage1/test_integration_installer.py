import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch


PATH=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','scripts','uk-integration-install.py'))
spec=importlib.util.spec_from_file_location('integration_installer',PATH)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)


class InstallerRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.dirname(PATH)))
        self.addCleanup(self.temp.cleanup)

    @staticmethod
    def write(path,data):
        with open(path,'wb') as stream: stream.write(data)

    def assert_release_error(self,path,expected):
        with self.assertRaises(ValueError) as caught:
            module.open_safe_release_root(path,os.geteuid())
        self.assertEqual(str(caught.exception),expected)
        self.assertEqual(str(caught.exception).split(),[expected])

    @staticmethod
    def render_contract():
        allowed={name:[] for name in module.IDENTITY_RENDERED_FILES}
        allowed['deploy/dispatcher.example.json']=[
            '@@GENERATION@@','@@INSTANCE_UUID@@','@@LEDGER_UUID@@','@@SOURCE_COMMIT@@']
        renderer_sha='a'*64
        target='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/'+module.REQUIRED_RENDERER
        return {
            'files':{module.REQUIRED_RENDERER:renderer_sha},
            'rendering':{'identity_files':list(module.IDENTITY_RENDERED_FILES),
                         'allowed_remaining_placeholders':allowed},
            'required_renderers':[{'path':module.REQUIRED_RENDERER,
                                   'sha256':renderer_sha,'target':target,
                                   'owner':'root','group':'root','mode':'0555',
                                   'invocation':[target,'--owner-host','<fqdn>',
                                                 '--tls-cert','<absolute-path>',
                                                 '--tls-key','<absolute-path>','--verify-files']}]
        }

    def test_manifest_hash_and_parse_use_same_open_descriptor(self):
        root=os.path.realpath(os.path.join(self.temp.name,'root')); os.mkdir(root)
        artifact=os.path.join(root,'artifact'); self.write(artifact,b'approved')
        value={'schema':1,'source_commit':'8'*40,'files':{
            'artifact':hashlib.sha256(b'approved').hexdigest()}}
        manifest=os.path.realpath(os.path.join(self.temp.name,'manifest.json'))
        data=json.dumps(value).encode(); self.write(manifest,data)
        replacement=os.path.join(self.temp.name,'replacement'); self.write(replacement,b'{"schema":999}')
        original=module.os.open; replaced=[False]
        def racing_open(path,flags,*args):
            fd=original(path,flags,*args)
            if path==manifest and not replaced[0]:
                replaced[0]=True; os.replace(replacement,manifest)
            return fd
        with patch.object(module.os,'open',side_effect=racing_open):
            observed,_=module.verify(root,manifest,'8'*40,hashlib.sha256(data).hexdigest())
        self.assertEqual(observed['schema'],1)

    def test_source_copy_uses_verified_open_descriptor(self):
        source=os.path.join(self.temp.name,'source'); destination=os.path.join(self.temp.name,'dest')
        approved=b'approved bytes'; self.write(source,approved)
        replacement=os.path.join(self.temp.name,'replacement'); self.write(replacement,b'tampered')
        original=module.os.open; replaced=[False]
        def racing_open(path,flags,*args):
            fd=original(path,flags,*args)
            if path==source and not replaced[0]:
                replaced[0]=True; os.replace(replacement,source)
            return fd
        with patch.object(module.os,'open',side_effect=racing_open):
            module.copy_verified(source,destination,hashlib.sha256(approved).hexdigest())
        with open(destination,'rb') as stream: self.assertEqual(stream.read(),approved)

    def test_release_root_classifies_direct_and_parent_symlinks_exactly(self):
        safe=os.path.join(self.temp.name,'safe'); os.mkdir(safe,0o700)
        actual=os.path.join(safe,'actual'); os.mkdir(actual,0o700)
        linked=os.path.join(safe,'linked'); os.symlink(actual,linked)
        self.assert_release_error(linked,'SYMLINKED')
        self.assert_release_error(os.path.join(linked,'releases'),'SYMLINKED')

    def test_release_root_non_directory_is_not_misclassified_as_symlink(self):
        safe=os.path.join(self.temp.name,'safe'); os.mkdir(safe,0o700)
        regular=os.path.join(safe,'regular'); self.write(regular,b'not a directory')
        self.assert_release_error(regular,'UNSAFE_RELEASE_ROOT')

    def test_release_root_preserves_exact_writable_classifications(self):
        safe=os.path.join(self.temp.name,'safe'); os.mkdir(safe,0o700)
        unsafe=os.path.join(safe,'unsafe'); os.mkdir(unsafe,0o777)
        os.chmod(unsafe,0o777)
        self.assert_release_error(unsafe,'UNSAFE_RELEASE_ROOT')
        self.assert_release_error(os.path.join(unsafe,'releases'),
                                  'UNSAFE_RELEASE_ANCESTRY')

    def test_release_root_probe_is_repeatable_for_safe_and_symlink_paths(self):
        safe=os.path.join(self.temp.name,'safe'); os.mkdir(safe,0o700)
        actual=os.path.join(safe,'actual'); os.mkdir(actual,0o700)
        linked=os.path.join(safe,'install'); os.symlink(actual,linked)
        for unused in range(2):
            descriptor=module.open_safe_release_root(actual,os.geteuid())
            os.close(descriptor)
            self.assert_release_error(linked,'SYMLINKED')

    def test_release_directory_and_full_artifact_are_distinct_typed_values(self):
        artifact='a'*64
        directory=module.release_identity(artifact)
        self.assertEqual(directory,'integration-'+'a'*16)
        self.assertNotEqual(directory,artifact)
        self.assertRegex(artifact,r'^[0-9a-f]{64}$')
        self.assertRegex(directory,r'^integration-[0-9a-f]{16}$')
        for invalid in (directory,'a'*16,'A'*64):
            with self.assertRaisesRegex(ValueError,'INVALID_ARTIFACT_SHA256'):
                module.release_identity(invalid)

    def test_identity_render_is_deterministic_and_preserves_only_allowlisted_runtime_tokens(self):
        manifest=self.render_contract(); artifact='b'*64
        source=(b'{"path":"/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/x",'
                b'"release_sha256":"@@ARTIFACT_SHA256@@",'
                b'"generation":"@@GENERATION@@"}')
        first=module.render_identity_bytes('deploy/dispatcher.example.json',source,artifact,manifest)
        second=module.render_identity_bytes('deploy/dispatcher.example.json',source,artifact,manifest)
        self.assertEqual(first,second)
        self.assertIn(module.release_identity(artifact).encode(),first)
        self.assertIn(artifact.encode(),first)
        self.assertNotIn(b'@@RELEASE_DIRECTORY@@',first)
        self.assertNotIn(b'@@ARTIFACT_SHA256@@',first)
        self.assertIn(b'@@GENERATION@@',first)

    def test_render_contract_rejects_unknown_unresolved_duplicate_and_bad_renderer(self):
        manifest=self.render_contract()
        module._validate_install_contract(manifest)
        with self.assertRaisesRegex(ValueError,'UNKNOWN_PLACEHOLDER'):
            module.render_identity_bytes('deploy/dispatcher.example.json',b'@@SURPRISE@@','c'*64,manifest)
        broken=json.loads(json.dumps(manifest))
        broken['rendering']['allowed_remaining_placeholders']['deploy/dispatcher.example.json'].append('@@GENERATION@@')
        with self.assertRaisesRegex(ValueError,'INVALID_PLACEHOLDER_ALLOWLIST'):
            module._validate_install_contract(broken)
        for mutation in ('missing','altered','wrong-mode','extra'):
            broken=json.loads(json.dumps(manifest))
            if mutation=='missing': broken['required_renderers']=[]
            if mutation=='altered': broken['required_renderers'][0]['sha256']='d'*64
            if mutation=='wrong-mode': broken['required_renderers'][0]['mode']='0755'
            if mutation=='extra': broken['required_renderers'].append(dict(broken['required_renderers'][0]))
            with self.assertRaisesRegex(ValueError,'INVALID_REQUIRED_RENDERER'):
                module._validate_install_contract(broken)

    def test_installed_renderer_wrong_mode_is_rejected(self):
        artifact='a'*64; directory=module.release_identity(artifact)
        root=os.path.join(self.temp.name,'staging'); os.mkdir(root)
        files={}; rendered={}
        for name in module.IDENTITY_RENDERED_FILES:
            path=os.path.join(root,name); os.makedirs(os.path.dirname(path),exist_ok=True)
            if name=='deploy/dispatcher.example.json':
                data=json.dumps({'release_sha256':artifact,
                                 'broker_client':'/opt/xuanjun-control-releases/'+directory+'/scripts/xj-root-broker-client'}).encode()
            else:
                data=('/opt/xuanjun-control-releases/'+directory+'/stage1/app.py').encode()
            self.write(path,data); files[name]=hashlib.sha256(data).hexdigest(); rendered[name]=files[name]
        renderer=os.path.join(root,module.REQUIRED_RENDERER)
        os.makedirs(os.path.dirname(renderer),exist_ok=True); self.write(renderer,b'renderer')
        os.chmod(renderer,0o555); renderer_sha=hashlib.sha256(b'renderer').hexdigest()
        files[module.REQUIRED_RENDERER]=renderer_sha; rendered[module.REQUIRED_RENDERER]=renderer_sha
        target='/opt/xuanjun-control-releases/@@RELEASE_DIRECTORY@@/'+module.REQUIRED_RENDERER
        manifest={'files':files,'required_renderers':[{'path':module.REQUIRED_RENDERER,
                  'sha256':renderer_sha,'target':target,'mode':'0555',
                  'invocation':[target]}]}
        module.verify_rendered_release(root,manifest,artifact,rendered)
        os.chmod(renderer,0o444)
        with self.assertRaisesRegex(ValueError,'REQUIRED_RENDERER_INSTALL_MISMATCH'):
            module.verify_rendered_release(root,manifest,artifact,rendered)

    def test_immutable_rollback_map_positive_and_negative_controls(self):
        artifact='d'*64
        target='/etc/systemd/system/xuanjun-development-dispatcher.service'
        value={'schema':2,
               'previous_release_directory':module.release_identity(artifact),
               'previous_manifest_sha256':'e'*64,
               'previous_artifact_sha256':artifact,
               'previous_epoch':6,'stopped_epoch':7,'cgroup_empty':True,
               'restoration_order':{'schema':1,'targets':[target]},
               'rendered_files':{
                   target:{
                       'sha256':'f'*64,
                       'backup_path':'/opt/xuanjun-control-releases/'+module.release_identity(artifact)+'/rollback/xuanjun-development-dispatcher.service'}}}
        self.assertTrue(module.validate_rollback_map(value,7))
        mutations=[('previous_release_directory','current'),
                   ('previous_artifact_sha256','0'*64),
                   ('stopped_epoch',6),('cgroup_empty',False)]
        for key,replacement in mutations:
            broken=json.loads(json.dumps(value)); broken[key]=replacement
            with self.assertRaises(ValueError): module.validate_rollback_map(broken,7)
        for target in ('/opt/xuanjun-control-releases/current/unit','relative/unit'):
            broken=json.loads(json.dumps(value))
            binding=next(iter(broken['rendered_files'].values()))
            broken['rendered_files']={target:binding}
            broken['restoration_order']['targets']=[target]
            with self.assertRaises(ValueError): module.validate_rollback_map(broken,7)

    def test_rollback_restoration_order_requires_exact_unique_canonical_coverage(self):
        artifact='d'*64; release=module.release_identity(artifact)
        config='/etc/xuanjun-development/dispatcher.json'
        unit='/etc/systemd/system/xuanjun-development-dispatcher.service'
        def binding(name,digest):
            return {'sha256':digest*64,
                    'backup_path':'/opt/xuanjun-control-releases/'+release+'/rollback/'+name}
        value={'schema':2,'previous_release_directory':release,
               'previous_manifest_sha256':'e'*64,
               'previous_artifact_sha256':artifact,
               'previous_epoch':6,'stopped_epoch':7,'cgroup_empty':True,
               'restoration_order':{'schema':1,'targets':[config,unit]},
               'rendered_files':{config:binding('dispatcher.json','a'),
                                 unit:binding('dispatcher.service','b')}}
        self.assertTrue(module.validate_rollback_map(value,7))

        for targets in ([config], [config,unit,config],
                        [config,unit,'/etc/unexpected']):
            broken=json.loads(json.dumps(value))
            broken['restoration_order']['targets']=targets
            with self.assertRaisesRegex(ValueError,'ROLLBACK_TARGET_SET_MISMATCH'):
                module.validate_rollback_map(broken,7)

        broken=json.loads(json.dumps(value))
        broken['rendered_files']['/etc/unexpected']=binding('unexpected','c')
        with self.assertRaisesRegex(ValueError,'ROLLBACK_TARGET_SET_MISMATCH'):
            module.validate_rollback_map(broken,7)

        for alias in ('/etc/xuanjun-development/./dispatcher.json',
                      '/etc/xuanjun-development/../xuanjun-development/dispatcher.json'):
            broken=json.loads(json.dumps(value))
            broken['rendered_files'][alias]=broken['rendered_files'].pop(config)
            broken['restoration_order']['targets'][0]=alias
            with self.assertRaisesRegex(ValueError,'INVALID_ROLLBACK_FILE_BINDING'):
                module.validate_rollback_map(broken,7)

        broken=json.loads(json.dumps(value))
        broken['rendered_files'][unit]['backup_path']=(
            '/opt/xuanjun-control-releases/'+release+'/rollback/./dispatcher.json')
        with self.assertRaisesRegex(ValueError,'INVALID_ROLLBACK_BACKUP_PATH'):
            module.validate_rollback_map(broken,7)

        broken=json.loads(json.dumps(value))
        broken['rendered_files'][unit]['backup_path']=broken['rendered_files'][config]['backup_path']
        with self.assertRaisesRegex(ValueError,'INVALID_ROLLBACK_BACKUP_PATH'):
            module.validate_rollback_map(broken,7)

    def test_rollback_restoration_executes_only_the_frozen_declared_order(self):
        artifact='d'*64; release=module.release_identity(artifact)
        first='/etc/xuanjun-development/dispatcher.json'
        second='/etc/systemd/system/xuanjun-development-dispatcher.service'
        value={'schema':2,'previous_release_directory':release,
               'previous_manifest_sha256':'e'*64,
               'previous_artifact_sha256':artifact,
               'previous_epoch':6,'stopped_epoch':7,'cgroup_empty':True,
               'restoration_order':{'schema':1,'targets':[second,first]},
               'rendered_files':{
                   first:{'sha256':'a'*64,
                          'backup_path':'/opt/xuanjun-control-releases/'+release+'/rollback/dispatcher.json'},
                   second:{'sha256':'b'*64,
                           'backup_path':'/opt/xuanjun-control-releases/'+release+'/rollback/dispatcher.service'}}}
        pristine=json.loads(json.dumps(value))
        observed=[]
        def restore(target,backup,digest):
            observed.append((target,backup,digest))
            value['restoration_order']['targets'][:]=[first]
            value['rendered_files'][first]['sha256']='c'*64
        restored=module.restore_rollback_files(value,7,restore)
        self.assertEqual(restored,(second,first))
        self.assertEqual([item[0] for item in observed],[second,first])
        self.assertEqual(observed[1][2],'a'*64)
        with self.assertRaisesRegex(ValueError,'INVALID_ROLLBACK_RESTORER'):
            module.restore_rollback_files(pristine,7,None)


if __name__=='__main__': unittest.main()

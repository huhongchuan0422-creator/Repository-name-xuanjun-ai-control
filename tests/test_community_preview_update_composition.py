"""Isolated real file projection + bounded transport frames; NEVER UK evidence."""
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import test_community_preview_upgrade as old
import test_community_preview_release_plan as fixture
from scripts import community_preview_update_composition as c


def frame(body,code=200):return json.dumps(dict(http_status=code,body_hex=json.dumps(body).encode().hex()))
def health():return dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
    runtime_source_sha=c.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=1000)


class CompositionScope(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(c.observation,'ROOT_ANCHOR',self.tmp.name).start()
        patch.object(c.observation,'ROOT_UID',os.getuid()).start()
        patch.object(c.observation,'PROJECT_UID',os.getuid()).start()
        patch.object(c,'now',return_value=1000).start()
        for path in c.observation.META_PATHS.values():
            p=self.root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
            if path in (c.plan.ROOT+'/config',c.plan.ROOT+'/data',c.plan.RUN):p.mkdir(exist_ok=True)
            else:p.write_bytes(b'PRIVATE_NOT_READ');p.chmod(0o600)
        for path in c.observation.ROUTE_PATHS.values():
            p=self.root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'route unchanged');p.chmod(0o600)
        self.backup_path='/opt/xuanjun-community-preview/existing-reviewed-reference.json'
        p=self.root/self.backup_path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'NOT_A_NEW_BACKUP');p.chmod(0o600)
        self.fd=os.open(str(p),os.O_RDONLY);self.addCleanup(os.close,self.fd)
        self.c=fixture.current();self.info=old.info(self.c['image_id'],self.c['container_id'])
        self.info.update(ports={},published={},devices=[],capadd=[])
        self.readlink=os.readlink
        patch.object(c.os,'readlink',side_effect=lambda p:self.backup_path if p=='/proc/self/fd/'+str(self.fd) else self.readlink(p)).start()
        # Duplicated reference capabilities retain same original protected path.
        self.realdup=os.dup
        def dup(fd):
            v=self.realdup(fd)
            if fd==self.fd:
                prior=c.os.readlink.side_effect
                c.os.readlink.side_effect=lambda p:self.backup_path if p=='/proc/self/fd/'+str(v) else prior(p)
            return v
        patch.object(c.os,'dup',side_effect=dup).start()
        patch.object(c,'root_host').start()
        self.checked=Mock()
        def capture(argv,**kw):
            if argv[3:5]==['container','inspect']:
                if argv[-1]==c.plan.NAME:return '\n'.join(json.dumps(self.info[k]) for k in ('id','image'))
                fields=c.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')]
                return '\n'.join(json.dumps(self.info[k]) for k,_ in fields)
            if argv[3:5]==['image','inspect']:
                return '\n'.join(json.dumps(v) for v in (self.c['image_id'],c.plan.OBSERVED_OCI,'10001:1008'))
            return frame(health())
        self.capture=patch.object(c.observation,'capture',side_effect=capture).start()
    def binding(self):
        self.c=c.observe_current(backup_fd=self.fd)
        return c.LiveBindings(self.c,self.fd,self.checked)
    def test_default_disabled_performs_zero_reads_writes_or_transport(self):
        with patch.object(c,'protected_body') as read,patch.object(c.controller.Journal,'from_original_parent') as j:
            with self.assertRaisesRegex(c.controller.Hold,'DISABLED'):c.compose(approval_sha256='a'*64,backup_fd=self.fd)
            read.assert_not_called();j.assert_not_called();self.capture.assert_not_called()
    def test_real_metadata_route_projection_and_exact_old_id_across_rename(self):
        b=self.binding();self.addCleanup(b.close)
        self.assertEqual(b(),self.c)
        self.info['running']=False;self.info['status']='exited'
        self.assertIs(b()['running'],False)
        calls=[a.args[0] for a in self.capture.call_args_list if a.args[0][3:5]==['container','inspect'] and a.args[0][-1]!=c.plan.NAME]
        self.assertTrue(all(a[-1]==self.c['container_id'] for a in calls))
        self.assertGreater(self.checked.call_count,2)
    def test_config_replacement_data_replacement_and_route_change_deny(self):
        for path in (c.plan.ROOT+'/config/host.json',c.plan.ROOT+'/data',next(iter(c.observation.ROUTE_PATHS.values()))):
            with self.subTest(path=path):
                b=self.binding()
                p=self.root/path.lstrip('/');q=p.with_name(p.name+'.retained');p.rename(q)
                if q.is_dir():p.mkdir()
                else:p.write_bytes(b'changed');p.chmod(0o600)
                try:
                    with self.assertRaises(c.controller.Hold):b()
                finally:
                    b.close()
                    if p.is_dir():p.rmdir()
                    else:p.unlink()
                    q.rename(p)
    def test_private_file_bodies_never_opened_and_directory_activity_is_not_identity(self):
        b=self.binding();self.addCleanup(b.close)
        real=c.os.open
        def opened(path,*args,**kwargs):
            self.assertNotIn(path,('host.json','center-keys.json','wechat.json'))
            return real(path,*args,**kwargs)
        (self.root/(c.plan.ROOT+'/data').lstrip('/')/'new-object').write_bytes(b'not read')
        with patch.object(c.os,'open',side_effect=opened):self.assertEqual(b(),self.c)
    def test_wrong_current_image_id_oci_or_published_port_denies(self):
        for key,value in (('image','sha256:'+'0'*64),('id','0'*64),('running',1),('ports',{'80/tcp':[{'HostPort':'8080'}]}),('capadd',['SYS_ADMIN'])):
            b=self.binding();before=self.info[key];self.info[key]=value
            try:
                with self.assertRaises(Exception):b()
            finally:self.info[key]=before;b.close()
        b=self.binding();self.addCleanup(b.close)
        self.capture.side_effect=lambda *a,**kw:'"WRONG"'
        with self.assertRaises(Exception):b()
    def test_parent_symlink_config_hardlink_and_wrong_owner_denied(self):
        b=self.binding();self.addCleanup(b.close)
        p=self.root/(c.plan.ROOT+'/config/host.json').lstrip('/');q=p.with_name('alias');os.link(str(p),str(q))
        with self.assertRaises(c.controller.Hold):b()
        q.unlink()
        d=p.parent;kept=d.with_name('config-kept');d.rename(kept);d.symlink_to(kept,target_is_directory=True)
        with self.assertRaises(Exception):b()
        d.unlink();kept.rename(d)
        with patch.object(c.observation,'ROOT_UID',99998):
            with self.assertRaises(Exception):b()
    def test_backup_missing_wrong_mode_replaced_or_body_not_read(self):
        self.assertEqual(len(c.backup_reference(self.fd)),64)
        p=self.root/self.backup_path.lstrip('/');p.chmod(0o644)
        with self.assertRaises(c.controller.Hold):c.backup_reference(self.fd)
        p.chmod(0o600);q=p.with_name('retained');p.rename(q);p.write_bytes(b'new');p.chmod(0o600)
        with self.assertRaises(c.controller.Hold):c.backup_reference(self.fd)
        with self.assertRaises(c.controller.Hold):c.backup_reference(True)
    def test_health_real_remote_times_preserved_private_public_both_required(self):
        self.capture.side_effect=[frame(health()),frame(dict(health(),observed_at=999))]
        r=c.actual_health();self.assertEqual(r['observed_at'],1000);self.assertEqual(r['runtime_source_sha'],c.PRODUCT)
        self.assertEqual(self.capture.call_args_list[-1].kwargs,dict(timeout=10,budget=10000))
        self.assertIn('/run/xuanjun-community-preview/preview.sock',c.PRIVATE_PROBE)
        self.assertNotIn('docker',c.PRIVATE_PROBE)
    def test_health_missing_stale_bool_float_future_remote_time_is_unknown(self):
        for value in (None,True,1000.0,1,1031):
            self.capture.side_effect=lambda *a,**kw:frame(dict(health(),observed_at=value))
            with self.assertRaises(c.controller.Hold):c.actual_health()
    def test_health_different_public_private_or_malformed_frames_denies(self):
        for other in (dict(health(),runtime_source_sha='0'*40),dict(health(),status='MAINTENANCE')):
            self.capture.side_effect=[frame(health()),frame(other)]
            with self.assertRaises(c.controller.Hold):c.actual_health()
        for raw in ('{}',json.dumps(dict(http_status=True,body_hex='00')),json.dumps(dict(http_status=200,body_hex=' '*2)),
                    json.dumps(dict(http_status=200,body_hex='0'*8194)),frame([]),'{"x":1,"x":2}'):
            self.capture.side_effect=lambda *a,**kw:raw
            with self.assertRaises(Exception):c.actual_health()
    def test_root_protected_source_digest_check(self):
        with patch.object(c.original,'read_root_file',return_value=(b'actual',0o600)):
            self.assertEqual(c.protected_body('/fixed',hashlib.sha256(b'actual').hexdigest()),b'actual')
            with self.assertRaises(c.controller.Hold):c.protected_body('/fixed','0'*64)
        self.assertEqual(c.PINS[c.controller],hashlib.sha256(Path(c.controller.__file__).read_bytes()).hexdigest())
        for module,pin in c.PINS.items():self.assertEqual(pin,hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
    def approval(self):
        return dict(format=1,host=c.plan.HOST,control_source_sha=c.CONTROL,product_source_sha=c.PRODUCT,
            composition_sha256='a'*64,receipt_sha256=c.RECEIPT_SHA,current=fixture.current(),issued_at=999,expires_at=1500,
            backup_verified_at=999,downgrade_compatibility_reviewed=True,actions=c.ACTIONS)
    def composed(self,a=None):
        a=a or self.approval();raw=json.dumps(a).encode()
        receipt=Path('deploy/community-preview/f131-image-receipt.json').read_bytes()
        def body(path,sha):
            if path==c.APPROVAL:return raw
            if path.endswith('f131-image-receipt.json'):return receipt
            return b'protected verified source'
        with patch.object(c,'protected_body',side_effect=body),patch.object(c.original,'read_root_file',return_value=(raw,0o600)),\
             patch.object(c,'LiveBindings') as bindings,patch.object(c.controller.OriginalTransport,'image_and_names_ready') as image,\
             patch.object(c.controller.Journal,'from_original_parent') as journal:
            bindings.return_value.return_value=dict(a['current'])
            result=c.compose(approval_sha256='b'*64,backup_fd=self.fd,execution_enabled=True)
            return result,journal,image,bindings
    def test_root_composition_exact_original_controller_fixed_product_and_no_load(self):
        result,j,image,b=self.composed();p=j.call_args.args[0]
        self.assertEqual(p['source']['source_sha'],c.PRODUCT);self.assertNotEqual(c.CONTROL,c.PRODUCT)
        self.assertEqual(p['image']['image_id'],'sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a')
        self.assertIs(type(result.update),c.controller.Update);self.assertIs(type(result.update.t),c.controller.OriginalTransport)
        image.assert_called_once();self.assertEqual(p['source']['push_evidence_run_id'],40058542631)
        result.close();b.return_value.close.assert_called_once()
    def test_approval_expired_wrong_scope_bool_version_or_unreviewed_backup_denies(self):
        for k,v in (('expires_at',999),('issued_at',True),('backup_verified_at',1),('downgrade_compatibility_reviewed',False),
                    ('product_source_sha',c.CONTROL),('control_source_sha',c.PRODUCT),('actions',[]),('format',True)):
            a=self.approval();a[k]=v
            with self.subTest(key=k):
                with self.assertRaises(Exception):self.composed(a)
    def test_approval_changed_or_binding_failure_before_journal_zero_journal_writes(self):
        with patch.object(c,'protected_body',side_effect=c.controller.Hold('CHANGED')),\
             patch.object(c.controller.Journal,'from_original_parent') as j:
            with self.assertRaises(c.controller.Hold):c.compose(approval_sha256='b'*64,backup_fd=self.fd,execution_enabled=True)
            j.assert_not_called()
    def test_real_live_bindings_journal_and_original_controller_composition_serial_success(self):
        b=self.binding();b.close()  # freeze actual isolated metadata, not a sample tuple
        approval=self.approval();approval['current']=dict(self.c)
        raw=json.dumps(approval).encode();receipt=Path('deploy/community-preview/f131-image-receipt.json').read_bytes()
        actions=[];new_id='9'*64;new_running=[False]
        def mutate(argv,timeout):
            actions.append(argv)
            if argv[3]=='stop':self.info['running']=False;self.info['status']='exited'
            if argv[3]=='run':new_running[0]=True;return new_id
            return ''
        def inspect(cid):
            if cid==self.c['container_id']:return dict(self.info)
            return old.info('sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a',new_id,new_running[0])
        def command(argv):
            if argv[3:5]==['image','inspect']:
                return '\n'.join(json.dumps(v) for v in (argv[-1],c.PRODUCT,'10001:1008'))
            return c.plan.NAME+'\n'
        def body(path,sha):
            if path==c.APPROVAL:return raw
            if path.endswith('f131-image-receipt.json'):return receipt
            return b'approved isolated source'
        parent=self.root/'journal';parent.mkdir(mode=0o700)
        with patch.object(c,'protected_body',side_effect=body),patch.object(c.original,'read_root_file',return_value=(raw,0o600)),\
             patch.object(c.original,'secure_directory'),patch.object(c.controller,'JOURNAL_PARENT',str(parent)),\
             patch.object(c.controller,'OWNER_UID',os.getuid()),patch.object(c.os,'uname',return_value=Mock(nodename=c.plan.HOST)),\
             patch.object(c.os,'getuid',return_value=0),patch.object(c.os,'geteuid',return_value=0),\
             patch.object(c.original,'inspect',side_effect=inspect),patch.object(c.original,'command',side_effect=command),\
             patch.object(c.original,'mutate',side_effect=mutate):
            result=c.compose(approval_sha256='b'*64,backup_fd=self.fd,execution_enabled=True)
            result.update.clock=lambda:1000
            try:
                self.assertIs(type(result.bindings),c.LiveBindings)
                r=result.update.run();self.assertEqual(r['phase'],'COMMITTED')
                self.assertFalse(self.info['running']);self.assertTrue(new_running[0])
                self.assertEqual([a[3] for a in actions],['stop','rename','run'])
                self.assertTrue((parent/result.journal.plan['attempt']/'checkpoint.json').is_file())
            finally:result.close()

    def test_no_main_cli_old_upgrader_image_loader_or_default_authorization(self):
        import ast
        tree=ast.parse(Path(c.__file__).read_text(),feature_version=(3,6))
        self.assertFalse(any(isinstance(n,ast.If) and '__name__' in ast.unparse(n.test) for n in tree.body))
        self.assertNotIn('original.main(',Path(c.__file__).read_text())
        self.assertNotIn('docker load',Path(c.__file__).read_text())

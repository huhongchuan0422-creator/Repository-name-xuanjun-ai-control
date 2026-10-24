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
        # Only the isolated reference file owner follows the Hosted fixture UID;
        # production stays fixed root and is asserted below. No OS chown/grant.
        self.production_reference_uid=c.REFERENCE_UID
        patch.object(c,'REFERENCE_UID',os.getuid()).start()
        patch.object(c.observation,'ROOT_UID',os.getuid()).start()
        patch.object(c.observation,'PROJECT_UID',os.getuid()).start()
        patch.object(c,'now',return_value=1000).start()
        for path in c.observation.META_PATHS.values():
            p=self.root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
            if path in (c.plan.ROOT+'/config',c.plan.ROOT+'/data',c.plan.RUN):p.mkdir(exist_ok=True)
            else:p.write_bytes(b'PRIVATE_NOT_READ');p.chmod(0o600)
        for path in c.observation.ROUTE_PATHS.values():
            p=self.root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(c.original.FRAGMENT if path==c.original.INC else b'route unchanged');p.chmod(0o600)
        self.backup_path='/opt/xuanjun-community-preview/existing-reviewed-reference.json'
        p=self.root/self.backup_path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'NOT_A_NEW_BACKUP');p.chmod(0o600)
        self.fd=os.open(str(p),os.O_RDONLY);self.addCleanup(os.close,self.fd)
        self.c=fixture.current();self.info=old.info(self.c['image_id'],self.c['container_id'])
        self.info.update(ports={},published={},devices=[],capadd=[])
        self.names={c.plan.NAME:self.c['container_id']};self.extra_objects={}
        self.readlink=os.readlink
        # Map only the actual private fixture file path, not reusable fd numbers.
        backup_fixture_path=str(p)
        patch.object(c.os,'readlink',side_effect=lambda name:self.backup_path
            if self.readlink(name)==backup_fixture_path else self.readlink(name)).start()
        patch.object(c,'root_host').start()
        self.checked=Mock()
        def capture(argv,**kw):
            if argv[3:5]==['container','inspect']:
                if argv[-1]==c.plan.NAME:
                    target=self.names[c.plan.NAME];info=self.extra_objects.get(target,self.info)
                    return '\n'.join(json.dumps(info[k]) for k in ('id','image'))
                info=self.extra_objects.get(argv[-1],self.info)
                fields=c.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')]
                return '\n'.join(json.dumps(info[k]) for k,_ in fields)
            if argv[3:5]==['container','ls']:
                return '\n'.join(json.dumps(dict(name=n,id=i)) for n,i in self.names.items())
            if argv[3:5]==['image','inspect']:
                return '\n'.join(json.dumps(v) for v in (argv[-1],c.plan.OBSERVED_OCI if argv[-1]==self.c['image_id'] else c.PRODUCT,'10001:1008'))
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
        self.assertEqual(self.production_reference_uid,0)
        self.assertEqual(len(c.backup_reference(self.fd)),64)
        with patch.object(c,'REFERENCE_UID',99998):
            with self.assertRaises(c.controller.Hold):c.backup_reference(self.fd)
        p=self.root/self.backup_path.lstrip('/');p.chmod(0o644)
        with self.assertRaises(c.controller.Hold):c.backup_reference(self.fd)
        p.chmod(0o600);q=p.with_name('retained');p.rename(q);p.write_bytes(b'new');p.chmod(0o600)
        with self.assertRaises(c.controller.Hold):c.backup_reference(self.fd)
        with self.assertRaises(c.controller.Hold):c.backup_reference(True)
    def test_public_probe_preserves_remote_time_and_unbound_actual_health_denies(self):
        self.capture.side_effect=[frame(health())]
        r=c.read_health_probe(c.observation.HTTP_PROBE);self.assertEqual(r['observed_at'],1000)
        self.assertEqual(self.capture.call_count,1)
        with self.assertRaisesRegex(c.controller.Hold,'CONTEXT'):c.actual_health()
    def test_health_missing_stale_bool_float_future_remote_time_is_unknown(self):
        for value in (None,True,1000.0,1,1031):
            self.capture.side_effect=lambda *a,**kw:frame(dict(health(),observed_at=value))
            with self.assertRaises(c.controller.Hold):c.read_health_probe(c.observation.HTTP_PROBE)
    def test_public_probe_malformed_frames_denied(self):
        for raw in ('{}',json.dumps(dict(http_status=True,body_hex='00')),json.dumps(dict(http_status=200,body_hex=' '*2)),
                    json.dumps(dict(http_status=200,body_hex='0'*8194)),frame([]),'{"x":1,"x":2}'):
            self.capture.side_effect=lambda *a,**kw:raw
            with self.assertRaises(Exception):c.read_health_probe(c.observation.HTTP_PROBE)
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
             patch.object(c.controller.Journal,'from_original_parent') as journal,patch.object(c,'exact_stage_names'):
            journal.return_value.state={'phase':'PREPARED'}
            def factory(candidate):journal.return_value.plan=candidate;return journal.return_value
            journal.side_effect=factory
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
            if argv[3]=='rename':
                self.names={n:i for n,i in self.names.items() if i!=argv[-2]};self.names[argv[-1]]=argv[-2]
            if argv[3]=='run':
                new_running[0]=True;self.names[c.plan.NAME]=new_id
                v=old.info('sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a',new_id,True)
                v.update(ports={},published={},devices=[],capadd=[]);self.extra_objects[new_id]=v;return new_id
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
             patch.object(c.original,'mutate',side_effect=mutate),patch.object(c,'socket_binding',return_value={'synthetic_socket':True}):
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


def reopen_process(root,stage):
    """Independent process: real files/journal/composition/controller, fake Docker.

    All authority/host/remote observations below are isolated synthetic fixtures.
    No real Docker, URL, socket, account or server is accessed.
    """
    from contextlib import ExitStack
    root=Path(root);model_path=root/'docker-fixture.json'
    model=json.loads(model_path.read_text());uid=os.getuid()
    backup_path='/opt/xuanjun-community-preview/existing-reviewed-reference.json'
    backup_file=root/backup_path.lstrip('/');backup_file.parent.mkdir(parents=True,exist_ok=True)
    if not backup_file.exists():backup_file.write_bytes(b'synthetic reference only');backup_file.chmod(0o600)
    for path in c.observation.META_PATHS.values():
        p=root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
        if path in (c.plan.ROOT+'/config',c.plan.ROOT+'/data',c.plan.RUN):p.mkdir(exist_ok=True)
        elif not p.exists():p.write_bytes(b'private fixture not read');p.chmod(0o600)
    for path in c.observation.ROUTE_PATHS.values():
        p=root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():p.write_bytes(c.original.FRAGMENT if path==c.original.INC else b'unchanged fixture route');p.chmod(0o600)
    parent=root/'journal';parent.mkdir(mode=0o700,exist_ok=True)
    approval_file=root/'approval.json';receipt_path=Path('deploy/community-preview/f131-image-receipt.json')
    real_readlink=os.readlink
    def capture(argv,**kwargs):
        if argv[3:5]==['container','inspect']:
            ref=argv[-1];cid=model['names'].get(ref,ref);obj=model['objects'][cid]
            if argv[-2]=='{{json .Id}}\n{{json .Image}}':return '\n'.join(json.dumps(obj[k]) for k in ('id','image'))
            return '\n'.join(json.dumps(obj[k]) for k,_ in c.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')])
        if argv[3:5]==['image','inspect']:
            return '\n'.join(json.dumps(v) for v in (argv[-1],c.plan.OBSERVED_OCI if argv[-1]==model['old_image'] else c.PRODUCT,'10001:1008'))
        if argv[3:5]==['container','ls']:
            return '\n'.join(json.dumps(dict(name=n,id=i)) for n,i in sorted(model['names'].items()))
        h=health()
        if stage=='first':h['status']='MAINTENANCE'
        elif stage=='missing_runtime':h.update(runtime_source_sha=None,version_source=None)
        elif stage=='recover':h.update(runtime_source_sha=None,version_source=None)
        return frame(h)
    def command(argv):
        if argv[3:5]==['image','inspect']:return capture(argv)
        return '\n'.join(model['names'])
    def inspect(cid):return copy.deepcopy(model['objects'][cid])
    def mutate(argv,timeout):
        model['actions'].append(argv)
        if argv[3] in ('stop','start'):
            obj=model['objects'][argv[-1]];obj['running']=argv[3]=='start';obj['status']='running' if obj['running'] else 'exited'
        elif argv[3]=='rename':
            cid=argv[-2];model['names']={n:i for n,i in model['names'].items() if i!=cid};model['names'][argv[-1]]=cid
        elif argv[3]=='run':
            cid='9'*64;obj=old.info(model['new_image'],cid,True);obj.update(ports={},published={},devices=[],capadd=[])
            model['objects'][cid]=obj;model['names'][c.plan.NAME]=cid
        model_path.write_text(json.dumps(model));model_path.chmod(0o600)
        return '9'*64 if argv[3]=='run' else ''
    def body(path,sha):
        raw=approval_file.read_bytes() if path==c.APPROVAL else Path(path).read_bytes()
        c.require(hashlib.sha256(raw).hexdigest()==sha,'FIXTURE_EXACT_APPROVED_SOURCE_OR_FILE_REQUIRED')
        return raw
    fd=os.open(str(backup_file),os.O_RDONLY);result=None
    with ExitStack() as stack:
        for target,name,value in ((c.observation,'ROOT_ANCHOR',str(root)),(c.observation,'ROOT_UID',uid),
            (c.observation,'PROJECT_UID',uid),(c,'REFERENCE_UID',uid),(c,'now',lambda:1000),
            (c.controller,'OWNER_UID',uid),(c.controller,'JOURNAL_PARENT',str(parent)),
            (c.os,'getuid',lambda:0),(c.os,'geteuid',lambda:0),(c.os,'uname',lambda:Mock(nodename=c.plan.HOST)),
            (c.os,'readlink',lambda path:backup_path if real_readlink(path)==str(backup_file) else real_readlink(path)),
            (c.observation,'capture',capture),(c.original,'command',command),(c.original,'inspect',inspect),
            (c.original,'mutate',mutate),(c,'protected_body',body),(c,'socket_binding',lambda:{'synthetic_socket':True})):
            stack.enter_context(patch.object(target,name,value))
        # Only the temporary journal parent's /tmp ancestors use the isolated
        # owner policy. Original root parent protection is unchanged in source.
        stack.enter_context(patch.object(c.original,'secure_directory'))
        if not approval_file.exists():
            current=c.observe_current(backup_fd=fd)
            a=dict(format=1,host=c.plan.HOST,control_source_sha=c.CONTROL,product_source_sha=c.PRODUCT,
                composition_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),receipt_sha256=c.RECEIPT_SHA,
                current=current,issued_at=999,expires_at=1500,backup_verified_at=999,
                downgrade_compatibility_reviewed=True,actions=c.ACTIONS)
            approval_file.write_text(json.dumps(a));approval_file.chmod(0o600)
        try:
            digest=hashlib.sha256(approval_file.read_bytes()).hexdigest()
            result=c.compose(approval_sha256=digest,backup_fd=fd,execution_enabled=True)
            result.update.clock=lambda:1000
            if stage in ('first','missing_runtime'):result.update.run()
            elif stage=='recover':result.update.recover()
            elif stage=='mark_unknown':result.journal.write(c.controller.HOLD_PHASE,result.journal.state['new_id'])
            outcome=dict(result='ACCEPTED',phase=result.journal.state['phase'])
        except Exception as error:
            outcome=dict(result='HOLD',reason=str(error))
        finally:
            if result is not None:result.close()
            os.close(fd)
    model_path.write_text(json.dumps(model));model_path.chmod(0o600)
    checkpoints=list(parent.glob('*/checkpoint.json'))
    if checkpoints:outcome['checkpoint']=json.loads(checkpoints[0].read_text())
    outcome['actions']=len(model['actions']);print(json.dumps(outcome))


class CompositionReopen(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        current=fixture.current();obj=old.info(current['image_id'],current['container_id']);obj.update(ports={},published={},devices=[],capadd=[])
        self.path=self.root/'docker-fixture.json'
        self.save(dict(old_image=current['image_id'],new_image='sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a',
            objects={current['container_id']:obj},names={c.plan.NAME:current['container_id']},actions=[]))
    def save(self,value):self.path.write_text(json.dumps(value));self.path.chmod(0o600)
    def child(self,stage):
        import subprocess,sys
        # Source/test imports only; each invocation is a fresh independent Python
        # process and actual flock/fsync/history is reopened, never mocked/reset.
        code='from test_community_preview_update_composition import reopen_process;import sys;reopen_process(sys.argv[1],sys.argv[2])'
        r=subprocess.run([sys.executable,'-B','-c',code,str(self.root),stage],capture_output=True,text=True,timeout=15,
                         env=dict(os.environ,PYTHONPATH='.:tests'))
        self.assertEqual(r.returncode,0,r.stderr);return json.loads(r.stdout)
    def first(self):
        r=self.child('first');self.assertEqual(r['result'],'HOLD');self.assertEqual(r['reason'],'KNOWN_FAILURE_RECOVERY_REQUIRED')
        self.assertEqual(r['checkpoint']['phase'],'KNOWN_FAILURE');self.assertEqual(r['checkpoint']['new_id'],'9'*64)
        self.assertEqual(r['actions'],3);return r
    def journal_bytes(self):return {str(p.relative_to(self.root)):p.read_bytes() for p in (self.root/'journal').rglob('*') if p.is_file()}
    def rejected_unchanged(self,expected):
        before=self.journal_bytes();actions=len(json.loads(self.path.read_text())['actions'])
        r=self.child('probe');self.assertEqual(r['result'],'HOLD');self.assertIn(expected,r['reason'])
        self.assertEqual(r['actions'],actions);self.assertEqual(self.journal_bytes(),before);return r
    def test_independent_process_known_failure_reopen_and_real_serial_recovery(self):
        self.first();approved=(self.root/'approval.json').read_bytes()
        r=self.child('recover');self.assertEqual(r['result'],'ACCEPTED');self.assertEqual(r['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertEqual((self.root/'approval.json').read_bytes(),approved)
        m=json.loads(self.path.read_text());self.assertFalse(m['objects']['9'*64]['running'])
        self.assertTrue(m['objects'][fixture.current()['container_id']]['running'])
        self.assertEqual([a[3] for a in m['actions']],['stop','rename','run','stop','rename','rename','start'])
        self.rejected_unchanged('EXISTING_PHASE_INSPECT_ONLY')
    def test_missing_public_runtime_after_real_composition_run_stays_unknown_no_recovery(self):
        r=self.child('missing_runtime');self.assertEqual(r['result'],'HOLD')
        self.assertEqual(r['checkpoint']['phase'],c.controller.HOLD_PHASE)
        self.assertEqual(r['actions'],3)
        self.rejected_unchanged('EXISTING_PHASE_INSPECT_ONLY')
    def test_already_stopped_known_new_writer_reopens_without_duplicate_stop(self):
        self.first();m=json.loads(self.path.read_text());m['objects']['9'*64].update(running=False,status='exited');self.save(m)
        r=self.child('recover');self.assertEqual(r['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertEqual([a[3] for a in json.loads(self.path.read_text())['actions']],['stop','rename','run','rename','rename','start'])
    def test_wrong_current_or_rollback_name_ownership_denies_without_mutation(self):
        self.first();original=json.loads(self.path.read_text())
        for target in ('current','rollback','failed'):
            m=copy.deepcopy(original);rollback=next(n for n in m['names'] if n!=c.plan.NAME)
            if target=='current':m['names'][c.plan.NAME]='8'*64
            elif target=='rollback':m['names'][rollback]='8'*64
            else:
                failed=rollback.replace('-before-','-failed-');m['names'][failed]='8'*64
            self.save(m)
            with self.subTest(target=target):self.rejected_unchanged('RECOVERY_CONTAINER_NAME_OWNERSHIP_CHANGED')
        self.save(original)
    def test_wrong_new_image_or_old_revived_denies_without_mutation(self):
        self.first();original=json.loads(self.path.read_text())
        m=copy.deepcopy(original);m['objects']['9'*64]['image']=m['old_image'];self.save(m)
        self.rejected_unchanged('EXACT_CONTAINER_STATE_REQUIRED')
        m=copy.deepcopy(original);m['objects'][fixture.current()['container_id']]['running']=True;self.save(m)
        self.rejected_unchanged('RECOVERY_OLD_WRITER_MUST_BE_STOPPED')
    def test_wrong_attempt_valid_live_binding_cannot_replace_active_record(self):
        self.first();m=json.loads(self.path.read_text());oldid=fixture.current()['container_id'];obj=m['objects'].pop(oldid)
        obj['id']='8'*64;m['objects']['8'*64]=obj;m['names']={n:('8'*64 if i==oldid else i) for n,i in m['names'].items()};self.save(m)
        p=self.root/'approval.json';a=json.loads(p.read_text());a['current']['container_id']='8'*64;p.write_text(json.dumps(a));p.chmod(0o600)
        self.rejected_unchanged('OTHER_ATTEMPT_OR_PARTIAL_ACTIVE_RECORD')
    def test_unknown_and_corrupt_complete_history_are_inspect_only(self):
        self.first();r=self.child('mark_unknown');self.assertEqual(r['phase'],c.controller.HOLD_PHASE)
        self.rejected_unchanged('EXISTING_PHASE_INSPECT_ONLY')
        event=next((self.root/'journal').glob('*/event-000001.json'));event.write_bytes(b'{partial')
        self.rejected_unchanged('CORRUPT_EVENT_INSPECT_ONLY')
    def test_prepared_reopen_preserves_original_running_and_name_collision_gates(self):
        r=self.child('probe');self.assertEqual(r['phase'],'PREPARED');self.assertEqual(r['actions'],0)
        m=json.loads(self.path.read_text());original=copy.deepcopy(m)
        m['objects'][fixture.current()['container_id']]['running']=False;self.save(m)
        self.rejected_unchanged('ORIGINAL_OLD_WRITER_NOT_RUNNING')
        m=original
        rollback=c.plan.NAME+'-before-'+c.PRODUCT[:12]+'-'+fixture.current()['container_id'][:12]
        m['names'][rollback]='8'*64;self.save(m)
        self.rejected_unchanged('EXISTING_RECOVERY_NAME_INSPECT_ONLY')

    def test_reopen_expired_approval_refuses_before_journal_and_mutation(self):
        self.first();p=self.root/'approval.json';a=json.loads(p.read_text());a['expires_at']=999;p.write_text(json.dumps(a));p.chmod(0o600)
        self.rejected_unchanged('APPROVAL_OR_BACKUP_EXPIRED')

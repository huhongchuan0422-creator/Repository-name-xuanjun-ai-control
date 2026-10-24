"""ONE proxy result fixture + real protected routes/journal; never real Nginx/UK."""
import copy
import hashlib
import json
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import test_community_preview_release_plan as f
import test_community_preview_upgrade as old
from scripts import community_preview_update_composition as c

RAW_SOCKET_BINDING=c.socket_binding


class HttpsAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        for key,value in (('ROOT_ANCHOR',str(self.root)),('ROOT_UID',os.getuid()),('PROJECT_UID',os.getuid())):
            patch.object(c.observation,key,value).start()
        routes={}
        for path in c.observation.ROUTE_PATHS.values():
            q=self.root/path.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True)
            q.write_bytes(c.original.FRAGMENT if path==c.original.INC else b'ROOT_REVIEWED_VHOST_FIXTURE');q.chmod(0o600)
            routes[path]=hashlib.sha256(q.read_bytes()).hexdigest()
        source=f.source();source['source_sha']=c.PRODUCT;image=f.image();image.update(source_sha=c.PRODUCT,oci_revision=c.PRODUCT,image_id='sha256:571b7c6e23135943172171e64851bfe7f8151ba7eba9d5590158c5c99409545a')
        self.current=f.current();self.current['routing_sha256']=c.digest(routes)
        self.p=c.plan.prepare(source,self.current,image)
        parent=self.root/'journal';parent.mkdir(mode=0o700)
        patch.object(c.controller,'OWNER_UID',os.getuid()).start();patch.object(c.controller,'JOURNAL_PARENT',str(parent)).start()
        fd=os.open(str(parent),os.O_RDONLY|os.O_DIRECTORY)
        try:self.j=c.controller.Journal(fd,self.p)
        finally:os.close(fd)
        self.addCleanup(self.j.close)
        for phase in ('OLD_STOP_INTENT','OLD_STOPPED','OLD_RENAME_INTENT','OLD_RETAINED','NEW_RUN_INTENT'):self.j.write(phase)
        self.new='9'*64;self.j.write('NEW_KNOWN',self.new)
        self.old_info=old.info(self.current['image_id'],self.current['container_id'],False)
        self.new_info=old.info(image['image_id'],self.new,True)
        for info in (self.old_info,self.new_info):info.update(ports={},published={},devices=[],capadd=[])
        self.target=self.new;self.image_revision=c.PRODUCT;self.time=1000;self.http_calls=0;self.on_http=None
        self.remote=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                         runtime_source_sha=c.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=1000)
        self.socket=dict(device=1,inode=2,uid=10001,gid=1008,mode=0o660,mtime_ns=1,ctime_ns=1)
        patch.object(c,'socket_binding',side_effect=lambda:dict(self.socket)).start()
        patch.object(c,'root_host').start();patch.object(c,'now',side_effect=lambda:self.time).start()
        self.live_extra={}
        def binding():return dict(self.current,running=self.old_info['running'],observed_at=self.time,**self.live_extra)
        self.bindings=binding
        def capture(argv,**kwargs):
            if argv[:3]==c.plan.DOCKER:
                if argv[3:5]==['container','inspect']:
                    if argv[-1]==c.plan.NAME:
                        info=self.old_info if self.target==self.current['container_id'] else self.new_info
                        return '\n'.join(json.dumps(v) for v in (self.target,info['image']))
                    info=self.old_info if argv[-1]==self.current['container_id'] else self.new_info
                    return '\n'.join(json.dumps(info[k]) for k,_ in c.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')])
                if argv[3:5]==['image','inspect']:
                    return '\n'.join(json.dumps(v) for v in (argv[-1],self.image_revision,'10001:1008'))
                raise AssertionError('NO_MUTATION_OR_OTHER_QUERY')
            self.assertEqual(argv,['/usr/bin/python3','-I','-B','-S','-c',c.observation.HTTP_PROBE])
            self.assertEqual(kwargs,dict(timeout=10,budget=10000));self.http_calls+=1
            if self.on_http:self.on_http()
            return json.dumps(dict(http_status=200,body_hex=json.dumps(self.remote).encode().hex()))
        self.capture=patch.object(c.observation,'capture',side_effect=capture).start()
        self.reader=c.BoundHttpsHealth(self.j,self.bindings)
    def denied(self):
        with self.assertRaises(Exception):self.reader()
        self.assertIsNone(self.reader.last_evidence)
    def test_one_anonymous_https_exact_host_binding_no_private_path(self):
        value=self.reader();self.assertEqual(self.http_calls,1);self.assertEqual(value['runtime_source_sha'],c.PRODUCT)
        proof=self.reader.last_evidence;self.assertFalse(proof['independent_private_health'])
        self.assertEqual(proof['target_id'],self.new);self.assertEqual(proof['contract'],'ANONYMOUS_HTTPS_ORIGINAL_NGINX_PATH')
        self.assertEqual(proof['backend_observed_at'],1000)
    def test_unbound_health_has_no_network_fallback(self):
        with self.assertRaisesRegex(c.controller.Hold,'CONTEXT'):c.actual_health()
        self.assertEqual(self.http_calls,0)
    def test_missing_wrong_runtime_stamp_and_old_200_ready_all_unknown(self):
        for key,value in (('runtime_source_sha',None),('runtime_source_sha',c.plan.OBSERVED_OCI),('version_source',None),('version_source','LOCAL_SHA')):
            with self.subTest(key=key,value=value):
                previous=self.remote[key];self.remote[key]=value;self.denied();self.remote[key]=previous
    def test_missing_stale_bool_float_future_remote_time_denied(self):
        for value in (None,True,1000.0,1,1031):
            with self.subTest(value=value):self.remote['observed_at']=value;self.denied()
    def test_response_expires_during_post_binding_reads(self):
        self.remote['observed_at']=401;self.on_http=lambda:setattr(self,'time',1002);self.denied()
    def test_route_changed_during_response_denied(self):
        self.on_http=lambda:(self.root/c.original.INC.lstrip('/')).write_bytes(b'WRONG_ROUTE')
        self.denied();self.assertEqual(self.http_calls,1)
    def test_initial_wrong_route_even_if_approved_digest_is_denied(self):
        q=self.root/c.original.INC.lstrip('/');q.write_bytes(b'WRONG_ROUTE')
        routes={path:c.observation.safe_file(path,True)[0]['sha256'] for path in c.observation.ROUTE_PATHS.values()}
        self.current['routing_sha256']=self.p['current']['routing_sha256']=c.digest(routes)
        self.denied();self.assertEqual(self.http_calls,0)
    def test_socket_missing_or_replaced_or_wrong_target_denied(self):
        self.on_http=lambda:self.socket.update(inode=3);self.denied()
        self.on_http=None
        with patch.object(c,'socket_binding',side_effect=FileNotFoundError()):self.denied()
        self.target='8'*64;self.denied()
    def test_new_image_oci_wrong_before_or_after_request_denied(self):
        self.image_revision=c.plan.OBSERVED_OCI;self.denied();self.assertEqual(self.http_calls,0)
        self.image_revision=c.PRODUCT;self.on_http=lambda:setattr(self,'image_revision',c.plan.OBSERVED_OCI);self.denied()
    def test_wrong_writer_pair_or_identity_after_response_denied(self):
        self.on_http=lambda:self.old_info.update(running=True);self.denied()
        self.old_info['running']=False;self.on_http=lambda:self.new_info.update(id='8'*64);self.denied()
    def test_journal_new_id_phase_or_sequence_change_during_response_denied(self):
        self.on_http=lambda:self.j.state.update(new_id='8'*64);self.denied()
    def test_protected_source_missing_or_immutable_field_change_denied(self):
        self.reader.bindings=lambda:dict(self.current,running=False,observed_at=1000,config_identity_sha256='0'*64)
        self.denied();self.assertEqual(self.http_calls,0)
        self.reader.bindings=lambda:{};self.denied()
    def test_legacy_rollback_without_runtime_or_time_not_new_acceptance(self):
        self.j.write('KNOWN_FAILURE',self.new)
        for phase in ('RECOVERY_STOP_NEW_INTENT','RECOVERY_RENAME_NEW_INTENT','RECOVERY_RESTORE_OLD_INTENT','RECOVERY_START_OLD_INTENT'):self.j.write(phase,self.new)
        self.old_info['running']=True;self.new_info['running']=False;self.target=self.current['container_id'];self.image_revision=c.plan.OBSERVED_OCI
        self.remote.update(runtime_source_sha=None,version_source=None,observed_at=None);self.denied()
        self.remote['observed_at']=1000;self.reader()
        self.assertEqual(self.reader.last_evidence['scope'],'LEGACY_ROLLBACK_PROCESS_DB_ONLY')
        self.assertIsNone(self.reader.last_evidence['runtime_source_sha'])
    def test_success_cannot_leave_cached_evidence_after_later_missing_source(self):
        self.reader();self.assertIsNotNone(self.reader.last_evidence)
        calls=[]
        def loses_source():
            calls.append(1)
            return self.bindings() if len(calls)==1 else {'running':False}
        self.reader.bindings=loses_source;self.denied()

    def test_raw_socket_stat_protection_synthetic_type_owner_mode_and_symlink(self):
        # Explicit stat fixture, never socket creation/connect/listen.
        q=self.root/(c.plan.RUN+'/preview.sock').lstrip('/');q.parent.mkdir(parents=True,exist_ok=True)
        q.write_bytes(b'NOT_A_SOCKET');q.chmod(0o660);real=os.stat;group=[1008]
        def projected(path,*args,**kwargs):
            value=real(path,*args,**kwargs)
            if path=='preview.sock' and stat.S_ISREG(value.st_mode):
                fields={k:getattr(value,k) for k in dir(value) if k.startswith('st_')}
                fields.update(st_mode=stat.S_IFSOCK|stat.S_IMODE(value.st_mode),st_gid=group[0])
                return types.SimpleNamespace(**fields)
            return value
        with patch.object(c.os,'stat',side_effect=projected):
            self.assertEqual(RAW_SOCKET_BINDING()['gid'],1008)
            group[0]=0
            with self.assertRaises(c.controller.Hold):RAW_SOCKET_BINDING()
            group[0]=1008;q.chmod(0o666)
            with self.assertRaises(c.controller.Hold):RAW_SOCKET_BINDING()
            q.unlink();q.symlink_to('/etc/passwd')
            with self.assertRaises(c.controller.Hold):RAW_SOCKET_BINDING()

    def test_clock_reversed_and_unknown_transport_are_denied(self):
        self.on_http=lambda:setattr(self,'time',999);self.denied()
        with patch.object(c,'read_health_probe',side_effect=TimeoutError()):self.denied()

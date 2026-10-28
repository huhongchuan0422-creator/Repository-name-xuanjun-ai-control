"""Five-object candidate isolation tests; no actual Docker/HTTPS/UK execution."""
import ast
import copy
import hashlib
import io
import json
import os
import signal
import stat
import types
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch,Mock
import test_community_preview_upgrade as fixture
from scripts import community_preview_preupdate_observe as p
from scripts import community_preview_preupdate_bundle as bundle


try:
    from . import test_community_historical_fixtures as frozen
except ImportError:
    import test_community_historical_fixtures as frozen

class FiveObjectReadonly(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        for key,value in (('ROOT_ANCHOR',str(self.root)),('ROOT_UID',os.getuid()),('PROJECT_UID',os.getuid())):
            patch.object(p.v,key,value).start()
        patch.object(p,'wall',return_value=1000).start()
        self.cid='e'*64;self.image='sha256:'+'f'*64
        self.info=fixture.info(self.image,self.cid);self.info.update(ports={},published={},devices=[],capadd=[])
        for path in p.v.META_PATHS.values():
            q=self.root/path.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True)
            if path in (p.v.ROOT+'/config',p.v.ROOT+'/data',p.v.RUN):q.mkdir(exist_ok=True)
            else:q.write_bytes(b'PRIVATE_CONFIG_SENTINEL');q.chmod(0o600)
        for path in list(p.v.ROUTE_PATHS.values())+['/usr/bin/docker',p.v.STAGE+'/include.before']:
            q=self.root/path.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b'PUBLIC_ROUTE_OR_FILE');q.chmod(0o600)
        # Explicit synthetic socket metadata: this environment denies socket
        # creation (EPERM). No retry, network, listener or socket file is made.
        q=self.root/p.SOCKET.lstrip('/');q.write_bytes(b'NOT_A_SOCKET_BODY');q.chmod(0o660)
        self.socket_fixture=True;real_stat=os.stat
        def socket_stat(path,*args,**kwargs):
            s=real_stat(path,*args,**kwargs)
            if path=='preview.sock' and self.socket_fixture and stat.S_ISREG(s.st_mode):
                values={k:getattr(s,k) for k in dir(s) if k.startswith('st_')}
                values['st_mode']=stat.S_IFSOCK|stat.S_IMODE(s.st_mode)
                return types.SimpleNamespace(**values)
            return s
        patch.object(p.os,'stat',side_effect=socket_stat).start()
        self.commands=[];self.body=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False)
        def capture(argv,**kw):
            self.commands.append(list(argv))
            if argv[:3]==p.v.DOCKER:
                if argv[3:5]==['container','ls']:
                    self.assertTrue(argv[-1].startswith('name=^/xuanjun-community-preview'))
                    self.assertTrue(argv[-1].endswith('$'))
                    return json.dumps(dict(id=self.cid,name=p.v.CURRENT)) if argv[-1]=='name=^/'+p.v.CURRENT+'$' else ''
                if argv[3:5]==['container','inspect']:
                    fmt=argv[6] if argv[5]=='--format' else argv[-2]
                    if fmt=='{{json .Id}}\n{{json .Name}}\n{{json .Image}}\n{{json .State.Running}}':return '\n'.join(json.dumps(v) for v in (self.cid,'/'+p.v.CURRENT,self.image,True))
                    if fmt=='{{json .Id}}\n{{json .Image}}':return '\n'.join(json.dumps(v) for v in (self.cid,self.image))
                    fields=p.approved.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')]
                    return '\n'.join(json.dumps(self.info[k]) for k,_ in fields)
                if argv[3:5]==['image','inspect']:
                    image=argv[-1];revision=p.PRODUCT if image==p.IMAGE else '2330dd55c07f58d7f45a7c4510a9761d0d4735d6'
                    return '\n'.join(json.dumps(v) for v in (image,[],revision,'10001:1008'))
                raise AssertionError('OUT_OF_SCOPE_DOCKER')
            self.assertEqual(argv[:5],['/usr/bin/python3','-I','-B','-S','-c'])
            self.assertIn(argv[-1],(p.v.HTTP_PROBE,p.approved.PRIVATE_PROBE))
            return json.dumps(dict(http_status=200,body_hex=json.dumps(self.body).encode().hex()))
        self.capture=patch.object(p.v,'capture',side_effect=capture).start()
    def report(self):
        r=dict(sections={});return p.observe(r)
    def test_five_sections_real_metadata_four_digests_unknown_fifth_no_fake_gate(self):
        r=self.report();s=r['sections'];current=s['current']
        self.assertEqual(current['container_id'],self.cid);self.assertEqual(current['image_id'],self.image)
        self.assertEqual(current['backup_reference_sha256'],'UNKNOWN')
        for key in ('config_identity_sha256','data_identity_sha256','routing_sha256','isolation_sha256'):
            self.assertRegex(current[key],r'^[0-9a-f]{64}$')
        self.assertEqual(s['current_recheck']['identity_image_isolation_four_digests'],'MATCH')
        self.assertEqual(s['socket_recheck']['identity'],'MATCH')
        self.assertEqual(s['f131_loaded_image']['candidate_relation'],'EXACT_ID_OCI_USER_MATCH')
        self.assertEqual(s['approval']['status'],'MISSING_FIXED_PATH');self.assertEqual(s['journal_parent']['status'],'MISSING_FIXED_PATH')
        self.assertEqual(s['database_backup']['verified_restore'],'UNKNOWN')
        self.assertTrue(s['root_caller_sources']['status'].startswith('UNKNOWN'))
        self.assertTrue(s['historical_route_backup']['scope'].startswith('ROUTE_BACKUP_ONLY'))
        names=s['phase_names'];self.assertEqual(sum(v['status']=='OBSERVED_ABSENT' for v in names.values()),2)
        self.assertNotIn('PRIVATE_CONFIG_SENTINEL',json.dumps(r))
    def test_current_digests_identical_to_approved_composition_metadata_algorithm(self):
        r=p.current_projection();a=p.approved
        config={q:a.stable_metadata(q) for q in (p.v.ROOT+'/config',p.v.ROOT+'/config/host.json',p.v.ROOT+'/config/center-keys.json',p.v.ROOT+'/config/wechat.json')}
        self.assertEqual(r['config_identity_sha256'],a.digest(config))
        isolation=a.canonical_isolation({k:v for k,v in self.info.items() if k not in ('id','image','running','status')})
        self.assertEqual(r['isolation_sha256'],a.digest(isolation))
    def test_allowed_docker_isolation_spellings_are_stable_but_real_drift_is_not(self):
        canonical=self.report()['sections']['current']['isolation_sha256']
        self.info['network']='default';self.info['security']=['no-new-privileges:true']
        self.assertEqual(self.report()['sections']['current']['isolation_sha256'],canonical)
        self.info['network']='host'
        self.assertEqual(self.report()['sections']['current']['status'],'HOLD_UNKNOWN')
    def test_no_private_bodies_no_path_search_no_receipt_recheck(self):
        real=p.v.os.read
        def read(fd,n):
            name=os.readlink('/proc/self/fd/'+str(fd))
            self.assertFalse(name.endswith(('host.json','center-keys.json','wechat.json','include.before')))
            return real(fd,n)
        with patch.object(p.v.os,'read',side_effect=read),patch.object(p.os,'listdir',side_effect=AssertionError('NO_SCAN')):
            self.report()
        commands=json.dumps(self.commands)
        for command in self.commands:
            if command[:3]==p.v.DOCKER:
                self.assertIn(command[3:5],(['container','inspect'],['container','ls'],['image','inspect']))
                self.assertFalse(any(token in command for token in ('exec','load','stop','start','rename','run','pull')))
        for forbidden in ('.Config.Env','attempt.json','resume-01','before-2330dd55'):
            self.assertNotIn(forbidden,commands)
    def test_private_and_public_missing_remote_time_never_mint_freshness(self):
        for private,probe in ((False,p.v.HTTP_PROBE),(True,p.approved.PRIVATE_PROBE)):
            r=p.health_probe(probe,private);self.assertEqual(r['backend_status'],'READY')
            self.assertEqual(r['backend_observed_at'],'UNKNOWN');self.assertEqual(r['freshness'],'UNKNOWN')
            self.assertEqual(r['collection_observed_at'],1000)
        for remote,expected in ((1,'STALE'),(1000,'FRESH'),(1031,'FUTURE'),(True,'UNKNOWN'),(1000.0,'UNKNOWN')):
            self.body['observed_at']=remote;self.assertEqual(p.health_probe(p.v.HTTP_PROBE)['freshness'],expected)
    def test_health_nested_fields_duplicate_json_or_oversized_frames_not_passed_through(self):
        self.body.update(status={'secret':'NESTED'},scope={'secret':'NESTED'},runtime_source_sha={'secret':'NESTED'})
        r=p.health_probe(p.v.HTTP_PROBE);self.assertNotIn('NESTED',json.dumps(r));self.assertEqual(r['backend_status'],'UNKNOWN')
        for raw in ('{"http_status":200,"http_status":200,"body_hex":"00"}',json.dumps(dict(http_status=True,body_hex='00')),
                    json.dumps(dict(http_status=200,body_hex='00'*4097))):
            with patch.object(p.v,'capture',return_value=raw):
                with self.assertRaises(Exception):p.health_probe(p.v.HTTP_PROBE)
    def test_socket_wrong_type_symlink_owner_mode_and_replacement_deny(self):
        q=self.root/p.SOCKET.lstrip('/');q.chmod(0o666)
        with self.assertRaises(p.v.Hold):p.socket_metadata()
        self.socket_fixture=False
        q.unlink();q.write_bytes(b'not socket');q.chmod(0o660)
        with self.assertRaises(p.v.Hold):p.socket_metadata()
        q.unlink();q.symlink_to('/etc/passwd')
        with self.assertRaises(p.v.Hold):p.socket_metadata()
    def test_socket_owner_and_read_time_replacement_denied(self):
        with patch.object(p.v,'PROJECT_UID',os.getuid()+1234):
            with self.assertRaises(p.v.Hold):p.socket_metadata()
        original=p.v.parent_fd;calls=[]
        def replace(path):
            calls.append(path)
            if len(calls)==2:
                q=self.root/p.SOCKET.lstrip('/');old=q.with_name('retained-socket-fixture');q.rename(old)
                q.write_bytes(b'replaced');q.chmod(0o660)
            return original(path)
        with patch.object(p.v,'parent_fd',side_effect=replace):
            with self.assertRaises(p.v.Hold):p.socket_metadata()
    def test_exact_name_query_malformed_duplicate_or_daemon_unknown_deny(self):
        current=dict(container_id=self.cid,image_id=self.image)
        original=self.capture.side_effect
        def bad(argv,**kw):
            if argv[3:5]==['container','ls']:return '{"id":"not-an-id","name":"outside"}'
            return original(argv,**kw)
        self.capture.side_effect=bad
        with self.assertRaises(p.v.Hold):p.names_for(current)
        def rejected(argv,**kw):
            if argv[3:5]==['container','ls']:raise p.v.Hold('DAEMON_UNKNOWN')
            return original(argv,**kw)
        self.capture.side_effect=rejected
        with self.assertRaises(p.v.Hold):p.names_for(current)

    def test_current_bad_isolation_and_recheck_change_are_hold(self):
        self.info['ports']={'80/tcp':[{'HostPort':'80'}]}
        self.assertEqual(self.report()['sections']['current']['status'],'HOLD_UNKNOWN')
        self.info['ports']={}
        original=p.current_projection;seen=[]
        def changed():
            value=original();seen.append(True)
            if len(seen)>1:value['routing_sha256']='0'*64
            return value
        with patch.object(p,'current_projection',side_effect=changed):
            self.assertEqual(self.report()['sections']['current_recheck']['status'],'HOLD_UNKNOWN')
    def test_image_unavailable_never_claims_absent_loaded_and_no_mutation(self):
        original=self.capture.side_effect
        def unavailable(argv,**kw):
            if argv[:3]==p.v.DOCKER and argv[-1]==p.IMAGE:raise p.v.Hold('COMMAND_REJECTED')
            return original(argv,**kw)
        self.capture.side_effect=unavailable
        self.assertEqual(self.report()['sections']['f131_loaded_image']['status'],'HOLD_UNKNOWN')
    def test_approval_journal_metadata_only_does_not_create_lock_or_file(self):
        q=self.root/p.APPROVAL.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b'SECRET_IN_APPROVAL_NOT_READ');q.chmod(0o600)
        d=self.root/p.JOURNAL.lstrip('/');d.mkdir(mode=0o700)
        before={str(f.relative_to(self.root)):f.stat().st_mtime_ns for f in self.root.rglob('*')}
        r=self.report();after={str(f.relative_to(self.root)):f.stat().st_mtime_ns for f in self.root.rglob('*')}
        self.assertEqual(before,after);self.assertEqual(r['sections']['approval']['mode'],'0600')
        self.assertEqual(list(d.iterdir()),[]);self.assertNotIn('SECRET_IN_APPROVAL',json.dumps(r))
    def test_root_host_argument_gate_no_observation(self):
        with patch.object(p,'observe') as read,patch.object(p.sys,'argv',['readonly','extra']),redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(),2);read.assert_not_called()
        with patch.object(p,'observe') as read,patch.object(p.sys,'argv',['readonly']),patch.object(p.os,'geteuid',return_value=1000),redirect_stdout(io.StringIO()):
            self.assertEqual(p.main(),2);read.assert_not_called()
    def test_bounded_main_hold_and_signal_restoration(self):
        before=signal.getsignal(signal.SIGALRM)
        with patch.object(p.sys,'argv',['readonly']),patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0),\
             patch.object(p.os,'uname',return_value=Mock(nodename=p.v.HOST)),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p.main(),2)
        r=json.loads(out.getvalue());self.assertFalse(r['executable_update']);self.assertEqual(r['execution_permission'],'NOT_GRANTED')
        self.assertEqual(signal.getsignal(signal.SIGALRM),before)
        with patch.object(p.sys,'argv',['readonly']),patch.object(p.os,'getuid',return_value=0),patch.object(p.os,'geteuid',return_value=0),\
             patch.object(p.os,'uname',return_value=Mock(nodename=p.v.HOST)),patch.object(p,'observe',side_effect=p.v.TotalDeadline()),redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p.main(),2);self.assertEqual(json.loads(out.getvalue())['state'],'HOLD_PARTIAL_BOUNDED_OBSERVATION')
    def test_bundle_exact_helpers_standalone_ast_shell_and_dependency_pin(self):
        with frozen.historical_tree(frozen.READONLY_COMMIT) as root,patch.object(bundle,'ROOT',root):
            python,shell=bundle.build()
            self.assertEqual(python,(bundle.ROOT/'deploy/community-preview/preupdate-five-readonly.py').read_bytes())
            self.assertEqual(shell,(bundle.ROOT/'deploy/community-preview/preupdate-five-readonly.sh').read_bytes())
            ast.parse(python,feature_version=(3,6));ast.parse(p.approved.PRIVATE_PROBE,feature_version=(3,6))
            self.assertEqual(shell.split(b"<<'COMMUNITY_PREUPDATE_READONLY_PY'",1)[1].split(b'\n',1)[1].split(b'\nCOMMUNITY_PREUPDATE_READONLY_PY\n',1)[0],python.rstrip(b'\n'))
            self.assertEqual(subprocess.run(['/bin/bash','-n'],input=shell,capture_output=True,timeout=3).returncode,0)
            with patch.dict(bundle.PINS,{'scripts/community_preview_update_composition.py':'0'*64}):
                with self.assertRaises(ValueError):bundle.build()
            ns={'__name__':'readonly_isolated_bundle'};exec(compile(python,'<bundle>','exec'),ns)
            helpers=bundle.selected((bundle.ROOT/'scripts/community_preview_update_composition.py').read_text(),
                {'require','digest','canonical_isolation','stable_metadata','inspect_bound','PRIVATE_PROBE'})
            self.assertIn(repr(helpers),python.decode())
            ns['v'].ROOT_ANCHOR=str(self.root);ns['v'].ROOT_UID=os.getuid();ns['v'].PROJECT_UID=os.getuid()
            ns['v'].capture=self.capture;ns['wall']=p.wall
            self.assertEqual(ns['current_projection'](),p.current_projection())
            self.assertNotIn('mutate',ns['original'].__dict__);self.assertNotIn('compose',ns['approved'].__dict__)

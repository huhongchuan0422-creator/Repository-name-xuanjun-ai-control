"""Proposal tests, NOT_EXECUTED by author. Real classes/files/locks; Docker is recorded IO."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from scripts import community_preview_stopped_handoff as h
from scripts import community_preview_bc_build as build
from scripts import community_preview_site_prepare as s
from scripts import community_preview_update_checkpoint as u
from scripts import community_preview_update_composition as c
from scripts import community_preview_release_plan as p
import test_community_preview_upgrade as old

class WholeEntry(unittest.TestCase):
    tty_actual=False
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.clock=1000;self.running=False;self.new=False;self.calls=[];self.reads=[]
        self.names={p.NAME:s.OLD_ID};self.on_intent=None;self.on_run=None
        uid=os.getuid();gid=os.getgid();site_prepare_source=Path(s.__file__).read_bytes()
        base=self.root/'opt/xuanjun-community-preview';base.mkdir(parents=True,mode=0o700)
        data=self.root/'var/lib/xuanjun-community-preview'
        (data/'data').mkdir(parents=True,mode=0o700);(data/'config').mkdir(mode=0o700)
        for name in ('host.json','center-keys.json','wechat.json'):
            q=data/'config'/name;q.write_bytes(b'SYNTHETIC_PRIVATE_NOT_A_CREDENTIAL');q.chmod(0o600)
        q=data/'data'/'synthetic.db';q.write_bytes(b'SYNTHETIC_DATA');q.chmod(0o600)
        run=self.root/'run/xuanjun-community-preview';run.mkdir(parents=True,mode=0o700)
        for path in c.observation.ROUTE_PATHS.values():
            q=self.root/path.lstrip('/');q.parent.mkdir(parents=True,exist_ok=True)
            q.write_bytes(c.original.FRAGMENT if path==c.original.INC else b'RECORDED_ROUTE');q.chmod(0o600)
        journal=base/'update-journal';journal.mkdir(mode=0o700)
        for obj,values in (
            (s,dict(BASE=str(base),ENTRY=str(base/'site-prepare-v1.py'),PERMIT=str(base/'site-prepare-approval.json'),
                FREEZE=str(base/'writer-freeze-reference.json'),BACKUP=str(base/'backup-2330-to-f131-v1'),
                DATA=str(data),ROOT_ANCHOR=str(self.root),UID=uid,ROOT_GID=gid,ALLOWED_GIDS=(gid,1008))),
            (h,dict(CONTROL=str(base/'control-stopped-v1'),B_APPROVAL=str(base/'bc-b-approval.json'),
                C_APPROVAL=str(base/'bc-c-approval.json'),MANIFEST=str(base/'control-stopped-v1/manifest.json'),
                PROOF=str(base/'backup-2330-to-f131-v1/stopped-handoff-v1.json'))),
            (u,dict(JOURNAL_PARENT=str(journal),OWNER_UID=uid)),
            (c.observation,dict(ROOT_ANCHOR=str(self.root),ROOT_UID=uid,PROJECT_UID=uid)),
            (c,dict(REFERENCE_UID=uid))):
            for name,value in values.items():self.stack.enter_context(patch.object(obj,name,value))
        self.stack.enter_context(patch.object(h,'operator',return_value=(uid,gid)))
        self.stack.enter_context(patch.object(s,'__file__',str(base/'site-prepare-v1.py')))
        self.stack.enter_context(patch.object(c,'root_host'))
        self.stack.enter_context(patch.object(c,'now',side_effect=lambda:self.clock))
        self.stack.enter_context(patch.object(s.time,'time',side_effect=lambda:self.clock))
        self.stack.enter_context(patch.object(u.os,'getuid',return_value=0))
        self.stack.enter_context(patch.object(u.os,'geteuid',return_value=0))
        self.stack.enter_context(patch.object(u.os,'uname',return_value=type('Host',(),{'nodename':p.HOST})()))
        self.stack.enter_context(patch.object(s,'space'))  # Capacity is fixture, not UK proof.
        if not self.tty_actual:self.stack.enter_context(patch.object(h,'acknowledge'))
        self.write(s.ENTRY,site_prepare_source)
        archive,manifest,_=build.build()
        import zipfile
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for name in z.namelist():
                q=Path(h.CONTROL)/name;q.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                q.write_bytes(z.read(name));q.chmod(0o600)
        # Fixture path only. Real output always uses the fixed production path.
        m=s.exact_json(manifest);m['install_root']=h.CONTROL;self.write(h.MANIFEST,s.canonical(m))
        freeze=dict(format=1,host=p.HOST,old_id=s.OLD_ID,old_image=s.OLD_IMAGE,
            roots=[s.DATA+'/data',s.DATA+'/config'],issued_at=1000,expires_at=1600,
            all_writers_frozen=True,owner_review_reference_sha256='e'*64)
        self.write(s.FREEZE,s.canonical(freeze))
        b=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),carrier_manifest_sha256=s.sha(s.canonical(m)),
            issued_at=1000,expires_at=1600,freeze_sha256=s.sha(s.canonical(freeze)),actions=['SNAPSHOT','THREE_ISOLATED_CLONES'])
        self.write(h.B_APPROVAL,s.canonical(b))
        self.logical=dict(format=1,original_host_open=True,center_integrity=True,stores=[[['sample',1,'a'*64]]])
        self.original_capture=s.capture
        self.stack.enter_context(patch.object(s,'capture',side_effect=self.recorded_prepare))
        self.stack.enter_context(patch.object(c.observation,'capture',side_effect=self.recorded_observe))
        self.stack.enter_context(patch.object(c.original,'inspect',side_effect=self.inspect))
        self.stack.enter_context(patch.object(c.original,'command',side_effect=self.command))
        self.stack.enter_context(patch.object(c.original,'mutate',side_effect=self.mutate))
        self.stack.enter_context(patch.object(c,'socket_binding',return_value=dict(device=1,inode=2,uid=10001,gid=1008,mode=0o660,mtime_ns=1,ctime_ns=1)))
        real_readlink=os.readlink
        def readlink(path):
            value=real_readlink(path)
            return '/opt/xuanjun-community-preview/backup-2330-to-f131-v1/clone-results.json' if value==s.BACKUP+'/clone-results.json' else value
        self.stack.enter_context(patch.object(c.os,'readlink',side_effect=readlink))
        real_lstat=os.lstat
        self.stack.enter_context(patch.object(s.os,'lstat',side_effect=lambda path,*a,**kw:real_lstat(str(run/'preview.sock') if path==p.RUN+'/preview.sock' else path,*a,**kw)))
        self.session=h.Session();self.addCleanup(self.session.close);self.session.acquire()
    def write(self,path,raw):
        Path(path).write_bytes(raw);Path(path).chmod(0o600)
    def inspect(self,cid):
        if cid==s.OLD_ID:v=old.info(s.OLD_IMAGE,cid,self.running)
        elif cid=='9'*64:v=old.info(s.NEW_IMAGE,cid,self.new)
        else:raise u.Hold('UNRECORDED_OBJECT')
        v.update(ports={},published={},devices=[],capadd=[]);return v
    def recorded_prepare(self,argv,timeout=10):
        self.reads.append(argv)
        if argv[3:5]==['container','inspect']:
            self.assertEqual(argv[-1],p.NAME)
            if self.names.get(p.NAME)!=s.OLD_ID:raise u.Hold('ORIGINAL_STOPPED_NAME_REQUIRED')
            return '\n'.join(json.dumps(v) for v in (s.OLD_ID,s.OLD_IMAGE,self.running)).encode()
        self.assertEqual(argv[:4],s.DOCKER+['run']);self.assertEqual(argv[-1],s.CLONE_CODE)
        self.assertIn('none',argv);self.assertIn('--read-only',argv)
        return s.canonical(self.logical)
    def command(self,argv):
        if argv[3:5]==['image','inspect']:return '\n'.join(json.dumps(v) for v in (s.NEW_IMAGE,s.PRODUCT,'10001:1008'))
        self.assertEqual(argv[3:5],['container','ls']);return '\n'.join(self.names)
    def recorded_observe(self,argv,**kwargs):
        self.reads.append(argv)
        if argv[:3]==p.DOCKER:
            if argv[3:5]==['container','inspect']:
                if argv[-1]==p.NAME:
                    cid=self.names[p.NAME];v=self.inspect(cid);return '\n'.join(json.dumps(v[k]) for k in ('id','image'))
                v=self.inspect(argv[-1])
                fields=c.original.INSPECT_FIELDS+[('ports',''),('published',''),('devices',''),('capadd','')]
                return '\n'.join(json.dumps(v[k]) for k,_ in fields)
            if argv[3:5]==['image','inspect']:
                return '\n'.join(json.dumps(v) for v in (argv[-1],s.PRODUCT if argv[-1]==s.NEW_IMAGE else p.OBSERVED_OCI,'10001:1008'))
            if argv[3:5]==['container','ls']:
                return '\n'.join(json.dumps(dict(name=n,id=i)) for n,i in self.names.items())
            raise AssertionError('UNRECORDED_DOCKER_READ')
        self.assertEqual(argv,['/usr/bin/python3','-I','-B','-S','-c',c.observation.HTTP_PROBE])
        body=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
        return json.dumps(dict(http_status=200,body_hex=json.dumps(body).encode().hex()))
    def mutate(self,argv,timeout):
        self.calls.append(argv)
        action=argv[3]
        if action=='rename':
            oldname=next(n for n,i in self.names.items() if i==argv[-2]);del self.names[oldname];self.names[argv[-1]]=argv[-2]
        elif action=='run':
            if self.on_run:return self.on_run()
            self.new=True;self.names[p.NAME]='9'*64
            # Legitimate new writes MUST NOT be compared to the old snapshot.
            with open(s.DATA+'/data/synthetic.db','ab') as f:f.write(b'NEW_WRITE')
            return '9'*64
        elif action=='stop':
            if argv[-1]=='9'*64:self.new=False
            else:raise AssertionError('NO_EXTRA_STOP_OLD')
        elif action=='start':self.running=True
        else:raise AssertionError('UNRECORDED_MUTATION')
        return ''
    def prepare_b_and_c(self):
        self.session.run_b()
        real=self.session.candidate
        def bind(semantic):
            candidate=real(semantic)
            a=dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],
                carrier_manifest_sha256=self.session.pins(),plan_sha256=candidate['plan_sha256'],
                issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
            self.write(h.C_APPROVAL,s.canonical(a));return candidate
        self.stack.enter_context(patch.object(self.session,'candidate',side_effect=bind))
    def test_actual_b_classes_same_lease_to_c_success_no_old_stop_start(self):
        self.prepare_b_and_c();result=self.session.update()
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertEqual([x[3] for x in self.calls],['rename','run'])
        phases=[json.loads(Path(u.JOURNAL_PARENT,self.session.journal.plan['attempt'],n).read_bytes())['phase']
                for n in sorted(os.listdir(self.session.journal.fd)) if n.startswith('event-')]
        self.assertEqual(phases[:3],['PREPARED','STOPPED_HANDOFF_ACCEPTED','OLD_RENAME_INTENT'])
        self.assertNotIn('OLD_STOP_INTENT',phases);self.assertNotIn('OLD_STOPPED',phases)
    def test_default_off_and_no_forged_b_done(self):
        with patch.object(h.Session,'acquire') as acquire,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(h.main([]),2);acquire.assert_not_called()
        with self.assertRaisesRegex(u.Hold,'CONTINUOUS_B'):self.session.update()
        self.assertEqual(self.calls,[])
    def test_tree_drift_or_bad_clone_zero_c_mutation(self):
        self.prepare_b_and_c()
        Path(s.DATA+'/data/synthetic.db').write_bytes(b'DRIFT')
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.calls,[])
    def test_clone_body_forgery_zero_c_mutation(self):
        self.prepare_b_and_c();path=h.paths()['verify-f131'];row,_=h.document(path);row['result']['center_integrity']=False
        self.write(path,s.canonical(row))
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.calls,[])
    def test_wrong_host_id_image_or_expiry_zero_b_mutation(self):
        b,raw=h.document(h.B_APPROVAL)
        for key,value in (('host','other'),('attempt','other'),('expires_at',1)):
            wrong=dict(b,**{key:value});self.write(h.B_APPROVAL,s.canonical(wrong))
            with self.assertRaises(Exception):self.session.run_b()
            self.assertEqual(self.calls,[])
        self.write(h.B_APPROVAL,raw)
    def test_intent_then_old_revival_or_reference_replacement(self):
        self.prepare_b_and_c();write=u.Journal.write
        def publish(j,phase,*args):
            write(j,phase,*args)
            if phase=='OLD_RENAME_INTENT':self.running=True
        with patch.object(u.Journal,'write',publish),self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.calls,[])
    def test_revoked_c_after_durable_intent_zero_run(self):
        self.prepare_b_and_c();write=u.Journal.write
        def publish(j,phase,*args):
            write(j,phase,*args)
            if phase=='NEW_RUN_INTENT':Path(h.C_APPROVAL).unlink()
        with patch.object(u.Journal,'write',publish),self.assertRaises(u.Hold):self.session.update()
        self.assertEqual([x[3] for x in self.calls],['rename'])
    def test_unknown_newrun_never_start_old_or_retry(self):
        self.prepare_b_and_c();self.on_run=lambda:'UNKNOWN'
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.session.journal.state['phase'],u.HOLD_PHASE)
        count=len(self.calls)
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(len(self.calls),count);self.assertNotIn('start',[x[3] for x in self.calls])
    def test_same_plan_history_reopen_does_not_replay_and_partial_is_hold(self):
        self.prepare_b_and_c();self.session.update()
        candidate=self.session.journal.plan;binding=self.session.journal.handoff_binding
        self.session.journal.close();self.session.journal=None
        j=u.Journal(self.session.parent,candidate,lease_fd=self.session.lease,handoff_binding=binding)
        self.addCleanup(j.close);self.assertEqual(j.state['phase'],'COMMITTED')
        q=Path(u.JOURNAL_PARENT,candidate['attempt'],'event-000001.json');q.write_bytes(b'{partial')
        with self.assertRaises(u.Hold):j.validate_history()
    def test_lost_lock_pin_and_cleanup_are_hold(self):
        self.prepare_b_and_c()
        held=Path(u.JOURNAL_PARENT,'community-update.lock');held.rename(held.with_suffix('.retained'))
        held.write_bytes(b'');held.chmod(0o600)
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.calls,[])
    def test_known_failure_stopnew_unknown_cannot_startold(self):
        self.prepare_b_and_c()
        original=u.Update.replace_and_verify
        def known(updater):
            # Actual serial path executes; only the fixed remote response is recorded failure.
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        with patch.object(u.Update,'replace_and_verify',known),self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.session.journal.state['phase'],'KNOWN_FAILURE')
        hobj=h.VerifiedHandoff(self.session,h.document(h.PROOF)[0],self.session.journal)
        t=u.OriginalTransport(hobj.bindings,lambda:None)
        v=u.Update(self.session.journal,t,execution_enabled=True,clock=c.now,handoff=hobj)
        with patch.object(t,'mutate',side_effect=TimeoutError()),self.assertRaises(u.Hold):v.recover()
        self.assertNotIn('start',[x[3] for x in self.calls])
    def test_real_pty_production_ack_prompt_then_input_eof_timeout(self):
        import pty,select,time,signal,errno
        source="""import sys,os
sys.path.insert(0,REPO)
from scripts import community_preview_stopped_handoff as h
if SHORT:
 real=h.select.select
 h.select.select=lambda r,w,e,t:real(r,w,e,.1)
try:
 h.acknowledge('STOPPED_UPDATE','a'*64)
 print('ACK_OK',flush=True)
except BaseException:print('ACK_HOLD',flush=True)
print('PARENT_ALIVE',flush=True)
"""
        for mode in ('ok','eof','timeout'):
            code=source.replace('REPO',repr(str(Path.cwd()))).replace('SHORT',repr(mode=='timeout'))
            pid,fd=pty.fork()
            if pid==0:os.execv(sys.executable,[sys.executable,'-I','-B','-S','-c',code])
            data=b'';sent=False;done=False;end=time.monotonic()+4
            try:
                while time.monotonic()<end:
                    if select.select([fd],[],[],.05)[0]:
                        try:b=os.read(fd,65536)
                        except OSError as error:
                            if error.errno==errno.EIO:break
                            raise
                        if not b:break
                        data+=b
                        if not sent and b'APPROVE_STOPPED_UPDATE '+b'a'*64 in data and mode!='timeout':
                            os.write(fd,b'\x04' if mode=='eof' else b'APPROVE_STOPPED_UPDATE '+b'a'*64+b'\n');sent=True
                got,status=os.waitpid(pid,os.WNOHANG);done=got==pid
                self.assertTrue(done);self.assertEqual(os.waitstatus_to_exitcode(status),0)
                self.assertIn(b'ACK_OK' if mode=='ok' else b'ACK_HOLD',data);self.assertIn(b'PARENT_ALIVE',data)
            finally:
                if not done:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
                os.close(fd)

    def test_wrong_actual_id_image_or_socket_zero_mutation(self):
        real=self.inspect
        for key,value in (('id','1'*64),('image','sha256:'+'1'*64)):
            def bad(cid,key=key,value=value):return dict(real(cid),**{key:value})
            with patch.object(self,'inspect',side_effect=bad),self.assertRaises(Exception):
                c.inspect_bound(s.OLD_ID,s.OLD_IMAGE)
            self.assertEqual(self.calls,[])
        self.prepare_b_and_c()
        sock=self.root/'run/xuanjun-community-preview/preview.sock';sock.write_bytes(b'NOT_GONE')
        with self.assertRaises(Exception):self.session.update()
        self.assertEqual(self.calls,[])
    def test_same_bytes_reference_replaced_after_intent_rejected(self):
        self.prepare_b_and_c();write=u.Journal.write
        def publish(j,phase,*args):
            write(j,phase,*args)
            if phase=='OLD_RENAME_INTENT':
                path=Path(s.BACKUP,'clone-results.json');replacement=path.with_suffix('.replacement')
                replacement.write_bytes(path.read_bytes());replacement.chmod(0o600);os.replace(str(replacement),str(path))
        with patch.object(u.Journal,'write',publish),self.assertRaises(Exception):self.session.update()
        self.assertEqual(self.calls,[])
    def test_cleanup_error_attempts_every_owned_fd_and_reports_hold(self):
        fds=[self.session.entry,self.session.lease,self.session.parent];real=os.close;raised=[False]
        def close(fd):
            real(fd)
            if fd==fds[0] and not raised[0]:raised[0]=True;raise OSError('SYNTHETIC_CLEANUP')
        with patch.object(h.os,'close',side_effect=close),self.assertRaises(u.Hold):self.session.close()
        for fd in fds:
            with self.assertRaises(OSError):os.fstat(fd)
    def test_same_name_different_plan_and_source_pin_change_reject(self):
        self.prepare_b_and_c();self.session.update()
        candidate=copy.deepcopy(self.session.journal.plan)
        candidate['current']['routing_sha256']='0'*64
        candidate=p.prepare_stopped(candidate['source'],candidate['current'],candidate['image'])
        self.session.journal.close();self.session.journal=None
        with self.assertRaises(u.Hold):u.Journal(self.session.parent,candidate,lease_fd=self.session.lease,
            handoff_binding=dict(approval_sha256='a'*64,handoff_sha256='b'*64))
        path=Path(h.CONTROL,'scripts/community_preview_release_plan.py');path.write_bytes(path.read_bytes()+b'#tamper\n')
        with self.assertRaises(Exception):self.session.boundary()
    def test_generated_wrapper_complete_main_three_prompts_and_child_receipts(self):
        import pty,select,time,signal,errno,re,shlex
        _,_,commands=build.build()
        worker="""import sys
sys.path[:0]=[REPO,REPO+'/tests']
from test_community_preview_stopped_handoff import WholeEntry
from scripts import community_preview_stopped_handoff as h
from unittest.mock import patch
t=WholeEntry();t.tty_actual=True;t.setUp()
real=t.session.candidate
def candidate(e):
 p=real(e)
 t.write(h.C_APPROVAL,h.s.canonical(dict(format=1,host=h.p.HOST,mode=h.MODE,attempt=p['attempt'],
 carrier_manifest_sha256=t.session.pins(),plan_sha256=p['plan_sha256'],issued_at=t.clock,expires_at=t.clock+600,actions=h.C_ACTIONS)))
 return p
t.session.candidate=candidate
with patch.object(h,'Session',return_value=t.session),patch.object(t.session,'acquire'):
 raise SystemExit(h.main(['--owner-bc']))
""".replace('REPO',repr(str(Path.cwd())))
        fake=self.root/'sudo-tty';fake.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -I -B -S -c '+shlex.quote(worker)+'\n');fake.chmod(0o700)
        command=commands['owner-bc'].decode().replace('/usr/bin/sudo',str(fake))
        pid,fd=pty.fork()
        if pid==0:os.execv('/bin/bash',['/bin/bash','-c','set -e\n'+command+'\necho LOGIN_ALIVE\n'])
        data=b'';sent=set();done=False;end=time.monotonic()+15
        try:
            while time.monotonic()<end:
                if select.select([fd],[],[],.05)[0]:
                    try:b=os.read(fd,65536)
                    except OSError as error:
                        if error.errno==errno.EIO:break
                        raise
                    if not b:break
                    data+=b
                    for line in re.findall(rb'APPROVE_(?:SNAPSHOT|VALIDATE_CLONES|STOPPED_UPDATE) [0-9a-f]{64}',data):
                        if line not in sent:os.write(fd,line+b'\n');sent.add(line)
            got,status=os.waitpid(pid,os.WNOHANG);done=got==pid
            self.assertTrue(done);self.assertEqual(os.waitstatus_to_exitcode(status),0)
            records=[json.loads(x) for x in data.splitlines() if x.startswith(b'{')]
            result=next(x for x in records if x.get('state')=='BC_RESULT')
            outer=next(x for x in records if x.get('record')=='SUDO_CHILD_EXIT')
            self.assertEqual(result['child_exit'],outer['child_exit']);self.assertEqual(outer['child_exit'],0)
            self.assertEqual(result['result']['phase'],'COMMITTED');self.assertEqual(len(sent),3)
            self.assertIn(b'LOGIN_ALIVE',data)
        finally:
            if not done:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            os.close(fd)

    def test_expiry_after_intent_and_clone_failure_never_runs_new(self):
        self.prepare_b_and_c();write=u.Journal.write
        def publish(j,phase,*args):
            write(j,phase,*args)
            if phase=='OLD_RENAME_INTENT':self.clock=1601
        with patch.object(u.Journal,'write',publish),self.assertRaises(Exception):self.session.update()
        self.assertEqual(self.calls,[])
    def test_original_clone_failure_leaves_b_intent_without_handoff(self):
        with patch.object(self.session,'old_clone',side_effect=TimeoutError()),self.assertRaises(TimeoutError):
            self.session.run_b()
        self.assertTrue(Path(u.JOURNAL_PARENT,h.attempt()+'-B-intent.json').exists())
        self.assertFalse(Path(h.PROOF).exists());self.assertEqual(self.calls,[])

    def test_v1_builder_refuses_changed_sources_instead_of_overwriting_a(self):
        from scripts import community_preview_control_carrier as v1
        with self.assertRaisesRegex(ValueError,'FROZEN_V1_SOURCE_ONLY'):v1.build()

    def test_real_original_subprocess_preexec_guard_and_cleanup(self):
        # Actual original Popen/limits/waitid/kill/reap; only this finite local
        # stdout probe, never Docker/server. Existing IO mocks stay read-only.
        result=self.original_capture([sys.executable,'-I','-B','-S','-c','print("BOUNDED_LOCAL_PROBE")'],3)
        self.assertEqual(result.strip(),b'BOUNDED_LOCAL_PROBE')
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()


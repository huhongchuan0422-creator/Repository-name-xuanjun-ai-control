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
from unittest.mock import patch,Mock
from scripts import community_preview_stopped_handoff as h
from scripts import community_preview_bc_build as build
from scripts import community_preview_site_prepare as s
from scripts import community_preview_update_checkpoint as u
from scripts import community_preview_update_composition as c
from scripts import community_preview_release_plan as p
import test_community_preview_upgrade as old

A_SOURCE_COMMIT='1d639347f404f952998b3b414a95e48f66571c3c'
def frozen_a_source():
    return frozen.a_source()

try:
    from . import test_community_historical_fixtures as frozen
except ImportError:
    import test_community_historical_fixtures as frozen

class WholeEntry(unittest.TestCase):
    tty_actual=False
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.root.chmod(0o700)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.clock=1000;self.running=False;self.new=False;self.legacy_running=False;self.calls=[];self.reads=[]
        self.names={p.NAME:s.OLD_ID};self.on_intent=None;self.on_run=None
        uid=os.getuid();gid=os.getgid();site_prepare_source=frozen_a_source()
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
                B_RESUME_APPROVAL=str(base/'bc-b-resume-approval.json'),RESUME_FREEZE=str(base/'writer-freeze-resume-reference.json'),
                B_RESUME_STAGE_PERMIT=str(base/'site-prepare-resume-approval.json'),
                C_APPROVAL=str(base/'bc-c-approval.json'),C_RESUME_APPROVAL=str(base/'bc-c-resume-approval.json'),
                C_RESUME_PLAN=str(base/'backup-2330-to-f131-v1/c-preconfirmation-resume-plan.json'),
                MANIFEST=str(base/'control-stopped-v1/manifest.json'),
                PROOF=str(base/'backup-2330-to-f131-v1/stopped-handoff-v1.json'))),
            (u,dict(JOURNAL_PARENT=str(journal),OWNER_UID=uid)),
            (c.observation,dict(ROOT_ANCHOR=str(self.root),ROOT_UID=uid,PROJECT_UID=uid)),
            (c,dict(REFERENCE_UID=uid))):
            for name,value in values.items():self.stack.enter_context(patch.object(obj,name,value))
        self.stack.enter_context(patch.object(h,'operator',return_value=(uid,gid)))
        # Direct-unit fixture mirrors the real V2 loader's module identity; A ENTRY remains separate.
        self.stack.enter_context(patch.object(s,'__file__',str(Path(h.CONTROL)/'scripts/community_preview_site_prepare.py')))
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
        elif cid=='36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc':v=old.info('sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30',cid,self.legacy_running)
        else:raise u.Hold('UNRECORDED_OBJECT')
        v.update(ports={},published={},devices=[],capadd=[]);return v
    def recorded_prepare(self,argv,timeout=10):
        self.reads.append(argv)
        if argv[3:5]==['container','inspect']:
            self.assertEqual(argv[-1],p.NAME)
            if self.names.get(p.NAME)!=s.OLD_ID:raise u.Hold('ORIGINAL_STOPPED_NAME_REQUIRED')
            return '\n'.join(json.dumps(v) for v in (s.OLD_ID,s.OLD_IMAGE,self.running)).encode()
        if argv[3:5]==['container','ls']:
            self.assertEqual(argv[5:],['--all','--format','{{.Names}}'])
            return '\n'.join(sorted(self.names)).encode()
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
    def seed_partial_resume(self):
        # Preserve the original failed-attempt evidence, then create only fresh
        # resume authority/freeze on separate paths. No old record is rewritten.
        old_b,old_braw=h.document(h.B_APPROVAL);old_freeze,old_freeze_raw=h.document(s.FREEZE,16384)
        intent=dict(format=1,mode=h.MODE,attempt=h.attempt(),approval_sha256=s.sha(old_braw),freeze_sha256=s.sha(old_freeze_raw))
        self.write(h.b_records()['B-intent'],s.canonical(intent))
        self.clock=1700
        fresh=dict(old_freeze,issued_at=1700,expires_at=2300,owner_review_reference_sha256='f'*64)
        self.write(h.RESUME_FREEZE,s.canonical(fresh))
        resume=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),carrier_manifest_sha256=self.session.pins(),
            issued_at=1700,expires_at=2300,old_b_intent_sha256=s.sha(s.canonical(intent)),
            old_b_approval_sha256=s.sha(old_braw),old_freeze_sha256=s.sha(old_freeze_raw),old_stage_permit_sha256=None,
            resume_freeze_sha256=s.sha(s.canonical(fresh)),actions=['RESUME_SNAPSHOT','THREE_ISOLATED_CLONES'])
        self.write(h.B_RESUME_APPROVAL,s.canonical(resume))
        return intent,old_braw,old_freeze_raw,resume
    def fresh_session(self):
        self.session.close()
        q=h.Session();q.acquire();self.addCleanup(q.close);self.session=q;return q

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
    def _prepare_completed_b_before_c_proof(self):
        self.seed_partial_resume()
        q=self.fresh_session();q.resume_b_partial()
        self.assertTrue(q.bdone);self.assertEqual(set(q.captured),set(h.CLONES))
        if not Path(h.C_APPROVAL).exists():
            old_c=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
                carrier_manifest_sha256=self.session.pins(),plan_sha256='d50795e5cd54974c0acd7692d38da3c97e0ff1809a6a7c30d77dce2c24aabbea',
                issued_at=1,expires_at=2,actions=h.C_ACTIONS)
            self.write(h.C_APPROVAL,s.canonical(old_c))

        historical_paths=[h.B_RESUME_APPROVAL,h.resume_record_path(),h.B_APPROVAL,s.FREEZE,
            s.BACKUP+'/private-manifest.json',s.BACKUP+'/clone-results.json']+list(h.paths().values())+list(h.b_records().values())
        historical={path:Path(path).read_bytes() for path in historical_paths if Path(path).exists()}
        q.close();self.clock=2400
        for path,raw in historical.items():self.assertEqual(Path(path).read_bytes(),raw,'HISTORICAL_B_EVIDENCE_MUTATED')
        q=self.fresh_session();q.configure_resumed_b_context()
        self.assertFalse(q.bdone)
        return q,historical

    def _register_c_resume_approval_from_persisted_plan(self,q):
        record,_=h.document(h.C_RESUME_PLAN)
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=record['attempt'],
            carrier_manifest_sha256=q.pins(),plan_sha256=record['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        return record['plan']

    def test_c_preconfirmation_tty_mismatch_then_same_plan_resume_once(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        historical,_=h.document(s.BACKUP+'/clone-results.json')
        self.assertLess(historical['tested_at'],self.clock-600)
        self.assertTrue(q.c_preconfirm_mode)
        before_calls=len(self.calls)
        with patch.object(h,'acknowledge',side_effect=u.Hold('EXACT_CONFIRMATION_REQUIRED')):
            with self.assertRaisesRegex(u.Hold,'EXACT_CONFIRMATION_REQUIRED'):
                q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before_calls)
        self.assertFalse(Path(h.PROOF).exists())
        self.assertFalse(Path(u.JOURNAL_PARENT,'active-attempt.json').exists())
        self.assertFalse(Path(u.JOURNAL_PARENT,h.attempt()).exists())
        q.close()
        resumed=h.Session();resumed.acquire();self.addCleanup(resumed.close);self.session=resumed
        with patch.object(h,'acknowledge',return_value=None):
            result=resumed.resume_c_before_confirmation()
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertEqual(resumed.journal.plan['plan_sha256'],candidate['plan_sha256'])
        self.assertEqual([row[3] for row in self.calls[before_calls:]],['rename','run'])
        self.assertTrue(Path(h.PROOF).exists())
        self.assertTrue(Path(u.JOURNAL_PARENT,'active-attempt.json').exists())

    def test_c_preconfirmation_prints_full_plan_and_waits_for_distinct_fresh_approval(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        original=h.Session._c_resume_approval;seen=[]
        output=io.StringIO()
        def owner_approves(session,plan):
            if not Path(h.C_RESUME_APPROVAL).exists():
                printed=json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual(printed['plan_sha256'],plan['plan_sha256'])
                self.assertEqual(printed['plan'],plan)
                seen.append(printed)
                candidate=self._register_c_resume_approval_from_persisted_plan(session)
                self.assertEqual(candidate['plan_sha256'],plan['plan_sha256'])
            return original(session,plan)
        with patch.object(h.Session,'_c_resume_approval',owner_approves),contextlib.redirect_stdout(output):
            result=q.resume_c_before_confirmation()
        candidate=h.document(h.C_RESUME_PLAN)[0]['plan']
        self.assertIn('"plan":',output.getvalue())
        self.assertIn(candidate['attempt'],output.getvalue())
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertTrue(Path(h.C_APPROVAL).exists())
        self.assertTrue(Path(h.C_RESUME_PLAN).exists())
        self.assertTrue(Path(h.C_RESUME_APPROVAL).exists())

    def test_c_preconfirmation_wrong_plan_or_expired_approval_holds_zero_mutation(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        bad,_=h.document(h.C_RESUME_APPROVAL)
        self.write(h.C_RESUME_APPROVAL,s.canonical(dict(bad,plan_sha256='0'*64)))
        before=len(self.calls)
        with self.assertRaisesRegex(u.Hold,'EXACT_C_RESUME_APPROVAL_REQUIRED'):
            q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before)
        bad,_=h.document(h.C_RESUME_APPROVAL)
        self.write(h.C_RESUME_APPROVAL,s.canonical(dict(bad,issued_at=1,expires_at=2)))
        with self.assertRaises(u.Hold):q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before)
        self.assertFalse(Path(h.PROOF).exists())

    def test_expired_plan_and_approval_create_one_preserved_successor(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        candidate=q.candidate(semantic)
        first=q._fixed_c_resume_plan(candidate,semantic)
        original_plan_raw=Path(h.C_RESUME_PLAN).read_bytes()
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=first['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        original_approval_raw=Path(h.C_RESUME_APPROVAL).read_bytes()
        self.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
        fresh_semantic=q.evidence(True);fresh_candidate=q.candidate(fresh_semantic)
        successor=q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        self.assertEqual(Path(h.C_RESUME_PLAN).read_bytes(),original_plan_raw)
        self.assertEqual(Path(h.C_RESUME_APPROVAL).read_bytes(),original_approval_raw)
        self.assertEqual(successor['predecessor_plan_sha256'],first['plan_sha256'])
        self.assertEqual(successor['predecessor_plan_record_sha256'],s.sha(original_plan_raw))
        self.assertEqual(successor['predecessor_approval_sha256'],s.sha(original_approval_raw))
        self.assertNotEqual(successor['plan_sha256'],first['plan_sha256'])
        successor_path=Path(q.c_resume_plan_path)
        self.assertTrue(successor_path.exists())
        before=successor_path.read_bytes()
        same=q._fixed_c_resume_plan(q.candidate(q.evidence(True)),q.evidence(True))
        self.assertEqual(same['plan_sha256'],successor['plan_sha256'])
        self.assertEqual(successor_path.read_bytes(),before)
        self.assertNotEqual(q.c_resume_approval_path,h.C_RESUME_APPROVAL)
        with self.assertRaises(FileNotFoundError):q._c_resume_approval(successor)
        successor_approval=dict(format=2,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
            predecessor_plan_sha256=successor['predecessor_plan_sha256'],
            predecessor_approval_sha256=successor['predecessor_approval_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(q.c_resume_approval_path,s.canonical(successor_approval))
        self.assertEqual(q._c_resume_approval(successor)['plan_sha256'],successor['plan_sha256'])
        # Once the operation-specific approval is bound, every later boundary
        # must re-read that exact path rather than the fixed predecessor path.
        q.boundary()

    def test_expired_successor_keeps_historical_carrier_and_binds_current_manifest(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        first=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        historical_carrier=q.approved_stamp
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=historical_carrier,plan_sha256=first['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        self.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
        current_carrier='f'*64
        q.approved_stamp=current_carrier
        with patch.object(q,'pins',return_value=current_carrier):
            fresh_semantic=q.evidence(True);fresh_candidate=q.candidate(fresh_semantic)
            successor=q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        self.assertEqual(h.document(h.C_RESUME_PLAN)[0]['carrier_manifest_sha256'],historical_carrier)
        self.assertEqual(successor['carrier_manifest_sha256'],current_carrier)
        self.assertEqual(h.document(q.c_resume_plan_path)[0]['carrier_manifest_sha256'],current_carrier)

    def test_expired_successor_rejects_execution_trace_and_stable_drift(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        first=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=first['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        self.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
        fresh_semantic=q.evidence(True);fresh_candidate=q.candidate(fresh_semantic)
        active=Path(u.JOURNAL_PARENT)/'active-attempt.json';self.write(str(active),b'{}')
        with self.assertRaisesRegex(u.Hold,'C_SUCCESSOR_EXECUTION_TRACE_PRESENT'):
            q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        active.unlink()
        attempt_dir=Path(u.JOURNAL_PARENT)/h.attempt();attempt_dir.mkdir(mode=0o700)
        with self.assertRaisesRegex(u.Hold,'C_SUCCESSOR_EXECUTION_TRACE_PRESENT'):
            q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        attempt_dir.rmdir()
        changed=copy.deepcopy(fresh_candidate);changed['current']['routing_sha256']='0'*64
        with self.assertRaisesRegex(u.Hold,'C_SUCCESSOR_STABLE_PLAN_CHANGED'):
            q._fixed_c_resume_plan(changed,fresh_semantic)

    def test_successor_predecessor_replacement_or_second_expiry_holds(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        first=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=first['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        self.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
        fresh_semantic=q.evidence(True);fresh_candidate=q.candidate(fresh_semantic)
        successor=q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        successor_path=q.c_resume_plan_path;successor_raw=Path(successor_path).read_bytes()
        successor_approval=dict(format=2,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
            predecessor_plan_sha256=successor['predecessor_plan_sha256'],
            predecessor_approval_sha256=successor['predecessor_approval_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(q.c_resume_approval_path,s.canonical(successor_approval))
        self.clock=h.document(successor_path)[0]['expires_at']+1;q.last=None
        fresh_semantic=q.evidence(True);fresh_candidate=q.candidate(fresh_semantic)
        current_carrier='f'*64;q.approved_stamp=current_carrier
        active=Path(u.JOURNAL_PARENT)/'active-attempt.json';self.write(str(active),b'{}')
        with patch.object(q,'pins',return_value=current_carrier):
            with self.assertRaisesRegex(u.Hold,'C_SUCCESSOR_EXECUTION_TRACE_PRESENT'):
                q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        active.unlink()
        with patch.object(q,'pins',return_value=current_carrier):
            reopened=q._fixed_c_resume_plan(fresh_candidate,fresh_semantic)
        self.assertEqual(reopened['plan_sha256'],successor['plan_sha256'])
        self.assertEqual(q.c_resume_plan_path,successor_path)
        self.assertEqual(Path(successor_path).read_bytes(),successor_raw)

        self.assertIn('successor-renewal-',q.c_resume_approval_path)
        renewal=dict(format=3,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=current_carrier,plan_sha256=successor['plan_sha256'],
            predecessor_plan_sha256=successor['predecessor_plan_sha256'],
            predecessor_approval_sha256=successor['predecessor_approval_sha256'],
            successor_plan_record_sha256=s.sha(successor_raw),
            successor_approval_sha256=s.sha(s.canonical(successor_approval)),
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(q.c_resume_approval_path,s.canonical(renewal))
        with patch.object(q,'pins',return_value=current_carrier):
            self.assertEqual(q._c_resume_approval(reopened)['format'],3)
        self.clock=renewal['expires_at']+1;q.last=None
        with patch.object(q,'pins',return_value=current_carrier):
            with self.assertRaisesRegex(u.Hold,'APPROVAL_EXPIRED'):
                q._c_resume_approval(reopened)
        self.assertEqual(Path(successor_path).read_bytes(),successor_raw)


    def test_c_preconfirmation_observed_at_drift_reuses_persisted_approved_plan(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        before=len(self.calls)
        self.clock += 1
        real=c.read_current
        def drift(*args,**kwargs):
            value=real(*args,**kwargs)
            value=dict(value,observed_at=value['observed_at']+1)
            return value
        with patch.object(c,'read_current',side_effect=drift):
            result=q.resume_c_before_confirmation()
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertEqual(q.journal.plan['plan_sha256'],candidate['plan_sha256'])
        self.assertGreater(len(self.calls),before)
        self.assertTrue(Path(h.PROOF).exists())
        self.assertTrue(Path(u.JOURNAL_PARENT,'active-attempt.json').exists())

    def test_c_preconfirmation_missing_b_evidence_or_c_sideeffect_holds(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        path=h.paths()['verify-f131'];saved=Path(path).read_bytes();Path(path).unlink()
        before=len(self.calls)
        with self.assertRaises(Exception):q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before);self.assertFalse(Path(h.PROOF).exists())
        self.write(path,saved)
        q.close()
        q=h.Session();q.acquire();self.addCleanup(q.close);self.session=q
        self.write(u.JOURNAL_PARENT+'/active-attempt.json',
                   s.canonical(dict(attempt=h.attempt(),plan_sha256=candidate['plan_sha256'])))
        with self.assertRaisesRegex(u.Hold,'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY'):
            q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before)

    def test_c_preconfirmation_c_approval_revoked_during_tty_wait_holds_before_proof(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        before=len(self.calls)
        def revoke(_action,_digest):
            value,_=h.document(h.C_RESUME_APPROVAL)
            self.write(h.C_RESUME_APPROVAL,s.canonical(dict(value,plan_sha256='0'*64)))
        with patch.object(h,'acknowledge',side_effect=revoke):
            with self.assertRaisesRegex(u.Hold,'C_APPROVAL_REVOKED|EXACT_C_RESUME_APPROVAL_REQUIRED|B_RESUME_REFERENCE_REPLACED'):
                q.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before)
        self.assertFalse(Path(h.PROOF).exists())
        self.assertFalse(Path(u.JOURNAL_PARENT,'active-attempt.json').exists())

    def test_real_c_resume_known_failure_reopens_and_recovers_with_new_approval(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        self.assertFalse(Path(h.C_RESUME_PLAN).exists());self.assertFalse(Path(h.C_RESUME_APPROVAL).exists())
        real_monotonic=h.time.monotonic
        deadline_reads=[0]
        def monotonic():
            import inspect
            if inspect.currentframe().f_back.f_code.co_name=='resume_c_before_confirmation':
                deadline_reads[0]+=1
                return 0 if deadline_reads[0]==1 else 121
            return real_monotonic()
        with patch.object(h.time,'monotonic',new=monotonic),patch.object(h.time,'sleep',return_value=None):
            with self.assertRaisesRegex(u.Hold,'C_RESUME_APPROVAL_NOT_RECEIVED'):
                q.resume_c_before_confirmation()
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        original=u.Update.replace_and_verify
        def known(updater):
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        before_calls=len(self.calls)
        with patch.object(h,'acknowledge',return_value=None),\
             patch.object(u.Update,'replace_and_verify',known),\
             self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            q.resume_c_before_confirmation()
        self.assertTrue(Path(h.PROOF).exists())
        proof=h.document(h.PROOF)[0]
        self.assertEqual(proof['approval_kind'],'C_RESUME_APPROVAL')
        self.assertEqual(proof['plan']['plan_sha256'],candidate['plan_sha256'])
        self.assertTrue(Path(u.JOURNAL_PARENT,'active-attempt.json').exists())
        self.assertGreater(len(self.calls),before_calls)
        q.close()
        reopened=h.Session();reopened.acquire(recover=True)
        self.addCleanup(reopened.close);self.session=reopened
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=None,version_source=None,observed_at=self.clock)
        with patch.object(h,'acknowledge',return_value=None), \
             patch.object(c,'BoundHttpsHealth',return_value=old_health):
            result=reopened.recover()
        self.assertIn(result['phase'],('ROLLED_BACK_PREVIEW_HOLD','COMMITTED'))
        self.assertEqual(reopened.journal.plan['plan_sha256'],candidate['plan_sha256'])
        self.assertEqual(proof['approval_sha256'],s.sha(Path(h.C_RESUME_APPROVAL).read_bytes()))
        self.assertEqual(Path(h.C_APPROVAL).read_bytes(),
            s.canonical(dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],
                carrier_manifest_sha256=q.pins(),plan_sha256='d50795e5cd54974c0acd7692d38da3c97e0ff1809a6a7c30d77dce2c24aabbea',
                issued_at=1,expires_at=2,actions=h.C_ACTIONS)))
        self.assertNotIn('snapshot',[x[3] for x in self.calls[before_calls:]])
        self.assertNotIn('clone',[x[3] for x in self.calls[before_calls:]])

    def test_successor_dynamic_approval_survives_tty_known_failure_reopen_recovery(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        first=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        predecessor=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=first['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(predecessor))
        self.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
        fresh_semantic=q.evidence(True);successor=q._fixed_c_resume_plan(
            q.candidate(fresh_semantic),fresh_semantic)
        successor_path=q.c_resume_approval_path
        approval=dict(format=2,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
            predecessor_plan_sha256=successor['predecessor_plan_sha256'],
            predecessor_approval_sha256=successor['predecessor_approval_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(successor_path,s.canonical(approval))
        q.backup=None
        original=u.Update.replace_and_verify
        def known(updater):
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        confirmations=[]
        with patch.object(h,'acknowledge',side_effect=lambda action,digest:confirmations.append((action,digest))), \
             patch.object(u.Update,'replace_and_verify',known), \
             self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            q.resume_c_before_confirmation()
        proof=h.document(h.PROOF)[0]
        self.assertEqual(proof['approval_path'],successor_path)
        self.assertEqual(proof['approval_sha256'],s.sha(Path(successor_path).read_bytes()))
        self.assertEqual(confirmations[0],('STOPPED_UPDATE',successor['plan_sha256']))
        q.close()
        reopened=h.Session();reopened.acquire(recover=True)
        self.addCleanup(reopened.close);self.session=reopened
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=None,version_source=None,observed_at=self.clock)
        with patch.object(h,'acknowledge',side_effect=lambda action,digest:confirmations.append((action,digest))), \
             patch.object(c,'BoundHttpsHealth',return_value=old_health):
            result=reopened.recover()
        self.assertIn(result['phase'],('ROLLED_BACK_PREVIEW_HOLD','COMMITTED'))
        self.assertEqual(reopened.c_resume_approval_path,successor_path)
        self.assertEqual(reopened.craw,Path(successor_path).read_bytes())
        self.assertEqual(confirmations[-1],('KNOWN_FAILURE_RECOVER',successor['plan_sha256']))
        self.assertNotEqual(successor_path,h.C_RESUME_APPROVAL)

    def test_recovery_rejects_unbound_dynamic_approval_path_before_consume(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        candidate={'attempt':h.attempt(),'plan_sha256':'a'*64,
            'predecessor_plan_sha256':'b'*64}
        proof={'format':1,'mode':h.MODE,'host':p.HOST,'attempt':h.attempt(),
            'plan':candidate,'approval_sha256':'c'*64,'evidence':{},
            'approval_kind':'C_RESUME_APPROVAL','approval_path':str(self.root/'forged.json')}
        with self.assertRaisesRegex(u.Hold,'C_SUCCESSOR_PLAN_REQUIRED_FOR_RECOVERY'):
            q._restore_c_resume_paths(proof)

    def test_independent_correction_reissue_real_pty_execute_and_recovery(self):
        """One expired correction is preserved; its unique reissue crosses both real TTY boundaries."""
        import pty,select,time,signal,errno,re
        worker="""import sys
sys.path[:0]=[REPO,REPO+'/tests']
from unittest.mock import patch
from test_community_preview_stopped_handoff import WholeEntry
from scripts import community_preview_stopped_handoff as h
from scripts import community_preview_site_prepare as s
from scripts import community_preview_update_checkpoint as u
from scripts import community_preview_update_composition as c
from scripts import community_preview_release_plan as p
t=WholeEntry();t.tty_actual=True;t.setUp()
try:
 with patch.object(h,'acknowledge'):
  q,_=t._prepare_completed_b_before_c_proof()
 semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
 first=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 predecessor=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=first['plan_sha256'],
  issued_at=t.clock,expires_at=t.clock+600,actions=h.C_ACTIONS)
 t.write(h.C_RESUME_APPROVAL,s.canonical(predecessor))
 t.clock=h.document(h.C_RESUME_PLAN)[0]['expires_at']+1;q.last=None
 semantic=q.evidence(True);successor=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 successor_record,successor_raw=h.document(q.c_resume_plan_path,4*1024*1024)
 successor_approval_path=q.c_resume_approval_path
 successor_approval=dict(format=2,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
  predecessor_plan_sha256=successor['predecessor_plan_sha256'],
  predecessor_approval_sha256=successor['predecessor_approval_sha256'],
  issued_at=t.clock,expires_at=t.clock+600,actions=h.C_ACTIONS)
 t.write(successor_approval_path,s.canonical(successor_approval))
 t.clock=successor_record['expires_at']+1;q.last=None
 semantic=q.evidence(True);successor=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 renewal_path=q.c_resume_approval_path
 renewal=dict(format=3,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
  predecessor_plan_sha256=successor['predecessor_plan_sha256'],
  predecessor_approval_sha256=successor['predecessor_approval_sha256'],
  successor_plan_record_sha256=s.sha(successor_raw),
  successor_approval_sha256=s.sha(s.canonical(successor_approval)),
  issued_at=t.clock,expires_at=t.clock+600,actions=h.C_ACTIONS)
 t.write(renewal_path,s.canonical(renewal))
 t.clock=renewal['expires_at']+1;q.last=None
 semantic=q.evidence(True);successor=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 recovery_path=q.c_resume_approval_path
 assert 'successor-recovery-' in recovery_path
 recovery=dict(format=4,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
  predecessor_plan_sha256=successor['predecessor_plan_sha256'],
  predecessor_approval_sha256=successor['predecessor_approval_sha256'],
  successor_plan_record_sha256=s.sha(successor_raw),
  successor_approval_sha256=s.sha(s.canonical(renewal)),
  issued_at=t.clock,expires_at=t.clock+600,actions=h.C_ACTIONS)
 recovery_raw=s.canonical(recovery);t.write(recovery_path,recovery_raw)
 t.clock=recovery['expires_at']+1;q.last=None
 semantic=q.evidence(True);successor=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 correction_path=q.c_resume_approval_path
 assert 'successor-independent-correction-' in correction_path and not h.exists_private(correction_path)
 correction=dict(format=1,kind=h.CORRECTION_KIND,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
  predecessor_plan_sha256=successor['predecessor_plan_sha256'],
  predecessor_plan_record_sha256=successor['predecessor_plan_record_sha256'],
  predecessor_approval_sha256=successor['predecessor_approval_sha256'],
  successor_plan_record_sha256=s.sha(successor_raw),
  successor_approval_sha256=s.sha(s.canonical(successor_approval)),
  successor_renewal_sha256=s.sha(s.canonical(renewal)),
  successor_recovery_sha256=s.sha(recovery_raw),issued_at=t.clock,expires_at=t.clock+600,
  actions=h.C_ACTIONS)
 correction_raw=s.canonical(correction);t.write(correction_path,correction_raw)
 t.clock=correction['expires_at']+1;q.last=None
 semantic=q.evidence(True);successor=q._fixed_c_resume_plan(q.candidate(semantic),semantic)
 reissue_path=q.c_resume_approval_path
 assert 'successor-independent-correction-reissue-' in reissue_path and not h.exists_private(reissue_path)
 reissue=dict(format=1,kind=h.CORRECTION_REISSUE_KIND,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
  carrier_manifest_sha256=q.pins(),plan_sha256=successor['plan_sha256'],
  predecessor_plan_sha256=successor['predecessor_plan_sha256'],
  predecessor_plan_record_sha256=successor['predecessor_plan_record_sha256'],
  predecessor_approval_sha256=successor['predecessor_approval_sha256'],
  successor_plan_record_sha256=s.sha(successor_raw),
  successor_approval_sha256=s.sha(s.canonical(successor_approval)),
  successor_renewal_sha256=s.sha(s.canonical(renewal)),
  successor_recovery_sha256=s.sha(recovery_raw),
  successor_correction_sha256=s.sha(correction_raw),issued_at=t.clock,expires_at=t.clock+600,
  actions=h.C_ACTIONS)
 t.write(reissue_path,s.canonical(reissue));q.backup=None
 original=u.Update.replace_and_verify
 def known(updater):
  updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
   scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
   runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=t.clock)
  return original(updater)
 try:
  with patch.object(u.Update,'replace_and_verify',known):q.resume_c_before_confirmation()
  raise AssertionError('KNOWN_FAILURE_REQUIRED')
 except u.Hold as error:
  assert 'KNOWN_FAILURE' in str(error)
 proof=h.document(h.PROOF)[0]
 assert proof['approval_path']==reissue_path and proof['approval_sha256']==s.sha(open(reissue_path,'rb').read())
 q.close()
 reopened=h.Session();reopened.acquire(recover=True);t.session=reopened
 old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
  scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
  runtime_source_sha=None,version_source=None,observed_at=t.clock)
 with patch.object(c,'BoundHttpsHealth',return_value=old_health):result=reopened.recover()
 assert result['phase'] in ('ROLLED_BACK_PREVIEW_HOLD','COMMITTED')
 assert reopened.c_resume_approval_path==reissue_path and reopened.craw==open(reissue_path,'rb').read()
 assert open(recovery_path,'rb').read()==recovery_raw
 assert open(correction_path,'rb').read()==correction_raw
 print('INDEPENDENT_CORRECTION_REISSUE_REAL_PTY_CHAIN_OK',flush=True)
finally:
 t.doCleanups()
""".replace('REPO',repr(str(Path.cwd())))
        pid,fd=pty.fork()
        if pid==0:os.execv(sys.executable,[sys.executable,'-I','-B','-S','-c',worker])
        data=b'';sent=[];done=False;end=time.monotonic()+30
        try:
            while time.monotonic()<end:
                if select.select([fd],[],[],.05)[0]:
                    try:b=os.read(fd,65536)
                    except OSError as error:
                        if error.errno==errno.EIO:break
                        raise
                    if not b:break
                    data+=b
                    for line in re.findall(rb'APPROVE_(?:STOPPED_UPDATE|KNOWN_FAILURE_RECOVER) [0-9a-f]{64}',data):
                        if line not in sent:os.write(fd,line+b'\n');sent.append(line)
            got,status=os.waitpid(pid,0 if b'INDEPENDENT_CORRECTION_REISSUE_REAL_PTY_CHAIN_OK' in data else os.WNOHANG);done=got==pid
            self.assertTrue(done,data.decode(errors='replace'))
            self.assertEqual(os.waitstatus_to_exitcode(status),0,data.decode(errors='replace'))
            self.assertEqual([x.split()[0] for x in sent],
                [b'APPROVE_STOPPED_UPDATE',b'APPROVE_KNOWN_FAILURE_RECOVER'])
            self.assertIn(b'INDEPENDENT_CORRECTION_REISSUE_REAL_PTY_CHAIN_OK',data)
        finally:
            if not done:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            os.close(fd)

    def test_known_failure_recovery_uses_new_c_resume_approval_provenance(self):
        q=self.fresh_session()
        candidate={'attempt':h.attempt(),'plan_sha256':'a'*64}
        proof={'format':1,'mode':h.MODE,'host':p.HOST,'attempt':h.attempt(),
            'plan':candidate,'approval_sha256':'b'*64,'evidence':{},'approval_kind':'C_RESUME_APPROVAL',
            'approval_path':h.C_RESUME_APPROVAL}
        owned_path=self.root/'owned-recovery-backup';owned_path.write_bytes(b'isolated-backup-fd')
        owned_fd=os.open(str(owned_path),os.O_RDONLY|os.O_NOFOLLOW)
        # The Session owns and closes this descriptor; do not register a second close.
        with patch.object(h,'document',return_value=(proof,b'proof')),\
             patch.object(q,'configure_resumed_recovery',return_value=True),\
             patch.object(h,'open_private',return_value=owned_fd),\
             patch.object(q,'_c_resume_approval',return_value={'ok':True}) as fresh_approval,\
             patch.object(q,'c_approval',side_effect=AssertionError('old C approval must not be used')),\
             patch.object(h,'acknowledge'),\
             patch.object(q,'consume',return_value={'phase':'KNOWN_FAILURE_RECOVERED'}) as consume:
            result=q.recover()
        self.assertEqual(result['phase'],'KNOWN_FAILURE_RECOVERED')
        fresh_approval.assert_called_once_with(candidate)
        self.assertTrue(q.c_preconfirm_mode)
        consume.assert_called_once_with(proof,True)

    def test_c_preconfirmation_duplicate_call_after_commit_is_rejected(self):
        q,historical=self._prepare_completed_b_before_c_proof()
        original=h.Session._c_resume_approval
        output=io.StringIO()
        def owner_approves(session,plan):
            if not Path(h.C_RESUME_APPROVAL).exists():
                printed=json.loads(output.getvalue().splitlines()[-1])
                self.assertEqual(printed['plan_sha256'],plan['plan_sha256'])
                candidate=self._register_c_resume_approval_from_persisted_plan(session)
                self.assertEqual(candidate['plan_sha256'],plan['plan_sha256'])
            return original(session,plan)
        with patch.object(h.Session,'_c_resume_approval',owner_approves), \
             patch.object(h,'acknowledge',return_value=None),contextlib.redirect_stdout(output):
            result=q.resume_c_before_confirmation()
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertTrue(Path(h.C_RESUME_PLAN).exists());self.assertTrue(Path(h.C_RESUME_APPROVAL).exists())
        self.assertTrue(Path(h.C_APPROVAL).exists())
        before=len(self.calls);q.close()
        second=h.Session();second.acquire();self.addCleanup(second.close);self.session=second
        with self.assertRaisesRegex(u.Hold,'C_ALREADY_STARTED_INSPECT_ORIGINAL_RECOVERY'):
            second.resume_c_before_confirmation()
        self.assertEqual(len(self.calls),before)

    def test_c_preconfirmation_cli_dispatches_exact_mode_without_b_or_recover(self):
        class FakeSession:
            def __init__(self):self.acquired=None;self.called=0;self.closed=False
            def acquire(self,recover=False):self.acquired=recover
            def resume_c_before_confirmation(self):self.called+=1;return {'phase':'COMMITTED'}
            def close(self):self.closed=True
        fake=FakeSession()
        with patch.object(h,'Session',return_value=fake),contextlib.redirect_stdout(io.StringIO()):
            code=h.main(['--resume-c-before-confirmation'])
        self.assertEqual(code,0)
        self.assertFalse(fake.acquired)
        self.assertEqual(fake.called,1)
        self.assertTrue(fake.closed)

    def test_prepared_reopen_cli_dispatches_only_exact_reopen_mode(self):
        class FakeSession:
            def __init__(self):self.acquired=None;self.called=0;self.closed=False
            def acquire(self,recover=False):self.acquired=recover
            def reopen_prepared(self):self.called+=1;return {'phase':'COMMITTED'}
            def close(self):self.closed=True
        fake=FakeSession()
        with patch.object(h,'Session',return_value=fake),contextlib.redirect_stdout(io.StringIO()):
            code=h.main(['--reopen-prepared'])
        self.assertEqual(code,0);self.assertTrue(fake.acquired)
        self.assertEqual(fake.called,1);self.assertTrue(fake.closed)

    def test_update_prepared_reopen_requires_exact_sequence_one_then_uses_stopped_path(self):
        state=dict(phase='PREPARED',sequence=1,new_id=None)
        journal=Mock(state=state,read=Mock(return_value=dict(state)),validate_history=Mock())
        update=object.__new__(u.Update);update.journal=journal
        with patch.object(u.Update,'run_stopped',return_value={'phase':'COMMITTED'}) as run:
            self.assertEqual(update.reopen_prepared_stopped()['phase'],'COMMITTED')
        journal.validate_history.assert_called_once_with();run.assert_called_once_with()
        for changed in (dict(state,sequence=2),dict(state,phase='KNOWN_FAILURE'),dict(state,new_id='9'*64)):
            journal.state=changed;journal.read.return_value=dict(changed)
            with self.assertRaisesRegex(u.Hold,'EXACT_PREPARED_REOPEN_REQUIRED'):
                update.reopen_prepared_stopped()

    def test_reviewed_shared_vhost_transition_keeps_exact_community_route(self):
        # PREPARED resume scope: the P2-owned vhost may take this one reviewed
        # transition, while the community-owned include remains byte-exact.
        saved={'routing_sha256':c.ROUTE_TRANSITION['saved_routing_sha256']}
        live={'routing_sha256':c.ROUTE_TRANSITION['live_routing_sha256']}
        marker=b'include /etc/nginx/community-preview.inc;'
        def route(path,body=False):
            if path==c.observation.ROUTE_PATHS['community_route']:
                return ({'sha256':c.ROUTE_TRANSITION['community_sha256']},b'community')
            return ({'sha256':c.ROUTE_TRANSITION['shared_vhost_sha256']},b'server { '+marker+b' }')
        with patch.object(c.observation,'safe_file',side_effect=route), \
             patch.object(c.original,'command',return_value='') as nginx:
            self.assertTrue(c.stopped_route_transition(saved,live))
        nginx.assert_called_once_with(['/usr/sbin/nginx','-t'])

    def test_reviewed_shared_vhost_transition_denies_unbound_or_missing_include(self):
        saved={'routing_sha256':c.ROUTE_TRANSITION['saved_routing_sha256']}
        live={'routing_sha256':c.ROUTE_TRANSITION['live_routing_sha256']}
        def route(path,body=False):
            key='community_sha256' if path==c.observation.ROUTE_PATHS['community_route'] else 'shared_vhost_sha256'
            return ({'sha256':c.ROUTE_TRANSITION[key]},b'no include')
        with patch.object(c.observation,'safe_file',side_effect=route),patch.object(c.original,'command') as nginx:
            self.assertFalse(c.stopped_route_transition(saved,live))
            self.assertFalse(c.stopped_route_transition({'routing_sha256':'0'*64},live))
        nginx.assert_not_called()

    def test_expired_artifact_window_allows_only_bound_prepared_reopen_with_exact_loaded_image(self):
        # Remote artifact retention expiry is not expiry of the exact verified local image.
        q=self.session
        self.clock=s.EXPIRES
        with self.assertRaisesRegex(u.Hold,'FROZEN_IMAGE_ARTIFACT_EXPIRED'):
            q.frozen_image_boundary(self.clock)
        q.recovering=True;q.prepared_reopen_raw=b'BOUND_SEPARATE_PREPARED_REOPEN'
        q.frozen_image_boundary(self.clock)
        with patch.object(c.observation,'capture',return_value=b'"sha256:bad"\n"bad"\n"0:0"'):
            with self.assertRaisesRegex(u.Hold,'EXACT_LOADED_IMAGE_REQUIRED'):
                q.frozen_image_boundary(self.clock)

    def test_persisted_prepared_reopens_same_attempt_with_separate_exact_authority(self):
        q,_=self._prepare_completed_b_before_c_proof()
        # Persist the dynamic plan first, then register its ordinary approval.
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        original_guard=u.Update.guard;first=[True]
        def transient(update,running):
            if first[0]:first[0]=False;raise u.Hold('PROTECTED_BINDING_CHANGED')
            return original_guard(update,running)
        with patch.object(u.Update,'guard',transient),self.assertRaisesRegex(u.Hold,'PROTECTED_BINDING_CHANGED'):
            q.resume_c_before_confirmation()
        self.assertEqual(q.journal.state['phase'],'PREPARED');self.assertEqual(q.journal.state['sequence'],1)
        self.assertEqual(self.calls,[])
        proof,proof_raw=h.document(h.PROOF);prior=proof['approval_sha256']
        # Exercise the real production path that previously passed Update.guard
        # but was rejected a second time by VerifiedHandoff.check.  Only the
        # separately-owned shared vhost changes; the community include is exact.
        community_path=self.root/c.observation.ROUTE_PATHS['community_route'].lstrip('/')
        shared_path=self.root/c.observation.ROUTE_PATHS['shared_vhost_file_digest_only'].lstrip('/')
        shared_raw=b'server { include /etc/nginx/community-preview.inc; }\n'
        shared_path.write_bytes(shared_raw);shared_path.chmod(0o600)
        community_raw=community_path.read_bytes()
        route_hashes={
            c.observation.ROUTE_PATHS['community_route']:s.sha(community_raw),
            c.observation.ROUTE_PATHS['shared_vhost_file_digest_only']:s.sha(shared_raw),
        }
        transition=dict(saved_routing_sha256=proof['plan']['current']['routing_sha256'],
            live_routing_sha256=c.digest(route_hashes),community_sha256=s.sha(community_raw),
            shared_vhost_sha256=s.sha(shared_raw))
        self.stack.enter_context(patch.object(c,'ROUTE_TRANSITION',transition))
        def route_command(argv):
            if argv==['/usr/sbin/nginx','-t']:return ''
            return self.command(argv)
        self.stack.enter_context(patch.object(c.original,'command',side_effect=route_command))
        q.close();self.clock=h.document(h.C_RESUME_APPROVAL)[0]['expires_at']+1
        reopened=h.Session();reopened.acquire(recover=True);self.addCleanup(reopened.close);self.session=reopened
        reopened.configure_resumed_recovery(proof);reopened.approved_stamp=reopened.pins()
        active=Path(u.JOURNAL_PARENT,'active-attempt.json').read_bytes()
        checkpoint=Path(u.JOURNAL_PARENT,candidate['attempt'],'checkpoint.json').read_bytes()
        permit=dict(format=1,kind=h.PREPARED_REOPEN_KIND,host=p.HOST,mode=h.MODE,
            attempt=candidate['attempt'],carrier_manifest_sha256=reopened.pins(),
            plan_sha256=candidate['plan_sha256'],proof_sha256=s.sha(proof_raw),
            prior_approval_sha256=prior,active_attempt_sha256=s.sha(active),
            prepared_event_sha256=s.sha(checkpoint),issued_at=self.clock,expires_at=self.clock+600,
            actions=['REOPEN_EXACT_PREPARED_SAME_ATTEMPT','KNOWN_FAILURE_SERIAL_RECOVERY'])
        self.write(reopened._prepared_reopen_path(s.sha(proof_raw)),s.canonical(permit))
        self.clock=permit['expires_at']+1
        original_replace=u.Update.replace_and_verify
        def known_failure(update):
            update.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original_replace(update)
        with patch.object(u.Update,'replace_and_verify',known_failure),self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            reopened.reopen_prepared()
        self.assertEqual(reopened.journal.state['phase'],'KNOWN_FAILURE')
        self.assertEqual([row[3] for row in self.calls],['rename','run'])
        self.assertEqual(proof_raw,Path(h.PROOF).read_bytes())
        reopened.close();recovery=h.Session();recovery.acquire(recover=True);self.addCleanup(recovery.close);self.session=recovery
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=None,version_source=None,observed_at=self.clock)
        with patch.object(c,'BoundHttpsHealth',return_value=old_health):result=recovery.recover()
        self.assertEqual(result['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertIn('start',[row[3] for row in self.calls])

    def test_expired_prepared_reopen_uses_one_bound_reissue_and_recovers_same_attempt(self):
        q,_=self._prepare_completed_b_before_c_proof()
        semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        q._fixed_c_resume_plan(q.candidate(semantic),semantic)
        candidate=self._register_c_resume_approval_from_persisted_plan(q)
        with patch.object(u.Update,'guard',side_effect=u.Hold('PROTECTED_BINDING_CHANGED')), \
             self.assertRaisesRegex(u.Hold,'PROTECTED_BINDING_CHANGED'):
            q.resume_c_before_confirmation()
        proof,proof_raw=h.document(h.PROOF);q.close();self.clock=4000
        reopened=h.Session();reopened.acquire(recover=True);self.addCleanup(reopened.close);self.session=reopened
        reopened.configure_resumed_recovery(proof);reopened.approved_stamp=reopened.pins()
        active=Path(u.JOURNAL_PARENT,'active-attempt.json').read_bytes()
        checkpoint=Path(u.JOURNAL_PARENT,candidate['attempt'],'checkpoint.json').read_bytes()
        old=dict(format=1,kind=h.PREPARED_REOPEN_KIND,host=p.HOST,mode=h.MODE,
            attempt=candidate['attempt'],carrier_manifest_sha256='1'*64,
            plan_sha256=candidate['plan_sha256'],proof_sha256=s.sha(proof_raw),
            prior_approval_sha256=proof['approval_sha256'],active_attempt_sha256=s.sha(active),
            prepared_event_sha256=s.sha(checkpoint),issued_at=3000,expires_at=3600,
            actions=['REOPEN_EXACT_PREPARED_SAME_ATTEMPT','KNOWN_FAILURE_SERIAL_RECOVERY'])
        old_raw=s.canonical(old);self.write(reopened._prepared_reopen_path(s.sha(proof_raw)),old_raw)
        fresh=dict(old,kind=h.PREPARED_REOPEN_REISSUE_KIND,
            carrier_manifest_sha256='2'*64,prior_prepared_reopen_sha256=s.sha(old_raw),
            issued_at=self.clock,expires_at=self.clock+600)
        self.write(reopened._prepared_reopen_reissue_path(s.sha(old_raw)),s.canonical(fresh))
        self.clock=fresh['expires_at']+1
        original_replace=u.Update.replace_and_verify
        def known_failure(update):
            update.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original_replace(update)
        with patch.object(u.Update,'replace_and_verify',known_failure),self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            reopened.reopen_prepared()
        self.assertEqual(reopened.journal.state['phase'],'KNOWN_FAILURE')
        self.assertEqual([row[3] for row in self.calls],['rename','run'])
        reopened.close();recovery=h.Session();recovery.acquire(recover=True);self.addCleanup(recovery.close);self.session=recovery
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=None,version_source=None,observed_at=self.clock)
        with patch.object(c,'BoundHttpsHealth',return_value=old_health):result=recovery.recover()
        self.assertEqual(result['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertIn('start',[row[3] for row in self.calls])

    def test_expired_prepared_reopen_reissue_real_pty_full_chain(self):
        """One real TTY gate reopens PREPARED and its bound known-failure recovery."""
        import pty,select,time,signal,errno,re
        worker="""import sys
sys.path[:0]=[REPO,REPO+'/tests']
from pathlib import Path
from unittest.mock import patch
from test_community_preview_stopped_handoff import WholeEntry
from scripts import community_preview_stopped_handoff as h
from scripts import community_preview_site_prepare as s
from scripts import community_preview_update_checkpoint as u
from scripts import community_preview_update_composition as c
from scripts import community_preview_release_plan as p
t=WholeEntry();t.tty_actual=True;t.setUp()
try:
 with patch.object(h,'acknowledge'):
  q,_=t._prepare_completed_b_before_c_proof()
  semantic=q.evidence(True);q.backup=h.open_private(s.BACKUP+'/clone-results.json')
  q._fixed_c_resume_plan(q.candidate(semantic),semantic)
  candidate=t._register_c_resume_approval_from_persisted_plan(q)
  try:
   with patch.object(u.Update,'guard',side_effect=u.Hold('PROTECTED_BINDING_CHANGED')):q.resume_c_before_confirmation()
   raise AssertionError('PREPARED_HOLD_REQUIRED')
  except u.Hold as error:assert 'PROTECTED_BINDING_CHANGED' in str(error)
 proof,proof_raw=h.document(h.PROOF);q.close();t.clock=4000;s.EXPIRES=3500
 reopened=h.Session();reopened.acquire(recover=True);t.session=reopened
 reopened.configure_resumed_recovery(proof);reopened.approved_stamp=reopened.pins()
 active=Path(u.JOURNAL_PARENT,'active-attempt.json').read_bytes()
 event=Path(u.JOURNAL_PARENT,candidate['attempt'],'event-000001.json').read_bytes()
 old=dict(format=1,kind=h.PREPARED_REOPEN_KIND,host=p.HOST,mode=h.MODE,
  attempt=candidate['attempt'],carrier_manifest_sha256='1'*64,
  plan_sha256=candidate['plan_sha256'],proof_sha256=s.sha(proof_raw),
  prior_approval_sha256=proof['approval_sha256'],active_attempt_sha256=s.sha(active),
  prepared_event_sha256=s.sha(event),issued_at=3000,expires_at=3600,
  actions=['REOPEN_EXACT_PREPARED_SAME_ATTEMPT','KNOWN_FAILURE_SERIAL_RECOVERY'])
 old_raw=s.canonical(old);t.write(reopened._prepared_reopen_path(s.sha(proof_raw)),old_raw)
 fresh=dict(old,kind=h.PREPARED_REOPEN_REISSUE_KIND,
  carrier_manifest_sha256='2'*64,prior_prepared_reopen_sha256=s.sha(old_raw),
  issued_at=t.clock,expires_at=t.clock+600)
 fresh_raw=s.canonical(fresh);fresh_path=reopened._prepared_reopen_reissue_path(s.sha(old_raw))
 t.write(fresh_path,fresh_raw)
 t.clock=fresh['expires_at']+1
 original=u.Update.replace_and_verify
 def known(update):
  update.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
   scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
   runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=t.clock)
  return original(update)
 try:
  with patch.object(u.Update,'replace_and_verify',known):reopened.reopen_prepared()
  raise AssertionError('KNOWN_FAILURE_REQUIRED')
 except u.Hold as error:assert 'KNOWN_FAILURE' in str(error)
 assert reopened.journal.state['phase']=='KNOWN_FAILURE'
 assert reopened.prepared_reopen_path==fresh_path and reopened.prepared_reopen_raw==fresh_raw
 reopened.close();recovery=h.Session();recovery.acquire(recover=True);t.session=recovery
 old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
  scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
  runtime_source_sha=None,version_source=None,observed_at=t.clock)
 with patch.object(c,'BoundHttpsHealth',return_value=old_health):result=recovery.recover()
 assert result['phase'] in ('ROLLED_BACK_PREVIEW_HOLD','COMMITTED')
 assert recovery.prepared_reopen_path==fresh_path and recovery.prepared_reopen_raw==fresh_raw
 print('PREPARED_REOPEN_REISSUE_REAL_PTY_FULL_CHAIN_OK',flush=True)
finally:
 t.doCleanups()
""".replace('REPO',repr(str(Path.cwd())))
        pid,fd=pty.fork()
        if pid==0:os.execv(sys.executable,[sys.executable,'-I','-B','-S','-c',worker])
        data=b'';sent=[];done=False;end=time.monotonic()+30
        try:
            while time.monotonic()<end:
                if select.select([fd],[],[],.05)[0]:
                    try:b=os.read(fd,65536)
                    except OSError as error:
                        if error.errno==errno.EIO:break
                        raise
                    if not b:break
                    data+=b
                    for line in re.findall(rb'APPROVE_(?:PREPARED_REOPEN|KNOWN_FAILURE_RECOVER) [0-9a-f]{64}',data):
                        if line not in sent:os.write(fd,line+b'\n');sent.append(line)
            got,status=os.waitpid(pid,0 if b'PREPARED_REOPEN_REISSUE_REAL_PTY_FULL_CHAIN_OK' in data else os.WNOHANG);done=got==pid
            self.assertTrue(done,data.decode(errors='replace'))
            self.assertEqual(os.waitstatus_to_exitcode(status),0,data.decode(errors='replace'))
            self.assertEqual([x.split()[0] for x in sent],[b'APPROVE_PREPARED_REOPEN'])
            self.assertIn(b'PREPARED_REOPEN_REISSUE_REAL_PTY_FULL_CHAIN_OK',data)
        finally:
            if not done:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)
            os.close(fd)

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
    def test_cleanup_error_after_effective_close_drops_ownership_and_stays_terminal_unknown(self):
        fds=[self.session.entry,self.session.lease,self.session.parent];real=os.close;seen=[]
        def close(fd):
            seen.append(fd);real(fd)
            if fd==fds[0]:raise OSError('SYNTHETIC_AFTER_CLOSE')
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        self.assertEqual(seen,fds);self.assertTrue(self.session.cleanup_unproven)
        self.assertIsNone(self.session.entry);self.assertIsNone(self.session.lease);self.assertIsNone(self.session.parent)
        before=len(seen)
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        self.assertEqual(len(seen),before);self.session.cleanup_unproven=False
    def test_cleanup_pre_effect_failure_does_not_retry_open_fd_and_stays_terminal_unknown(self):
        target=self.session.entry;real=os.close;seen=[]
        def close(fd):
            seen.append(fd)
            if fd==target:raise OSError('SYNTHETIC_PRE_EFFECT')
            return real(fd)
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        os.fstat(target);before=len(seen)
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        self.assertEqual(len(seen),before);real(target);self.session.cleanup_unproven=False
    def test_cleanup_exception_never_retries_recycled_fd_on_second_cleanup(self):
        target=self.session.entry;real=os.close;seen=[];replacement=[None];raised=[False]
        def close(fd):
            seen.append(fd)
            if fd==target and not raised[0]:
                raised[0]=True;real(fd)
                new=os.open('/dev/null',os.O_RDONLY)
                if new!=target:os.dup2(new,target);real(new)
                replacement[0]=target
                raise OSError('SYNTHETIC_CLOSE_UNKNOWN_AFTER_RECYCLE')
            return real(fd)
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        self.assertEqual(seen.count(target),1);self.assertIsNone(self.session.entry)
        before=len(seen)
        with patch.object(h.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'CLEANUP_UNKNOWN'):self.session.close()
        self.assertEqual(len(seen),before);os.fstat(replacement[0]);real(replacement[0]);self.session.cleanup_unproven=False
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

    def test_v2_authority_uses_a_entry_bytes_and_cleans_failed_active_permit(self):
        original=h.write_private
        def write_then_expire(parent,name,value):
            original(parent,name,value)
            if name==os.path.basename(s.PERMIT):self.clock=1601
        with patch.object(h,'write_private',side_effect=write_then_expire),self.assertRaisesRegex(u.Hold,'APPROVAL_EXPIRED|STAGE_APPROVAL_EXPIRED'):
            self.session.run_b()
        self.assertFalse(Path(s.PERMIT).exists())
        self.assertTrue(Path(u.JOURNAL_PARENT,h.attempt()+'-B-intent.json').exists())
        self.assertEqual(self.calls,[])

    def test_carrier_stamp_changed_after_c_approval_even_with_matching_manifest_holds(self):
        self.prepare_b_and_c();real=self.session.c_approval
        def approved_then_replace(candidate):
            value=real(candidate)
            path=Path(h.CONTROL,'scripts/community_preview_release_plan.py');path.write_bytes(path.read_bytes()+b'\n#same-manifest-replacement\n')
            manifest,_=h.document(h.MANIFEST);body=path.read_bytes();manifest['files']['scripts/community_preview_release_plan.py']['bytes']=len(body);manifest['files']['scripts/community_preview_release_plan.py']['sha256']=s.sha(body)
            self.write(h.MANIFEST,s.canonical(manifest))
            return value
        with patch.object(self.session,'c_approval',side_effect=approved_then_replace),self.assertRaisesRegex(u.Hold,'CARRIER_STAMP_CHANGED'):
            self.session.update()
        self.assertEqual(self.calls,[])

    def test_newrun_health_and_commit_extra_prefix_objects_hold(self):
        # Extra immediately after docker run.
        self.prepare_b_and_c()
        def run_extra():
            self.new=True;self.names[p.NAME]='9'*64;self.names['xuanjun-community-preview-extra']='8'*64;return '9'*64
        self.on_run=run_extra
        with self.assertRaises(u.Hold):self.session.update()
        self.assertEqual([x[3] for x in self.calls],['rename','run'])

    def test_health_midflight_extra_prefix_object_holds(self):
        self.prepare_b_and_c();real=self.recorded_observe;fired=[False]
        def observe(argv,**kwargs):
            value=real(argv,**kwargs)
            if argv and argv[0]=='/usr/bin/python3' and not fired[0]:
                fired[0]=True;self.names['xuanjun-community-preview-extra']='8'*64
            return value
        with patch.object(c.observation,'capture',side_effect=observe),self.assertRaises(u.Hold):self.session.update()
        self.assertTrue(fired[0]);self.assertNotEqual(self.session.journal.state['phase'],'COMMITTED')

    def _commit_inventory_fault(self,legacy):
        self.prepare_b_and_c();write=u.Journal.write
        def publish(j,phase,*args):
            write(j,phase,*args)
            if phase=='COMMITTED':
                if legacy:
                    self.names['xuanjun-community-preview-before-2330dd55']='36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc';self.legacy_running=True
                else:self.names['xuanjun-community-preview-extra']='8'*64
        with patch.object(u.Journal,'write',publish),self.assertRaises(u.Hold):self.session.update()
        self.assertEqual(self.session.journal.state['phase'],u.HOLD_PHASE)
    def test_commit_final_extra_prefix_cannot_commit(self):
        self._commit_inventory_fault(False)
    def test_commit_final_running_legacy_cannot_commit(self):
        self._commit_inventory_fault(True)

    def test_recovery_extra_inventory_or_unknown_inspect_never_starts_old(self):
        self.prepare_b_and_c();real=self.recorded_observe
        def failed_health(argv,**kwargs):
            value=real(argv,**kwargs)
            if argv and argv[0]=='/usr/bin/python3':
                frame=json.loads(value);body=json.loads(bytes.fromhex(frame['body_hex']));body['status']='UNAVAILABLE';frame['body_hex']=json.dumps(body).encode().hex();return json.dumps(frame)
            return value
        with patch.object(c.observation,'capture',side_effect=failed_health),self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            self.session.update()
        self.assertEqual(self.session.journal.state['phase'],'KNOWN_FAILURE')
        before=len(self.calls);self.names['xuanjun-community-preview-extra']='8'*64
        with self.assertRaises(u.Hold):self.session.consume(h.document(h.PROOF)[0],True)
        self.assertEqual(len(self.calls),before);self.assertNotIn('start',[x[3] for x in self.calls[before:]])

    def test_known_failure_full_serial_recovery_rechecks_phase_inventory_to_terminal(self):
        self.prepare_b_and_c();original=u.Update.replace_and_verify
        def known(updater):
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        with patch.object(u.Update,'replace_and_verify',known),self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            self.session.update()
        proof=h.document(h.PROOF)[0];hobj=h.VerifiedHandoff(self.session,proof,self.session.journal)
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,runtime_source_sha=None,version_source=None,observed_at=self.clock)
        t=u.OriginalTransport(hobj.bindings,old_health);v=u.Update(self.session.journal,t,execution_enabled=True,clock=c.now,handoff=hobj)
        result=v.recover();self.assertEqual(result['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertEqual([x[3] for x in self.calls[-4:]],['stop','rename','rename','start'])
        self.assertTrue(self.running);self.assertFalse(self.new);self.assertEqual(self.names[p.NAME],s.OLD_ID)

    def test_recovery_unknown_new_inspect_never_starts_old(self):
        self.prepare_b_and_c();original=u.Update.replace_and_verify
        def known(updater):
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        with patch.object(u.Update,'replace_and_verify',known),self.assertRaises(u.Hold):self.session.update()
        proof=h.document(h.PROOF)[0];hobj=h.VerifiedHandoff(self.session,proof,self.session.journal)
        t=u.OriginalTransport(hobj.bindings,lambda:None);v=u.Update(self.session.journal,t,execution_enabled=True,clock=c.now,handoff=hobj)
        real=c.original.inspect
        def inspect(cid):
            if cid=='9'*64:raise u.Hold('INSPECT_UNKNOWN')
            return real(cid)
        before=len(self.calls)
        with patch.object(c.original,'inspect',side_effect=inspect),self.assertRaises(u.Hold):v.recover()
        self.assertNotIn('start',[x[3] for x in self.calls[before:]])

    def test_stopped_journal_requires_same_lease_and_legacy_rejects_lease(self):
        self.prepare_b_and_c();self.session.update();candidate=self.session.journal.plan;binding=self.session.journal.handoff_binding
        self.session.journal.close();self.session.journal=None
        with self.assertRaisesRegex(u.Hold,'CONTINUOUS_LEASE'):u.Journal(self.session.parent,candidate,handoff_binding=binding)
        dup=os.dup(self.session.lease)
        try:
            j=u.Journal(self.session.parent,candidate,lease_fd=dup,handoff_binding=binding);j.close()
        finally:os.close(dup)
        other=os.open('other.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=self.session.parent)
        try:
            with self.assertRaisesRegex(u.Hold,'SAME_CONTINUOUS_LOCK'):u.Journal(self.session.parent,candidate,lease_fd=other,handoff_binding=binding)
        finally:os.close(other)
        current=copy.deepcopy(candidate['current']);current['running']=True
        legacy=p.prepare(candidate['source'],current,candidate['image'])
        with self.assertRaisesRegex(u.Hold,'LEGACY_JOURNAL_NO_HANDOFF_ARGUMENTS'):u.Journal(self.session.parent,legacy,lease_fd=self.session.lease)

    def test_journal_cleanup_exception_drops_ownership_and_never_retries_recycled_fd(self):
        self.prepare_b_and_c();self.session.update();j=self.session.journal;fds=[j.fd,j.lock,j.parent];real=os.close;seen=[];replacement=[None];raised=[False]
        def close(fd):
            seen.append(fd)
            if fd==fds[0] and not raised[0]:
                raised[0]=True;real(fd)
                new=os.open('/dev/null',os.O_RDONLY)
                if new!=fds[0]:os.dup2(new,fds[0]);real(new)
                replacement[0]=fds[0]
                raise OSError('SYNTHETIC_CLOSE_UNKNOWN_AFTER_RECYCLE')
            return real(fd)
        with patch.object(u.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'JOURNAL_CLEANUP_UNKNOWN'):j.close()
        self.assertTrue(j.cleanup_unproven);self.assertEqual(seen.count(fds[0]),1);self.assertIn(fds[1],seen);self.assertIn(fds[2],seen)
        self.assertIsNone(j.fd);self.assertIsNone(j.lock);self.assertIsNone(j.parent)
        before=len(seen)
        with patch.object(u.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'JOURNAL_CLEANUP_UNKNOWN'):j.close()
        self.assertEqual(len(seen),before);os.fstat(replacement[0]);real(replacement[0]);j.cleanup_unproven=False;self.session.journal=None
    def test_journal_cleanup_pre_effect_failure_stays_terminal_unknown_without_retry(self):
        self.prepare_b_and_c();self.session.update();j=self.session.journal;target=j.fd;real=os.close;seen=[]
        def close(fd):
            seen.append(fd)
            if fd==target:raise OSError('SYNTHETIC_PRE_EFFECT')
            return real(fd)
        with patch.object(u.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'JOURNAL_CLEANUP_UNKNOWN'):j.close()
        os.fstat(target);before=len(seen)
        with patch.object(u.os,'close',side_effect=close),self.assertRaisesRegex(u.Hold,'JOURNAL_CLEANUP_UNKNOWN'):j.close()
        self.assertEqual(len(seen),before);real(target);j.cleanup_unproven=False;self.session.journal=None

    def test_unknown_second_update_is_explicit_inspect_only_and_preserves_files(self):
        self.prepare_b_and_c();self.on_run=lambda:'UNKNOWN'
        with self.assertRaises(u.Hold):self.session.update()
        before={str(q):q.read_bytes() for q in Path(u.JOURNAL_PARENT).rglob('*') if q.is_file()};calls=len(self.calls)
        with self.assertRaisesRegex(u.Hold,'EXISTING_ATTEMPT_INSPECT_OR_RECOVER_ONLY'):self.session.update()
        after={str(q):q.read_bytes() for q in Path(u.JOURNAL_PARENT).rglob('*') if q.is_file()}
        self.assertEqual(before,after);self.assertEqual(len(self.calls),calls);self.assertTrue(Path(h.PROOF).exists());self.assertFalse(Path(s.PERMIT).exists())

    def test_partial_resume_accepts_distinct_historical_and_new_carrier_sha(self):
        old,_=h.document(h.B_APPROVAL)
        old['carrier_manifest_sha256']='1'*64
        self.write(h.B_APPROVAL,s.canonical(old))
        self.seed_partial_resume()
        q=self.fresh_session()
        q.resume_b_partial()
        self.assertTrue(q.bdone)
        self.assertNotEqual(old['carrier_manifest_sha256'],q.approved_stamp)

    def test_partial_resume_old_permit_appearing_after_admission_is_hold(self):
        self.seed_partial_resume()
        q=self.fresh_session();q.resume_admission()
        self.write(s.PERMIT,b'UNEXPECTED_HISTORICAL_PERMIT')
        with self.assertRaisesRegex(u.Hold,'B_PARTIAL_STATE_CONFLICT'):
            q.boundary()

    def test_partial_resume_prior_permit_changed_between_reads_rejected(self):
        intent,old_braw,old_freeze_raw,resume=self.seed_partial_resume()
        old_b=s.exact_json(old_braw);old_freeze=s.exact_json(old_freeze_raw)
        permit=dict(format=1,host=p.HOST,stage='snapshot',entry_sha256=h.A_ENTRY_SHA,
            issued_at=1000,expires_at=1500,
            all_writers_frozen_evidence_sha256=s.sha(old_freeze_raw),
            snapshot_manifest_sha256=None)
        good=s.canonical(permit);self.write(s.PERMIT,good)
        resume['old_stage_permit_sha256']=s.sha(good)
        self.write(h.B_RESUME_APPROVAL,s.canonical(resume))
        q=self.fresh_session()
        original=h.resume_reference
        def swapped(path,limit=65536):
            result=original(path,limit)
            if path==s.PERMIT:
                changed=dict(permit,expires_at=1400)
                self.write(s.PERMIT,s.canonical(changed))
            return result
        with patch.object(h,'resume_reference',side_effect=swapped):
            with self.assertRaisesRegex(u.Hold,'B_RESUME_REFERENCE_REPLACED'):
                q.resume_admission()

    def test_partial_resume_reacquires_lock_preserves_old_evidence_and_finishes_b(self):
        intent,old_braw,old_freeze_raw,resume=self.seed_partial_resume();old_intent=Path(h.b_records()['B-intent']).read_bytes()
        q=self.fresh_session();q.resume_b_partial()
        self.assertTrue(q.bdone);self.assertEqual(set(q.captured),set(h.CLONES))
        self.assertEqual(Path(h.b_records()['B-intent']).read_bytes(),old_intent)
        self.assertEqual(Path(h.B_APPROVAL).read_bytes(),old_braw);self.assertEqual(Path(s.FREEZE).read_bytes(),old_freeze_raw)
        record,_=h.document(h.resume_record_path())
        self.assertEqual(record['old_b_intent_sha256'],s.sha(old_intent))
        self.assertEqual(record['resume_approval_sha256'],s.sha(Path(h.B_RESUME_APPROVAL).read_bytes()))
        self.assertTrue(Path(s.BACKUP,'private-manifest.json').exists());self.assertTrue(Path(s.BACKUP,'clone-results.json').exists())
    def test_partial_resume_requires_new_lock_and_rejects_concurrent_executor(self):
        self.seed_partial_resume();other=h.Session()
        try:
            with self.assertRaises((BlockingIOError,OSError,u.Hold)):other.acquire()
            self.assertFalse(Path(h.resume_record_path()).exists())
        finally:
            try:other.close()
            except Exception:pass
    def test_partial_resume_rejects_duplicate_record_and_crash_preserves_it(self):
        self.seed_partial_resume();q=self.fresh_session()
        with patch.object(q,'b_stage',side_effect=RuntimeError('SYNTHETIC_CRASH')),self.assertRaises(RuntimeError):q.resume_b_partial()
        raw=Path(h.resume_record_path()).read_bytes();self.assertTrue(raw)
        q.close();r=h.Session();r.acquire();self.addCleanup(r.close)
        with self.assertRaisesRegex(u.Hold,'B_PARTIAL_STATE_CONFLICT'):r.resume_admission()
        self.assertEqual(Path(h.resume_record_path()).read_bytes(),raw)
    def test_partial_resume_rejects_old_identity_or_new_authority_mismatch(self):
        intent,old_braw,old_freeze_raw,resume=self.seed_partial_resume();q=self.fresh_session()
        bad=dict(resume,old_b_intent_sha256='0'*64);self.write(h.B_RESUME_APPROVAL,s.canonical(bad))
        with self.assertRaisesRegex(u.Hold,'B_RESUME_EVIDENCE_BINDING_CHANGED'):q.resume_admission()
        self.write(h.B_RESUME_APPROVAL,s.canonical(resume));self.write(s.FREEZE,old_freeze_raw+b' ')
        with self.assertRaises(Exception):q.resume_admission()
    def test_partial_resume_rejects_any_snapshot_clone_proof_or_c_journal_state(self):
        self.seed_partial_resume();q=self.fresh_session()
        conflict_paths=[h.b_records()['snapshot-result'],h.b_records()['snapshot-permit'],h.b_records()['validate-clones-result'],
            h.b_records()['validate-clones-permit'],s.BACKUP,h.C_APPROVAL,h.B_RESUME_STAGE_PERMIT,
            u.JOURNAL_PARENT+'/active-attempt.json',u.JOURNAL_PARENT+'/'+h.attempt()]
        for path in conflict_paths:
            target=Path(path)
            if path in (s.BACKUP,u.JOURNAL_PARENT+'/'+h.attempt()):target.mkdir(parents=True,mode=0o700)
            else:self.write(path,b'{}')
            try:
                with self.subTest(path=path),self.assertRaisesRegex(u.Hold,'B_PARTIAL_OUTPUT_PRESENT|B_PARTIAL_STATE_CONFLICT'):
                    q.resume_admission()
            finally:
                if target.is_dir():target.rmdir()
                elif target.exists():target.unlink()
    def test_partial_resume_preserves_old_stage_permit_and_uses_new_excl_path(self):
        intent,old_braw,old_freeze_raw,resume=self.seed_partial_resume()
        old_permit=dict(format=1,host=p.HOST,stage='snapshot',entry_sha256=h.A_ENTRY_SHA,issued_at=1000,expires_at=1100,
            all_writers_frozen_evidence_sha256=s.sha(old_freeze_raw),snapshot_manifest_sha256=None)
        self.write(s.PERMIT,s.canonical(old_permit));resume=dict(resume,old_stage_permit_sha256=s.sha(s.canonical(old_permit)))
        self.write(h.B_RESUME_APPROVAL,s.canonical(resume));old_raw=Path(s.PERMIT).read_bytes()
        q=self.fresh_session();q.resume_b_partial()
        self.assertEqual(Path(s.PERMIT).read_bytes(),old_raw);self.assertFalse(Path(h.B_RESUME_STAGE_PERMIT).exists())
        record,_=h.document(h.resume_record_path());self.assertEqual(record['old_stage_permit_sha256'],s.sha(old_raw))
    def test_partial_resume_old_expired_approval_is_never_reused(self):
        self.seed_partial_resume();q=self.fresh_session();Path(h.B_RESUME_APPROVAL).unlink()
        with self.assertRaises(FileNotFoundError):q.resume_admission()
        old,_=h.document(h.B_APPROVAL);self.assertLess(old['expires_at'],self.clock)
    def test_partial_resume_c_plan_must_bind_new_real_plan(self):
        self.seed_partial_resume();q=self.fresh_session();q.resume_b_partial();semantic=q.evidence(True)
        q.backup=h.open_private(s.BACKUP+'/clone-results.json');candidate=q.candidate(semantic)
        bad=dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],carrier_manifest_sha256=q.pins(),
            plan_sha256='0'*64,issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_APPROVAL,s.canonical(bad))
        with self.assertRaisesRegex(u.Hold,'EXACT_C_APPROVAL_REQUIRED'):q.c_approval(candidate)
    def test_partial_resume_rejects_incomplete_or_inconsistent_prior_stage_permit(self):
        intent,old_braw,old_freeze_raw,resume=self.seed_partial_resume()
        base=dict(format=1,host=p.HOST,stage='snapshot',entry_sha256=h.A_ENTRY_SHA,issued_at=1000,expires_at=1100,
            all_writers_frozen_evidence_sha256=s.sha(old_freeze_raw),snapshot_manifest_sha256=None)
        cases=[dict(base,stage='validate-clones'),dict(base,entry_sha256='0'*64),
               dict(base,all_writers_frozen_evidence_sha256='0'*64),dict(base,snapshot_manifest_sha256='0'*64),
               dict(base,expires_at=1700)]
        for n,bad in enumerate(cases):
            with self.subTest(case=n):
                self.write(s.PERMIT,s.canonical(bad))
                bound=dict(resume,old_stage_permit_sha256=s.sha(s.canonical(bad)))
                self.write(h.B_RESUME_APPROVAL,s.canonical(bound));q=self.fresh_session()
                with self.assertRaisesRegex(u.Hold,'EXACT_PRIOR_STAGE_PERMIT_REQUIRED'):q.resume_admission()
        Path(s.PERMIT).unlink()
    def test_partial_resume_continuously_rechecks_old_reference_and_absence(self):
        self.seed_partial_resume();q=self.fresh_session();q.resume_admission()
        # A C/journal artifact appearing after admission is not absorbed as a new baseline.
        self.write(h.C_APPROVAL,b'{}')
        with self.assertRaisesRegex(u.Hold,'B_PARTIAL_STATE_CONFLICT'):q.b_stage('snapshot')
        Path(h.C_APPROVAL).unlink()
        # Same bytes written back at a new inode would still be a replacement; never reset the baseline.
        old=Path(h.B_APPROVAL).read_bytes();self.write(h.B_APPROVAL,old+b' ')
        with self.assertRaisesRegex(u.Hold,'B_RESUME_REFERENCE_REPLACED'):q.b_stage('snapshot')
    def test_partial_resume_probe_name_conflict_or_unknown_holds_before_first_write(self):
        self.seed_partial_resume();q=self.fresh_session()
        self.names[h.resume_probe_names()[0]]='8'*64
        with self.assertRaisesRegex(u.Hold,'B_RESUME_PROBE_NAME_CONFLICT'):q.resume_admission()
        self.assertFalse(Path(h.resume_record_path()).exists())
        del self.names[h.resume_probe_names()[0]]
        q.close();q=h.Session();q.acquire();self.addCleanup(q.close)
        with patch.object(h,'probe_names_absent',side_effect=u.Hold('B_RESUME_PROBE_INVENTORY_UNKNOWN')),self.assertRaisesRegex(u.Hold,'B_RESUME_PROBE_INVENTORY_UNKNOWN'):
            q.resume_admission()
        self.assertFalse(Path(h.resume_record_path()).exists())
    def test_partial_resume_known_failure_reopens_new_lock_session_and_recovers_bound_resume_evidence(self):
        self.seed_partial_resume();q=self.fresh_session();q.resume_b_partial()
        real=q.candidate
        def bind(semantic):
            candidate=real(semantic)
            approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],
                carrier_manifest_sha256=q.pins(),plan_sha256=candidate['plan_sha256'],
                issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
            self.write(h.C_APPROVAL,s.canonical(approval));return candidate
        original=u.Update.replace_and_verify
        def known(updater):
            updater.t.health=lambda:dict(http_status=503,url=p.URL,status='UNAVAILABLE',
                scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                runtime_source_sha=s.PRODUCT,version_source='IMAGE_BUILD_STAMP',observed_at=self.clock)
            return original(updater)
        with patch.object(q,'candidate',side_effect=bind),patch.object(u.Update,'replace_and_verify',known),self.assertRaisesRegex(u.Hold,'KNOWN_FAILURE'):
            q.update()
        self.assertEqual(q.journal.state['phase'],'KNOWN_FAILURE')
        q.close()
        # The old permit was absent at admission. It must remain absent
        # across a new recover lease, even if introduced after C failed.
        mutation_count=len(self.calls)
        self.write(s.PERMIT,b'UNEXPECTED_OLD_PERMIT')
        blocked=h.Session();blocked.acquire(recover=True);self.addCleanup(blocked.close)
        with self.assertRaisesRegex(u.Hold,'B_PARTIAL_STATE_CONFLICT'):
            blocked.recover()
        self.assertEqual(len(self.calls),mutation_count)
        blocked.close();Path(s.PERMIT).unlink()

        # Inject after configure_resumed_recovery has rebound the history,
        # but before the recovery action confirmation/consume boundary.
        blocked=h.Session();blocked.acquire(recover=True);self.addCleanup(blocked.close)
        def late_old_permit(action,digest):
            self.write(s.PERMIT,b'LATE_UNEXPECTED_OLD_PERMIT')
        with patch.object(h,'acknowledge',side_effect=late_old_permit):
            with self.assertRaisesRegex(u.Hold,'B_PARTIAL_STATE_CONFLICT'):
                blocked.recover()
        self.assertEqual(len(self.calls),mutation_count)
        blocked.close();Path(s.PERMIT).unlink()

        r=h.Session();r.acquire(recover=True);self.addCleanup(r.close)
        old_health=lambda:dict(http_status=200,url=p.URL,status='READY',
            scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
            runtime_source_sha=None,version_source=None,observed_at=self.clock)
        with patch.object(c,'BoundHttpsHealth',return_value=old_health):
            result=r.recover()
        self.assertEqual(result['phase'],'ROLLED_BACK_PREVIEW_HOLD')
        self.assertTrue(r.resume_mode)
        self.assertEqual([x[3] for x in self.calls[-4:]],['stop','rename','rename','start'])
        # Historical resume evidence remains mandatory in the new lock session.
        r.close();bad=Path(h.B_APPROVAL).read_bytes();self.write(h.B_APPROVAL,bad+b' ')
        z=h.Session();z.acquire(recover=True);self.addCleanup(z.close)
        with self.assertRaisesRegex(u.Hold,'B_RESUME_REFERENCE_REPLACED|B_RESUME_PROOF_BINDING_CHANGED'):z.recover()

    def test_builder_exposes_resume_wrapper_without_changing_default_acceptance(self):
        archive,manifest,commands=build.build()
        self.assertIn('resume-b-partial',commands);self.assertIn(b'--resume-b-partial',commands['resume-b-partial'])
        self.assertIn('resume-c-before-confirmation',commands)
        self.assertIn(b'--resume-c-before-confirmation',commands['resume-c-before-confirmation'])
        self.assertIn(b'BC_OUTER_NOT_ACCEPTANCE',commands['resume-c-before-confirmation'])
        self.assertIn(b'BC_OUTER_NOT_ACCEPTANCE',commands['resume-b-partial'])

    def test_builder_binding_checks_builder_loader_and_source_set(self):
        head='a'*40;original=build.subprocess.check_output
        paths=build.BUILD_INPUTS|{('scripts/community_preview_bc_loader.py' if n=='loader.py' else n) for n in build.EXPECTED_SOURCE_FILES}
        committed={path:(build.ROOT/path).read_bytes() for path in paths}
        def git(args,**kwargs):
            if args[:2]==['git','rev-parse']:return head+'\n'
            if args[:2]==['git','show']:
                path=args[2].split(':',1)[1];return committed[path]
            return original(args,**kwargs)
        with patch.object(build.subprocess,'check_output',side_effect=git),patch.dict(os.environ,{'GITHUB_SHA':head}):
            self.assertEqual(build.commit_binding(),head)
            q=build.ROOT/'scripts/community_preview_bc_loader.py';raw=q.read_bytes();q.write_bytes(raw+b'#dirty\n')
            try:self.assertIsNone(build.commit_binding())
            finally:q.write_bytes(raw)
            q=build.ROOT/'scripts/community_preview_bc_build.py';raw=q.read_bytes();q.write_bytes(raw+b'#dirty\n')
            try:self.assertIsNone(build.commit_binding())
            finally:q.write_bytes(raw)
            oldset=h.SOURCE_FILES;h.SOURCE_FILES=set(oldset)-{'loader.py'}
            try:self.assertIsNone(build.commit_binding())
            finally:h.SOURCE_FILES=oldset

    def test_wrapper_child_exit_two_is_never_acceptance_and_zip_is_deflated(self):
        import zipfile
        archive,_,commands=build.build()
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            self.assertTrue(z.infolist());self.assertTrue(all(i.compress_type==zipfile.ZIP_DEFLATED for i in z.infolist()))
            self.assertTrue(all((i.external_attr>>16)&0o777==0o600 for i in z.infolist()))
        import shlex
        fake=self.root/'sudo-fail';fake.write_text('#!/bin/sh\nexit 2\n');fake.chmod(0o700)
        command=commands['owner-bc'].decode().replace('/usr/bin/sudo',str(fake))
        proc=subprocess.run(['/bin/bash','-c',command+'\nprintf "OUTER_RC=%s\\n" "$?"\n'],capture_output=True,text=True)
        records=[json.loads(x) for x in proc.stdout.splitlines() if x.startswith('{')]
        self.assertEqual(proc.returncode,0);self.assertFalse(any(x.get('state')=='BC_RESULT' for x in records))
        self.assertEqual(next(x for x in records if x.get('record')=='SUDO_CHILD_EXIT')['child_exit'],2)
        self.assertEqual(next(x for x in records if x.get('record')=='BC_OUTER_NOT_ACCEPTANCE')['shell_rc_is_acceptance'],False)
        self.assertIn('OUTER_RC=0',proc.stdout)

    def test_real_loader_path_runs_snapshot_and_three_clone_b_with_v2_authority(self):
        with patch.object(h,'CONTROL','/opt/xuanjun-community-preview/control-stopped-v1'):
            archive,manifest,_=build.build()
        bundle=self.root/'carrier.zip';bundle.write_bytes(archive)
        worker=r"""import importlib.util,io,json,os,sys,tempfile,types,zipfile
from pathlib import Path
repo=Path(sys.argv[1]);bundle=Path(sys.argv[2])
with zipfile.ZipFile(bundle) as z:entries={n:z.read(n) for n in z.namelist()}
manifest=entries['manifest.json'];manifest_sha=__import__('hashlib').sha256(manifest).hexdigest()
spec=importlib.util.spec_from_file_location('isolated_bc_loader',repo/'scripts/community_preview_bc_loader.py')
loader=importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)
loader.read_file=lambda rel: manifest if rel=='manifest.json' else entries[rel]
uid=os.getuid();gid=os.getgid()
loader.os.getuid=lambda:0;loader.os.geteuid=lambda:0;loader.os.uname=lambda:types.SimpleNamespace(nodename=loader.HOST)
h=loader.load(manifest_sha);s=h.s;c=h.c;u=h.u;p=h.p
assert s.__file__==h.CONTROL+'/scripts/community_preview_site_prepare.py'
root=Path(tempfile.mkdtemp());root.chmod(0o700)
base=root/'opt/xuanjun-community-preview';base.mkdir(parents=True,mode=0o700)
data=root/'var/lib/xuanjun-community-preview';(data/'data').mkdir(parents=True,mode=0o700);(data/'config').mkdir(mode=0o700)
for name in ('host.json','center-keys.json','wechat.json'):
 q=data/'config'/name;q.write_bytes(b'SYNTHETIC_PRIVATE_NOT_A_CREDENTIAL');q.chmod(0o600)
q=data/'data'/'synthetic.db';q.write_bytes(b'SYNTHETIC_DATA');q.chmod(0o600)
run=root/'run/xuanjun-community-preview';run.mkdir(parents=True,mode=0o700)
journal=base/'update-journal';journal.mkdir(mode=0o700)
s.BASE=str(base);s.ENTRY=str(base/'site-prepare-v1.py');s.PERMIT=str(base/'site-prepare-approval.json');s.FREEZE=str(base/'writer-freeze-reference.json');s.BACKUP=str(base/'backup-2330-to-f131-v1');s.DATA=str(data);s.ROOT_ANCHOR=str(root);s.UID=uid;s.ROOT_GID=gid;s.ALLOWED_GIDS=(gid,1008)
h.B_APPROVAL=str(base/'bc-b-approval.json');h.C_APPROVAL=str(base/'bc-c-approval.json');h.PROOF=str(base/'backup-2330-to-f131-v1/stopped-handoff-v1.json')
u.JOURNAL_PARENT=str(journal);u.OWNER_UID=uid;c.REFERENCE_UID=uid
clock=[1000];c.root_host=lambda:None;c.now=lambda:clock[0];s.time.time=lambda:clock[0];s.space=lambda *a,**k:None;h.operator=lambda:(uid,gid);h.acknowledge=lambda *a:None
A=Path(sys.argv[3]).read_bytes()
assert __import__('hashlib').sha256(A).hexdigest()=='48357b6ff333d4cf727b203140d7b427ec8eeb84ea3d07c00a8a443f5430ed55'
Path(s.ENTRY).write_bytes(A);Path(s.ENTRY).chmod(0o600)
freeze=dict(format=1,host=p.HOST,old_id=s.OLD_ID,old_image=s.OLD_IMAGE,roots=[s.DATA+'/data',s.DATA+'/config'],issued_at=1000,expires_at=1600,all_writers_frozen=True,owner_review_reference_sha256='e'*64)
Path(s.FREEZE).write_bytes(s.canonical(freeze));Path(s.FREEZE).chmod(0o600)
carrier_sha=s.sha(manifest)
b=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),carrier_manifest_sha256=carrier_sha,issued_at=1000,expires_at=1600,freeze_sha256=s.sha(s.canonical(freeze)),actions=['SNAPSHOT','THREE_ISOLATED_CLONES'])
Path(h.B_APPROVAL).write_bytes(s.canonical(b));Path(h.B_APPROVAL).chmod(0o600)
def raw(path,limit=65536):
 if path==h.MANIFEST:return manifest
 prefix=h.CONTROL+'/'
 if path.startswith(prefix):
  rel=path[len(prefix):];return entries[rel]
 return s.read(path,limit)
h.raw=raw
logical=dict(format=1,original_host_open=True,center_integrity=True,stores=[[['sample',1,'a'*64]]])
def capture(argv,timeout=10):
 if argv[3:5]==['container','inspect']:return b'"'+s.OLD_ID.encode()+b'"\n"'+s.OLD_IMAGE.encode()+b'"\nfalse'
 if argv[:4]==s.DOCKER+['run']:return s.canonical(logical)
 raise AssertionError(argv)
s.capture=capture;c.inspect_bound=lambda cid,image:{'running':False};s._COMPONENT=c
session=h.Session();session.acquire();session.run_b()
assert session.bdone and set(session.captured)==set(h.CLONES)
assert not Path(s.PERMIT).exists()
assert Path(s.BACKUP,'private-manifest.json').exists() and Path(s.BACKUP,'clone-results.json').exists()
session.close();print('REAL_LOADER_B_OK')
"""
        a_entry=self.root/'verified-original-a.py';a_entry.write_bytes(frozen.a_source())
        proc=subprocess.run([sys.executable,'-I','-B','-S','-c',worker,str(Path.cwd()),str(bundle),str(a_entry)],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout);self.assertIn('REAL_LOADER_B_OK',proc.stdout)

    def test_v1_builder_refuses_changed_sources_instead_of_overwriting_a(self):
        from scripts import community_preview_control_carrier as v1
        with self.assertRaisesRegex(ValueError,'FROZEN_V1_SOURCE_ONLY'):v1.build()

    def test_real_original_subprocess_preexec_guard_and_cleanup(self):
        # Actual original Popen/limits/waitid/kill/reap; only this finite local
        # stdout probe, never Docker/server. Existing IO mocks stay read-only.
        result=self.original_capture([sys.executable,'-I','-B','-S','-c','print("BOUNDED_LOCAL_PROBE")'],3)
        self.assertEqual(result.strip(),b'BOUNDED_LOCAL_PROBE')
        self.assertEqual(self.calls,[])

    def test_main_cleanup_unknown_is_child2_and_never_success_acceptance(self):
        fake=type('FakeSession',(),{})()
        fake.acquire=lambda recover=False:None
        fake.run_b=lambda:None
        fake.update=lambda:{'phase':'COMMITTED'}
        fake.recover=lambda:{'phase':'ROLLED_BACK_PREVIEW_HOLD'}
        fake.close=lambda:(_ for _ in ()).throw(u.Hold('BC_CLEANUP_UNKNOWN'))
        out=io.StringIO()
        with patch.object(h,'Session',return_value=fake),contextlib.redirect_stdout(out):
            self.assertEqual(h.main(['--owner-bc']),2)
        row=json.loads(out.getvalue().strip());self.assertEqual(row['state'],'BC_RESULT');self.assertEqual(row['child_exit'],2)
        self.assertEqual(row['result']['phase'],'HOLD_CLEANUP_UNKNOWN');self.assertFalse(row['production_acceptance'])

class ExactHistoricalInitializeInventoryTests(unittest.TestCase):
    BEFORE_NAME='xuanjun-community-preview-before-2330dd55'
    BEFORE_ID='36b54db9973ee39bc71e5e8f8532ee52b79390531c79f593ce57d553a91122cc'
    INITIALIZE_NAME='xuanjun-community-preview-initialize'
    INITIALIZE_ID='ef62749e3efb1b41f69d241f0fe4aab5d6a4fb7356c2f732eff4522f947ffa21'
    IMAGE='sha256:7fb56688456d5f4d46599d34e2bf8496cbbbd3f3181ded3bab70a2de953e6c30'
    def setUp(self):
        self.candidate={'handoff_mode':'STOPPED_HANDOFF_V1',
            'current':{'container_id':s.OLD_ID},
            'rollback_name':'xuanjun-community-preview-rollback-fixture',
            'failed_name':'xuanjun-community-preview-failed-fixture'}
        self.current={'id':s.OLD_ID,'name':p.NAME}
        self.before={'id':self.BEFORE_ID,'name':self.BEFORE_NAME}
        self.initialize={'id':self.INITIALIZE_ID,'name':self.INITIALIZE_NAME}
    def inventory(self,*rows):
        return '\n'.join(json.dumps(x,separators=(',',':')) for x in rows).encode()
    def run_inventory(self,*rows):
        with patch.object(c.observation,'capture',return_value=self.inventory(*rows)):
            return c.exact_stopped_names(self.candidate,'PREPARED')
    def test_owner_exact_three_container_inventory_allows_both_stopped_historical_objects(self):
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,self.initialize)):
            with patch.object(c,'inspect_bound',return_value={'running':False}) as inspect:
                self.assertTrue(c.exact_stopped_names(self.candidate,'PREPARED'))
        self.assertEqual(inspect.call_args_list,[
            unittest.mock.call(self.BEFORE_ID,self.IMAGE),
            unittest.mock.call(self.INITIALIZE_ID,self.IMAGE,True)])
    def test_unknown_prefix_name_still_rejected(self):
        extra={'id':'a'*64,'name':'xuanjun-community-preview-initialize-rogue'}
        with self.assertRaisesRegex(u.Hold,'STOPPED_NAME_INVENTORY_CHANGED'):
            self.run_inventory(self.current,self.before,self.initialize,extra)
    def test_before_2330_changed_id_rejected(self):
        changed=dict(self.before,id='a'*64)
        with self.assertRaisesRegex(u.Hold,'LEGACY_BEFORE_2330_NOT_STOPPED'):
            self.run_inventory(self.current,changed,self.initialize)
    def test_before_2330_changed_image_rejected(self):
        def inspect(cid,image,*args):
            if cid==self.BEFORE_ID:
                self.assertEqual(image,self.IMAGE)
                raise u.Hold('CONTAINER_IMAGE_MISMATCH')
            return {'running':False}
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,self.initialize)):
            with patch.object(c,'inspect_bound',side_effect=inspect):
                with self.assertRaisesRegex(u.Hold,'CONTAINER_IMAGE_MISMATCH'):
                    c.exact_stopped_names(self.candidate,'PREPARED')
    def test_before_2330_running_rejected(self):
        def inspect(cid,image,*args):return {'running':cid==self.BEFORE_ID}
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,self.initialize)):
            with patch.object(c,'inspect_bound',side_effect=inspect):
                with self.assertRaisesRegex(u.Hold,'LEGACY_BEFORE_2330_NOT_STOPPED'):
                    c.exact_stopped_names(self.candidate,'PREPARED')
    def test_initialize_changed_id_rejected(self):
        changed=dict(self.initialize,id='e'*64)
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,changed)):
            with patch.object(c,'inspect_bound',return_value={'running':False}):
                with self.assertRaisesRegex(u.Hold,'LEGACY_INITIALIZE_NOT_STOPPED'):
                    c.exact_stopped_names(self.candidate,'PREPARED')
    def test_initialize_changed_image_rejected(self):
        def inspect(cid,image,*args):
            if cid==self.INITIALIZE_ID:
                self.assertEqual(image,self.IMAGE)
                raise u.Hold('CONTAINER_IMAGE_MISMATCH')
            return {'running':False}
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,self.initialize)):
            with patch.object(c,'inspect_bound',side_effect=inspect):
                with self.assertRaisesRegex(u.Hold,'CONTAINER_IMAGE_MISMATCH'):
                    c.exact_stopped_names(self.candidate,'PREPARED')
    def test_initialize_running_rejected(self):
        def inspect(cid,image,*args):return {'running':cid==self.INITIALIZE_ID}
        with patch.object(c.observation,'capture',return_value=self.inventory(self.current,self.before,self.initialize)):
            with patch.object(c,'inspect_bound',side_effect=inspect):
                with self.assertRaisesRegex(u.Hold,'LEGACY_INITIALIZE_NOT_STOPPED'):
                    c.exact_stopped_names(self.candidate,'PREPARED')


    # Exact source-backed initialize contract; never allowlist the live hash alone.
    def _initialize_inspect_output(self, entrypoint=None, cmd=None, network='none'):
        root=p.ROOT
        info={
            'id':self.INITIALIZE_ID,'image':self.IMAGE,'running':False,'status':'exited',
            'user':'10001:1008',
            'entrypoint':c.INITIALIZE_ENTRYPOINT if entrypoint is None else entrypoint,
            'cmd':c.INITIALIZE_CMD if cmd is None else cmd,
            'mounts':[
                {'Type':'bind','Source':root+'/config','Destination':root+'/config','RW':False},
                {'Type':'bind','Source':root+'/data','Destination':root+'/data','RW':True}],
            'cpu':500000000,'memory':536870912,'swap':536870912,'pids':64,
            'readonly':True,'privileged':False,'restart':'no','network':network,
            'capdrop':['ALL'],'security':['no-new-privileges'],
            'tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'},
            'log':{'Type':'json-file','Config':{'max-size':'10m','max-file':'2'}},
            'ports':None,'published':None,'devices':[],'capadd':[]}
        fields=c.original.INSPECT_FIELDS+[('ports','.HostConfig.PortBindings'),
            ('published','.NetworkSettings.Ports'),('devices','.HostConfig.Devices'),('capadd','.HostConfig.CapAdd')]
        return '\n'.join(json.dumps(info[key],separators=(',',':')) for key,_ in fields)

    def test_initialize_uses_real_typed_validate_chain_and_exact_source_contract(self):
        output=self._initialize_inspect_output()
        with patch.object(c.observation,'capture',return_value=output):
            value=c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)
        self.assertEqual(value['entrypoint'],['python'])
        self.assertEqual(value['cmd'],[
            '-B','-m','scripts.community_first_install','--plan',
            p.ROOT+'/config/initialize.json','--center-keys',p.ROOT+'/config/center-keys.json'])
        self.assertFalse(value['running'])

    def test_initialize_entrypoint_drift_rejected_by_real_validate_chain(self):
        output=self._initialize_inspect_output(entrypoint=['/bin/sh'])
        with patch.object(c.observation,'capture',return_value=output):
            with self.assertRaisesRegex(Exception,'LEGACY_INITIALIZE_ENTRYPOINT_CHANGED'):
                c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)


    def test_initialize_validator_reason_is_preserved_as_safe_hold(self):
        output=self._initialize_inspect_output()
        with patch.object(c.observation,'capture',return_value=output), \
             patch.object(c.original,'validate',side_effect=c.original.Rejected('CONTAINER_ISOLATION_CHANGED')):
            with self.assertRaisesRegex(c.controller.Hold,'CONTAINER_ISOLATION_CHANGED'):
                c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)

    def test_initialize_mounts_are_exactly_original_two_binds(self):
        output=self._initialize_inspect_output()
        with patch.object(c.observation,'capture',return_value=output):
            value=c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)
        self.assertEqual(len(value['mounts']),2)
        self.assertFalse(next(m for m in value['mounts'] if m['Destination']==p.ROOT+'/config')['RW'])
        self.assertTrue(next(m for m in value['mounts'] if m['Destination']==p.ROOT+'/data')['RW'])

    def test_initialize_extra_or_changed_mount_rejected(self):
        output=self._initialize_inspect_output()
        fields=c.original.INSPECT_FIELDS+[('ports','.HostConfig.PortBindings'),
            ('published','.NetworkSettings.Ports'),('devices','.HostConfig.Devices'),('capadd','.HostConfig.CapAdd')]
        rows=output.splitlines()
        values=[json.loads(x) for x in rows]
        idx=[k for k,_ in fields].index('mounts')
        values[idx].append({'Type':'bind','Source':p.RUN,'Destination':p.RUN,'RW':True})
        changed='\n'.join(json.dumps(v,separators=(',',':')) for v in values)
        with patch.object(c.observation,'capture',return_value=changed):
            with self.assertRaisesRegex(Exception,'LEGACY_INITIALIZE_MOUNTS_CHANGED'):
                c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)

    def test_initialize_network_mode_is_exactly_none(self):
        output=self._initialize_inspect_output()
        with patch.object(c.observation,'capture',return_value=output):
            value=c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)
        self.assertEqual(value['network'],'none')

    def test_initialize_network_drift_rejected_by_real_validate_chain(self):
        output=self._initialize_inspect_output(network='bridge')
        with patch.object(c.observation,'capture',return_value=output):
            with self.assertRaisesRegex(Exception,'LEGACY_INITIALIZE_NETWORK_CHANGED'):
                c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)

    def test_initialize_cmd_drift_rejected_by_real_validate_chain(self):
        cmd=list(c.INITIALIZE_CMD);cmd[-1]=p.ROOT+'/config/other-keys.json'
        output=self._initialize_inspect_output(cmd=cmd)
        with patch.object(c.observation,'capture',return_value=output):
            with self.assertRaisesRegex(Exception,'LEGACY_INITIALIZE_CMD_CHANGED'):
                c.inspect_bound(self.INITIALIZE_ID,self.IMAGE,historical_initialize=True)


class CBoundaryReasonClassification(unittest.TestCase):
    def test_known_numeric_hold_code_is_reported_without_secret(self):
        with patch.object(h,'Session') as session:
            session.return_value.acquire.side_effect=h.u.Hold('V2_SOURCE_CHANGED')
            with patch('builtins.print') as output:
                self.assertEqual(h.main(['--resume-c-before-confirmation']),2)
        record=json.loads(output.call_args.args[0])
        self.assertEqual(record['result']['reason'],'V2_SOURCE_CHANGED')

    def test_untrusted_exception_text_remains_redacted(self):
        with patch.object(h,'Session') as session:
            session.return_value.acquire.side_effect=RuntimeError('secret=PRIVATE_VALUE')
            with patch('builtins.print') as output:
                self.assertEqual(h.main(['--resume-c-before-confirmation']),2)
        record=json.loads(output.call_args.args[0])
        self.assertEqual(record['result']['reason'],'BC_BOUNDARY_UNKNOWN')
        self.assertEqual(record['result']['error_type'],'RuntimeError')
        self.assertTrue(record['result']['safe_call_trail'])
        self.assertNotIn('PRIVATE_VALUE',json.dumps(record))

if __name__=='__main__':unittest.main()


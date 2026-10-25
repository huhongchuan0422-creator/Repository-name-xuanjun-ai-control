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

A_SOURCE_COMMIT='1d639347f404f952998b3b414a95e48f66571c3c'
def frozen_a_source():
    path=os.environ.get('COMMUNITY_TEST_A_ENTRY_FILE')
    if path:return Path(path).read_bytes()
    return subprocess.check_output(['git','show',A_SOURCE_COMMIT+':scripts/community_preview_site_prepare.py'])

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
        # Model the immutable B-resume-admission record produced by the real
        # admission path; C tests must bind both records, not synthesize one later.
        admission=dict(format=1,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=self.session.pins(),
            old_b_intent_sha256=s.sha(s.canonical(intent)),
            old_b_approval_sha256=s.sha(old_braw),
            old_freeze_sha256=s.sha(old_freeze_raw),
            old_stage_permit_sha256=None,
            resume_approval_sha256=s.sha(s.canonical(resume)),
            resume_freeze_sha256=s.sha(s.canonical(fresh)),
            actions=['RESUME_SNAPSHOT','THREE_ISOLATED_CLONES'])
        self.write(h.resume_record_path(),s.canonical(admission))
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
        # Both historical B and freeze windows are expired; only the new C
        # operation approval below is fresh. Historical bytes stay unchanged.
        self.clock=2400
        # Historical B-resume carrier is deliberately distinct from current C
        # source carrier. Rebind the fixture record hashes, never the old B data.
        resume,_=h.document(h.resume_record_path())
        bresume,_=h.document(h.B_RESUME_APPROVAL)
        historical_carrier='a'*64
        bresume['carrier_manifest_sha256']=historical_carrier
        self.write(h.B_RESUME_APPROVAL,s.canonical(bresume))
        resume['carrier_manifest_sha256']=historical_carrier
        resume['resume_approval_sha256']=s.sha(s.canonical(bresume))
        self.write(h.resume_record_path(),s.canonical(resume))
        q=self.fresh_session()
        q.configure_resumed_b_context()
        self.assertNotEqual(q.approved_stamp,historical_carrier)
        q.resume_mode=True
        self.assertFalse(q.bdone)
        q.backup=h.open_private(s.BACKUP+'/clone-results.json')
        semantic=q.evidence(True)
        candidate=q.candidate(semantic)
        # The original C approval is immutable historical evidence; never edit it.
        old_approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],
            carrier_manifest_sha256=q.pins(),plan_sha256='d50795e5cd54974c0acd7692d38da3c97e0ff1809a6a7c30d77dce2c24aabbea',
            issued_at=1,expires_at=2,actions=h.C_ACTIONS)
        self.write(h.C_APPROVAL,s.canonical(old_approval))
        record=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
            carrier_manifest_sha256=q.approved_stamp,evidence_sha256=s.sha(s.canonical(h.Session._without_observed_at(semantic))),
            plan=candidate,plan_sha256=candidate['plan_sha256'],
            plan_document_sha256=s.sha(s.canonical(candidate)),
            issued_at=self.clock,expires_at=self.clock+600)
        self.write(h.C_RESUME_PLAN,s.canonical(record))
        approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=candidate['attempt'],
            carrier_manifest_sha256=q.pins(),plan_sha256=candidate['plan_sha256'],
            issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
        self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
        os.close(q.backup);q.backup=None
        return q,candidate

    def test_c_preconfirmation_tty_mismatch_then_same_plan_resume_once(self):
        q,candidate=self._prepare_completed_b_before_c_proof()
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
        q,candidate=self._prepare_completed_b_before_c_proof()
        old_c=Path(h.C_APPROVAL).read_bytes()
        Path(h.C_RESUME_PLAN).unlink()
        Path(h.C_RESUME_APPROVAL).unlink()
        original=h.Session._c_resume_approval
        def owner_approves(session,plan):
            if not Path(h.C_RESUME_APPROVAL).exists():
                record,_=h.document(h.C_RESUME_PLAN)
                approval=dict(format=1,host=p.HOST,mode=h.MODE,attempt=h.attempt(),
                    carrier_manifest_sha256=session.pins(),plan_sha256=record['plan_sha256'],
                    issued_at=self.clock,expires_at=self.clock+600,actions=h.C_ACTIONS)
                self.write(h.C_RESUME_APPROVAL,s.canonical(approval))
            return original(session,plan)
        output=io.StringIO()
        with patch.object(h.Session,'_c_resume_approval',owner_approves),contextlib.redirect_stdout(output):
            result=q.resume_c_before_confirmation()
        self.assertIn('"plan":',output.getvalue())
        self.assertIn(candidate['attempt'],output.getvalue())
        self.assertEqual(result['phase'],'COMMITTED')
        self.assertEqual(Path(h.C_APPROVAL).read_bytes(),old_c)
        self.assertTrue(Path(h.C_RESUME_PLAN).exists())
        self.assertTrue(Path(h.C_RESUME_APPROVAL).exists())

    def test_c_preconfirmation_wrong_plan_or_expired_approval_holds_zero_mutation(self):
        q,candidate=self._prepare_completed_b_before_c_proof()
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

    def test_c_preconfirmation_observed_at_drift_reuses_persisted_approved_plan(self):
        q,candidate=self._prepare_completed_b_before_c_proof()
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
        q,candidate=self._prepare_completed_b_before_c_proof()
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
        q,candidate=self._prepare_completed_b_before_c_proof()
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
        q,candidate=self._prepare_completed_b_before_c_proof()
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
        with patch.object(h,'acknowledge',return_value=None):
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

    def test_known_failure_recovery_uses_new_c_resume_approval_provenance(self):
        q=self.fresh_session()
        candidate={'attempt':h.attempt(),'plan_sha256':'a'*64}
        proof={'format':1,'mode':h.MODE,'host':p.HOST,'attempt':h.attempt(),
            'plan':candidate,'approval_sha256':'b'*64,'evidence':{},'approval_kind':'C_RESUME_APPROVAL'}
        with patch.object(h,'document',return_value=(proof,b'proof')),\
             patch.object(q,'configure_resumed_recovery',return_value=True),\
             patch.object(h,'open_private',return_value=44),\
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
        q,candidate=self._prepare_completed_b_before_c_proof()
        with patch.object(h,'acknowledge',return_value=None):
            result=q.resume_c_before_confirmation()
        self.assertEqual(result['phase'],'COMMITTED')
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
a_path=os.environ.get('COMMUNITY_TEST_A_ENTRY_FILE')
if a_path:A=Path(a_path).read_bytes()
else:
 import subprocess
 A=subprocess.check_output(['git','show','1d639347f404f952998b3b414a95e48f66571c3c:scripts/community_preview_site_prepare.py'],cwd=repo)
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
        proc=subprocess.run([sys.executable,'-I','-B','-S','-c',worker,str(Path.cwd()),str(bundle)],capture_output=True,text=True)
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

if __name__=='__main__':unittest.main()


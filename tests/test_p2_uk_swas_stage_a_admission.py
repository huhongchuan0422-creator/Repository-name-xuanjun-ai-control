import base64, hashlib, json, sys, unittest, zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import p2_uk_stage_a_admission as a
def observation_fixture():
    ident=[1,2,33188,0,0,1,10,20,30]
    sha='a'*64
    return {
      'worker':{'state':'OBSERVED','current_identity':ident,'release':'e78bd7749414d1637012f57b65d2019955282fc3','source_files_read':9,'nine_file_pin':sha,'candidate_twelve_file_pin':None,'active_process':'UNKNOWN_NOT_QUERIED'},
      'config':{'state':'OBSERVED','identity':ident,'sha256':sha,'executor_sha256':None,'actor_matches':True,'state_root_matches':True,'github_owner_matches':True,'b5_hook_present':True,'website_hook_present':False,'b5_hook_reference_matches':True,'b5_hook_sha256':sha},
      'binding':{'state':'OBSERVED','identity':ident,'sha256':sha,'project_matches':True,'target_matches':True,'operation_matches':True,'execution_identity_matches':True,'v3_sha_matches':True,'request_id_present':True,'valid_from':None,'valid_until':None,'single_consumption':'UNKNOWN_NOT_QUERIED'},
      'frozen_root':{'state':'OBSERVED','root_identity':ident,'expected':59,'matched':59,'missing':0,'mismatched':0,'unobserved':0,'all_3_metadata_14_controller_42_runtime_match':True}}

class AdmissionTests(unittest.TestCase):
    def valid(self):
        return {'scope':'UK_STAGE_A_ADMISSION_METADATA_ONLY','host_matches':True,'euid':0,'egid':0,'sudo_uid_1000':True,'writes':False,'network':False,'product_imports':False,'stage_a_executed':False,'db_rows_read':0,**observation_fixture(),'queue':{'state':'METADATA_ONLY','sqlite_connected':False,'conflicts':'UNKNOWN_DB_NOT_OPENED','rows_read':0,'main':{'state':'ABSENT'},'wal':{'state':'ABSENT'},'shm':{'state':'ABSENT'},'journal':{'state':'ABSENT'}},'state':'OBSERVED_REVIEW_REQUIRED','read_bytes':65536}
    def output(self,v,inner=0): return json.dumps(v,separators=(',',':'),sort_keys=True)+'\n\nEXIT_CODE='+str(inner)+'\n'
    def test_original_bytes_pin_and_command_bound(self):
        raw=a.wrapper_bytes(ROOT/'scripts')
        self.assertEqual(len(raw),16975);self.assertEqual(hashlib.sha256(raw).hexdigest(),a.WRAPPER_SHA256)
        cmd=a.command_content(ROOT/'scripts').encode();self.assertLessEqual(len(cmd),16384)
        encoded=cmd.split(b"printf '%s' '",1)[1].split(b"' |",1)[0]
        restored=zlib.decompress(base64.b64decode(encoded))
        self.assertEqual(restored,raw)
    def test_valid_observation_is_not_stagea_pass(self):
        r=a.safe_receipt(self.output(self.valid()),0)
        self.assertEqual(r['state'],'OBSERVED_REVIEW_REQUIRED');self.assertFalse(r['stage_a_pass']);self.assertFalse(r['install_authorized']);self.assertEqual(r['db_rows_read'],0)
    def test_reject_missing_field_wrong_host_and_identity(self):
        for mutate in ('missing','host','euid','egid','sudo','network','stagea','dbrows'):
            v=self.valid()
            if mutate=='missing':v.pop('queue')
            elif mutate=='host':v['host_matches']=False
            elif mutate=='euid':v['euid']=True
            elif mutate=='egid':v['egid']=1
            elif mutate=='sudo':v['sudo_uid_1000']=False
            elif mutate=='network':v['network']=True
            elif mutate=='stagea':v['stage_a_executed']=True
            else:v['db_rows_read']=False
            with self.subTest(mutate=mutate),self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(v),0)
    def test_inner_failure_outer_zero_not_success(self):
        v=self.valid();v={k:x for k,x in v.items() if k not in ('worker','config','binding','frozen_root','queue')};v['state']='HOST_OR_SUDO_IDENTITY_HOLD';v['host_matches']=False;v['read_bytes']=65536
        r=a.safe_receipt(self.output(v,2),0)
        self.assertEqual(r['state'],'B5_ADMISSION_HOLD');self.assertFalse(r['redispatch_allowed'])
        with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(self.valid(),2),0)
    def test_real_wrapper_blank_line_and_strict_exit_envelope(self):
        raw=self.output(self.valid())
        self.assertIn('\n\nEXIT_CODE=0\n',raw)
        result=a.safe_receipt(raw,0)
        self.assertIn('queue_metadata',result);self.assertIn('historical_db_identity_matches',result['queue_metadata']['main'] if result['queue_metadata']['main'].get('state')=='PRESENT' else {'historical_db_identity_matches':None})
        for bad in (raw.replace('EXIT_CODE=0','EXIT_CODE=1'),raw+'NOISE\n',raw.replace('\n\n','\n')):
            with self.subTest(bad=bad[-30:]),self.assertRaises(a.AdmissionHold):a.safe_receipt(bad,0)
    def test_outer_exit_bool_rejected(self):
        with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(self.valid()),False)
    def test_output_noise_duplicate_or_extra_line_rejected(self):
        v=self.valid();line=json.dumps(v,separators=(',',':'))
        for raw in (line+'\nEXIT_CODE=0\nNOISE\n',line[:-1]+',"state":"OBSERVED_REVIEW_REQUIRED"}\nEXIT_CODE=0\n','x'*17000):
            with self.subTest(length=len(raw)),self.assertRaises(a.AdmissionHold):a.safe_receipt(raw,0)
    def test_queue_rows_or_sqlite_access_rejected(self):
        present={'state':'PRESENT','identity':[1,2,33188,0,0,1,10,20,30],'regular':True,'historical_db_identity_matches':True}
        v=self.valid();v['queue']['main']=present
        self.assertEqual(a.safe_receipt(self.output(v),0)['queue_metadata']['main']['state'],'PRESENT')
        for field,value in (('rows_read',1),('sqlite_connected',True),('conflicts','NONE')):
            v=self.valid();v['queue'][field]=value
            with self.subTest(field=field),self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(v),0)
    def test_new_action_contract_is_separate_from_existing_actions(self):
        req={'purpose':'B5_STAGE_A_ADMISSION_METADATA_ONLY','attempt':'attempt-1'}
        run={'operation':'B5_ADMISSION_METADATA_ONLY','attempt':'attempt-1'}
        query={'operation':'B5_ADMISSION_QUERY','attempt':'attempt-1'}
        self.assertTrue(a.validate_action_contract('b5-admission',req,run))
        self.assertTrue(a.validate_action_contract('b5-admission-query',req,query))
        for old in ('remote-run','cloud-query','read-only-diagnostic','read-only-diagnostic-query'):
            with self.subTest(old=old),self.assertRaises(a.AdmissionHold):
                a.validate_action_contract(old,req,run)
        with self.assertRaises(a.AdmissionHold):a.validate_action_contract('b5-admission',req,query)
        with self.assertRaises(a.AdmissionHold):a.validate_action_contract('b5-admission',dict(req,purpose='READ_ONLY_DIAGNOSTIC_ONLY'),run)
    def test_hold_minimal_and_full_envelopes(self):
        v={k:x for k,x in self.valid().items() if k not in ('worker','config','binding','frozen_root','queue')}
        v['state']='HOST_OR_SUDO_IDENTITY_HOLD';v['host_matches']=False;v['read_bytes']=65536
        self.assertEqual(a.safe_receipt(self.output(v,2),0)['state'],'B5_ADMISSION_HOLD')
        self.assertEqual(a.safe_receipt('{\"state\":\"OUTPUT_BOUND_HOLD\"}\n\nEXIT_CODE=2\n',0)['hold_reason'],'OUTPUT_BOUND_HOLD')
    def test_partial_deadline_prefix_and_holds(self):
        v=self.valid();base={k:x for k,x in v.items() if k not in ('worker','config','binding','frozen_root','queue')}
        base['state']='DEADLINE_HOLD'
        for n in range(6):
            candidate=dict(base)
            for k in ('worker','config','binding','frozen_root','queue')[:n]:candidate[k]=v[k]
            r=a.safe_receipt(self.output(candidate,2),0)
            self.assertEqual(r['state'],'B5_ADMISSION_HOLD')
            self.assertFalse(r['redispatch_allowed'])
        for bad in (dict(base,queue=v['queue']),dict(base,worker=v['worker'],binding=v['binding']),dict(base,unexpected='PRIVATE')):
            with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(bad,2),0)
        early=dict(base,state='HOST_OR_SUDO_IDENTITY_HOLD',host_matches=False,worker=v['worker'])
        with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(early,2),0)
    def test_strict_observation_whitelist_and_types(self):
        v=self.valid();r=a.safe_receipt(self.output(v),0)
        self.assertEqual(r['worker_metadata']['nine_file_pin'],'a'*64)
        self.assertEqual(r['frozen_root_metadata']['matched'],59)
        for k,field,value in (('worker','release','/tmp/evil'),('worker','source_files_read',True),
             ('worker','nine_file_pin','NOT_SHA'),('config','actor_matches',1),
             ('binding','valid_from',True),('binding','single_consumption','PRIVATE'),
             ('frozen_root','matched',True),('frozen_root','expected',58)):
            t=self.valid();t[k][field]=value
            with self.subTest(k=k,field=field),self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(t),0)
        for k in ('worker','config','binding','frozen_root'):
            t=self.valid();t[k]['unexpected_private_text']='SYNTHETIC_CANARY_NOT_A_REAL_SECRET'
            with self.subTest(k=k),self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(t),0)
        t=self.valid();t['queue']['main']={'state':'PRESENT','identity':[1,2,33188,0,0,1,10,20,30],
          'regular':True,'historical_db_identity_matches':True,'unexpected_private_text':'SYNTHETIC'}
        with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(t),0)
    def test_worker_unknown_release_shape(self):
        v=self.valid();v['worker']={'state':'UNKNOWN_RELEASE_NOT_READ','current_identity':[1,2,33188,0,0,1,10,20,30],'target_sha256':'b'*64}
        self.assertEqual(a.safe_receipt(self.output(v),0)['worker_state'],'UNKNOWN_RELEASE_NOT_READ')
        v['worker']['extra']='CANARY'
        with self.assertRaises(a.AdmissionHold):a.safe_receipt(self.output(v),0)
    def test_wrapper_pin_mismatch_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            Path(td,a.WRAPPER_NAME).write_bytes(b'wrong')
            with self.assertRaises(a.AdmissionHold):a.command_content(td)
if __name__=='__main__':unittest.main(verbosity=2)

# These cases run in the repository CI against the actual existing split_cloud,
# GitJournal fixture and transport module. They are skipped only in this delivery
# container, which has no full repository checkout.
try:
    import importlib.util
    transport_path=ROOT/'scripts'/'p2_uk_swas_diagnostic.py'
    if transport_path.is_file():
        spec=importlib.util.spec_from_file_location('b5_admission_transport_under_test',str(transport_path))
        d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
    else:
        d=None
except Exception:
    d=None

@unittest.skipIf(d is None,'requires exact repository main checkout; not present in artifact-only container')
class OriginalTransportIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        p=ROOT/'tests'/'test_p2_uk_swas_diagnostic.py'
        spec=importlib.util.spec_from_file_location('b5_admission_existing_transport_fixtures',str(p))
        cls.fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.fixtures)
    def make_case(self, operation, invoke='', comment=1):
        case=self.fixtures.SplitCloudTests('test_cloud_intent_precedes_credentials');case.setUp();self.addCleanup(case.doCleanups)
        case.request['purpose']='B5_STAGE_A_ADMISSION_METADATA_ONLY'
        case.policy=case.make_policy(operation,invoke,comment)
        binding=case.policy['binding']
        helper=d.admission_module()
        binding['command_sha256']=hashlib.sha256(helper.command_content(ROOT/'scripts').encode()).hexdigest()
        permit={'decision':'B5_ADMISSION_APPROVED','binding':binding,'issued_unix':90,
                'expires_unix':200,'max_executions':1,'install_allowed':False,
                'private_inputs_allowed':False}
        case.body='P2_UK_SPLIT_ONCE\n'+json.dumps(permit)
        case.policy['approval_body_sha256']=hashlib.sha256(case.body.encode()).hexdigest()
        return case
    def valid_output(self):
        v={'scope':'UK_STAGE_A_ADMISSION_METADATA_ONLY','host_matches':True,'euid':0,'egid':0,
           'sudo_uid_1000':True,'writes':False,'network':False,'product_imports':False,
           'stage_a_executed':False,'db_rows_read':0,**observation_fixture(),'queue':{'state':'METADATA_ONLY',
           'sqlite_connected':False,'conflicts':'UNKNOWN_DB_NOT_OPENED','rows_read':0,
           'main':{'state':'ABSENT'},'wal':{'state':'ABSENT'},'shm':{'state':'ABSENT'},
           'journal':{'state':'ABSENT'}},'state':'OBSERVED_REVIEW_REQUIRED','read_bytes':65536}
        return json.dumps(v,separators=(',',':'))+'\n\nEXIT_CODE=0\n'
    def bind_rpc(self,case,status='Success'):
        parent=case;output=self.valid_output()
        def call(obj,endpoint,action,**kw):
            parent.calls.append(action)
            if action=='RunCommand':return {'InvokeId':'t-real-fixture'}
            return {'InvocationResult':{'InvokeId':kw['InvokeId'],'InstanceId':d.receipt.INSTANCE,
                'InvocationStatus':status,'ExitCode':0,'Output':output}}
        old_call=case.rpc.__class__.__call__;case.rpc.__class__.__call__=call;self.addCleanup(setattr,case.rpc.__class__,'__call__',old_call)
        case.factory=lambda:case.rpc
    def test_b5_run_uses_admin_and_compressed_pinned_wrapper(self):
        case=self.make_case('B5_ADMISSION_METADATA_ONLY');captured={}
        old=case.rpc.__class__.__call__
        def call(obj,endpoint,action,**kw):
            if action=='RunCommand':captured.update(kw)
            return old(obj,endpoint,action,**kw)
        case.rpc.__class__.__call__=call;self.addCleanup(setattr,case.rpc.__class__,'__call__',old)
        result=case.call('b5-admission')
        self.assertEqual(result['state'],'CLOUD_DISPATCHED_AWAIT_SEPARATE_QUERY')
        self.assertEqual(captured['WorkingUser'],'admin');self.assertEqual(captured['WorkingDir'],'/home/admin')
        self.assertLessEqual(len(captured['CommandContent'].encode()),16384)
        self.assertEqual(case.calls.count('RunCommand'),1)
    def test_b5_duplicate_attempt_is_not_redispatched(self):
        case=self.make_case('B5_ADMISSION_METADATA_ONLY')
        case.call('b5-admission')
        with self.assertRaises(RuntimeError):case.call('b5-admission')
        self.assertEqual(case.calls.count('RunCommand'),1)
    def test_b5_query_uses_saved_invoke_only_and_unknown_is_not_replayed(self):
        case=self.make_case('B5_ADMISSION_METADATA_ONLY');self.bind_rpc(case)
        case.call('b5-admission')
        case.policy=case.make_policy('B5_ADMISSION_QUERY','t-real-fixture',2)
        binding=case.policy['binding'];binding['command_sha256']=hashlib.sha256(d.admission_module().command_content(ROOT/'scripts').encode()).hexdigest()
        permit={'decision':'B5_ADMISSION_APPROVED','binding':binding,'issued_unix':90,'expires_unix':200,
                'max_executions':1,'install_allowed':False,'private_inputs_allowed':False}
        case.body='P2_UK_SPLIT_ONCE\n'+json.dumps(permit);case.policy['approval_body_sha256']=hashlib.sha256(case.body.encode()).hexdigest()
        self.assertEqual(case.call('b5-admission-query','t-real-fixture')['state'],'B5_ADMISSION_RESULT')
        self.assertEqual(case.calls.count('RunCommand'),1);self.assertEqual(case.calls.count('DescribeInvocationResult'),1)
    def test_actual_cli_route_calls_existing_supervisor_and_entry(self):
        seen={}
        def supervisor(action,operation):
            seen['supervisor_action']=action
            return operation(None)
        def entry(action,attempt,invoke_id):
            seen.update(action=action,attempt=attempt,invoke_id=invoke_id)
            return 23
        self.assertEqual(d.dispatch_cli_action('b5-admission','attempt-x','',supervisor,entry),23)
        self.assertEqual(seen,{'supervisor_action':'run-once','action':'b5-admission','attempt':'attempt-x','invoke_id':''})
        self.assertEqual(d.dispatch_cli_action('b5-admission-query','attempt-x','invoke-x',supervisor,entry),23)
        self.assertEqual(seen['action'],'b5-admission-query');self.assertEqual(seen['invoke_id'],'invoke-x')
    def test_existing_remote_run_keeps_root_identity(self):
        case=self.fixtures.SplitCloudTests('test_cloud_intent_precedes_credentials');case.setUp();self.addCleanup(case.doCleanups);captured={}
        old=case.rpc.__class__.__call__
        def call(obj,endpoint,action,**kw):
            if action=='RunCommand':captured.update(kw)
            return old(obj,endpoint,action,**kw)
        case.rpc.__class__.__call__=call;self.addCleanup(setattr,case.rpc.__class__,'__call__',old)
        case.call('remote-run')
        self.assertEqual(captured['WorkingUser'],'root');self.assertEqual(captured['WorkingDir'],'/root')

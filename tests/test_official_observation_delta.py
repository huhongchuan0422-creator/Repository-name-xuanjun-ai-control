import copy,hashlib,json,os,tempfile,unittest
from types import SimpleNamespace
from unittest import mock
import test_delivery_ledger_route as fixture
from task_center_app import build_handler
from task_delivery_observer import MetadataReader
from task_delivery_observation import ApprovedObservationReader,ObservationUnavailable,normalize

COLLECTOR='main-bounded-sessions-20261116'
def sample():
    def rec(msg,role='toolResult'):
        return {'role':role,'tool_name':'exec' if role=='toolResult' else None,'is_error':False if role=='toolResult' else None,'observed_timestamp_ms':1794800321745,'message_ref':msg,'run_ref':'00000000-0000-4000-8000-000000000002','stop_reason':None if role=='toolResult' else 'stop','tool_calls':[]}
    obs={'role_ref':'ledger-author','source_api':'sessions_history','query':{'session_ref':'agent:developer:subagent:00000000-0000-4000-8000-000000000001','limit':2,'includeTools':True},'pending_count':0,'truncated':True,'content_truncated':True,'records':[rec('00000000-0000-4000-8000-000000000003'),rec('00000000-0000-4000-8000-000000000004','assistant')]}
    return {'schema_version':'1.0','source':'main official agents_list and bounded sessions_history calls','observation_time_basis':'record time only','scope':'ledger only','purpose':'no authority','limitations':['bounded'],'observations':[obs]}
class MetadataTests(unittest.TestCase):
    def test_strict_fields_and_no_raw_payload(self):
        for field in ('body','rawlog','arguments'):
            x=sample();x['observations'][0]['records'][0][field]='synthetic-example';self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();del x['observations'][0]['records'][0]['run_ref'];self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();x['observations'][0]['records'][0]['tool_calls']=[{'arguments':'synthetic-example'}];self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
    def test_dedup_stale_unknown_and_anonymous_role(self):
        x=sample();x['observations'][0]['records']=[x['observations'][0]['records'][0]]*2
        out=normalize(x,COLLECTOR);self.assertEqual(out['state'],'UNTRUSTED_METADATA_ONLY');self.assertEqual(out['source_observation_verified'],'UNAVAILABLE');self.assertEqual(len(out['records']),1);r=out['records'][0]
        for key in ('pending','actual_received','worker_started','business_result','writer_authority','permission','unresolved_effects'):self.assertEqual(r[key],'UNKNOWN')
        self.assertEqual(r['freshness'],'STALE');self.assertTrue(r['history_truncated']);self.assertFalse(out['dispatch_performed']);self.assertEqual(out['handoff_completed'],'UNKNOWN')
        text=json.dumps(out);self.assertNotIn('agent:developer',text);self.assertNotIn('00000000-0000',text)
        y=copy.deepcopy(x['observations'][0]);y['query']['session_ref']='agent:developer:subagent:00000000-0000-4000-8000-000000000005';y['records'][0]['message_ref']='00000000-0000-4000-8000-000000000006';y['records'][0]['run_ref']='00000000-0000-4000-8000-000000000007';y['records']=y['records'][:1]
        out=normalize(dict(x,observations=[x['observations'][0],y]),COLLECTOR);self.assertNotEqual(out['records'][0]['session_ref'],out['records'][1]['session_ref']);self.assertEqual(out['records'][1]['role_identity_verification'],'UNKNOWN')
    def test_unapproved_json_and_input_mutation_not_trusted(self):
        with tempfile.NamedTemporaryFile() as f:
            raw=json.dumps(sample()).encode();f.write(raw);f.flush();reader=ApprovedObservationReader(f.name,COLLECTOR)
            self.assertRaises(ObservationUnavailable,reader.read)
            # Test-only injection of an allowlisted fingerprint exercises strict parser;
            # never used by the app or as a real identity verifier.
            with mock.patch.dict('task_delivery_observation.APPROVED_SNAPSHOTS',{COLLECTOR:hashlib.sha256(raw).hexdigest()}):self.assertEqual(len(reader.read()['records']),2)
            f.seek(0);f.write(raw+b' ');f.truncate();f.flush();self.assertRaises(ObservationUnavailable,reader.read)
    def test_source_types_and_duplicate_conflicts(self):
        x=sample();x['source']='github-comment';self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();x['observations'][0]['truncated']='false';self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();del x['observations'][0]['content_truncated'];self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();r=x['observations'][0]['records'][0];different=dict(r,observed_timestamp_ms=r['observed_timestamp_ms']+1);x['observations'][0]['records']=[r,different];self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        x=sample();y=copy.deepcopy(x['observations'][0]);y['role_ref']='ledger-reviewer';x['observations'].append(y);self.assertRaises(ObservationUnavailable,normalize,x,COLLECTOR)
        with self.assertRaises(ObservationUnavailable):ApprovedObservationReader('irrelevant','random-comment-source')

class OfficialRouteTests(unittest.TestCase):
    def setUp(self):self.f=fixture.RouteTests();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def call(self,reader,path):
        cls=build_handler(self.f.db,fixture.KEY,'tenant-ui','viewer',admin_token=fixture.ADMIN,delivery_ledger_reader=reader)
        h=cls.__new__(cls);h.path=path;h.command='GET';h.headers={'Host':'localhost:8765','X-Test-Admin-Token':fixture.ADMIN};h.server=SimpleNamespace(server_port=8765)
        out=[];h._send=lambda status,body,content_type,extra_headers=None:out.append((status,body,extra_headers));h.do_GET();return out[0]
    def test_real_approved_input_through_main_handler(self):
        path=os.environ.get('OFFICIAL_SAMPLE_PATH')
        if not path:self.skipTest('approved source not mounted in ordinary isolated tests')
        source=ApprovedObservationReader(path,COLLECTOR);reader=MetadataReader(os.path.join(self.f.tmp.name,'not-mounted'),'pilot354','ledger-writer','tenant-ui',source)
        status,body,_=self.call(reader,'/api/admin/delivery-ledger');self.assertEqual(status,200);v=json.loads(body.decode());obs=v['observations']
        self.assertEqual(obs['state'],'OBSERVED_METADATA_ONLY');self.assertEqual(obs['source_observation_verified'],'MAIN_APPROVED_SNAPSHOT_BYTES_MATCH');self.assertEqual(len(obs['records']),4);self.assertEqual(obs['scope'],'LEDGER_IMPLEMENTATION_AND_REVIEW_ONLY')
        self.assertEqual(obs['official_api_issuer_verification'],'UNAVAILABLE');self.assertEqual(obs['writer_verification'],'UNKNOWN');self.assertEqual(obs['permission_verification'],'UNKNOWN')
        self.assertEqual(obs['global_idle'],'UNKNOWN');self.assertEqual(obs['freshness'],'STALE');self.assertTrue(all(r['actual_received']=='UNKNOWN' and r['worker_started']=='UNKNOWN' and r['business_result']=='UNKNOWN' for r in obs['records']))
        self.assertEqual([r['observation_kind'] for r in obs['records']].count('TOOL_RESULT_OBSERVED'),2);self.assertEqual([r['observation_kind'] for r in obs['records']].count('ROLE_RESULT_OBSERVED'),2)
        self.assertNotIn('agent:developer',body.decode());self.assertNotIn('agent:platform-engineer',body.decode());self.assertEqual(v['ledger_state'],'UNAVAILABLE');self.assertEqual(v['tasks'],[]);self.assertEqual(self.f.reader.view()['tasks'][0]['permissions'][0]['validity'],'EXPIRED')
        status,body,headers=self.call(reader,'/api/admin/delivery-handoff?scope=ledger-self-observation');self.assertEqual(status,200);out=json.loads(body.decode());self.assertEqual(len(out['records']),4);self.assertEqual(out['handoff_completed'],'UNKNOWN');self.assertEqual(out['business_acceptance'],'UNKNOWN');self.assertIn(('Content-Disposition','attachment; filename="xuanjun-observation-evidence.json"'),headers)
        self.assertEqual(self.call(reader,'/api/admin/delivery-handoff?scope=ledger-self-observation&task_id=task1')[0],503)
    def test_unavailable_observation_does_not_pollute_task(self):
        source=ApprovedObservationReader('/path-does-not-exist',COLLECTOR);reader=MetadataReader(self.f.root,'synthetic','writer','tenant-ui',source)
        status,body,_=self.call(reader,'/api/admin/delivery-ledger');self.assertEqual(status,200);v=json.loads(body.decode());self.assertEqual(v['observations']['state'],'UNAVAILABLE');self.assertEqual(v['tasks'][0]['task_id'],'task1')
        self.assertEqual(self.call(reader,'/api/admin/delivery-handoff?scope=ledger-self-observation')[0],503)
if __name__=='__main__':unittest.main()

"""New admission seam only. Real HTTP, canonical temporary ledger, no grants."""
import copy
import hashlib
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_task_center_app as fixture
from task_supervisor import canonical
from execution_policy_gateway import ExecutionPolicyGateway

class ExistingAdmissionTests(unittest.TestCase):
    def setUp(self):
        from urllib.request import build_opener,ProxyHandler
        opener_patch=patch.object(fixture,'urlopen',build_opener(ProxyHandler({})).open);opener_patch.start();self.addCleanup(opener_patch.stop)
        self.f=fixture.TaskCenterAppTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        from task_supervisor import Supervisor
        self.s=Supervisor(self.f.db);self.addCleanup(self.s.close)
        self.spec={'goal':'original recovery','allowed_files':['scripts/example.py'],'acceptance':['same commit tests','independent review']}
        digest=hashlib.sha256(canonical(self.spec).encode()).hexdigest()
        # Only fixture seed: actual helper cannot mutate task/spec/registration.
        self.s.db.execute("UPDATE tasks SET spec_sha256=? WHERE task_id='demo-b'",(digest,));self.s.db.commit()
        self.query={'action':'QUERY_CANONICAL_ASSET','task_id':'demo-b','query_id':'original-query','asset_key':'fake:demo-b','source_version':'input-v1'}
        self.f.post(self.query)
        self.args={'task_id':'demo-b','project_id':'demo-project','checkpoint_sha256':'a'*64,'spec':self.spec,'scope':['READ_SOURCE','WRITE_SOURCE','RUN_TEST'],'query_ids':['original-query'],'reuse_reason':'reuse original canonical kernel, no new task or queue'}
    def post(self, action, args):
        return self.f.post(dict(args,action=action))
    def rejected(self,value,expect_error=None):
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as caught:self.f.post(value)
        self.assertEqual(caught.exception.code,400)
    def status(self):
        return self.post('TASK_ADMISSION_STATUS',{'task_id':'demo-b','project_id':'demo-project'})
    def test_existing_task_records_and_reads_back_idempotently_without_claim(self):
        before=self.status();self.assertEqual(before['work_specs'],[]);self.assertEqual(before['units'],[])
        result=self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        self.assertEqual(len(result['work_specs']),1);self.assertEqual(len(result['units']),1);self.assertEqual(len(result['dispatch_preflights']),1)
        self.assertEqual(result['task']['state'],'READY');self.assertEqual(result['task']['authority_state'],'NONE');self.assertFalse(result['authority_created'])
        self.assertEqual(result,self.post('RECORD_EXISTING_TASK_ADMISSION',self.args))
        read=self.status();self.assertEqual(result['work_specs'],read['work_specs']);self.assertEqual(result['units'],read['units'])
        self.assertNotIn('query_json',read['asset_queries'][0])
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM tasks').fetchone()[0],3)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM gateway_graphs').fetchone()[0],1)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM resource_claims').fetchone()[0],0)
    def test_changed_spec_checkpoint_project_or_unknown_receipt_has_no_write(self):
        cases=[]
        for field,value in [('spec',dict(self.spec,goal='tampered')),('checkpoint_sha256','f'*64),('project_id','other'),('query_ids',['missing'])]:
            case=copy.deepcopy(self.args);case[field]=value;cases.append(case)
        for args in cases:self.rejected(dict(args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(self.status()['work_specs'],[]);self.assertEqual(self.status()['units'],[])
    def test_conflicting_existing_unit_is_preserved_no_spec_half_write(self):
        self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        changed=copy.deepcopy(self.args);changed['scope']=['READ_SOURCE']
        self.rejected(dict(changed,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(json.loads(self.status()['units'][0]['scope_json']),self.args['scope'])
    def test_retry_resumes_original_spec_checkpoint_after_unit_failure(self):
        with patch.object(ExecutionPolicyGateway,'record_unit',side_effect=ValueError('FIXTURE_UNIT_FAILURE')):
            self.rejected(dict(self.args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(len(self.status()['work_specs']),1);self.assertEqual(self.status()['units'],[])
        result=self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        self.assertEqual(len(result['work_specs']),1);self.assertEqual(len(result['units']),1)
    def test_wrong_version_or_unregistered_resource_receipt_cannot_admit(self):
        for suffix,key,version in [('wrong-version','fake:demo-b','other'),('wrong-resource','fake:other','input-v1')]:
            query=dict(self.query,query_id=suffix,asset_key=key,source_version=version)
            self.f.post(query)
            args=copy.deepcopy(self.args);args['query_ids']=[suffix]
            self.rejected(dict(args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(self.status()['work_specs'],[]);self.assertEqual(self.status()['units'],[])
    def test_required_project_and_task_identifiers_reject_null_empty_and_omission(self):
        for field in ('project_id','task_id'):
            for bad in (None,'',[],{}):
                args=copy.deepcopy(self.args);args[field]=bad
                self.rejected(dict(args,action='RECORD_EXISTING_TASK_ADMISSION'))
                status={'task_id':'demo-b','project_id':'demo-project'};status[field]=bad
                self.rejected(dict(status,action='TASK_ADMISSION_STATUS'))
            args=copy.deepcopy(self.args);del args[field]
            self.rejected(dict(args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(self.status()['work_specs'],[]);self.assertEqual(self.status()['units'],[])
    def test_conflicting_latest_resource_preflight_is_rejected_without_rewriting_history(self):
        first=self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        self.f.post(dict(self.query,query_id='other-resource',asset_key='fake:other'))
        other=self.post('RECORD_DISPATCH_PREFLIGHT',{'task_id':'demo-b','asset_version':'input-v1','query_ids':['other-resource'],'outcome':'NOT_FOUND','reuse_reason':'conflicting pre-existing resource stage'})
        self.assertNotEqual(first['admission']['preflight_id'],other['preflight_id'])
        before=tuple(self.s.db.iterdump())
        self.rejected(dict(self.args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(before,tuple(self.s.db.iterdump()))
    def test_old_conflicting_history_does_not_block_matching_current_preflight(self):
        first=self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        self.f.post(dict(self.query,query_id='other-resource',asset_key='fake:other'))
        other=self.post('RECORD_DISPATCH_PREFLIGHT',{'task_id':'demo-b','asset_version':'input-v1','query_ids':['other-resource'],'outcome':'NOT_FOUND','reuse_reason':'older history'})
        # Fixture history ordering only; product code never updates a preflight.
        observed=self.s.db.execute('SELECT observed_at FROM dispatch_preflights WHERE preflight_id=?',(first['admission']['preflight_id'],)).fetchone()[0]
        self.s.db.execute('UPDATE dispatch_preflights SET observed_at=? WHERE preflight_id=?',(observed-1,other['preflight_id']));self.s.db.commit()
        before=tuple(self.s.db.iterdump())
        result=self.post('RECORD_EXISTING_TASK_ADMISSION',self.args)
        self.assertEqual(result['admission']['preflight_id'],first['admission']['preflight_id'])
        self.assertEqual(before,tuple(self.s.db.iterdump()))
    def test_scope_cannot_supply_deploy_publish_or_authority(self):
        for change in ({'scope':['DEPLOY']},{'principal_id':'admin:fake'}):
            args=copy.deepcopy(self.args);args.update(change)
            self.rejected(dict(args,action='RECORD_EXISTING_TASK_ADMISSION'))
        self.assertEqual(self.status()['work_specs'],[])

if __name__=='__main__':unittest.main()

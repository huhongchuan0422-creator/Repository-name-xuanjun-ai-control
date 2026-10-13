import copy
import unittest
from scripts.ci_receipt_collection import collect_ci_receipt
from five_support import load_dependencies


def fixtures():
    policy=dict(id=1,name='fixture',runner_id=2,runner_name='runner',runner_group_id=0,labels=['ubuntu'],required_steps=['test'])
    expected=dict(repository='fixture/repo',head_sha='a'*40,workflow_path='.github/workflows/test.yml',run_id=4,run_attempt=1,scope='HOSTED_FIXTURE',jobs=[policy])
    run=dict(id=4,run_attempt=1,head_sha='a'*40,path=expected['workflow_path'],repository={'full_name':'fixture/repo'},status='completed',conclusion='success')
    job=dict(policy,run_id=4,run_attempt=1,head_sha='a'*40,status='completed',conclusion='success',steps=[{'name':'test','status':'completed','conclusion':'success'}])
    del job['required_steps']
    return expected,run,job

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.expected,self.run,self.job=fixtures();self.rows=[self.job];self.calls=[];self.after=None
    def reader(self,path):
        self.calls.append(path)
        if '/jobs?' in path:
            page=int(path.rsplit('=',1)[1]);return dict(total_count=len(self.rows),jobs=copy.deepcopy(self.rows[(page-1)*100:page*100]))
        return copy.deepcopy(self.after if self.after is not None and len(self.calls)>1 else self.run)
    def collect(self,reader=None):
        bind=load_dependencies()['ci_receipt_binding'].bind_ci_receipt
        return collect_ci_receipt(self.expected,reader or self.reader,bind,100)
    def test_real_binding_composed(self):
        result=self.collect()
        self.assertEqual(result['association']['state'],'CI_ASSOCIATION_VERIFIED')
        self.assertFalse(result['release_granted']);self.assertFalse(result['artifact_bytes_verified'])
        self.assertEqual(self.calls[1],'/repos/fixture/repo/actions/runs/4/attempts/1/jobs?per_page=100&page=1')
    def test_second_page_complete(self):
        self.rows=[dict(self.job,id=n) for n in range(1,129)]
        result=self.collect();self.assertEqual(result['job_count'],128);self.assertEqual(len(self.calls),4)
    def test_incomplete_first_page(self):
        def bad(path):
            if '/jobs?' in path:return dict(total_count=101,jobs=[self.job])
            return self.run
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):self.collect(bad)
    def test_total_changes_between_pages(self):
        self.rows=[dict(self.job,id=n) for n in range(1,102)]
        def bad(path):
            value=self.reader(path)
            if 'page=2' in path:value['total_count']=102
            return value
        with self.assertRaisesRegex(ValueError,'CHANGING'):self.collect(bad)
    def test_duplicate_across_pages(self):
        self.rows=[dict(self.job,id=n) for n in range(1,101)]+[self.job]
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.collect()
    def test_rerun_during_collection(self):
        self.after=dict(self.run,run_attempt=2)
        with self.assertRaisesRegex(ValueError,'RUN_CHANGED'):self.collect()
    def test_terminal_changes_during_collection(self):
        self.after=dict(self.run,status='in_progress')
        with self.assertRaisesRegex(ValueError,'RUN_CHANGED'):self.collect()
    def test_empty_jobs_hold(self):
        self.rows=[];self.assertEqual(self.collect()['association']['state'],'HOLD')
    def test_skipped_required_step_hold(self):
        self.job['steps'][0]['conclusion']='skipped'
        self.assertEqual(self.collect()['association']['state'],'HOLD')
    def test_cross_attempt_hold(self):
        self.job['run_attempt']=2
        self.assertEqual(self.collect()['association']['state'],'HOLD')
    def test_reader_failure_propagates_no_success(self):
        def fail(path):raise IOError('unavailable')
        with self.assertRaises(IOError):self.collect(fail)
    def test_limits_types(self):
        for count in (-1,129,True,1.0,None):
            def bad(path):return dict(total_count=count,jobs=[]) if '/jobs?' in path else self.run
            with self.assertRaises(ValueError):self.collect(bad)
    def test_no_input_mutation(self):
        before=copy.deepcopy((self.expected,self.run,self.rows));self.collect()
        self.assertEqual(before,(self.expected,self.run,self.rows))
    def test_untrusted_repository_and_run(self):
        for key,value in (('repository','owner/../../secrets'),('run_id',True),('run_attempt',0)):
            expected=copy.deepcopy(self.expected);expected[key]=value
            with self.assertRaises(ValueError):collect_ci_receipt(expected,self.reader,None,100)
            self.assertEqual(self.calls,[])

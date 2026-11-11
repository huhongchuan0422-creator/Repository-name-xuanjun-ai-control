import copy
import unittest
from scripts.ci_receipt_binding import bind_ci_receipt


class Tests(unittest.TestCase):
    def setUp(self):
        self.policy = {'id': 10, 'name': 'test', 'runner_id': 20, 'runner_name': 'GitHub Actions 20',
                       'runner_group_id': 0, 'labels': ['ubuntu-latest'], 'required_steps': ['Tests']}
        self.expected = {'repository': 'owner/repo', 'head_sha': 'a'*40,
                         'workflow_path': '.github/workflows/test.yml', 'run_id': 1,
                         'run_attempt': 2, 'scope': 'HOSTED_FIXTURE', 'jobs': [self.policy]}
        self.run = {'id': 1, 'run_attempt': 2, 'head_sha': 'a'*40,
                    'path': self.expected['workflow_path'], 'repository': {'full_name': 'owner/repo'},
                    'status': 'completed', 'conclusion': 'success'}
        self.jobs = [dict(self.policy, run_id=1, run_attempt=2, head_sha='a'*40,
                          status='completed', conclusion='success', steps=[
                              {'name': 'Tests', 'status': 'completed', 'conclusion': 'success'}])]
        self.jobs[0].pop('required_steps')

    def call(self, **kw):
        return bind_ci_receipt(self.expected, self.run, self.jobs, **dict({'observed_at': 100, 'now': 100}, **kw))

    def hold(self):
        self.assertEqual(self.call()['state'], 'HOLD')

    def test_valid_does_not_grant_test_or_release(self):
        result = self.call()
        self.assertEqual(result['state'], 'CI_ASSOCIATION_VERIFIED')
        for key in ('test_assertions_verified','artifact_verified','installed_acceptance','release_granted'):
            self.assertIs(result[key], False)
        self.assertIsNone(result['checked_out_commit'])

    def test_does_not_mutate_inputs(self):
        before=copy.deepcopy((self.expected,self.run,self.jobs));self.call()
        self.assertEqual(before,(self.expected,self.run,self.jobs))

    def test_cross_repository(self):
        self.run['repository']['full_name']='other/repo';self.hold()

    def test_wrong_head(self):
        self.run['head_sha']='b'*40;self.hold()

    def test_wrong_workflow(self):
        self.run['path']='.github/workflows/other.yml';self.hold()

    def test_run_attempt_mismatch(self):
        self.run['run_attempt']=1;self.hold()

    def test_job_old_attempt(self):
        self.jobs[0]['run_attempt']=1;self.hold()

    def test_job_cross_run(self):
        self.jobs[0]['run_id']=2;self.hold()

    def test_job_wrong_head(self):
        self.jobs[0]['head_sha']='b'*40;self.hold()

    def test_job_wrong_name(self):
        self.jobs[0]['name']='another';self.hold()

    def test_missing_job(self):
        self.jobs=[];self.hold()

    def test_duplicate_job(self):
        self.jobs.append(copy.deepcopy(self.jobs[0]));self.hold()

    def test_skipped_run(self):
        self.run['conclusion']='skipped';self.hold()

    def test_skipped_job(self):
        self.jobs[0]['conclusion']='skipped';self.hold()

    def test_running_job(self):
        self.jobs[0]['status']='in_progress';self.hold()

    def test_required_step_skipped(self):
        self.jobs[0]['steps'][0]['conclusion']='skipped';self.hold()

    def test_required_step_missing(self):
        self.jobs[0]['steps']=[];self.hold()

    def test_duplicate_step_name(self):
        self.jobs[0]['steps']*=2;self.hold()

    def test_wrong_runner(self):
        self.jobs[0]['runner_id']=30;self.hold()

    def test_wrong_group(self):
        self.jobs[0]['runner_group_id']=7;self.hold()

    def test_wrong_labels(self):
        self.jobs[0]['labels']=['self-hosted'];self.hold()

    def test_uk_requires_trusted_selfhosted_policy(self):
        self.expected['scope']='UK_ISOLATED_FIXTURE'
        with self.assertRaises(ValueError):self.call()

    def test_verified_uk_fixture_still_not_installed(self):
        self.expected['scope']='UK_ISOLATED_FIXTURE'
        for p in (self.policy,self.jobs[0]):
            p.update(runner_name='UK_FIXED',runner_id=33,runner_group_id=4,labels=['self-hosted','linux','x64'])
        result=self.call();self.assertEqual(result['state'],'CI_ASSOCIATION_VERIFIED')
        self.assertFalse(result['installed_acceptance'])

    def test_stale_and_future(self):
        for now in (99,401):self.assertEqual(self.call(now=now)['state'],'HOLD')
        self.assertEqual(self.call(now=400)['state'],'CI_ASSOCIATION_VERIFIED')

    def test_nonfinite_and_bool_times(self):
        for value in (True,float('nan'),float('inf'),-1):
            with self.assertRaises(ValueError):self.call(now=value)

    def test_bool_ids_do_not_match_int(self):
        self.run['id']=True;self.hold()

    def test_invalid_policy_arrays(self):
        for value in ([],['Tests','Tests'],[{}],['x\n']):
            self.policy['required_steps']=value
            with self.assertRaises(ValueError):self.call()

    def test_malformed_job_visible_hold(self):
        self.jobs.append({});self.hold()

    def test_bounds(self):
        self.jobs=[{}]*129
        with self.assertRaises(ValueError):self.call()

    def test_output_does_not_echo_untrusted_details(self):
        self.jobs[0]['error']='SECRET';self.run['payload']='SECRET'
        self.assertNotIn('SECRET',str(self.call()))


if __name__=='__main__':unittest.main()

import base64
import json
import unittest
from unittest.mock import patch
from tests.test_pr122_customer_small_edit import SmallEditTests
from tests.test_pr122_customer_http import HttpTests
from scripts.pr122_customer_edit_jobs import enqueue, drain, get
from scripts.pr122_customer_core import Denied, digest
from scripts.pr122_customer_http import COOKIE


class EditJobTests(unittest.TestCase):
    imported = SmallEditTests.imported
    install = SmallEditTests.install
    request = SmallEditTests.request
    setUp = SmallEditTests.setUp

    def queued(self):
        case = self.request()
        with patch('scripts.pr122_customer_publication_worker.notify', return_value=False):
            return case, enqueue(self.c, self.reviewer, 'project-a', case)

    def test_durable_queue_drains_to_real_encrypted_candidate_without_network(self):
        case, job = self.queued()
        with patch('socket.socket', side_effect=AssertionError('zero API')):
            result = drain(self.c)
        self.assertEqual(result['done'], 1)
        candidate = get(self.c, self.reviewer, 'project-a', job['id'])
        self.assertEqual(candidate['state'], 'CANDIDATE_READY')
        artifact = candidate['result']['artifact']
        self.assertEqual(base64.b64decode(artifact['page_base64']), self.body.replace(b'Welcome', b'Welcomes'))
        row = self.c.db.execute('SELECT result FROM preview_edit_jobs').fetchone()[0]
        self.assertNotIn(b'Welcomes', row)
        self.assertNotIn(b'page_base64', row)
        self.assertFalse(candidate['production_published'])
        self.assertEqual(drain(self.c)['done'], 0)
        with patch('scripts.pr122_customer_publication_worker.notify', side_effect=AssertionError('no duplicate notification')):
            again = enqueue(self.c, self.reviewer, 'project-a', case)
        self.assertEqual(again['id'], job['id'])
        self.assertEqual(again['state'], 'CANDIDATE_READY')

    def test_candidate_contains_exact_unchanged_reviewed_resource_closure(self):
        import hmac, hashlib
        from scripts.pr122_customer_core import canonical
        from scripts.pr122_customer_change_authority import load, import_snapshot
        current=load(self.c)
        row=self.c.db.execute('SELECT payload FROM change_authority_history WHERE revision=?',(current['revision'],)).fetchone()
        source=json.loads(self.c.decrypt(row[0],'change-authority-source:'+str(current['revision'])))['payload']
        source['revision']+=1
        entry=source['previews'][0]
        resource=b'p{color:navy}'
        entry['manifest']['pages'].append({'path':'/preview/theme.css','sha256':digest(resource)})
        entry['blobs'][digest(resource)]=base64.b64encode(resource).decode()
        entry['manifest_sha256']=digest(canonical(entry['manifest']))
        import_snapshot(self.c,{'payload':source,'signature':hmac.new(self.auth,canonical(source),hashlib.sha256).hexdigest()},self.auth)
        _, job=self.queued();drain(self.c)
        artifact=get(self.c,self.reviewer,'project-a',job['id'])['result']['artifact']
        self.assertEqual(len(artifact['files']),2)
        asset=next(x for x in artifact['files'] if x['path']=='/preview/theme.css')
        self.assertEqual(base64.b64decode(asset['base64']),resource)
        self.assertEqual(asset['sha256'],digest(resource))
        self.assertEqual(artifact['modified_files'],[self.path])

    def test_customer_cannot_queue_or_download_candidate(self):
        case, job = self.queued()
        with self.assertRaises(Denied):
            enqueue(self.c, self.owner, 'project-a', case)
        with self.assertRaises(Denied):
            get(self.c, self.owner, 'project-a', job['id'])
        with self.assertRaises(Denied):
            get(self.c, self.reviewer, 'project-missing', job['id'])

    def test_changed_assessment_after_enqueue_is_held_not_retried(self):
        case, job = self.queued()
        from scripts.pr122_customer_changes import Changes
        Changes(self.c).assess(self.reviewer, 'project-a', case, 2, 'UNKNOWN', 1, [], [], '范围变化')
        self.assertEqual(drain(self.c)['held'], 1)
        self.assertEqual(get(self.c, self.reviewer, 'project-a', job['id'])['state'], 'HOLD_UNKNOWN')
        self.assertEqual(drain(self.c)['done'], 0)

    def test_processing_unknown_is_never_automatically_reclaimed(self):
        _, job = self.queued()
        self.c.db.execute("UPDATE preview_edit_jobs SET state='PROCESSING' WHERE id=?", (job['id'],))
        self.assertEqual(drain(self.c)['unknown'], 1)
        self.assertEqual(drain(self.c)['done'], 0)

    def test_stale_published_source_invalidates_candidate_export(self):
        _, job = self.queued()
        drain(self.c)
        self.revision = 2
        self.install(self.body.replace(b'Welcome', b'New title'))
        with self.assertRaises(Denied):
            get(self.c, self.reviewer, 'project-a', job['id'])

    def test_revoked_reporter_cannot_run_old_job(self):
        self.queued()
        self.imported(2, [])
        self.assertEqual(drain(self.c)['held'], 1)


class EditJobHTTPTests(HttpTests):
    imported = SmallEditTests.imported
    install = SmallEditTests.install
    finish = HttpTests.finish
    request = HttpTests.request

    def setUp(self):
        HttpTests.setUp(self)
        self.path = '/preview/consumer/'
        self.body = b'<html><body><p data-xj-small-text="TYPO_ONLY_V1">Welcome</p></body></html>'
        self.revision = 1
        self.install()

    def test_actual_http_queue_worker_artifact_chain_and_rejection(self):
        case = SmallEditTests.request(self)
        headers = {'Cookie': COOKIE + '=' + self.users['reviewer']['token'], 'X-CSRF-Token': self.users['reviewer']['csrf']}
        payload = {'project': 'project-a', 'case': case}
        status, _, raw = self.request('api/change_small_edit', payload, headers)
        self.assertEqual(status, 200)
        job = json.loads(raw)['id']
        self.assertEqual(drain(self.c)['done'], 1)
        status, response_headers, raw = self.request('api/edit_candidate/project-a/' + job, headers=headers)
        self.assertEqual(status, 200)
        self.assertIn('application/json', response_headers['Content-Type'])
        self.assertIn('no-store', response_headers['Cache-Control'])
        artifact = json.loads(raw)['result']['artifact']
        self.assertEqual(digest(base64.b64decode(artifact['page_base64'])), artifact['receipt']['after_sha256'])
        self.assertEqual(self.request('api/edit_candidate/project-a/' + job)[0], 403)
        self.assertEqual(self.request('api/edit_candidate/project-a/' + job, headers={**headers, 'Range': 'bytes=0-2'})[0], 403)
        owner = {'Cookie': COOKIE + '=' + self.users['owner']['token'], 'X-CSRF-Token': self.users['owner']['csrf']}
        self.assertEqual(self.request('api/change_small_edit', payload, owner)[0], 403)
        self.assertEqual(self.request('api/change_small_edit', {**payload, 'page_bytes': 'arbitrary'}, headers)[0], 400)


for _name in HttpTests.__dict__:
    if _name.startswith('test_'):setattr(EditJobHTTPTests,_name,None)

if __name__ == '__main__':
    unittest.main()

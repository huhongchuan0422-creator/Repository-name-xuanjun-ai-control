import contextlib
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('domestic_helper', Path(__file__).parents[1] / 'domestic_helper.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def fixture():
    pin = dict(schema=1, comment_id=123, body_sha256='a'*64,
               source_writer_principal='source-person', reviewer_principal='task5-person',
               owner_principal='owner-person', custody_evidence_sha256='b'*64,
               nonce='c'*64, issued_at='2026-10-17T10:00:00Z', expires_at='2026-10-17T10:30:00Z',
               helper_sha256='d'*64, wrapper_sha256='e'*64, policy_sha256='f'*64,
               review_source='original-task5-pr122', github_author_id=332398908, github_app_id=1144995)
    permit = {k: v for k,v in pin.items() if k not in ('comment_id', 'body_sha256')}
    permit.update(scope=h.SCOPE, host=h.HOST, runner_uid=1002, max_executions=1,
                  channel_sha256=h.CHANNEL_SHA, payload_sha256=h.PAYLOAD_SHA,
                  probe_sha256=h.PROBE_SHA, creation_authorized=False)
    body = h.PREFIX + json.dumps(permit, sort_keys=True)
    pin['body_sha256'] = h.digest(body.encode())
    comment = dict(id=123, body=body, url=f'https://api.github.com/repos/{h.REPO}/issues/comments/123',
                   issue_url=f'https://api.github.com/repos/{h.REPO}/issues/122',
                   html_url=f'https://github.com/{h.REPO}/pull/122#issuecomment-123',
                   user={'id':332398908}, performed_via_github_app={'id':1144995})
    return pin, comment


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.pin, self.comment = fixture()
        self.now = h.timestamp('2026-10-17T10:05:00Z')

    def test_valid_exact_permit(self):
        h.validate_pin(self.pin, self.now)
        self.assertEqual(h.validate_comment(self.pin, self.comment)['scope'], h.SCOPE)

    def test_pin_negative_matrix(self):
        cases = [('schema',True),('comment_id',True),('body_sha256','bad'),
                 ('custody_evidence_sha256',''),('nonce','short'),('review_source','Other'),
                 ('github_author_id',True),('github_app_id',0),
                 ('reviewer_principal','source-person'),('owner_principal','source-person'),
                 ('issued_at','2026-10-17T10:06:00Z'),('expires_at','2026-10-17T10:05:00Z'),
                 ('expires_at','2026-10-17T10:30:01Z')]
        for key,value in cases:
            with self.subTest(key=key,value=value):
                pin=copy.deepcopy(self.pin);pin[key]=value
                with self.assertRaises(ValueError):h.validate_pin(pin,self.now)

    def test_unknown_pin_fields(self):
        self.pin['arbitrary_command']='id'
        with self.assertRaises(ValueError):h.validate_pin(self.pin,self.now)

    def test_exact_comment_origin(self):
        cases = [('id',124),('url','https://evil.invalid'),('issue_url','wrong'),
                 ('html_url','wrong'),('user',{'id':1}),('performed_via_github_app',{'id':2}),
                 ('body',self.comment['body']+' ')]
        for key,value in cases:
            with self.subTest(key=key):
                comment=copy.deepcopy(self.comment);comment[key]=value
                with self.assertRaises(ValueError):h.validate_comment(self.pin,comment)

    def test_permit_scope_matrix_even_when_body_is_pinned(self):
        cases=[('scope','apply'),('host','other'),('runner_uid',True),('max_executions',2),
               ('creation_authorized',True),('channel_sha256','a'*64),('payload_sha256','a'*64),
               ('probe_sha256','a'*64),('nonce','a'*64),('helper_sha256','a'*64)]
        for key,value in cases:
            with self.subTest(key=key):
                pin,comment=fixture();permit=json.loads(comment['body'][len(h.PREFIX):]);permit[key]=value
                comment['body']=h.PREFIX+json.dumps(permit);pin['body_sha256']=h.digest(comment['body'].encode())
                with self.assertRaises(ValueError):h.validate_comment(pin,comment)

    def test_duplicate_json(self):
        with self.assertRaises(ValueError):h.strict_json('{"a":1,"a":2}')

    def test_nonfinite_json(self):
        with self.assertRaises(ValueError):h.strict_json('{"a":NaN}')

    def test_no_redirect(self):
        with self.assertRaises(ValueError):h.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_no_args_before_probe(self):
        with mock.patch.object(h.sys,'argv',['helper','plan']):
            with self.assertRaisesRegex(ValueError,'NO_ARGUMENTS'):h.run()

    def test_wrong_executor_before_probe(self):
        with mock.patch.object(h.sys,'argv',['helper']), mock.patch.object(h.os,'getuid',return_value=1002):
            with self.assertRaisesRegex(ValueError,'EXECUTOR'):h.run()

    def test_missing_pin_never_consumes(self):
        with mock.patch.object(h,'secure_read',side_effect=FileNotFoundError),mock.patch.object(h.os,'mkdir') as mkdir:
            with self.assertRaises(FileNotFoundError):h.Admission().admit()
            mkdir.assert_not_called()

    def admission_context(self, stack, existing=False):
        raw=json.dumps(self.pin).encode()
        def read(path,*args):
            if path==h.TRUST:return raw,(1,2)
            if path==h.CHANNEL:return b'channel',(3,4)
            raise AssertionError(path)
        stack.enter_context(mock.patch.object(h,'secure_read',side_effect=read))
        stack.enter_context(mock.patch.object(h,'now',return_value=self.now))
        stack.enter_context(mock.patch.object(h,'check_files'))
        stack.enter_context(mock.patch.object(h,'fetch_comment',return_value=self.comment))
        stack.enter_context(mock.patch.object(h,'secure_parents'))
        mkdir=stack.enter_context(mock.patch.object(h.os,'mkdir',side_effect=FileExistsError if existing else None))
        stack.enter_context(mock.patch.object(h,'sync_dir'))
        write=stack.enter_context(mock.patch.object(h,'write_receipt'))
        return mkdir,write

    def test_consume_before_observe_receipt(self):
        with contextlib.ExitStack() as stack:
            mkdir,write=self.admission_context(stack)
            gate=h.Admission();gate.admit()
            self.assertTrue(gate.consumed)
            mkdir.assert_called_once_with(h.RECEIPT,0o700)
            self.assertEqual(write.call_args.args[0],'started.json')

    def test_existing_or_partial_receipt_blocks(self):
        with contextlib.ExitStack() as stack:
            _,write=self.admission_context(stack,existing=True)
            gate=h.Admission()
            with self.assertRaises(FileExistsError):gate.admit()
            self.assertFalse(gate.consumed);write.assert_not_called()

    def test_real_exclusive_directory_prevents_second_nonce(self):
        real_mkdir=h.os.mkdir
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            self.admission_context(stack)
            stack.enter_context(mock.patch.object(h,'RECEIPT',directory+'/once'))
            stack.enter_context(mock.patch.object(h.os,'mkdir',side_effect=real_mkdir))
            first=h.Admission();first.admit()
            self.assertTrue(first.consumed)
            # A replacement approval or nonce cannot reset the fixed operation.
            second=h.Admission()
            with self.assertRaises(FileExistsError):second.admit()
            self.assertFalse(second.consumed)

    def test_durability_failure_consumes_no_replay(self):
        with contextlib.ExitStack() as stack:
            self.admission_context(stack)
            stack.enter_context(mock.patch.object(h,'sync_dir',side_effect=OSError('fsync')))
            gate=h.Admission()
            with self.assertRaises(OSError):gate.admit()
            self.assertTrue(gate.consumed)

    def test_approval_denial_before_consumption(self):
        with contextlib.ExitStack() as stack:
            mkdir,write=self.admission_context(stack)
            stack.enter_context(mock.patch.object(h,'validate_comment',side_effect=ValueError('DENY')))
            with self.assertRaises(ValueError):h.Admission().admit()
            mkdir.assert_not_called();write.assert_not_called()

    def test_trust_drift(self):
        gate=h.Admission();gate.pin=self.pin;gate.trust_raw=b'old';gate.lock_inode=(1,2)
        with mock.patch.object(h,'now',return_value=self.now),mock.patch.object(h,'secure_read',return_value=(b'changed',(1,2))):
            with self.assertRaisesRegex(ValueError,'TRUST_DRIFT'):gate.revalidate()

    def test_expiry_after_probe(self):
        gate=h.Admission();gate.pin=self.pin
        with mock.patch.object(h,'now',return_value=h.timestamp(self.pin['expires_at'])):
            with self.assertRaisesRegex(ValueError,'EXPIRED'):gate.revalidate()

    def test_receipt_names_closed(self):
        with self.assertRaisesRegex(ValueError,'RECEIPT_NAME'):h.write_receipt('../escape',{})

    def test_secure_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file';p.write_text('x');p.chmod(0o600)
            link=Path(d)/'link';link.symlink_to(p)
            with mock.patch.object(h,'secure_parents'):
                with self.assertRaises(OSError):h.secure_read(str(link),0o600)

    def test_secure_read_rejects_hardlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file';p.write_text('x');p.chmod(0o600)
            h.os.link(p,Path(d)/'link')
            with mock.patch.object(h,'secure_parents'):
                with self.assertRaisesRegex(ValueError,'UNSAFE_FILE'):h.secure_read(str(p),0o600)

    def test_comment_edited_immediately_before_consume(self):
        with contextlib.ExitStack() as stack:
            mkdir,write=self.admission_context(stack)
            changed=copy.deepcopy(self.comment);changed['body']+='edited'
            stack.enter_context(mock.patch.object(h,'fetch_comment',side_effect=[self.comment,changed]))
            with self.assertRaisesRegex(ValueError,'BODY_PIN'):h.Admission().admit()
            mkdir.assert_not_called();write.assert_not_called()

    def test_comment_deleted_before_consume(self):
        with contextlib.ExitStack() as stack:
            mkdir,write=self.admission_context(stack)
            stack.enter_context(mock.patch.object(h,'fetch_comment',side_effect=[self.comment,OSError('404')]))
            with self.assertRaises(OSError):h.Admission().admit()
            mkdir.assert_not_called();write.assert_not_called()

    def test_final_comment_validation_fails_closed_after_consumption(self):
        with contextlib.ExitStack() as stack:
            self.admission_context(stack)
            gate=h.Admission();gate.admit()
            stack.enter_context(mock.patch.object(h,'fetch_comment',side_effect=OSError('404')))
            with self.assertRaises(OSError):gate.verify_current_comment()
            self.assertTrue(gate.consumed)

    def test_grant_json_and_all_deployed_hashes(self):
        values={h.CHANNEL:b'channel',h.HELPER:b'helper',h.WRAPPER:b'wrapper',h.POLICY:b'policy',
                h.BASE+'/grant-state.json':b'{"state":"GRANTED"}'}
        control=h.BASE+'/readonly-bootstrap-20261017'
        values[control+'/VERIFIED.json']=b'{"state":"VERIFIED"}'
        plan={'scope':'DOMESTIC_READONLY_BOOTSTRAP_20261017','baseline':{'device':1,'inode':2,'code_sha256':h.digest(b'channel'),'grant_sha256':h.digest(values[h.BASE+'/grant-state.json'])}}
        plan['baseline']['interpreter']={'fixed':'/usr/bin/python3','resolved':'/usr/bin/python3.8','chain':[],'device':1,'inode':123,'mode':493,'size':1000,'sha256':'f'*64,'version':[3,8,0]}
        values[control+'/plan.json']=json.dumps(plan).encode()
        pin=dict(self.pin)
        for path,field in ((h.HELPER,'helper_sha256'),(h.WRAPPER,'wrapper_sha256'),(h.POLICY,'policy_sha256')):
            pin[field]=h.digest(values[path])
        with mock.patch.object(h,'CHANNEL_SHA',h.digest(b'channel')), mock.patch.object(h,'secure_read',side_effect=lambda p,*a:(values[p],(1,2))):
            h.check_files(pin)
            values[h.BASE+'/grant-state.json']=b'{"state":"UPGRADING"}'
            with self.assertRaisesRegex(ValueError,'CHANNEL_NOT_GRANTED'):h.check_files(pin)
            values[h.BASE+'/grant-state.json']=b'{"state":"GRANTED"}'
            plan['baseline']['inode']=3
            values[control+'/plan.json']=json.dumps(plan).encode()
            with self.assertRaisesRegex(ValueError,'ORIGINAL_INODE_OR_GRANT_DRIFT'):h.check_files(pin)
            plan['baseline']['inode']=2
            values[control+'/plan.json']=json.dumps(plan).encode()
            values[h.WRAPPER]=b'changed'
            with self.assertRaisesRegex(ValueError,'DEPLOYED_HASH'):h.check_files(pin)

    def test_rollback_started_blocks_direct_helper(self):
        with mock.patch.object(h.os.path,'lexists',return_value=True),mock.patch.object(h,'secure_read') as read:
            with self.assertRaisesRegex(ValueError,'ROLLBACK_STARTED'):h.check_files(self.pin)
            read.assert_not_called()

    def test_missing_verified_blocks_direct_helper(self):
        with mock.patch.object(h.os.path,'lexists',return_value=False),mock.patch.object(h,'secure_read',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):h.check_files(self.pin)

    def test_single_lock_and_admission_precede_observations(self):
        events=[]
        class FakeOS:
            @contextlib.contextmanager
            def lock_existing(self,path):
                events.append('lock')
                try:yield
                finally:events.append('unlock')
        ns={'OS':FakeOS}
        def fake_probe_run(namespace):
            with namespace['OS']().lock_existing(h.CHANNEL):
                events.append('observation')
            return {'mutations':0}
        def fake_exec(code,namespace):
            namespace.update(load_approved=lambda raw:ns,run=fake_probe_run)
        class Gate:
            consumed=False
            pin=self.pin
            lock_inode=(3,4)
            def admit(self):events.append('admit');self.consumed=True
            def revalidate(self):events.append('revalidate')
            def verify_current_comment(self):events.append('verify_current_comment')
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(h.sys,'argv',['helper']))
            stack.enter_context(mock.patch.object(h.os,'uname',return_value=type('U',(),{'nodename':h.HOST})()))
            stack.enter_context(mock.patch.object(h.os,'getuid',return_value=0))
            stack.enter_context(mock.patch.object(h.os,'geteuid',return_value=0))
            stack.enter_context(mock.patch.dict(h.os.environ,{'SUDO_UID':'1002'}))
            stack.enter_context(mock.patch.object(h.base64,'b64decode',side_effect=[b'payload',b'probe']))
            stack.enter_context(mock.patch.object(h,'digest',side_effect=[h.PAYLOAD_SHA,h.PROBE_SHA]))
            stack.enter_context(mock.patch.object(h,'exec',side_effect=fake_exec,create=True))
            stack.enter_context(mock.patch.object(h,'compile',return_value=None,create=True))
            stack.enter_context(mock.patch.object(h,'Admission',Gate))
            stack.enter_context(mock.patch.object(h,'secure_read',return_value=(b'channel',(3,4))))
            write=stack.enter_context(mock.patch.object(h,'write_receipt'))
            result=h.run()
        self.assertEqual(events,['lock','admit','observation','revalidate','unlock','verify_current_comment'])
        self.assertEqual(result['admission']['github_job_identity'],'NOT_ATTESTED')
        write.assert_called_once()

    def test_after_probe_comment_drift_records_unknown(self):
        events=[]
        class FakeOS:
            @contextlib.contextmanager
            def lock_existing(self,path):
                events.append('lock')
                try:yield
                finally:events.append('unlock')
        ns={'OS':FakeOS}
        def fake_probe_run(namespace):
            with namespace['OS']().lock_existing(h.CHANNEL):
                events.append('observation')
            return {'mutations':0}
        def fake_exec(code,namespace):
            namespace.update(load_approved=lambda raw:ns,run=fake_probe_run)
        class Gate:
            consumed=False
            pin=self.pin
            lock_inode=(3,4)
            def admit(self):events.append('admit');self.consumed=True
            def revalidate(self):events.append('revalidate')
            def verify_current_comment(self):raise ValueError('BODY_PIN')
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(h.sys,'argv',['helper']))
            stack.enter_context(mock.patch.object(h.os,'uname',return_value=type('U',(),{'nodename':h.HOST})()))
            stack.enter_context(mock.patch.object(h.os,'getuid',return_value=0))
            stack.enter_context(mock.patch.object(h.os,'geteuid',return_value=0))
            stack.enter_context(mock.patch.dict(h.os.environ,{'SUDO_UID':'1002'}))
            stack.enter_context(mock.patch.object(h.base64,'b64decode',side_effect=[b'payload',b'probe']))
            stack.enter_context(mock.patch.object(h,'digest',side_effect=[h.PAYLOAD_SHA,h.PROBE_SHA]))
            stack.enter_context(mock.patch.object(h,'exec',side_effect=fake_exec,create=True))
            stack.enter_context(mock.patch.object(h,'compile',return_value=None,create=True))
            stack.enter_context(mock.patch.object(h,'Admission',Gate))
            stack.enter_context(mock.patch.object(h,'secure_read',return_value=(b'channel',(3,4))))
            write=stack.enter_context(mock.patch.object(h,'write_receipt'))
            with self.assertRaisesRegex(ValueError,'BODY_PIN'):h.run()
        write.assert_called_once_with('result.json',{'state':'UNKNOWN_CONSUMED_NO_RETRY','retry_allowed':False})

    def test_lock_inode_drift_blocks(self):
        gate=h.Admission();gate.pin=self.pin;gate.trust_raw=b'pin';gate.lock_inode=(3,4)
        with mock.patch.object(h,'now',return_value=self.now),mock.patch.object(h,'check_files'),mock.patch.object(h,'secure_read',side_effect=[(b'pin',(1,2)),(b'channel',(3,5))]):
            with self.assertRaisesRegex(ValueError,'LOCK_INODE_DRIFT'):gate.revalidate()

    def test_template_inert(self):
        self.assertEqual(h.PAYLOAD_B64,'__PAYLOAD_B64__')
        self.assertEqual(h.PROBE_B64,'__PROBE_B64__')


if __name__=='__main__':unittest.main()

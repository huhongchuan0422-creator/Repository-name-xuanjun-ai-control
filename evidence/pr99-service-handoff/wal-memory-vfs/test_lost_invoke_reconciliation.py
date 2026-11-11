import base64
import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

import lost_invoke_reconciliation as m


def intent():
    return {'operation_id': 'a'*64, 'source_sha256': 'b'*64,
        'command_sha256': hashlib.sha256(b'fixed reviewed command').hexdigest(),
        'region': m.REGION, 'instance': m.INSTANCE, 'host': m.HOST,
        'action': 'PR99_FINAL_DOMESTIC_START_V1'}


def entry(invoke='t-fixture'):
    return {'InvokeId': invoke, 'CommandName': 'pr99-final-start-'+'a'*24,
        'CommandType': 'RunShellScript', 'Username': 'root', 'WorkingDir': '/root', 'Timeout': 240,
        'CommandContent': 'fixed reviewed command', 'Parameters': '{}',
        'InvokeInstances': [{'InstanceId': m.INSTANCE, 'Output': 'PRIVATE', 'ErrorInfo': 'PRIVATE'}]}


def rpc(rows):
    def call(endpoint, version, action, credentials, **params):
        assert action == 'DescribeCommandInvocations' and params['InstanceId'] == m.INSTANCE
        assert 'CommandName' not in params
        start = (params['PageNumber']-1)*50
        return {'TotalCount': len(rows), 'CommandInvocations': rows[start:start+50]}
    return call


class LostInvokeTests(unittest.TestCase):
    def test_exact_match_and_redaction(self):
        r = m.locate_once(intent(), rpc([entry()]), ('fake',)*3)
        self.assertEqual(r['invoke_id'], 't-fixture')
        self.assertNotIn('PRIVATE', repr(r)); self.assertNotIn('fixed reviewed command', repr(r))

    def test_zero_match_stays_unknown(self):
        r = m.locate_once(intent(), rpc([]), ())
        self.assertEqual(r['status'], 'UNKNOWN_NO_MATCH_NO_REPLAY')

    def test_duplicate_exact_command_holds(self):
        with self.assertRaisesRegex(m.ReconciliationHold, 'AMBIGUOUS'):
            m.locate_once(intent(), rpc([entry('t-one'), entry('t-two')]), ())

    def test_scope_and_content_conflicts_hold(self):
        for field, value in (('Username', 'other'), ('CommandContent', 'foreign'),
                             ('WorkingDir', '/tmp'), ('Timeout', 10), ('Parameters', '{"x":1}')):
            row = entry(); row[field] = value
            with self.assertRaises(m.ReconciliationHold): m.locate_once(intent(), rpc([row]), ())

    def test_base64_command_and_full_pagination(self):
        rows = []
        for i in range(60):
            row = entry('t-other-'+str(i)); row['CommandName'] = 'unrelated'; rows.append(row)
        found = entry(); found['CommandContent'] = base64.b64encode(b'fixed reviewed command').decode()
        rows.append(found)
        self.assertEqual(m.locate_once(intent(), rpc(rows), ())['invoke_id'], 't-fixture')

    def test_wrong_instance_holds(self):
        row = entry(); row['InvokeInstances'][0]['InstanceId'] = 'foreign'
        with self.assertRaises(m.ReconciliationHold): m.locate_once(intent(), rpc([row]), ())

    def test_boolean_count_holds(self):
        with self.assertRaises(m.ReconciliationHold):
            m.locate_once(intent(), lambda *a, **k: {'TotalCount': True, 'CommandInvocations': []}, ())

    def test_changing_total_holds(self):
        def changing(*a, **k):
            return {'TotalCount': 60 if k['PageNumber'] == 1 else 61,
                    'CommandInvocations': [dict(entry('t-'+str(i)), CommandName='unrelated') for i in range(50)]}
        with self.assertRaisesRegex(m.ReconciliationHold, 'CHANGED'):
            m.locate_once(intent(), changing, ())

    def test_persist_original_record_and_restart_without_rpc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); q = p/'cloud-start.intent.json'; q.write_bytes(m.encode(intent())); q.chmod(0o600)
            fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
            try:
                first = m.bind_missing_invoke(fd, lambda: None, rpc([entry()]), ())
                self.assertEqual(first['invoke_id'], 't-fixture')
                def no_call(*a, **k): raise AssertionError('RPC replayed')
                second = m.bind_missing_invoke(fd, lambda: None, no_call, ())
                self.assertEqual(second['status'], 'EXISTING_INVOKE_QUERY_RESULT_ONLY')
                self.assertEqual(set(x.name for x in p.iterdir()), {'cloud-start.intent.json','cloud-start.invocation.json'})
            finally: os.close(fd)

    def test_partial_record_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); q=p/'cloud-start.intent.json';q.write_bytes(m.encode(intent()));q.chmod(0o600)
            q=p/'cloud-start.invocation.json';q.write_bytes(b'{');q.chmod(0o600)
            fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaises(m.ReconciliationHold): m.bind_missing_invoke(fd,lambda:None,rpc([entry()]),())
                self.assertEqual(q.read_bytes(),b'{')
            finally:os.close(fd)


if __name__ == '__main__': unittest.main()

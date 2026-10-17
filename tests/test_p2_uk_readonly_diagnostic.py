"""PR128 R1-R7 offline and Python 3.6 diagnostic regression tests."""
import hashlib
import uuid  # Import before inherited os.uname fixture replacement.
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
def load(name, file):
    spec=importlib.util.spec_from_file_location(name,str(ROOT/file))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

class ReadOnlyDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=load('fixed_diag_test','scripts/p2_uk_readonly_diagnostic.py')
        cls.t=load('fixed_transport_test','scripts/p2_uk_swas_diagnostic.py')

    def valid(self,controllers='1:cpu,cpuacct'):
        d=self.d
        lines=['DIAG_SCHEMA=1','TARGET_HOST='+d.TARGET_HOST,'EXEC_UID=0',
               'PYTHON_VERSION=3.6.8','CGROUP_MOUNT_TYPE=tmpfs',
               'CGROUP_PROC_SELF='+controllers.split('|')[0]]
        lines.extend(controllers.split('|')[1:])
        lines.extend(['SITE_PATH='+d.SITE_PATH,'SITE_STATUS=ABSENT'])
        for unit in sorted(d.UNIT_NAMES):
            lines.extend(['UNIT='+unit,'LoadState=loaded','ActiveState=inactive',
                          'SubState=dead','MainPID=0','UnitFileState=masked'])
        for path in sorted(d.DB_NAMES):
            lines.append('DB_FILE_ABSENT='+path)
        for key in ('CANONICAL_WRITER','EPOCH','LEASE','FENCE','ROOT_TRUST','HISTORICAL_INVOKEID'):
            lines.append(key+'=UNKNOWN')
        lines.append('DIAG_END=COMPLETE')
        return '\n'.join(lines)+'\n'

    def test_exact_command(self):
        raw=self.d.command_content().encode()
        self.assertEqual(len(raw),1771)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),self.d.COMMAND_SHA256)
        self.assertEqual(self.t.diagnostic_module().command_content(),raw.decode())

    def test_v1_v2_real_shapes(self):
        for c in ('1:cpu,cpuacct|2:name=systemd|3:memory','0:','1:cpu,cpuacct|2:memory'):
            with self.subTest(c=c):
                result=self.d.safe_receipt(self.valid(c))
                self.assertEqual(result['state'],'DIAGNOSTIC_METADATA_ONLY')
                self.assertFalse(result['writer_verified'])

    def test_complete_required_and_canary_rejection(self):
        ok=self.valid()
        lines=ok.splitlines()
        for index in range(len(lines)):
            bad='\n'.join(lines[:index]+lines[index+1:])+'\n'
            with self.subTest(missing=index),self.assertRaises(self.d.DiagnosticHold):
                self.d.safe_receipt(bad)
        for i in range(len(lines)):
            bad='\n'.join(lines[:i]+[lines[i]]+lines[i:])+'\n'
            with self.subTest(duplicate=i),self.assertRaises(self.d.DiagnosticHold):
                self.d.safe_receipt(bad)
        for key in ('SITE_STATUS','LoadState','ActiveState','SubState','UnitFileState','CGROUP_MOUNT_TYPE'):
            source='SITE_STATUS=ABSENT' if key=='SITE_STATUS' else next(row for row in lines if row.startswith(key+'='))
            bad=ok.replace(source,key+'=SYNTHETIC_SECRET_CANARY')
            with self.subTest(canary=key),self.assertRaises(self.d.DiagnosticHold):
                self.d.safe_receipt(bad)
        for bad in (ok+'SECRET=anything\n',ok.replace('EPOCH=UNKNOWN','EPOCH=123'),
                    ok.replace('1:cpu,cpuacct','1:cpu,cpuacct|3:secret'),
                    ok.replace('EXEC_UID=0','EXEC_UID=1'),
                    ok.replace('DIAG_END=COMPLETE','DIAG_END=FAIL'),
                    ok+'x'*6000):
            with self.assertRaises(self.d.DiagnosticHold):self.d.safe_receipt(bad)

    def test_file_metadata_and_exit(self):
        ok=self.valid()
        present=ok.replace('SITE_STATUS=ABSENT',
            'SITE_UID=0 SITE_GID=0 SITE_MODE=444 SITE_SIZE=200\nSITE_SHA256='+('a'*64))
        self.assertEqual(self.d.safe_receipt(present)['state'],'DIAGNOSTIC_METADATA_ONLY')
        for stderr,code in [('SECRET',0),('',40),('',41),('',2)]:
            with self.assertRaises(self.d.DiagnosticHold):
                self.d.safe_receipt(ok,stderr,code)

    def test_workflow_failure_json_no_stderr_leak(self):
        import json
        import subprocess
        workflow=(ROOT/'.github/workflows/p2-uk-swas-diagnostic.yml').read_text()
        entries=[line.strip() for line in workflow.splitlines()
                 if line.strip().startswith("printf '%s") and 'redispatch_allowed' in line]
        self.assertEqual(len(entries),1)
        safe=entries[0].split(' > /tmp/',1)[0]
        run=subprocess.Popen(['/bin/bash','-c',safe],stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        stdout,stderr=run.communicate(timeout=4)
        self.assertEqual(run.returncode,0)
        self.assertEqual(stderr,b'')
        self.assertEqual(json.loads(stdout),{'state':'HOLD','redispatch_allowed':False})
        self.assertEqual(stdout.count(b'\n'),1)

    def test_approval_contract(self):
        self.assertEqual(self.t.OWNER_ID,332398908)
        self.assertEqual(self.t.AUDITOR_ID,95597695)
        self.assertNotEqual(self.t.OWNER_ID,self.t.AUDITOR_ID)


    def test_cloud_timeout_saved_id_and_no_replay(self):
        import json
        legacy=load('p2_legacy_tests_fixture','tests/test_p2_uk_swas_diagnostic.py')
        case=legacy.SplitCloudTests('test_cloud_intent_precedes_credentials')
        case.setUp()
        case.request['purpose']='READ_ONLY_DIAGNOSTIC_ONLY'
        def permit(operation,invoke,ident):
            case.policy=case.make_policy(operation,invoke,ident)
            binding=case.policy['binding']
            binding['command_sha256']=self.d.COMMAND_SHA256
            data=json.loads(case.body.split(chr(10),1)[1])
            data['decision']='READ_ONLY_DIAGNOSTIC_APPROVED'
            data['binding']=binding
            case.body='P2_UK_SPLIT_ONCE'+chr(10)+json.dumps(data)
            case.policy['approval_body_sha256']=hashlib.sha256(case.body.encode()).hexdigest()
        permit('READ_ONLY_DIAGNOSTIC','',1)
        self.assertEqual(case.call('read-only-diagnostic')['state'],'CLOUD_DISPATCHED_AWAIT_SEPARATE_QUERY')
        self.assertEqual(case.calls.count('RunCommand'),1)
        with self.assertRaises(RuntimeError):case.call('read-only-diagnostic')
        permit('READ_ONLY_DIAGNOSTIC_QUERY','t-real-fixture',2)
        results=['Timeout','Success']
        def query(obj,endpoint,action,**kwargs):
            case.calls.append(action)
            self.assertEqual(action,'DescribeInvocationResult')
            self.assertEqual(kwargs['InvokeId'],'t-real-fixture')
            return {'InvocationResult':{'InvokeId':kwargs['InvokeId'],
                'InstanceId':self.t.receipt.INSTANCE,'InvocationStatus':results.pop(0),
                'ExitCode':0,'Output':self.valid()}}
        case.rpc.__class__.__call__=query
        self.assertEqual(case.call('read-only-diagnostic-query','t-real-fixture')['state'],'CLOUD_QUERY_UNKNOWN')
        self.assertEqual(case.rows['state'],'CLOUD_QUERY_UNKNOWN')
        with self.assertRaises(RuntimeError):case.call('read-only-diagnostic-query','t-real-fixture')
        permit('READ_ONLY_DIAGNOSTIC_QUERY','t-real-fixture',3)
        self.assertEqual(case.call('read-only-diagnostic-query','t-real-fixture')['state'],'DIAGNOSTIC_VERIFIED')
        self.assertEqual(case.calls.count('RunCommand'),1)
        self.assertEqual(case.calls.count('DescribeInvocationResult'),2)

if __name__=='__main__':
    unittest.main()

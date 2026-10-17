import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import p2_uk_swas_diagnostic as d


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chmod(self.tmp.name,0o700)
        self.ledger=d.Ledger(self.tmp.name)
        self.addCleanup(self.ledger.close)
        self.calls=[]
        self.nonce='fixture_nonce'
        self.sha=hashlib.sha256(d.command(self.nonce).encode()).hexdigest()

    def rpc(self,endpoint,action,**kw):
        self.calls.append((endpoint,action,kw))
        if action=='RunCommand':return {'InvokeId':'t-fixture'}
        body=dict(hostname=d.receipt.HOST,uid=0,python=[3,6,8],nonce=self.nonce,private_inputs_read=False)
        return {'InvocationResult':dict(InvokeId='t-fixture',InstanceId=d.receipt.INSTANCE,InvocationStatus='Success',ExitCode=0,Output=json.dumps(body))}

    def start(self):return d.dispatch_once(self.ledger,'fixture_attempt',self.nonce,self.sha,self.rpc)

    def test_complete_fixed_uk_transport(self):
        self.start();r=d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(r['state'],'TRANSPORT_VERIFIED')
        self.assertFalse(r['p2_accepted'])
        self.assertTrue(all(c[0]==d.ENDPOINT for c in self.calls))
        self.assertEqual(self.calls[0][2]['InstanceId'],d.receipt.INSTANCE)

    def test_second_dispatch_rejected(self):
        self.start()
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(len(self.calls),1)

    def test_unknown_dispatch_consumed(self):
        def unknown(*a,**k):self.calls.append('network');raise OSError('PRIVATE')
        with self.assertRaises(RuntimeError) as c:d.dispatch_once(self.ledger,'a',self.nonce,self.sha,unknown)
        self.assertNotIn('PRIVATE',str(c.exception))
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(self.calls,['network'])

    def test_fsync_failure_prevents_dispatch(self):
        with patch.object(d.os,'fsync',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.start()
        self.assertEqual(self.calls,[])
        with self.assertRaises(FileExistsError):self.start()

    def test_crash_before_invoke_persist_no_redispatch(self):
        original=self.ledger.create
        def fail(name,value):
            if name=='invoke.json':raise OSError('fixture')
            return original(name,value)
        with patch.object(self.ledger,'create',side_effect=fail),self.assertRaises(RuntimeError):self.start()
        with self.assertRaises(FileExistsError):self.start()
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(FileNotFoundError):d.poll_existing(self.ledger,self.rpc)

    def test_bad_hash_before_consumption(self):
        with self.assertRaises(RuntimeError):d.dispatch_once(self.ledger,'a',self.nonce,'wrong',self.rpc)
        self.assertEqual(os.listdir(self.tmp.name),[])
        self.assertEqual(self.calls,[])

    def test_timeout_only_requery_same_invoke(self):
        self.start()
        def pending(*a,**kw):return {'InvocationResult':dict(InvokeId='t-fixture',InstanceId=d.receipt.INSTANCE,InvocationStatus='Running')}
        r=d.poll_existing(self.ledger,pending,2)
        self.assertEqual(r['state'],'QUERY_LIMIT_UNKNOWN')
        self.assertFalse(r['redispatch_allowed'])
        d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(sum(x[1]=='RunCommand' for x in self.calls),1)

    def test_terminal_rejected_and_no_repoll(self):
        self.start()
        def bad(*a,**kw):
            v=self.rpc(*a,**kw);v['InvocationResult']['Output']='PRIVATE';return v
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,bad)
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,self.rpc)
        self.assertTrue((Path(self.tmp.name)/'rejected.json').exists())

    def test_complete_receipt_no_repoll(self):
        self.start();d.poll_existing(self.ledger,self.rpc)
        with self.assertRaises(RuntimeError):d.poll_existing(self.ledger,self.rpc)

    def test_nonce_command_injection_rejected(self):
        with self.assertRaises(RuntimeError):d.command("a'; rm -rf /")

    def test_ledger_permissions(self):
        os.chmod(self.tmp.name,0o755)
        with self.assertRaises(RuntimeError):d.Ledger(self.tmp.name)

    def test_query_network_failure_keeps_saved_invoke(self):
        self.start()
        for error in (OSError('PRIVATE'),RuntimeError('PRIVATE')):
            def fail(*a,**kw):raise error
            with self.assertRaises(RuntimeError) as c:d.poll_existing(self.ledger,fail)
            self.assertNotIn('PRIVATE',str(c.exception))
        d.poll_existing(self.ledger,self.rpc)
        self.assertEqual(sum(x[1]=='RunCommand' for x in self.calls),1)

if __name__=='__main__':unittest.main()

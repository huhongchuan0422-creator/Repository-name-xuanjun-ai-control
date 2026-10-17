import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import pr122_remote_custody_prepare as r


class RemotePrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'attempt'
        self.expected=dict(attempt_id=r.ATTEMPT,source_commit='a'*40,
                           launcher_sha256='b'*64,review_zip_sha256=r.old.ZIP_SHA,
                           audit_body_sha256=r.old.AUDIT_SHA)
        self.trust=r.old.canonical(dict(binding=self.expected,owner_key={'fixture':True}))
        self.request=b'{"fixture":"no real Owner material"}'
        self.start(patch.object(r,'ROOT',self.root))
        self.start(patch.object(r.os,'getuid',return_value=0))
        self.start(patch.object(r.os,'geteuid',return_value=0))
        self.start(patch.object(r.os,'uname',return_value=type('Host',(),{'nodename':r.old.HOST})()))
        self.priv=self.start(patch.object(r,'private_read',side_effect=lambda p:self.trust if p==r.TRUST else self.request))
        self.val=self.start(patch.object(r.evidence,'validate',return_value={'envelope_sha256':'e'*64}))
        self.real_authorize=r.authorize
        self.auth=self.start(patch.object(r,'authorize',return_value='approved'))
        self.start(patch.object(r.old,'comment_body',return_value='audit'))
        self.start(patch.object(r.old,'read',return_value=b'package'))
        self.dec=self.start(patch.object(r.old,'decode',return_value=(b'helper',b'runtime')))

    def start(self,p):
        v=p.start();self.addCleanup(p.stop);return v

    def run_prepare(self):return r.prepare(123,'f'*64,get=lambda n:{})

    def test_success_only_prepares_and_consumes(self):
        result=self.run_prepare()
        self.assertFalse(result['helper_executed'])
        self.assertFalse(result['custody_independence_verified'])
        self.assertEqual(result['channel_changes'],0)
        for p in self.root.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o400)
        with self.assertRaises(RuntimeError):self.run_prepare()

    def test_missing_trust_stops_before_consumption(self):
        self.priv.side_effect=FileNotFoundError()
        with self.assertRaises(FileNotFoundError):self.run_prepare()
        self.assertFalse(self.root.exists())

    def test_invalid_signature_stops_before_consumption(self):
        self.val.side_effect=ValueError('HOLD')
        with self.assertRaises(ValueError):self.run_prepare()
        self.assertFalse(self.root.exists())

    def test_missing_new_permission_stops(self):
        self.auth.side_effect=RuntimeError('HOLD')
        with self.assertRaises(RuntimeError):self.run_prepare()
        self.assertFalse(self.root.exists())

    def test_bad_package_consumes_without_retry(self):
        self.dec.side_effect=RuntimeError('HOLD')
        with self.assertRaises(RuntimeError):self.run_prepare()
        self.assertEqual(json.loads((self.root/'failure.json').read_text())['state'],'HOLD')
        with self.assertRaises(RuntimeError):self.run_prepare()
        self.assertEqual(self.dec.call_count,1)

    def test_drift_after_consumption_holds(self):
        self.auth.side_effect=['approved','changed']
        with self.assertRaises(RuntimeError):self.run_prepare()
        self.assertTrue((self.root/'failure.json').exists())
        self.assertFalse((self.root/'receipt.json').exists())

    def test_interrupted_write_never_reopens_attempt(self):
        actual=r.old.write
        def crash(path,raw):
            if path.name=='attempt.json':raise OSError('synthetic fsync failure')
            return actual(path,raw)
        with patch.object(r.old,'write',side_effect=crash),self.assertRaises(OSError):self.run_prepare()
        with self.assertRaises(RuntimeError):self.run_prepare()
        self.assertTrue(self.root.exists())

    def test_real_gate_rejects_old_tty_permission(self):
        # Unmock only the gate under test; package/host fixtures stay isolated.
        self.auth.side_effect=None
        body=r.old.canonical({'decision':'OWNER_CUSTODY_PREPARE_APPROVED'}).decode()
        with patch.object(r.old,'comment_body',return_value='XUANJUN_PR122_OWNER_CUSTODY_PREPARE\n'+body):
            with self.assertRaises(RuntimeError):
                self.real_authorize(123,'f'*64,self.expected,'e'*64,'a'*64,lambda n:{})

    def test_real_gate_binds_exact_dependencies_and_limit(self):
        p=dict(decision='REMOTE_CUSTODY_PREPARE_APPROVED',attempt_id=r.ATTEMPT,
               host=r.old.HOST,binding=self.expected,envelope_sha256='e'*64,
               trust_sha256='a'*64,executor_sha256=r.old.sha(b'package'),
               evidence_validator_sha256=r.old.sha(b'package'),
               package_validator_sha256=r.old.sha(b'package'),max_attempts=1,
               channel_write_allowed=False,apply_allowed=False,issued_unix=100,expires_unix=200)
        with patch.object(r.time,'time',return_value=150):
            with patch.object(r.old,'comment_body',return_value=r.PURPOSE+'\n'+json.dumps(p)):
                self.real_authorize(123,'f'*64,self.expected,'e'*64,'a'*64,lambda n:{})
            for k,v in (('executor_sha256','wrong'),('trust_sha256','wrong'),
                        ('max_attempts',True),('apply_allowed',True),('expires_unix',149)):
                changed=dict(p);changed[k]=v
                with self.subTest(k=k),patch.object(r.old,'comment_body',return_value=r.PURPOSE+'\n'+json.dumps(changed)),self.assertRaises(RuntimeError):
                    self.real_authorize(123,'f'*64,self.expected,'e'*64,'a'*64,lambda n:{})

    def test_wrong_host_stops(self):
        with patch.object(r.os,'uname',return_value=type('Host',(),{'nodename':'other'})()),self.assertRaises(RuntimeError):self.run_prepare()
        self.assertFalse(self.root.exists())

if __name__=='__main__':unittest.main()

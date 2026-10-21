"""Real original queue/worker loop and files; cloud observations are fixtures."""
import base64
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import shlex
import tempfile
import unittest
from unittest.mock import patch

from production.cloud_connection.queue import Queue, Hold, canonical, TARGETS
from production.cloud_connection.worker import execute_ready, query_existing, HOSTS, PREFIX
from production.cloud_connection.runtime import Loop, PrivateStore, optional_hooks
from production.cloud_connection.fixed_actions import WebsiteBaselinePolicy, COLLECTOR_SHA, LABELS, SEALED

NOW=1800000000
PIN='a'*64
ACTOR=332398908


class FixedActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/root')
        self.root=Path(self.tmp.name)
        self.raw_source=(Path(__file__).resolve().parents[1]/'production/cloud_connection/pr122_baseline_collector.py').read_bytes()
        self.b={'schema':1,'project':'site-fixture','target':'domestic','operation':'website_baseline_collect',
                'source_commit':'b'*40,'collector_sha256':COLLECTOR_SHA,'execution_identity':'root',
                'max_output_bytes':32768,'input_manifest_sha256':'c'*64,'plan_sha256':'d'*64,
                'approval_ref':'offline-fixture-only','valid_from':NOW-1,'valid_until':NOW+100}
        self.policy=self.make_policy()
        self.q=Queue(str(self.root/'queue.sqlite'),PIN,{ACTOR},project_actions=self.policy)
        (self.root/'private').mkdir(mode=0o700)
        self.store=PrivateStore(self.root/'private')
        self.r={'schema':1,'request_id':'fixed-site','project':'site-fixture','target':'domestic',
                'operation':'project_fixed_action','executor_sha256':PIN,
                'arguments':{'binding_sha256':self.policy.sha},'expires_unix':NOW+60}
        self.calls=[]

    def make_policy(self):
        raw=canonical(self.b).encode()
        return WebsiteBaselinePolicy(self.raw_source,raw,hashlib.sha256(raw).hexdigest())

    def tearDown(self): self.store.close(); self.q.close(); self.tmp.cleanup()

    def cloud(self, dispatch_unknown=False, result=None):
        owner=self
        class Cloud:
            def call(self,target,action,args):
                owner.calls.append((target,action,args))
                if action == 'RunCommand':
                    if dispatch_unknown: raise OSError('response lost')
                    return {'InvokeId':'t-fixed'}
                return result or owner.response()
        return Cloud()

    def response(self, observation=None):
        if observation is None:
            observation={'scope':'STATIC_BASELINE_FIXED_READONLY_CANDIDATE','state':'OBSERVATION_ONLY',
                         'observations':[{'label':x,'state':'OBSERVED'} for x in sorted(LABELS)],
                         'inputs_root':'UNKNOWN_NOT_READ','source_root':'UNKNOWN_NOT_READ',
                         'writer_fence_lock_availability':'UNKNOWN','production_changes':0}
        data=canonical(observation).encode()
        v={'hostname':HOSTS['domestic'],'uid':0,'nonce':hashlib.sha256(canonical(self.r).encode()).hexdigest(),
           'collector_exit':0 if observation['state']=='OBSERVATION_ONLY' else 2,
           'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
        return {'InvocationResult':{'InvokeId':'t-fixed','InstanceId':TARGETS['domestic'][2],
                'InvocationStatus':'Success','ExitCode':0,'Output':canonical(v)}}

    def submit(self): return self.q.submit(canonical(self.r),ACTOR,NOW)

    def test_optional_hooks_default_does_not_read_any_file(self):
        with patch('production.cloud_connection.runtime.protected_read',side_effect=AssertionError('disabled')):
            self.assertEqual(optional_hooks({},self.root),(None,None))

    def test_optional_host_hooks_exact_binding_and_path(self):
        raw=canonical(self.b).encode()
        config={'website_baseline':{'metadata_ref':'/etc/xuanjun-cloud-executor/website-baseline-binding.json',
                                   'metadata_sha256':self.policy.sha}}
        source_dir=Path(__file__).resolve().parents[1]/'production/cloud_connection'
        with patch('production.cloud_connection.runtime.protected_read',return_value=raw):
            expiry,action=optional_hooks(config,source_dir)
            self.assertIsNone(expiry); self.assertEqual(action.sha,self.policy.sha)
            config['website_baseline']['metadata_sha256']='0'*64
            with self.assertRaisesRegex(Hold,'CONFIG_SHA'): optional_hooks(config,source_dir)
        config['website_baseline']['metadata_ref']='/tmp/untrusted'
        with self.assertRaisesRegex(Hold,'CONFIG_SCOPE'): optional_hooks(config,source_dir)

    def test_expiry_optional_hook_loads_only_pinned_nonsecret_metadata(self):
        raw=b'{"nonsecret":"fixture"}'
        c={'expiry_watch':{'metadata_ref':'/etc/xuanjun-cloud-executor/tunnel-expiry.json',
                           'metadata_sha256':hashlib.sha256(raw).hexdigest()}}
        with patch('production.cloud_connection.runtime.protected_read',return_value=raw):
            watch,action=optional_hooks(c,self.root)
            self.assertEqual(watch,(raw,hashlib.sha256(raw).hexdigest())); self.assertIsNone(action)
        # The existing lifecycle validator still checks the full schema at tick.

    def test_frozen_command_fits_swas_limit(self):
        command=self.policy.command(self.r)['CommandContent']
        self.assertLessEqual(len(base64.b64encode(command.encode())),16384)
        self.assertNotIn('curl',command)
        self.assertNotIn('wget',command)

    def test_real_frozen_command_rejects_local_wrong_host(self):
        if os.uname().nodename == HOSTS['domestic']:
            self.fail('offline test must not run on domestic production host')
        command=self.policy.command(self.r)['CommandContent']
        result=subprocess.run(shlex.split(command),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(result.returncode,0)
        envelope=json.loads(result.stdout.decode())
        self.assertNotEqual(envelope['collector_exit'],0)
        observed=json.loads(base64.b64decode(envelope['base64']).decode())
        self.assertEqual(observed['state'],'HOLD')

    def test_default_queue_refuses(self):
        other=Queue(str(self.root/'default.sqlite'),PIN,{ACTOR})
        try:
            with self.assertRaisesRegex(Hold,'NOT_ENROLLED'): other.submit(canonical(self.r),ACTOR,NOW)
        finally: other.close()

    def test_original_intake_loop_custody_and_repeat(self):
        owner=self
        class Github:
            def comments(self,since):
                return [{'id':1,'body':PREFIX+canonical(owner.r),'user':{'id':ACTOR},'created_at':'x','updated_at':'x'}]
            def call(self,path,body):
                self_body=body['body']
                owner.assertNotIn('base64',self_body)
                owner.assertNotIn('observations',self_body)
                return {'id':2}
        loop=Loop(self.q,Github(),self.cloud(),self.store)
        loop.tick(NOW); loop.tick(NOW+1)
        status=self.q.inspect('fixed-site')
        self.assertEqual(status['state'],'SUCCESS')
        receipt=status['receipt']
        data=self.store.read(receipt['file_ref'].split(':')[1])
        self.assertEqual(hashlib.sha256(data).hexdigest(),receipt['sha256'])
        self.assertEqual(len(json.loads(data)['observations']),20)
        self.assertEqual(len([x for x in self.calls if x[1]=='RunCommand']),1)
        self.assertEqual(self.calls[0][2]['WorkingUser'],'root')
        self.assertEqual(self.calls[0][2]['Timeout'],30)

    def test_source_and_host_approval_digest_required(self):
        raw=canonical(self.b).encode()
        with self.assertRaisesRegex(Hold,'SOURCE_PIN'): WebsiteBaselinePolicy(self.raw_source+b'\n',raw,self.policy.sha)
        with self.assertRaisesRegex(Hold,'HOST_ACTION_BINDING'): WebsiteBaselinePolicy(self.raw_source,raw,'0'*64)

    def test_wrong_project_target_args_and_sealed_refuse(self):
        for key,value in [('project','other'),('target','uk'),('arguments',{'binding_sha256':self.policy.sha,'command':'id'}),('request_id',SEALED)]:
            r=dict(self.r); r[key]=value
            with self.assertRaises(Hold): self.q.submit(canonical(r),ACTOR,NOW)
        self.assertEqual(self.q.db.execute('SELECT COUNT(*) FROM connection_jobs').fetchone()[0],0)

    def test_expiry_revalidated_before_original_dispatch(self):
        self.submit()
        with self.assertRaises(Hold): execute_ready(self.q,self.cloud(),'fixed-site',NOW+101)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.q.inspect('fixed-site')['state'],'READY')

    def test_ambiguous_dispatch_never_replayed_after_reopen(self):
        self.submit()
        with self.assertRaises(OSError): execute_ready(self.q,self.cloud(True),'fixed-site',NOW)
        self.q.close(); self.q=Queue(str(self.root/'queue.sqlite'),PIN,{ACTOR},project_actions=self.policy)
        with self.assertRaises(Hold): execute_ready(self.q,self.cloud(),'fixed-site',NOW)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(self.q.inspect('fixed-site')['state'],'UNKNOWN')

    def test_existing_invoke_queries_after_reopen_no_dispatch(self):
        self.submit(); execute_ready(self.q,self.cloud(),'fixed-site',NOW)
        self.q.unknown('fixed-site')
        self.q.close(); self.q=Queue(str(self.root/'queue.sqlite'),PIN,{ACTOR},project_actions=self.policy)
        query_existing(self.q,self.cloud(),'fixed-site',self.store.put)
        self.assertEqual(self.q.inspect('fixed-site')['state'],'SUCCESS')
        self.assertEqual([x[1] for x in self.calls],['RunCommand','DescribeInvocationResult'])

    def test_hold_keeps_private_failed_evidence(self):
        self.submit(); execute_ready(self.q,self.cloud(),'fixed-site',NOW)
        obs={'scope':'STATIC_BASELINE_FIXED_READONLY_CANDIDATE','state':'HOLD','observations':[]}
        query_existing(self.q,self.cloud(result=self.response(obs)),'fixed-site',self.store.put)
        r=self.q.inspect('fixed-site')
        self.assertEqual(r['state'],'FAILED')
        self.assertEqual(json.loads(self.store.read(r['receipt']['file_ref'].split(':')[1]))['state'],'HOLD')

    def test_wrong_identity_nonce_invoke_and_digest_refuse(self):
        for key,value in [('uid',1000),('hostname','wrong'),('nonce','0'*64),('sha256','0'*64)]:
            response=self.response(); v=json.loads(response['InvocationResult']['Output']); v[key]=value
            response['InvocationResult']['Output']=canonical(v)
            with self.assertRaises(Hold): self.policy.result(self.r,'t-fixed',response)
        response=self.response(); response['InvocationResult']['InvokeId']='t-other'
        with self.assertRaises(Hold): self.policy.result(self.r,'t-fixed',response)

    def test_missing_twentieth_observation_refuses(self):
        obs={'scope':'STATIC_BASELINE_FIXED_READONLY_CANDIDATE','state':'OBSERVATION_ONLY',
             'observations':[{'label':x} for x in sorted(LABELS)[:-1]]}
        with self.assertRaisesRegex(Hold,'TWENTY'): self.policy.result(self.r,'t-fixed',self.response(obs))

    def test_concurrent_original_project_writer_refused(self):
        self.submit(); execute_ready(self.q,self.cloud(),'fixed-site',NOW)
        other=dict(self.r,request_id='second-fixture')
        self.q.submit(canonical(other),ACTOR,NOW)
        with self.assertRaises(sqlite3.IntegrityError): execute_ready(self.q,self.cloud(),'second-fixture',NOW)
        self.assertEqual(len(self.calls),1)

    def test_private_sink_failure_preserves_existing_invoke(self):
        self.submit(); execute_ready(self.q,self.cloud(),'fixed-site',NOW)
        def failed(*args): raise OSError('custody failed')
        with self.assertRaises(OSError): query_existing(self.q,self.cloud(),'fixed-site',failed)
        self.assertEqual(self.q.inspect('fixed-site')['invoke_id'],'t-fixed')
        self.assertNotEqual(self.q.inspect('fixed-site')['state'],'SUCCESS')
        with self.assertRaises(Hold): execute_ready(self.q,self.cloud(),'fixed-site',NOW)

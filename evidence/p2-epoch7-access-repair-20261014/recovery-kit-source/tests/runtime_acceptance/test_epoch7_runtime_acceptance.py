import copy
import hashlib
import io
import json
import os
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

import epoch7_runtime_acceptance as m
from epoch7_recovery_sequence import BoundedDiagnostics
from epoch7_complete_approval import (preapproval_sequence_contract, sequence_contract,
    sequence_contract_sha256, expected_complete_from_inputs, digest)
from epoch7_injected_recovery import required_authorization
from test_epoch7_delta import fixture
import epoch7_delta as d


def inputs():
    # Complete synthetic proposal; pure preapproval construction has no ID.
    snapshot, candidate = fixture()
    candidate['manifest_sha256'] = m.MANIFEST
    candidate['activation']['release_sha256'] = m.MANIFEST
    delta = d.build_delta(snapshot, d.digest(snapshot), candidate)
    authorization = required_authorization(delta, 'a'*64, 'b'*64, [])
    contract = preapproval_sequence_contract(delta, authorization)
    # Only execution fixtures receive a synthetic admission ID.
    context = dict(contract, review_id=7000000000)
    context['context_sha256'] = digest(context)
    rows=[]
    for role,(unit,user,uid,gid) in sorted(m.ROLES.items()):
        nss=sorted(set([uid,gid]));supp=[]
        identity={'unit':unit,'user':user,'uid':uid,'gid':gid,'nss_groups':nss,
                  'unit_supplementary_groups':supp,'groups':nss}
        paths=[{'path':p,'kind':kind,'sha256':None if kind=='directory' else 'b'*64}
               for p,kind in sorted(m.required_paths()[role].items())]
        rows.append({'role':role,'identity':identity,'paths':paths})
    tls={'journal':m.TRANSACTION+'/tls-lifecycle.json','journal_sha256':'c'*64,
         'root':m.TLS_ROOT,'tree_sha256':'d'*64,'certificate_sha256':'e'*64,
         'config_sha256':'f'*64,'domain':m.DOMAIN,'manifest_sha256':m.MANIFEST}
    return context,rows,tls


def module(code):
    ns={'__name__':'fixture_worker'};exec(compile(code,'<fixture-worker>','exec'),ns);return ns


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.context,self.rows,self.tls=inputs();self.diag=BoundedDiagnostics(Mock())
        self.guard=Mock(return_value=True);self.calls=[];self.outputs={}
    def factory(self,contract,guard,diagnostics):
        self.contract=contract
        def run(key):
            self.assertTrue(guard());self.calls.append(key)
            if key in self.outputs:return self.outputs[key]
            v=json.loads(contract[key]['argv'][-1]);digest=m.sha(m.canonical(v))
            if key.startswith('access_'):
                i=v['identity'];result={'schema':1,'phase':'verify_runtime_access','state':'OBSERVED',
                    'contract_sha256':digest,'role':v['role'],'uid':i['uid'],'gid':i['gid'],
                    'groups':i['groups'],'paths_verified':len(v['paths']),'file_contents_emitted':False,
                    'service_namespace_reproduced':False,'model_calls':0,'database_operations':0}
            else:
                result={'schema':1,'phase':'post_install_checks','state':'OBSERVED','contract_sha256':digest,
                    'retained_certificate_ready':True,'served_certificate_sha256':v['certificate_sha256'],
                    'https_statuses':{'/owner/':200,'/owner/api/state':401,'/owner-callback':405},
                    'new_issue_calls':0,'renew_calls':0,'dry_run_calls':0,'model_calls':0,'notification_calls':0,
                    'owner_ack':'PENDING','business_e2e':'PENDING','production_acceptance':'PENDING'}
            return subprocess.CompletedProcess(None,0,m.packed(result),b'')
        return types.SimpleNamespace(run=run)
    def make(self,**changes):
        values=dict(context=self.context,access_rows=self.rows,tls=self.tls,live_check=self.guard,
            diagnostics=self.diag,expected_contract_sha256=m.sha(m.canonical(
                m.compile_acceptance_contract(self.context,self.rows,self.tls))),runner_factory=self.factory)
        values.update(changes);return m.RuntimeAcceptanceChecks(**values)
    def test_finite_contract_actual_uid_workers_no_shell_or_network_on_construct(self):
        r=self.make();self.assertEqual(len(r.contract),7);self.assertEqual(self.calls,[])
        m.ExactCommandRunner(r.contract,lambda:True,self.diag,Mock())
        for spec in r.contract.values():
            self.assertEqual(spec['argv'][:5],['/usr/bin/python3','-I','-B','-S','-c'])
            self.assertEqual(spec['cwd'],'/');self.assertLessEqual(spec['timeout'],50)
            self.assertLessEqual(len(spec['argv'][5]),8192)
        self.assertNotIn('subprocess',m.ACCESS_WORKER+m.HTTPS_WORKER)
    def test_exact_six_role_access_observations(self):
        r=self.make();result=r.verify_runtime_access(self.context,self.diag)
        self.assertEqual(len(self.calls),6);self.assertEqual(result['operation'],'verify_runtime_access')
        self.assertTrue(all(v['service_namespace_reproduced'] is False for v in r.results['verify_runtime_access']))
    def test_https_retained_fact_never_claims_new_issuance_or_owner_acceptance(self):
        r=self.make();result=r.post_install_checks(self.context,self.diag)
        facts=r.results['post_install_checks'];self.assertTrue(facts['retained_certificate_ready'])
        self.assertEqual(facts['new_issue_calls'],0);self.assertEqual(facts['renew_calls'],0)
        self.assertEqual(facts['owner_ack'],'PENDING');self.assertEqual(facts['production_acceptance'],'PENDING')
        self.assertEqual(result['operation'],'post_install_checks')
    def test_contract_hash_required(self):
        with self.assertRaises(ValueError):self.make(expected_contract_sha256='0'*64)
        self.assertEqual(self.calls,[])
    def test_missing_path_extra_path_and_unpinned_file_rejected(self):
        for variant in ('missing','extra','pin'):
            rows=copy.deepcopy(self.rows)
            if variant=='missing':rows[0]['paths'].pop()
            elif variant=='extra':rows[0]['paths'].append({'path':'/etc/shadow','kind':'file','sha256':'a'*64})
            else:next(p for p in rows[0]['paths'] if p['kind']=='file')['sha256']=None
            with self.assertRaises(ValueError):m.validate_access(rows)
    def test_wrong_uid_root_group_and_unknown_role_rejected(self):
        for name in ('uid','groups','role'):
            rows=copy.deepcopy(self.rows)
            if name=='uid':rows[0]['identity']['uid']=0
            elif name=='groups':rows[0]['identity']['groups']=[0]
            else:rows[0]['role']='other'
            with self.assertRaises(ValueError):m.validate_access(rows)
    def test_tls_scope_no_external_target_or_missing_pin(self):
        for key,value in (('domain','example.com'),('root','/tmp/tls'),('certificate_sha256',None)):
            bad=dict(self.tls,**{key:value})
            with self.assertRaises(ValueError):m.validate_tls(bad)
    def test_live_guard_literal_true_and_no_phase_retry(self):
        self.guard.return_value=1;r=self.make()
        with self.assertRaises(ValueError):r.verify_runtime_access(self.context,self.diag)
        self.guard.return_value=True
        with self.assertRaises(ValueError):r.verify_runtime_access(self.context,self.diag)
        self.assertEqual(self.calls,[])
    def test_mutated_reviewed_access_contract_cannot_launch(self):
        r=self.make();next(p for p in r.access[0]['paths'] if p['kind']=='file')['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'ACCEPTANCE_CONTRACT_MUTATED'):
            r.verify_runtime_access(self.context,self.diag)
        self.assertEqual(self.calls,[])
    def test_stale_worker_output_or_wrong_identity_cannot_be_observed(self):
        r=self.make();self.outputs['access_callback']=subprocess.CompletedProcess(None,0,b'{"schema":1,"state":"OBSERVED"}',b'')
        with self.assertRaises(ValueError):r.verify_runtime_access(self.context,self.diag)
        self.assertEqual(self.calls,['access_callback'])

    def test_preapproval_acceptance_pin_independent_of_future_review_id(self):
        neutral = sequence_contract(self.context)
        before = m.compile_acceptance_contract(neutral, self.rows, self.tls)
        frozen_plan = m.packed({'schema':1, 'acceptance_contract_sha256':digest(before),
                               'sequence_contract_sha256':sequence_contract_sha256(neutral)})
        frozen_hash = m.sha(frozen_plan)
        contexts = []
        for review_id in (7000000000, 7000000001):
            context = dict(neutral, review_id=review_id)
            context['context_sha256'] = digest(context)
            contexts.append(context)
            after = m.compile_acceptance_contract(context, self.rows, self.tls)
            self.assertEqual(after, before)
            self.assertEqual(m.sha(m.packed({'schema':1,
                'acceptance_contract_sha256':digest(after),
                'sequence_contract_sha256':sequence_contract_sha256(context)})), frozen_hash)
        self.assertNotEqual(contexts[0]['context_sha256'], contexts[1]['context_sha256'])
        self.assertNotIn('context_sha256', before)
        self.assertNotIn('review_id', neutral)

    def test_neutral_contract_is_not_execution_admission(self):
        neutral = sequence_contract(self.context)
        with self.assertRaisesRegex(ValueError, 'ACCEPTANCE_ADMITTED_CONTEXT_REQUIRED'):
            self.make(context=neutral)
        self.assertEqual(self.calls, [])

    def test_execution_input_hash_binds_actual_review_id(self):
        first = self.make()
        other_context = sequence_contract(self.context)
        other_context['review_id'] = self.context['review_id'] + 1
        other_context['context_sha256'] = digest(other_context)
        second = self.make(context=other_context)
        self.assertEqual(first.binding, second.binding)
        self.assertNotEqual(first.inputs, second.inputs)
        self.assertEqual(first.inputs['access_callback']['context_sha256'],
                         self.context['context_sha256'])
        with self.assertRaisesRegex(ValueError, 'ACCEPTANCE_ONE_EXACT_PHASE'):
            first.verify_runtime_access(other_context, self.diag)
        self.assertEqual(self.calls, [])

    def test_self_consistent_switch_to_other_id_cannot_rebind_execution(self):
        instance = self.make()
        instance.context['review_id'] += 1
        instance.context.pop('context_sha256')
        instance.context['context_sha256'] = digest(instance.context)
        with self.assertRaisesRegex(ValueError, 'ACCEPTANCE_ONE_EXACT_PHASE'):
            instance.verify_runtime_access(instance.context, self.diag)
        self.assertEqual(self.calls, [])

    def test_stale_context_hash_cannot_compile_or_execute(self):
        other = dict(self.context, review_id=self.context['review_id']+1)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_CONTEXT_MUTATED'):
            m.compile_acceptance_contract(other, self.rows, self.tls)
        with self.assertRaisesRegex(ValueError, 'COMPLETE_CONTEXT_MUTATED'):
            self.make(context=other)

    def test_any_changed_reviewed_pin_changes_acceptance_contract(self):
        neutral = sequence_contract(self.context)
        before = m.compile_acceptance_contract(neutral, self.rows, self.tls)
        neutral['security_delta_sha256'] = 'f'*64
        after = m.compile_acceptance_contract(neutral, self.rows, self.tls)
        self.assertNotEqual(before, after)
        self.assertNotEqual(digest(before), digest(after))


def isolated_access_value(role='callback'):
    unit,user,uid,gid=m.ROLES[role]
    return {'mode':'access','role':role,'identity':{'unit':unit,'user':user,'uid':uid,'gid':gid,
        'nss_groups':[gid],'unit_supplementary_groups':[],'groups':[gid]},
        'paths':[{'path':path,'kind':kind,'sha256':None if kind=='directory' else 'b'*64}
            for path,kind in sorted(m.required_paths()[role].items())]}


class AccessWorkerTests(unittest.TestCase):
    def setUp(self):self.w=module(m.ACCESS_WORKER)
    def test_permanent_identity_drop_precedes_file_inspection(self):
        v=isolated_access_value();i=v['identity'];order=[]
        with patch.object(self.w['os'],'geteuid',return_value=0), \
             patch.object(self.w['pwd'],'getpwnam',return_value=types.SimpleNamespace(pw_uid=i['uid'],pw_gid=i['gid'])), \
             patch.object(self.w['os'],'getgrouplist',return_value=i['nss_groups']), \
             patch.object(self.w['os'],'setgroups',side_effect=lambda g:order.append('groups')), \
             patch.object(self.w['os'],'setresgid',side_effect=lambda *g:order.append('gid')), \
             patch.object(self.w['os'],'setresuid',side_effect=lambda *g:order.append('uid')), \
             patch.object(self.w['os'],'getresuid',return_value=(i['uid'],)*3), \
             patch.object(self.w['os'],'getresgid',return_value=(i['gid'],)*3), \
             patch.object(self.w['os'],'getgroups',return_value=i['groups']), \
             patch('builtins.open',return_value=io.BytesIO(b'CapEff:\t0000000000000000\nCapPrm:\t0000000000000000\n')):
            self.w['inspect_rows']=lambda paths,end:order.append('read') or len(paths)
            result=self.w['execute'](v)
        self.assertEqual(order,['groups','gid','uid','read']);self.assertEqual(result['uid'],i['uid'])
        self.assertEqual(result['database_operations'],0)
    def test_unit_primary_not_passwd_primary_drives_nss(self):
        v=isolated_access_value();i=v['identity']
        i['nss_groups']=[1006];i['groups']=sorted(set([1006]+i['unit_supplementary_groups']))
        def resolved(user,primary):
            self.assertEqual((user,primary),('xuanjun-callback',1006))
            return [1006]
        with patch.object(self.w['os'],'geteuid',return_value=0), \
             patch.object(self.w['pwd'],'getpwnam',return_value=types.SimpleNamespace(pw_uid=1004,pw_gid=1004)), \
             patch.object(self.w['os'],'getgrouplist',side_effect=resolved), \
             patch.object(self.w['os'],'setgroups') as drop, \
             patch.object(self.w['os'],'setresgid'),patch.object(self.w['os'],'setresuid'), \
             patch.object(self.w['os'],'getresuid',return_value=(1004,)*3), \
             patch.object(self.w['os'],'getresgid',return_value=(1006,)*3), \
             patch.object(self.w['os'],'getgroups',return_value=i['groups']), \
             patch('builtins.open',return_value=io.BytesIO(b'CapEff:\t0000000000000000\nCapPrm:\t0000000000000000\n')):
            self.w['inspect_rows']=lambda paths,end:len(paths)
            self.w['execute'](v)
            drop.assert_called_once_with(i['groups']);self.assertNotIn(1004,i['groups'])
    def test_nss_drift_stops_before_drop(self):
        v=isolated_access_value();i=v['identity']
        with patch.object(self.w['os'],'geteuid',return_value=0), \
             patch.object(self.w['pwd'],'getpwnam',return_value=types.SimpleNamespace(pw_uid=i['uid'],pw_gid=i['gid'])), \
             patch.object(self.w['os'],'getgrouplist',return_value=[999]), \
             patch.object(self.w['os'],'setgroups') as drop:
            with self.assertRaises(ValueError):self.w['execute'](v)
            drop.assert_not_called()
    def test_deadline_stops_reads(self):
        with patch.object(self.w['time'],'monotonic',return_value=10):
            with self.assertRaises(ValueError):self.w['inspect_rows']([{'path':'/fixture','kind':'directory'}],9)
    def inspect_file(self,path,uid,gid,mode=0o600):
        raw=b'LOCAL_SYNTHETIC_PRIVATE_VALUE';row={'path':path,'kind':'file','sha256':m.sha(raw)}
        info=types.SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|mode,st_uid=uid,st_gid=gid,
            st_nlink=1,st_size=len(raw),st_mtime_ns=1,st_ctime_ns=1)
        with patch.object(self.w['os'].path,'realpath',return_value=path), \
             patch.object(self.w['os'],'open',return_value=123),patch.object(self.w['os'],'fstat',return_value=info), \
             patch.object(self.w['os'],'lstat',return_value=info),patch.object(self.w['os'],'read',side_effect=[raw,b'']), \
             patch.object(self.w['os'],'close'),patch.object(self.w['time'],'monotonic',return_value=1):
            return self.w['inspect_rows']([row],10)
    def test_exact_five_owner_private_paths_accept_callback_owned0600(self):
        for leaf in ('owner-callback-auth','owner-callback-hmac','owner-user-id','owner-chat-id','owner-dashboard-token'):
            self.assertEqual(self.inspect_file(m.OWNER+'/'+leaf,1004,1006),1)
    def test_owner_private_root_other_uid_gid_or_mode_rejected(self):
        for uid,gid,mode in ((0,1006,0o600),(1002,1006,0o600),(1004,1004,0o600),(1004,1006,0o640)):
            with self.assertRaises(ValueError):self.inspect_file(m.OWNER+'/owner-callback-auth',uid,gid,mode)
    def test_other_file_cannot_use_callback_ownership(self):
        for path in (m.CONFIG+'/dispatcher.json',m.OWNER+'/unreviewed-secret',m.RELEASE+'/stage1/ledger_service.py'):
            with self.assertRaises(ValueError):self.inspect_file(path,1004,1006)
    def test_other_root_protected_file_still_accepts(self):
        self.assertEqual(self.inspect_file(m.CONFIG+'/dispatcher.json',0,1003,0o640),1)


class HttpsWorkerTests(unittest.TestCase):
    def setUp(self):
        self.w=module(m.HTTPS_WORKER);self.c,self.rows,self.tls=inputs();self.cert=b'FIXTURE_CERT'
        self.tls['certificate_sha256']=hashlib.sha256(self.cert).hexdigest()
        self.raw=Mock();self.secure=Mock();self.context=Mock(check_hostname=True,verify_mode=self.w['ssl'].CERT_REQUIRED)
        self.context.wrap_socket.return_value=self.secure
        self.secure.getpeercert.side_effect=lambda binary_form=False:self.cert if binary_form else {'notAfter':'far future'}
    def route(self,path='/owner/',status=200,headers=None):
        data=headers or ('HTTP/1.1 %s OK\r\nContent-Length: 0\r\n\r\n'%status).encode()
        self.secure.recv.side_effect=[data[i:i+1] for i in range(len(data))]
        with patch.object(self.w['socket'],'socket',return_value=self.raw), \
             patch.object(self.w['ssl'],'create_default_context',return_value=self.context), \
             patch.object(self.w['ssl'],'cert_time_to_seconds',return_value=200000), \
             patch.object(self.w['time'],'time',return_value=100), \
             patch.object(self.w['time'],'monotonic',return_value=1):
            return self.w['route'](path,self.tls,50)
    def test_loopback_tls_sni_cert_pin_and_crlf_get_only(self):
        self.assertEqual(self.route(),200)
        self.raw.connect.assert_called_once_with(('127.0.0.1',443))
        self.context.wrap_socket.assert_called_once_with(self.raw,server_hostname=m.DOMAIN)
        request=self.secure.sendall.call_args[0][0]
        self.assertIn(b'GET /owner/ HTTP/1.1\r\n',request);self.assertTrue(request.endswith(b'\r\n\r\n'))
        self.assertNotIn(b'Authorization',request);self.secure.close.assert_called_once()
    def test_unauthenticated_api_and_callback_expected_statuses(self):
        self.assertEqual(self.route('/owner/api/state',401),401)
        self.assertEqual(self.route('/owner-callback',405),405)
    def test_redirect_auth_success_bad_cert_and_untrusted_context_hold(self):
        for variant in ('redirect','auth_success','cert','trust'):
            self.setUp()
            if variant=='cert':self.tls['certificate_sha256']='a'*64
            if variant=='trust':self.context.check_hostname=False
            with self.assertRaises(ValueError):self.route('/owner/api/state',302 if variant=='redirect' else 200)
            self.raw.close.assert_called_once()
    def test_header_output_bound(self):
        with self.assertRaises(ValueError):self.route(headers=b'HTTP/1.1 200 OK\r\nX: '+b'x'*32768)
        self.secure.close.assert_called_once()
    def test_one_deadline_bounds_trickle(self):
        with patch.object(self.w['time'],'monotonic',return_value=100):
            with self.assertRaises(ValueError):self.w['remaining'](99)
    def test_retained_ready_journal_checks_before_network_and_after(self):
        v=dict(self.tls,mode='https');record={'state':m.TLS_READY,'certificate_sha256':v['certificate_sha256'],
            'fingerprint':v['tree_sha256'],'config':{'release_sha256':m.MANIFEST}}
        raw=m.canonical(record);v['journal_sha256']=m.sha(raw);v['config_sha256']=m.sha(m.canonical(record['config']))
        reads=Mock(return_value=raw);fp=Mock(return_value=v['tree_sha256']);routes=Mock(side_effect=[200,401,405])
        self.w['read_regular'],self.w['fingerprint'],self.w['route']=reads,fp,routes
        with patch.object(self.w['os'],'geteuid',return_value=0):result=self.w['execute'](v)
        self.assertEqual(reads.call_count,2);self.assertEqual(fp.call_count,2);self.assertEqual(routes.call_count,3)
        self.assertTrue(result['retained_certificate_ready']);self.assertEqual(result['new_issue_calls'],0)
        self.assertEqual(result['business_e2e'],'PENDING')
    def test_wrong_retained_journal_state_cannot_reach_network(self):
        v=dict(self.tls,mode='https');record={'state':'REQUESTED'};raw=m.canonical(record);v['journal_sha256']=m.sha(raw)
        self.w['read_regular']=Mock(return_value=raw);self.w['route']=Mock()
        with patch.object(self.w['os'],'geteuid',return_value=0):
            with self.assertRaises((ValueError,KeyError)):self.w['execute'](v)
        self.w['route'].assert_not_called()


if __name__=='__main__':unittest.main()

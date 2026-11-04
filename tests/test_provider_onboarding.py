from __future__ import print_function

import json
import os
import shutil
import tempfile
import time
import unittest
import sys

from cryptography.fernet import Fernet

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))

from model_orchestration import ModelControl, OpenAICompatibleAdapter, ProviderError
from provider_onboarding import (PRESETS, ensure_schema, projection,
    public_presets, issue_receipt, save, test_connection, test_model,
    verify_receipt)
from connection_management import ConnectionManager
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_supervisor import Supervisor


KEY=b'0123456789abcdef0123456789abcdef'
SECRET='sk-test-only-123456789'


class ProviderOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.mkdtemp();self.db=os.path.join(self.root,'state.sqlite3')
        self.supervisor=Supervisor(self.db)
        authority=TestTenantAuthority(KEY)
        self.gateway=GatewayKernel(self.supervisor,authority)
        self.context=authority.issue('tenant-a','admin:owner')
        self.master=Fernet.generate_key()
        self.control=ModelControl(self.gateway,self.context,self.master)

    def tearDown(self):
        self.supervisor.close();shutil.rmtree(self.root)

    def test_public_presets_hide_internal_destination_and_include_first_platforms(self):
        values=public_presets();encoded=json.dumps(values,ensure_ascii=False)
        self.assertEqual({x['platform'] for x in values},
          {'siliconflow','bailian','deepseek','openai','chatgpt'})
        chatgpt=next(x for x in values if x['platform']=='chatgpt')
        self.assertEqual(chatgpt['availability'],'UNSUPPORTED')
        for internal in ('base_url','provider_id','adapter_type','api.siliconflow.cn'):
            self.assertNotIn(internal,encoded)

    def test_auth_catalog_receipt_and_save_keep_secret_encrypted(self):
        class Adapter(object):
            def list_models(self,base_url,secret,timeout):
                self.base_url=base_url;self.secret=secret
                return ['model-b','model-a','model-a']
        adapter=Adapter();tested=test_connection('siliconflow',SECRET,adapter)
        self.assertEqual(tested['auth_state'],'SUCCEEDED')
        self.assertEqual(tested['model_callable_state'],'UNVERIFIED_NO_INFERENCE')
        receipt=issue_receipt(self.master,'tenant-a','siliconflow',SECRET,
                              tested['models'])
        result=save(self.control,self.master,'siliconflow','团队默认',SECRET,
                    'model-a',receipt)
        self.assertEqual(result['configuration_state'],'SAVED')
        self.assertEqual(result['quota_state'],'UNKNOWN')
        self.assertEqual(result['paid_inference'],'NOT_EXECUTED')
        projected=json.dumps(self.control.projection(),ensure_ascii=False)
        self.assertNotIn(SECRET,projected);self.assertIn('••••6789',projected)
        self.supervisor.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.supervisor.db.commit()
        with open(self.db,'rb') as stream:self.assertNotIn(SECRET.encode(),stream.read())

    def test_previous_single_connection_and_model_are_unambiguously_recovered(self):
        value=PRESETS['siliconflow']
        self.control.upsert_provider({'provider_id':'siliconflow',
          'display_name':'硅基流动','adapter_type':'siliconflow',
          'base_url':value['base_url'],'enabled':True,'price_state':'UNKNOWN',
          'rate_limit_per_min':10,'concurrency_limit':2,
          'timeout_seconds':10,'retry_limit':0},SECRET)
        self.control.upsert_model({'provider_id':'siliconflow',
          'model_id':'chosen-chat','capabilities':['general'],'enabled':True,
          'price_state':'UNKNOWN','input_unit_cost':None,'output_unit_cost':None})
        ConnectionManager(self.gateway,self.context,self.master).upsert({
          'connection_id':'siliconflow-custom','provider_id':'siliconflow',
          'purpose':'MODEL_INFERENCE','auth_type':'API_KEY',
          'destination_origin':value['base_url'],'issuer':None,
          'authorization_endpoint':None,'token_endpoint':None,
          'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
          'scopes':[],'supports_refresh':False},SECRET)
        ensure_schema(self.supervisor.db)
        saved=projection(self.supervisor.db,'tenant-a')
        self.assertEqual(saved[0]['connection_id'],'siliconflow-custom')
        self.assertEqual(saved[0]['model_id'],'chosen-chat')
        self.assertEqual(saved[0]['model_callable_state'],
                         'UNVERIFIED_NO_INFERENCE')

    def test_tampered_expired_or_unlisted_model_receipt_is_rejected_before_save(self):
        now=time.time();token=issue_receipt(self.master,'tenant-a','deepseek',
          SECRET,['deepseek-chat'],now=now)
        cases=[('other-model',token,now),
               ('deepseek-chat',token+'x',now),
               ('deepseek-chat',token,now+601)]
        for model,receipt,clock in cases:
            with self.assertRaisesRegex(ValueError,'RECEIPT'):
                verify_receipt(self.master,'tenant-a','deepseek',SECRET,model,
                               receipt,now=clock)
        self.assertEqual(self.control.list_providers(),[])

    def test_auth_failure_is_chinese_and_has_zero_writes(self):
        class Rejected(object):
            def list_models(self,*args):raise ProviderError('AUTH','HTTP_401')
        with self.assertRaisesRegex(ValueError,'API Key'):
            test_connection('deepseek',SECRET,Rejected())
        self.assertEqual(self.control.list_providers(),[])

    def test_openai_compatible_catalog_uses_platform_prefix_and_parses_ids(self):
        seen=[]
        class Response(object):
            def read(self,_limit):return b'{"data":[{"id":"qwen-plus"},{"id":"qwen-max"}]}'
        def opener(request,timeout):
            seen.append((request.full_url,request.get_method(),timeout,
                         request.get_header('Authorization')))
            return Response()
        models=OpenAICompatibleAdapter(opener).list_models(
          PRESETS['bailian']['base_url'],SECRET,7)
        self.assertEqual(models,['qwen-max','qwen-plus'])
        self.assertEqual(seen,[('https://dashscope.aliyuncs.com/compatible-mode/v1/models',
                                'GET',7,'Bearer '+SECRET)])

    def test_real_model_test_requires_explicit_one_call_confirmation(self):
        token=issue_receipt(self.master,'tenant-a','deepseek',SECRET,
                            ['deepseek-chat'])
        calls=[]
        class Adapter(object):
            def invoke(self,*args,**kwargs):
                calls.append((args,kwargs));return {'content':'OK','usage':{
                  'input_tokens':5,'output_tokens':1,'total_tokens':6},
                  'provider_request_id':'fixture-call'}
        with self.assertRaisesRegex(ValueError,'CONFIRMATION'):
            test_model(self.control,self.master,'tenant-a','deepseek',SECRET,
                       'deepseek-chat',token,False,Adapter())
        self.assertEqual(calls,[])
        result=test_model(self.control,self.master,'tenant-a','deepseek',SECRET,
                          'deepseek-chat',token,True,Adapter())
        self.assertEqual(result['model_callable_state'],'TESTED_SUCCEEDED')
        self.assertEqual(result['usage_state'],'KNOWN')
        self.assertEqual(calls[0][1]['max_output_tokens'],2)
        with self.assertRaisesRegex(ValueError,'ALREADY_USED'):
            test_model(self.control,self.master,'tenant-a','deepseek',SECRET,
              'deepseek-chat',token,True,Adapter())
        self.assertEqual(len(calls),1)
        saved=save(self.control,self.master,'deepseek',None,SECRET,
                   'deepseek-chat',token,result['call_receipt'])
        self.assertEqual(saved['model_callable_state'],'TESTED_SUCCEEDED')


if __name__=='__main__':unittest.main()

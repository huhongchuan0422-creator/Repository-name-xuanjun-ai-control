from __future__ import print_function

import os
import http.client
import json
import socket
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

ROOT=os.path.realpath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0,os.path.join(ROOT,'scripts'))
import task_center_mcp_free_model_gate as gate
from task_center_mcp_free_model_gate import parse_zero_price_page
from model_orchestration import OpenAICompatibleAdapter


class FreeModelGateTests(unittest.TestCase):
    def page(self,prompt='0',completion='0',display='Qwen2.5-7B-Instruct (Free)'):
        return (r'''631:{\"price\":\"%s\",\"specification\":\"prompt\",\"unitOfGood\":\"/ M Tokens\"}\n'''+
          r'''632:{\"price\":\"%s\",\"specification\":\"completion\",\"unitOfGood\":\"/ M Tokens\"}\n'''+
          r'''630:[\"$631\",\"$632\"]\n'''+
          r'''622:{\"modelName\":\"Qwen/Qwen2.5-7B-Instruct\",\"price\":\"0\",\"currency\":\"¥\",\"DisplayName\":\"%s\",\"type\":\"text\",\"subType\":\"chat\",\"status\":\"normal\",\"targetModelName\":\"Qwen/Qwen2.5-7B-Instruct\",\"onlyByChargeBalance\":false,\"pricing\":\"$630\",\"priceUnit\":\"/ M Tokens\"}\n''')%(prompt,completion,display)

    def test_exact_free_chat_model_and_both_zero_prices_are_required(self):
        value=parse_zero_price_page(self.page().encode('utf-8'))
        self.assertEqual(value['model_id'],'Qwen/Qwen2.5-7B-Instruct')
        self.assertEqual((value['prompt_price'],value['completion_price']),('0','0'))
        self.assertEqual(value['only_by_charge_balance'],False)

    def test_nonzero_prompt_or_completion_is_rejected(self):
        for prompt,completion in (('1','0'),('0','1')):
            with self.assertRaisesRegex(ValueError,'ZERO_PROMPT_AND_COMPLETION'):
                parse_zero_price_page(self.page(prompt,completion).encode('utf-8'))

    def test_pro_or_changed_display_record_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'EXACT_FREE_MODEL_FIELDS'):
            parse_zero_price_page(self.page(display=
              'Qwen2.5-7B-Instruct (Pro)').encode('utf-8'))

    def test_pinned_transport_receives_exact_price_models_and_chat_paths(self):
        adapter=OpenAICompatibleAdapter();response=mock.Mock(status=200)
        address=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1',443))]
        with mock.patch.object(socket,'getaddrinfo',return_value=address), \
             mock.patch.object(http.client.HTTPSConnection,'request',
               autospec=True) as request, \
             mock.patch.object(http.client.HTTPSConnection,'getresponse',
               autospec=True,return_value=response):
            connections=[]
            connections.append(adapter._pinned_open(urlparse(
              'https://siliconflow.cn/pricing'),None,{},10,method='GET',
              endpoint_path='')[0])
            connections.append(adapter._pinned_open(urlparse(
              'https://api.siliconflow.cn'),None,{},10,method='GET',
              endpoint_path='/v1/models')[0])
            connections.append(adapter._pinned_open(urlparse(
              'https://api.siliconflow.cn'),b'{}',{},10)[0])
            for connection in connections:connection.close()
        observed=[(item[0][1],item[0][2]) for item in request.call_args_list]
        self.assertEqual(observed,[('GET','/pricing'),
          ('GET','/v1/models'),('POST','/v1/chat/completions')])

    def test_pricing_follows_one_official_https_redirect_and_parses_zero(self):
        page=self.page().encode('utf-8')
        class Response(object):
            def __init__(self,status,headers=None,body=b''):
                self.status=status;self.headers=headers or {};self.body=body
            def getheader(self,name,default=''):
                return self.headers.get(name,default)
            def read(self,limit):return self.body[:limit]
        class Connection(object):
            def close(self):pass
        class Adapter(object):
            def __init__(self):self.calls=[]
            def _pinned_open(inner,parsed,body,headers,timeout,method,
                             endpoint_path):
                inner.calls.append((parsed.geturl(),method,endpoint_path))
                if len(inner.calls)==1:
                    return Connection(),Response(301,{'Location':
                      'https://www.siliconflow.cn/pricing'})
                return Connection(),Response(200,{'Content-Type':
                  'text/html; charset=utf-8'},page)
        adapter=Adapter();result=gate.fetch_pricing(adapter,10)
        self.assertEqual(adapter.calls,[('https://siliconflow.cn/pricing',
          'GET',''),('https://www.siliconflow.cn/pricing','GET','')])
        self.assertEqual(result['status_chain'],[301,200])
        self.assertEqual(result['final_source_uri'],
                         'https://www.siliconflow.cn/pricing')
        self.assertEqual((result['prompt_price'],result['completion_price']),
                         ('0','0'))

    def test_pricing_redirect_rejects_nonofficial_downgrade_private_and_loop(self):
        class Response(object):
            status=301
            def __init__(self,location):self.location=location
            def getheader(self,name,default=''):
                return self.location if name=='Location' else default
        class Connection(object):
            def close(self):pass
        for location,error in (
          ('https://example.com/pricing','OFFICIAL_HOST_REQUIRED'),
          ('http://www.siliconflow.cn/pricing','HTTPS_REQUIRED'),
          ('https://127.0.0.1/pricing','PRIVATE_TARGET')):
            class Adapter(object):
                def _pinned_open(self,*args,**kwargs):
                    return Connection(),Response(location)
            with self.assertRaisesRegex(ValueError,error):
                gate.fetch_pricing(Adapter(),10)
        class LoopAdapter(object):
            def _pinned_open(self,*args,**kwargs):
                return Connection(),Response('https://siliconflow.cn/pricing')
        with self.assertRaisesRegex(ValueError,'REDIRECT_LOOP'):
            gate.fetch_pricing(LoopAdapter(),10)

    def test_connection_id_resolves_real_provider_without_rebinding(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.executescript('''
          CREATE TABLE service_connections(tenant_id TEXT,connection_id TEXT,
            provider_id TEXT,status TEXT,purpose TEXT);
          CREATE TABLE provider_onboarding_configs(tenant_id TEXT,
            connection_id TEXT,model_id TEXT);
          CREATE TABLE model_providers(tenant_id TEXT,provider_id TEXT,
            base_url TEXT,timeout_seconds REAL,retry_limit INTEGER,enabled INTEGER);
          CREATE TABLE model_benchmark_cases(tenant_id TEXT,suite_version TEXT,
            case_id TEXT,capability TEXT,messages_json TEXT,expected_contains TEXT);
          CREATE TABLE model_call_attempts(tenant_id TEXT,provider_id TEXT,
            model_id TEXT,worker_id TEXT);
          CREATE TABLE model_evaluations(tenant_id TEXT,evaluation_id TEXT,
            provider_id TEXT,model_id TEXT,suite_version TEXT,state TEXT,
            quality_score REAL,observed_at REAL);
          CREATE TABLE model_quota_status(tenant_id TEXT,provider_id TEXT,
            quota_state TEXT,quota_source TEXT,verified_at REAL,
            unavailable_reason TEXT);
          INSERT INTO service_connections VALUES('tenant-a',
            'siliconflow-siliconflow-default','siliconflow','ACTIVE',
            'MODEL_INFERENCE');
          INSERT INTO provider_onboarding_configs VALUES('tenant-a',
            'siliconflow-siliconflow-default','Qwen/Qwen2.5-7B-Instruct');
          INSERT INTO model_providers VALUES('tenant-a','siliconflow',
            'https://api.siliconflow.cn',10,0,1);
        ''')
        calls=[]
        class Control(object):
            tenant_id='tenant-a'
            def __init__(self):self.db=db
            def provider_secret(self,provider_id):
                calls.append(('secret',provider_id));return 'redacted-fixture'
            def record_free_model_preflight(self,provider_id,*args,**kwargs):
                calls.append(('preflight',provider_id))
            def register_benchmark_suite(self,version,cases):
                case=cases[0];db.execute('INSERT INTO model_benchmark_cases VALUES '
                  '(?,?,?,?,?,?)',('tenant-a',version,case['case_id'],
                  case['capability'],json.dumps(case['messages'],sort_keys=True,
                  separators=(',',':')),case['expected_contains']));db.commit()
            def run_benchmark(self,provider_id,model_id,suite_version,**kwargs):
                calls.append(('benchmark',provider_id,kwargs['allow_paid'],
                              kwargs['allow_unverified_free_probe']))
                db.execute('INSERT INTO model_call_attempts VALUES (?,?,?,?)',
                  ('tenant-a',provider_id,model_id,'benchmark:'+suite_version))
                db.execute('INSERT INTO model_evaluations VALUES (?,?,?,?,?,?,?,?)',
                  ('tenant-a','evaluation-1',provider_id,model_id,suite_version,
                   'QUALIFIED',1.0,kwargs['now']))
                db.execute('INSERT INTO model_quota_status VALUES (?,?,?,?,?,?)',
                  ('tenant-a',provider_id,'AVAILABLE',
                   'REAL_BENCHMARK_CALL_SUCCEEDED_NOT_BALANCE:'+suite_version,
                   kwargs['now'],None));db.commit()
                return {'state':'QUALIFIED'}
        class Adapter(object):
            def list_models(self,base_url,secret,timeout):
                return ['Qwen/Qwen2.5-7B-Instruct']
        pricing={'source_sha256':'a'*64,'source_uri':gate.PRICING_URL}
        try:
            with mock.patch.object(gate,'fetch_pricing',return_value=pricing):
                result=gate.run_gate(Control(),Adapter(),1000)
            self.assertEqual(result['connection_id'],
                             'siliconflow-siliconflow-default')
            self.assertEqual(result['provider_id'],'siliconflow')
            self.assertIn(('secret','siliconflow'),calls)
            self.assertIn(('benchmark','siliconflow',False,True),calls)
        finally:db.close()


if __name__=='__main__':unittest.main()

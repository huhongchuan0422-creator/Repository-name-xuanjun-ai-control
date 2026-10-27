#!/usr/bin/env python3
"""One-call zero-price admission gate for the existing MCP model worker.

This helper is intentionally not an HTTP endpoint.  It runs under the existing
service identity while the service is stopped, reuses the canonical database
and encrypted provider credential, and emits only redacted evidence.
"""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0,os.path.dirname(__file__))
from model_orchestration import (ModelControl, SiliconFlowAdapter,
                                 load_master_key)
from reusable_task_gateway import GatewayKernel, TestTenantAuthority, canonical
from secure_file_input import read_owned_secret_file
from task_supervisor import Supervisor


CONNECTION_ID='siliconflow-siliconflow-default'
MODEL_ID='Qwen/Qwen2.5-7B-Instruct'
PRICING_URL='https://siliconflow.cn/pricing'
SUITE_VERSION='owner-mcp-classification-20261027-v1'


def parse_zero_price_page(raw):
    """Return exact free-model evidence from the current official page."""
    if not isinstance(raw,bytes) or not raw or len(raw)>2*1024*1024:
        raise ValueError('PRICING_BODY_BOUNDS')
    text=raw.decode('utf-8')
    marker='\\"modelName\\":\\"'+MODEL_ID+'\\"'
    if marker not in text:
        raise ValueError('EXACT_MODEL_PRICE_RECORD_REQUIRED')
    required=(
      '\\"price\\":\\"0\\"',
      '\\"DisplayName\\":\\"Qwen2.5-7B-Instruct (Free)\\"',
      '\\"currency\\":\\"¥\\"',
      '\\"priceUnit\\":\\"/ M Tokens\\"',
      '\\"status\\":\\"normal\\"',
      '\\"type\\":\\"text\\"',
      '\\"subType\\":\\"chat\\"',
      '\\"targetModelName\\":\\"'+MODEL_ID+'\\"',
      '\\"onlyByChargeBalance\\":false')
    separator='\\n';candidates=[];position=0
    while True:
        position=text.find(marker,position)
        if position<0:break
        start=text.rfind(separator,0,position)+len(separator)
        end=text.find(separator,position)
        line=text[start:] if end<0 else text[start:end]
        if (re.match(r'^[0-9a-f]+:\{',line) and
                all(value in line for value in required)):
            candidates.append(line)
        position+=len(marker)
    if len(set(candidates))!=1:
        raise ValueError('EXACT_FREE_MODEL_FIELDS_REQUIRED')
    line=candidates[0]
    match=re.search(r'\\"pricing\\":\\"\$([0-9a-f]+)\\"',line)
    if match is None:raise ValueError('PRICING_REFERENCE_REQUIRED')
    collection=re.search(r'(?:^|\\n)'+re.escape(match.group(1))+
      r':\[(.*?)\](?:\\n|$)',text)
    if collection is None:raise ValueError('PRICING_COLLECTION_REQUIRED')
    references=re.findall(r'\\"\$([0-9a-f]+)\\"',collection.group(1))
    prices={}
    for reference in references:
        item=re.search(r'(?:^|\\n)'+re.escape(reference)+
          r':\{(.*?)\}(?:\\n|$)',text)
        if item is None:continue
        specification=re.search(r'\\"specification\\":\\"([^\"]+)\\"',
                                item.group(1))
        price=re.search(r'\\"price\\":\\"([^\"]+)\\"',item.group(1))
        if specification is not None and price is not None:
            prices[specification.group(1)]=price.group(1)
    if prices.get('prompt')!='0' or prices.get('completion')!='0':
        raise ValueError('ZERO_PROMPT_AND_COMPLETION_PRICE_REQUIRED')
    return {'model_id':MODEL_ID,'display_name':'Qwen2.5-7B-Instruct (Free)',
      'status':'normal','type':'text','sub_type':'chat','prompt_price':'0',
      'completion_price':'0','unit':'/ M Tokens','currency':'CNY',
      'only_by_charge_balance':False,'source_uri':PRICING_URL,
      'source_sha256':hashlib.sha256(raw).hexdigest()}


def fetch_pricing(adapter,timeout):
    parsed=urlparse(PRICING_URL);headers={'Accept':'text/html',
      'User-Agent':'Xuanjun-TEST-ONLY-Pricing-Verification'}
    connection=None
    try:
        connection,response=adapter._pinned_open(parsed,None,headers,timeout,
          method='GET',endpoint_path='')
        content_type=response.getheader('Content-Type','').lower()
        if response.status!=200:raise ValueError('PRICING_HTTP_STATUS')
        if 'text/html' not in content_type:raise ValueError('PRICING_CONTENT_TYPE')
        raw=response.read(2*1024*1024+1)
    finally:
        if connection is not None:connection.close()
    return parse_zero_price_page(raw)


def registered_suite(control):
    rows=list(control.db.execute('''SELECT case_id,capability,messages_json,
      expected_contains FROM model_benchmark_cases WHERE tenant_id=? AND
      suite_version=? ORDER BY case_id''',(control.tenant_id,SUITE_VERSION)))
    expected=[('classification','general',canonical([{'role':'system',
      'content':'Classify the fixed public test text. Reply with exactly SAFE_TEXT.'},
      {'role':'user','content':'A public weather note with no sensitive data and no action request.'}]),
      'SAFE_TEXT')]
    if not rows:
        control.register_benchmark_suite(SUITE_VERSION,[{'case_id':'classification',
          'capability':'general','messages':json.loads(expected[0][2]),
          'expected_contains':'SAFE_TEXT'}])
        return
    if [tuple(row) for row in rows]!=expected:
        raise ValueError('BENCHMARK_SUITE_DRIFT')


def existing_probe(control,provider_id):
    attempted=control.db.execute('''SELECT COUNT(*) FROM model_call_attempts
      WHERE tenant_id=? AND provider_id=? AND model_id=? AND worker_id=?''',(
      control.tenant_id,provider_id,MODEL_ID,'benchmark:'+SUITE_VERSION)).fetchone()[0]
    evaluation=control.db.execute('''SELECT evaluation_id,state,quality_score,
      observed_at FROM model_evaluations WHERE tenant_id=? AND provider_id=?
      AND model_id=? AND suite_version=? ORDER BY observed_at DESC LIMIT 1''',(
      control.tenant_id,provider_id,MODEL_ID,SUITE_VERSION)).fetchone()
    quota=control.db.execute('''SELECT quota_state,quota_source,verified_at,
      unavailable_reason FROM model_quota_status WHERE tenant_id=? AND
      provider_id=?''',(control.tenant_id,provider_id)).fetchone()
    return attempted,(dict(evaluation) if evaluation else None),(
      dict(quota) if quota else None)


def run_gate(control,adapter,now):
    pricing=fetch_pricing(adapter,10)
    binding=control.db.execute('''SELECT c.provider_id,c.status,c.purpose,
      o.model_id FROM service_connections c JOIN provider_onboarding_configs o
      ON o.tenant_id=c.tenant_id AND o.connection_id=c.connection_id WHERE
      c.tenant_id=? AND c.connection_id=?''',(control.tenant_id,
      CONNECTION_ID)).fetchone()
    if (binding is None or binding['status']!='ACTIVE' or
            binding['purpose']!='MODEL_INFERENCE' or
            binding['model_id']!=MODEL_ID):
        raise ValueError('EXACT_ACTIVE_CONNECTION_BINDING_REQUIRED')
    provider_id=binding['provider_id']
    provider=control.db.execute('''SELECT base_url,timeout_seconds,retry_limit
      FROM model_providers WHERE tenant_id=? AND provider_id=? AND enabled=1''',(
      control.tenant_id,provider_id)).fetchone()
    if provider is None:raise ValueError('ACTIVE_PROVIDER_REQUIRED')
    if provider['retry_limit']!=0:raise ValueError('ZERO_RETRY_PROVIDER_REQUIRED')
    models=adapter.list_models(provider['base_url'],control.provider_secret(
      provider_id),provider['timeout_seconds'])
    if MODEL_ID not in models:raise ValueError('EXACT_MODEL_NOT_VISIBLE')
    attempted,evaluation,quota=existing_probe(control,provider_id)
    if attempted:
        qualified=(attempted==1 and evaluation is not None and
          evaluation['state']=='QUALIFIED' and quota is not None and
          quota['quota_state']=='AVAILABLE' and
          quota['quota_source']==
          'REAL_BENCHMARK_CALL_SUCCEEDED_NOT_BALANCE:'+SUITE_VERSION)
        return {'state':'QUALIFIED_REUSED' if qualified else 'HOLD_NO_RETRY',
          'connection_id':CONNECTION_ID,'provider_id':provider_id,
          'model_id':MODEL_ID,
          'pricing':pricing,'model_visible':True,'model_count':len(models),
          'attempt_count':attempted,'evaluation':evaluation,'quota':quota,
          'quota_balance':'NOT_ASSERTED','external_calls_this_run':0}
    control.record_free_model_preflight(provider_id,MODEL_ID,PRICING_URL,
      pricing['source_sha256'],now,now,now=now)
    registered_suite(control)
    result=control.run_benchmark(provider_id,MODEL_ID,SUITE_VERSION,
      adapter=adapter,allow_paid=False,now=now,
      allow_unverified_free_probe=True)
    attempted,evaluation,quota=existing_probe(control,provider_id)
    return {'state':result['state'],'connection_id':CONNECTION_ID,
      'provider_id':provider_id,
      'model_id':MODEL_ID,'pricing':pricing,'model_visible':True,
      'model_count':len(models),'attempt_count':attempted,
      'evaluation':evaluation,'quota':quota,'quota_balance':'NOT_ASSERTED',
      'external_calls_this_run':1,'automatic_retry':False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--authority-key-file',required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--principal',required=True)
    parser.add_argument('--model-master-key-file',required=True)
    args=parser.parse_args(argv)
    raw_key=read_owned_secret_file(args.authority_key_file,
      'TEST_AUTHORITY_KEY').rstrip('\r\n')
    supervisor=Supervisor(os.path.realpath(args.db))
    try:
        authority=TestTenantAuthority(raw_key.encode('utf-8'))
        gateway=GatewayKernel(supervisor,authority)
        control=ModelControl(gateway,authority.issue(args.tenant,
          'admin:'+args.principal),load_master_key(args.model_master_key_file))
        result=run_gate(control,SiliconFlowAdapter(),time.time())
        print(json.dumps(result,sort_keys=True,separators=(',',':')))
        return 0 if result['state'] in ('QUALIFIED','QUALIFIED_REUSED') else 12
    finally:supervisor.close()


if __name__=='__main__':raise SystemExit(main())

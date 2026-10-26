"""Simple, server-controlled API provider onboarding.

The browser selects a platform and supplies a credential.  Destinations,
adapter types and authentication details stay server presets.  A successful
model-catalogue GET proves authentication only; it is not an inference, quota
or pricing attestation.
"""
from __future__ import print_function

import base64
import hashlib
import hmac
import json
import re
import sqlite3
import time

from connection_management import ConnectionManager
from model_orchestration import (OpenAICompatibleAdapter, SiliconFlowAdapter,
                                 ProviderError)
from task_supervisor import canonical


PRESETS={
  'siliconflow':{
    'label':'硅基流动','provider_id':'siliconflow','adapter_type':'siliconflow',
    'base_url':'https://api.siliconflow.cn','auth_type':'API_KEY',
    'extra_field':None,'timeout_seconds':10,
    'free_default_model':'Qwen/Qwen2.5-7B-Instruct'},
  'openai':{
    'label':'OpenAI API','provider_id':'openai','adapter_type':'openai-compatible',
    'base_url':'https://api.openai.com','auth_type':'API_KEY',
    'extra_field':None,'timeout_seconds':10},
  'deepseek':{
    'label':'DeepSeek API','provider_id':'deepseek','adapter_type':'openai-compatible',
    'base_url':'https://api.deepseek.com','auth_type':'API_KEY',
    'extra_field':None,'timeout_seconds':10},
  'bailian':{
    'label':'阿里云百炼（兼容模式）','provider_id':'bailian',
    'adapter_type':'openai-compatible',
    'base_url':'https://dashscope.aliyuncs.com/compatible-mode',
    'auth_type':'API_KEY','extra_field':None,'timeout_seconds':10},
}

DISPLAY_ONLY={
  'chatgpt':{'label':'ChatGPT 登录（暂未接通）',
    'auth_type':'OAUTH','extra_field':None,'availability':'UNSUPPORTED'},
}


ERROR_ZH={
  'AUTH':'API Key 无效或无权读取模型目录',
  'RATE_LIMIT':'平台限流，请稍后重试；配置尚未保存',
  'TIMEOUT':'连接平台超时；配置尚未保存',
  'DNS':'平台域名解析失败；配置尚未保存',
  'UNSAFE_DESTINATION':'目标地址未通过安全检查',
  'PROTOCOL':'平台返回格式不受支持',
  'TRANSPORT':'连接平台失败；配置尚未保存',
  'HTTP':'平台服务返回错误；配置尚未保存',
}


def public_presets():
    values=[{'platform':key,'label':value['label'],
      'auth_type':value['auth_type'],'extra_field':value['extra_field'],
      'free_default_model':value.get('free_default_model'),
      'availability':'SUPPORTED'} for key,value in sorted(PRESETS.items())]
    values.extend({'platform':key,'label':value['label'],
      'auth_type':value['auth_type'],'extra_field':value['extra_field'],
      'availability':value['availability']}
      for key,value in sorted(DISPLAY_ONLY.items()))
    return values


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS provider_onboarding_call_tests(
      tenant_id TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
      state TEXT NOT NULL, started_at REAL NOT NULL,
      PRIMARY KEY(tenant_id,receipt_sha256))''')
    db.execute('''CREATE TABLE IF NOT EXISTS provider_onboarding_configs(
      tenant_id TEXT NOT NULL, platform TEXT NOT NULL,
      connection_id TEXT NOT NULL, connection_name TEXT,
      model_id TEXT NOT NULL, auth_state TEXT NOT NULL,
      catalog_state TEXT NOT NULL, model_callable_state TEXT NOT NULL,
      tested_model_id TEXT, models_json TEXT NOT NULL,
      secret_mask TEXT, updated_at REAL NOT NULL,
      PRIMARY KEY(tenant_id,platform))''')
    db.commit()


def projection(db,tenant_id):
    actual={row[0] for row in db.execute(
      "SELECT name FROM sqlite_master WHERE type='table'")}
    if 'provider_onboarding_configs' not in actual:return []
    result=[]
    for row in db.execute('''SELECT platform,connection_id,connection_name,
      model_id,auth_state,catalog_state,model_callable_state,tested_model_id,
      models_json,secret_mask,updated_at FROM provider_onboarding_configs
      WHERE tenant_id=? ORDER BY platform''',(tenant_id,)):
        item=dict(row);item['models']=json.loads(item.pop('models_json'))
        result.append(item)
    return result


def saved_credential(control,master_key,platform,name=None):
    value=preset(platform);cid=connection_id(platform,name)
    manager=ConnectionManager(control.gateway,control.context,master_key)
    secret,version=manager.credential(cid,value['base_url'],'MODEL_INFERENCE')
    return secret,cid,version


def preset(platform):
    value=PRESETS.get(platform)
    if value is None:raise ValueError('SUPPORTED_PLATFORM_REQUIRED')
    return value


def _credential(value):
    if (not isinstance(value,str) or len(value)<8 or '\n' in value or
            '\r' in value):raise ValueError('VALID_API_KEY_REQUIRED')
    return value


def _adapter(value, override=None):
    if override is not None:return override
    return (SiliconFlowAdapter() if value['adapter_type']=='siliconflow'
            else OpenAICompatibleAdapter())


def test_connection(platform,credential,adapter=None):
    value=preset(platform);secret=_credential(credential)
    try:models=_adapter(value,adapter).list_models(value['base_url'],secret,
                                                    value['timeout_seconds'])
    except ProviderError as exc:
        raise ValueError('CONNECTION_TEST_%s:%s'%(exc.kind,
          ERROR_ZH.get(exc.kind,'连接测试失败；配置尚未保存')))
    return {'platform':platform,'auth_state':'SUCCEEDED',
      'catalog_state':'RETRIEVED','model_callable_state':'UNVERIFIED_NO_INFERENCE',
      'models':models,'message_zh':'鉴权成功并已读取模型；尚未执行付费推理'}


def issue_receipt(master_key,tenant_id,platform,credential,models,now=None):
    now=time.time() if now is None else now
    body={'tenant_id':tenant_id,'platform':platform,
      'credential_sha256':hashlib.sha256(_credential(credential).encode()).hexdigest(),
      'models':sorted(set(models)),'expires_at':int(now+600)}
    encoded=base64.urlsafe_b64encode(canonical(body).encode()).decode().rstrip('=')
    signature=hmac.new(master_key,encoded.encode(),hashlib.sha256).hexdigest()
    return encoded+'.'+signature


def verify_receipt(master_key,tenant_id,platform,credential,model_id,token,
                   now=None):
    now=time.time() if now is None else now
    try:
        encoded,signature=token.split('.',1)
        expected=hmac.new(master_key,encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):raise ValueError()
        padded=encoded+'='*((4-len(encoded)%4)%4)
        body=json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:raise ValueError('CONNECTION_TEST_RECEIPT_INVALID')
    if (body.get('tenant_id')!=tenant_id or body.get('platform')!=platform or
        body.get('credential_sha256')!=hashlib.sha256(
          _credential(credential).encode()).hexdigest() or
        type(body.get('expires_at')) is not int or now>=body['expires_at'] or
        model_id not in body.get('models',[])):
        raise ValueError('CONNECTION_TEST_RECEIPT_MISMATCH_OR_EXPIRED')
    return body


def test_model(control,master_key,tenant_id,platform,credential,model_id,
               catalogue_receipt,confirmed,adapter=None,now=None):
    if confirmed is not True:raise ValueError('PAID_TEST_CONFIRMATION_REQUIRED')
    verify_receipt(master_key,tenant_id,platform,credential,model_id,
                   catalogue_receipt,now=now)
    receipt_sha=hashlib.sha256(catalogue_receipt.encode()).hexdigest()
    ensure_schema(control.gateway.supervisor.db)
    try:
        control.gateway.supervisor.db.execute('BEGIN IMMEDIATE')
        control.gateway.supervisor.db.execute('''INSERT INTO
          provider_onboarding_call_tests(tenant_id,receipt_sha256,state,started_at)
          VALUES(?,?,?,?)''',(tenant_id,receipt_sha,'CLAIMED',
          time.time() if now is None else now))
        control.gateway.supervisor.db.commit()
    except sqlite3.IntegrityError:
        control.gateway.supervisor.db.rollback()
        raise ValueError('MODEL_TEST_RECEIPT_ALREADY_USED')
    except Exception:
        control.gateway.supervisor.db.rollback();raise
    value=preset(platform);secret=_credential(credential)
    try:
        result=_adapter(value,adapter).invoke(value['base_url'],secret,model_id,
          [{'role':'user','content':'Reply exactly OK.'}],
          value['timeout_seconds'],max_output_tokens=2)
    except ProviderError as exc:
        control.gateway.supervisor.db.execute('''UPDATE provider_onboarding_call_tests
          SET state=? WHERE tenant_id=? AND receipt_sha256=?''',
          ('FAILED',tenant_id,receipt_sha));control.gateway.supervisor.db.commit()
        raise ValueError('MODEL_TEST_%s:%s'%(exc.kind,
          ERROR_ZH.get(exc.kind,'模型调用测试失败')))
    usage=result.get('usage') or {};fields=('input_tokens','output_tokens','total_tokens')
    present=[usage.get(x) is not None for x in fields]
    usage_state='KNOWN' if all(present) else ('PARTIAL' if any(present) else 'UNKNOWN')
    at=time.time() if now is None else now
    body={'kind':'MODEL_CALL','tenant_id':tenant_id,'platform':platform,
      'credential_sha256':hashlib.sha256(secret.encode()).hexdigest(),
      'model_id':model_id,'expires_at':int(at+600)}
    encoded=base64.urlsafe_b64encode(canonical(body).encode()).decode().rstrip('=')
    signature=hmac.new(master_key,encoded.encode(),hashlib.sha256).hexdigest()
    control.gateway.supervisor.db.execute('''UPDATE provider_onboarding_call_tests
      SET state=? WHERE tenant_id=? AND receipt_sha256=?''',
      ('SUCCEEDED',tenant_id,receipt_sha));control.gateway.supervisor.db.commit()
    return {'model_callable_state':'TESTED_SUCCEEDED','usage_state':usage_state,
      'usage':usage,'provider_request_id':result.get('provider_request_id','UNKNOWN'),
      'call_receipt':encoded+'.'+signature,
      'message_zh':'模型真实调用成功；本次最多一次请求、最多2个输出token'}


def verify_call_receipt(master_key,tenant_id,platform,credential,model_id,token,
                        now=None):
    now=time.time() if now is None else now
    try:
        encoded,signature=token.split('.',1)
        expected=hmac.new(master_key,encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature,expected):raise ValueError()
        padded=encoded+'='*((4-len(encoded)%4)%4)
        body=json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:raise ValueError('MODEL_CALL_RECEIPT_INVALID')
    if (body.get('kind')!='MODEL_CALL' or body.get('tenant_id')!=tenant_id or
        body.get('platform')!=platform or body.get('model_id')!=model_id or
        body.get('credential_sha256')!=hashlib.sha256(
          _credential(credential).encode()).hexdigest() or
        type(body.get('expires_at')) is not int or now>=body['expires_at']):
        raise ValueError('MODEL_CALL_RECEIPT_MISMATCH_OR_EXPIRED')
    return body


def connection_id(platform,name):
    if name is None or not str(name).strip():name=platform+'-default'
    slug=re.sub(r'[^a-z0-9-]+','-',str(name).strip().lower()).strip('-')
    if not slug:slug=platform+'-default'
    return (platform+'-'+slug)[:96]


def save(control,master_key,platform,name,credential,model_id,receipt,
         call_receipt=None):
    value=preset(platform);ensure_schema(control.gateway.supervisor.db)
    existing=control.gateway.supervisor.db.execute('''SELECT * FROM
      provider_onboarding_configs WHERE tenant_id=? AND platform=?''',(
      control.tenant_id,platform)).fetchone()
    if receipt:
        receipt_body=verify_receipt(master_key,control.tenant_id,platform,
          credential,model_id,receipt)
        models=receipt_body['models']
    else:
        if existing is None:raise ValueError('CONNECTION_TEST_REQUIRED_FOR_FIRST_SAVE')
        models=json.loads(existing['models_json'])
        if model_id not in models:raise ValueError('MODEL_NOT_IN_SAVED_CATALOG')
    callable_state='UNVERIFIED_NO_INFERENCE'
    if call_receipt:
        verify_call_receipt(master_key,control.tenant_id,platform,credential,
                            model_id,call_receipt)
        callable_state='TESTED_SUCCEEDED'
    elif (existing is not None and existing['model_id']==model_id and
          existing['tested_model_id']==model_id and
          existing['model_callable_state']=='TESTED_SUCCEEDED'):
        callable_state='TESTED_SUCCEEDED'
    cid=connection_id(platform,name);provider_id=value['provider_id']
    provider=control.upsert_provider({'provider_id':provider_id,
      'display_name':value['label'],'adapter_type':value['adapter_type'],
      'base_url':value['base_url'],'enabled':True,'price_state':'UNKNOWN',
      'rate_limit_per_min':10,'concurrency_limit':2,
      'timeout_seconds':value['timeout_seconds'],'retry_limit':0},credential)
    manager=ConnectionManager(control.gateway,control.context,master_key)
    connection=manager.upsert({'connection_id':cid,'provider_id':provider_id,
      'purpose':'MODEL_INFERENCE','auth_type':'API_KEY',
      'destination_origin':value['base_url'],'issuer':None,
      'authorization_endpoint':None,'token_endpoint':None,
      'revocation_endpoint':None,'redirect_uri':None,'client_id':None,
      'scopes':[],'supports_refresh':False},credential)
    model=control.upsert_model({'provider_id':provider_id,'model_id':model_id,
      'capabilities':['general'],'enabled':True,'price_state':'UNKNOWN',
      'input_unit_cost':None,'output_unit_cost':None})
    tested_model=model_id if callable_state=='TESTED_SUCCEEDED' else None
    control.gateway.supervisor.db.execute('''INSERT OR REPLACE INTO
      provider_onboarding_configs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(
      control.tenant_id,platform,cid,name,model_id,'SUCCEEDED','RETRIEVED',
      callable_state,tested_model,canonical(models),connection['secret_mask'],
      time.time()))
    control.gateway.supervisor.db.commit()
    return {'configuration_state':'SAVED','auth_state':'SUCCEEDED',
      'model_catalog_state':'SAVED','model_callable_state':callable_state,
      'provider_id':provider['provider_id'],'connection_id':cid,
      'connection_config_version':connection['config_version'],
      'model_id':model['model_id'],'secret_mask':connection['secret_mask'],
      'quota_state':'UNKNOWN','paid_inference':'NOT_EXECUTED',
      'message_zh':'配置已保存；鉴权成功；模型尚未执行推理，费用和额度未核验'}

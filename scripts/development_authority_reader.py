#!/usr/bin/env python3
"""Executable fail-closed reader: only verified authorization exits zero."""
import argparse, json, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from development_authority import (SQLiteReplayGuard,load_public_key,verify_envelope)
from secure_file_input import read_owned_secret_file

REJECT=69

def read(config,task_id,request_id,now=None):
    required={'url','bearer_token_file','public_key_file','replay_db','anchor_id',
      'issuer','instance_id','version','service_id','attempt_id','lease_id','fence',
      'epoch','resource_scope_digest','max_age'}
    if not isinstance(config,dict) or set(config)!=required: raise ValueError('EXACT_READER_CONFIG_REQUIRED')
    query=urlencode({'task_id':task_id,'request_id':request_id})
    token=read_owned_secret_file(config['bearer_token_file'],'AUTHORITY_READER_TOKEN').strip()
    request=Request(config['url']+'?'+query,headers={'Authorization':'Bearer '+token,
      'X-Xuanjun-Service-Identity':config['service_id']})
    with urlopen(request,timeout=5) as response:
        if response.status != 200: raise ValueError('AUTHORITY_HTTP_REJECTED')
        envelope=json.loads(response.read().decode('utf-8'))
    public=load_public_key(read_owned_secret_file(config['public_key_file'],
      'AUTHORITY_PUBLIC_KEY').encode('ascii'))
    expected={key:config[key] for key in ('issuer','instance_id','version','service_id',
      'attempt_id','lease_id','fence','epoch','resource_scope_digest','max_age')}
    expected.update(task_id=task_id,request_id=request_id,now=time.time() if now is None else now)
    guard=SQLiteReplayGuard(config['replay_db'])
    try: return verify_envelope(envelope,public,{'anchor_id':config['anchor_id']},expected,guard)
    finally: guard.close()

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--config-file',required=True)
    p.add_argument('--task-id',required=True); p.add_argument('--request-id',required=True); a=p.parse_args(argv)
    try:
        config=json.loads(read_owned_secret_file(a.config_file,'AUTHORITY_READER_CONFIG'))
        value=read(config,a.task_id,a.request_id)
        if value.get('authority',{}).get('authorized') is not True: return REJECT
        print(json.dumps(value,sort_keys=True)); return 0
    except Exception as exc:
        print(json.dumps({'authorized':False,'error':str(exc)},sort_keys=True)); return REJECT

if __name__=='__main__': raise SystemExit(main())

import base64
import concurrent.futures
import datetime
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
CN = 'acs:ram::1384884686754410:role/xuanjun-automation'
HOSTS = (('tokyo', CN, 'ap-northeast-1', '68985c531add4e90a131aef703a389e6', 'iZ6wee8q9z4t03hvqumwfhZ'),)

class Hold(Exception):
    pass

def safe(value):
    return value if isinstance(value, str) and re.fullmatch('[A-Za-z0-9_.:-]{1,180}', value) else 'DETAIL_WITHHELD'

def quote(value):
    return urllib.parse.quote(str(value), safe='~')

class NoRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def rpc(endpoint, version, action, credentials, **params):
    if endpoint not in {'sts.aliyuncs.com'} | {'swas.' + h[2] + '.aliyuncs.com' for h in HOSTS}:
        raise Hold('ENDPOINT_REJECTED')
    key, secret, token = credentials
    values = dict(params, Action=action, Version=version, Format='JSON', AccessKeyId=key, SignatureMethod='HMAC-SHA1', SignatureVersion='1.0', SignatureNonce=uuid.uuid4().hex, Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    if token:
        values['SecurityToken'] = token
    canonical = '&'.join((quote(k) + '=' + quote(v) for k, v in sorted(values.items())))
    signature = hmac.new((secret + '&').encode(), ('POST&%2F&' + quote(canonical)).encode(), hashlib.sha1).digest()
    values['Signature'] = base64.b64encode(signature).decode()
    request = urllib.request.Request('https://' + endpoint + '/', data=urllib.parse.urlencode(values).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(262145)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read(262145))
            code = safe(data.get('Code'))
        except Exception:
            code = 'HTTP_' + str(error.code)
        raise Hold(code) from None
    except Exception:
        raise Hold('TRANSPORT_RESULT_UNKNOWN') from None
    if len(raw) > 262144:
        raise Hold('RESPONSE_TOO_LARGE')
    try:
        data = json.loads(raw)
    except Exception:
        raise Hold('INVALID_API_RESPONSE') from None
    if not isinstance(data, dict):
        raise Hold('INVALID_API_RESPONSE')
    if 'Code' in data:
        raise Hold(safe(data['Code']))
    return data
import zlib

INVOKE='t-jpn70ewzbz4t62o'
INSTANCE='68985c531add4e90a131aef703a389e6'

def failure_projection(output):
    if type(output) is not str or len(output)>120000:raise Hold('FAILURE_OUTPUT_BOUND')
    try:raw=base64.b64decode(output,validate=True).decode('utf-8','replace')
    except (ValueError,UnicodeError):raw=output
    rows=[]
    for line in raw.splitlines()[-40:]:
        error=re.fullmatch(r'([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?::\s*(.*))?',line)
        if error:
            detail=error.group(2) or ''
            row={'exception':error.group(1)}
            if re.fullmatch('[A-Z0-9_]{1,160}',detail):row['code']=detail
            match=re.search(r'\[Errno ([0-9]{1,4})\]',detail)
            if match:row['errno']=int(match.group(1))
            rows.append(row)
        frame=re.fullmatch(r'\s*File ".*", line ([0-9]{1,8}), in ([A-Za-z0-9_<>]{1,80})',line)
        if frame:rows.append({'line':int(frame.group(1)),'function':frame.group(2)})
        for phrase,code in (('No such file or directory','PATH_NOT_FOUND'),('Permission denied','PERMISSION_DENIED'),
                            ('command not found','COMMAND_NOT_FOUND'),('Operation not permitted','OPERATION_NOT_PERMITTED')):
            if phrase in line:rows.append({'category':code})
    return rows

def self_test():
    assert failure_projection('RuntimeError: SOURCE_NAME_BOUND')==[{'exception':'RuntimeError','code':'SOURCE_NAME_BOUND'}]
    assert failure_projection(base64.b64encode(b'RuntimeError: SOURCE_DRIFT').decode())==[{'exception':'RuntimeError','code':'SOURCE_DRIFT'}]
    for raw in ('ValueError: PRIVATE_SECRET=123','  File "/PRIVATE_SECRET", line 9, in analyze',
                'Traceback PRIVATE_SECRET','PermissionError: [Errno 13] PRIVATE_SECRET'):
        assert 'PRIVATE_SECRET' not in json.dumps(failure_projection(raw))
    print('PR99_FAILURE_QUERY_REDACTION_PASS_SIX_CASES_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':self_test();return
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise Hold('RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-query-error-'+head[:12]:
        raise Hold('EXACT_QUERY_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    value=rpc('sts.aliyuncs.com','2015-04-01','AssumeRole',master,RoleArn=CN,
              RoleSessionName='pr99-error-'+uuid.uuid4().hex[:16],DurationSeconds=900)['Credentials']
    credentials=(value['AccessKeyId'],value['AccessKeySecret'],value['SecurityToken'])
    if not all(type(v) is str and v and '\n' not in v and '\r' not in v for v in credentials):
        raise Hold('CREDENTIAL_RESPONSE_INVALID')
    for v in credentials:print('::add-mask::'+v,flush=True)
    data=rpc('swas.ap-northeast-1.aliyuncs.com','2020-06-01','DescribeInvocationResult',credentials,
             RegionId='ap-northeast-1',InstanceId=INSTANCE,InvokeId=INVOKE)
    detail=data.get('InvocationResult',{})
    if type(detail) is not dict or detail.get('InstanceId')!=INSTANCE or detail.get('InvokeId')!=INVOKE:
        raise Hold('ORIGINAL_RESULT_IDENTITY_UNKNOWN')
    status=detail.get('InvocationStatus')
    if status not in ('Success','Failed','Error','Timeout','Cancelled','Terminated','Invalid','Aborted'):
        raise Hold('ORIGINAL_RESULT_NONTERMINAL_OR_UNKNOWN')
    code=detail.get('ExitCode')
    if type(code) is not int:raise Hold('ORIGINAL_EXIT_UNKNOWN')
    receipt={'scope':'ORIGINAL_FAILED_INVOKE_QUERY_ONLY','invoke_id':INVOKE,'instance_id':INSTANCE,
             'status':status,'exit_code':code,'error_projection':failure_projection(detail.get('Output','')),
             'host_commands':0,'service_actions':0,'database_opened':False,'retry_allowed':False,
             'production_cutover':False,'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    print('PR99_ORIGINAL_FAILURE_QUERY_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)

if __name__=='__main__':
    try:main()
    except Hold as error:
        print('PR99_FAILURE_QUERY_HOLD='+safe(str(error)),flush=True);raise SystemExit(2)

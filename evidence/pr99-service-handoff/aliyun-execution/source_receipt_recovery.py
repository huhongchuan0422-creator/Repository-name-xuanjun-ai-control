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
    if action not in ('AssumeRole','DescribeInvocationResult'):
        raise Hold('QUERY_ONLY_ACTION_REJECTED')
    if action=='DescribeInvocationResult' and params!={'RegionId':'ap-northeast-1','InstanceId':INSTANCE,'InvokeId':INVOKE}:
        raise Hold('QUERY_SCOPE_REJECTED')
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

INVOKE='t-jpn70eyimb7p0xs'
INSTANCE='68985c531add4e90a131aef703a389e6'
EXPECTED='iZ6wee8q9z4t03hvqumwfhZ'

def validate_original_shape(d, expected, nonce):
    import re

    def need(ok):
        if not ok:
            raise ValueError('DATA_INVENTORY_CONTRACT')

    def fields(x, keys):
        need(type(x) is dict and set(x) == set(keys.split()))

    def integer(x, maximum=2 ** 64):
        need(type(x) is int and 0 <= x < maximum)

    def digest(x):
        need(type(x) is str and re.fullmatch('[0-9a-f]{64}', x))

    def filename(x):
        need(type(x) is str and re.fullmatch('[A-Za-z0-9_./-]{1,240}', x) and ('..' not in x.split('/')))
    fields(d, 'hostname nonce observed_at scope source schedulers business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations')
    need(d['hostname'] == expected and d['nonce'] == nonce)
    need(d['scope'] == 'PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY')
    need(type(d['observed_at']) is str and re.fullmatch('[0-9T:.Z-]{19,40}', d['observed_at']))
    for name in ('business_source_imports', 'service_actions', 'business_requests'):
        need(type(d[name]) is int and d[name] == 0)
    need(d['database_opened'] is False and d['canonical_data_assigned'] is False)
    need(d['authoritative_writer'] == d['enforced_fence'] == 'UNKNOWN')
    need(d['limitations'] == ['STATIC_CANDIDATES_NOT_PROVEN_WRITERS', 'DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED', 'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED', 'NO_DRAIN_OR_FENCE_PERFORMED'])
    s = d['source']
    fields(s, 'files bytes manifest_sha256 candidate_files_total omitted_candidate_files candidates parse_errors excluded_links')
    integer(s['files'], 2049)
    integer(s['bytes'], 67108865)
    digest(s['manifest_sha256'])
    for key in ('candidate_files_total', 'omitted_candidate_files', 'excluded_links'):
        integer(s[key], 4097)
    need(s['candidate_files_total'] <= s['files'] and s['omitted_candidate_files'] == max(0, s['candidate_files_total'] - 128))
    need(type(s['candidates']) is list and len(s['candidates']) == min(128, s['candidate_files_total']))
    seen = set()
    for row in s['candidates']:
        fields(row, 'path sha256 calls environment_keys environment_keys_total')
        filename(row['path'])
        need(row['path'].endswith('.py') and row['path'] not in seen)
        seen.add(row['path'])
        digest(row['sha256'])
        fields(row['calls'], 'DB_FACTORY FILE_WRITE MUTATION_CALL')
        for count in row['calls'].values():
            integer(count, 100001)
        need(sum(row['calls'].values()) > 0)
        integer(row['environment_keys_total'], 100001)
        need(type(row['environment_keys']) is list and len(row['environment_keys']) == min(12, row['environment_keys_total']))
        need(row['environment_keys'] == sorted(set(row['environment_keys'])))
        for key in row['environment_keys']:
            need(type(key) is str and re.fullmatch('[A-Z][A-Z0-9_]{1,100}', key))
    need(type(s['parse_errors']) is list and len(s['parse_errors']) <= 32)
    for path in s['parse_errors']:
        filename(path)
    r = d['schedulers']
    fields(r, 'regular_fragments_read excluded_symlinks candidates')
    integer(r['regular_fragments_read'], 2050)
    integer(r['excluded_symlinks'], 100001)
    need(type(r['candidates']) is list and len(r['candidates']) <= 129)
    seen = set()
    for row in r['candidates']:
        fields(row, 'root_slot name sha256 bytes matching_lines')
        integer(row['root_slot'], 5)
        filename(row['name'])
        need('/' not in row['name'])
        need((row['root_slot'], row['name']) not in seen)
        seen.add((row['root_slot'], row['name']))
        digest(row['sha256'])
        integer(row['bytes'], 131073)
        integer(row['matching_lines'], 131073)
    return d

def validate_observation(d, expected, nonce):
    assert type(d) is dict and set(d) == set('hostname nonce observed_at scope source scheduler_evidence business_source_imports database_opened service_actions business_requests canonical_data_assigned authoritative_writer enforced_fence limitations'.split())
    assert d['scope'] == 'PR99_SOURCE_ONLY_STATIC_CANDIDATES_NOT_AUTHORITY'
    assert d['scheduler_evidence'] == 'INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN'
    x = dict(d)
    del x['scheduler_evidence']
    x['scope'] = 'PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY'
    x['schedulers'] = {'regular_fragments_read': 0, 'excluded_symlinks': 0, 'candidates': []}
    validate_original_shape(x, expected, nonce)
    return d

def decode_receipt(output, expected, nonce):
    if type(output) is not str or len(output.encode()) >= 32768:
        raise Hold('SOURCE_WIRE_BOUND')
    try:
        try:
            envelope = output.encode()
            env = json.loads(envelope)
        except ValueError:
            envelope = base64.b64decode(output, validate=True)
            env = json.loads(envelope)
        assert len(envelope) < 23000
        assert type(env) is dict and set(env) == {'encoding', 'bytes', 'sha256', 'payload'}
        assert env['encoding'] == 'PR99_ZLIB_BASE64_V1'
        assert type(env['bytes']) is int and 0 < env['bytes'] <= 110000
        assert type(env['sha256']) is str and re.fullmatch('[0-9a-f]{64}', env['sha256'])
        assert type(env['payload']) is str and len(env['payload']) < 22000
        packed = base64.b64decode(env['payload'], validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, 110001)
        assert decoder.eof and (not decoder.unconsumed_tail) and (not decoder.unused_data)
        assert len(raw) == env['bytes'] and hashlib.sha256(raw).hexdigest() == env['sha256']
        value=json.loads(raw)
        observed_nonce=value.get('nonce') if type(value)is dict else None
        assert type(observed_nonce)is str and re.fullmatch('[0-9a-f]{32}',observed_nonce)
        return validate_observation(value,expected,observed_nonce if nonce is None else nonce)
    except Exception:
        raise Hold('SOURCE_COMPACT_CONTRACT_REJECTED') from None

def self_test():

    def wire(value):
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        return json.dumps({'encoding': 'PR99_ZLIB_BASE64_V1', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'payload': base64.b64encode(zlib.compress(raw, 9)).decode()})
    valid = {'hostname': 'test', 'nonce': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'observed_at': '2026-10-18T12:00:00Z', 'scope': 'PR99_SOURCE_AND_SCHEDULER_INVENTORY_NOT_AUTHORITY', 'source': {'files': 3, 'bytes': 10, 'manifest_sha256': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'candidate_files_total': 1, 'omitted_candidate_files': 0, 'candidates': [{'path': 'database/session.py', 'sha256': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'calls': {'DB_FACTORY': 1, 'FILE_WRITE': 0, 'MUTATION_CALL': 0}, 'environment_keys': ['DATABASE_URL'], 'environment_keys_total': 1}], 'parse_errors': [], 'excluded_links': 0}, 'schedulers': {'regular_fragments_read': 5, 'excluded_symlinks': 2, 'candidates': [{'root_slot': 0, 'name': 'xuanjun-example.service', 'sha256': 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', 'bytes': 30, 'matching_lines': 1}]}, 'business_source_imports': 0, 'database_opened': False, 'service_actions': 0, 'business_requests': 0, 'canonical_data_assigned': False, 'authoritative_writer': 'UNKNOWN', 'enforced_fence': 'UNKNOWN', 'limitations': ['STATIC_CANDIDATES_NOT_PROVEN_WRITERS', 'DYNAMIC_PATHS_AND_IDLE_WRITERS_NOT_RESOLVED', 'EXCLUDED_LINKS_AND_OTHER_NAMESPACES_NOT_COVERED', 'NO_DRAIN_OR_FENCE_PERFORMED']}
    valid.pop('schedulers')
    valid['scope'] = 'PR99_SOURCE_ONLY_STATIC_CANDIDATES_NOT_AUTHORITY'
    valid['scheduler_evidence'] = 'INHERIT_T_JPN70EXLHV86XA8_NO_RESCAN'
    assert decode_receipt(wire(valid), 'test', 'a' * 32) == valid
    assert decode_receipt(base64.b64encode(wire(valid).encode()).decode(), 'test', 'a' * 32) == valid
    mutations = (lambda x: x.update(enforced_fence='PASS'), lambda x: x.update(canonical_data_assigned=True), lambda x: x.update(private='SECRET'), lambda x: x.update(service_actions=True), lambda x: x['source'].update(bytes=True), lambda x: x['source'].update(omitted_candidate_files=99), lambda x: x['source']['candidates'][0].update(source_text='SECRET'), lambda x: x['source']['candidates'][0].update(path='../SECRET.py'), lambda x: x['source']['candidates'][0].update(environment_keys=['SECRET=value']), lambda x: x['source']['candidates'][0]['calls'].update(DB_FACTORY=True), lambda x: x.update(schedulers={'command': 'SECRET'}), lambda x: x.update(scheduler_evidence='FALSE_RECEIPT'), lambda x: x.update(database_opened=True))
    for mutate in mutations:
        bad = json.loads(json.dumps(valid))
        mutate(bad)
        try:
            decode_receipt(wire(bad), 'test', 'a' * 32)
        except Hold:
            pass
        else:
            raise AssertionError('INVALID_DATA_INVENTORY_ACCEPTED')
    for change in (lambda x: x.update(bytes=True), lambda x: x.update(bytes=1), lambda x: x.update(sha256='0' * 64), lambda x: x.update(payload=x['payload'] + 'A'), lambda x: x.update(private='SECRET')):
        bad = json.loads(wire(valid))
        change(bad)
        try:
            decode_receipt(json.dumps(bad), 'test', 'a' * 32)
        except Hold:
            pass
        else:
            raise AssertionError('BAD_COMPRESSED_ENVELOPE_ACCEPTED')
    try:
        decode_receipt('x' * 24576, 'test', 'a' * 32)
    except Hold:
        pass
    else:
        raise AssertionError('OVERSIZE_WIRE_ACCEPTED')
    assert decode_receipt(wire(valid),'test',None)==valid
    bad=json.loads(json.dumps(valid));bad['scope']='PR99_SOURCE_COMPACT_STATIC_CANDIDATES_NOT_AUTHORITY'
    try:decode_receipt(wire(bad),'test',None)
    except Hold:pass
    else:raise AssertionError('OLD_WRONG_SCOPE_ACCEPTED')
    try:rpc('sts.aliyuncs.com','2015-04-01','INVALID_ACTION',('a','b',''))
    except Hold as e:assert str(e)=='QUERY_ONLY_ACTION_REJECTED'
    else:raise AssertionError('MUTATION_ACTION_ALLOWED')
    print('PR99_SOURCE_RECEIPT_QUERY_13_METADATA_6_ENVELOPE_REJECTIONS_SCOPE_AND_QUERY_ONLY_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE') == 'SELF_TEST':
        self_test()
        return
    if os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise Hold('RERUN_FORBIDDEN')
    head = os.environ.get('PR99_HEAD', '')
    if not re.fullmatch('[0-9a-f]{40}', head) or os.environ.get('PR99_LABEL') != 'pr99-source-receipt-' + head[:12]:
        raise Hold('EXACT_QUERY_LABEL_REQUIRED')
    master = (os.environ.get('ALIYUN_ACCESS_KEY_ID', ''), os.environ.get('ALIYUN_ACCESS_KEY_SECRET', ''), '')
    if not all(master[:2]):
        raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    value = rpc('sts.aliyuncs.com', '2015-04-01', 'AssumeRole', master, RoleArn=CN, RoleSessionName='pr99-error-' + uuid.uuid4().hex[:16], DurationSeconds=900)['Credentials']
    credentials = (value['AccessKeyId'], value['AccessKeySecret'], value['SecurityToken'])
    if not all((type(v) is str and v and ('\n' not in v) and ('\r' not in v) for v in credentials)):
        raise Hold('CREDENTIAL_RESPONSE_INVALID')
    for v in credentials:
        print('::add-mask::' + v, flush=True)
    data = rpc('swas.ap-northeast-1.aliyuncs.com', '2020-06-01', 'DescribeInvocationResult', credentials, RegionId='ap-northeast-1', InstanceId=INSTANCE, InvokeId=INVOKE)
    detail = data.get('InvocationResult', {})
    if type(detail) is not dict or detail.get('InstanceId') != INSTANCE or detail.get('InvokeId') != INVOKE:
        raise Hold('ORIGINAL_RESULT_IDENTITY_UNKNOWN')
    status = detail.get('InvocationStatus')
    if status!='Success' or type(detail.get('ExitCode'))is not int or detail['ExitCode']!=0:
        raise Hold('ORIGINAL_COMPACT_RESULT_NOT_SUCCESS')
    value=decode_receipt(detail.get('Output'),EXPECTED,None)
    receipt={'scope':'ORIGINAL_COMPACT_SOURCE_RECEIPT_RECOVERY_QUERY_ONLY','invoke_id':INVOKE,'instance_id':INSTANCE,
        'status':status,'exit_code':0,'receipt':value,'host_commands':0,'service_actions':0,'database_opened':False,
        'retry_allowed':False,'production_cutover':False,'nonce_binding':'EXACT_CLOUD_INSTANCE_AND_INVOKE_ID_LOCAL_CLAIM_NOT_RECOVERED',
        'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    print('PR99_SOURCE_RECEIPT_RECOVERED='+json.dumps(receipt,sort_keys=True),flush=True)

if __name__=='__main__':
    try:main()
    except Hold as error:
        print('PR99_FAILURE_QUERY_HOLD='+safe(str(error)),flush=True);raise SystemExit(2)

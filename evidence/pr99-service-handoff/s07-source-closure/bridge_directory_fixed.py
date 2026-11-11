"""Temporary S07 startup against copies inside new mount/network/PID namespaces.
Applications run as uid/gid65534 inside a copied chroot; no host runtime mounts.
No production service/unit/proxy change. All generated logs/materials stay private.
"""
import ast
import base64
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path,PurePosixPath
import re
import resource
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

KOREA='iZmj7a5kwr75qc1tul4kf9Z'
DOMESTIC='iZvt5t8tlrm8oiZ'
LOCAL=Path('/root/pr99-s07-isolated-start-launch-v4')
ATTEMPT=Path('/var/lib/xuanjun-pr99-s07-isolated-start-v4')
MATERIAL=Path('/var/lib/xuanjun-pr99-s07-private-materials-v1')
TRANSFER_PATH=Path('/root/pr99-s07-domestic-data-launch.FbAIVIap/transfer.py')
TRANSFER_SHA='90b49446307de25820b8190988582a53f05cc093ea97655d567cdf96a275df79'
ORIGINAL_SHA='745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd'
SOURCE_SHA='137a2acea1924b4c62e43abfe6f8689c64450db868c7a216d759a16779c939b4'
TAR_SHA='dee6e24933f6a9b14c12ea0b838099093c40e53dda447360080d382793bc8c8c'
WIRE_SHA='7b0c1dbde63482c10d02ff51081fd1cdee0d3f1c17b1fbd75ffe3b111e40ab4f'
SUPPLEMENT_PINS={'binance_integration/commercial_ledger_adapter.py': 'f28817c29750c6f35a03e34be2a6daafc9e72e814bfcaa507145866f664e2bf1', 'database/models/account_anomaly_events.py': '1f2bf80ec12669e9c16e109d17c3ef8dbcd758418813c9cfa0fe55d48f27c54d', 'database/models/credential_records.py': 'dd065152c3a6471f3be9f52536e2cd93e6dc1c716585f177b7f3b02bb38a7d06', 'database/models/crm_customer_mappings.py': 'fe5c277e51e96b85d8ca31b4fa3cf70b67e8bb8c904408f901a72ee302683f3e', 'database/models/exchange_readiness_v5.py': 'ad6a3d296a3c0a40efa25812a978ef7807ec117e44bb680f95e087a6fb2423ce', 'database/models/execution_requests.py': 'd317539a2a104e32e1781e3157d1ad1e0bb4e8ff38e6164dd1727c1069110116', 'database/models/health_checks.py': '401bc04ccea46f71389a7b5b8ddacd19e9bd68d919d8d234af344d877b30082c', 'database/models/idempotency_records.py': 'c8edf8a28d7dd812450ae7699076fdc9d94759fc3f00c48c268697410509d8b5', 'database/models/market_data.py': 'd94600e2cecf5a647a8c31b119dc12e4eb57bb75491f495d2a9fd2bca0395b8d', 'database/models/orders.py': '7a8b79d5d6e881ad3de964263511d650b5178dc75b36fb82610215187031c1f2', 'database/models/outbound_events.py': '6bd324ccf33057238c45704d425618c6ba3129975cf17aecab5268fd6d1c0001', 'database/models/positions.py': '7be8ab06cd4a1ebc1aa77b1c7014f686a84db86f151ce42adf2fb6c2a3a1bb04', 'database/models/recovery_items.py': '3823441407ca1b27b237c9d8fb77f546c0872f9d21ae1b6bb9f01b6bc5de1244', 'database/models/referral_partner.py': 'eae4102528895161aab531609273f1ead2ecc085e8e69245824fb64c2c1f7be5', 'database/models/risk_events.py': '5fda854896eabee426e9d7a0ec36aac9fcd104af574dba6601c4ae4eb26fd23a', 'database/models/signals.py': '9635affb609c992abae29bdf9ed7f97bc570ed5cd9999aab3b4345ff279a13ce', 'database/models/trading_execution_v4.py': 'c5de63dfdfdbe0f9c2cc9a5c557c6e51518dc30d237443ab1c7fc8dd8c6298ed', 'database/models/trading_integration_snapshots.py': '215a5685cddebce16df604bdcfb9471fbc254053d6ac0c24ea485f915a601bda', 'database/models/verification_results.py': '2c0ac138615f230517e3ba9f2de0325220178cf115fe793c4460e448cf777b19', 'database/models/windows_interaction.py': 'c4ab0ee6c6404ff3ffb93498d894960854f265fdb9d2435261fd0f29d809b2c6', 'database/repositories/anomaly_repository.py': 'cf2299fa7d83d11a6fa3026436761b34bc359cb8f64bf680e056a0bb7d2edd83', 'database/repositories/audit_repository.py': 'f777007abda3df14d07f76abea0339788936e7cb0544cc8c180df146d071bfa6', 'database/repositories/credential_repository.py': '8e133d4b07b0d6698befb2f0c9c98963a2d1156f58fa9e2c2a0fe4879bbf9104', 'database/repositories/crm_mapping_repository.py': '03c36b817602d86905ca29d7af73d516257cf16692da4863ca13789074f69fdc', 'database/repositories/customer_repository.py': '7968dc4b5b4455f90c61f6515469eaf7aabd44cdf5b2f4400e1b1d725f91878b', 'database/repositories/exchange_readiness_repository.py': '4f2b28bcbbdd24aa24ea6eafc8b1790f554e63de372923b9663e746af9225df5', 'database/repositories/execution_request_repository.py': '57124ba963bb262653afca94e377f0a65848f9596a6fa9b12b18dd362554b3bd', 'database/repositories/execution_request_uow.py': 'fc2f84164b0e24f6349e6bd287ad0ff8cd3ff05af558e68cb1517660768b2a93', 'database/repositories/health_repository.py': 'ba243632b3501c9f1e9451de8b28db4fc3fbe258f7cd4ce5f6898af45cd232e2', 'database/repositories/idempotency_repository.py': 'ec918b4986ba060494cea5fc90aa73ef4198b9174596eccae45970e2954225fe', 'database/repositories/operations_repository.py': '66cfaba926edb788ff08482103dafa51fb50578d9fa336ce87473b8aaedde700', 'database/repositories/outbound_repository.py': '7fadc03f35ba3e40f0fb131797597c168001c693db5addee9bc5b42446df6d6e', 'database/repositories/recovery_repository.py': 'a2ce3679568dbc07d4676c20cd4190f59cbee6130911a8755c4892f6ce615b24', 'database/repositories/referral_partner_repository.py': '7445f12792a4bed3ad88bf13f58430dae4e71e037c9a4d77f1cb040b0a3cc510', 'database/repositories/trading_execution_repository.py': 'ffb13d6db3ae54d1f765cf6920161cc6f081be15e16d51ee72d4e722f4cbc21d', 'database/repositories/trading_integration_repository.py': 'a50594a6c417ab5699a7a0a6549e294c1b15f33d5b99a1e5e6b7c0f1f78ee311', 'database/repositories/verification_repository.py': '73554cbc705db251e17c678410398bfed5d5619722432cfcf75ffd6f6bbb5b0e', 'database/repositories/windows_interaction_repository.py': 'e45051fd6beadd89ece247e6229ea2eb64df9fbaafa4f91e61f1e43f577c0df9', 'risk/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'risk/account_gate.py': '551d49b29eab305ce35301b8a6aebb0df4eb3d9fd2bbe13dc64d3dcfc9d8cb51', 'signal/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'strategy/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'trading_execution/billing_lifecycle.py': '18213c4017ce9e285259600b09871450bec0856c4fbfb52fc772e212e4426002', 'trading_execution/commercial_ledger_sync.py': '04dcd327bfe4c7495cf0f94b9d6712345eb1341658080b25b454bd176d846681', 'trading_execution/finance_collection.py': '0cedb6129db487f337a57ac45cf0434da11392fcc75c0bc8a7ae8c55c176fab4', 'trading_execution/weekly_settlement.py': 'e3c5be0f254390d65ad3d6cfad51aedd9655f5c1a55d8c70602ca3dd410f6757'}
ROLES={
 'portal':('secure-secrets-portal.service','scripts/secure_secrets_portal_server.py',18080),
 'contact':('xuanjun-wecom-customer-contact.service','ai_service/wecom_customer_contact_service.py',18781),
 'customer_service':('xuanjun-wecom-customer-service.service','ai_service/wecom_customer_service.py',18780)}

def need(v,code):
    if not v:raise RuntimeError(code)

def sha(b):return hashlib.sha256(b).hexdigest()

def load(raw,digest):
    need(sha(raw)==digest,'HELPER_HASH_CHANGED')
    ns={'__name__':'frozen_functions','__file__':'frozen_helper.py'}
    exec(compile(raw,'frozen_helper.py','exec'),ns)
    return ns

def safe_errors(path):
    if not path.is_file():return [{'log_missing':True}]
    rows=[]
    for line in path.read_bytes()[-32768:].decode('utf-8','replace').splitlines():
        m=re.match(r'^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception)):\s*(.*)$',line)
        if m:
            detail=m.group(2);row={'exception':m.group(1)}
            if re.fullmatch(r'[A-Z0-9_]{1,100}',detail):row['code']=detail
            for pattern,key in ((r"No module named '([A-Za-z0-9_.]+)'",'missing_module'),
                                (r"cannot import name '([A-Za-z0-9_]+)'",'missing_import'),
                                (r'\[Errno (\d+)\]','errno')):
                match=re.search(pattern,detail)
                if match:row[key]=match.group(1)
            rows.append(row)
        elif 'unrecognized arguments' in line:rows.append({'code':'CLI_ARGUMENT_REJECTED'})
        elif 'error while loading shared libraries' in line:rows.append({'code':'SHARED_LIBRARY_MISSING'})
    return rows[-12:]

def validate_stdlib_signal(sources):
    need('signal.py' not in sources and not any(n.startswith('signal/') for n in sources),'STDLIB_SIGNAL_SHADOW')
    # Omitting the empty unrelated repository package is valid only while none
    # of the admitted source files requests a project-local signal submodule.
    for name,b in sources.items():
        tree=ast.parse(b,filename=name)
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module:
                need(not node.module.startswith('signal.'),'LOCAL_SIGNAL_SUBMODULE_REQUIRED')
            if isinstance(node,ast.Import):
                need(not any(a.name.startswith('signal.') for a in node.names),'LOCAL_SIGNAL_SUBMODULE_REQUIRED')

def collect_supplement(read,initial):
    need(len(initial)==79,'INITIAL_SOURCE_COUNT')
    root=Path('/root/pr99-current-point-received-v2/verified/code')
    extra={}
    for name,expected in SUPPLEMENT_PINS.items():
        need(name not in initial,'SUPPLEMENT_COLLISION')
        b=read(root/name,2*1024*1024)
        need(sha(b)==expected,'SUPPLEMENT_SOURCE_CHANGED')
        if name=='signal/__init__.py':
            need(b==b'','SIGNAL_EXCLUSION_CHANGED')
            continue
        extra[name]=b
    need(len(extra)==45 and sum(map(len,extra.values()))<1024*1024,'SUPPLEMENT_COUNT_OR_SIZE')
    validate_stdlib_signal(dict(initial,**extra))
    return extra

def decode_supplement(encoded,initial):
    expected={n:h for n,h in SUPPLEMENT_PINS.items() if n!='signal/__init__.py'}
    need(isinstance(encoded,dict) and set(encoded)==set(expected),'SUPPLEMENT_MEMBER_SET')
    extra={}
    for name,value in encoded.items():
        need(name not in initial,'SUPPLEMENT_COLLISION')
        need(isinstance(value,str) and len(value)<=2*1024*1024,'SUPPLEMENT_ENCODING_SIZE')
        b=base64.b64decode(value,validate=True)
        need(sha(b)==expected[name],'SUPPLEMENT_HASH_CHANGED')
        extra[name]=b
    need(sum(map(len,extra.values()))<1024*1024,'SUPPLEMENT_TOTAL_SIZE')
    return extra


BRIDGE_ROOT=PurePosixPath('/opt/trading-system/runtime/v8-domestic-operations/internal-bridge')
BRIDGE_LOCAL=Path('/root/pr99-s07-bridge-materials-v1')
TOKYO='iZ6wee8q9z4t03hvqumwfhZ'
TOKYO_KEY='47.245.53.152 ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBMfngQ3DTnuC8aP0TZ0fBhcq+8p7Yw0c7VEYKWSpFrtpqWf+shoFTiyrAWj1OlrnoeOlsZq1SS1zOavODbJOnzs=\n'

def bridge_paths(sources):
    # Evaluate only path construction and environment DEFAULTS in AST, never code.
    unknown=object();found=set()
    for name in ('ai_service/telegram_customer_service_canary.py','ai_service/wecom_customer_service.py'):
        tree=ast.parse(sources[name]);symbols={}
        def value(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):return node.value
            if isinstance(node,ast.Name):return symbols.get(node.id,unknown)
            if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):
                left,right=value(node.left),value(node.right)
                if isinstance(left,(str,PurePosixPath)) and isinstance(right,(str,PurePosixPath)):
                    return PurePosixPath(left)/right
            if isinstance(node,ast.Call):
                func=ast.unparse(node.func)
                if func in ('Path','pathlib.Path','PurePosixPath','str') and len(node.args)==1:
                    arg=value(node.args[0])
                    if isinstance(arg,(str,PurePosixPath)):return str(arg) if func=='str' else PurePosixPath(arg)
                if func in ('os.getenv','os.environ.get','environ.get','getenv'):
                    if len(node.args)==2:return value(node.args[1])
                    for kw in node.keywords:
                        if kw.arg=='default':return value(kw.value)
                if isinstance(node.func,ast.Attribute) and node.func.attr in ('resolve','absolute','expanduser') and not node.args:
                    return value(node.func.value)
            return unknown
        assignments=[n for n in tree.body if isinstance(n,(ast.Assign,ast.AnnAssign))]
        for iteration in range(len(assignments)+1):
            changed=False
            for node in assignments:
                targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                if node.value is None:continue
                v=value(node.value)
                if v is unknown:continue
                for target in targets:
                    if isinstance(target,ast.Name) and symbols.get(target.id,unknown)!=v:
                        symbols[target.id]=v;changed=True
            if not changed:break
        for node in ast.walk(tree):
            v=value(node)
            if not isinstance(v,(str,PurePosixPath)):continue
            text=str(v)
            if not text.startswith(str(BRIDGE_ROOT)+'/'):continue
            if text==str(BRIDGE_ROOT/'secrets'):
                provider=ast.parse(sources['ai_service/internal_provider_neutral_bridge.py'])
                cls=next(x for x in provider.body if isinstance(x,ast.ClassDef) and x.name=='BridgeSecretProvider')
                current=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='current')
                need(any(isinstance(x,ast.Constant) and x.value=='bridge_hmac.current' for x in ast.walk(current)),'BRIDGE_CURRENT_FILENAME_NOT_PROVEN')
                text=str(BRIDGE_ROOT/'secrets'/'bridge_hmac.current')
            p=PurePosixPath(text)
            need(str(p)==text and '..' not in p.parts and (p.parent==BRIDGE_ROOT or p==BRIDGE_ROOT/'secrets'/'bridge_hmac.current'),'BRIDGE_PATH_NOT_EXACT_FILE')
            need(bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',p.name)),'BRIDGE_FILE_NAME')
            found.add(str(p))
    need(str(BRIDGE_ROOT/'domestic_bridge_cert.sha256') in found,'BRIDGE_CERT_PATH_NOT_PROVEN')
    need(1<=len(found)<=8,'BRIDGE_FILE_COUNT')
    return sorted(found)

def bridge_pack(h):
    need(os.geteuid()==0 and os.uname().nodename==TOKYO,'TOKYO_ROOT_REQUIRED')
    helper=load(base64.b64decode(h['source_helper'],validate=True),SOURCE_SHA)
    hashes=h['source_hashes']
    need(isinstance(hashes,dict) and len(hashes)==124,'TOKYO_SOURCE_COUNT')
    for name,expected in hashes.items():
        rel=PurePosixPath(name)
        need(not rel.is_absolute() and '..' not in rel.parts and str(rel)==name and name.endswith('.py'),'TOKYO_SOURCE_SCOPE')
        b=helper['read_plain_file'](Path('/opt/trading-system')/name,2*1024*1024)
        need(sha(b)==expected,'TOKYO_CURRENT_SOURCE_CHANGED')
    paths=h['bridge_paths']
    need(isinstance(paths,list) and 1<=len(paths)<=8 and len(set(paths))==len(paths),'BRIDGE_FILE_COUNT')
    result={}
    for name in paths:
        p=PurePosixPath(name)
        need((p.parent==BRIDGE_ROOT or p==BRIDGE_ROOT/'secrets'/'bridge_hmac.current') and str(p)==name and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',p.name),'BRIDGE_SOURCE_SCOPE')
        b=helper['read_plain_file'](Path(name),65536)
        need(0<len(b)<=65536,'BRIDGE_EMPTY_OR_SIZE')
        if p.name=='domestic_bridge_cert.sha256':
            need(bool(re.fullmatch(rb'[0-9a-fA-F]{64}\s*',b)),'BRIDGE_CERT_PIN_FORMAT')
        result[name]={'data':base64.b64encode(b).decode(),'sha256':sha(b),'bytes':len(b)}
    print(json.dumps({'host':TOKYO,'files':result,'service_actions':0,'api_requests':0,'source_files':124,'current_source_hashes':'PASS'},sort_keys=True),flush=True)

def collect_bridge(sources,sr,selfraw):
    paths=bridge_paths(sources)
    need(not os.path.lexists(BRIDGE_LOCAL),'BRIDGE_STAGE_EXISTS_PRESERVE')
    BRIDGE_LOCAL.mkdir(mode=0o700)
    put(BRIDGE_LOCAL/'known_hosts',TOKYO_KEY.encode(),0o400)
    h={'bridge_paths':paths,'source_hashes':{n:sha(b) for n,b in sources.items()},'source_helper':base64.b64encode(sr).decode(),
       'self':base64.b64encode(selfraw).decode()}
    payload=(json.dumps(h)+'\n').encode();need(len(payload)<250000,'TOKYO_HEADER_SIZE')
    put(BRIDGE_LOCAL/'private-input.json',payload,0o400)
    bootstrap='import sys,json,base64;h=json.loads(sys.stdin.buffer.readline(250000));n={"__name__":"bridge_functions"};exec(base64.b64decode(h["self"]),n);n["bridge_pack"](h)'
    command='/usr/bin/python3.11 -I -B -u -c '+shlex.quote(bootstrap)
    ssh=['/usr/bin/ssh','-T','-o','UserKnownHostsFile='+str(BRIDGE_LOCAL/'known_hosts'),
         '-o','GlobalKnownHostsFile=/dev/null','-o','StrictHostKeyChecking=yes',
         '-o','HostKeyAlgorithms=ecdsa-sha2-nistp256','-o','UpdateHostKeys=no',
         '-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
         '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    print('请输入东京root密码：只读取源码确定的桥接文件，私有传输，不更改东京服务。',flush=True)
    with (BRIDGE_LOCAL/'private-input.json').open('rb') as inp,(BRIDGE_LOCAL/'materials.private.json').open('xb') as out,(BRIDGE_LOCAL/'ssh-private.log').open('xb') as err:
        try:r=subprocess.run(ssh+['root@47.245.53.152',command],stdin=inp,stdout=out,stderr=err,timeout=180)
        except subprocess.TimeoutExpired:raise RuntimeError('TOKYO_READ_TIMEOUT_PRESERVE')
    need(r.returncode==0,'TOKYO_BRIDGE_READ_FAILED_PRIVATE_LOG_PRESERVED')
    raw=(BRIDGE_LOCAL/'materials.private.json').read_bytes();need(len(raw)<1024*1024,'BRIDGE_RESPONSE_SIZE')
    material=json.loads(raw)
    need(material['host']==TOKYO and material['service_actions']==0 and material['api_requests']==0 and material['source_files']==124 and material['current_source_hashes']=='PASS','TOKYO_BRIDGE_SCOPE')
    decode_bridge(material['files'],paths)
    put(BRIDGE_LOCAL/'receipt.json',json.dumps({'status':'AUTHENTIC_BRIDGE_MATERIALS_PRIVATE_RECEIVED','files':len(paths),'service_actions':0},sort_keys=True).encode(),0o400)
    print('AUTHENTIC_BRIDGE_MATERIALS_RECEIVED files='+str(len(paths)),flush=True)
    return material['files']

def decode_bridge(files,paths):
    need(isinstance(files,dict) and set(files)==set(paths),'BRIDGE_MEMBER_SET')
    out={}
    for name,row in files.items():
        p=PurePosixPath(name)
        need((p.parent==BRIDGE_ROOT or p==BRIDGE_ROOT/'secrets'/'bridge_hmac.current') and str(p)==name and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',p.name),'BRIDGE_TARGET_SCOPE')
        need(isinstance(row,dict) and type(row['bytes']) is int and 0<row['bytes']<=65536,'BRIDGE_SIZE')
        need(isinstance(row['data'],str) and len(row['data'])<=90000,'BRIDGE_ENCODING_SIZE')
        b=base64.b64decode(row['data'],validate=True)
        need(len(b)==row['bytes'] and sha(b)==row['sha256'],'BRIDGE_HASH_CHANGED')
        if p.name=='domestic_bridge_cert.sha256':
            need(bool(re.fullmatch(rb'[0-9a-fA-F]{64}\s*',b)),'BRIDGE_CERT_PIN_FORMAT')
        out['project/'+str(p.relative_to('/opt/trading-system'))]=b
    return out


def launch_command(raw,entry,port):
    # Accept only the observed Python entry and host/port options, never a shell.
    a=shlex.split(raw)
    need(a and re.fullmatch(r'/(?:usr/bin/python3(?:\.11)?|opt/trading-system/venv/bin/python(?:3(?:\.11)?)?)',a[0]),'UNIT_PYTHON_EXECUTABLE')
    tail=a[1:]
    while tail and tail[0] in ('-u','-B'):tail=tail[1:]
    module=entry[:-3].replace('/','.')
    if tail[:2]==['-m',module]:
        invocation=['-m',module];tail=tail[2:]
    else:
        need(tail and tail[0] in (entry,'/opt/trading-system/'+entry),'UNIT_ENTRY_CHANGED')
        invocation=['/opt/trading-system/'+entry];tail=tail[1:]
    # Owner metadata + pinned portal AST confirm the literal serve subcommand.
    if entry=='scripts/secure_secrets_portal_server.py' and tail[:1]==['serve']:
        invocation.append('serve');tail=tail[1:]
    normalized=[]
    while tail:
        token=tail.pop(0)
        if '=' in token:key,value=token.split('=',1)
        else:
            key=token;need(bool(tail),'UNIT_OPTION_VALUE');value=tail.pop(0)
        need(key in ('--host','--port'),'UNSUPPORTED_START_OPTION')
        if key=='--host':
            need(value in ('127.0.0.1','0.0.0.0','localhost'),'UNSUPPORTED_LISTEN_HOST')
            value='127.0.0.1'
        else:need(value==str(port),'UNIT_PORT_CHANGED')
        need(key not in normalized,'DUPLICATE_START_OPTION')
        normalized.extend([key,value])
    return ['/venv/bin/python','-B','-u']+invocation+normalized

def put(path,b,mode=0o600):
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    with path.open('xb') as f:f.write(b)
    path.chmod(mode)

def public_directory(path):
    # mkdir's requested mode is masked by the coordinator's private umask.
    path.mkdir(mode=0o755,exist_ok=True)
    need(not path.is_symlink() and path.is_dir(),'ISOLATION_DIRECTORY_TYPE')
    path.chmod(0o755)

def require_preserved_failure(old):
    previous=Path('/var/lib/xuanjun-pr99-s07-isolated-start-v3')
    need(previous.is_dir() and not previous.is_symlink(),'PREVIOUS_ATTEMPT_MISSING')
    receipt=json.loads(old['stable'](previous/'receipt.json',100000))
    need(receipt['status']=='ISOLATED_START_HOLD' and receipt['application_processes_stopped'] is True
         and receipt['protected_state_unchanged'] is True,'PREVIOUS_RECEIPT_CHANGED')
    need(set(receipt['roles'])==set(ROLES),'PREVIOUS_ROLE_SET')
    need(receipt['source_files']==124 and receipt['supplement_files']==45,'PREVIOUS_SOURCE_SCOPE')
    contact=receipt['roles']['contact']
    need(contact['loopback_listener'] is True and contact['health_http_status']==200,'PREVIOUS_CONTACT_STATE')
    for role in ('portal','customer_service'):
        row=receipt['roles'][role]
        need(row['returncode']==1 and row['loopback_listener'] is False,'PREVIOUS_ROLE_STATE')
        log=old['stable'](previous/(role+'.private.log'),100000)
        need(b'FileNotFoundError:' in log and str(BRIDGE_ROOT/'domestic_bridge_cert.sha256').encode() in log,'PREVIOUS_ERROR_CHANGED')
    before=json.loads(old['stable'](previous/'protected.before.json',4*1024*1024))
    after=json.loads(old['stable'](previous/'protected.after.json',4*1024*1024))
    need(before==after==old['protected_snapshot'](),'PREVIOUS_PROTECTED_STATE_CHANGED')
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            cmd=(p/'cmdline').read_bytes()
            process_root=os.readlink(p/'root')
        except FileNotFoundError:continue
        need(str(previous) not in process_root and str(previous).encode() not in cmd,
             'PREVIOUS_ISOLATED_PROCESS_PRESENT')

def copy_project(root,sources,data):
    project=root/'opt/trading-system'
    project.mkdir(parents=True,mode=0o700)
    for n,b in sources.items():
        p=PurePosixPath(n)
        need(not p.is_absolute() and '..' not in p.parts and str(p)==n and '\\' not in n,'SOURCE_PATH')
        put(project/n,b,0o400)
    for name,b in data.items():
        if name.startswith('project/'):target=project/name[len('project/'):]
        elif name=='referral/0.json':
            target=root/'home/admin/.openclaw/workspace/xuanjun-agent-coordination/CUSTOMER_REFERRAL_CONFIG.json'
        elif name=='referral/1.json':
            target=root/'home/openclaw_ops/v8-domestic-operations/config/customer-referral/CUSTOMER_REFERRAL_CONFIG.json'
        else:raise RuntimeError('MATERIAL_PATH')
        if target.exists():need(target.read_bytes()==b,'SOURCE_DATA_COLLISION')
        else:put(target,b)
    for base in (root/'opt',root/'home'):
        if not base.exists():continue
        for current,dirs,files in os.walk(base,followlinks=False):
            os.chown(current,65534,65534);os.chmod(current,0o700)
            for name in files:os.chown(Path(current)/name,65534,65534)
    # The fixed /opt and /home mount-root paths need traversing after dropping uid.
    for p in (root/'opt',root/'home'):
        if p.exists():p.chmod(0o755)
    for n,b in sources.items():need(sha((project/n).read_bytes())==sha(b),'COPIED_SOURCE_CHANGED')
    return project

def child(root,commands):
    need(os.geteuid()==0 and os.uname().nodename==DOMESTIC,'NAMESPACE_HOST')
    subprocess.run(['/usr/bin/mount','--make-rprivate','/'],check=True,timeout=10)
    ip=next((p for p in ('/usr/sbin/ip','/sbin/ip','/usr/bin/ip') if Path(p).is_file()),None);need(bool(ip),'IP_TOOL_MISSING')
    links=json.loads(subprocess.check_output([ip,'-j','link','show'],timeout=10))
    need([x['ifname'] for x in links]==['lo'],'NETWORK_NAMESPACE_HAS_EXTERNAL_INTERFACE')
    subprocess.run([ip,'link','set','lo','up'],check=True,timeout=10)
    for name in ('usr','lib','lib64'):
        origin=Path('/'+name)
        if not origin.exists():continue
        target=root/name;target.mkdir(mode=0o755,exist_ok=True)
        subprocess.run(['/usr/bin/mount','--bind',str(origin),str(target)],check=True,timeout=10)
        subprocess.run(['/usr/bin/mount','-o','remount,bind,ro,nosuid,nodev',str(target)],check=True,timeout=10)
    public_directory(root/'dev')
    for name in ('null','urandom'):
        target=root/'dev'/name;target.touch(mode=0o600)
        subprocess.run(['/usr/bin/mount','--bind','/dev/'+name,str(target)],check=True,timeout=10)
    libc=ctypes.CDLL(None,use_errno=True)
    def confined():
        os.chroot(root);os.chdir('/opt/trading-system')
        need(libc.prctl(38,1,0,0,0)==0,'NO_NEW_PRIVILEGES_FAILED')
        os.setgroups([]);os.setgid(65534);os.setuid(65534)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        resource.setrlimit(resource.RLIMIT_NOFILE,(256,256))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024*1024,128*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(30,30))
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
    procs={};logs=[];observed={}
    env={'PATH':'/venv/bin:/usr/bin:/bin','HOME':'/nonexistent','LANG':'C.UTF-8',
         'PYTHONPATH':'/opt/trading-system','PYTHONDONTWRITEBYTECODE':'1',
         'WECOM_CONTACT_HOST':'127.0.0.1','WECOM_CONTACT_PORT':'18781',
         'WECOM_KF_HOST':'127.0.0.1','WECOM_KF_PORT':'18780'}
    try:
        for role,command in commands.items():
            f=(ATTEMPT/(role+'.private.log')).open('xb');logs.append(f)
            procs[role]=subprocess.Popen(command,preexec_fn=confined,env=env,
                stdin=subprocess.DEVNULL,stdout=f,stderr=f,start_new_session=True)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            for role,proc in procs.items():
                alive=proc.poll() is None
                s=socket.socket();s.settimeout(0.2)
                try:listening=alive and s.connect_ex(('127.0.0.1',ROLES[role][2]))==0
                finally:s.close()
                observed[role]={'process_alive':alive,'returncode':proc.poll(),'loopback_listener':listening,
                    'health_http_status':None}
            if all(x['loopback_listener'] for x in observed.values()) or all(p.poll() is not None for p in procs.values()):break
            time.sleep(0.5)
        for role,row in observed.items():
            if row['loopback_listener']:
                c=http.client.HTTPConnection('127.0.0.1',ROLES[role][2],timeout=3)
                try:
                    c.request('GET','/healthz');r=c.getresponse()
                    row['health_http_status']=r.status;r.read(65536)
                except (OSError,http.client.HTTPException):row['health_http_status']='UNKNOWN'
                finally:c.close()
    finally:
        for p in procs.values():
            if p.poll() is None:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
        for p in procs.values():
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                p.wait(timeout=5)
        for f in logs:f.close()
    result={'status':'ISOLATED_THREE_LISTENERS_PASS_RUNTIME_ACCEPTANCE_PENDING'
        if len(observed)==3 and all(x['loopback_listener'] for x in observed.values()) else 'ISOLATED_START_HOLD',
        'roles':observed,'network_namespace_external_interfaces':0,
        'app_uid_gid':'65534:65534','application_root':'COPIED_CHROOT','application_processes_stopped':True,
        'temporary_app_process_starts':len(procs),'production_service_actions':0,
        'production_cutover':False,'final_cutover_snapshot':False}
    print(json.dumps(result,sort_keys=True),flush=True)

def run_domestic(h):
    need(os.geteuid()==0 and os.uname().nodename==DOMESTIC,'DOMESTIC_ROOT_REQUIRED')
    os.umask(0o077)
    old=load(base64.b64decode(h['original'],validate=True),ORIGINAL_SHA)
    transfer=load(base64.b64decode(h['transfer'],validate=True),TRANSFER_SHA)
    source=load(base64.b64decode(h['source_helper'],validate=True),SOURCE_SHA)
    require_preserved_failure(old)
    need(not os.path.lexists(ATTEMPT),'ISOLATED_ATTEMPT_EXISTS_NO_RETRY')
    r=json.loads(old['stable'](MATERIAL/'receipt.json',100000))
    need(r['status']=='DOMESTIC_S07_PRIVATE_MATERIALS_STAGED_PASS' and r['tar_sha256']==TAR_SHA and r['wire_sha256']==WIRE_SHA,'DOMESTIC_MATERIAL_RECEIPT_CHANGED')
    wire=old['stable'](MATERIAL/'received.tar.gz',transfer['MAX_RAW'])
    need(sha(wire)==WIRE_SHA,'DOMESTIC_WIRE_CHANGED')
    raw=transfer['decompress_checked'](wire,{'wire_bytes':len(wire),'wire_sha256':WIRE_SHA,
        'tar_bytes':h['tar_bytes'],'tar_sha256':TAR_SHA})
    manifest,data=transfer['checked_members'](raw,source)
    for name,b in data.items():need(sha(old['stable'](MATERIAL/'received'/name,len(b)))==sha(b),'STAGED_MATERIAL_CHANGED')
    sources={}
    installed=json.loads(old['stable'](old['BASE']/'source-manifest.json',2*1024*1024))
    need(installed==h['sources'] and len(installed)==79,'INSTALLED_SOURCE_MANIFEST_CHANGED')
    for n,row in installed.items():
        p=PurePosixPath(n);need(not p.is_absolute() and '..' not in p.parts and str(p)==n,'SOURCE_PATH')
        b=old['stable'](old['BASE']/'app'/n,row['bytes'])
        need(sha(b)==row['sha256'],'INSTALLED_SOURCE_CHANGED');sources[n]=b
    extra=decode_supplement(h['supplement'],sources)
    sources.update(extra)
    need(len(sources)==124,'COMBINED_SOURCE_COUNT')
    validate_stdlib_signal(sources)
    bridge=decode_bridge(h['bridge'],bridge_paths(sources))
    for name,b in bridge.items():
        need(name not in data or data[name]==b,'BRIDGE_MATERIAL_COLLISION')
        data[name]=b
    need(set(h['commands'])==set(ROLES),'ROLE_SET')
    for role,command in h['commands'].items():
        # Revalidate the final fixed launcher; no arbitrary command/port can enter.
        fake='/usr/bin/python3 '+shlex.join(command[3:])
        need(launch_command(fake,ROLES[role][1],ROLES[role][2])==command,'LAUNCH_COMMAND_BINDING')
    before=old['protected_snapshot']()
    ATTEMPT.mkdir(mode=0o700)
    try:
        put(ATTEMPT/'protected.before.json',old['encoded'](before),0o400)
        unshare='/usr/bin/unshare';need(Path(unshare).is_file() and Path('/usr/bin/mount').is_file(),'NAMESPACE_TOOLS_MISSING')
        with (ATTEMPT/'namespace-preflight.private.log').open('xb') as f:
            subprocess.run([unshare,'--mount','--net','--pid','--fork','/usr/bin/true'],
                stdout=f,stderr=f,check=True,timeout=15)
        root=ATTEMPT/'rootfs';public_directory(root)
        copy_project(root,sources,data)
        shutil.copytree(old['BASE']/'venv',root/'venv',symlinks=True)
        for current,dirs,files in os.walk(root/'venv',followlinks=False):
            os.chmod(current,0o755)
            for name in files:
                p=Path(current)/name
                if not p.is_symlink():p.chmod(0o555 if p.stat().st_mode&0o111 else 0o444)
        for n in ('tmp','etc','usr','lib','lib64'):public_directory(root/n)
        (root/'tmp').chmod(0o1777)
        put(root/'etc/passwd',b'root:x:0:0:root:/root:/bin/false\nnobody:x:65534:65534:nobody:/nonexistent:/bin/false\n',0o444)
        put(root/'etc/group',b'root:x:0:\nnobody:x:65534:\n',0o444)
        put(root/'etc/hosts',b'127.0.0.1 localhost\n::1 localhost\n',0o444)
        bootstrap='import base64;n={"__name__":"namespace_functions"};exec(base64.b64decode('+repr(h['self'])+'),n);n["child"](n["Path"]('+repr(str(root))+'),'+repr(h['commands'])+')'
        with (ATTEMPT/'isolated-result.private.log').open('xb') as out,(ATTEMPT/'namespace.private.log').open('xb') as err:
            p=subprocess.Popen([unshare,'--mount','--net','--pid','--fork','/usr/bin/python3','-I','-B','-u','-c',bootstrap],
                stdout=out,stderr=err,stdin=subprocess.DEVNULL,start_new_session=True)
            try:p.wait(timeout=75)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
                raise RuntimeError('ISOLATED_NAMESPACE_TIMEOUT_KILLED_PRESERVE')
            need(p.returncode==0,'NAMESPACE_EXECUTION_FAILED_PRESERVE_PRIVATE_LOG')
        raw=old['stable'](ATTEMPT/'isolated-result.private.log',100000).decode()
        rows=[json.loads(x) for x in raw.splitlines() if x.startswith('{')]
        need(rows,'ISOLATED_RESULT_MISSING')
        result=rows[-1]
        after=old['protected_snapshot']();put(ATTEMPT/'protected.after.json',old['encoded'](after),0o400)
        need(before==after,'DOMESTIC_PROTECTED_STATE_CHANGED')
        result['protected_state_unchanged']=True
        result['source_files']=len(sources);result['supplement_files']=len(extra)
        result['supplement_provenance']='R2_COPY_HASHES_RECHECKED_ON_CURRENT_TOKYO'
        result['current_tokyo_source_hashes']='PASS_124'
        result['bridge_material_files']=len(bridge)
        result['bridge_materials']='AUTHENTIC_TOKYO_PRIVATE_COPY_NO_VERIFICATION_BYPASS'
        result['dynamic_completeness_proven']=False
        for role in ROLES:result['roles'][role]['errors']=safe_errors(ATTEMPT/(role+'.private.log'))
        result['data_source']='PRELIMINARY_165_FILE_COPY_NOT_CANONICAL_WRITER'
        result['services_installed']=False;result['runtime_configuration_complete']=False
        put(ATTEMPT/'receipt.json',old['encoded'](result),0o400)
        print(json.dumps(result,sort_keys=True),flush=True)
    except BaseException:
        put(ATTEMPT/'failure.json',b'{"status":"HOLD_PRESERVE_NO_RETRY"}\n',0o400)
        print(json.dumps({'status':'ISOLATED_INFRASTRUCTURE_HOLD','errors':{name:safe_errors(ATTEMPT/name) for name in ('namespace.private.log','portal.private.log','contact.private.log','customer_service.private.log')}},sort_keys=True),flush=True)
        raise

def main():
    need(os.geteuid()==0 and os.uname().nodename==KOREA,'KOREA_ROOT_REQUIRED')
    os.umask(0o077);need(not os.path.lexists(LOCAL),'LOCAL_ATTEMPT_EXISTS_NO_RETRY')
    tr=TRANSFER_PATH.read_bytes();transfer=load(tr,TRANSFER_SHA)
    material_path=Path('/root/pr99-s07-material-v2-launch.mgOIzkS1/stage.py')
    sr=material_path.read_bytes();source=load(sr,SOURCE_SHA)
    original=source['read_plain_file'](Path('/root/pr99-s07-install-launch.a5NZU99H/install.py'),100000)
    old=load(original,ORIGINAL_SHA)
    p=Path('/root/pr99-s07-runtime-inventory.8no57zD5/inspect.py')
    inventory=load(source['read_plain_file'](p,100000),'295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134')
    resolver=inventory['load_pinned'](inventory['RESOLVER'],inventory['RESOLVER_SHA'])
    projection,collector=resolver['bootstrap']()
    receipt=json.loads(collector['stable_file'](projection['ROOT']/'receipt.json',20000,private=True))
    need(receipt['archive_sha256']==projection['ARCHIVE_SHA'],'S06_ARCHIVE_BINDING')
    archive=collector['stable_file'](projection['ROOT']/'payload.tar.gz',4*1024*1024+65536,private=True)
    need(sha(archive)==projection['ARCHIVE_SHA'],'S06_ARCHIVE_CHANGED')
    units=collector['verify_archive'](archive,receipt)
    commands={}
    for role,(unit,entry,port) in ROLES.items():
        fields=resolver['unit_service'](units['units/'+unit])
        need(len(fields.get('ExecStart',[]))==1,'UNIT_START_COUNT')
        commands[role]=launch_command(fields['ExecStart'][0],entry,port)
    package=old['stable'](old['LOCAL_ATTEMPT']/'package.json',64*1024*1024)
    plan,files=old['unpack'](package,sha(package))
    need(sha(package)=='9b702576d48883786d051b2f1b49972baf94db3d1e8bf330ee59250a5974efa3','PACKAGE_CHANGED')
    extra=collect_supplement(source['read_plain_file'],files)
    selfraw=source['read_plain_file'](Path(__file__).absolute(),100000)
    bridge=collect_bridge(dict(files,**extra),sr,selfraw)
    h={'bridge':bridge,'original':base64.b64encode(original).decode(),'transfer':base64.b64encode(tr).decode(),
       'source_helper':base64.b64encode(sr).decode(),'self':base64.b64encode(selfraw).decode(),
       'supplement':{n:base64.b64encode(b).decode() for n,b in extra.items()},
       'commands':commands,'sources':{n:{'bytes':len(b),'sha256':sha(b)} for n,b in files.items()},
       'tar_bytes':(Path('/root/pr99-s07-private-materials-v2/materials.tar')).stat().st_size}
    auth=Path(tempfile.mkdtemp(prefix='pr99-s07-isolated-auth-',dir='/root'))
    (auth/'known_hosts').write_text(transfer['HOST_KEY'])
    ssh=['/usr/bin/ssh','-T','-S',str(auth/'socket'),'-o','ControlMaster=auto','-o','ControlPersist=600',
       '-o','UserKnownHostsFile='+str(auth/'known_hosts'),'-o','GlobalKnownHostsFile=/dev/null',
       '-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ecdsa-sha2-nistp256',
       '-o','UpdateHostKeys=no','-o','ForwardAgent=no','-o','ForwardX11=no','-o','ClearAllForwardings=yes',
       '-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2']
    remote='root@47.101.152.210'
    try:
        print('请输入国内root密码；仅复制品隔离启动，禁外网，结束即停止，不切入口。',flush=True)
        subprocess.run(ssh+['-n',remote,'test "$(hostname -s)" = '+DOMESTIC+' && test "$(id -u)" = 0'],check=True,timeout=180)
        LOCAL.mkdir(mode=0o700);wire=(json.dumps(h)+'\n').encode();need(len(wire)<2*1024*1024,'BOOTSTRAP_LENGTH')
        put(LOCAL/'private-input.json',wire,0o400)
        bootstrap='import sys,json,base64;h=json.loads(sys.stdin.buffer.readline(2097152));n={"__name__":"isolated_start_functions"};exec(base64.b64decode(h["self"]),n);n["run_domestic"](h)'
        command='/usr/bin/python3 -I -B -u -c '+shlex.quote(bootstrap)
        with (LOCAL/'private-input.json').open('rb') as inp,(LOCAL/'result.log').open('xb') as out,(LOCAL/'ssh-private.log').open('xb') as err:
            p=subprocess.Popen(ssh+['-o','BatchMode=yes',remote,command],stdin=inp,stdout=out,stderr=err)
            deadline=time.monotonic()+240
            while True:
                try:p.wait(timeout=15);break
                except subprocess.TimeoutExpired:
                    print('S07_ISOLATED_START_PROGRESS',flush=True)
                    if time.monotonic()>deadline:
                        p.terminate();p.wait(timeout=15);raise RuntimeError('REMOTE_RESULT_UNKNOWN_PRESERVE')
            if p.returncode:
                for line in (LOCAL/'result.log').read_text().splitlines():
                    if line.startswith('{'):
                        row=json.loads(line)
                        if row.get('status')=='ISOLATED_INFRASTRUCTURE_HOLD':print(json.dumps(row,sort_keys=True),flush=True)
            need(p.returncode==0,'REMOTE_ISOLATED_START_FAILED_PRESERVE_PRIVATE_LOG')
        text=old['stable'](LOCAL/'result.log',100000).decode()
        rows=[json.loads(x) for x in text.splitlines() if x.startswith('{')]
        need(rows,'RESULT_RECEIPT_MISSING')
        put(LOCAL/'receipt.json',old['encoded'](rows[-1]),0o400)
        print(json.dumps(rows[-1],sort_keys=True),flush=True)
    finally:
        try:subprocess.run(ssh+['-O','exit',remote],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):pass

if __name__=='__main__':
    try:main()
    except BaseException as e:
        reason=str(e) if isinstance(e,RuntimeError) and str(e).replace('_','').isalnum() and len(str(e))<120 else type(e).__name__
        print('S07_ISOLATED_START_HOLD='+reason+' PRESERVE_NO_RETRY',flush=True)
        raise SystemExit(2)

"""Read four exact source files to resolve the missing startup loader/order.

Output is redacted syntax, never executable business imports, raw literals,
environment values, database bytes or an in-memory/effective-config attestation.
"""
import ast
import base64
import copy
import datetime
import hashlib
import json
import os
import re
import stat
import zlib

PINS=(
 ('scripts/secure_secrets_portal_server.py','57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'),
 ('ai_service/wecom_customer_contact_service.py','c95ca9ec711d05d64489ed927cae770157954b46661411b5f762f193ba711571'),
 ('ai_service/wecom_customer_service.py','aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402'),
 ('database/connection.py','58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece'))
LITERALS=frozenset(('__main__','__name__','PRIVATE_LITERAL_WITHHELD','TRADING_DATABASE_URL',
 'DATABASE_URL','credential-store.env','utf-8','utf8','=', '#','',':','\n',
 '--host','--port','--runtime-dir','--env-file','--database-url','--db-url','--config','--credential-env-file',
 '/opt/trading-system/runtime/secure-secrets-portal',
 '/opt/trading-system/runtime/v8-domestic-operations',
 '/opt/trading-system/runtime/v8-domestic-operations/operations-secretref-store',
 '/opt/trading-system/runtime/v8-domestic-operations/wecom-customer-service',
 '/opt/trading-system/runtime/v8-domestic-operations/wecom-customer-contact',
 'serve','store_true','dest','default','required','type'))


def sha(raw):return hashlib.sha256(raw).hexdigest()


class Redact(ast.NodeTransformer):
    def visit_Constant(self,node):
        if type(node.value)is str and node.value in LITERALS:return node
        if node.value is None or type(node.value)is bool:return node
        if type(node.value)is int and node.value in (0,1,2):return node
        return ast.copy_location(ast.Constant('PRIVATE_LITERAL_WITHHELD'),node)


def excerpt(raw):
    tree=ast.parse(raw)
    selected=[];functions=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            functions.append({'name':node.name,'line':node.lineno})
            if re.search(r'main$|^serve$|env|config|^build_|^create_|^parser',node.name,re.I):
                selected.append(node)
        elif isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign)):
            selected.append(node)
    clean=Redact().visit(copy.deepcopy(ast.Module(body=selected,type_ignores=[])))
    code=ast.unparse(ast.fix_missing_locations(clean))
    if len(code.encode())>55000 or len(functions)>120:raise RuntimeError('CONFIG_FLOW_BOUND')
    return {'functions':functions,'redacted_syntax':code}


def read_source(root,path):
    parts=path.split('/');parent=os.dup(root)
    try:
        for name in parts[:-1]:
            nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=nxt
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or before.st_size>1048576:raise RuntimeError('SOURCE_TYPE_BOUND')
            raw=os.pread(fd,1048577,0);after=os.fstat(fd);linked=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
            fingerprint=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if fingerprint(before)!=fingerprint(after) or fingerprint(after)!=fingerprint(linked) or len(raw)!=before.st_size:raise RuntimeError('SOURCE_DRIFT')
            return raw
        finally:os.close(fd)
    finally:os.close(parent)


def observe(expected,nonce):
    if os.geteuid()!=0 or os.uname().nodename!=expected or expected!='iZ6wee8q9z4t03hvqumwfhZ':raise RuntimeError('FIXED_TOKYO_ROOT')
    root=os.open('/opt/trading-system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    rows=[]
    try:
        for path,pin in PINS:
            raw=read_source(root,path)
            if sha(raw)!=pin:raise RuntimeError('PINNED_CONFIG_SOURCE_CHANGED')
            rows.append({'path':path,'sha256':pin,**excerpt(raw)})
    finally:os.close(root)
    return {'scope':'PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION',
      'hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z','sources':rows,
      'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,
      'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}


def wire(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    if len(raw)>180000:raise RuntimeError('CONFIG_FLOW_OUTPUT_BOUND')
    result={'encoding':'PR99_CONFIG_FLOW_ZLIB_V1','bytes':len(raw),'sha256':sha(raw),
            'payload':base64.b64encode(zlib.compress(raw,9)).decode()}
    out=json.dumps(result,separators=(',',':'))
    if len(out.encode())>=23000:raise RuntimeError('CONFIG_FLOW_WIRE_BOUND')
    return out


if __name__=='__main__':print(wire(observe(EXPECTED,NONCE)),flush=True)

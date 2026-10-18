"""Fixed storage implementation inspection, with every business literal removed.

Read source definitions only. No imports from the project, database opens,
process injection, requests, service control or runtime-configuration claims.
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

TARGETS=(
 ('database/repositories.py', ('CredentialRepository',)),
 ('accounts/credential_store.py', ('CredentialStore',)),
 ('ai_service/secure_secrets_portal.py', ('OperationsSecretRefStore','FileBackedSubmissionSessionRepository','SecureSecretsPortalService')),
 ('ai_service/wecom_customer_service.py', ('WeComCustomerServiceIngress',)),
 ('ai_service/wecom_customer_contact_service.py', ('WeComCustomerContactIngress',)),
 ('ai_service/telegram_customer_service_canary.py', ('TelegramCustomerServiceCanary',)),
 ('database/connection.py', ()),
)
PINS={
 'ai_service/wecom_customer_service.py':'aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402',
 'ai_service/wecom_customer_contact_service.py':'c95ca9ec711d05d64489ed927cae770157954b46661411b5f762f193ba711571',
 'database/connection.py':'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece',
}
SAFE_CONSTANTS=('PRIVATE_LITERAL_WITHHELD',)

def sha(raw):return hashlib.sha256(raw).hexdigest()

class RemoveLiterals(ast.NodeTransformer):
    def generic_visit(self,node):
        node=super().generic_visit(node)
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)) and not node.body:
            node.body=[ast.Pass()]
        return node
    def visit_Expr(self,node):
        if isinstance(node.value,ast.Constant):return None
        return self.generic_visit(node)
    def visit_Constant(self,node):
        if node.value is None or type(node.value)is bool:return node
        if type(node.value)is int and node.value in (0,1,2):return node
        return ast.copy_location(ast.Constant('PRIVATE_LITERAL_WITHHELD'),node)

def excerpt(raw,classes):
    tree=ast.parse(raw)
    selected=[];definitions=[];found=[]
    for node in tree.body:
        if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            definitions.append({'name':node.name,'line':node.lineno,'kind':type(node).__name__})
        if isinstance(node,ast.ClassDef):
            if node.name not in classes:continue
            found.append(node.name)
        elif not isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        selected.append(node)
    if set(found)!=set(classes):raise RuntimeError('REQUESTED_CLASS_NOT_FOUND')
    clean=RemoveLiterals().visit(copy.deepcopy(ast.Module(body=selected,type_ignores=[])))
    code=ast.unparse(ast.fix_missing_locations(clean))
    # Removing docstrings can empty an otherwise valid class/function body.
    # Parsing here catches such transformations before any evidence is emitted.
    ast.parse(code)
    if len(code.encode())>170000 or len(definitions)>160:raise RuntimeError('STORAGE_SOURCE_BOUND')
    return {'definitions':definitions,'selected_classes':list(classes),'redacted_syntax':code}

def read_source(root,path):
    parent=os.dup(root)
    try:
        pieces=path.split('/')
        for piece in pieces[:-1]:
            child=os.open(piece,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=child
        fd=os.open(pieces[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        try:
            a=os.fstat(fd)
            if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_size>1048576:raise RuntimeError('SOURCE_TYPE_BOUND')
            raw=os.pread(fd,1048577,0);b=os.fstat(fd)
            c=os.stat(pieces[-1],dir_fd=parent,follow_symlinks=False)
            fp=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if fp(a)!=fp(b) or fp(b)!=fp(c) or len(raw)!=a.st_size:raise RuntimeError('SOURCE_DRIFT')
            return raw
        finally:os.close(fd)
    finally:os.close(parent)

def observe(expected,nonce):
    if os.geteuid()!=0 or os.uname().nodename!=expected or expected!='iZ6wee8q9z4t03hvqumwfhZ':raise RuntimeError('FIXED_TOKYO_ROOT')
    root=os.open('/opt/trading-system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    rows=[]
    try:
        for path,classes in TARGETS:
            raw=read_source(root,path);pin=sha(raw)
            if path in PINS and pin!=PINS[path]:raise RuntimeError('PINNED_SOURCE_DRIFT')
            rows.append({'path':path,'sha256':pin,**excerpt(raw,classes)})
    finally:os.close(root)
    return {'scope':'PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION','hostname':expected,'nonce':nonce,
      'observed_at':datetime.datetime.utcnow().isoformat()+'Z','sources':rows,
      'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,
      'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}

def wire(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    if len(raw)>360000:raise RuntimeError('STORAGE_SEMANTICS_RAW_BOUND')
    value={'encoding':'PR99_STORAGE_SEMANTICS_ZLIB_V1','bytes':len(raw),'sha256':sha(raw),'payload':base64.b64encode(zlib.compress(raw,9)).decode()}
    out=json.dumps(value,separators=(',',':'))
    if len(out.encode())>=23000:raise RuntimeError('STORAGE_SEMANTICS_WIRE_BOUND')
    return out

if __name__=='__main__':
    try:print(wire(observe(EXPECTED,NONCE)),flush=True)
    except BaseException as error:
        code=str(error)
        print(json.dumps({'status':'STORAGE_SEMANTICS_HOLD','exception':type(error).__name__,
          'code':code if re.fullmatch('[A-Z0-9_]{1,100}',code) else 'PRIVATE_DETAIL_WITHHELD','retry_allowed':False}),flush=True)
        raise SystemExit(2)

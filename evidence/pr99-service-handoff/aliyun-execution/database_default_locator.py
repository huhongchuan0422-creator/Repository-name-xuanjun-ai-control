"""Two-host PR99 writer-descriptor observation. No command input or automatic dispatch retry."""
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

UK = 'acs:ram::1107191612880779:role/xuanjun-ai-esc'
KR = 'acs:ram::1691189778575891:role/xuanjun-automation'
CN = 'acs:ram::1384884686754410:role/xuanjun-automation'
HOSTS=(('tokyo',CN,'ap-northeast-1','68985c531add4e90a131aef703a389e6','iZ6wee8q9z4t03hvqumwfhZ'),)


class Hold(Exception):
    pass


def safe(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', value) else 'DETAIL_WITHHELD'


def quote(value):
    return urllib.parse.quote(str(value), safe='~')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def rpc(endpoint, version, action, credentials, **params):
    # Endpoint and action are fixed by this program, never accepted from a task.
    if endpoint not in {'sts.aliyuncs.com'} | {'swas.' + h[2] + '.aliyuncs.com' for h in HOSTS}:
        raise Hold('ENDPOINT_REJECTED')
    key, secret, token = credentials
    values = dict(params, Action=action, Version=version, Format='JSON',
                  AccessKeyId=key, SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                  SignatureNonce=uuid.uuid4().hex,
                  Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    if token:
        values['SecurityToken'] = token
    canonical = '&'.join(quote(k) + '=' + quote(v) for k, v in sorted(values.items()))
    signature = hmac.new((secret + '&').encode(), ('POST&%2F&' + quote(canonical)).encode(), hashlib.sha1).digest()
    values['Signature'] = base64.b64encode(signature).decode()
    request = urllib.request.Request('https://' + endpoint + '/',
        data=urllib.parse.urlencode(values).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
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
        # Never print a URL/body, key, temporary token, or raw exception.
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


# This recovery does not import, publish or run the M99-R1 repair candidate.
# Only this exact new read-only scope is authorized. Historical attempts are never replayed.
import zlib

HOST_PROGRAM='"""Interpret a deliberately small source-expression subset without executing it.\n\nResults are SOURCE DEFAULT candidates. They never establish effective runtime\nconfiguration, Writer ownership, admission, SQLite format or a source fence.\n"""\nimport ast\nimport os\nfrom pathlib import PurePosixPath\n\nclass Unresolved(Exception):\n    pass\n\nclass Defaults:\n    def __init__(self, raw, filename, cwd):\n        self.tree=ast.parse(raw)\n        self.filename=filename;self.cwd=cwd\n        self.functions={n.name:n for n in self.tree.body if isinstance(n,ast.FunctionDef)}\n        self.imports={}\n        for node in self.tree.body:\n            if isinstance(node,ast.Import):\n                for a in node.names:self.imports[a.asname or a.name]=a.name\n            elif isinstance(node,ast.ImportFrom) and node.module:\n                for a in node.names:self.imports[a.asname or a.name]=node.module+\'.\'+a.name\n        self.globals={\'__file__\':filename};self.depth=0\n        for n in self.tree.body:\n            self.assign(n,self.globals)\n\n    def fullname(self,node):\n        if isinstance(node,ast.Name):return self.imports.get(node.id,node.id)\n        if isinstance(node,ast.Attribute):return self.fullname(node.value)+\'.\'+node.attr\n        return \'\'\n\n    def defaults(self,function,scope):\n        positional=function.args.posonlyargs+function.args.args\n        for arg in positional:scope[arg.arg]=Unresolved\n        for arg,node in zip(positional[len(positional)-len(function.args.defaults):],function.args.defaults):\n            try:scope[arg.arg]=self.value(node,scope)\n            except Exception:scope[arg.arg]=Unresolved\n        for arg,node in zip(function.args.kwonlyargs,function.args.kw_defaults):\n            try:scope[arg.arg]=self.value(node,scope)\n            except Exception:scope[arg.arg]=Unresolved\n        return scope\n\n    def assign(self,node,scope):\n        if isinstance(node,ast.If):\n            try:\n                condition=self.value(node.test,scope)\n                if type(condition)is not bool:raise Unresolved()\n                for statement in (node.body if condition else node.orelse):self.assign(statement,scope)\n            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):\n                for child in ast.walk(node):\n                    if isinstance(child,ast.Name) and isinstance(child.ctx,ast.Store):scope[child.id]=Unresolved\n        if isinstance(node,(ast.Assign,ast.AnnAssign)):\n            targets=node.targets if isinstance(node,ast.Assign) else [node.target]\n            try:value=self.value(node.value,scope)\n            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):value=Unresolved\n            for target in targets:\n                if isinstance(target,ast.Name):scope[target.id]=value\n\n    def value(self,n,scope):\n        if n is None:raise Unresolved()\n        if isinstance(n,ast.Constant) and type(n.value) in (str,int,bool,type(None)):return n.value\n        if isinstance(n,ast.Name):\n            v=scope.get(n.id,Unresolved)\n            if v is Unresolved:raise Unresolved()\n            return v\n        if isinstance(n,ast.Compare) and len(n.ops)==len(n.comparators)==1:\n            a=self.value(n.left,scope);b=self.value(n.comparators[0],scope)\n            if isinstance(n.ops[0],ast.Is) and (a is None or b is None):return a is b\n            if isinstance(n.ops[0],ast.IsNot) and (a is None or b is None):return a is not b\n            raise Unresolved()\n        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not self.value(n.operand,scope)\n        if isinstance(n,ast.BinOp):\n            a=self.value(n.left,scope);b=self.value(n.right,scope)\n            if isinstance(n.op,ast.Div) and isinstance(a,PurePosixPath) and type(b)is str:return a/b\n            if isinstance(n.op,ast.Add) and type(a)is type(b)is str:return a+b\n            raise Unresolved()\n        if isinstance(n,ast.JoinedStr):\n            out=\'\'\n            for v in n.values:\n                if isinstance(v,ast.Constant) and type(v.value)is str:out+=v.value\n                elif isinstance(v,ast.FormattedValue) and v.conversion==-1 and v.format_spec is None:\n                    x=self.value(v.value,scope)\n                    if type(x) not in (str,int) and not isinstance(x,PurePosixPath):raise Unresolved()\n                    out+=str(x)\n                else:raise Unresolved()\n            return out\n        if isinstance(n,ast.Attribute):\n            v=self.value(n.value,scope)\n            if isinstance(v,PurePosixPath) and n.attr==\'parent\':return v.parent\n            if isinstance(v,PurePosixPath) and n.attr==\'parents\':return tuple(v.parents)\n            raise Unresolved()\n        if isinstance(n,ast.Subscript):\n            v=self.value(n.value,scope);i=self.value(n.slice,scope)\n            if type(v)is tuple and type(i)is int and 0<=i<16:return v[i]\n            raise Unresolved()\n        if isinstance(n,ast.BoolOp) and isinstance(n.op,ast.Or):\n            for v in n.values:\n                value=self.value(v,scope)\n                if value:return value\n            return value\n        if isinstance(n,ast.Call):\n            name=self.fullname(n.func)\n            if n.keywords:raise Unresolved()\n            args=[self.value(x,scope) for x in n.args]\n            if name==\'pathlib.Path\' and len(args)==1 and type(args[0])is str:return PurePosixPath(args[0])\n            if name==\'str\' and len(args)==1 and (type(args[0])in(str,int) or isinstance(args[0],PurePosixPath)):return str(args[0])\n            if name in (\'os.getenv\',\'os.environ.get\') and len(args)in(1,2) and args[0]==\'TRADING_DATABASE_URL\':return args[1] if len(args)==2 else None\n            if name==\'os.path.dirname\' and len(args)==1 and type(args[0])is str:return os.path.dirname(args[0])\n            if name==\'os.path.join\' and args and all(type(x)is str for x in args):return os.path.join(*args)\n            if name==\'os.path.abspath\' and len(args)==1 and type(args[0])is str:return os.path.normpath(os.path.join(self.cwd,args[0]))\n            if name==\'os.getcwd\' and not args:return self.cwd\n            if isinstance(n.func,ast.Attribute) and n.func.attr in (\'resolve\',\'absolute\') and not args:\n                path=self.value(n.func.value,scope)\n                if isinstance(path,PurePosixPath):return PurePosixPath(os.path.normpath(os.path.join(self.cwd,str(path))))\n            if isinstance(n.func,ast.Name) and n.func.id in self.functions and not args and self.depth<8:\n                f=self.functions[n.func.id]\n                if f.args.args or f.args.posonlyargs or f.args.kwonlyargs or f.args.vararg or f.args.kwarg:raise Unresolved()\n                local=dict(self.globals);self.depth+=1\n                try:\n                    for statement in f.body:\n                        if isinstance(statement,(ast.Assign,ast.AnnAssign)):self.assign(statement,local)\n                        elif isinstance(statement,ast.Return):return self.value(statement.value,local)\n                        elif isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Constant):continue\n                        else:raise Unresolved()\n                finally:self.depth-=1\n            raise Unresolved()\n        raise Unresolved()\n\n    def factories(self):\n        rows=[]\n        for block in [self.tree]+list(self.functions.values()):\n            scope=dict(self.globals)\n            if isinstance(block,ast.FunctionDef):self.defaults(block,scope)\n            for node in block.body:\n                self.assign(node,scope)\n                # Only direct statement expressions; no pretending to resolve arbitrary control flow.\n                for call in ast.walk(node):\n                    if not isinstance(call,ast.Call) or self.fullname(call.func)!=\'sqlalchemy.create_engine\':continue\n                    value=None\n                    try:\n                        value=self.value(call.args[0],scope) if call.args else None\n                    except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):pass\n                    rows.append((call.lineno,value if type(value)is str else None))\n        # Module walk also visits function bodies: keep resolved function-local result over unresolved duplicate.\n        unique={}\n        for line,value in rows:\n            if line not in unique or value is not None:unique[line]=value\n        return sorted(unique.items())\n\nimport datetime,hashlib,json,re,stat,urllib.parse\ndef bounded_read(path, limit):\n    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)\n    try:\n        raw = b\'\'\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        if len(raw) > limit:\n            raise ValueError(\'INPUT_BOUND\')\n        return raw\n    finally:\n        os.close(fd)\n\ndef start_ticks(pid):\n    raw = bounded_read(\'/proc/\' + str(pid) + \'/stat\', 8192)\n    return int(raw[raw.rfind(b\')\') + 2:].split()[19])\n\ndef locate(value, kind, cwd):\n    if type(value) is not str or not value or \'\\x00\' in value:\n        return (\'UNRESOLVED\', None)\n    if kind == \'URL\':\n        m = re.match(\'^sqlite(?:\\\\+pysqlite)?:///\', value)\n        if not m:\n            return (\'NON_SQLITE_OR_UNSUPPORTED_URL\', None)\n        value = value[m.end():]\n        if \'?\' in value or \'#\' in value or value.startswith(\'file:\'):\n            return (\'URI_OPTIONS_UNRESOLVED\', None)\n        value = urllib.parse.unquote(value)\n        if not value or value == \':memory:\':\n            return (\'NON_FILE_SQLITE\', None)\n    if not value.startswith(\'/\'):\n        if not cwd.startswith(\'/\'):\n            return (\'RELATIVE_CWD_UNRESOLVED\', None)\n        value = os.path.join(cwd, value)\n    if \'\\x00\' in value:\n        return (\'UNRESOLVED\', None)\n    return (\'FILE_CANDIDATE\', os.path.normpath(value))\n\ndef descriptor(path):\n    try:\n        s = os.lstat(path)\n    except FileNotFoundError:\n        return {\'state\': \'MISSING\'}\n    except OSError:\n        return {\'state\': \'METADATA_UNREADABLE\'}\n    if stat.S_ISLNK(s.st_mode):\n        return {\'state\': \'SYMLINK_UNRESOLVED\'}\n    if not stat.S_ISREG(s.st_mode):\n        return {\'state\': \'NOT_REGULAR\'}\n    return {\'state\': \'REGULAR_METADATA_CANDIDATE\', \'device\': s.st_dev, \'inode\': s.st_ino, \'uid\': s.st_uid, \'gid\': s.st_gid, \'mode\': stat.S_IMODE(s.st_mode), \'bytes\': s.st_size, \'nlink\': s.st_nlink}\n\ndef read_at(directory, name, limit):\n    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)\n    try:\n        before = os.fstat(fd)\n        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:\n            raise RuntimeError(\'SOURCE_TYPE_OR_SIZE\')\n        raw = b\'\'\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        after = os.fstat(fd)\n        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)\n        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:\n            raise RuntimeError(\'SOURCE_DRIFT\')\n        return raw\n    finally:\n        os.close(fd)\n\nEXPECTED_SOURCE=\'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece\'\nIDENTITIES=((\'portal\',3082952,248360883),(\'contact\',1903204,179522510),(\'customer_service\',1875349,178615731))\n\ndef shape(node,depth=0):\n    if depth>5:return {\'kind\':\'DEPTH_BOUND\'}\n    if isinstance(node,ast.Constant):return {\'kind\':\'Constant\',\'literal_type\':type(node.value).__name__}\n    row={\'kind\':type(node).__name__}\n    if isinstance(node,ast.Name):row[\'name\']=node.id\n    elif isinstance(node,ast.Attribute):row[\'name\']=node.attr\n    children=list(ast.iter_child_nodes(node))\n    if children:row[\'children\']=[shape(c,depth+1) for c in children[:8]]\n    return row\n\ndef observe(expected,nonce):\n    assert os.geteuid()==0 and os.uname().nodename==expected==\'iZ6wee8q9z4t03hvqumwfhZ\'\n    root=os.open(\'/opt/trading-system\',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)\n    try:\n        d=os.open(\'database\',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=root)\n        try:raw=read_at(d,\'connection.py\',1048576)\n        finally:os.close(d)\n    finally:os.close(root)\n    digest=hashlib.sha256(raw).hexdigest()\n    assert digest==EXPECTED_SOURCE,\'DATABASE_SOURCE_HASH_CHANGED_UNKNOWN_NO_RETRY\'\n    tree=ast.parse(raw)\n    expressions=[]\n    imported=[]\n    for n in ast.walk(tree):\n        if isinstance(n,(ast.Import,ast.ImportFrom)):\n            if isinstance(n,ast.ImportFrom) and n.module:imported.append(n.module)\n            elif isinstance(n,ast.Import):imported.extend(a.name for a in n.names)\n        if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Name) and n.func.id==\'create_engine\') or (isinstance(n.func,ast.Attribute) and n.func.attr==\'create_engine\')):\n            expressions.append({\'line\':n.lineno,\'expression\':shape(n.args[0]) if n.args else {\'kind\':\'NO_POSITIONAL_ARGUMENT\'}})\n    assert len(expressions)<=16\n    assert len(json.dumps(expressions))<12000\n    resolution_nodes=[]\n    for node in ast.walk(tree):\n        selected=(isinstance(node,(ast.Assign,ast.AnnAssign)) and any(isinstance(x,ast.Name) and x.id==\'database_url\' and isinstance(x.ctx,ast.Store) for x in ast.walk(node))) or isinstance(node,ast.Return)\n        if selected and len(resolution_nodes)<12:\n            candidate={\'line\':node.lineno,\'expression\':shape(node)}\n            if len(json.dumps(resolution_nodes+[candidate]))<8000:resolution_nodes.append(candidate)\n    contexts=[]\n    for role,pid,ticks in IDENTITIES:\n        row={\'role\':role,\'pid\':pid,\'start_ticks\':ticks,\'status\':\'UNKNOWN\',\'factories\':[]}\n        try:\n            assert start_ticks(pid)==ticks\n            assert os.readlink(\'/proc/\'+str(pid)+\'/root\')==\'/\'\n            cwd=os.readlink(\'/proc/\'+str(pid)+\'/cwd\')\n            interpreter=Defaults(raw,\'/opt/trading-system/database/connection.py\',cwd)\n            factories=interpreter.factories();assert len(factories)<=16\n            for line,value in factories:\n                status,path=locate(value,\'URL\',cwd)\n                data=[] if path is None else [{\'part\':part,\'metadata\':descriptor(path+suffix)} for part,suffix in ((\'MAIN\',\'\'),(\'WAL\',\'-wal\'),(\'SHM\',\'-shm\'))]\n                row[\'factories\'].append({\'line\':line,\'status\':status,\'data\':data})\n            assert start_ticks(pid)==ticks\n            row[\'status\']=\'SOURCE_DEFAULT_CANDIDATES_OBSERVED\'\n        except Exception:row[\'factories\']=[];row[\'status\']=\'PROCESS_OR_DEFAULT_RESOLUTION_UNKNOWN\'\n        contexts.append(row)\n    assert all(re.fullmatch(\'[A-Za-z_][A-Za-z0-9_.]{0,180}\',x) for x in imported)\n    return {\'scope\':\'PR99_PINNED_SOURCE_DEFAULT_DATABASE_CANDIDATES_NOT_EFFECTIVE_CONFIG\',\'hostname\':expected,\'nonce\':nonce,\'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'source_sha256\':digest,\'imports\':sorted(set(imported)),\'factory_expressions\':expressions,\'resolution_nodes\':resolution_nodes,\'contexts\':contexts,\'private_values_disclosed\':False,\'database_opened\':False,\'service_actions\':0,\'business_requests\':0,\'business_source_imports\':0,\'authoritative_writer\':\'UNKNOWN\',\'enforced_fence\':\'UNKNOWN\',\'limitations\':[\'SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIG\',\'ENV_ABSENCE_ASSUMED_ONLY_TO_CALCULATE_DEFAULT_NOT_CURRENT_ENV_PROOF\',\'ANCESTOR_BINDING_NOT_PRODUCTION_PATHGUARD\',\'ALL_WRITERS_AND_FENCE_NOT_PROVEN\']}\n\nif __name__==\'__main__\':\n    print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)\n'
ACTIVE = ('Pending','Running','Stopping')
TERMINAL = frozenset(('Invalid','Aborted','Success','Failed','Error','Timeout','Cancelled','Terminated'))
ID = re.compile(r'[A-Za-z0-9_-]{1,180}')
ALLOWED_ACTIONS = {'AssumeRole','DescribeCommandInvocations','RunCommand','DescribeInvocationResult'}
original_rpc = rpc


def bounded_rpc(endpoint, version, action, credentials, **params):
    if action not in ALLOWED_ACTIONS:
        raise Hold('RPC_ACTION_REJECTED')
    return original_rpc(endpoint, version, action, credentials, **params)


def project_invocations(data, instance, status):
    if type(data) is not dict or type(data.get('TotalCount')) is not int or data['TotalCount'] < 0:
        raise Hold('INVOCATION_LIST_SCHEMA')
    entries = data.get('CommandInvocations')
    if type(entries) is not list or len(entries) > 50:
        raise Hold('INVOCATION_LIST_SCHEMA')
    projected=[]
    for item in entries:
        if type(item) is not dict or type(item.get('InvokeId')) is not str or not ID.fullmatch(item['InvokeId']):
            raise Hold('INVOCATION_ID_REJECTED')
        peers=item.get('InvokeInstances')
        if type(peers) is not list:
            raise Hold('INVOCATION_PEERS_SCHEMA')
        selected=[p for p in peers if type(p) is dict and p.get('InstanceId') == instance]
        if len(selected)!=1:
            raise Hold('INVOCATION_TARGET_NOT_PROVEN')
        actual=selected[0].get('InvocationStatus')
        if actual not in ACTIVE and actual not in TERMINAL:
            raise Hold('INVOCATION_STATUS_UNKNOWN')
        # Never retain CommandContent, Output, ErrorInfo, Parameters or any other raw fields.
        projected.append({'invoke_id':item['InvokeId'],'status':actual})
    return data['TotalCount'],projected


def active_invocations(host, credentials, call=bounded_rpc):
    name,role,region,instance,expected=host
    endpoint='swas.'+region+'.aliyuncs.com'
    rows=[]
    for status in ACTIVE:
        expected_total=None
        for page in range(1,6):
            response=call(endpoint,'2020-06-01','DescribeCommandInvocations',credentials,
                RegionId=region,InstanceId=instance,InvocationStatus=status,
                PageNumber=page,PageSize=50)
            total,items=project_invocations(response,instance,status)
            if expected_total is not None and total!=expected_total:
                raise Hold('INVOCATION_LIST_CHANGED_RECHECK_REQUIRED')
            expected_total=total
            rows.extend(items)
            if page*50>=total:break
            if not items:raise Hold('INVOCATION_PAGINATION_INCOMPLETE')
        else:
            raise Hold('INVOCATION_PAGINATION_BOUND_HOLD')
    # This is an observed API list, not a fence or exclusive Writer assignment.
    return sorted({r['invoke_id']:r for r in rows}.values(),key=lambda x:x['invoke_id'])


def shell_for(expected,nonce):
    program='EXPECTED='+repr(expected)+'\nNONCE='+repr(nonce)+'\n'+HOST_PROGRAM
    payload=base64.b64encode(zlib.compress(program.encode(),9)).decode()
    digest=hashlib.sha256(program.encode()).hexdigest()
    bootstrap="import base64,zlib,hashlib; b=zlib.decompress(base64.b64decode("+repr(payload)+")); assert hashlib.sha256(b).hexdigest()=="+repr(digest)+"; exec(compile(b,'<pr99-readonly-recovery>','exec'))"
    shell="#!/bin/sh\nset -eu\n/usr/bin/python3.11 -I -B - <<'PR99_READONLY'\n"+bootstrap+"\nPR99_READONLY\n"
    if len(shell.encode())>8192:raise Hold('COMMAND_LENGTH')
    return shell


"""Strict public metadata boundary for the fixed observer, not an admission."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('DEFAULT_DATABASE_CONTRACT')
    def fields(v,keys):need(type(v)is dict and set(v)==set(keys.split()))
    def integer(v):need(type(v)is int and 0<=v<2**64)
    fields(d,'scope hostname nonce observed_at source_sha256 imports factory_expressions resolution_nodes contexts private_values_disclosed database_opened service_actions business_requests business_source_imports authoritative_writer enforced_fence limitations')
    need(d['scope']=='PR99_PINNED_SOURCE_DEFAULT_DATABASE_CANDIDATES_NOT_EFFECTIVE_CONFIG' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    need(d['source_sha256']=='58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece')
    need(d['private_values_disclosed']is False and d['database_opened']is False and d['authoritative_writer']==d['enforced_fence']=='UNKNOWN')
    for key in ('service_actions','business_requests','business_source_imports'):need(type(d[key])is int and d[key]==0)
    need(d['limitations']==['SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIG','ENV_ABSENCE_ASSUMED_ONLY_TO_CALCULATE_DEFAULT_NOT_CURRENT_ENV_PROOF','ANCESTOR_BINDING_NOT_PRODUCTION_PATHGUARD','ALL_WRITERS_AND_FENCE_NOT_PROVEN'])
    need(type(d['imports'])is list and len(d['imports'])<=64)
    for module in d['imports']:need(type(module)is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_.]{0,180}',module))
    def expression(value,depth=0):
        need(type(value)is dict and depth<=7 and set(value)<=set(('kind','name','children','literal_type')))
        need(type(value.get('kind'))is str and re.fullmatch('[A-Za-z_]{1,80}',value['kind']))
        if 'name' in value:need(type(value['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,100}',value['name']))
        if 'literal_type' in value:need(value['literal_type'] in ('str','int','float','bool','NoneType','bytes','complex','ellipsis'))
        if 'children' in value:
            need(type(value['children'])is list and len(value['children'])<=8)
            for child in value['children']:expression(child,depth+1)
    need(type(d['factory_expressions'])is list and len(d['factory_expressions'])<=16 and len(json.dumps(d['factory_expressions']))<12000)
    for item in d['factory_expressions']:
        fields(item,'line expression');integer(item['line']);expression(item['expression'])
    need(type(d['resolution_nodes'])is list and len(d['resolution_nodes'])<=12 and len(json.dumps(d['resolution_nodes']))<8000)
    for item in d['resolution_nodes']:
        fields(item,'line expression');integer(item['line']);expression(item['expression'])
    need(type(d['contexts'])is list and len(d['contexts'])==3)
    for row,(role,pid,ticks) in zip(d['contexts'],(('portal',3082952,248360883),('contact',1903204,179522510),('customer_service',1875349,178615731))):
        fields(row,'role pid start_ticks status factories');need(row['role']==role and row['pid']==pid and row['start_ticks']==ticks)
        need(row['status'] in ('UNKNOWN','SOURCE_DEFAULT_CANDIDATES_OBSERVED','PROCESS_OR_DEFAULT_RESOLUTION_UNKNOWN'))
        need(type(row['factories'])is list and len(row['factories'])<=16)
        if row['status']!='SOURCE_DEFAULT_CANDIDATES_OBSERVED':need(not row['factories'])
        for f in row['factories']:
            fields(f,'line status data');integer(f['line'])
            need(f['status'] in ('UNRESOLVED','NON_SQLITE_OR_UNSUPPORTED_URL','URI_OPTIONS_UNRESOLVED','NON_FILE_SQLITE','RELATIVE_CWD_UNRESOLVED','FILE_CANDIDATE'))
            need(type(f['data'])is list and len(f['data'])==(3 if f['status']=='FILE_CANDIDATE' else 0))
            for part,item in zip(('MAIN','WAL','SHM'),f['data']):
                fields(item,'part metadata');need(item['part']==part);m=item['metadata']
                need(type(m)is dict and m.get('state') in ('MISSING','METADATA_UNREADABLE','SYMLINK_UNRESOLVED','NOT_REGULAR','REGULAR_METADATA_CANDIDATE'))
                fields(m,'state device inode uid gid mode bytes nlink' if m['state']=='REGULAR_METADATA_CANDIDATE' else 'state')
                if m['state']=='REGULAR_METADATA_CANDIDATE':
                    for key in ('device','inode','uid','gid','mode','bytes','nlink'):integer(m[key])
    return d

def decode_receipt(output,expected,nonce):
    if type(output)is not str or len(output)>30000:raise Hold('DATABASE_DEFAULT_OUTPUT_BOUND')
    try:
        try:value=json.loads(output)
        except ValueError:value=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(value,expected,nonce)
    except Exception:raise Hold('DATABASE_DEFAULT_OUTPUT_REJECTED') from None

def probe_current(host,master):
    name,role,region,instance,expected=host
    row={'host':name,'instance_id':instance,'status':'HOLD','host_commands':0,'run_command_attempted':False,'service_actions':0,
         'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN'}
    try:
        c=bounded_rpc('sts.aliyuncs.com','2015-04-01','AssumeRole',master,
            RoleArn=role,RoleSessionName='pr99-resume-'+uuid.uuid4().hex[:16],DurationSeconds=900)['Credentials']
        credentials=(c['AccessKeyId'],c['AccessKeySecret'],c['SecurityToken'])
        if not all(type(v) is str and v and '\r' not in v and '\n' not in v for v in credentials):
            raise Hold('CREDENTIAL_RESPONSE_INVALID')
        for value in credentials:print('::add-mask::'+value,flush=True)
        row['sts']='PASS_CURRENT'
        row['nonterminal_invocations']=active_invocations(host,credentials)
        row['cloud_query']='PASS_CURRENT_OBSERVATION_NOT_FENCE'
        if any(x['status'] in ACTIVE for x in row['nonterminal_invocations']):
            raise Hold('EXISTING_INFLIGHT_PRESERVED_NO_NEW_HOST_COMMAND')
        nonce=uuid.uuid4().hex
        shell=shell_for(expected,nonce)
        # Local job claim stops repeat dispatch in this process; no production state is created.
        # A lost InvokeId remains UNKNOWN. Workflow reruns are rejected before credentials.
        claim=Path('pr99-database-default-r2-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-database-default-r2-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_DATABASE_DEFAULT_R2_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            response=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','DescribeInvocationResult',credentials,
                RegionId=region,InstanceId=instance,InvokeId=invoke)
            detail=response.get('InvocationResult')
            if type(detail) is not dict or detail.get('InstanceId')!=instance or detail.get('InvokeId')!=invoke:
                raise Hold('RESULT_IDENTITY_UNKNOWN_NO_RETRY')
            state=detail.get('InvocationStatus')
            if state in ACTIVE:time.sleep(5);continue
            row['invocation_status']=safe(state)
            if state!='Success' or detail.get('ExitCode')!=0:
                raise Hold('READONLY_COMMAND_FAILED_NO_RETRY')
            row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)
            row['host_commands']=1
            row['status']='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN'
            return row
        raise Hold('READONLY_RESULT_UNKNOWN_NO_RETRY')
    except Hold as e:row['error_code']=safe(str(e))
    except Exception:row['error_code']='UNEXPECTED_UNKNOWN_NO_RETRY'
    return row


TEST_PROGRAM='import os\nimport tempfile\nimport unittest\n\n\nclass DefaultTests(unittest.TestCase):\n    def values(self,s):return Defaults(s,\'/opt/trading-system/database/connection.py\',\'/opt/trading-system\').factories()\n    def test_literal(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ne=create_engine("sqlite:///a.db")\'),[(2,\'sqlite:///a.db\')])\n    def test_alias(self):self.assertEqual(self.values(\'import sqlalchemy as sa\\ne=sa.create_engine("sqlite:///a.db")\'),[(2,\'sqlite:///a.db\')])\n    def test_path_default(self):\n        s=\'from pathlib import Path\\nimport os\\nfrom sqlalchemy import create_engine\\nROOT=Path(__file__).resolve().parents[1]\\nURL=os.getenv("TRADING_DATABASE_URL",f"sqlite:///{ROOT / \\\'data\\\' / \\\'trading.db\\\'}")\\ne=create_engine(URL)\'\n        self.assertEqual(self.values(s),[(6,\'sqlite:////opt/trading-system/data/trading.db\')])\n    def test_simple_function(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef url():\\n return "sqlite:///a.db"\\ne=create_engine(url())\'),[(4,\'sqlite:///a.db\')])\n    def test_local(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef engine():\\n url="sqlite:///a.db"\\n return create_engine(url)\'),[(4,\'sqlite:///a.db\')])\n    def test_or_default(self):self.assertEqual(self.values(\'import os\\nfrom sqlalchemy import create_engine\\ne=create_engine(os.getenv("TRADING_DATABASE_URL") or "sqlite:///a.db")\'),[(3,\'sqlite:///a.db\')])\n    def test_other_environment_not_assumed_absent(self):self.assertEqual(self.values(\'import os\\nfrom sqlalchemy import create_engine\\ne=create_engine(os.getenv("SECRET","sqlite:///a.db"))\'),[(3,None)])\n    def test_no_arbitrary_call(self):\n        with tempfile.TemporaryDirectory() as d:\n            p=d+\'/must-not-exist\'\n            s=f\'from sqlalchemy import create_engine\\nimport os\\ne=create_engine(os.system("touch {p}"))\'\n            self.assertEqual(self.values(s),[(3,None)]);self.assertFalse(os.path.exists(p))\n    def test_no_source_import(self):self.assertEqual(self.values(\'import missing_business_module\\nfrom sqlalchemy import create_engine\\ne=create_engine("sqlite:///a.db")\'),[(3,\'sqlite:///a.db\')])\n    def test_no_comprehension(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ne=create_engine([x for x in "secret"])\'),[(2,None)])\n    def test_conditional_not_resolved(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ne=create_engine("sqlite:///a.db" if True else "sqlite:///b.db")\'),[(2,None)])\n    def test_keywords_not_evaluated(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ne=create_engine(str(x="secret"))\'),[(2,None)])\n    def test_nested_function_rejected(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef url():\\n if True:return "sqlite:///a.db"\\ne=create_engine(url())\'),[(4,None)])\n    def test_arbitrary_attribute_rejected(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ne=create_engine("x".__class__)\'),[(2,None)])\n\n\n    def test_optional_parameter_or_default(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef engine(database_url=None):\\n database_url=database_url or "sqlite:///a.db"\\n return create_engine(database_url)\'),[(4,\'sqlite:///a.db\')])\n    def test_optional_parameter_if_none(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef engine(database_url=None):\\n if database_url is None:database_url="sqlite:///a.db"\\n return create_engine(database_url)\'),[(4,\'sqlite:///a.db\')])\n    def test_unknown_parameter_stays_unresolved(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef engine(database_url):\\n if database_url is None:database_url="sqlite:///a.db"\\n return create_engine(database_url)\'),[(4,None)])\n    def test_keyword_default(self):self.assertEqual(self.values(\'from sqlalchemy import create_engine\\ndef engine(*,database_url="sqlite:///a.db"):\\n return create_engine(database_url)\'),[(3,\'sqlite:///a.db\')])\n\n'

def self_test():
    namespace={'__name__':'default_locator_definitions'};exec(compile(HOST_PROGRAM,'fixed-default-definitions','exec'),namespace)
    context={'__name__':'default_tests','Defaults':namespace['Defaults']}
    exec(compile(TEST_PROGRAM,'ordinary_expression_tests','exec'),context)
    suite=context['unittest'].defaultTestLoader.loadTestsFromTestCase(context['DefaultTests'])
    result=context['unittest'].TextTestRunner(verbosity=1).run(suite)
    assert result.wasSuccessful() and result.testsRun==18
    hidden=namespace['shape'](namespace['ast'].parse("secret='PRIVATE_VALUE'").body[0])
    assert 'PRIVATE_VALUE' not in json.dumps(hidden)
    expected='iZ6wee8q9z4t03hvqumwfhZ'
    valid={'scope':'PR99_PINNED_SOURCE_DEFAULT_DATABASE_CANDIDATES_NOT_EFFECTIVE_CONFIG','hostname':expected,'nonce':'a'*32,'observed_at':'2026-10-18T13:00:00Z','source_sha256':namespace['EXPECTED_SOURCE'],'imports':['sqlalchemy'],'factory_expressions':[{'line':1,'expression':hidden}],'resolution_nodes':[],'contexts':[{'role':r,'pid':p,'start_ticks':t,'status':'SOURCE_DEFAULT_CANDIDATES_OBSERVED','factories':[]} for r,p,t in namespace['IDENTITIES']],'private_values_disclosed':False,'database_opened':False,'service_actions':0,'business_requests':0,'business_source_imports':0,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN','limitations':['SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIG','ENV_ABSENCE_ASSUMED_ONLY_TO_CALCULATE_DEFAULT_NOT_CURRENT_ENV_PROOF','ANCESTOR_BINDING_NOT_PRODUCTION_PATHGUARD','ALL_WRITERS_AND_FENCE_NOT_PROVEN']}
    assert decode_receipt(json.dumps(valid),expected,'a'*32)==valid
    mutations=(lambda x:x.update(private='SECRET'),lambda x:x.update(enforced_fence='PASS'),lambda x:x.update(service_actions=True),lambda x:x.update(private_values_disclosed=True),lambda x:x['factory_expressions'][0]['expression'].update(value='PRIVATE_VALUE'),lambda x:x['contexts'][0].update(pid=1),lambda x:x.update(database_opened=True),lambda x:x.update(source_sha256='0'*64))
    for mutate in mutations:
        bad=json.loads(json.dumps(valid));mutate(bad)
        try:decode_receipt(json.dumps(bad),expected,'a'*32)
        except Hold:pass
        else:raise AssertionError('PRIVATE_OR_FALSE_PROOF_ACCEPTED')
    assert len(HOSTS)==1
    shell_for(expected,'f'*32)
    print('PR99_DATABASE_DEFAULT_18_EXPRESSION_TESTS_8_REJECTIONS_AND_LITERAL_REDACTION_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-database-default-r2-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_DATABASE_DEFAULT_R2_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_DATABASE_DEFAULT_R2_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)

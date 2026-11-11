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

HOST_PROGRAM='"""Interpret a deliberately small source-expression subset without executing it.\n\nResults are SOURCE DEFAULT candidates. They never establish effective runtime\nconfiguration, Writer ownership, admission, SQLite format or a source fence.\n"""\nimport ast\nimport os\nfrom pathlib import PurePosixPath\n\nclass Unresolved(Exception):\n    pass\n\nclass Defaults:\n    def __init__(self, raw, filename, cwd):\n        self.tree=ast.parse(raw)\n        self.filename=filename;self.cwd=cwd\n        self.functions={n.name:n for n in self.tree.body if isinstance(n,ast.FunctionDef)}\n        self.imports={}\n        for node in self.tree.body:\n            if isinstance(node,ast.Import):\n                for a in node.names:self.imports[a.asname or a.name]=a.name\n            elif isinstance(node,ast.ImportFrom) and node.module:\n                for a in node.names:self.imports[a.asname or a.name]=node.module+\'.\'+a.name\n        self.globals={\'__file__\':filename};self.depth=0\n        for n in self.tree.body:\n            self.assign(n,self.globals)\n\n    def fullname(self,node):\n        if isinstance(node,ast.Name):return self.imports.get(node.id,node.id)\n        if isinstance(node,ast.Attribute):return self.fullname(node.value)+\'.\'+node.attr\n        return \'\'\n\n    def defaults(self,function,scope):\n        positional=function.args.posonlyargs+function.args.args\n        for arg in positional:scope[arg.arg]=Unresolved\n        for arg,node in zip(positional[len(positional)-len(function.args.defaults):],function.args.defaults):\n            try:scope[arg.arg]=self.value(node,scope)\n            except Exception:scope[arg.arg]=Unresolved\n        for arg,node in zip(function.args.kwonlyargs,function.args.kw_defaults):\n            try:scope[arg.arg]=self.value(node,scope)\n            except Exception:scope[arg.arg]=Unresolved\n        return scope\n\n    def assign(self,node,scope):\n        if isinstance(node,ast.If):\n            try:\n                condition=self.value(node.test,scope)\n                if type(condition)is not bool:raise Unresolved()\n                for statement in (node.body if condition else node.orelse):self.assign(statement,scope)\n            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):\n                for child in ast.walk(node):\n                    if isinstance(child,ast.Name) and isinstance(child.ctx,ast.Store):scope[child.id]=Unresolved\n        if isinstance(node,(ast.Assign,ast.AnnAssign)):\n            targets=node.targets if isinstance(node,ast.Assign) else [node.target]\n            try:value=self.value(node.value,scope)\n            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):value=Unresolved\n            for target in targets:\n                if isinstance(target,ast.Name):scope[target.id]=value\n\n    def value(self,n,scope):\n        if n is None:raise Unresolved()\n        if isinstance(n,ast.Constant) and type(n.value) in (str,int,bool,type(None)):return n.value\n        if isinstance(n,ast.Name):\n            v=scope.get(n.id,Unresolved)\n            if v is Unresolved:raise Unresolved()\n            return v\n        if isinstance(n,ast.Compare) and len(n.ops)==len(n.comparators)==1:\n            a=self.value(n.left,scope);b=self.value(n.comparators[0],scope)\n            if isinstance(n.ops[0],ast.Is) and (a is None or b is None):return a is b\n            if isinstance(n.ops[0],ast.IsNot) and (a is None or b is None):return a is not b\n            raise Unresolved()\n        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not self.value(n.operand,scope)\n        if isinstance(n,ast.BinOp):\n            a=self.value(n.left,scope);b=self.value(n.right,scope)\n            if isinstance(n.op,ast.Div) and isinstance(a,PurePosixPath) and type(b)is str:return a/b\n            if isinstance(n.op,ast.Add) and type(a)is type(b)is str:return a+b\n            raise Unresolved()\n        if isinstance(n,ast.JoinedStr):\n            out=\'\'\n            for v in n.values:\n                if isinstance(v,ast.Constant) and type(v.value)is str:out+=v.value\n                elif isinstance(v,ast.FormattedValue) and v.conversion==-1 and v.format_spec is None:\n                    x=self.value(v.value,scope)\n                    if type(x) not in (str,int) and not isinstance(x,PurePosixPath):raise Unresolved()\n                    out+=str(x)\n                else:raise Unresolved()\n            return out\n        if isinstance(n,ast.Attribute):\n            v=self.value(n.value,scope)\n            if type(v)is dict and n.attr in v:return v[n.attr]\n            if isinstance(v,PurePosixPath) and n.attr==\'parent\':return v.parent\n            if isinstance(v,PurePosixPath) and n.attr==\'parents\':return tuple(v.parents)\n            raise Unresolved()\n        if isinstance(n,ast.Subscript):\n            v=self.value(n.value,scope);i=self.value(n.slice,scope)\n            if type(v)is tuple and type(i)is int and 0<=i<16:return v[i]\n            raise Unresolved()\n        if isinstance(n,ast.BoolOp) and isinstance(n.op,ast.Or):\n            for v in n.values:\n                value=self.value(v,scope)\n                if value:return value\n            return value\n        if isinstance(n,ast.Call):\n            name=self.fullname(n.func)\n            if n.keywords:raise Unresolved()\n            args=[self.value(x,scope) for x in n.args]\n            if name==\'pathlib.Path\' and len(args)==1 and type(args[0])is str:return PurePosixPath(args[0])\n            if name==\'str\' and len(args)==1 and (type(args[0])in(str,int) or isinstance(args[0],PurePosixPath)):return str(args[0])\n            if name in (\'os.getenv\',\'os.environ.get\') and len(args)in(1,2) and args[0]==\'TRADING_DATABASE_URL\':return args[1] if len(args)==2 else None\n            if name==\'os.path.dirname\' and len(args)==1 and type(args[0])is str:return os.path.dirname(args[0])\n            if name==\'os.path.join\' and args and all(type(x)is str for x in args):return os.path.join(*args)\n            if name==\'os.path.abspath\' and len(args)==1 and type(args[0])is str:return os.path.normpath(os.path.join(self.cwd,args[0]))\n            if name==\'os.getcwd\' and not args:return self.cwd\n            if isinstance(n.func,ast.Attribute) and n.func.attr in (\'resolve\',\'absolute\') and not args:\n                path=self.value(n.func.value,scope)\n                if isinstance(path,PurePosixPath):return PurePosixPath(os.path.normpath(os.path.join(self.cwd,str(path))))\n            if isinstance(n.func,ast.Name) and n.func.id in self.functions and not args and self.depth<8:\n                f=self.functions[n.func.id]\n                if f.args.args or f.args.posonlyargs or f.args.kwonlyargs or f.args.vararg or f.args.kwarg:raise Unresolved()\n                local=dict(self.globals);self.depth+=1\n                try:\n                    for statement in f.body:\n                        if isinstance(statement,(ast.Assign,ast.AnnAssign)):self.assign(statement,local)\n                        elif isinstance(statement,ast.Return):return self.value(statement.value,local)\n                        elif isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Constant):continue\n                        else:raise Unresolved()\n                finally:self.depth-=1\n            raise Unresolved()\n        raise Unresolved()\n\n    def factories(self):\n        rows=[]\n        for block in [self.tree]+list(self.functions.values()):\n            scope=dict(self.globals)\n            if isinstance(block,ast.FunctionDef):self.defaults(block,scope)\n            for node in block.body:\n                self.assign(node,scope)\n                # Only direct statement expressions; no pretending to resolve arbitrary control flow.\n                for call in ast.walk(node):\n                    if not isinstance(call,ast.Call) or self.fullname(call.func)!=\'sqlalchemy.create_engine\':continue\n                    value=None\n                    try:\n                        value=self.value(call.args[0],scope) if call.args else None\n                    except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):pass\n                    rows.append((call.lineno,value if type(value)is str else None))\n        # Module walk also visits function bodies: keep resolved function-local result over unresolved duplicate.\n        unique={}\n        for line,value in rows:\n            if line not in unique or value is not None:unique[line]=value\n        return sorted(unique.items())\n\nimport datetime,hashlib,json,re,stat,urllib.parse,base64,zlib\ndef bounded_read(path, limit):\n    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)\n    try:\n        raw = b\'\'\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        if len(raw) > limit:\n            raise ValueError(\'INPUT_BOUND\')\n        return raw\n    finally:\n        os.close(fd)\n\ndef start_ticks(pid):\n    raw = bounded_read(\'/proc/\' + str(pid) + \'/stat\', 8192)\n    return int(raw[raw.rfind(b\')\') + 2:].split()[19])\n\ndef locate(value, kind, cwd):\n    if type(value) is not str or not value or \'\\x00\' in value:\n        return (\'UNRESOLVED\', None)\n    if kind == \'URL\':\n        m = re.match(\'^sqlite(?:\\\\+pysqlite)?:///\', value)\n        if not m:\n            return (\'NON_SQLITE_OR_UNSUPPORTED_URL\', None)\n        value = value[m.end():]\n        if \'?\' in value or \'#\' in value or value.startswith(\'file:\'):\n            return (\'URI_OPTIONS_UNRESOLVED\', None)\n        value = urllib.parse.unquote(value)\n        if not value or value == \':memory:\':\n            return (\'NON_FILE_SQLITE\', None)\n    if not value.startswith(\'/\'):\n        if not cwd.startswith(\'/\'):\n            return (\'RELATIVE_CWD_UNRESOLVED\', None)\n        value = os.path.join(cwd, value)\n    if \'\\x00\' in value:\n        return (\'UNRESOLVED\', None)\n    return (\'FILE_CANDIDATE\', os.path.normpath(value))\n\ndef descriptor(path):\n    try:\n        s = os.lstat(path)\n    except FileNotFoundError:\n        return {\'state\': \'MISSING\'}\n    except OSError:\n        return {\'state\': \'METADATA_UNREADABLE\'}\n    if stat.S_ISLNK(s.st_mode):\n        return {\'state\': \'SYMLINK_UNRESOLVED\'}\n    if not stat.S_ISREG(s.st_mode):\n        return {\'state\': \'NOT_REGULAR\'}\n    return {\'state\': \'REGULAR_METADATA_CANDIDATE\', \'device\': s.st_dev, \'inode\': s.st_ino, \'uid\': s.st_uid, \'gid\': s.st_gid, \'mode\': stat.S_IMODE(s.st_mode), \'bytes\': s.st_size, \'nlink\': s.st_nlink}\n\ndef read_at(directory, name, limit):\n    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)\n    try:\n        before = os.fstat(fd)\n        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:\n            raise RuntimeError(\'SOURCE_TYPE_OR_SIZE\')\n        raw = b\'\'\n        while len(raw) <= limit:\n            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not chunk:\n                break\n            raw += chunk\n        after = os.fstat(fd)\n        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)\n        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)\n        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:\n            raise RuntimeError(\'SOURCE_DRIFT\')\n        return raw\n    finally:\n        os.close(fd)\n\nEXPECTED_SOURCE=\'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece\'\nIDENTITIES=((\'portal\',3082952,248360883),(\'contact\',1903204,179522510),(\'customer_service\',1875349,178615731))\n\ndef shape(node,depth=0):\n    if depth>5:return {\'kind\':\'DEPTH_BOUND\'}\n    if isinstance(node,ast.Constant):return {\'kind\':\'Constant\',\'literal_type\':type(node.value).__name__}\n    row={\'kind\':type(node).__name__}\n    if isinstance(node,ast.Name):row[\'name\']=node.id\n    elif isinstance(node,ast.Attribute):row[\'name\']=node.attr\n    children=list(ast.iter_child_nodes(node))\n    if children:row[\'children\']=[shape(c,depth+1) for c in children[:8]]\n    return row\n\n\n"""Observe handles to one newly identified source-default database candidate.\nNo database open, data content read, process control, drain, fence or authority.\n"""\nimport os, stat, re, json, datetime\nfrom pathlib import Path\n\nPIN = (64771, 1601016)\n\n\ndef writable_flags(raw):\n    values = [line.partition(b\':\')[2].strip() for line in raw.splitlines() if line.startswith(b\'flags:\')]\n    if len(values) != 1:\n        raise ValueError(\'FD_FLAGS_SCHEMA\')\n    return (int(values[0], 8) & os.O_ACCMODE) in (os.O_WRONLY, os.O_RDWR)\n\n\ndef shared_writable_mapping(line, identities):\n    parts = line.split(None, 5)\n    if len(parts) < 5:\n        return False\n    permissions, device, inode = parts[1], parts[3], parts[4]\n    if len(permissions) != 4 or permissions[1] != \'w\' or permissions[3] != \'s\':\n        return False\n    major, minor = device.split(\':\')\n    return (int(major, 16), int(minor, 16), int(inode)) in identities\n\n\ndef read_meta(path, limit):\n    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)\n    try:\n        raw = b\'\'\n        while len(raw) <= limit:\n            part = os.read(fd, min(65536, limit + 1 - len(raw)))\n            if not part:\n                break\n            raw += part\n        if len(raw) > limit:\n            raise ValueError(\'PROC_METADATA_BOUND\')\n        return raw\n    finally:\n        os.close(fd)\n\n\ndef ticks(process):\n    raw = read_meta(process / \'stat\', 8192)\n    return int(raw[raw.rfind(b\')\')+2:].split()[19])\n\n\ndef observe(expected, nonce):\n    assert os.geteuid() == 0 and os.uname().nodename == expected == \'iZ6wee8q9z4t03hvqumwfhZ\'\n    root = os.open(\'/opt/trading-system/database\', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)\n    try:\n        raw = read_at(root, \'connection.py\', 1048576)\n    finally:\n        os.close(root)\n    assert hashlib.sha256(raw).hexdigest() == \'58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece\'\n    model = Defaults(raw, \'/opt/trading-system/database/connection.py\', \'/opt/trading-system\')\n    status, location = locate(model.globals.get(\'DATABASE_URL\'), \'URL\', \'/opt/trading-system\')\n    assert status == \'FILE_CANDIDATE\'\n    main = os.lstat(location)\n    assert stat.S_ISREG(main.st_mode) and (main.st_dev, main.st_ino) == PIN and main.st_nlink == 1\n    parts, targets = [], {}\n    for role, suffix in ((\'MAIN\',\'\'), (\'WAL\',\'-wal\'), (\'SHM\',\'-shm\'), (\'JOURNAL\',\'-journal\')):\n        try:\n            item = os.lstat(location + suffix)\n        except FileNotFoundError:\n            parts.append({\'part\': role, \'state\': \'MISSING\'})\n            continue\n        assert stat.S_ISREG(item.st_mode) and item.st_nlink == 1\n        targets[(item.st_dev, item.st_ino)] = role\n        parts.append({\'part\': role, \'state\': \'REGULAR\', \'device\': item.st_dev, \'inode\': item.st_ino, \'uid\': item.st_uid, \'gid\': item.st_gid, \'bytes\': item.st_size})\n    mapping_ids = {(os.major(dev), os.minor(dev), ino) for dev, ino in targets}\n    processes = sorted((p for p in Path(\'/proc\').iterdir() if p.name.isdigit()), key=lambda p:int(p.name))\n    assert len(processes) <= 4096\n    counts = {\'processes_seen\':len(processes), \'processes_scanned\':0, \'races\':0, \'unreadable_or_bounded\':0, \'fds_inspected\':0}\n    owners = []\n    for process in processes:\n        try:\n            before = ticks(process)\n            fds = list((process / \'fd\').iterdir())\n            if len(fds) > 4096 or counts[\'fds_inspected\'] + len(fds) > 200000:\n                counts[\'unreadable_or_bounded\'] += 1\n                continue\n            handles = []\n            for fd in fds:\n                counts[\'fds_inspected\'] += 1\n                try:\n                    fs = fd.stat()\n                    part = targets.get((fs.st_dev,fs.st_ino))\n                    if part:\n                        writable = writable_flags(read_meta(process/\'fdinfo\'/fd.name, 8192))\n                        after_fd = fd.stat()\n                        if (after_fd.st_dev,after_fd.st_ino) != (fs.st_dev,fs.st_ino):\n                            raise ProcessLookupError()\n                        handles.append({\'fd\':int(fd.name),\'part\':part,\'writable\':writable})\n                except FileNotFoundError:\n                    counts[\'races\'] += 1\n            maps = read_meta(process/\'maps\', 1048576).decode(\'utf-8\',\'replace\')\n            mappings = sum(shared_writable_mapping(line,mapping_ids) for line in maps.splitlines())\n            candidate = None\n            if handles or mappings:\n                cg = read_meta(process/\'cgroup\',32768).decode(\'utf-8\',\'replace\')\n                units = sorted({segment for line in cg.splitlines() for segment in line.split(\'/\') if re.fullmatch(r\'[A-Za-z0-9_.@-]{1,180}\\.service\',segment)})\n                assert len(handles) <= 256 and len(units) <= 16\n                candidate = {\'pid\':int(process.name),\'start_ticks\':before,\'units\':units,\'handles\':handles,\'shared_writable_mappings\':mappings}\n            if ticks(process) != before:\n                raise ProcessLookupError()\n            if candidate:\n                owners.append(candidate)\n            counts[\'processes_scanned\'] += 1\n        except (FileNotFoundError,ProcessLookupError):\n            counts[\'races\'] += 1\n        except (OSError,ValueError):\n            counts[\'unreadable_or_bounded\'] += 1\n    after = os.lstat(location)\n    assert (after.st_dev,after.st_ino) == PIN and len(owners) <= 64\n    return {\'scope\':\'PR99_EXACT_CREDENTIAL_DB_CANDIDATE_HANDLE_SAMPLE_NOT_FENCE\', \'hostname\':expected,\'nonce\':nonce,\n        \'observed_at\':datetime.datetime.utcnow().isoformat()+\'Z\',\'parts\':parts,\'counts\':counts,\'owners\':owners,\n        \'source_default_candidate_only\':True,\'database_opened\':False,\'business_requests\':0,\'service_actions\':0,\n        \'fence_enforced\':False,\'all_writers_proven\':False,\'inflight_drained\':False,\n        \'limitations\':[\'INSTANT_VISIBLE_PROC_SAMPLE_NOT_IDLE_OR_FUTURE_WRITER_PROOF\',\'SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIGURATION\',\'NO_DATABASE_CONTENT_OR_FORMAT_INSPECTION\',\'NO_FENCE_DRAIN_STOP_OR_CHECKPOINT\']}\n\nif __name__==\'__main__\':\n print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)\n'
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
    if len(shell.encode())>11000:raise Hold('COMMAND_LENGTH')
    return shell


"""Strict public metadata boundary for the fixed observer, not an admission."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
"""Public projection boundary: technical names/counts/hashes only, never authority."""
def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('CREDENTIAL_WRITER_CONTRACT')
    def fields(v,keys):need(type(v)is dict and set(v)==set(keys.split()))
    def integer(v):need(type(v)is int and 0<=v<2**64)
    fields(d,'scope hostname nonce observed_at parts counts owners source_default_candidate_only database_opened business_requests service_actions fence_enforced all_writers_proven inflight_drained limitations')
    need(d['scope']=='PR99_EXACT_CREDENTIAL_DB_CANDIDATE_HANDLE_SAMPLE_NOT_FENCE' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    need(d['source_default_candidate_only']is True)
    for key in ('database_opened','fence_enforced','all_writers_proven','inflight_drained'):need(d[key]is False)
    for key in ('business_requests','service_actions'):need(type(d[key])is int and d[key]==0)
    need(d['limitations']==['INSTANT_VISIBLE_PROC_SAMPLE_NOT_IDLE_OR_FUTURE_WRITER_PROOF','SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIGURATION','NO_DATABASE_CONTENT_OR_FORMAT_INSPECTION','NO_FENCE_DRAIN_STOP_OR_CHECKPOINT'])
    need(type(d['parts'])is list and len(d['parts'])==4)
    for p,part in zip(d['parts'],('MAIN','WAL','SHM','JOURNAL')):
        need(type(p)is dict and p.get('part')==part and p.get('state')in('REGULAR','MISSING'))
        fields(p,'part state device inode uid gid bytes' if p['state']=='REGULAR' else 'part state')
        for key in p:
            if key not in ('part','state'):integer(p[key])
    main=d['parts'][0];need(main['state']=='REGULAR' and (main['device'],main['inode'])==(64771,1601016))
    fields(d['counts'],'processes_seen processes_scanned races unreadable_or_bounded fds_inspected')
    for value in d['counts'].values():integer(value)
    need(d['counts']['processes_seen']<=4096 and d['counts']['processes_scanned']<=d['counts']['processes_seen'] and d['counts']['fds_inspected']<=200000)
    need(type(d['owners'])is list and len(d['owners'])<=64)
    seen=set()
    for p in d['owners']:
        fields(p,'pid start_ticks units handles shared_writable_mappings')
        for key in ('pid','start_ticks','shared_writable_mappings'):integer(p[key])
        need(p['pid'] not in seen);seen.add(p['pid'])
        need(type(p['units'])is list and len(p['units'])<=16)
        for unit in p['units']:need(type(unit)is str and re.fullmatch(r'[A-Za-z0-9_.@-]{1,180}\.service',unit))
        need(type(p['handles'])is list and len(p['handles'])<=256)
        for fd in p['handles']:
            fields(fd,'fd part writable');integer(fd['fd']);need(fd['part']in('MAIN','WAL','SHM','JOURNAL') and type(fd['writable'])is bool)
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=24000:raise ValueError()
        try:value=json.loads(output)
        except ValueError:value=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(value,expected,nonce)
    except Exception:raise Hold('CREDENTIAL_WRITER_RECEIPT_REJECTED') from None

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
        claim=Path('pr99-credential-writer-'+name+'.once')
        with claim.open('x') as f:
            f.write(json.dumps({'host':name,'nonce':nonce,'state':'READONLY_DISPATCH_INTENT'}))
            f.flush();os.fsync(f.fileno())
        row.update(run_command_attempted=True,host_commands='UNKNOWN_UNTIL_TERMINAL_RECEIPT')
        out=bounded_rpc('swas.'+region+'.aliyuncs.com','2020-06-01','RunCommand',credentials,
            RegionId=region,InstanceId=instance,Type='RunShellScript',
            WorkingUser='root',WorkingDir='/root',Timeout=55,
            Name='pr99-credential-writer-v1',CommandContent=shell)
        invoke=out.get('InvokeId')
        if type(invoke) is not str or not ID.fullmatch(invoke):
            raise Hold('DISPATCH_RESULT_UNKNOWN_NO_RETRY')
        row.update(invoke_id=invoke)
        print('PR99_CREDENTIAL_WRITER_INVOKE='+json.dumps({'host':name,'invoke_id':invoke}),flush=True)
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


def self_test():
    n={'__name__':'credential_writer_definitions'};exec(compile(HOST_PROGRAM,'fixed-credential-writer','exec'),n)
    assert n['writable_flags'](b'flags:\t0100002\n') is True
    assert n['writable_flags'](b'flags:\t0100001\n') is True
    assert n['writable_flags'](b'flags:\t0100000\n') is False
    assert n['shared_writable_mapping']('0000-1000 rw-s 0 00:01 123 PRIVATE_PATH',{(0,1,123)}) is True
    assert n['shared_writable_mapping']('0000-1000 rw-p 0 00:01 123 PRIVATE_PATH',{(0,1,123)}) is False
    assert n['shared_writable_mapping']('0000-1000 rw-s 0 00:01 999 PRIVATE_PATH',{(0,1,123)}) is False
    d={'scope':'PR99_EXACT_CREDENTIAL_DB_CANDIDATE_HANDLE_SAMPLE_NOT_FENCE','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-18T14:00:00Z','parts':[{'part':'MAIN','state':'REGULAR','device':64771,'inode':1601016,'uid':1000,'gid':1000,'bytes':46907392}]+[{'part':p,'state':'MISSING'} for p in ('WAL','SHM','JOURNAL')],'counts':{'processes_seen':1,'processes_scanned':1,'races':0,'unreadable_or_bounded':0,'fds_inspected':0},'owners':[],'source_default_candidate_only':True,'database_opened':False,'business_requests':0,'service_actions':0,'fence_enforced':False,'all_writers_proven':False,'inflight_drained':False,'limitations':['INSTANT_VISIBLE_PROC_SAMPLE_NOT_IDLE_OR_FUTURE_WRITER_PROOF','SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIGURATION','NO_DATABASE_CONTENT_OR_FORMAT_INSPECTION','NO_FENCE_DRAIN_STOP_OR_CHECKPOINT']}
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(json.dumps(d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    for change in (lambda x:x.update(database_opened=True),lambda x:x.update(all_writers_proven=True),lambda x:x.update(private='SECRET'),lambda x:x['parts'][0].update(inode=1),lambda x:x.update(service_actions=True),lambda x:x['owners'].append({'pid':1,'start_ticks':2,'units':['SECRET=value'],'handles':[],'shared_writable_mappings':0})):
        value=json.loads(json.dumps(d));change(value)
        try:decode_receipt(json.dumps(value),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('INVALID_RECEIPT_ACCEPTED')
    shell_for(HOSTS[0][4],'f'*32)
    print('PR99_CREDENTIAL_WRITER_6_FLAGS_MAP_CASES_6_SCHEMA_REJECTIONS_PASS_NO_CLOUD',flush=True)

def main():
    if os.environ.get('PR99_MODE')=='SELF_TEST':
        self_test();return 0
    if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
        raise Hold('WORKFLOW_RERUN_FORBIDDEN')
    head=os.environ.get('PR99_HEAD','')
    if not re.fullmatch('[0-9a-f]{40}',head) or os.environ.get('PR99_LABEL')!='pr99-credential-writer-'+head[:12]:
        raise Hold('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED')
    master=(os.environ.get('ALIYUN_ACCESS_KEY_ID',''),os.environ.get('ALIYUN_ACCESS_KEY_SECRET',''),'')
    if not all(master[:2]):raise Hold('MISSING_ORIGINAL_REPOSITORY_SECRETS')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        rows=list(pool.map(lambda host:probe_current(host,master),HOSTS))
    receipt={'status':'WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','hosts':rows,
        'production_actions':0,'production_cutover':False,'authoritative_writer':'UNKNOWN',
        'enforced_fence':'UNKNOWN','migration_started':False}
    print('PR99_CREDENTIAL_WRITER_RECEIPT='+json.dumps(receipt,sort_keys=True),flush=True)
    return 0 if all(r['status']=='WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN' for r in rows) else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Hold as error:
        print('PR99_CREDENTIAL_WRITER_HOLD='+safe(str(error)),flush=True)
        raise SystemExit(2)

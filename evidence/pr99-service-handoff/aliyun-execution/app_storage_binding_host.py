"""Interpret a deliberately small source-expression subset without executing it.

Results are SOURCE DEFAULT candidates. They never establish effective runtime
configuration, Writer ownership, admission, SQLite format or a source fence.
"""
import ast
import os
from pathlib import PurePosixPath

class Unresolved(Exception):
    pass

class Defaults:
    def __init__(self, raw, filename, cwd):
        self.tree=ast.parse(raw)
        self.filename=filename;self.cwd=cwd
        self.functions={n.name:n for n in self.tree.body if isinstance(n,ast.FunctionDef)}
        self.imports={}
        for node in self.tree.body:
            if isinstance(node,ast.Import):
                for a in node.names:self.imports[a.asname or a.name]=a.name
            elif isinstance(node,ast.ImportFrom) and node.module:
                for a in node.names:self.imports[a.asname or a.name]=node.module+'.'+a.name
        self.globals={'__file__':filename};self.depth=0
        for n in self.tree.body:
            self.assign(n,self.globals)

    def fullname(self,node):
        if isinstance(node,ast.Name):return self.imports.get(node.id,node.id)
        if isinstance(node,ast.Attribute):return self.fullname(node.value)+'.'+node.attr
        return ''

    def defaults(self,function,scope):
        positional=function.args.posonlyargs+function.args.args
        for arg in positional:scope[arg.arg]=Unresolved
        for arg,node in zip(positional[len(positional)-len(function.args.defaults):],function.args.defaults):
            try:scope[arg.arg]=self.value(node,scope)
            except Exception:scope[arg.arg]=Unresolved
        for arg,node in zip(function.args.kwonlyargs,function.args.kw_defaults):
            try:scope[arg.arg]=self.value(node,scope)
            except Exception:scope[arg.arg]=Unresolved
        return scope

    def assign(self,node,scope):
        if isinstance(node,ast.If):
            try:
                condition=self.value(node.test,scope)
                if type(condition)is not bool:raise Unresolved()
                for statement in (node.body if condition else node.orelse):self.assign(statement,scope)
            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):
                for child in ast.walk(node):
                    if isinstance(child,ast.Name) and isinstance(child.ctx,ast.Store):scope[child.id]=Unresolved
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            try:value=self.value(node.value,scope)
            except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):value=Unresolved
            for target in targets:
                if isinstance(target,ast.Name):scope[target.id]=value

    def value(self,n,scope):
        if n is None:raise Unresolved()
        if isinstance(n,ast.Constant) and type(n.value) in (str,int,bool,type(None)):return n.value
        if isinstance(n,ast.Name):
            v=scope.get(n.id,Unresolved)
            if v is Unresolved:raise Unresolved()
            return v
        if isinstance(n,ast.Compare) and len(n.ops)==len(n.comparators)==1:
            a=self.value(n.left,scope);b=self.value(n.comparators[0],scope)
            if isinstance(n.ops[0],ast.Is) and (a is None or b is None):return a is b
            if isinstance(n.ops[0],ast.IsNot) and (a is None or b is None):return a is not b
            raise Unresolved()
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not self.value(n.operand,scope)
        if isinstance(n,ast.BinOp):
            a=self.value(n.left,scope);b=self.value(n.right,scope)
            if isinstance(n.op,ast.Div) and isinstance(a,PurePosixPath) and type(b)is str:return a/b
            if isinstance(n.op,ast.Add) and type(a)is type(b)is str:return a+b
            raise Unresolved()
        if isinstance(n,ast.JoinedStr):
            out=''
            for v in n.values:
                if isinstance(v,ast.Constant) and type(v.value)is str:out+=v.value
                elif isinstance(v,ast.FormattedValue) and v.conversion==-1 and v.format_spec is None:
                    x=self.value(v.value,scope)
                    if type(x) not in (str,int) and not isinstance(x,PurePosixPath):raise Unresolved()
                    out+=str(x)
                else:raise Unresolved()
            return out
        if isinstance(n,ast.Attribute):
            v=self.value(n.value,scope)
            if type(v)is dict and n.attr in v:return v[n.attr]
            if isinstance(v,PurePosixPath) and n.attr=='parent':return v.parent
            if isinstance(v,PurePosixPath) and n.attr=='parents':return tuple(v.parents)
            raise Unresolved()
        if isinstance(n,ast.Subscript):
            v=self.value(n.value,scope);i=self.value(n.slice,scope)
            if type(v)is tuple and type(i)is int and 0<=i<16:return v[i]
            raise Unresolved()
        if isinstance(n,ast.BoolOp) and isinstance(n.op,ast.Or):
            for v in n.values:
                value=self.value(v,scope)
                if value:return value
            return value
        if isinstance(n,ast.Call):
            name=self.fullname(n.func)
            if n.keywords:raise Unresolved()
            args=[self.value(x,scope) for x in n.args]
            if name=='pathlib.Path' and len(args)==1 and type(args[0])is str:return PurePosixPath(args[0])
            if name=='str' and len(args)==1 and (type(args[0])in(str,int) or isinstance(args[0],PurePosixPath)):return str(args[0])
            if name in ('os.getenv','os.environ.get') and len(args)in(1,2) and args[0]=='TRADING_DATABASE_URL':return args[1] if len(args)==2 else None
            if name=='os.path.dirname' and len(args)==1 and type(args[0])is str:return os.path.dirname(args[0])
            if name=='os.path.join' and args and all(type(x)is str for x in args):return os.path.join(*args)
            if name=='os.path.abspath' and len(args)==1 and type(args[0])is str:return os.path.normpath(os.path.join(self.cwd,args[0]))
            if name=='os.getcwd' and not args:return self.cwd
            if isinstance(n.func,ast.Attribute) and n.func.attr in ('resolve','absolute') and not args:
                path=self.value(n.func.value,scope)
                if isinstance(path,PurePosixPath):return PurePosixPath(os.path.normpath(os.path.join(self.cwd,str(path))))
            if isinstance(n.func,ast.Name) and n.func.id in self.functions and not args and self.depth<8:
                f=self.functions[n.func.id]
                if f.args.args or f.args.posonlyargs or f.args.kwonlyargs or f.args.vararg or f.args.kwarg:raise Unresolved()
                local=dict(self.globals);self.depth+=1
                try:
                    for statement in f.body:
                        if isinstance(statement,(ast.Assign,ast.AnnAssign)):self.assign(statement,local)
                        elif isinstance(statement,ast.Return):return self.value(statement.value,local)
                        elif isinstance(statement,ast.Expr) and isinstance(statement.value,ast.Constant):continue
                        else:raise Unresolved()
                finally:self.depth-=1
            raise Unresolved()
        raise Unresolved()

    def factories(self):
        rows=[]
        for block in [self.tree]+list(self.functions.values()):
            scope=dict(self.globals)
            if isinstance(block,ast.FunctionDef):self.defaults(block,scope)
            for node in block.body:
                self.assign(node,scope)
                # Only direct statement expressions; no pretending to resolve arbitrary control flow.
                for call in ast.walk(node):
                    if not isinstance(call,ast.Call) or self.fullname(call.func)!='sqlalchemy.create_engine':continue
                    value=None
                    try:
                        value=self.value(call.args[0],scope) if call.args else None
                    except (Unresolved,ValueError,TypeError,IndexError,KeyError,AttributeError):pass
                    rows.append((call.lineno,value if type(value)is str else None))
        # Module walk also visits function bodies: keep resolved function-local result over unresolved duplicate.
        unique={}
        for line,value in rows:
            if line not in unique or value is not None:unique[line]=value
        return sorted(unique.items())

import datetime,hashlib,json,re,stat,urllib.parse,base64,zlib
def bounded_read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        if len(raw) > limit:
            raise ValueError('INPUT_BOUND')
        return raw
    finally:
        os.close(fd)

def start_ticks(pid):
    raw = bounded_read('/proc/' + str(pid) + '/stat', 8192)
    return int(raw[raw.rfind(b')') + 2:].split()[19])

def locate(value, kind, cwd):
    if type(value) is not str or not value or '\x00' in value:
        return ('UNRESOLVED', None)
    if kind == 'URL':
        m = re.match('^sqlite(?:\\+pysqlite)?:///', value)
        if not m:
            return ('NON_SQLITE_OR_UNSUPPORTED_URL', None)
        value = value[m.end():]
        if '?' in value or '#' in value or value.startswith('file:'):
            return ('URI_OPTIONS_UNRESOLVED', None)
        value = urllib.parse.unquote(value)
        if not value or value == ':memory:':
            return ('NON_FILE_SQLITE', None)
    if not value.startswith('/'):
        if not cwd.startswith('/'):
            return ('RELATIVE_CWD_UNRESOLVED', None)
        value = os.path.join(cwd, value)
    if '\x00' in value:
        return ('UNRESOLVED', None)
    return ('FILE_CANDIDATE', os.path.normpath(value))

def descriptor(path):
    try:
        s = os.lstat(path)
    except FileNotFoundError:
        return {'state': 'MISSING'}
    except OSError:
        return {'state': 'METADATA_UNREADABLE'}
    if stat.S_ISLNK(s.st_mode):
        return {'state': 'SYMLINK_UNRESOLVED'}
    if not stat.S_ISREG(s.st_mode):
        return {'state': 'NOT_REGULAR'}
    return {'state': 'REGULAR_METADATA_CANDIDATE', 'device': s.st_dev, 'inode': s.st_ino, 'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode), 'bytes': s.st_size, 'nlink': s.st_nlink}

def read_at(directory, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise RuntimeError('SOURCE_TYPE_OR_SIZE')
        raw = b''
        while len(raw) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(fd)
        linked = os.stat(name, dir_fd=directory, follow_symlinks=False)
        fp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if fp(before) != fp(after) or fp(after) != fp(linked) or len(raw) != before.st_size:
            raise RuntimeError('SOURCE_DRIFT')
        return raw
    finally:
        os.close(fd)

EXPECTED_SOURCE='58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece'
IDENTITIES=(('portal',3082952,248360883),('contact',1903204,179522510),('customer_service',1875349,178615731))

def shape(node,depth=0):
    if depth>5:return {'kind':'DEPTH_BOUND'}
    if isinstance(node,ast.Constant):return {'kind':'Constant','literal_type':type(node.value).__name__}
    row={'kind':type(node).__name__}
    if isinstance(node,ast.Name):row['name']=node.id
    elif isinstance(node,ast.Attribute):row['name']=node.attr
    children=list(ast.iter_child_nodes(node))
    if children:row['children']=[shape(c,depth+1) for c in children[:8]]
    return row



ENTRY_PINS=(('scripts/secure_secrets_portal_server.py','57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1'),('ai_service/wecom_customer_contact_service.py','c95ca9ec711d05d64489ed927cae770157954b46661411b5f762f193ba711571'),('ai_service/wecom_customer_service.py','aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402'))
SAFE_REL=re.compile('[A-Za-z0-9_./-]{1,240}')

def source_at(root,path):
    assert SAFE_REL.fullmatch(path) and '..' not in path.split('/')
    pieces=path.split('/');parent=os.dup(root)
    try:
        for piece in pieces[:-1]:
            following=os.open(piece,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=following
        return read_at(parent,pieces[-1],1048576)
    finally:os.close(parent)

def metadata(path):
    try:s=os.lstat(path)
    except FileNotFoundError:return {'state':'MISSING'}
    except OSError:return {'state':'UNREADABLE'}
    kind='DIRECTORY' if stat.S_ISDIR(s.st_mode) else 'REGULAR' if stat.S_ISREG(s.st_mode) else 'SYMLINK' if stat.S_ISLNK(s.st_mode) else 'OTHER'
    return {'state':kind,'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,'mode':stat.S_IMODE(s.st_mode),'bytes':s.st_size}

"""Bounded static storage dataflow. No business import, environment or file I/O.

Resolved paths describe SOURCE expressions, never effective configuration or
permission to migrate. Unsupported/conditional assignments remain unresolved.
"""
import ast
import re
from pathlib import PurePosixPath

MODULE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
RUNTIME = re.compile(r"/opt/trading-system/runtime/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+")
STORAGE = re.compile(r"Store|Repository|Ledger|State")


def module_candidates(module):
    if not isinstance(module, str) or not MODULE.fullmatch(module):
        raise ValueError('MODULE_NAME_REJECTED')
    stem = module.replace('.', '/')
    return (stem + '.py', stem + '/__init__.py')


def runtime_path(value):
    if not isinstance(value, (str, PurePosixPath)):
        return None
    value = str(value)
    if len(value) > 400 or not RUNTIME.fullmatch(value) or any(p in ('.', '..') for p in value.split('/')):
        return None
    return value


def imports(tree, filename):
    """Include function-local and package-relative imports without importing them."""
    result = {}
    package = filename.removesuffix('/__init__.py').replace('/', '.') if filename.endswith('/__init__.py') else filename.rsplit('/', 1)[0].replace('/', '.')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            prefix = node.module or ''
            if node.level:
                parts = package.split('.')
                if node.level > len(parts):
                    continue
                prefix = '.'.join(parts[:len(parts)-node.level+1] + ([prefix] if prefix else []))
            for alias in node.names:
                if alias.name != '*' and prefix:
                    result[alias.asname or alias.name] = prefix + '.' + alias.name
    return result


def analyze_source(raw, filename, Defaults, shape):
    # Use the existing expression interpreter, with ALL environment reads unknown.
    # The legacy TRADING_DATABASE_URL absent-default assumption is not inherited.
    class StrictDefaults(Defaults):
        def value(self, node, scope):
            if isinstance(node, ast.Call) and self.fullname(node.func) in ('os.getenv', 'os.environ.get'):
                raise ValueError('ENVIRONMENT_NOT_SOURCE_DEFAULT')
            return super().value(node, scope)

    engine = StrictDefaults(raw, '/opt/trading-system/' + filename, '/opt/trading-system')
    engine.imports = imports(engine.tree, filename)
    constructors, assignments, operations, options = [], [], [], []
    paths = set()

    def expression(node, scope):
        result = {'shape': shape(node), 'source_runtime_path': None}
        try:
            result['source_runtime_path'] = runtime_path(engine.value(node, scope))
        except Exception:
            # The supplied interpreter uses its own Unresolved type. No source is
            # executed; all failures are conservatively unresolved, not fallback.
            pass
        if result['source_runtime_path']:
            paths.add(result['source_runtime_path'])
        return result

    def walk(statements, scope, owner):
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                local = dict(engine.globals)
                engine.defaults(statement, local)
                walk(statement.body, local, owner + '.' + statement.name)
                continue
            if isinstance(statement, ast.ClassDef):
                walk(statement.body, dict(engine.globals), statement.name)
                continue
            if isinstance(statement, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)):
                # Record unresolved shapes in conditional blocks, never merge a
                # branch's assignment into the enclosing execution flow.
                for child in ast.iter_child_nodes(statement):
                    if isinstance(child, ast.stmt):
                        unknown = {key: None for key in scope}
                        walk([child], unknown, owner)
                engine.assign(statement, scope)
                continue
            engine.assign(statement, scope)
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self' and re.search(r'path|root|file|dir|db', target.attr, re.I):
                        assignments.append({'owner': owner, 'line': statement.lineno, 'attribute': target.attr, 'value': expression(statement.value, scope)})
            for node in ast.walk(statement):
                if not isinstance(node, ast.Call):
                    continue
                name = engine.fullname(node.func)
                if STORAGE.search(name) and MODULE.fullmatch(name):
                    constructors.append({'owner': owner, 'line': node.lineno, 'name': name,
                        'arguments': [expression(a, scope) for a in node.args[:6]],
                        'keywords': [{'name': kw.arg or 'EXPANSION_UNRESOLVED', 'value': expression(kw.value, scope)} for kw in node.keywords[:12]]})
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument':
                    option = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                    if isinstance(option, str) and re.fullmatch(r'--[a-z][a-z-]{0,50}', option):
                        for kw in node.keywords:
                            if kw.arg == 'default':
                                options.append({'line': node.lineno, 'option': option, 'default': expression(kw.value, scope)})
                if name and (name.startswith(('sqlite3.', 'json.')) or name.rsplit('.', 1)[-1] in ('open', 'write_text', 'write_bytes', 'read_text', 'read_bytes', 'replace', 'unlink', 'mkdir')):
                    operations.append({'owner': owner, 'line': node.lineno, 'name': name, 'arguments': [expression(a, scope) for a in node.args[:3]]})
    walk(engine.tree.body, dict(engine.globals), 'MODULE')
    result = {'imports': engine.imports, 'constructors': constructors[:30], 'path_assignments': assignments[:40], 'storage_operations': operations[:60], 'cli_defaults': options[:30], 'source_paths': sorted(paths), 'omitted': max(0, len(constructors)-30)+max(0, len(assignments)-40)+max(0, len(operations)-60)+max(0, len(options)-30)}
    return result


def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'
    root=os.open('/opt/trading-system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    pending=[(p,h) for p,h in ENTRY_PINS]+[('database/repositories/credential_repository.py',None),('accounts/credential_store.py',None)];seen=set();sources=[];roots={};missing=[];omitted=0
    try:
        while pending:
            path,pin=pending.pop(0)
            if path in seen:continue
            if len(seen)>=24:omitted+=1;continue
            seen.add(path)
            try:raw=source_at(root,path)
            except (FileNotFoundError,NotADirectoryError):
                if path.endswith('.py') and not path.endswith('/__init__.py'):
                    fallback=path[:-3]+'/__init__.py'
                    try:raw=source_at(root,fallback);path=fallback
                    except (FileNotFoundError,NotADirectoryError):missing.append(path);continue
                else:missing.append(path);continue
            digest=hashlib.sha256(raw).hexdigest();assert pin is None or pin==digest,'ENTRY_SOURCE_DRIFT'
            interpreter=Defaults(raw,'/opt/trading-system/'+path,'/opt/trading-system');t=interpreter.tree
            imports=[];constructors=[];references=[]
            details=analyze_source(raw,path,Defaults,shape)
            omitted+=details.pop('omitted')
            # Bound each source record without silently pretending completeness.
            while len(json.dumps(details))>6500:
                groups=['storage_operations','constructors','path_assignments','cli_defaults']
                selected=max(groups,key=lambda key:len(json.dumps(details[key])) if details[key] else 0)
                if not details[selected]:raise RuntimeError('SOURCE_DETAILS_BOUND')
                details[selected].pop();omitted+=1
            for alias,origin in sorted(details['imports'].items()):
                if origin.startswith(('ai_service.','database.','trading_execution.','accounts.','douyin.','tiktok.','integrations.')):
                    imports.append(origin)
                    if re.search('store|repository|ledger|state|canary',alias,re.I):
                        module=origin.rsplit('.',1)[0]
                        pending.append((module_candidates(module)[0],None))
            details.pop('imports')
            for location in details.pop('source_paths'):
                references.append((0,'SOURCE_EXPRESSION_NOT_RUNTIME',location))
            for node in ast.walk(t):
                if isinstance(node,ast.Constant) and type(node.value)is str and node.value.startswith('/opt/trading-system/runtime/') and re.fullmatch('/[A-Za-z0-9_./-]{1,400}',node.value):
                    references.append((node.lineno,'LITERAL_RUNTIME_REFERENCE',node.value))
                if isinstance(node,ast.Call):
                    name=interpreter.fullname(node.func)
                    if re.search('Store|Repository|Ledger|State',name) and re.fullmatch('[A-Za-z_][A-Za-z0-9_.]{0,180}',name):
                        row={'line':node.lineno,'name':name,'arguments':[shape(a) for a in node.args[:3]]}
                        if len(constructors)<20 and len(json.dumps(constructors+[row]))<10000:constructors.append(row)
            for name,value in interpreter.globals.items():
                if isinstance(value,PurePosixPath) or type(value)is str:
                    value=str(value)
                    if value.startswith('/opt/trading-system/runtime/') and re.fullmatch('/[A-Za-z0-9_./-]{1,400}',value):references.append((0,name,value))
            rootrefs=[]
            for line,symbol,location in references:
                location=os.path.normpath(location)
                if not location.startswith('/opt/trading-system/runtime/'):continue
                if location not in roots:
                    if len(roots)>=32:omitted+=1;continue
                    roots[location]=len(roots)
                rootrefs.append({'line':line,'symbol':symbol,'slot':roots[location]})
            sources.append({'path':path,'sha256':digest,'project_imports':imports,'storage_constructors':constructors,'runtime_references':rootrefs,'binding_details':details})
    finally:os.close(root)
    locations=[]
    for location,slot in roots.items():
        # Source-literal technical runtime paths only, never values from private env/config.
        locations.append({'slot':slot,'source_literal_path':location,'metadata':metadata(location)})
    value={'scope':'PR99_STORAGE_BINDINGS_SOURCE_ONLY_NOT_EFFECTIVE_CONFIG','hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z','sources':sources,'locations':locations,'missing_source_paths':missing,'omitted_candidates':omitted,'private_values_disclosed':False,'database_opened':False,'service_actions':0,'business_requests':0,'business_source_imports':0,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN','limitations':['SOURCE_LITERAL_PATHS_NOT_EFFECTIVE_RUNTIME_CONFIG','MAX_24_SELECTED_STORAGE_MODULES_NOT_FULL_IMPORT_GRAPH','METADATA_ONLY_NO_DATA_CONTENT_OR_SQLITE_FORMAT_PROOF','NO_WRITER_FENCE_DRAIN_OR_STOP']}
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode();assert len(raw)<=180000
    wire={'encoding':'PR99_STORAGE_ZLIB_BASE64_V1','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':base64.b64encode(zlib.compress(raw,9)).decode()}
    text=json.dumps(wire,separators=(',',':'));assert len(text.encode())<23000
    return text

if __name__=='__main__':
    print(observe(EXPECTED,NONCE),flush=True)

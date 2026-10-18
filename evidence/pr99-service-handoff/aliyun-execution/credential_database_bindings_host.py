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


SOURCE_FILES=(('database/connection.py', '58d9705addf7b997a7c2405a2f53d2414495a72e5be72d91d6c550ac2bd83ece'), ('database/repositories/credential_repository.py', '8e133d4b07b0d6698befb2f0c9c98963a2d1156f58fa9e2c2a0fe4879bbf9104'))

def source_at(root,path):
    pieces=path.split('/');parent=os.dup(root)
    try:
        for piece in pieces[:-1]:
            following=os.open(piece,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
            os.close(parent);parent=following
        return read_at(parent,pieces[-1],1048576)
    finally:os.close(parent)

def connection_call(path,origin,local_names):
    return origin=='sqlalchemy.create_engine' or origin.startswith('database.connection.') or (path=='database/connection.py' and origin in local_names)

def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'
    root=os.open('/opt/trading-system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    sources={}
    try:
        for path,pin in SOURCE_FILES:
            raw=source_at(root,path);digest=hashlib.sha256(raw).hexdigest()
            assert pin is None or pin==digest,'PINNED_SOURCE_CHANGED_HOLD'
            sources[path]=(raw,digest)
    finally:os.close(root)
    connection=ast.parse(sources['database/connection.py'][0])
    names={n.name for n in connection.body if isinstance(n,ast.FunctionDef)}
    rows=[]
    for path,(raw,digest) in sources.items():
        interpreter=Defaults(raw,'/opt/trading-system/'+path,'/opt/trading-system')
        module={'path':path,'sha256':digest,'connection_imports':[], 'environment_mutation_or_loader_sites':0,'call_sites':[],'definition_shapes':[]}
        for alias,origin in sorted(interpreter.imports.items()):
            if origin.startswith('database.connection.') or origin.startswith('ai_service.domestic_runtime_closure.'):
                module['connection_imports'].append(origin)
        tree=interpreter.tree
        namespace={}
        for call in ast.walk(tree):
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute) or call.func.attr!='add_argument':continue
            flags=[a.value for a in call.args if isinstance(a,ast.Constant) and a.value in ('--database-url','--db-url','--trading-database-url')]
            if not flags:continue
            destination=flags[0][2:].replace('-','_')
            for keyword in call.keywords:
                if keyword.arg=='dest' and isinstance(keyword.value,ast.Constant) and type(keyword.value.value)is str:destination=keyword.value.value
            value=None
            try:
                for keyword in call.keywords:
                    if keyword.arg=='default':value=interpreter.value(keyword.value,dict(interpreter.globals))
            except Exception:value=Unresolved
            # Only defaults are analyzed. Runtime CLI/env overrides remain outside this candidate proof.
            namespace[destination]=value
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                origin=interpreter.fullname(node.func)
                if 'dotenv' in origin or origin.endswith('.load_env') or origin.endswith('.load_environment'):
                    module['environment_mutation_or_loader_sites']+=1
            if isinstance(node,ast.Subscript) and isinstance(node.ctx,ast.Store) and interpreter.fullname(node.value)=='os.environ':module['environment_mutation_or_loader_sites']+=1
        seen=set()
        for block in [tree]+list(interpreter.functions.values()):
            scope=dict(interpreter.globals)
            if isinstance(block,ast.FunctionDef):interpreter.defaults(block,scope)
            if namespace:scope['args']=namespace
            for statement in block.body:
                interpreter.assign(statement,scope)
                for call in ast.walk(statement):
                    if not isinstance(call,ast.Call):continue
                    origin=interpreter.fullname(call.func)
                    matches=connection_call(path,origin,names)
                    if not matches:continue
                    arguments=[('POSITIONAL_'+str(i),n) for i,n in enumerate(call.args[:5])]
                    arguments += [(k.arg,k.value) for k in call.keywords if k.arg and any(x in k.arg.lower() for x in ('database','db_url','session','runtime'))]
                    if not arguments:arguments=[('NO_ARGUMENT',None)]
                    for position,arg in arguments:
                        identity=(call.lineno,position)
                        value=None
                        if arg is not None:
                            try:value=interpreter.value(arg,scope)
                            except Exception:pass
                        status,location=locate(value,'URL','/opt/trading-system')
                        row={'line':call.lineno,'constructor':origin,'argument':position,'expression':shape(arg) if arg is not None else {'kind':'NO_ARGUMENT'},'default_status':status,'data':[] if location is None else [{'part':part,'metadata':descriptor(location+suffix)} for part,suffix in (('MAIN',''),('WAL','-wal'),('SHM','-shm'))]}
                        if identity in seen:
                            oldrow=next(x for x in module['call_sites'] if (x['line'],x['argument'])==identity)
                            if oldrow['default_status']=='UNRESOLVED' and status!='UNRESOLVED':module['call_sites'].remove(oldrow)
                            else:continue
                        module['call_sites'].append(row);seen.add(identity)
        bindings=[statement for statement in tree.body if isinstance(statement,(ast.Assign,ast.AnnAssign,ast.If,ast.Try))]
        if bindings:
            module['definition_shapes'].append({'name':'MODULE_BINDINGS','line':0,'arguments':[],'body':[{'line':n.lineno,'expression':shape(n)} for n in bindings[:8]]})
        # Literal-redacted signatures and direct URL-related statements resolve unsupported-call diagnostics.
        for fn in interpreter.functions.values():
            interesting=path=='database/connection.py' or any(isinstance(n,ast.Name) and any(k in n.id.lower() for k in ('database_url','db_url','database_path')) for n in ast.walk(fn))
            if not interesting:continue
            body=[{'line':n.lineno,'expression':shape(n)} for n in fn.body[:8]]
            item={'name':fn.name,'line':fn.lineno,'arguments':[x.arg for x in fn.args.posonlyargs+fn.args.args+fn.args.kwonlyargs],'body':body}
            if len(module['definition_shapes'])<8 and len(json.dumps(module['definition_shapes']+[item]))<14000:module['definition_shapes'].append(item)
        assert len(module['call_sites'])<=40
        rows.append(module)
    value={'scope':'PR99_CREDENTIAL_LOCAL_FACTORY_BINDINGS_NOT_AUTHORITY','hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z','sources':rows,'private_values_disclosed':False,'database_opened':False,'service_actions':0,'business_requests':0,'business_source_imports':0,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN','limitations':['TWO_PINNED_CREDENTIAL_CONNECTION_SOURCES_NOT_COMPLETE_CONFIG','ONLY_SOURCE_DEFAULTS_ENV_AND_RUNTIME_OVERRIDES_NOT_PROVEN','RELATIVE_PATHS_ASSUME_PROJECT_WORKDIR_NOT_ADMISSION','NO_WRITER_FENCE_DRAIN_OR_STOP']}
    raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    assert len(raw)<=180000,'CALLER_RECEIPT_RAW_BOUND'
    wire={'encoding':'PR99_CALLER_ZLIB_BASE64_V1','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'payload':base64.b64encode(zlib.compress(raw,9)).decode()}
    text=json.dumps(wire,separators=(',',':'));assert len(text.encode())<23000,'CALLER_RECEIPT_WIRE_BOUND'
    return text

if __name__=='__main__':
    import base64,zlib
    print(observe(EXPECTED,NONCE),flush=True)

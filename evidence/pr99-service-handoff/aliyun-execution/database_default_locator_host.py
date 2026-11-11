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

import datetime,hashlib,json,re,stat,urllib.parse
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

def observe(expected,nonce):
    assert os.geteuid()==0 and os.uname().nodename==expected=='iZ6wee8q9z4t03hvqumwfhZ'
    root=os.open('/opt/trading-system',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        d=os.open('database',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=root)
        try:raw=read_at(d,'connection.py',1048576)
        finally:os.close(d)
    finally:os.close(root)
    digest=hashlib.sha256(raw).hexdigest()
    assert digest==EXPECTED_SOURCE,'DATABASE_SOURCE_HASH_CHANGED_UNKNOWN_NO_RETRY'
    tree=ast.parse(raw)
    expressions=[]
    imported=[]
    for n in ast.walk(tree):
        if isinstance(n,(ast.Import,ast.ImportFrom)):
            if isinstance(n,ast.ImportFrom) and n.module:imported.append(n.module)
            elif isinstance(n,ast.Import):imported.extend(a.name for a in n.names)
        if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Name) and n.func.id=='create_engine') or (isinstance(n.func,ast.Attribute) and n.func.attr=='create_engine')):
            expressions.append({'line':n.lineno,'expression':shape(n.args[0]) if n.args else {'kind':'NO_POSITIONAL_ARGUMENT'}})
    assert len(expressions)<=16
    assert len(json.dumps(expressions))<12000
    resolution_nodes=[]
    for node in ast.walk(tree):
        selected=(isinstance(node,(ast.Assign,ast.AnnAssign)) and any(isinstance(x,ast.Name) and x.id=='database_url' and isinstance(x.ctx,ast.Store) for x in ast.walk(node))) or isinstance(node,ast.Return)
        if selected and len(resolution_nodes)<12:
            candidate={'line':node.lineno,'expression':shape(node)}
            if len(json.dumps(resolution_nodes+[candidate]))<8000:resolution_nodes.append(candidate)
    contexts=[]
    for role,pid,ticks in IDENTITIES:
        row={'role':role,'pid':pid,'start_ticks':ticks,'status':'UNKNOWN','factories':[]}
        try:
            assert start_ticks(pid)==ticks
            assert os.readlink('/proc/'+str(pid)+'/root')=='/'
            cwd=os.readlink('/proc/'+str(pid)+'/cwd')
            interpreter=Defaults(raw,'/opt/trading-system/database/connection.py',cwd)
            factories=interpreter.factories();assert len(factories)<=16
            for line,value in factories:
                status,path=locate(value,'URL',cwd)
                data=[] if path is None else [{'part':part,'metadata':descriptor(path+suffix)} for part,suffix in (('MAIN',''),('WAL','-wal'),('SHM','-shm'))]
                row['factories'].append({'line':line,'status':status,'data':data})
            assert start_ticks(pid)==ticks
            row['status']='SOURCE_DEFAULT_CANDIDATES_OBSERVED'
        except Exception:row['factories']=[];row['status']='PROCESS_OR_DEFAULT_RESOLUTION_UNKNOWN'
        contexts.append(row)
    assert all(re.fullmatch('[A-Za-z_][A-Za-z0-9_.]{0,180}',x) for x in imported)
    return {'scope':'PR99_PINNED_SOURCE_DEFAULT_DATABASE_CANDIDATES_NOT_EFFECTIVE_CONFIG','hostname':expected,'nonce':nonce,'observed_at':datetime.datetime.utcnow().isoformat()+'Z','source_sha256':digest,'imports':sorted(set(imported)),'factory_expressions':expressions,'resolution_nodes':resolution_nodes,'contexts':contexts,'private_values_disclosed':False,'database_opened':False,'service_actions':0,'business_requests':0,'business_source_imports':0,'authoritative_writer':'UNKNOWN','enforced_fence':'UNKNOWN','limitations':['SOURCE_DEFAULT_NOT_EFFECTIVE_RUNTIME_CONFIG','ENV_ABSENCE_ASSUMED_ONLY_TO_CALCULATE_DEFAULT_NOT_CURRENT_ENV_PROOF','ANCESTOR_BINDING_NOT_PRODUCTION_PATHGUARD','ALL_WRITERS_AND_FENCE_NOT_PROVEN']}

if __name__=='__main__':
    print(json.dumps(observe(EXPECTED,NONCE),sort_keys=True),flush=True)

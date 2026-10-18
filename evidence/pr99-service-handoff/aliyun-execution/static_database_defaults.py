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

    def assign(self,node,scope):
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

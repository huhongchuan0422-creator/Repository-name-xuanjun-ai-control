"""Resolve storage wiring syntax in received S07 copies without disclosing literals.
Static expressions only: no importing apps, opening data/config/keys or networking.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

BASE = Path('/root/pr99-s07-runtime-inventory.8no57zD5/inspect.py')
BASE_SHA = '295b3e4df882793978042edcb3222c1068c493a9a33e47370ae8558d37095134'
TARGETS = ('scripts/secure_secrets_portal_server.py', 'ai_service/secure_secrets_portal.py',
 'ai_service/wecom_customer_contact_service.py', 'ai_service/wecom_customer_service.py',
 'database/connection.py', 'douyin/open_api_foundation.py', 'tiktok/open_api_foundation.py',
 'crm/channel_referral_attribution.py', 'knowledge/service.py')
RELEVANT = re.compile(r'root|path|file|key|host|port|state|audit|database|storage|credential|referral|knowledge|runtime|config', re.I)
DIRECTORIES = {'runtime','config','state','audit','secrets','operations','data','logs','portal',
 'wecom','wecom-kf','wecom-customer-contact','wecom-customer-service','secure-secrets-portal'}


def path_literal(v):
    if not isinstance(v,str) or len(v)>180 or not re.fullmatch(r'[A-Za-z0-9_./-]+',v):
        return False
    if '..' in v.split('/') or any(len(x)>48 for x in v.split('/')):
        return False
    if v.startswith('/'):
        return v.startswith(('/opt/trading-system/','/home/admin/','/home/openclaw_ops/','/var/lib/','/etc/')) or v=='/opt/trading-system'
    return v in DIRECTORIES or v.endswith(('.db','.sqlite','.sqlite3','.json','.jsonl','.yaml','.yml','.env','.pem','.key','.log'))


class Redact(ast.NodeTransformer):
    def visit_Constant(self,node):
        v=node.value
        if isinstance(v,str):
            keep=path_literal(v)
            return ast.copy_location(ast.Constant(v if keep else '<REDACTED_STRING>'),node)
        if v is None or isinstance(v,bool):
            return node
        if type(v) is int and -10<=v<=10:
            return node
        return ast.copy_location(ast.Constant('<REDACTED_LITERAL>'),node)


def expression(node):
    # Reparse before transforming, to avoid mutating nodes used by later scans.
    tree=ast.parse(ast.unparse(node),mode='eval')
    safe=ast.unparse(ast.fix_missing_locations(Redact().visit(tree))).strip()
    return safe if len(safe)<=1600 else safe[:1600]+' <TRUNCATED_STATIC_EXPRESSION>'


def inspect(raw):
    tree=ast.parse(raw)
    out=[]
    def walk(body,scope):
        for n in body:
            if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                name=scope+'.'+n.name if scope else n.name
                if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='__init__':
                    args=n.args
                    defaults={a.arg:expression(v) for a,v in zip(args.args[-len(args.defaults):],args.defaults)} if args.defaults else {}
                    defaults.update({a.arg:expression(v) for a,v in zip(args.kwonlyargs,args.kw_defaults) if v is not None})
                    out.append({'line':n.lineno,'scope':name,'constructor_parameter_names':[a.arg for a in args.posonlyargs+args.args+args.kwonlyargs],'defaults':defaults})
                walk(n.body,name)
            elif isinstance(n,(ast.Assign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                names=[ast.unparse(t) for t in targets]
                if n.value is not None and any(RELEVANT.search(t) for t in names):
                    out.append({'line':n.lineno,'scope':scope,'assigned_names':names,'expression':expression(n.value)})
            elif isinstance(n,(ast.If,ast.For,ast.While,ast.With,ast.Try)):
                walk(n.body,scope)
                walk(getattr(n,'orelse',[]),scope)
                walk(getattr(n,'finalbody',[]),scope)
                for h in getattr(n,'handlers',[]):walk(h.body,scope)
    walk(tree.body,'')
    return out


def main():
    assert os.geteuid()==0 and os.uname().nodename=='iZmj7a5kwr75qc1tul4kf9Z'
    # Read only the authenticated prior inventory helper, then its frozen loader.
    for p in reversed(BASE.parents):
        st=p.lstat();assert stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022
    with os.fdopen(os.open(BASE,os.O_RDONLY|os.O_NOFOLLOW),'rb') as f:
        a=os.fstat(f.fileno());assert stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and not a.st_mode&0o077 and a.st_size<100000
        raw=f.read(100001);b=os.fstat(f.fileno())
    c=BASE.lstat()
    assert len(raw)==a.st_size and hashlib.sha256(raw).hexdigest()==BASE_SHA
    assert all(getattr(a,k)==getattr(b,k)==getattr(c,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns'))
    ns={'__name__':'prior_inventory_functions','__file__':str(BASE)}
    exec(compile(raw,str(BASE),'exec'),ns)
    old=ns['load_pinned'](ns['ORIGINAL'],ns['ORIGINAL_SHA'])
    package=old['stable'](ns['PACKAGE'],64*1024*1024)
    assert ns['digest'](package)==ns['PACKAGE_SHA']
    plan,sources=old['unpack'](package,ns['PACKAGE_SHA'])
    assert len(sources)==79 and all(p in sources for p in TARGETS)
    report={p:inspect(sources[p]) for p in TARGETS}
    print(json.dumps({'status':'S07_STORAGE_WIRING_STATIC_PROJECTION','source_files':79,
        'report':report,'literal_policy':'PATH_CLUES_ONLY_OTHER_LITERALS_REDACTED',
        'scope':'SYNTAX_NOT_RUNTIME_CLOSURE_OR_CURRENT_TOKYO_STATE',
        'application_imports':0,'database_config_key_reads':0,'service_actions':0,
        'network_requests':0,'production_cutover':False},sort_keys=True),flush=True)

if __name__=='__main__': main()

"""Read-only conservative S07 source closure inventory; never imports business code."""
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

def need(value, code):
    if not value: raise RuntimeError(code)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def module_name(name):
    p = PurePosixPath(name)
    parts = list(p.with_suffix('').parts)
    if parts[-1] == '__init__': parts.pop()
    return '.'.join(parts)

def closure(index, initial, read):
    selected = set()
    pending = list(initial)
    reasons = {}
    dynamic = []
    external = set()
    def add(module, origin):
        if module not in index: return False
        path = index[module]
        if path not in selected:
            pending.append(path)
            reasons.setdefault(path, set()).add(origin)
        parts = module.split('.')
        for i in range(1, len(parts)):
            parent = '.'.join(parts[:i])
            if parent in index and index[parent].endswith('/__init__.py'):
                if index[parent] not in selected: pending.append(index[parent])
        return True
    while pending:
        name = pending.pop()
        if name in selected: continue
        need(len(selected) < 2000, 'CLOSURE_LIMIT')
        selected.add(name)
        module = module_name(name)
        package = module if name.endswith('/__init__.py') else module.rpartition('.')[0]
        add(module, 'selected')
        tree = ast.parse(read(name), filename=name)
        nodes = list(ast.walk(tree))
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not add(alias.name, name): external.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = package.split('.') if package else []
                    need(node.level <= len(parts), 'RELATIVE_IMPORT_OUTSIDE_PACKAGE')
                    base = '.'.join(parts[:len(parts)-node.level+1])
                    if node.module: base = base+'.'+node.module if base else node.module
                else: base = node.module or ''
                local = add(base, name)
                for alias in node.names: local = add(base+'.'+alias.name, name) or local
                if not local and not node.level and base: external.add(base.split('.')[0])
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Lazy-export tables often store a relative module name in a tuple.
                # Admit only exact matches in the existing Python-file index.
                value = node.value
                if re.fullmatch(r'\.*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', value):
                    add(value, 'literal:'+name)
                    suffix = value.lstrip('.')
                    parts = package.split('.') if package else []
                    for i in range(len(parts), 0, -1):
                        add('.'.join(parts[:i])+'.'+suffix, 'literal:'+name)
            elif isinstance(node, ast.Call):
                func = node.func
                key = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ''
                if key in ('import_module', '__import__', 'exec', 'eval'):
                    dynamic.append({'path':name, 'line':node.lineno, 'kind':key,
                                    'literal_first_argument':bool(node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str))})
    return selected, reasons, dynamic, external

def main():
    need(os.geteuid()==0 and os.uname().nodename=='iZmj7a5kwr75qc1tul4kf9Z', 'KOREA_ROOT_REQUIRED')
    os.umask(0o077)
    def load(path, expected):
        raw=Path(path).read_bytes();need(digest(raw)==expected,'PIN_CHANGED')
        ns={'__name__':'frozen_functions','__file__':str(path)}
        exec(compile(raw,str(path),'exec'),ns)
        return ns
    helper=load('/root/pr99-s07-material-v2-launch.mgOIzkS1/stage.py',
        '137a2acea1924b4c62e43abfe6f8689c64450db868c7a216d759a16779c939b4')
    read=helper['read_plain_file']
    old=load('/root/pr99-s07-install-launch.a5NZU99H/install.py',
        '745c67d34cf4b0d546aee28c74c11b1586a315a03d970cbebc37508ebc61f8fd')
    raw=old['stable'](old['LOCAL_ATTEMPT']/'package.json',64*1024*1024)
    need(digest(raw)=='9b702576d48883786d051b2f1b49972baf94db3d1e8bf330ee59250a5974efa3','PACKAGE_CHANGED')
    plan, initial=old['unpack'](raw,digest(raw));need(len(initial)==79,'INITIAL_COUNT')
    root=Path('/root/pr99-current-point-received-v2/verified/code')
    need(root.is_dir() and not root.is_symlink(),'R2_CODE_MISSING')
    index={}
    entries=0
    for current,dirs,files in os.walk(root,followlinks=False):
        dirs.sort();files.sort()
        for name in dirs:
            need(not (Path(current)/name).is_symlink(),'R2_DIRECTORY_SYMLINK')
        for name in files:
            entries+=1;need(entries<=10000,'INDEX_LIMIT')
            if not name.endswith('.py'):continue
            p=Path(current)/name;need(not p.is_symlink(),'R2_FILE_SYMLINK')
            rel=p.relative_to(root).as_posix();mod=module_name(rel)
            need(mod not in index,'AMBIGUOUS_MODULE_PATH');index[mod]=rel
    cache={};total=0
    def source(name):
        nonlocal total
        if name not in cache:
            b=read(root/name,2*1024*1024);total+=len(b)
            need(total<=64*1024*1024,'SOURCE_TOTAL_LIMIT');cache[name]=b
        return cache[name]
    for name,b in initial.items():need(source(name)==b,'R2_INITIAL_SOURCE_CHANGED')
    selected,reasons,dynamic,external=closure(index,initial,source)
    missing='database/repositories/audit_repository.py'
    out={'status':'S07_CONSERVATIVE_CLOSURE_INVENTORY_NOT_RUNTIME_PASS',
         'initial_files':79,'candidate_files':len(selected),'indexed_modules':len(index),
         'known_missing_module_available':missing in index.values(),
         'known_missing_module_selected':missing in selected,
         'added_files':[{'path':name,'sha256':digest(source(name)), 'bytes':len(source(name))}
                        for name in sorted(selected-set(initial))],
         'dynamic_sites':dynamic,'external_import_roots':sorted(external),
         'business_imports':0,'service_actions':0,'transfer_performed':False,
         'dynamic_completeness_proven':False}
    print(json.dumps(out,sort_keys=True))

if __name__=='__main__':
    try:main()
    except BaseException as e:
        code=str(e) if isinstance(e,RuntimeError) and re.fullmatch(r'[A-Z0-9_]{1,100}',str(e)) else type(e).__name__
        print('S07_CLOSURE_HOLD='+code)
        raise SystemExit(2)

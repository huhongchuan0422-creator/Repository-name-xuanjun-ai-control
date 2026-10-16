"""Nonroot Tokyo SOURCE-only reconciliation schema compatibility probe.

No live DB, credentials, production imports or raw SQL/literals in output.
Only approved table/column names from the existing reconciliation contract may
be emitted. A source declaration is not a proof of actual database schema.
"""
import ast
import hashlib
import os
from pathlib import Path
import re
import stat

HOST='iZ6wee8q9z4t03hvqumwfhZ'
ROOT=Path('/opt/trading-system')
# Frozen names from the approved readonly_reconciliation_adapter.TABLE_SPECS.
REQUIRED={
 'account_snapshots':('id','snapshot_id','account_id','created_time','payload_json'),
 'account_capabilities':('id','account_id','environment','position_mode','status','verified_time'),
 'position_snapshots':('id','snapshot_id','account_id','symbol','side','quantity','created_time','payload_json'),
 'order_snapshots':('id','snapshot_id','account_id','symbol','order_id','status','created_time','payload_json'),
 'algo_order_snapshots':('id','snapshot_id','account_id','symbol','algo_id','status','created_time','payload_json'),
 'protective_order_snapshots':('id','snapshot_id','account_id','symbol','algo_id','status','created_time','payload_json'),
 'trade_snapshots':('id','snapshot_id','account_id','symbol','trade_id','order_id','created_time','payload_json'),
 'execution_requests':('id','request_id','account_id','status','intent'),
 'recovery_items':('id','recovery_id','account_id','state','action'),
 'execution_attempts':('id','attempt_id','status','error_type','http_method'),
 'kill_switch_state':('id','switch_name','enabled','reason'),
 'health_checks':('id','check_id','component','status'),
 'audit_events':('id','event_id','entity_type','entity_id','account_id'),
 'sync_runs':('id','sync_run_id','account_id','symbol','status'),
 'account_anomaly_events':('id','event_id','account_id','anomaly_type','state','new_positions_locked')}


def declarations(raw):
    tree=ast.parse(raw);found={}
    for n in ast.walk(tree):
        if isinstance(n,ast.Constant) and type(n.value) is str:
            for match in re.finditer(r'(?i)\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?(\w+)["`\]]?\s*\(',n.value):
                table=match.group(1)
                if table not in REQUIRED:continue
                depth=1;quote=None;part=[];parts=[]
                for c in n.value[match.end():]:
                    if quote:
                        if c==quote:quote=None
                    elif c in ('"',"'",'`'):quote=c
                    elif c=='(':depth+=1
                    elif c==')':
                        depth-=1
                        if depth==0:
                            parts.append(''.join(part));break
                    if c==',' and depth==1 and quote is None:
                        parts.append(''.join(part));part=[]
                    else:part.append(c)
                if depth:continue # Incomplete/dynamic declaration remains unresolved.
                cols=set()
                for p in parts:
                    m=re.match(r'\s*["`\[]?(\w+)["`\]]?(?:\s|$)',p)
                    if m and m.group(1) in REQUIRED[table]:cols.add(m.group(1))
                found.setdefault(table,[]).append(cols)
    for cls in (n for n in ast.walk(tree) if isinstance(n,ast.ClassDef)):
        names={};columns=set()
        for n in cls.body:
            if isinstance(n,ast.Assign):
                for target in n.targets:
                    if isinstance(target,ast.Name):
                        if isinstance(n.value,ast.Constant):names[target.id]=n.value.value
                        if isinstance(n.value,ast.Call) and (
                            isinstance(n.value.func,ast.Name) and n.value.func.id=='Column' or
                            isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='Column'):
                            columns.add(target.id)
        table=names.get('__tablename__')
        if type(table) is str and table in REQUIRED:
            found.setdefault(table,[]).append(columns & set(REQUIRED[table]))
    return found


def main():
    if os.geteuid()==0 or os.uname().nodename!=HOST:raise RuntimeError('NONROOT_TOKYO_REQUIRED')
    root=ROOT;files=[];coverage={};total=0
    for folder in ('database','database/models','database/repositories'):
        parent=root/folder
        if not parent.exists():continue
        if not stat.S_ISDIR(parent.lstat().st_mode):raise RuntimeError('SOURCE_DIRECTORY_LINK')
        for p in sorted(parent.glob('*.py')):
            if len(files)>=128:raise RuntimeError('SOURCE_FILE_LIMIT')
            fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                s=os.fstat(fd)
                if not stat.S_ISREG(s.st_mode) or not 0<=s.st_size<=1048576:raise RuntimeError('SOURCE_FILE_BOUND')
                raw=os.read(fd,1048577)
                after=os.fstat(fd)
                if len(raw)!=s.st_size or any(getattr(s,k)!=getattr(after,k) for k in ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
                    raise RuntimeError('SOURCE_FILE_CHANGED')
            finally:os.close(fd)
            total+=len(raw)
            if total>8*1048576:raise RuntimeError('SOURCE_TOTAL_BOUND')
            row={'path':str(p.relative_to(root)),'sha256':hashlib.sha256(raw).hexdigest()}
            try:found=declarations(raw);row['ast_parse']='PASS'
            except (SyntaxError,UnicodeError):found={};row['ast_parse']='UNRESOLVED'
            files.append(row)
            for table,decls in found.items():coverage.setdefault(table,[]).extend(decls)
    result={}
    for table,columns in REQUIRED.items():
        decls=coverage.get(table,[])
        best=max(decls,key=len) if decls else set()
        result[table]={'source_declarations':len(decls),'required_columns_observed':sorted(best),
            'unresolved_columns':sorted(set(columns)-best),
            'contract':'SOURCE_COMPATIBLE_DECLARATION' if set(columns)<=best else 'UNRESOLVED_NOT_LIVE_SCHEMA_PROOF'}
    return {'host':HOST,'uid':os.geteuid(),'files':files,'required_contracts':result,
            'database_opened':False,'credentials_read':False,'production_imports':False,
            'evidence_scope':'SOURCE_DECLARATIONS_ONLY_NOT_ACTUAL_DB_SCHEMA'}

"""Bounded syntax-only checks on untrusted bytes. Never execute submitted code."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

PY_CHECK = """import json,sys
raw=sys.stdin.buffer.read(131073)
try:
 compile(raw.decode('utf-8'),'<submitted>','exec',dont_inherit=True)
 print(json.dumps({'state':'PASS_SYNTAX'}))
except (SyntaxError,UnicodeError,ValueError) as error:
 print(json.dumps({'state':'REJECT_SYNTAX','line':getattr(error,'lineno',None),'column':getattr(error,'offset',None),'error_type':type(error).__name__}))
"""
TS_CHECK = """const fs=require('fs');const ts=require(process.argv[1]);
const src=fs.readFileSync(0,'utf8');
const r=ts.transpileModule(src,{fileName:'submitted.ts',reportDiagnostics:true,
compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.ESNext}});
const errors=(r.diagnostics||[]).filter(d=>d.category===ts.DiagnosticCategory.Error);
console.log(JSON.stringify({state:errors.length?'REJECT_SYNTAX':'PASS_SYNTAX',
diagnostic_codes:errors.map(d=>d.code)}));
"""


def check_bytes(path, raw, typescript_module=None):
    if (not isinstance(path,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',path)
            or any(p in ('','.','..') for p in path.split('/'))):
        raise ValueError('UNSAFE_PATH')
    if type(raw) is not bytes or len(raw)>131072:
        raise ValueError('BOUNDED_BYTES_REQUIRED')
    receipt={'path':path,'sha256':hashlib.sha256(raw).hexdigest(),
             'bytes':len(raw),'code_executed':False,'security_approved':False}
    try:
        text=raw.decode('utf-8','strict')
        if '\x00' in text or '\r' in text:
            raise ValueError('NONCANONICAL_ENCODING')
    except (UnicodeError,ValueError):
        return dict(receipt,state='REJECT_ENCODING')
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    if path.endswith('.py'):
        argv=[sys.executable,'-I','-B','-c',PY_CHECK]
    elif path.endswith(('.sh','.bash')):
        argv=['/usr/bin/bash','--noprofile','--norc','-n']
    elif path.endswith(('.js','.mjs','.cjs')):
        node=shutil.which('node')
        if not node: return dict(receipt,state='HOLD_NODE_UNAVAILABLE')
        argv=[node,'--input-type='+('commonjs' if path.endswith('.cjs') else 'module'),'--check']
    elif path.endswith(('.ts','.tsx')):
        node=shutil.which('node')
        # Module path is an operator-owned checker dependency, never bundle data.
        if not node or not typescript_module or not os.path.isabs(typescript_module):
            return dict(receipt,state='HOLD_TYPESCRIPT_CHECKER_UNAVAILABLE')
        script=TS_CHECK.replace("fileName:'submitted.ts'", "fileName:'submitted.tsx'") if path.endswith('.tsx') else TS_CHECK
        argv=[node,'-e',script,typescript_module]
    elif path.endswith('.json'):
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result: raise ValueError('DUPLICATE_KEY')
                result[key]=value
            return result
        try:
            json.loads(text,object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE')))
            return dict(receipt,state='PASS_SYNTAX')
        except (ValueError,RecursionError):
            return dict(receipt,state='REJECT_SYNTAX')
    else:
        return dict(receipt,state='HOLD_UNSUPPORTED_FORMAT')
    try:
        proc=subprocess.run(argv,input=raw,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,env=env,timeout=5,check=False)
    except subprocess.TimeoutExpired:
        return dict(receipt,state='HOLD_CHECKER_TIMEOUT')
    except OSError:
        return dict(receipt,state='HOLD_CHECKER_UNAVAILABLE')
    # Parser stderr can quote source or secrets; never publish it.
    if path.endswith(('.py','.ts','.tsx')) and proc.returncode==0:
        try:
            value=json.loads(proc.stdout)
            if value.get('state') not in ('PASS_SYNTAX','REJECT_SYNTAX'):
                raise ValueError('BAD_CHECKER')
            return dict(receipt,**value)
        except (ValueError,TypeError):
            return dict(receipt,state='HOLD_CHECKER_PROTOCOL')
    return dict(receipt,state='PASS_SYNTAX' if proc.returncode==0 else 'REJECT_SYNTAX')

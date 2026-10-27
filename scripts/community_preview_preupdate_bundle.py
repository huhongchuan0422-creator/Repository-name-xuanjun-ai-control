"""Offline deterministic bundler; generates readonly Python/shell, never runs them.

Approved helper bodies are extracted byte-for-byte, not independently maintained.
No root-site path discovery, installation, source download or permission action.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PINS={
 'scripts/community_preview_version_inspect.py':'98773bcd199f5cb50d15fb3bba1b6959541a12c3f5f2a4879dcd88e5d3bb6cc3',
 'scripts/community_preview_update_composition.py':'6fb687b06aa6410ccc390611cdb572357534067615cf3588c32ca3c9ce006100',
 'scripts/community_preview_upgrade.py':'2584441af33e6db1c5d24596f6cbc82077364a0b2b18554c6ba550ec8f66e0ee'}


def selected(raw,names):
    tree=ast.parse(raw);lines=raw.splitlines(keepends=True);result=[];found=set()
    for node in tree.body:
        name=node.name if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else node.targets[0].id if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) else None
        if name in names:result.append(''.join(lines[node.lineno-1:node.end_lineno]));found.add(name)
    if found!=set(names):raise ValueError('APPROVED_HELPER_SELECTION_CHANGED')
    return '\n\n'.join(result)+'\n'


def build():
    sources={}
    for path,pin in PINS.items():
        raw=(ROOT/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('APPROVED_READONLY_SOURCE_CHANGED')
        sources[path]=raw.decode()
    observer=sources['scripts/community_preview_version_inspect.py']
    old=selected(sources['scripts/community_preview_upgrade.py'],{'ROOT','RUN','INSPECT_FIELDS','Rejected','validate'})
    helpers=selected(sources['scripts/community_preview_update_composition.py'],{'require','digest','canonical_isolation','stable_metadata','inspect_bound','PRIVATE_PROBE'})
    prefix='''# Generated exact readonly helper composition; no site installation or mutation.
import types,hashlib,json,os,re,stat
v=types.ModuleType('fixed_approved_observer')
'''
    prefix+='exec(compile('+repr(observer)+",'<approved-observer>','exec'),v.__dict__)\n"
    prefix+="original=types.ModuleType('fixed_original_readonly_validation')\n"
    prefix+='exec(compile('+repr(old)+",'<approved-validation>','exec'),original.__dict__)\n"
    prefix+="approved=types.ModuleType('fixed_b09_readonly_helpers')\napproved.__dict__.update(controller=types.SimpleNamespace(Hold=v.Hold),observation=v,original=original,plan=types.SimpleNamespace(DOCKER=v.DOCKER),hashlib=hashlib,json=json)\n"
    prefix+='exec(compile('+repr(helpers)+",'<approved-composition-readonly>','exec'),approved.__dict__)\n"
    thin=(ROOT/'scripts/community_preview_preupdate_observe.py').read_text()
    thin=thin.replace('from scripts import community_preview_version_inspect as v\n','').replace('from scripts import community_preview_update_composition as approved\n','')
    python=(prefix+thin).encode()
    shell=("#!/bin/bash\n# REVIEW CANDIDATE ONLY; no sudo/network/install outside bounded readonly Python.\nset -eu\nif [ \"$#\" -ne 0 ]; then exit 2; fi\ncommunity_preupdate_exit=0\n/usr/bin/python3 -I -B -S - <<'COMMUNITY_PREUPDATE_READONLY_PY' || community_preupdate_exit=$?\n".encode()+python.rstrip(b'\n')+
           b"\nCOMMUNITY_PREUPDATE_READONLY_PY\nprintf 'COMMUNITY_PREUPDATE_READONLY_EXIT_CODE=%s\\n' \"$community_preupdate_exit\"\nexit \"$community_preupdate_exit\"\n")
    return python,shell


def build_three():
    five,_=build()
    text=(ROOT/'scripts/community_preview_three_diagnostics.py').read_text().replace(
        'from scripts import community_preview_preupdate_observe as base\n','')
    prefix="import types\nbase=types.ModuleType('fixed_readonly_base')\n"
    prefix+='exec(compile('+repr(five.decode())+",'<fixed-readonly-base>','exec'),base.__dict__)\n"
    python=(prefix+text).encode()
    shell=(b"#!/bin/bash\n# REVIEW ONLY: three fixed objects, never executed by author.\nset -eu\nif [ \"$#\" -ne 0 ]; then exit 2; fi\ncommunity_three_exit=0\n/usr/bin/python3 -I -B -S - <<'COMMUNITY_THREE_READONLY_PY' || community_three_exit=$?\n"+python.rstrip(b'\n')+
        b"\nCOMMUNITY_THREE_READONLY_PY\nprintf 'COMMUNITY_THREE_EXIT_CODE=%s\\n' \"$community_three_exit\"\nexit \"$community_three_exit\"\n")
    return python,shell


if __name__=='__main__':
    python,shell=build()
    target=ROOT/'deploy/community-preview'
    (target/'preupdate-five-readonly.py').write_bytes(python)
    (target/'preupdate-five-readonly.sh').write_bytes(shell)
    python,shell=build_three()
    (target/'three-reasons-readonly.py').write_bytes(python)
    (target/'three-reasons-readonly.sh').write_bytes(shell)

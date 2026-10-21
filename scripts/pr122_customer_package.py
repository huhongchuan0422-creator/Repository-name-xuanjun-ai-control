"""Deterministic review-only source/dependency closure, no credentials or data."""
import argparse
import ast
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from scripts.pr122_customer_core import canonical,digest
ROOT=Path(__file__).resolve().parent.parent

def build(output,commit,tree):
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise ValueError('EXACT_COMMIT')
    paths={p.relative_to(ROOT).as_posix() for p in (ROOT/'scripts').glob('pr122_customer_*.py')}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'deploy/pr122-customer-center').rglob('*') if p.is_file())
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_pr122_customer_*.py'))
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('pr122_customer_*') if p.is_file())
    paths.add('docs/development/PR122_CUSTOMER_CENTER_CHANGE_CONTROL_20261016.md')
    paths.add('docs/development/PR122_CUSTOMER_CENTER_IDENTITY_CONTRACT_V1.md')
    paths.update({'docs/development/PR122_CUSTOMER_CENTER_PRIVATE_MATERIALS_RULES_V1_20261016.md','docs/development/PR122_CUSTOMER_CENTER_IMPLEMENTATION_20261016.md','.github/workflows/pr122-customer-center.yml'})
    pending=list(paths)
    while pending:
        name=pending.pop()
        if not name.endswith('.py'):continue
        for node in ast.walk(ast.parse((ROOT/name).read_text())):
            names=[]
            if isinstance(node,ast.Import):names=[x.name for x in node.names]
            if isinstance(node,ast.ImportFrom) and node.module:
                names=[node.module]
                if node.module.split('.')[0] in ('scripts','tests'):names +=[node.module+'.'+x.name for x in node.names]
            for mod in names:
                dep=mod.replace('.','/')+'.py'
                if (dep.startswith('scripts/') or dep.startswith('tests/')) and (ROOT/dep).is_file() and dep not in paths:paths.add(dep);pending.append(dep)
    files={p:(ROOT/p).read_bytes() for p in sorted(paths)}
    files['boot.py']=(ROOT/'deploy/pr122-customer-center/boot.py').read_bytes()
    manifest={'source_tree':tree,'schema':1,'state':'REVIEW_ONLY_NOT_DEPLOYED','source_commit':commit,'minimum_python':'3.11','cryptography':'46.0.3','files':[{'path':p,'size':len(b),'sha256':digest(b)} for p,b in sorted(files.items())]}
    raw=canonical(manifest);files['CUSTOMER_MANIFEST.json']=raw
    out=Path(output);out.mkdir(parents=True,exist_ok=True);archive=out/'PR122_CUSTOMER_CENTER_REVIEW_ONLY.tar.gz'
    stream=io.BytesIO()
    # gzip timestamp fixed for reproducibility.
    import gzip
    with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as gz:
        with tarfile.open(fileobj=gz,mode='w') as t:
            for p,b in sorted(files.items()):
                info=tarfile.TarInfo('customer-center/'+p);info.mode=0o644;info.mtime=0;info.size=len(b);t.addfile(info,io.BytesIO(b))
    archive.write_bytes(stream.getvalue())
    receipt={'source_commit':commit,'manifest_sha256':digest(raw),'tar_sha256':digest(archive.read_bytes()),'members':len(files),'bound_files':len(manifest['files']),'production':'NOT_DEPLOYED','independent_review':'PENDING'}
    (out/'CUSTOMER_PACKAGE_RECEIPT.json').write_bytes(canonical(receipt));print(json.dumps(receipt));return receipt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--source-commit',required=True);ap.add_argument('--source-tree',required=True);a=ap.parse_args();build(a.output,a.source_commit,a.source_tree)
if __name__=='__main__':main()

"""Package the full existing-code dependency closure for one-time review/install."""
import argparse
import ast
import json
from pathlib import Path
from scripts.pr122_showcase import canonical,sha,need
from scripts.pr122_showcase_package import tar_bytes

ROOT=Path(__file__).resolve().parents[1]

def code_files():
    pending=list((ROOT/'scripts').glob('pr122_showcase*.py'))+[ROOT/'scripts/pr122_website_release.py'];seen=set()
    while pending:
        path=pending.pop();name=path.relative_to(ROOT).as_posix()
        if name in seen:continue
        seen.add(name);tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            names=[]
            if isinstance(node,ast.ImportFrom) and node.module=='scripts':names=[n.name for n in node.names]
            elif isinstance(node,ast.ImportFrom) and node.module and node.module.startswith('scripts.'):names=[node.module.split('.')[1]]
            elif isinstance(node,ast.Import):names=[n.name.split('.')[1] for n in node.names if n.name.startswith('scripts.')]
            for module in names:
                target=ROOT/'scripts'/(module+'.py');need(target.is_file(),'MISSING_CODE_DEPENDENCY:'+module);pending.append(target)
    return sorted(seen)

def build(output,commit):
    names=code_files()+['deploy/pr122-showcase/'+name for name in ('locations.conf','xuanjun-showcase-publish.service','xuanjun-showcase-publish.timer','xuanjun-showcase-build.service','policy.example.json')]
    names+=['.github/workflows/pr122-site-hub-preflight.yml','.github/workflows/pr122-showcase-review-event.yml','docs/development/PR122_DYNAMIC_SHOWCASE_PROTOCOL_20261016.md','docs/development/PR122_CUSTOMER_CENTER_PRIVATE_MATERIALS_RULES_V1_20261016.md']
    names+=[p.relative_to(ROOT).as_posix() for p in (ROOT/'showcase').rglob('*') if p.is_file()]
    files={name:(ROOT/name).read_bytes() for name in names}
    manifest={'schema':1,'source_commit':commit,'state':'REVIEW_ONLY_NOT_INSTALLED','files':[{'path':name,'size':len(raw),'sha256':sha(raw)} for name,raw in sorted(files.items())]}
    raw=canonical(manifest);files['MECHANISM_MANIFEST.json']=raw
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    archive=tar_bytes(files,'showcase-mechanism/');(output/'SHOWCASE_MECHANISM_REVIEW_ONLY.tar.gz').write_bytes(archive)
    receipt={'source_commit':commit,'tar_sha256':sha(archive),'mechanism_manifest_sha256':sha(raw),'member_count':len(files),'production_changes':0,'state':'REVIEW_ONLY_NOT_INSTALLED'}
    (output/'SHOWCASE_MECHANISM_RECEIPT.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n');print(json.dumps(receipt,sort_keys=True));return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--source-commit',required=True);a=p.parse_args();build(a.output,a.source_commit)

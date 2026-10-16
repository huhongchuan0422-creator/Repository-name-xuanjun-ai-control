#!/usr/bin/env python3
"""Developer intake: create immutable project/page/module declarations, never publish."""
import argparse
import json
from pathlib import Path
import shutil
from scripts.pr122_showcase import ID,need,validate,sha,canonical,scan_public_tree

def register(args):
    for value in (args.project_id,args.id):need(ID.fullmatch(value),'INVALID_REGISTRATION_ID')
    root=args.registry/'projects'/args.project_id;root.mkdir(parents=True,exist_ok=True)
    need(not root.is_symlink(),'REGISTRY_SYMLINK')
    item={'kind':args.kind,'id':args.id,'project_id':args.project_id,'version':args.version,'visibility':'PUBLIC',
          'title':{'zh':args.title_zh,'en':args.title_en},'summary':{'zh':args.summary_zh,'en':args.summary_en}}
    target=root/(args.id+'-v'+str(args.version)+'.json');need(not target.exists(),'IMMUTABLE_DECLARATION_EXISTS')
    if args.kind=='project':
        need(args.id==args.project_id,'PROJECT_ID_MISMATCH');need(args.milestone,'REQUIRED_MILESTONES')
        item.update(state='DEVELOPING',scenarios=[{'zh':args.scenario_zh,'en':args.scenario_en}],required_milestones=args.milestone)
    elif args.kind=='page':
        need(args.public and args.public.is_dir(),'PUBLIC_BUNDLE_REQUIRED')
        destination=root/'views'/args.id/('v'+str(args.version))/'public';need(not destination.exists(),'IMMUTABLE_PAGE_VERSION_EXISTS')
        rows,_=scan_public_tree(args.public)
        need('index.html' in rows,'PAGE_INDEX_REQUIRED')
        item.update(href='/showcase/projects/'+args.project_id+'/views/'+args.id+'/v'+str(args.version)+'/',role=args.title_zh,
                    artifact_sha256=rows['index.html']['sha256'],release_artifact_sha256=sha(canonical(rows)))
        validate(item)
        # The same public-bundle guard used by the compiler verifies filenames,
        # size/type/paths before any version can enter a published package.
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(args.public,destination,symlinks=True)
        need(scan_public_tree(destination)[0]==rows,'SOURCE_CHANGED_DURING_REGISTRATION')
    else:
        need(args.requirements is not None,'MODULE_REQUIREMENTS_FILE_REQUIRED')
        item.update(module_id=args.module_id,package_sha256=args.package_sha256,demo_href=args.demo_href,requirements=json.loads(args.requirements.read_text()))
    validate(item)
    with target.open('x') as stream:stream.write(json.dumps(item,ensure_ascii=False,indent=2)+'\n')
    return {'state':'REGISTERED_PENDING_REVIEW','object_sha256':sha(canonical(item)),'path':str(target),'production_changes':0}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('kind',choices=('project','page','module'));p.add_argument('--registry',type=Path,default=Path('showcase'))
    for name in ('project-id','id','title-zh','title-en','summary-zh','summary-en'):p.add_argument('--'+name,required=True)
    p.add_argument('--version',type=int,required=True);p.add_argument('--public',type=Path);p.add_argument('--scenario-zh');p.add_argument('--scenario-en');p.add_argument('--milestone',action='append')
    p.add_argument('--requirements',type=Path);p.add_argument('--module-id');p.add_argument('--package-sha256');p.add_argument('--demo-href');print(json.dumps(register(p.parse_args()),ensure_ascii=False))

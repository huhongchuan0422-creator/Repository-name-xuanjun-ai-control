#!/usr/bin/env python3
"""Build a catalog from GitHub-verified reviews, or an explicit unpublished preview."""
import argparse
import json
from pathlib import Path
from scripts import pr122_showcase as display
from scripts.pr122_showcase_sources import reviewed_objects,module_prices,collect_review_ids

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,default=Path('showcase'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--discover-reviews',action='store_true')
    parser.add_argument('--review-comment-id',type=int,action='append',default=[])
    parser.add_argument('--reviewer',action='append',default=[])
    parser.add_argument('--published-pages',type=Path)
    parser.add_argument('--offer-store',type=Path);parser.add_argument('--cost-store',type=Path);parser.add_argument('--registered-packages',type=Path)
    args=parser.parse_args();objects=display.discover(args.registry)
    if args.preview:
        # This is visibly watermarked and cannot supply a release approval.
        approvals={display.sha(display.canonical(o)):{'decision':'PUBLIC_CONTENT_APPROVED','comment_id':None,'commit':None,'ci_run_id':None} for o in objects}
        pages={o['href']:{'artifact_sha256':o['artifact_sha256'],'release_artifact_sha256':o['release_artifact_sha256']} for o in objects if o['kind']=='page'}
    else:
        if args.discover_reviews:args.review_comment_id=collect_review_ids(set(args.reviewer))
        display.need(args.reviewer and args.review_comment_id,'VERIFIED_CONTENT_REVIEW_REQUIRED')
        approvals=reviewed_objects(args.review_comment_id,objects,set(args.reviewer))
        pages=json.loads(args.published_pages.read_text()) if args.published_pages else {}
    stores=(args.offer_store,args.cost_store,args.registered_packages)
    display.need(all(stores) or not any(stores),'ALL_AUTHORITY_STORES_REQUIRED')
    prices=module_prices(*stores[:2],json.loads(stores[2].read_text())) if all(stores) else {}
    owned_pages,project_files=display.project_public_pages(args.registry,objects,approvals)
    pages={**pages,**owned_pages}
    catalog=display.compile_catalog(objects,approvals,prices,pages)
    root=Path(__file__).resolve().parents[1]
    pins=json.loads((root/'deploy/pr122-site-hub-experience/HOST_PINS.json').read_text())
    shell=display.official_shell(root/'evidence/pr122-site-hub-experience/PR122_SITE_HUB_REVIEW_ONLY.tar.gz',pins['static_artifact_sha256'])
    manifest=display.render(catalog,args.output,args.preview,project_files,shell)
    (args.output/'SHOWCASE_MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'state':'PREVIEW_ONLY' if args.preview else 'REVIEWED_CANDIDATE_NOT_DEPLOYED','files':len(manifest['files']),'projects':len(catalog['projects']),'modules':len(catalog['modules']),'production_changes':0}))

if __name__=='__main__':main()

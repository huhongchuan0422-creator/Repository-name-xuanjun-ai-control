"""Read-only adapters. No approval signing, payments, database creation or writes."""
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
from scripts.pr122_showcase import need,canonical,sha
from scripts.community_saas_modules import catalog
from scripts.community_saas_offers import quote_offers

REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
WORKFLOW_ID=386249451

def github(path):
    headers={'Accept':'application/vnd.github+json','User-Agent':'XuanJun-Showcase-ReadOnly'}
    token=os.environ.get('GITHUB_TOKEN')
    if token:headers['Authorization']='Bearer '+token
    request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/'+path,headers=headers)
    with urllib.request.urlopen(request,timeout=20) as response:
        raw=response.read(2000001);need(len(raw)<=2000000,'GITHUB_RESPONSE_LIMIT');return json.loads(raw)

def verify_review(comment_id,objects,approved_reviewers,fetch=github,known_only=False):
    """Only real PR122 comments + exact successful CI may approve declarations.

    The reviewer allowlist is protected operator policy, not project content.
    A declaration's own approved/status flag is never an authority input.
    """
    need(type(comment_id) is int and comment_id>0,'COMMENT_ID')
    c=fetch('issues/comments/'+str(comment_id))
    need(c['id']==comment_id and c['user']['login'] in approved_reviewers and c.get('issue_url','').endswith('/issues/122'),'REVIEW_ORIGIN')
    body=c['body'].strip();need(body.startswith('XUANJUN_SHOWCASE_REVIEW\n'),'REVIEW_FORMAT')
    review=json.loads(body.split('\n',1)[1])
    need(review.get('decision') in ('PUBLIC_CONTENT_APPROVED','PUBLIC_CONTENT_REVOKED') and review.get('reviewer_role')=='INDEPENDENT_AUDITOR','INDEPENDENT_REVIEW_REQUIRED')
    commit=review['commit'];need(type(commit) is str and len(commit)==40 and all(ch in '0123456789abcdef' for ch in commit),'REVIEW_COMMIT')
    run=fetch('actions/runs/'+str(review['ci_run_id']))
    need(run['head_sha']==commit and run['status']=='completed' and run['conclusion']=='success' and run['workflow_id']==WORKFLOW_ID and run['event'] in ('push','workflow_dispatch'),'EXACT_CI_GATE')
    hashes={sha(canonical(o)) for o in objects}
    cache={}
    def blob(identifier):
        if identifier not in cache:cache[identifier]=fetch('git/blobs/'+identifier)
        return cache[identifier]
    need(type(review.get('object_sha256')) is list and review['object_sha256'] and all(type(h) is str and len(h)==64 and all(ch in '0123456789abcdef' for ch in h) for h in review['object_sha256']),'REVIEW_OBJECT_BINDING')
    admissions=review.get('module_admission_sha256',[])
    need(type(admissions) is list and all(h in review['object_sha256'] for h in admissions),'MODULE_ADMISSION_BINDING')
    known_modules={sha(canonical(o)) for o in objects if o['kind']=='module'}
    need(all(h in known_modules or (known_only and h not in hashes) for h in admissions),'MODULE_ADMISSION_KIND')
    if known_only:review['object_sha256']=[h for h in review['object_sha256'] if h in hashes]
    if not review['object_sha256']:return {}
    need(all(h in hashes for h in review['object_sha256']),'REVIEW_OBJECT_BINDING')
    # Verify the approved object bytes actually belonged to that tested commit.
    tree=fetch('git/trees/'+commit+'?recursive=1');need(not tree.get('truncated'),'TRUNCATED_SOURCE_TREE')
    blobs={row['sha'] for row in tree['tree'] if row['type']=='blob' and row['path'].startswith('showcase/projects/') and row['path'].endswith('.json') and len(row['path'].split('/'))==4}
    for item in objects:
        if sha(canonical(item)) in review['object_sha256']:
            # Author formatting differs from canonical hashing: read the declared
            # source path from the commit to compare parsed content below.
            matches=[row for row in tree['tree'] if row['type']=='blob' and row['sha'] in blobs]
            found=False
            for row in matches:
                import base64
                raw=blob(row['sha'])
                if json.loads(base64.b64decode(raw['content']))==item:found=True;break
            need(found,'OBJECT_NOT_IN_REVIEWED_COMMIT')
    return {h:{'decision':review['decision'],'comment_id':comment_id,'commit':commit,'ci_run_id':review['ci_run_id'],'module_admission':h in review.get('module_admission_sha256',[])} for h in review['object_sha256']}

def reviewed_objects(ids,objects,reviewers,fetch=github):
    result={};cache={}
    def cached(path):
        if path not in cache:cache[path]=fetch(path)
        return cache[path]
    for identifier in sorted(set(ids)):
        result.update(verify_review(identifier,objects,reviewers,cached,known_only=True))
    return result

def read_only_db(path):
    path=Path(path).resolve();need(path.is_file(),'AUTHORITY_STORE_MISSING')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);db.execute('PRAGMA query_only=ON');return db

def module_prices(offer_path,cost_path,package_bindings):
    """Reuse EFFECTIVE/PUBLIC offers and cost gates; retain both native currencies.

    package_bindings is supplied by the reviewed module registration service.
    No exchange rates, prices, cost evidence or listing status are invented.
    """
    offers=read_only_db(offer_path);costs=read_only_db(cost_path);result={}
    try:
        from scripts.community_saas_schema_guard import verify
        from scripts.community_saas_offers import SCHEMA as OFFER_SCHEMA
        from scripts.community_saas_cost_pricing import SCHEMA as COST_SCHEMA
        verify(offers,OFFER_SCHEMA,{'offers','components'})
        verify(costs,COST_SCHEMA,{'component_costs'})
        for module in catalog():
            identifier=module['id']
            if identifier not in package_bindings:continue
            quotes=quote_offers(offers,identifier,cost_db=costs)
            for quote in quotes:
                need(quote['mode'] in __import__('scripts.community_saas_offers',fromlist=['PAYMENT_MODES']).PAYMENT_MODES,'UNKNOWN_AUTHORITY_PAYMENT_MODE')
                for cadence,amount in quote['totals_by_cadence'].items():
                    need(cadence in ('ONCE','MONTHLY','YEARLY','PER_UNIT') and set(amount)=={'cny_minor','usd_minor'} and all(type(v) is int and 0<=v<=9007199254740991 for v in amount.values()),'INVALID_AUTHORITY_MONEY')
            if quotes:result[identifier]={'publication_eligible':True,'package_sha256':package_bindings[identifier],'offers':quotes,'purchase_href':None}
    finally:offers.close();costs.close()
    return result


def collect_review_ids(reviewers,fetch=github):
    result=[]
    for page in range(1,21):
        batch=fetch('issues/122/comments?per_page=100&page='+str(page))
        need(type(batch) is list,'COMMENTS_RESPONSE')
        result.extend(c['id'] for c in batch if c['user']['login'] in reviewers and c['body'].startswith('XUANJUN_SHOWCASE_REVIEW\n'))
        if len(batch)<100:return sorted(set(result))
    raise ValueError('COMMENT_HISTORY_LIMIT')

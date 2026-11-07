"""Fixed existing task-center Hosted CI evidence reader, GET-only/public.

Does not push, dispatch workflows, run generated code, grant a role or complete a
canonical task. A successful result is scoped test evidence for an exact tree.
"""
import base64,hashlib,json,re,time,urllib.request
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
REPO_ID=1413132159
WORKFLOW='.github/workflows/mcp-current-successor-gates.yml'
WORKFLOW_BLOB='3e4c1893bdbf8bb109912f4b37cd1103a9763cc4'
ALLOWED_FILES=frozenset((
 '.github/workflows/mcp-current-successor-gates.yml',
 'deploy/xuanjun-pr17-gateway-consumer.path.in',
 'deploy/xuanjun-pr17-gateway-consumer.service.in',
 'deploy/xuanjun-pr17-gateway-consumer.timer.in',
 'deploy/xuanjun-pr17-gateway-intake.service.in',
 'deploy/xuanjun-pr17-gateway-intake.timer.in',
 'deploy/xuanjun-pr17-gateway-publisher.path.in',
 'deploy/xuanjun-pr17-gateway-publisher.service.in',
 'deploy/xuanjun-pr17-gateway-publisher.timer.in',
 'scripts/development_review_continuation.py',
 'scripts/gateway_multifile_candidate.py',
 'scripts/github_runtime_ci.py',
 'scripts/original_gateway_readback.py',
 'scripts/original_gateway_transport.py',
 'scripts/pr17_gateway_bridge.py',
 'scripts/reusable_task_gateway.py',
 'scripts/task_center_mcp_development.py',
 'scripts/task_skill_admission.py',
 'scripts/task_supervisor.py',
 'tests/test_mcp_development_bridge.py',
 'tests/test_pr17_gateway_bridge.py',
 'tests/test_reusable_task_gateway.py'))
TEST_STEP='Validate exact current successor'
def require(ok,code):
 if not ok:raise ValueError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def _hex(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{40}',value) is not None

class GitHubRuntimeCI:
 def __init__(self):self.deadline=None;self.calls=0
 def _get(self,path):
  self.calls+=1;left=self.deadline-time.monotonic()
  require(left>0 and self.calls<=32,'CI_READ_DEADLINE')
  # Every path is constructed below from fixed endpoints plus bounded IDs/hashes.
  url='https://api.github.com/repos/'+REPO+'/'+path
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):raise ValueError('CI_REDIRECT_REFUSED')
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
  req=urllib.request.Request(url,headers={'Accept':'application/vnd.github+json','User-Agent':'xuanjun-fixed-runtime-ci','X-GitHub-Api-Version':'2022-11-28'})
  try:
   with opener.open(req,timeout=min(2,left)) as response:
    require(response.status==200,'CI_HTTP_SUCCESS_REQUIRED');raw=response.read(524289)
  except ValueError:raise
  except Exception:raise ValueError('CI_PUBLIC_READ_UNAVAILABLE') from None
  require(len(raw)<=524288 and time.monotonic()<=self.deadline,'CI_RESPONSE_BUDGET')
  def unique(pairs):
   out={}
   for k,v in pairs:
    require(k not in out,'CI_DUPLICATE_JSON_KEY');out[k]=v
   return out
  try:return json.loads(raw,object_pairs_hook=unique)
  except (TypeError,UnicodeError,RecursionError):raise ValueError('CI_INVALID_JSON') from None

 def verify(self,code_commit,branch,files,run_id):
  require(_hex(code_commit) and isinstance(branch,str) and re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){0,4}',branch),'CI_EXACT_CANDIDATE_REQUIRED')
  require(type(run_id)is int and 1<=run_id<10**14,'CI_RUN_ID_REQUIRED')
  require(isinstance(files,dict) and 1<=len(files)<=len(ALLOWED_FILES) and set(files)<=ALLOWED_FILES,'CI_ORIGINAL_WORKFLOW_SOURCE_SCOPE')
  require(all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in files.values()),'CI_FILE_DIGESTS_REQUIRED')
  self.deadline=time.monotonic()+8;self.calls=0
  run=self._get('actions/runs/'+str(run_id))
  workflow_id=run.get('workflow_id')
  require(type(workflow_id)is int and workflow_id>0,'CI_WORKFLOW_REGISTRATION_REQUIRED')
  registration=self._get('actions/workflows/'+str(workflow_id))
  require(registration.get('id')==workflow_id and registration.get('path')==WORKFLOW
   and registration.get('state')=='active','CI_WORKFLOW_REGISTRATION_MISMATCH')
  require(run.get('id')==run_id and run.get('workflow_id')==workflow_id and run.get('path')==WORKFLOW
   and run.get('event')=='pull_request' and run.get('head_sha')==code_commit and run.get('head_branch')==branch
   and run.get('repository',{}).get('id')==REPO_ID and run.get('head_repository',{}).get('id')==REPO_ID,'CI_RUN_BINDING_MISMATCH')
  require(run.get('status')=='completed' and run.get('conclusion')=='success' and type(run.get('run_attempt'))is int and run['run_attempt']>0,'CI_NOT_COMPLETED_SUCCESS')
  prs=run.get('pull_requests');require(isinstance(prs,list) and len(prs)==1,'CI_SINGLE_ORIGINAL_PR_REQUIRED')
  recorded=prs[0];number=recorded.get('number');require(type(number)is int and number>0,'CI_PR_ID_REQUIRED')
  pr=self._get('pulls/'+str(number));head=pr.get('head',{});base=pr.get('base',{})
  require(head.get('sha')==code_commit and head.get('ref')==branch and head.get('repo',{}).get('id')==REPO_ID
   and base.get('repo',{}).get('id')==REPO_ID and base.get('ref')=='main'
   and recorded.get('head',{}).get('sha')==code_commit and recorded.get('base',{}).get('sha')==base.get('sha'),'CI_PR_SNAPSHOT_CHANGED')
  merge=pr.get('merge_commit_sha');require(_hex(merge) and _hex(base.get('sha')),'CI_MERGE_SOURCE_REQUIRED')
  commit=self._get('git/commits/'+code_commit);tested=self._get('git/commits/'+merge)
  tree=commit.get('tree',{}).get('sha')
  require(commit.get('sha')==code_commit and tested.get('sha')==merge and _hex(tree)
   and tested.get('tree',{}).get('sha')==tree
   and [x.get('sha') for x in tested.get('parents',[])]==[base['sha'],code_commit],
   'CI_TESTED_MERGE_TREE_NOT_EXACT_CANDIDATE')
  # The pinned original workflow uses default PR-merge checkout. Same head/base
  # as the run plus exact merge tree equality establishes tested source bytes.
  workflow=self._get('contents/'+WORKFLOW+'?ref='+merge)
  require(workflow.get('sha')==WORKFLOW_BLOB and workflow.get('type')=='file','CI_WORKFLOW_CHANGED')
  jobs=self._get('actions/runs/'+str(run_id)+'/attempts/'+str(run['run_attempt'])+'/jobs?per_page=10')
  require(jobs.get('total_count')==1 and isinstance(jobs.get('jobs'),list) and len(jobs['jobs'])==1,'CI_EXACT_JOB_REQUIRED')
  job=jobs['jobs'][0];steps=job.get('steps',[])
  require(type(job.get('id'))is int and job['id']>0 and job.get('name')=='affected-gates' and job.get('run_id')==run_id and job.get('status')=='completed' and job.get('conclusion')=='success'
   and isinstance(steps,list) and len(steps)<=12 and sum(x.get('name')==TEST_STEP and x.get('conclusion')=='success' for x in steps)==1,
   'CI_FIXED_TEST_STEP_REQUIRED')
  for path,expected in sorted(files.items()):
   item=self._get('contents/'+path+'?ref='+code_commit)
   require(item.get('type')=='file' and item.get('encoding')=='base64' and type(item.get('size'))is int and 0<=item['size']<=131072,'CI_BOUNDED_SOURCE_REQUIRED')
   try:raw=base64.b64decode(item['content'],validate=False)
   except Exception:raise ValueError('CI_SOURCE_ENCODING') from None
   require(len(raw)==item['size'] and digest(raw)==expected,'CI_CANDIDATE_FILE_CHANGED')
  require(time.monotonic()<=self.deadline,'CI_READ_DEADLINE')
  return {'schema':1,'source':'GITHUB_FIXED_RUNTIME_CI','repository':REPO,'repository_id':REPO_ID,'workflow_path':WORKFLOW,
   'workflow_blob':WORKFLOW_BLOB,'workflow_id':workflow_id,'run_id':run_id,'run_attempt':run['run_attempt'],'job_id':job['id'],'pr_number':number,
   'code_commit':code_commit,'tested_merge_commit':merge,'tree':tree,'base_sha':base['sha'],'branch':branch,
   'files':dict(files),'test_step':TEST_STEP,'state':'TESTS_PASSED_EXACT_TREE','approval_generated':False,'workflow_dispatched':False}

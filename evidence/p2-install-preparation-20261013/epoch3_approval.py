"""Fresh PR58 exact-version approval. Old consumed decisions never match.

GitHub account provenance authenticates the repository account used by the
independent reviewer; human/agent independence still requires the review process.
"""
import hashlib,json,re,urllib.request
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
TX='c529c379-9341-4510-8384-fc6be1e412e5'
MARKER='CHATGPT_NATIVE_TASK5_EXACT_EPOCH3_RECOVERY_ACCEPTANCE\n'
DECISION='APPROVED_ONE_EXACT_EPOCH3_RESUME_WITH_FENCED_RETAIN_ON_FAILURE'
CONSUMED=frozenset((6160188919,6161965867))
SHA=re.compile(r'^[0-9a-f]{64}$')

def need(value,label):
 if not value:raise ValueError(label)
def unique(pairs):
 result={}
 for key,value in pairs:
  need(key not in result,'APPROVAL_DUPLICATE_JSON_KEY');result[key]=value
 return result
def decode(raw):
 return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('APPROVAL_NONFINITE')))
def expected(plan_sha,kit_sha,manifest_sha,snapshot_sha):
 for value in (plan_sha,kit_sha,manifest_sha,snapshot_sha):
  need(isinstance(value,str) and SHA.fullmatch(value),'APPROVAL_HASH_FORMAT')
 return {'schema':1,'reviewer':'CHATGPT_NATIVE_TASK5','decision':DECISION,'transaction_id':TX,
         'recovery_plan_sha256':plan_sha,'recovery_kit_manifest_sha256':kit_sha,
         'runtime_manifest_sha256':manifest_sha,'snapshot_sha256':snapshot_sha,
         'expected_epoch':3,'proposed_prepared_epoch':4,'authorized_attempts':1,
         'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','legacy_restart':False,
         'historical_notification_replay':False,'production_acceptance':'PENDING'}
def validate(raw,review_id,wanted):
 need(type(review_id) is int and review_id>0 and review_id not in CONSUMED,'APPROVAL_FRESH_ID_REQUIRED')
 need(isinstance(raw,bytes) and len(raw)<=65536,'APPROVAL_RESPONSE_BOUND')
 value=decode(raw.decode('utf-8','strict'))
 need(type(value.get('id')) is int and value['id']==review_id and
      value.get('user',{}).get('id')==332398908 and
      value.get('user',{}).get('login')=='huhongchuan0422-creator','APPROVAL_AUTHOR')
 need(value.get('issue_url')=='https://api.github.com/repos/'+REPO+'/issues/58','APPROVAL_DESTINATION')
 body=value.get('body');need(isinstance(body,str) and body.startswith(MARKER),'APPROVAL_MARKER')
 parsed=decode(body[len(MARKER):])
 # Canonical JSON distinguishes bool from int, unlike Python dict equality.
 canon=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
 need(canon(parsed)==canon(wanted),'APPROVAL_EXACT_BINDING')
 return {'review_id':review_id,'body_sha256':hashlib.sha256(body.encode()).hexdigest(),'approval':parsed}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('APPROVAL_REDIRECT_REFUSED')
def fetch(review_id,wanted):
 need(type(review_id) is int and review_id>0 and review_id not in CONSUMED,'APPROVAL_FRESH_ID_REQUIRED')
 request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/issues/comments/'+str(review_id),
                               headers={'Accept':'application/vnd.github+json','User-Agent':'xuanjun-exact-epoch3-recovery'})
 with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:
  raw=response.read(65537)
 return validate(raw,review_id,wanted)

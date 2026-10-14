"""Nonprivileged caller; verify real approval before a hash-pinned Root load."""
import argparse,hashlib,json,os,stat,subprocess,sys,urllib.request
EXPECTED='f4dd7e7c37dc9744a0697e09e9147b10cf325417c5b0e441e376905d9ef4922a'
REPO='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
MARKER='CHATGPT_NATIVE_TASK5_COMPLETE_INSTALL_ACCEPTANCE\n'
ROOT_LOADER=r'''
import hashlib,os,stat,sys
expected='f4dd7e7c37dc9744a0697e09e9147b10cf325417c5b0e441e376905d9ef4922a'
path=sys.argv[1]
if os.geteuid()!=0 or os.path.realpath(path)!=path:raise ValueError('ROOT_EXACT_SOURCE_REQUIRED')
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
with os.fdopen(fd,'rb') as f:
 i=os.fstat(f.fileno());b=f.read(65537)
if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1 or len(b)>65536 or hashlib.sha256(b).hexdigest()!=expected:raise ValueError('ROOT_EXECUTOR_SOURCE_HASH')
sys.argv=[path]+sys.argv[2:]
ns={'__name__':'__main__','__file__':path,'EXECUTOR_SHA256':expected}
exec(compile(b,path,'exec'),ns)
'''
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*a,**k):raise ValueError('CALLER_REVIEW_REDIRECT')
def main():
 p=argparse.ArgumentParser();p.add_argument('--binding',required=True);p.add_argument('--run-id',required=True);a=p.parse_args()
 fd=os.open(a.binding,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:
  i=os.fstat(f.fileno());b=f.read(16385)
 if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1 or len(b)>16384:raise ValueError('CALLER_BINDING_BOUND')
 binding=json.loads(b.decode());keys={'candidate','review_id','review_body_sha256','operation'}
 if set(binding)!=keys or type(binding['review_id']) is not int or binding['review_id']<=0 or binding['operation'] not in ('install','rollback'):raise ValueError('CALLER_EXACT_BINDING')
 headers={'Accept':'application/vnd.github+json'}
 if os.environ.get('GH_TOKEN'):headers['Authorization']='Bearer '+os.environ['GH_TOKEN']
 request=urllib.request.Request('https://api.github.com/repos/'+REPO+'/issues/comments/'+str(binding['review_id']),headers=headers)
 with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as r:raw=r.read(65537)
 if len(raw)>65536:raise ValueError('CALLER_REVIEW_BOUND')
 c=json.loads(raw.decode());body=c.get('body','')
 if c.get('id')!=binding['review_id'] or c.get('user',{}).get('login')!='huhongchuan0422-creator' or hashlib.sha256(body.encode()).hexdigest()!=binding['review_body_sha256'] or not body.startswith(MARKER):raise ValueError('CALLER_ACTUAL_APPROVAL')
 approval=json.loads(body[len(MARKER):])
 if approval.get('decision')!='APPROVED_FOR_PROTECTED_INSTALL_AND_FENCED_ROLLBACK' or approval.get('reviewer')!='CHATGPT_NATIVE_TASK5' or approval.get('release_granted') is not True or approval.get('executor_sha256')!=EXPECTED:raise ValueError('CALLER_INDEPENDENT_INSTALL_APPROVAL')
 path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'complete_install_executor.py')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
 with os.fdopen(fd,'rb') as f:b=f.read(65537);i=os.fstat(f.fileno())
 if not stat.S_ISREG(i.st_mode) or i.st_nlink!=1 or len(b)>65536 or hashlib.sha256(b).hexdigest()!=EXPECTED:raise ValueError('CALLER_EXECUTOR_HASH')
 argv=['/usr/bin/sudo','-n','/usr/bin/python3','-I','-B','-c',ROOT_LOADER,path,'--candidate',binding['candidate'],'--review-id',str(binding['review_id']),'--review-body-sha256',binding['review_body_sha256'],'--operation',binding['operation'],'--run-id',a.run_id]
 print('COMPLETE_INSTALL_CALLER_APPROVAL_AND_EXECUTOR_HASH=PASS',flush=True)
 return subprocess.run(argv,env={'PATH':'/usr/bin:/bin','LANG':'C'},timeout=1100).returncode
if __name__=='__main__':sys.exit(main())

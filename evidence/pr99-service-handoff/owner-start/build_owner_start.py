"""Derive the explicit Owner entry from the already published production helper.

This does not republish the restricted 40-file candidate or execute M99.
It removes the superseded reviewer requirement, retains real final-data proofs,
and retires only the original exact stopped candidate under its existing lock.
"""
import hashlib
from pathlib import Path

BASE=Path(__file__).parent
published=BASE.parent/'s09-install-candidate'
if not all((published/n).is_file() for n in ('production_start.py','stopped_transaction.py')):published=BASE.parent/'published-controller'
source=(published/'production_start.py').read_text()
stopped=(published/'stopped_transaction.py').read_text()
assert hashlib.sha256(source.encode()).hexdigest()=='d645edc0013af34804626315a6ddce1b47b870c012b6b632131c320ed4c20688'
assert hashlib.sha256(stopped.encode()).hexdigest()=='99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315'
source=source.replace('PR99 domestic production start candidate. Does not issue its own admission.',
 'PR99 Owner-direct domestic production entry. No reviewer or permit wait.')
source=source.replace('and exact root-held\nadmission.', 'and root-held exact technical start inputs.')
source=source.replace("PERMIT=Path('/etc/xuanjun-pr99/s09-production-start.admission.json')", "INPUTS=Path('/etc/xuanjun-pr99/domestic-final.start-inputs.json')")
source=source.replace('PERMIT','INPUTS').replace('permit_sha256','start_inputs_sha256')
old=" require(type(p['independent_review_comment_id']) is int and p['independent_review_comment_id']>0,'INDEPENDENT_REVIEW_REQUIRED')"
assert source.count(old)==1
source=source.replace(old," validate_owner_authority(p)")
source=source.replace('# Root-held admission is supplied by the original independent host authority.',
 '# Owner removed the review/permit wait; the remaining inputs bind actual data and effects.')
source=source.replace('# These bytes must ALSO be pinned by the original independent root-held permit.',
 '# These technical proof bytes must match the exact root-held start inputs.')
source=source.replace('def start():','def _start():')
source=source.replace(' # A new source hash requires a NEW exact independently issued private admission.\n # Historical approval and stopped-only permits cannot admit these changed bytes.',
 ' # Owner authority is explicit; exact final files/Fence/assignment remain required facts.')
source=source.replace(' p,payload=admit();STATE.mkdir(mode=0o700)',
 ' p,payload=admit();candidate=inspect_stopped_candidate();STATE.mkdir(mode=0o700)')
source=source.replace("  for n in payload:require(not os.path.lexists(SYSTEMD/n) and stopped(n),'UNIT_ALREADY_OWNED')", "  require(inspect_stopped_candidate()['kind']==candidate['kind'],'CANDIDATE_CHANGED')")
source=source.replace('  created={};journal=EffectJournal()\n  try:',
 "  created={};journal=EffectJournal()\n  journal.effect('retire-stopped-candidate',lambda:retire_stopped_candidate(p,candidate))\n  try:")
sequence=' forward=[\'create:\'+n for n in payload]'
assert source.count(sequence)==1
source=source.replace(sequence," if operations and operations[0]['operation']=='retire-stopped-candidate':\n  require(operations[0]['status']=='SUCCEEDED' or len(operations)==1,'OPERATION_AFTER_UNRESOLVED_RETIREMENT')\n  operations=operations[1:]\n"+sequence)
source=source.replace(" if r.returncode!=0:raise KnownEffectFailure('SYSTEMCTL_FAILED')", " if r.returncode!=0:\n  values=dict(l.split('=',1) for l in r.stdout.decode('utf-8','strict').splitlines() if '=' in l)\n  missing=(len(args)==4 and args[0]=='show' and args[-1]=='--no-pager' and r.returncode==1 and values.get('ActiveState')=='inactive' and values.get('MainPID')=='0' and values.get('LoadState','not-found')=='not-found')\n  if not missing:raise KnownEffectFailure('SYSTEMCTL_FAILED')")
source=source[:source.index("if __name__=='__main__':")]
helpers='''
OWNER_AUTHORITY={'mode':'OWNER_DIRECT','instruction_at':'2026-10-19T00:29:13+08:00','scope':'PR99_DOMESTIC_MIGRATION'}

def validate_owner_authority(p):
 require(p.get('owner_authority')==OWNER_AUTHORITY,'OWNER_AUTHORITY_BINDING')
 require(type(p.get('nonce'))is str and re.fullmatch('[A-Za-z0-9_-]{16,80}',p['nonce']),'OWNER_INPUT_NONCE')
 # A reviewer ID cannot replace Owner authority and is not required.
 return True

def stopped_library():
 require(sha(FROZEN_STOPPED.encode())=='99225aacc11cae6dc9d190015c95c9883e13d8e2691da864fb026f8afdfee315','ORIGINAL_STOPPED_SOURCE')
 n={'__name__':'original_stopped_definitions'}
 exec(compile(FROZEN_STOPPED,'original_stopped_definitions','exec'),n)
 n['PROTECTED']=tuple(sorted(set(n['PROTECTED'])|{'windows-interaction-http.service'}))
 n['systemctl']=ctl
 return n

def inspect_stopped_candidate():
 n=stopped_library();names=n['NAMES'];state=Path(n['STATE'])
 present=[os.path.lexists(SYSTEMD/name) for name in names]
 if not any(present):
  if os.path.lexists(state):
   # Previously installed candidates may only be absent after the exact
   # original terminal rollback; unexplained deletion is never adopted.
   receipt=json.loads(n['read_regular'](state/'rollback.receipt.json',private=True))
   require(receipt.get('status')=='OWNED_STOPPED_UNITS_REMOVED' and set(receipt.get('removed',[]))==set(names),'ORIGINAL_REMOVAL_UNKNOWN')
  require(all(stopped(name) for name in names),'TARGET_STILL_RUNNING')
  return {'kind':'NO_CANDIDATE','library':n}
 require(all(present),'PARTIAL_OR_FOREIGN_CANDIDATE')
 receipt=json.loads(n['read_regular'](state/'receipt.json',private=True))
 require(receipt.get('status')=='QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION' and receipt.get('manifest')==n['manifest']() and receipt.get('starts')==receipt.get('enables')==0,'ORIGINAL_STOPPED_RECEIPT')
 require(not os.path.lexists(state/'rollback.intent.json'),'ORIGINAL_RETIREMENT_ALREADY_CONSUMED')
 for name,data in n['unit_bytes']().items():
  require(n['read_regular'](SYSTEMD/name)==data and stopped(name),'FOREIGN_OR_RUNNING_CANDIDATE')
  marker=json.loads(n['read_regular'](state/(name+'.created'),private=True))
  require(marker.get('sha256')==n['digest'](data),'ORIGINAL_CANDIDATE_OWNERSHIP')
 return {'kind':'EXACT_OWNED_STOPPED_CANDIDATE','library':n}

def retire_stopped_candidate(p,candidate):
 require(inspect_stopped_candidate()['kind']==candidate['kind'],'CANDIDATE_CHANGED_BEFORE_RETIREMENT')
 if candidate['kind']=='NO_CANDIDATE':return {'status':'NO_CANDIDATE_TO_RETIRE'}
 require(candidate['kind']=='EXACT_OWNED_STOPPED_CANDIDATE','CANDIDATE_KIND')
 n=candidate['library'];state=Path(n['STATE'])
 # The original rollback removes ONLY its exact stopped bytes and records
 # its own before/after protected snapshots. It does not stop any service.
 n['rollback'](SYSTEMD,state,{'nonce':p['nonce']},sha(canonical(p['owner_authority'])))
 receipt=json.loads(n['read_regular'](state/'rollback.receipt.json',private=True))
 require(receipt.get('status')=='OWNED_STOPPED_UNITS_REMOVED' and set(receipt.get('removed',[]))==set(n['NAMES']),'ORIGINAL_RETIREMENT_TERMINAL_RECEIPT')
 return receipt

def start():
 from contextlib import ExitStack
 require(os.geteuid()==0 and os.uname().nodename==HOST,'HOST_ROOT')
 n=stopped_library();state=Path(n['STATE'])
 # Borrow the exact existing stopped-install lock across final admission,
 # removal and production installation. No second candidate claim is made.
 with ExitStack() as stack:
  if os.path.lexists(state):
   s=state.lstat();require(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700,'ORIGINAL_STOPPED_STATE')
   fd=os.open(state/'lock',os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC)
   stack.callback(os.close,fd)
   s=os.fstat(fd);require(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and stat.S_IMODE(s.st_mode)==0o600,'ORIGINAL_STOPPED_LOCK')
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  return _start()

if __name__=='__main__':
 import sys
 os.umask(0o077)
 if sys.argv[1:]==['query-only']:result=query_only()
 elif sys.argv[1:]==['start']:result=start()
 else:raise SystemExit('EXPECTED_START_OR_QUERY_ONLY')
 print(json.dumps(result,sort_keys=True))
'''
source+='\nFROZEN_STOPPED='+repr(stopped)+'\n'+helpers
compile(source,'owner_production_start.py','exec')
capacity={'__name__':'capacity_build_definitions'}
exec(compile((BASE/'apply_checkpoint_capacity.py').read_text(),'capacity_build','exec'),capacity)
source=capacity['repair'](source)
compile(source,'owner_production_start.py','exec')
(BASE/'owner_production_start.py').write_text(source)
print('OWNER_START_BUILD_COMPLETE source_sha256='+hashlib.sha256(source.encode()).hexdigest())

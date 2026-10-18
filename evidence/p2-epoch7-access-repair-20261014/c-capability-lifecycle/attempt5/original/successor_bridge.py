"""Offline adapter for a future independently approved Epoch7 5-attempt executor.
No production authority or original coordinator implementation is provided.
"""
from attempt_ledger import Ledger, _require
PHASES=tuple('phase_%02d'%i for i in range(1,17))
class Bridge(object):
 def __init__(self,ledger,authority,reconciler,executor):
  _require(isinstance(ledger,Ledger) and all(callable(f) for f in (authority,reconciler,executor)),'DEPENDENCY')
  self.ledger,self.authority,self.reconciler,self.executor=ledger,authority,reconciler,executor
 def fence(self,aid,phase):
  v=self.authority(self.ledger.grant,aid,phase)
  _require(type(v) is dict and set(v)=={'writer','lease','fence','exclusive','digest'},'FENCE_PROOF')
  _require(all(v[k] is True for k in ('writer','lease','fence','exclusive')) and type(v['digest']) is str and len(v['digest'])==64,'GLOBAL_FENCE_UNKNOWN')
 def begin(self,command_sha):
  self.fence('CANDIDATE','before_claim')
  aid=self.ledger.claim()
  self.fence(aid,'claim')
  self.ledger.intent(aid,command_sha)
  return aid
 def phases(self,aid,bindings):
  _require(type(bindings) is dict and set(bindings)==set(PHASES),'PHASE_CLOSURE')
  state=self.ledger.snapshot()
  _require(state['attempts'] and state['attempts'][-1]['id']==aid and state['attempts'][-1]['state']=='INTENT_RECORDED','INTENT_REQUIRED')
  for name in PHASES:
   self.fence(aid,name)
   digest=bindings[name]
   _require(type(digest) is str and len(digest)==64,'STAGE_DIGEST')
   old=[row for row in self.ledger.snapshot()['completed'] if row['name']==name]
   if old:
    _require(old[0]['sha256']==digest and self.reconciler(aid,name,digest,'SKIP') is True,'REPLAY_UNVERIFIED')
    continue
   result=self.executor(aid,name,digest)
   _require(type(result) is dict and set(result)=={'status','effect_sha256','log_sha256'} and result['status']=='SUCCESS' and result['effect_sha256']==digest and type(result['log_sha256']) is str and len(result['log_sha256'])==64,'EFFECT_UNKNOWN')
   _require(self.reconciler(aid,name,digest,'COMPLETE') is True,'EFFECT_UNRECONCILED')
   self.ledger.checkpoint(aid,name,digest)
  return 'ALL_16_VERIFIED'
 def terminal(self,aid,proof):
  self.fence(aid,'terminal')
  return self.ledger.reconcile(aid,proof,lambda x:self.reconciler(aid,'TERMINAL',x,'RECONCILE') is True)

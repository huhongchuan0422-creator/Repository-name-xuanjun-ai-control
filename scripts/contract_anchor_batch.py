"""Offline batch policy and Merkle proofs; no network, tokens or legal claims."""
import hashlib

def _digest(data): return hashlib.sha256(data).digest()
def _leaf(commitment):
 if not isinstance(commitment,str) or len(commitment)!=64:raise ValueError('INVALID_COMMITMENT')
 try: raw=bytes.fromhex(commitment)
 except ValueError:raise ValueError('INVALID_COMMITMENT')
 if len(raw)!=32:raise ValueError('INVALID_COMMITMENT')
 return _digest(b'\x00'+raw)
def due(count, oldest_age_seconds, max_count=100, max_age_seconds=300):
 for n in (count,oldest_age_seconds,max_count,max_age_seconds):
  if type(n) is not int or n<0:raise ValueError('INVALID_THRESHOLD')
 if max_count==0 or max_age_seconds==0:raise ValueError('INVALID_THRESHOLD')
 return count>0 and (count>=max_count or oldest_age_seconds>=max_age_seconds)
def batch(commitments):
 if not commitments or len(commitments)>10000 or len(set(commitments))!=len(commitments):raise ValueError('INVALID_BATCH')
 nodes=[_leaf(c) for c in commitments];paths=[[] for _ in nodes];groups=[[i] for i in range(len(nodes))]
 while len(nodes)>1:
  next_nodes=[];next_groups=[]
  for i in range(0,len(nodes),2):
   j=min(i+1,len(nodes)-1)
   for k in groups[i]:paths[k].append({'side':'right','hash':nodes[j].hex()})
   if j!=i:
    for k in groups[j]:paths[k].append({'side':'left','hash':nodes[i].hex()})
   next_nodes.append(_digest(b'\x01'+nodes[i]+nodes[j]));next_groups.append(groups[i]+(groups[j] if j!=i else []))
  nodes,groups=next_nodes,next_groups
 return {'root':nodes[0].hex(),'proofs':paths,'chain_status':'NOT_SUBMITTED'}
def verify(commitment,proof,root):
 try:
  node=_leaf(commitment)
  for item in proof:
   sibling=bytes.fromhex(item['hash'])
   if len(sibling)!=32 or item['side'] not in ('left','right'):return False
   node=_digest(b'\x01'+(sibling+node if item['side']=='left' else node+sibling))
  return node.hex()==root
 except (TypeError,KeyError,ValueError):return False

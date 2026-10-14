"""Compile the finite private recovery plan from byte-pinned existing inputs.

No writes. The returned private plan contains original reference metadata and
must stay protected on the host. Publish its digest, not its content.
"""
import copy,hashlib,json,pathlib
from inspect_epoch3 import C,T
from prepare_epoch5_bindings import proposal
from build_epoch5_runtime import SOURCE_COMMIT,SOURCE_TREE
MANIFEST='153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7'
ROOT=C+'/epoch5-recovery-candidate-v4/xuanjun-p2-package'
TLS_CONFIG=T+'/epoch6-tls-renewal-candidate.json'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(value,label):
 if not value:raise ValueError(label)

def compile_plan(original_bytes,old_root,new_root):
 public,binding=proposal(original_bytes,old_root,new_root)
 need(public['new_manifest_sha256']==MANIFEST,'EPOCH5_EXACT_MANIFEST')
 original=json.loads(original_bytes.decode());runtime=copy.deepcopy(original['runtime'])
 runtime['release_directory']=public['new_release_directory']
 runtime['provisioning']=binding['provisioning']
 by_target={r['target']:r for r in runtime['provisioning']}
 plugin=runtime['plugin']
 for path_key,hash_key in (('binding_file','binding_sha256'),('ledger_client_config','ledger_client_sha256'),
                           ('gateway_relay_config','gateway_relay_sha256')):
  plugin[hash_key]=by_target[plugin[path_key]]['rendered_sha256']
 tls_raw=binding['tls_config_bytes'].encode()
 runtime['tls_renewal']={'path':TLS_CONFIG,'sha256':sha(tls_raw)}
 artifact={'root':ROOT,'manifest':ROOT+'/deploy/integration-manifest.json',
           'manifest_sha256':MANIFEST,'source_commit':SOURCE_COMMIT,'source_tree':SOURCE_TREE,
           'releases':'/opt/xuanjun-control-releases'}
 plan={'schema':1,'transaction_id':original['transaction_id'],
       'operation':'ONE_EXACT_EPOCH5_RETAINED_RECOVERY','expected_epoch':5,'proposed_epoch':6,
       'failure_policy':'FENCE_STOP_RETAIN_NO_REPLAY','automatic_retry':False,
       'original_plan_sha256':sha(original_bytes),'artifact':artifact,'runtime':runtime,
       'activation_proposal':binding['activation_proposal'],'cutover':copy.deepcopy(original['cutover']),
       'auth':copy.deepcopy(original['auth']),'tls':copy.deepcopy(original['tls']),
       'tls_config_bytes':binding['tls_config_bytes'],
       'historical_notification_replay':False,'legacy_writer_restart':False}
 need(plan['runtime']['legacy_cutover']==plan['cutover'],'EPOCH5_CUTOVER_BINDING')
 return plan

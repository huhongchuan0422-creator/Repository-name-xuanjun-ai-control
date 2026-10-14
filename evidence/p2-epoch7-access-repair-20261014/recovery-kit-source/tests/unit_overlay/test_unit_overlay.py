"""Static service/compiler access contracts; no systemd or privilege operations."""
import hashlib
import json
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=ROOT.parents[1]
FROZEN=WORK/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package'
OVERLAY=ROOT/'unit-overlay'
EXPECTED={
 'deploy/xuanjun-ledger.service':('Group=xuanjun-control-db\n','Group=xuanjun-control-db\nSupplementaryGroups=xuanjun-dispatcher\n'),
 'deploy/xuanjun-github-intake.service':('Group=xuanjun-control-db\n','Group=xuanjun-control-db\nSupplementaryGroups=xuanjun-dispatcher\n'),
 'deploy/xj-root-broker.service':('Group=root\n','Group=root\nSupplementaryGroups=xuanjun-ledger-client\n'),
 'deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service':('Group=xuanjun-control-db\n','Group=xuanjun-control-db\nSupplementaryGroups=xuanjun-ledger-client\nInaccessiblePaths=/etc/xuanjun-owner-callback/owner-user-id /etc/xuanjun-owner-callback/owner-chat-id /etc/xuanjun-owner-callback/owner-callback-auth /etc/xuanjun-owner-callback/owner-callback-hmac\n'),
 'deploy/xj-root-broker.socket':('DirectoryMode=0750\n','DirectoryMode=0711\n'),
}


def unit(path):
 source=OVERLAY/path if (OVERLAY/path).exists() else FROZEN/path
 out={}
 for line in source.read_text().splitlines():
  if line and not line.startswith(('#','[')) and '=' in line:
   key,value=line.split('=',1);out.setdefault(key,[]).append(value)
 return out


def permission(uid,groups,owner,group,mode,mask):
 """Pure DAC model with no capabilities/ACL; not a kernel acceptance test."""
 bits=(mode>>6)&7 if uid==owner else ((mode>>3)&7 if group in groups else mode&7)
 return bits&mask==mask


class UnitOverlayTests(unittest.TestCase):
 def test_exact_five_unit_scope(self):
  files={str(p.relative_to(OVERLAY)) for p in (OVERLAY/'deploy').rglob('*') if p.is_file()}
  self.assertEqual(files,set(EXPECTED))

 def test_only_justified_deltas(self):
  for path,(before,after) in EXPECTED.items():
   source=ROOT/path if path=='deploy/xuanjun-ledger.service' else FROZEN/path
   self.assertEqual((OVERLAY/path).read_text(),source.read_text().replace(before,after))

 def test_ledger_config_and_client_binding_are_distinct_rights(self):
  u=unit('deploy/xuanjun-ledger.service')
  self.assertEqual(u['User'],['xuanjun-dispatcher'])
  self.assertEqual(u['Group'],['xuanjun-control-db'])
  self.assertEqual(u['SupplementaryGroups'],['xuanjun-dispatcher'])
  self.assertTrue(permission(1003,{1003,1006},0,1003,0o640,4)) # dispatcher.json
  self.assertFalse(permission(1003,{1003,1006},0,1002,0o640,4)) # native client config: ACL required
  self.assertFalse(permission(1003,{1003,1006},1002,1002,0o600,4)) # Gateway private profile

 def test_intake_has_relay_socket_group_only(self):
  u=unit('deploy/xuanjun-github-intake.service')
  self.assertEqual(u['SupplementaryGroups'],['xuanjun-dispatcher'])
  self.assertTrue(permission(1003,{1003,1006},1002,1003,0o660,2))
  self.assertNotIn('xuanjun-ledger-client',u['SupplementaryGroups'][0])
  self.assertEqual(unit('deploy/xuanjun-p2-gateway-relay.socket')['SocketGroup'],['xuanjun-dispatcher'])

 def test_capless_broker_requires_client_group_without_db_group(self):
  u=unit('deploy/xj-root-broker.service')
  self.assertEqual(u['User'],['root']);self.assertEqual(u['Group'],['root'])
  self.assertEqual(u['SupplementaryGroups'],['xuanjun-ledger-client'])
  self.assertEqual(u['CapabilityBoundingSet'],[''])
  self.assertFalse(permission(0,{0},1003,1007,0o660,2))
  self.assertTrue(permission(0,{0,1007},1003,1007,0o660,2))
  self.assertFalse(permission(0,{0,1007},1003,1006,0o600,4))

 def test_dashboard_callback_socket_membership_without_db_grant(self):
  for path in ('deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service',
               'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service'):
   u=unit(path)
   self.assertEqual(u['User'],['xuanjun-callback'])
   self.assertEqual(u['Group'],['xuanjun-control-db'])
   self.assertEqual(u['SupplementaryGroups'],['xuanjun-ledger-client'])
   self.assertEqual(u['CapabilityBoundingSet'],[''])
   self.assertTrue(permission(1004,{1006,1007},1003,1007,0o660,2))
   self.assertFalse(permission(1004,{1006,1007},1003,1006,0o600,4))
   self.assertFalse(permission(1004,{1006,1007},1003,1006,0o700,1))

 def test_dashboard_masks_only_exact_callback_secrets(self):
  u=unit('deploy/uk-owner-workbench/xuanjun-uk-owner-dashboard.service')
  expected={'/etc/xuanjun-owner-callback/'+name for name in
            ('owner-user-id','owner-chat-id','owner-callback-auth','owner-callback-hmac')}
  actual=set(' '.join(u['InaccessiblePaths']).split())
  self.assertEqual(actual,expected)
  token='/etc/xuanjun-owner-callback/owner-dashboard-token'
  self.assertFalse(any(token==p or token.startswith(p+'/') for p in actual))
  self.assertNotIn('/etc/xuanjun-owner-callback',actual)
  self.assertTrue(all(not path.startswith('-') for path in actual))
  self.assertIn('--token-file '+token,u['ExecStart'][0])

 def test_callback_secrets_remain_available_to_callback_unit(self):
  u=unit('deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service')
  self.assertNotIn('InaccessiblePaths',u)
  for name in ('owner-user-id','owner-chat-id','owner-callback-auth','owner-callback-hmac'):
   self.assertIn('/etc/xuanjun-owner-callback/'+name,u['ExecStart'][0])

 def test_gateway_bridge_inherits_service_scoped_client_group(self):
  u=unit('deploy/xuanjun-uk-openclaw-p2-docker.conf')
  self.assertEqual(u['SupplementaryGroups'],['docker xuanjun-ledger-client'])
  self.assertTrue(permission(1002,{1002,1007},1003,1007,0o660,2))
  self.assertTrue(permission(1002,{1002,1007},0,1002,0o640,4))

 def test_dispatcher_retains_relay_and_existing_socket_groups(self):
  u=unit('deploy/xuanjun-development-dispatcher.service')
  self.assertEqual(u['Group'],['xuanjun-dispatcher'])
  self.assertEqual(u['SupplementaryGroups'],['xuanjun-ledger-client'])
  self.assertTrue(permission(1003,{1003,1006,1007},1002,1003,0o660,2))
  self.assertTrue(permission(1003,{1003,1006,1007},0,1003,0o660,2))

 def test_all_shared_socket_parents_use_0711_and_leaf_modes_stay_0660(self):
  expected={
   'deploy/xj-root-broker.socket':('root','xuanjun-dispatcher','broker.sock'),
   'deploy/xuanjun-ledger.socket':('xuanjun-dispatcher','xuanjun-ledger-client','ledger.sock'),
   'deploy/xuanjun-p2-gateway-relay.socket':('xuanjun_dev','xuanjun-dispatcher','p2-gateway.sock')}
  for path,(owner,group,leaf) in expected.items():
   u=unit(path)
   self.assertEqual(u['DirectoryMode'],['0711'])
   self.assertEqual(u['SocketMode'],['0660'])
   self.assertEqual(u['SocketUser'],[owner]);self.assertEqual(u['SocketGroup'],[group])
   self.assertEqual(u['ListenStream'],['/run/xuanjun-development/'+leaf])
  for uid,groups in ((1002,{1002,1007}),(1003,{1003,1006}),(1004,{1006,1007})):
   self.assertTrue(permission(uid,groups,0,0,0o711,1))
   self.assertFalse(permission(uid,groups,0,0,0o711,4))

 def test_worker_and_nginx_cannot_connect_or_read_database(self):
  for uid in (1005,1008):
   groups={uid}
   for owner,group in ((1003,1007),(0,1003),(1002,1003)):
    self.assertFalse(permission(uid,groups,owner,group,0o660,2))
   self.assertFalse(permission(uid,groups,1003,1006,0o600,4))
   self.assertFalse(permission(uid,groups,0,1002,0o640,4))

 def test_ledger_only_capability_and_native_abi_filter(self):
  ledger=unit('deploy/xuanjun-ledger.service')
  self.assertEqual(ledger['CapabilityBoundingSet'],['CAP_SYS_PTRACE'])
  self.assertEqual(ledger['AmbientCapabilities'],['CAP_SYS_PTRACE'])
  self.assertEqual(ledger['SystemCallFilter'],['~ptrace process_vm_readv process_vm_writev'])
  self.assertEqual(ledger['SystemCallArchitectures'],['native'])
  for path in EXPECTED:
   if path.endswith('.service'):
    u=unit(path)
    self.assertEqual(u['ProtectHome'],['yes'])
    self.assertEqual(u['NoNewPrivileges'],['yes'])
    self.assertEqual(u['ProtectSystem'],['strict'])
    if path!='deploy/xuanjun-ledger.service':
     self.assertEqual(u['CapabilityBoundingSet'],[''])
     self.assertNotIn('AmbientCapabilities',u)

 def test_no_readwrite_expansion_or_global_nss_change(self):
  for path in EXPECTED:
   if not path.endswith('.service'):continue
   def values(text,key):return [x for x in text.splitlines() if x.startswith(key+'=')]
   old=(FROZEN/path).read_text();new=(OVERLAY/path).read_text()
   self.assertEqual(values(old,'ReadWritePaths'),values(new,'ReadWritePaths'))
   self.assertEqual(values(old,'ExecStart'),values(new,'ExecStart'))
  raw=(FROZEN/'deploy/integration-manifest.json').read_bytes()
  self.assertEqual(hashlib.sha256(raw).hexdigest(),'153653ebc48d6b20680e513402dad077d50dce953ab3d4b7cc1748bcff0f64e7')
  manifest=json.loads(raw.decode())
  for path in ('stage1/p2_prerequisites.py','stage1/p2_fixed_host_runtime.py',
               'stage1/p2_legacy_adoption.py','deploy/xuanjun-uk-openclaw-p2-docker.conf'):
   self.assertEqual(hashlib.sha256((FROZEN/path).read_bytes()).hexdigest(),manifest['files'][path])
  self.assertFalse(any(p.suffix=='.py' for p in OVERLAY.rglob('*')))


if __name__=='__main__':unittest.main(verbosity=2)

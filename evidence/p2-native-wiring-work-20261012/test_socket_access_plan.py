import copy, os, pathlib, sys, tempfile, unittest
from unittest.mock import patch
ROOT=pathlib.Path(os.environ['P2_SOURCE_ROOT']);sys.path.insert(0,str(ROOT/'stage1'))
import p2_prerequisites as p
def plan():
 groups={'xuanjun-dispatcher':1003,'xuanjun-callback':1004,'xj_codex_worker':1005,
  'xuanjun-control-db':1006,'xuanjun-ledger-client':1007}
 return {'schema':1,'groups':groups,'users':{name:{'uid':groups[name],'gid':groups[name],
  'home':'/var/lib/xuanjun-development/users/'+name,
  'groups':[] if name=='xj_codex_worker' else ['xuanjun-control-db']} for name in p.USERS},
  'directories':[{'path':'/opt/xuanjun-runtime','uid':0,'gid':0,'mode':0o755}],'binaries':[]}
class SocketPlan(unittest.TestCase):
 def test_exact_client_group(self):self.assertTrue(p.validate(plan()))
 def test_missing_group_rejected(self):
  value=plan();del value['groups']['xuanjun-ledger-client']
  with self.assertRaises(ValueError):p.validate(value)
 def test_aliased_db_gid_rejected(self):
  value=plan();value['groups']['xuanjun-ledger-client']=1006
  with self.assertRaises(ValueError):p.validate(value)
 def test_no_global_client_membership(self):
  for name in p.USERS:
   value=plan();value['users'][name]['groups'].append('xuanjun-ledger-client')
   with self.assertRaises(ValueError):p.validate(value)
 def test_global_gateway_group_member_rejected(self):
  def named(name):
   if name=='xuanjun-ledger-client':return type('G',(),{'gr_gid':1007,'gr_mem':['xuanjun_dev']})()
   raise KeyError(name)
  def missing(gid):raise KeyError(gid)
  with tempfile.TemporaryDirectory() as directory:
   runtime=p.Prerequisites(directory);runtime.authority=lambda:None
   with patch.object(p.grp,'getgrnam',side_effect=named),patch.object(p.grp,'getgrgid',side_effect=missing):
    with self.assertRaisesRegex(ValueError,'UNREVIEWED_GROUP_MEMBERS'):runtime.preflight(plan())
 def test_parent_traversal_and_socket_mode(self):
  for rel in ('xuanjun-ledger.socket','xuanjun-p2-gateway-relay.socket'):
   text=(ROOT/'deploy'/rel).read_text();self.assertIn('DirectoryMode=0711',text);self.assertIn('SocketMode=0660',text)
  self.assertIn('SocketGroup=xuanjun-ledger-client',(ROOT/'deploy/xuanjun-ledger.socket').read_text())
 def test_gateway_has_no_database_group(self):
  text=(ROOT/'deploy/xuanjun-uk-openclaw-p2-docker.conf').read_text()
  self.assertIn('SupplementaryGroups=docker xuanjun-ledger-client',text);self.assertNotIn('xuanjun-control-db',text)
 def test_dispatcher_and_callback_service_membership(self):
  for rel in ('xuanjun-development-dispatcher.service','uk-owner-workbench/xuanjun-uk-owner-callback.service'):
   self.assertIn('SupplementaryGroups=xuanjun-ledger-client',(ROOT/'deploy'/rel).read_text())
if __name__=='__main__':unittest.main(verbosity=2)

"""Give typed socket clients service-scoped access without database group access."""
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1]);mp=root/'deploy/integration-manifest.json';manifest=json.loads(mp.read_text())
edits={
 'stage1/p2_prerequisites.py':[
  ("GROUPS = USERS | {'xuanjun-control-db'}", "GROUPS = USERS | {'xuanjun-control-db', 'xuanjun-ledger-client'}"),
  ("            allowed={'xuanjun-dispatcher','xuanjun-callback'} if name=='xuanjun-control-db' else {name}",
   "            allowed=({'xuanjun-dispatcher','xuanjun-callback'} if name=='xuanjun-control-db'\n                     else set() if name=='xuanjun-ledger-client' else {name})")],
 'deploy/xuanjun-ledger.socket':[
  ('SocketGroup=xuanjun-control-db','SocketGroup=xuanjun-ledger-client'),
  ('DirectoryMode=0750','DirectoryMode=0711')],
 'deploy/xuanjun-p2-gateway-relay.socket':[('DirectoryMode=0750','DirectoryMode=0711')],
 'deploy/xuanjun-uk-openclaw-p2-docker.conf':[
  ('SupplementaryGroups=docker','SupplementaryGroups=docker xuanjun-ledger-client')],
 'deploy/xuanjun-development-dispatcher.service':[
  ('Group=xuanjun-dispatcher\n','Group=xuanjun-dispatcher\nSupplementaryGroups=xuanjun-ledger-client\n')],
 'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service':[
  ('Group=xuanjun-control-db\n','Group=xuanjun-control-db\nSupplementaryGroups=xuanjun-ledger-client\n')]
}
pins={'stage1/p2_prerequisites.py':'b39355a8378e81ab4e045fd8fdac73f12dbed2ca7c4c6bd79120015a18ea30f1',
 'deploy/xuanjun-ledger.socket':'3a1e7c9d12ba01c99c76a3ab4a75efa9b4756130387fecbe4e02a5967729ff72',
 'deploy/xuanjun-p2-gateway-relay.socket':'6e5be375be0ddb78a710253cafff8330d54b6c84f7118a8ae440c15eaf1a0f7f',
 'deploy/xuanjun-uk-openclaw-p2-docker.conf':'885fd26828b88dc369b6477fdad50fd02f207789e7ae726f130f2f577756cf4f',
 'deploy/xuanjun-development-dispatcher.service':'6b76b43ab2c12ac235acaf0db6768912c6a9fb143c06c3c7c0e56a5e7d1bf2d3',
 'deploy/uk-owner-workbench/xuanjun-uk-owner-callback.service':'b71ac796718c44933c182e84fbd7630df315876dddb8e1d65ebd6d9e93a4c68a'}
texts={}
for rel,pairs in edits.items():
 raw=(root/rel).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pins[rel] or manifest['files'].get(rel)!=pins[rel]:raise ValueError('SOCKET_BASE_HASH')
 text=raw.decode()
 for old,new in pairs:
  if text.count(old)!=1:raise ValueError('SOCKET_ANCHOR')
  text=text.replace(old,new)
 texts[rel]=text
for rel,text in texts.items():
 (root/rel).write_text(text);manifest['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
mp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print('SERVICE_SCOPED_SOCKET_ACCESS_OVERLAY=PASS; NSS_CHANGED=NO; INSTALL=NO')

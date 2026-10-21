import hashlib,os,pathlib,subprocess,tarfile,tempfile,unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'deploy/community-preview/deploy.sh'
HOST='community-preview.wenwenwenyiyiyi.work'

class OfflineDeployCandidate(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.root=pathlib.Path(self.tmp.name)
  self.fake=self.root/'fake';self.bin=self.root/'bin';self.bin.mkdir()
  self.state=self.root/'state';self.state.mkdir()
  self.sock=self.root/'preview.sock'
  cert=self.fake/'etc/letsencrypt/live'/HOST;cert.mkdir(parents=True)
  (cert/'fullchain.pem').write_text('cert');(cert/'privkey.pem').write_text('key')
  (self.fake/'proc').mkdir(parents=True)
  pkgroot=self.root/'pkgroot'/'deploy/community-preview';pkgroot.mkdir(parents=True)
  (pkgroot/'nginx.conf').write_text('server_name '+HOST+';\n')
  (pkgroot/'server.py').write_text('print("candidate")\n')
  self.pkg=self.root/'candidate.tar.gz'
  with tarfile.open(self.pkg,'w:gz') as tf:tf.add(self.root/'pkgroot'/'deploy',arcname='deploy')
  self.sha=hashlib.sha256(self.pkg.read_bytes()).hexdigest()
  self._stubs()
 def tearDown(self):self.tmp.cleanup()
 def stub(self,name,body):
  p=self.bin/name;p.write_text('#!/bin/bash\nset -eu\n'+body);p.chmod(0o755);return str(p)
 def _stubs(self):
  self.systemctl=self.stub('systemctl',r"""
S="$FAKE_STATE"; cmd="$1"; shift || true
case "$cmd" in
 is-active) [ -e "$S/active" ];;
 is-enabled) [ -e "$S/enabled" ];;
 show) cat "$S/pid";;
 stop) rm -f "$S/active";;
 start|restart)
   [ "${FAIL_START:-0}" != 1 ] || exit 70
   old=0; [ -f "$S/pid" ] && old="$(cat "$S/pid")"
   if [ "${KEEP_OLD_PID:-0}" = 1 ] && [ "$old" -gt 0 ];then pid="$old";else pid=$((old+1));[ "$pid" -ge 101 ]||pid=101;fi
   echo "$pid" >"$S/pid";: >"$S/active"
   rm -rf "$FAKE_PROC/$pid";mkdir -p "$FAKE_PROC/$pid"
   target="$(readlink -f "$FAKE_CURRENT")"
   [ "${WRONG_CWD:-0}" != 1 ] || target="$FAKE_WRONG_RELEASE"
   ln -s "$target" "$FAKE_PROC/$pid/cwd"
   python - "$FAKE_SOCKET" <<'PY'
import os,socket,sys
p=sys.argv[1]
try: os.unlink(p)
except FileNotFoundError: pass
s=socket.socket(socket.AF_UNIX);s.bind(p);s.close()
PY
   ;;
 daemon-reload) :;;
 reload) [ "${FAIL_RELOAD:-0}" != 1 ];;
 enable) : >"$S/enabled";;
 disable) rm -f "$S/enabled";;
 *) exit 71;;
esac
""")
  self.nginx=self.stub('nginx',r"""
if [ "$1" = "-T" ];then echo "user nginx;";exit 0;fi
if [ "$1" = "-t" ];then [ "${FAIL_NGINX_TEST:-0}" != 1 ];exit;fi
exit 72
""")
  self.curl=self.stub('curl',r"""
case "$*" in *"/community/health"*) echo '{"status":"READY"}';; *) echo 'Synthetic identities/data';; esac
""")
  self.getent=self.stub('getent','exit 0\n')
  self.idbin=self.stub('id',r"""
if [ "$1" = "-u" ];then [ "$#" = 1 ] && echo 0 || echo 1001;exit 0;fi
if [ "$1" = "-gn" ];then echo nginx;exit 0;fi
exit 73
""")
 def base(self):return self.fake/'opt/xuanjun-community-preview'
 def env(self,**extra):
  e=dict(os.environ)
  e.update({
   'COMMUNITY_PREVIEW_TEST_MODE':'1','COMMUNITY_PREVIEW_TEST_ROOT':str(self.fake),
   'COMMUNITY_PREVIEW_RELEASE_SHA':'new-release','COMMUNITY_PREVIEW_PACKAGE':str(self.pkg),
   'COMMUNITY_PREVIEW_PACKAGE_SHA256':self.sha,'COMMUNITY_PREVIEW_SYSTEMCTL':self.systemctl,
   'COMMUNITY_PREVIEW_NGINX':self.nginx,'COMMUNITY_PREVIEW_CURL':self.curl,
   'COMMUNITY_PREVIEW_GETENT':self.getent,'COMMUNITY_PREVIEW_ID':self.idbin,
   'COMMUNITY_PREVIEW_SOCKET_PATH':str(self.sock),'FAKE_STATE':str(self.state),
   'FAKE_PROC':str(self.fake/'proc'),'FAKE_CURRENT':str(self.base()/'current'),
   'FAKE_SOCKET':str(self.sock),'FAKE_WRONG_RELEASE':str(self.root/'wrong-release')})
  e.update({k:str(v) for k,v in extra.items()});return e
 def run(self,**extra):
  return subprocess.run(['bash',str(SCRIPT)],cwd=ROOT,env=self.env(**extra),text=True,capture_output=True,timeout=20)
 def seed_old(self):
  old=self.base()/'releases/old-release';old.mkdir(parents=True)
  (old/'KEEP').write_text('old')
  cur=self.base()/'current';cur.parent.mkdir(parents=True,exist_ok=True);cur.symlink_to(old)
  (self.state/'active').write_text('');(self.state/'enabled').write_text('');(self.state/'pid').write_text('100')
  p=self.fake/'proc/100';p.mkdir(parents=True);(p/'cwd').symlink_to(old)
  return old
 def test_preexisting_release_sentinel_is_not_deleted(self):
  rel=self.base()/'releases/new-release';rel.mkdir(parents=True);sent=rel/'KEEP';sent.write_text('sentinel')
  p=self.run();self.assertEqual(p.returncode,32,p.stdout+p.stderr)
  self.assertEqual(sent.read_text(),'sentinel');self.assertFalse((self.base()/'transactions/new-release').exists())
 def test_first_start_commits_only_running_new_release(self):
  p=self.run();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  rel=self.base()/'releases/new-release';pid=(self.state/'pid').read_text().strip()
  self.assertEqual((self.fake/'proc'/pid/'cwd').resolve(),rel.resolve())
  self.assertEqual((self.base()/'transactions/new-release/COMMITTED').read_text().strip(),'new-release')
 def test_active_upgrade_restarts_and_binds_new_pid(self):
  old=self.seed_old();p=self.run();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
  self.assertNotEqual((self.state/'pid').read_text().strip(),'100')
  self.assertEqual((self.base()/'current').resolve(),(self.base()/'releases/new-release').resolve())
  self.assertTrue((old/'KEEP').exists())
 def test_old_pid_and_ready_output_cannot_commit(self):
  old=self.seed_old();p=self.run(KEEP_OLD_PID=1)
  self.assertNotEqual(p.returncode,0);self.assertFalse((self.base()/'transactions/new-release/COMMITTED').exists())
  self.assertEqual((self.base()/'current').resolve(),old.resolve())
 def test_wrong_running_version_cwd_cannot_commit(self):
  old=self.seed_old();(self.root/'wrong-release').mkdir();p=self.run(WRONG_CWD=1)
  self.assertNotEqual(p.returncode,0);self.assertFalse((self.base()/'transactions/new-release/COMMITTED').exists())
  self.assertEqual((self.base()/'current').resolve(),old.resolve())
 def test_start_failure_restores_old_and_removes_only_owned_release(self):
  old=self.seed_old();p=self.run(FAIL_START=1)
  self.assertNotEqual(p.returncode,0);self.assertEqual((self.base()/'current').resolve(),old.resolve())
  self.assertFalse((self.base()/'releases/new-release').exists());self.assertTrue((old/'KEEP').exists())
 def test_rollback_failure_records_hold(self):
  self.seed_old();p=self.run(FAIL_START=1,FAIL_RELOAD=1)
  tx=self.base()/'transactions/new-release'
  self.assertEqual(p.returncode,91,p.stdout+p.stderr);self.assertTrue((tx/'HOLD').exists())
  self.assertFalse((tx/'ROLLED_BACK').exists());self.assertFalse((tx/'COMMITTED').exists())

if __name__=='__main__':unittest.main()

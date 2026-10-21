"""Protected file -> original objects, with synthetic identities/persistent stores.

No host execution, real credentials, provider calls or customer data.
"""
import copy,json,os,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import test_community_mini_host_config as existing
from scripts.community_mini_host_config import load_protected,stores
from scripts.community_mini_application import MiniApplication
from scripts.community_mini_login import LoginUnavailable


class ProtectedFileComposition(unittest.TestCase):
    def setUp(self):
        self.host=existing.ExistingPersistentHost()
        self.host.setUp()
        self.addCleanup(self.host.doCleanups)
        self.path=Path(self.host.tmp.name)/'host-config.json'
        self.write(self.host.config)

    def write(self,config):
        self.path.write_text(json.dumps(config))
        self.path.chmod(0o600)

    def compose(self,path=None):
        return MiniApplication.from_existing_config_file(
            self.host.fx.center,self.host.runtime,self.host.principals,
            self.path if path is None else path,'a'*32)

    def test_uses_existing_eight_connections_without_opening_or_creating_state(self):
        before=dict(stores(self.host.fx.center,self.host.runtime))
        files=set(Path(self.host.tmp.name).rglob('*'))
        accounts=self.host.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
        with (patch('sqlite3.connect',side_effect=AssertionError('NO_NEW_DATABASE')),
              patch('scripts.community_mini_application.LocalStage',side_effect=AssertionError('NO_NEW_STAGE'))):
            with self.compose() as app:
                self.assertIs(app.identity.center,self.host.fx.center)
                self.assertIs(app.identity.runtime,self.host.runtime)
                self.assertEqual(app.https_origin,self.host.config['https_origin'])
                self.assertIsNone(app.server)
        self.assertEqual(files,set(Path(self.host.tmp.name).rglob('*')))
        for key,db in before.items():
            self.assertIs(db,stores(self.host.fx.center,self.host.runtime)[key])
            db.execute('SELECT 1')
        self.assertEqual(accounts,self.host.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0])

    def test_original_login_unbound_refusal_and_revocation_remain_in_force(self):
        with self.compose() as app:
            app.gateway.provider.exchange=Mock(return_value=dict(appid=self.host.config['appid'],openid='openid1'))
            token=app.gateway.login({'code':'config_file_login'})['session_token']
            self.assertEqual(self.host.fx.center.session(token),self.host.fx.uid1)
            with self.assertRaises(PermissionError):
                app.gateway.dispatch(token,dict(scene='other_shop',operation='community.storefront',params={}))
            before=self.host.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0]
            app.gateway.provider.exchange.return_value=dict(appid=self.host.config['appid'],openid='unknown_identity')
            with self.assertRaises(LoginUnavailable):app.gateway.login({'code':'unbound_config_file_login'})
            self.assertEqual(before,self.host.fx.center.db.execute('SELECT count(*) FROM accounts').fetchone()[0])
            self.host.fx.center.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
            with self.assertRaises(PermissionError):
                app.gateway.dispatch(token,dict(scene='shop1',operation='community.storefront',params={}))

    def test_missing_relative_and_traversal_config_do_not_create_files(self):
        before=set(Path(self.host.tmp.name).rglob('*'))
        for path in (self.path.parent/'missing.json','relative.json',str(self.path.parent/'..'/'host-config.json')):
            with self.subTest(path=str(path)),self.assertRaises((ValueError,PermissionError)):
                self.compose(path)
        self.assertEqual(before,set(Path(self.host.tmp.name).rglob('*')))

    def test_duplicate_nonfinite_invalid_utf8_and_oversize_are_refused(self):
        for raw in (b'{"version":1,"version":1}',b'{"value":NaN}',b'\xff',b' ',b'x'*65537):
            self.path.write_bytes(raw)
            with self.subTest(size=len(raw)),self.assertRaises(ValueError):load_protected(self.path)

    def test_links_fifo_and_nonprivate_permissions_are_refused_without_reading(self):
        for mode in ('symlink','hardlink','fifo','public_file','public_parent'):
            self.write(self.host.config)
            target=self.path
            extra=self.path.parent/'alternate.json'
            if mode=='symlink':extra.symlink_to(self.path);target=extra
            elif mode=='hardlink':os.link(self.path,extra)
            elif mode=='fifo':self.path.unlink();os.mkfifo(self.path,0o600)
            elif mode=='public_file':self.path.chmod(0o644)
            else:self.path.parent.chmod(0o755)
            try:
                with (self.subTest(mode=mode),patch('scripts.community_mini_host_config.os.read',side_effect=AssertionError('NO_CONTENT_READ')),
                      self.assertRaises(PermissionError)):load_protected(target)
            finally:
                self.path.parent.chmod(0o700)
                if extra.exists() or extra.is_symlink():extra.unlink()
                self.path.unlink()
                self.write(self.host.config)

    def test_parent_symlink_and_read_race_are_refused(self):
        alias=self.path.parent/'linked-parent';alias.symlink_to(self.path.parent,target_is_directory=True)
        with self.assertRaises(PermissionError):load_protected(alias/self.path.name)
        original_read=os.read
        def changed(fd,size):
            raw=original_read(fd,size)
            with self.path.open('ab') as f:f.write(b' ')
            return raw
        with patch('scripts.community_mini_host_config.os.read',side_effect=changed),self.assertRaisesRegex(ValueError,'CHANGED_DURING_READ'):
            load_protected(self.path)

    def test_invalid_bindings_stop_before_provider_construction(self):
        for mode in ('store','scene','secret','revoked_project'):
            config=copy.deepcopy(self.host.config)
            if mode=='store':config['stores']['orders']=config['stores']['merchants']
            elif mode=='scene':config['scenes']['shop1']['principal']='unknown'
            elif mode=='secret':config['app_secret']='must_not_be_a_config_field'
            else:self.host.fx.center.db.execute("UPDATE projects SET active=0 WHERE id='project1'")
            self.write(config)
            with (self.subTest(mode=mode),patch('scripts.community_mini_application.WechatCodeClient',side_effect=AssertionError('PROVIDER_NOT_REACHED')),
                  self.assertRaises((ValueError,PermissionError))):self.compose()


if __name__=='__main__':unittest.main()

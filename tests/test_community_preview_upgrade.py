"""Bounded upgrade state-machine tests; no host commands, identities or secrets."""
import copy
import hashlib
import re
import io
import subprocess
import unittest
from pathlib import Path
from contextlib import ExitStack,redirect_stdout
from unittest.mock import patch,Mock
from scripts import community_preview_upgrade as u

NEW_ID='a'*64

def info(image=u.OLD_IMAGE,cid=u.OLD_ID,running=True):
    return {'id':cid,'image':image,'running':running,'status':'running' if running else 'exited',
        'user':'10001:1008','cpu':500000000,'memory':536870912,'swap':536870912,'pids':64,
        'readonly':True,'privileged':False,'restart':'no','capdrop':['ALL'],'network':'default',
        'security':['no-new-privileges'],'entrypoint':['python','-B','-m','scripts.community_platform_host'],
        'cmd':['--plan',u.ROOT+'/config/host.json','--center-keys',u.ROOT+'/config/center-keys.json','--wechat-secret',u.ROOT+'/config/wechat.json'],
        'tmpfs':{'/tmp':'rw,noexec,nosuid,nodev,size=16777216,mode=1777'},
        'log':{'Type':'json-file','Config':{'max-size':'10m','max-file':'2'}},
        'mounts':[{'Type':'bind','Source':p,'Destination':p,'RW':rw} for p,rw in [(u.ROOT+'/config',False),(u.ROOT+'/data',True),(u.RUN,True)]]}

def legacy_onboarding_asset(filename="community_preview_2330_onboarding.html"):
    """Rebuild immutable 2330 role-page bytes; never compare its pin to current onboarding."""
    raw=(Path(__file__).parent/'fixtures'/filename).read_text()
    prefix='/community-preview'
    raw=re.sub(r"""((?:href|src)=[\"'])(/(?:merchant|community)/[^\"']+)""",lambda m:m[1]+prefix+m[2],raw)
    pages={
        '/merchant/workbench':('workbench.html','商家工作台'),
        '/community/portal':('communities.html','社区管理'),
        '/merchant/review':('onboarding.html','平台入驻审核'),
        '/merchant/join':('onboarding.html','商家入驻'),
    }
    nav='<nav aria-label="角色入口">'+''.join('<a href="'+prefix+p+'">'+title+'</a> ' for p,(_,title) in pages.items())+'</nav>'
    panel='<section id="community-session" aria-label="原平台登录"><p>工作人员使用本社区原账户登录；普通用户继续使用小程序微信登录，无需邮箱。</p><form><label>原账户邮箱<input name="email" type="email" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><button type="submit">登录</button></form><label>已授权工作区<select aria-label="已授权工作区"></select></label><button type="button" data-logout>退出登录</button><p role="status">请登录本社区原账户。</p></section>'
    raw=raw.replace('<body>','<body>'+nav+panel,1)
    raw=raw.replace('</body>','<script src="'+prefix+'/community/web-session.js" defer></script></body>',1)
    return raw.encode()


def legacy_session_asset():
    """Pinned original session transport, not the current role/finance projection."""
    raw=(Path(__file__).parent/'fixtures/community_preview_2330_web-session.js').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='021e4e78e275d71a350b0e010e6544ac61e458c70060c458a021b0c553e2261f':
        raise AssertionError('FROZEN_ORIGINAL_SESSION_BYTES_CHANGED')
    return re.sub(r"([\"'])(/(?:merchant|community)/[A-Za-z0-9_./-]+)\1",lambda m:m[1]+'/community-preview'+m[2]+m[1],raw.decode()).encode()


class UpgradeBoundary(unittest.TestCase):
    def test_fixed_source_fragment_image_and_original_role_assets(self):
        # Frozen 2330 installer and intermediate admin-shell projection remain pinned.
        # Current successor additionally permits only the reviewed fixed WeChat session path.
        current=(Path(__file__).resolve().parents[1]/'deploy/community-preview/nginx-uk-path-candidate.conf').read_bytes()
        self.assertEqual(hashlib.sha256(u.FRAGMENT).hexdigest(),'df55f5f11413c623d3f9d966b6feacf54fda25ecfe42ee11d70052d544f2ca83')
        admin_projection=u.FRAGMENT.replace(b'|web-session',b'|admin-shell\\.(css|js)|web-session',1)
        self.assertEqual(hashlib.sha256(admin_projection).hexdigest(),'82e81b56e2adeb1519ff34a981e0f5a8037923df59718192ee5eafe2d03f11a9')
        self.assertEqual(admin_projection.count(b'session/(login|check|logout)'),1)
        self.assertEqual(current,admin_projection.replace(b'session/(login|check|logout)',
                                                        b'session/(login|check|logout|wechat)',1))
        self.assertEqual(hashlib.sha256(current).hexdigest(),'a5ccafb9421929a1e5076b41af7a3c08542458aeec24274587dffee4bd6eca9d')
        self.assertEqual(set(u.ASSET_HASHES),{'/merchant/workbench','/merchant/review','/merchant/join','/community/portal','/community/web-session.js'})
        for path,digest in u.ASSET_HASHES.items():
            raw=(legacy_onboarding_asset() if path in ('/merchant/review','/merchant/join') else
                 legacy_onboarding_asset('community_preview_2330_communities.html') if path=='/community/portal' else
                 legacy_onboarding_asset('community_preview_2330_workbench.html') if path=='/merchant/workbench' else
                 legacy_session_asset())
            self.assertEqual(digest,hashlib.sha256(raw).hexdigest(),path)
        self.assertEqual(u.SOURCE,'2330dd55c07f58d7f45a7c4510a9761d0d4735d6')
    def test_only_existing_bounded_container_and_mounts_are_admitted(self):
        u.validate(info(),u.OLD_IMAGE,u.OLD_ID)
        for field,value in [('id','b'*64),('image',u.IMAGE),('cpu',0),('memory',0),('swap',-1),('pids',-1),('user','0'),('readonly',False),('privileged',True),('restart','always'),('network','host'),('security',[]),('capdrop',[]),('tmpfs',{}),('log',{}),('cmd',[])]:
            candidate=info();candidate[field]=value
            with self.subTest(field=field),self.assertRaises(u.Rejected):u.validate(candidate,u.OLD_IMAGE,u.OLD_ID)
        for mutation in ('writable_config','extra','redirect_data'):
            candidate=info()
            if mutation=='writable_config':candidate['mounts'][0]['RW']=True
            elif mutation=='extra':candidate['mounts'].append({'Type':'bind','Source':'/','Destination':'/host','RW':False})
            else:candidate['mounts'][1]['Source']='/other-project'
            with self.subTest(mutation=mutation),self.assertRaises(u.Rejected):u.validate(candidate,u.OLD_IMAGE,u.OLD_ID)
    def test_resource_parameters_no_pull_no_secrets_no_first_install(self):
        args=u.run_args();self.assertEqual(args[args.index('--pull')+1],'never')
        self.assertEqual(args[args.index('--cpus')+1],'0.5')
        self.assertEqual(args[args.index('--memory')+1],'512m')
        self.assertEqual(args[args.index('--pids-limit')+1],'64')
        self.assertNotIn('--privileged',args);self.assertNotIn('--env',args);self.assertNotIn('--publish',args)
        self.assertNotIn('scripts.community_first_install',args)
        self.assertEqual(args[args.index('--name')+1],u.NAME)
    def test_transport_and_bytes_fail_before_docker_or_file_write(self):
        with patch.object(u,'command') as command,patch.object(u,'create') as create:
            for url in ['http://sdmntprwestus.oaiusercontent.com/a','https://evil.invalid/a','https://user@sdmntprwestus.oaiusercontent.com/a','https://sdmntprwestus.oaiusercontent.com:444/a']:
                with self.subTest(url=url),self.assertRaises(u.Rejected):u.load_artifact(url)
            with self.assertRaises(u.Rejected):u.archive_from_zip(b'corrupt')
            command.assert_not_called();create.assert_not_called()
    def test_mutating_rejection_or_timeout_is_unknown_never_automatic_retry(self):
        with patch.object(u,'command',side_effect=u.Rejected('FAIL')) as command,redirect_stdout(io.StringIO()):
            with self.assertRaises(u.Unknown):u.mutate(u.DOCKER+['run','anything'])
            self.assertEqual(command.call_count,1)
        with patch.object(u.subprocess,'run',side_effect=subprocess.TimeoutExpired(['docker'],1)) as run:
            with self.assertRaises(u.Unknown):u.command(u.DOCKER+['start',u.OLD_ID])
            self.assertEqual(run.call_count,1)

class UpgradeState(unittest.TestCase):
    def fixture(self):
        stack=ExitStack();self.addCleanup(stack.close)
        self.calls=[];self.files=[]
        old=b'original own include';vhost=b'server { include /etc/nginx/community-preview.inc; }'
        for target,value in [('os.getuid',0),('os.geteuid',0)]:stack.enter_context(patch('scripts.community_preview_upgrade.'+target,return_value=value))
        stack.enter_context(patch.object(u.os,'uname',return_value=Mock(nodename=u.HOST)))
        for name in ('secure_directory','load_artifact','await_private_ready'):
            stack.enter_context(patch.object(u,name))
        stack.enter_context(patch.object(u,'private_ready',return_value=True))
        stack.enter_context(patch.object(u,'OLD_FRAGMENT_SHA',hashlib.sha256(old).hexdigest()))
        stack.enter_context(patch.object(u.os.path,'lexists',return_value=False))
        stack.enter_context(patch.object(u.os,'mkdir'))
        stack.enter_context(patch.object(u.signal,'signal'));stack.enter_context(patch.object(u.signal,'alarm'))
        stack.enter_context(patch.object(u,'read_root_file',side_effect=lambda path:(vhost if path==u.VHOST else old,0o600)))
        self.replace=stack.enter_context(patch.object(u,'replace_include'))
        self.create=stack.enter_context(patch.object(u,'create',side_effect=lambda p,b:self.files.append(p)))
        self.public=stack.enter_context(patch.object(u,'public_ready'))
        self.rollback=stack.enter_context(patch.object(u,'rollback'))
        self.inspect=stack.enter_context(patch.object(u,'inspect',side_effect=[info(),info(),info(running=False),info(u.IMAGE,NEW_ID)]))
        def command(args,timeout=8):
            self.calls.append(args)
            if args[3:5]==['container','ls']:return u.NAME+'\n'
            return ''
        self.command=stack.enter_context(patch.object(u,'command',side_effect=command))
        def mutate(args,timeout=8):
            self.calls.append(args)
            return NEW_ID if args[3:4]==['run'] else ''
        self.mutate=stack.enter_context(patch.object(u,'mutate',side_effect=mutate))
        stack.enter_context(redirect_stdout(io.StringIO()))
        return old,vhost
    def test_success_stops_old_before_new_and_preserves_data_config_owner_file(self):
        self.fixture();u.main('fixed transport fixture')
        verbs=[args[3] for args in self.calls if args[:3]==u.DOCKER]
        self.assertEqual(verbs,['container','stop','rename','run'])
        self.assertIn(u.STAGE+'/receipt.json',self.files)
        self.assertFalse(any(p.startswith(u.ROOT) for p in self.files))
        self.assertTrue(all(call.args[0] != u.VHOST for call in self.create.call_args_list))
        self.rollback.assert_not_called()
    def test_known_public_failure_rolls_back_only_known_new_receipt(self):
        old,vhost=self.fixture();self.public.side_effect=u.Rejected('PUBLIC_MISMATCH')
        with self.assertRaisesRegex(u.Rejected,'KNOWN_FAILURE_ROLLED_BACK'):u.main('fixture')
        self.rollback.assert_called_once_with(NEW_ID,old,0o600,hashlib.sha256(vhost).hexdigest())
        self.assertNotIn(u.STAGE+'/receipt.json',self.files)
    def test_unknown_run_result_never_starts_old_or_replays_new(self):
        self.fixture()
        original=self.mutate.side_effect
        def mutation(args,timeout=8):
            if args[3:4]==['run']:raise u.Unknown('RUN_TIMEOUT')
            return original(args,timeout)
        self.mutate.side_effect=mutation
        with self.assertRaises(u.Unknown):u.main('fixture')
        self.rollback.assert_not_called()
        self.assertEqual(sum(c.args[0][3:4]==['run'] for c in self.mutate.call_args_list),1)
        self.assertFalse(any(args[3:4]==['start'] for args in self.calls))
    def test_unknown_public_network_preserves_new_state_for_inspection(self):
        self.fixture();self.public.side_effect=u.Unknown('PUBLIC_NETWORK')
        with self.assertRaises(u.Unknown):u.main('fixture')
        self.rollback.assert_not_called()
        self.assertNotIn(u.STAGE+'/receipt.json',self.files)
    def test_failed_nginx_candidate_restores_own_include_before_stopping_old(self):
        old,_=self.fixture();original=self.command.side_effect;count=[0]
        def cmd(args,timeout=8):
            if args==['/usr/sbin/nginx','-t']:
                count[0]+=1
                if count[0]==2:raise u.Rejected('SYNTAX')
            return original(args,timeout)
        self.command.side_effect=cmd
        with self.assertRaisesRegex(u.Rejected,'CANDIDATE_INVALID'):u.main('fixture')
        self.assertEqual(self.replace.call_args_list[-1].args,(u.FRAGMENT,old,0o600))
        self.mutate.assert_not_called();self.rollback.assert_not_called()
    def test_concurrent_owner_change_holds_before_stop(self):
        _,vhost=self.fixture();count=[0]
        def read(path):
            if path==u.VHOST:
                count[0]+=1;return (vhost if count[0]==1 else vhost+b'changed'),0o600
            return b'original own include',0o600
        with patch.object(u,'read_root_file',side_effect=read),self.assertRaises(u.Unknown):u.main('fixture')
        self.mutate.assert_not_called();self.rollback.assert_not_called()

class RollbackBoundary(unittest.TestCase):
    def test_unknown_new_stop_cannot_start_old_writer(self):
        with patch.object(u,'inspect',return_value=info(u.IMAGE,NEW_ID)),patch.object(u,'mutate',side_effect=u.Unknown('STOP_TIMEOUT')) as mutate:
            with self.assertRaises(u.Unknown):u.rollback(NEW_ID,b'old',0o600,'hash')
            self.assertEqual(mutate.call_count,1)
            self.assertEqual(mutate.call_args.args[0][3],'stop')
    def test_lingering_socket_blocks_old_writer_after_new_exit(self):
        stopped=info(u.IMAGE,NEW_ID,running=False)
        with patch.object(u,'inspect',return_value=stopped),patch.object(u.os.path,'lexists',return_value=True),patch.object(u,'mutate') as mutate:
            with self.assertRaisesRegex(u.Unknown,'SOCKET_REMAINS'):u.rollback(NEW_ID,b'old',0o600,'hash')
            mutate.assert_not_called()

class PublicReloadReadiness(unittest.TestCase):
    def test_transition_rechecks_whole_contract_then_succeeds(self):
        with patch.object(u,'public_ready_once',side_effect=[u.PublicPending('PUBLIC_HTTP_404'),None]) as probe,patch.object(u.time,'sleep') as sleep,redirect_stdout(io.StringIO()):
            u.public_ready()
            self.assertEqual(probe.call_count,2);sleep.assert_called_once_with(1)
    def test_transition_is_bounded_and_still_fails(self):
        with patch.object(u,'public_ready_once',side_effect=u.PublicPending('PUBLIC_HTTP_404')) as probe,patch.object(u.time,'sleep'),redirect_stdout(io.StringIO()):
            with self.assertRaises(u.PublicPending):u.public_ready()
            self.assertEqual(probe.call_count,4)
    def test_hash_mismatch_or_unknown_never_retried(self):
        for error in (u.Rejected('PUBLIC_ASSET_HASH'),u.Unknown('PUBLIC_NETWORK_INSPECT_ONLY')):
            with self.subTest(error=type(error).__name__),patch.object(u,'public_ready_once',side_effect=error) as probe,patch.object(u.time,'sleep') as sleep:
                with self.assertRaises(type(error)):u.public_ready()
                self.assertEqual(probe.call_count,1);sleep.assert_not_called()
    def test_http_status_classification_and_path_evidence(self):
        from urllib.error import HTTPError
        for status,pending in ((404,True),(502,True),(503,True),(403,False),(301,False)):
            error=HTTPError('https://example.invalid/',status,'status',{},io.BytesIO())
            opener=Mock();opener.open.side_effect=error
            output=io.StringIO()
            with self.subTest(status=status),patch.object(u,'build_opener',return_value=opener),redirect_stdout(output):
                with self.assertRaises(u.PublicPending if pending else u.Rejected):u.public_ready_once()
                self.assertIn('/merchant/workbench',output.getvalue())
                self.assertIn(str(status),output.getvalue())
                self.assertEqual(opener.open.call_count,1)

class PublicRealHTTP(unittest.TestCase):
    def test_real_http_404_then_exact_assets_and_catalog(self):
        from scripts.community_web_entries import asset
        import json,threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        from urllib.request import urlopen
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                requests.append(self.path)
                if len(requests)==1:
                    self.send_response(404);self.end_headers();return
                path=self.path[len('/community-preview'):]
                if path in u.ASSET_HASHES:body=asset(path)[0]
                elif path.endswith('health'):body=json.dumps({'status':'READY','production_acceptance':False}).encode()
                else:body=json.dumps({'source_sha':u.SOURCE,'project_ids':['community_platform'],'production_acceptance':False}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        class LocalTransport:
            def open(self,url,timeout):
                self.assert_origin(url)
                return urlopen('http://127.0.0.1:'+str(server.server_port)+url.split('.work',1)[1],timeout=timeout)
            @staticmethod
            def assert_origin(url):
                if not url.startswith('https://uk.wenwenwenyiyiyi.work/community-preview/'):raise AssertionError(url)
        try:
            current_hashes={path:hashlib.sha256(asset(path)[0]).hexdigest() for path in u.ASSET_HASHES}
            with patch.object(u,'ASSET_HASHES',current_hashes),patch.object(u,'build_opener',return_value=LocalTransport()),patch.object(u.time,'sleep'),redirect_stdout(io.StringIO()):u.public_ready()
            self.assertEqual(len(requests),8)
            self.assertEqual(requests[:2],['/community-preview/merchant/workbench']*2)
            self.assertEqual(set(requests[1:]),{'/community-preview'+p for p in list(u.ASSET_HASHES)+['/community/health','/community/entrypoints']})
        finally:server.shutdown();server.server_close();thread.join(2)

class ResumeRolledBack(unittest.TestCase):
    def fixture(self):
        old,vhost=UpgradeState.fixture(self)
        attempt={'source_sha':u.SOURCE,'old_id':u.OLD_ID,'new_image':u.IMAGE,
                 'owner_vhost_sha256':hashlib.sha256(vhost).hexdigest(),'phase':'PREPARED'}
        def read(path):
            if path.endswith('/attempt.json'):return __import__('json').dumps(attempt).encode(),0o600
            if path.endswith('/new-container-id.txt'):return (u.RESUME_ID+'\n').encode(),0o600
            return (vhost if path==u.VHOST else old),0o600
        u.read_root_file.side_effect=read
        self.inspect.side_effect=[info(),info(u.IMAGE,u.RESUME_ID,False),info(),info(u.IMAGE,u.RESUME_ID,False),info(running=False),info(u.IMAGE,u.RESUME_ID)]
        return old,vhost
    def test_resume_reuses_exact_stopped_container_no_download_run_or_init(self):
        self.fixture();u.resume_rolled_back()
        verbs=[args[3] for args in self.calls if args[:3]==u.DOCKER]
        self.assertEqual(verbs,['container','stop','rename','rename','start'])
        u.load_artifact.assert_not_called()
        self.assertIn(u.STAGE+'/resume-01/receipt.json',self.files)
        self.rollback.assert_not_called()
    def test_resume_public_failure_preserves_reason_and_rolls_back(self):
        self.fixture();self.public.side_effect=u.Rejected('PUBLIC_ASSET_HASH')
        with self.assertRaisesRegex(u.Rejected,'KNOWN_FAILURE_ROLLED_BACK'):u.resume_rolled_back()
        self.assertIn(u.STAGE+'/resume-01/failure.json',self.files)
        self.rollback.assert_called_once()
    def test_resume_unknown_never_rollback_or_replay(self):
        self.fixture();self.public.side_effect=u.Unknown('PUBLIC_NETWORK')
        with self.assertRaises(u.Unknown):u.resume_rolled_back()
        self.rollback.assert_not_called()
        self.assertEqual(sum(args[3:4]==['start'] for args in self.calls),1)
    def test_existing_resume_or_different_container_blocks_all_mutations(self):
        self.fixture()
        with patch.object(u.os.path,'lexists',return_value=True),self.assertRaisesRegex(u.Rejected,'EXISTING_RESUME'):u.resume_rolled_back()
        self.mutate.assert_not_called();self.replace.assert_not_called()
    def test_old_health_false_blocks_before_any_write(self):
        self.fixture();u.private_ready.return_value=False
        with self.assertRaisesRegex(u.Rejected,'ORIGINAL_BACKEND_NOT_READY'):u.resume_rolled_back()
        self.create.assert_not_called();self.mutate.assert_not_called()
    def test_wrong_failed_id_blocks_before_any_write(self):
        self.fixture();self.inspect.side_effect=[info(),info(u.IMAGE,'b'*64,False)]
        with self.assertRaisesRegex(u.Rejected,'EXACT_CONTAINER_STATE'):u.resume_rolled_back()
        self.create.assert_not_called();self.mutate.assert_not_called()

if __name__=='__main__':unittest.main()

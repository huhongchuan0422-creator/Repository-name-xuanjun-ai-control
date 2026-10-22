"""Bounded upgrade state-machine tests; no host commands, identities or secrets."""
import copy
import hashlib
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

class UpgradeBoundary(unittest.TestCase):
    def test_fixed_source_fragment_image_and_original_role_assets(self):
        self.assertEqual(u.FRAGMENT,(Path(__file__).resolve().parents[1]/'deploy/community-preview/nginx-uk-path-candidate.conf').read_bytes())
        from scripts.community_web_entries import asset
        self.assertEqual(set(u.ASSET_HASHES),{'/merchant/workbench','/merchant/review','/merchant/join','/community/portal','/community/web-session.js'})
        for path,digest in u.ASSET_HASHES.items():self.assertEqual(digest,hashlib.sha256(asset(path)[0]).hexdigest())
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

if __name__=='__main__':unittest.main()

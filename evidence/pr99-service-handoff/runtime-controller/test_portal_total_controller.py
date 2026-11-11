"""Local fixtures only. Never execute real systemctl, SSH, firewall or ioctl."""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tarfile

import portal_total_controller as m


class Tests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='pr99-offline-fixture-',dir='/root')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        image=self.file('controller.py',Path(m.__file__).read_bytes())
        image_patch=patch.object(m,'__file__',str(image))
        image_patch.start();self.addCleanup(image_patch.stop)

    def file(self,name,raw=b''):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        m.create(path,raw)
        return path

    def test_explicit_file_mode_survives_private_umask(self):
        import os,stat
        old=os.umask(0o077)
        try:
            path=self.root/'sudoers-fixture'
            m.create(path,b'fixture',0o440)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o440)
        finally:os.umask(old)

    def test_nginx_empty_quoted_header_is_a_valid_token(self):
        self.assertEqual(m.nginx_tokens('proxy_set_header Connection "";'),
            [('word','proxy_set_header'),('word','Connection'),('word',''),('punct',';')])

    def test_route_exact_must_use_existing_owned_include(self):
        text='server { location = /'+m.VERIFY_NAME+' { include '+str(m.ROUTE)+'; } }'
        self.assertEqual(m.route_probe_path(text),'/'+m.VERIFY_NAME)

    def test_static_verification_route_not_mistaken_for_proxy(self):
        text='server { location = /'+m.VERIFY_NAME+' { root /site; } }'
        with self.assertRaisesRegex(m.Hold,'NO_VERIFIABLE'):
            m.route_probe_path(text)

    def test_prefix_route_and_quoted_braces(self):
        text='log_format test "{"; # } ignored\nserver { location ^~ /api/ { include '+str(m.ROUTE)+'; } }'
        self.assertTrue(m.route_probe_path(text).startswith('/api/__pr99_nonexistent_'))

    def test_unsafe_route_rewrite_excluded(self):
        text='location /api/ { rewrite ^ /else; include '+str(m.ROUTE)+'; }'
        with self.assertRaises(m.Hold): m.route_probe_path(text)

    def test_regex_route_not_used_as_literal(self):
        text='location ~ "^/x/{1,4}" { include '+str(m.ROUTE)+'; }'
        with self.assertRaises(m.Hold): m.route_probe_path(text)

    def test_relative_nginx_include_resolves_to_existing_config(self):
        text='location /api/ { include pr122-minimal-cutover/tokyo-proxy-settings.conf; }'
        self.assertTrue(m.route_probe_path(text).startswith('/api/'))

    def test_checkpoint_consumes_unknown_without_replay(self):
        journal=m.Checkpoint(self.root)
        calls=[]
        def fail(): calls.append(1);raise m.Unknown('TEST_TIMEOUT')
        with self.assertRaises(m.Unknown): journal.perform('start',fail,'fixture')
        with self.assertRaisesRegex(m.Hold,'QUERY_ONLY'): journal.perform('start',fail,'fixture')
        self.assertEqual(calls,[1])
        self.assertEqual(journal.summary()['start']['status'],'UNKNOWN_PRESERVED')

    def test_checkpoint_keeps_success_and_exact_binding(self):
        journal=m.Checkpoint(self.root)
        journal.perform('transfer',lambda:{'sha256':'fixture'},'fixture-package')
        value=journal.summary()['transfer']
        self.assertEqual(value['result']['binding'],'fixture-package')
        self.assertEqual(value['status'],'PASS')

    def test_root_reader_refuses_symlink(self):
        good=self.file('safe',b'fixture')
        link=self.root/'link';link.symlink_to(good)
        with self.assertRaises(m.Hold):m.root_read(link)

    def test_stop_propagation_to_binance_denied(self):
        state={'RequiredBy':'binance.service','BoundBy':'','ConsistsOf':''}
        with self.assertRaisesRegex(m.Hold,'OUTSIDE_SCOPE'):m.stop_edges(state,m.RETIRED)

    def test_snapshot_real_sqlite_backup_and_tar_hashes(self):
        base=self.root/'app';base.mkdir(mode=0o700)
        database=base/'database/data/trading.db';database.parent.mkdir(parents=True,mode=0o700)
        con=sqlite3.connect(database)
        con.execute('CREATE TABLE credential_records(credential_id TEXT)')
        con.executemany('INSERT INTO credential_records VALUES (?)',[(str(i),) for i in range(3)])
        con.commit();con.close()
        keys=self.root/'keys';keys.mkdir(mode=0o700)
        for name in m.KEYS:
            raw=m.encode({'bindings':{str(i):{} for i in range(3)}}) if name=='credential-bindings.json' else b'SYNTHETIC_KEY_ONLY=fixture\n'
            m.create(keys/name,raw)
        for prefix in m.PREFIXES:
            folder=base/prefix;folder.mkdir(parents=True,mode=0o700)
            m.create(folder/'state.json',b'{"synthetic":true}')
        job=self.root/'job';job.mkdir(mode=0o700)
        m.create(job/'source-fence.json',m.encode({'objects':[],'class':'TEST_FIXTURE_NOT_LIVE_PROOF'}))
        with patch.object(m,'BASE',base),patch.object(m,'KEY_ROOT',keys),patch.object(m,'SOURCE_JOB',job),patch.object(m,'check_source_fence'):
            result=m.source_package('fixture-job')
        raw=(job/'migration-data.tar.gz').read_bytes()
        self.assertEqual(m.sha(raw),result['sha256'])
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            manifest=json.load(archive.extractfile('manifest.json'))
            for name,expected in manifest['files'].items():
                self.assertEqual(m.sha(archive.extractfile(name).read()),expected)
        copy=sqlite3.connect(job/'database.sqlite')
        self.assertEqual(copy.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(copy.execute('SELECT COUNT(*) FROM credential_records').fetchone()[0],3)
        copy.close()

    def pipeline(self,fail_operation=None):
        job=self.root/'job';lock=self.file('lock')
        calls=[]
        def remote(operation,identifier,package_sha=None):
            calls.append(operation)
            if operation==fail_operation:raise m.Unknown('FIXTURE_LOST_RESPONSE')
            if operation=='capabilities':return {'fixture':True}
            if operation=='preflight':return {'source_files':{}}
            if operation=='query':return {'service':{'ActiveState':'inactive','MainPID':'0'}}
            return {'fixture_operation':operation}
        def fence(*args):
            m.create(job/'source-fence.json',m.encode({'objects':[],'class':'TEST_FIXTURE_NOT_LIVE_PROOF'}))
            return {'fixture':True}
        patches=[patch.object(m,'SOURCE_JOB',job),patch.object(m,'SOURCE_LOCK',lock),
                 patch.object(m,'host'),patch.object(m,'remote_action',side_effect=remote),
                 patch.object(m,'source_preflight',return_value={'pid':123}),
                 patch.object(m,'seal_source',return_value={'fixture':True}),
                 patch.object(m,'source_stop_and_fence',side_effect=fence),
                 patch.object(m,'source_package',return_value={'sha256':'f'*64,'bytes':10,'files':7}),
                 patch.object(m,'transfer',return_value={'fixture':True}),
                 patch.object(m,'check_source_fence')]
        for item in patches:item.start();self.addCleanup(item.stop)
        return job,calls

    def test_pipeline_orders_all_actual_adapters_under_single_checkpoint(self):
        job,calls=self.pipeline()
        with patch('sys.stdout',new=io.StringIO()):m.source_main()
        self.assertEqual(calls,['capabilities','preflight','prepare','check','start','cutover'])
        result=json.loads((job/'receipt.json').read_text())
        self.assertEqual(result['status'],'PASS_PORTAL_CUTOVER')
        self.assertFalse(result['whole_server_migration_complete'])
        self.assertFalse(result['source_writer_resumed'])

    def test_remote_unknown_stops_before_start_or_cutover(self):
        job,calls=self.pipeline('prepare')
        with patch('sys.stdout',new=io.StringIO()):
            with self.assertRaises(m.Unknown):m.source_main()
        self.assertEqual(calls,['capabilities','preflight','prepare'])
        self.assertTrue((job/'target_prepare.unknown.json').exists())
        self.assertFalse((job/'receipt.json').exists())

    def test_existing_job_is_query_only_no_second_fence(self):
        job,calls=self.pipeline()
        job.mkdir(mode=0o700)
        m.create(job/'job.json',m.encode({'job':'portal-final-'+'a'*32}))
        with patch.object(m,'ctl',return_value={'MainPID':'0','ActiveState':'inactive','LoadState':'masked'}),\
             patch.object(m,'firewall_args',return_value=(['iptables'],['INPUT'])),\
             patch.object(m,'command',return_value=SimpleNamespace(returncode=0)),\
             patch('sys.stdout',new=io.StringIO()):m.source_main()
        self.assertEqual(calls,['query'])
        m.seal_source.assert_not_called()
        m.source_stop_and_fence.assert_not_called()

    def test_failed_source_preflight_creates_no_job_or_gate(self):
        job,calls=self.pipeline()
        m.source_preflight.side_effect=m.Hold('FIXTURE_CLASSIFICATION_REQUIRED')
        with self.assertRaises(m.Hold):m.source_main()
        self.assertFalse(job.exists())
        m.seal_source.assert_not_called()

    def test_target_stage_requires_previous_success_and_same_package(self):
        job=self.root/'target';job.mkdir(mode=0o700)
        job_id='portal-final-'+'a'*32
        m.create(job/'claim.json',m.encode({'job':job_id,'code_sha256':m.sha(m.root_read(Path(m.__file__)))}))
        m.create(job/'preflight.result.json',m.encode({'status':'PASS','binding':None}))
        m.create(job/'prepare.result.json',m.encode({'status':'PASS','binding':'a'*64}))
        with patch.object(m,'TARGET_JOB',job),patch.object(m,'static_target'):
            with self.assertRaisesRegex(m.Hold,'PACKAGE_CHANGED'):
                m.target_context({'operation':'check','job':job_id,'sha256':'b'*64})

    def test_any_prior_target_unknown_blocks_later_effects(self):
        job=self.root/'target';job.mkdir(mode=0o700)
        job_id='portal-final-'+'a'*32
        m.create(job/'claim.json',m.encode({'job':job_id,'code_sha256':m.sha(m.root_read(Path(m.__file__)))}))
        m.create(job/'prepare.unknown.json',b'{}')
        with patch.object(m,'TARGET_JOB',job),patch.object(m,'static_target'):
            with self.assertRaisesRegex(m.Hold,'PRIOR_UNKNOWN'):
                m.target_context({'operation':'start','job':job_id,'sha256':'a'*64})


if __name__=='__main__':unittest.main()

class RoutingFailureTests(unittest.TestCase):
    setUp=Tests.setUp
    file=Tests.file
    def route_fixture(self,fail_test=False,unknown_reload=False):
        job=self.root/'routing-job';job.mkdir(mode=0o700)
        prep=self.root/'prep';prep.mkdir(mode=0o700)
        route=self.file('nginx/route.conf',b'original\n')
        m.create(prep/'original-tokyo-proxy-settings.conf',b'original\n')
        m.create(prep/'candidate-domestic-proxy-settings.conf',b'candidate\n')
        baseline=b'BEGIN\noriginal\nEND\n'
        m.create(job/'nginx-baseline.conf',baseline)
        m.create(job/'start.result.json',b'{}')
        state={'MainPID':'123','ActiveState':'active'}
        calls=[]
        def command(argv,*args,**kwargs):
            calls.append(argv)
            if argv==['/usr/sbin/nginx','-T']:
                return SimpleNamespace(returncode=0,stdout=b'BEGIN\n'+route.read_bytes()+b'END\n',stderr=b'')
            if argv==['/usr/sbin/nginx','-t']:
                return SimpleNamespace(returncode=1 if fail_test else 0,stdout=b'',stderr=b'')
            if 'reload' in argv and unknown_reload: raise m.Unknown('FIXTURE_RELOAD_TIMEOUT')
            if 'stop' in argv: state['MainPID']='0';state['ActiveState']='inactive'
            return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        patches=[patch.object(m,'TARGET_JOB',job),patch.object(m,'PREP',prep),patch.object(m,'ROUTE',route),
                 patch.object(m,'verify_protected',return_value={'route_probe':'/api/__fixture'}),
                 patch.object(m,'incoming'),patch.object(m,'portal_http',return_value=True),
                 patch.object(m,'ctl',side_effect=lambda unit:dict(state)),patch.object(m,'static_target'),
                 patch.object(m,'command',side_effect=command),
                 patch.object(m,'backend_probe',return_value={'status':404,'body_sha256':'a'*64}),
                 patch.object(m,'https_probe',return_value={'status':502,'body_sha256':'b'*64})]
        for item in patches:item.start();self.addCleanup(item.stop)
        return job,route,calls

    def test_invalid_candidate_restores_only_owned_file_without_reload(self):
        job,route,calls=self.route_fixture(fail_test=True)
        with self.assertRaisesRegex(m.Hold,'ORIGINAL_RESTORED'):
            m.target_cutover('a'*64,m.Checkpoint(job))
        self.assertEqual(route.read_bytes(),b'original\n')
        self.assertFalse(any('reload' in call for call in calls))

    def test_reload_unknown_does_not_compensate_or_replay(self):
        job,route,calls=self.route_fixture(unknown_reload=True)
        with self.assertRaises(m.Unknown):m.target_cutover('a'*64,m.Checkpoint(job))
        self.assertEqual(route.read_bytes(),b'candidate\n')
        self.assertEqual(len([call for call in calls if 'reload' in call]),1)
        self.assertFalse(any('stop' in call for call in calls))
        self.assertTrue((job/'nginx_reload.unknown.json').exists())

    def test_known_https_failure_restores_route_and_stops_only_target(self):
        job,route,calls=self.route_fixture()
        with patch.object(m.time,'monotonic',side_effect=[0,20]):
            with self.assertRaisesRegex(m.Hold,'SOURCE_FENCED_DATA_PRESERVED'):
                m.target_cutover('a'*64,m.Checkpoint(job))
        self.assertEqual(route.read_bytes(),b'original\n')
        stopped=[call for call in calls if 'stop' in call]
        self.assertEqual(stopped,[['/usr/bin/systemctl','stop',m.TARGET_UNIT]])
        self.assertTrue((job/'stop_owned.result.json').exists())

    def test_completed_reload_and_exact_https_result(self):
        job,route,calls=self.route_fixture()
        with patch.object(m,'https_probe',side_effect=[{'status':502,'body_sha256':'b'*64},
                                                     {'status':404,'body_sha256':'a'*64}]):
            result=m.target_cutover('a'*64,m.Checkpoint(job))
        self.assertTrue(result['production_cutover'])
        self.assertFalse(result['source_resumed'])
        self.assertEqual(route.read_bytes(),b'candidate\n')


class NativeFenceFixtureTest(unittest.TestCase):
    def test_private_synthetic_inode_immutable_readable_not_writable(self):
        status=Path('/proc/self/status').read_text()
        caps=int(next(line.split()[1] for line in status.splitlines() if line.startswith('CapEff:')),16)
        if not caps & (1<<9):
            self.skipTest('CAP_LINUX_IMMUTABLE absent; live source kernel fence NOT_VERIFIED')
        with tempfile.TemporaryDirectory(prefix='pr99-kernel-fixture-',dir='/root') as folder:
            path=Path(folder)/'synthetic-only'
            m.create(path,b'SYNTHETIC_NO_CUSTOMER_DATA')
            original=m.flag(path)
            try:
                m.flag(path,original|m.IMMUTABLE)
                self.assertEqual(m.read(path),b'SYNTHETIC_NO_CUSTOMER_DATA')
                with self.assertRaises(PermissionError):
                    with path.open('wb') as output:output.write(b'must not write')
            finally:
                m.flag(path,original)

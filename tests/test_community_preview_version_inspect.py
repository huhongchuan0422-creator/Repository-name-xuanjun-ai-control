"""Incremental synthetic filesystem/process/typed-projection tests; no host/provider calls."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
import unittest
from email.message import Message
from unittest.mock import patch
from scripts import community_preview_version_inspect as v

ROOT=Path(__file__).resolve().parents[1]

class ReadonlyVersion(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('ROOT_ANCHOR','ROOT_UID','PROJECT_UID'):
            value=str(self.root) if name=='ROOT_ANCHOR' else os.getuid()
            guard=patch.object(v,name,value);guard.start();self.addCleanup(guard.stop)
    def file(self,path,body=b'{}',mode=0o600):
        p=self.root/path.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
        p.write_bytes(body);p.chmod(mode);return p
    def test_parent_and_leaf_symlinks_and_writable_parent_denied(self):
        path=v.ROUTE_PATHS['community_route'];p=self.file(path,b'route')
        p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaises((v.Hold,OSError)):v.safe_file(path,True)
        p.unlink();p.write_bytes(b'route');p.chmod(0o600)
        p.parent.chmod(0o777)
        with self.assertRaises(v.Hold):v.safe_file(path,True)
        p.parent.chmod(0o700)
        parent=p.parent;renamed=parent.with_name('original-nginx');parent.rename(renamed);parent.symlink_to(renamed)
        with self.assertRaises((v.Hold,OSError)):v.safe_file(path,True)
    def test_metadata_never_reads_secret_or_database_bytes(self):
        for path in v.META_PATHS.values():
            if path.endswith('.json'):self.file(path,b'SECRET_BODY_MUST_NOT_BE_READ')
            else:(self.root/path.lstrip('/')).mkdir(parents=True,exist_ok=True)
        with patch.object(v.os,'read',side_effect=AssertionError('NO_BODY_READ')):
            for path in v.META_PATHS.values():self.assertEqual(v.safe_file(path)['status'],'OBSERVED')
        with self.assertRaises(v.Hold):v.safe_file(v.META_PATHS['wechat_secret_reference'],True)
        with self.assertRaises(v.Hold):v.safe_file(v.ROOT+'/data/center.db',True)
    def test_fifo_oversize_hardlink_and_wrong_owner_denied(self):
        path=v.TRANSACTION_PATHS['attempt'];p=self.file(path)
        p.unlink();os.mkfifo(p)
        with self.assertRaises(v.Hold):v.safe_file(path,True)
        p.unlink();p.write_bytes(b'x'*65537)
        with self.assertRaises(v.Hold):v.safe_file(path,True)
        p.write_bytes(b'{}');os.link(p,p.with_name('hardlink'))
        with self.assertRaises(v.Hold):v.safe_file(path,True)
        with patch.object(v,'ROOT_UID',os.getuid()+1234):
            with self.assertRaises(v.Hold):v.safe_file(path)
    def test_replacement_and_read_time_metadata_change_denied(self):
        path=v.TRANSACTION_PATHS['attempt'];p=self.file(path,b'{}')
        original=v.os.read
        def replace(fd,n):
            raw=original(fd,n)
            if raw:
                alternate=p.with_name('replacement');alternate.write_bytes(b'{}');alternate.chmod(0o600);os.replace(alternate,p)
            return raw
        with patch.object(v.os,'read',side_effect=replace):
            with self.assertRaises(v.Hold):v.safe_file(path,True)
        def change(fd,n):
            raw=original(fd,n)
            if raw:p.write_bytes(b'longer')
            return raw
        with patch.object(v.os,'read',side_effect=change):
            with self.assertRaises(v.Hold):v.safe_file(path,True)
    def test_route_digest_only_and_transaction_no_nested_passthrough(self):
        path=v.ROUTE_PATHS['shared_vhost_file_digest_only'];raw=b'P2_PRIVATE_CONFIG_SENTINEL'
        self.file(path,raw);meta,_=v.safe_file(path,True)
        self.assertEqual(meta['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertNotIn('SENTINEL',json.dumps(meta))
        good=dict(state='PUBLIC_ORIGINAL_ROLE_ASSETS_READY_AUTH_ACCEPTANCE_PENDING',source_sha='a'*40,
            image_id='sha256:'+'b'*64,container_id='c'*64,rollback_container=v.ROLLBACK,
            private_inputs_and_data='REUSED_UNCHANGED',old_id='d'*64,new_image='sha256:'+'e'*64,
            owner_vhost_sha256='f'*64,phase='PREPARED',payments=False,role_acceptance=False,wechat_login_verified=False)
        self.assertEqual(v.project_transaction(good),good)
        evil={key:{'secret':'NESTED_SENTINEL'} for key in good};evil['extra']=['SENTINEL']
        result=v.project_transaction(evil)
        self.assertTrue(all(value==v.UNKNOWN for value in result.values()))
        self.assertNotIn('SENTINEL',json.dumps(result));self.assertNotIn('extra',result)
        for key in ('payments','role_acceptance','wechat_login_verified'):
            self.assertEqual(v.project_transaction(dict(good,**{key:1}))[key],v.UNKNOWN)
        with self.assertRaises(v.Hold):v.project_transaction([])
    def test_parent_directory_replacement_and_reference_type_confusion_denied(self):
        path=v.ROUTE_PATHS['community_route'];p=self.file(path,b'route')
        original=v.os.read;done=[]
        def replace_parent(fd,n):
            raw=original(fd,n)
            if raw and not done:
                done.append(True);old=p.parent.with_name('old-nginx');p.parent.rename(old)
                p.parent.mkdir(mode=0o700);p.write_bytes(b'route');p.chmod(0o600)
            return raw
        with patch.object(v.os,'read',side_effect=replace_parent):
            with self.assertRaises(v.Hold):v.safe_file(path,True)
        plan=v.META_PATHS['host_plan_reference'];(self.root/plan.lstrip('/')).mkdir(parents=True)
        with self.assertRaises(v.Hold):v.safe_file(plan)
    def test_unavailable_binary_never_falls_back_to_history_image_or_other_command(self):
        with patch.object(v,'safe_file',side_effect=FileNotFoundError()), \
             patch.object(v,'health',return_value={'status':'OBSERVED','runtime_source_sha':v.UNKNOWN}):
            report=v.observe(lambda *a:self.fail('no Docker execution without protected original binary'))
        self.assertEqual(report['sections']['current_image']['status'],'NOT_OBSERVED')
        self.assertEqual(report['state'],'HOLD_PARTIAL_OBSERVATION')
        self.assertEqual(report['runtime_image_revision_relation'],v.UNKNOWN)
    def test_duplicate_and_nonfinite_json_rejected(self):
        for raw in ('{"state":1,"state":2}','{"x":NaN}'):
            with self.assertRaises(v.Hold):v.exact_json(raw)
    def test_container_image_projection_never_echoes_unknown_user_or_registry(self):
        base=['c'*64,'sha256:'+'b'*64,True,'SECRET_USER_SENTINEL']
        result=v.project_container('\n'.join(json.dumps(x) for x in base))
        self.assertEqual(result['original_nonroot_user'],v.UNKNOWN)
        self.assertNotIn('SENTINEL',json.dumps(result))
        result=v.project_container('\n'.join(json.dumps(x) for x in base+[True,True,3,'CONFIG_RO','DATA_RW','RUNTIME_RW']),True)
        self.assertTrue(result['original_mounts_match'])
        image=v.project_image('\n'.join(json.dumps(x) for x in ['sha256:'+'b'*64,
            ['private-registry.example/repo@sha256:'+'d'*64],'a'*40,'10001:1008']),'sha256:'+'b'*64)
        self.assertEqual(image['repository_digest_hashes'],['sha256:'+'d'*64])
        self.assertNotIn('private-registry',json.dumps(image))
        self.assertEqual(v.project_image('\n'.join(json.dumps(x) for x in ['sha256:'+'b'*64,None,None,'root']),'sha256:'+'b'*64)['repository_digest_state'],'EMPTY')
        with self.assertRaises(v.Hold):v.project_container('\n'.join(json.dumps(x) for x in ['bad',base[1],True,'root']))
        with self.assertRaises(v.Hold):v.project_image('\n'.join(json.dumps(x) for x in ['sha256:'+'b'*64,[],None,'root']),'sha256:'+'e'*64)
    def response(self,value=None,url=None):
        value=value if value is not None else dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',
            production_acceptance=False,runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=100)
        response=io.BytesIO(json.dumps(value).encode());response.status=200;response.headers=Message()
        response.headers['Content-Type']='application/json';response.geturl=lambda:url or v.URL
        return response
    def test_health_version_unknown_stale_wrong_types_not_current_same_source(self):
        def call(value):return v.health(lambda *a,**k:self.response(value),now=100)
        good=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                  runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=100)
        self.assertEqual(call(good)['runtime_source_sha'],'a'*40)
        missing=dict(good);missing.pop('runtime_source_sha');self.assertEqual(call(missing)['runtime_source_sha'],v.UNKNOWN)
        self.assertEqual(call(dict(good,runtime_source_sha={'secret':'SENTINEL'}))['runtime_source_sha'],v.UNKNOWN)
        self.assertEqual(call(dict(good,observed_at=True))['freshness'],v.UNKNOWN)
        self.assertEqual(v.health(lambda *a,**k:self.response(good),now=701)['freshness'],'STALE')
        self.assertEqual(call(dict(good,observed_at=131))['freshness'],'FUTURE')
        with self.assertRaises(v.Hold):v.health(lambda *a,**k:self.response(good,'https://other.invalid'),now=100)
    def test_health_dns_and_http_use_fixed_bounded_process_and_typed_frame(self):
        good=dict(status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False,
                  runtime_source_sha='a'*40,version_source='IMAGE_BUILD_STAMP',observed_at=100)
        frame=json.dumps(dict(http_status=200,body_hex=json.dumps(good).encode().hex()))
        with patch.object(v,'capture',return_value=frame) as capture:
            self.assertEqual(v.health(now=100)['runtime_source_sha'],'a'*40)
        args,kwargs=capture.call_args
        self.assertEqual(args[0][:5],['/usr/bin/python3','-I','-B','-S','-c'])
        self.assertEqual(args[0][5],v.HTTP_PROBE)
        self.assertEqual(kwargs,{'timeout':10,'budget':10000})
        self.assertIn(v.URL,v.HTTP_PROBE)
        self.assertNotIn('environ',v.HTTP_PROBE)
        for bad in (dict(http_status=True,body_hex=''),dict(http_status=200,body_hex={'secret':'SENTINEL'}),
                    dict(http_status=200,body_hex='a'*8193),dict(http_status=200,body_hex='00',extra='SENTINEL')):
            with patch.object(v,'capture',return_value=json.dumps(bad)),self.assertRaises(v.Hold):v.health(now=100)
    def test_network_process_timeout_is_hold_not_fallback_to_local_or_old_sha(self):
        with patch.object(v,'capture',side_effect=v.Hold('COMMAND_TIMEOUT')):
            with self.assertRaises(v.Hold):v.health(now=100)
    def test_command_timeout_and_combined_output_cap_kill_and_reap(self):
        spawned=[];real=v.subprocess.Popen
        def spawn(*a,**kw):
            p=real(*a,**kw);spawned.append(p);return p
        with patch.object(v.subprocess,'Popen',side_effect=spawn):
            with self.assertRaises(v.Hold):v.capture([sys.executable,'-c','import time;time.sleep(5)'],timeout=.05)
            with self.assertRaises(v.Hold):v.capture([sys.executable,'-c','import os;os.write(1,b"a"*40000);os.write(2,b"b"*40000)'])
        self.assertTrue(all(p.poll() is not None for p in spawned))
    def test_process_creation_failure_closes_selector(self):
        created=[];factory=v.selectors.DefaultSelector
        def selector():
            value=factory();created.append(value);return value
        with patch.object(v.selectors,'DefaultSelector',side_effect=selector), \
             patch.object(v.subprocess,'Popen',side_effect=OSError('synthetic no process')):
            with self.assertRaises(OSError):v.capture(['synthetic'])
        self.assertTrue(all(value.get_map() is None for value in created))
    def test_global_deadline_is_not_swallowed_by_section_collector(self):
        with patch.object(v,'safe_file',side_effect=v.TotalDeadline()):
            with self.assertRaises(v.TotalDeadline):v.observe(lambda *a:None)
    def test_changed_current_container_recheck_is_hold_and_no_history_fallback(self):
        calls=[]
        def command(args):
            calls.append(args)
            if args[-1]==v.CURRENT:
                count=sum(a[-1]==v.CURRENT for a in calls)
                base=['c'*64 if count==1 else 'd'*64,'sha256:'+'b'*64,True,'10001:1008']
                return '\n'.join(json.dumps(x) for x in (base+[True,True,3,'CONFIG_RO','DATA_RW','RUNTIME_RW'] if count==1 else base))
            if args[3]=='image':return '\n'.join(json.dumps(x) for x in ['sha256:'+'b'*64,[],'a'*40,'10001:1008'])
            return '\n'.join(json.dumps(x) for x in ['e'*64,'sha256:'+'f'*64,False,'10001:1008'])
        with patch.object(v,'safe_file',return_value={'status':'OBSERVED','type':'REGULAR_FILE'}), \
             patch.object(v,'health',return_value={'status':'OBSERVED','runtime_source_sha':'a'*40}):
            report=v.observe(command)
        self.assertEqual(report['sections']['current_container_recheck']['status'],'HOLD_UNKNOWN')
        self.assertFalse(report['executable']);self.assertFalse(report['snapshot_atomic'])
        self.assertEqual(report['preview_version_acceptance'],'NOT_EVALUATED_EXACT_SOURCE_MATCH_STILL_REQUIRED')
        self.assertTrue(all(a[:3]==v.DOCKER and a[3:5] in (['container','inspect'],['image','inspect']) for a in calls))
        self.assertTrue(all('.Env' not in a[6] for a in calls))
    def test_wrong_host_stops_before_any_observation(self):
        with patch.object(v.os,'getuid',return_value=0),patch.object(v.os,'geteuid',return_value=0), \
             patch.object(v.os,'uname',return_value=type('Host',(),{'nodename':'not-the-host'})()), \
             patch.object(v,'observe',side_effect=AssertionError('NO_OBSERVATION')),patch('sys.stdout',new_callable=io.StringIO) as out:
            self.assertEqual(v.main(),2)
        self.assertIn('HOLD_HOST_OR_IDENTITY',out.getvalue())
    def test_scope_has_no_env_secret_or_db_body_or_mutating_subprocess(self):
        tree=ast.parse(Path(v.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Attribute):self.assertNotEqual(node.attr,'environ')
        self.assertNotIn('.Env',v.current_template())
        self.assertIn('eq (json .Config.Cmd)',v.current_template())
        self.assertNotIn('{{json .Config.Cmd}}',v.current_template())
        self.assertEqual(set(v.ROUTE_PATHS.values()),{'/etc/nginx/community-preview.inc','/etc/nginx/conf.d/xuanjun-p2-owner.conf'})

class CandidateBundle(unittest.TestCase):
    def test_shell_embeds_exact_python_manifest_and_python36_syntax(self):
        source=(ROOT/'scripts/community_preview_version_inspect.py').read_bytes()
        shell=(ROOT/'deploy/community-preview/inspect-version-readonly.sh').read_bytes()
        self.assertEqual(shell.split(b"<<'COMMUNITY_READONLY_PY'",1)[1].split(b'\n',1)[1].split(b'\nCOMMUNITY_READONLY_PY\n',1)[0],source.rstrip(b'\n'))
        ast.parse(source.decode(),feature_version=(3,6))
        manifest=json.loads((ROOT/'deploy/community-preview/readonly-version-manifest.json').read_text())
        self.assertFalse(manifest['site_executed'])
        self.assertEqual(manifest['host'],v.HOST)
        self.assertEqual(manifest['allowed_docker_operations'],['container inspect','image inspect'])
        self.assertEqual(manifest['shared_vhost_scope'],'FILE_METADATA_AND_SHA256_ONLY_NO_P2_RUNTIME_OR_DATA')
        for path,meta in manifest['files'].items():
            raw=(ROOT/path).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),meta['sha256'])
            self.assertEqual(len(raw),meta['bytes'])
    def test_candidate_scope_reuses_original_test_gate_without_enabling_site_jobs(self):
        import textwrap
        workflow=(ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
        code=textwrap.dedent(workflow.split("python - <<'EVIDENCE'\n",1)[1].split('          EVIDENCE',1)[0])
        ns={'__name__':'readonly_scope_evidence_fixture'};exec(compile(code,'actual-original-evidence-gate','exec'),ns)
        repo='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
        branch='feature/chatgpt-community-wechat-sp-offline-20261017'
        run=dict(id=1,head_sha='a'*40,head_branch=branch,path='.github/workflows/chatgpt-community-wechat-sp-offline.yml',
                 event='push',status='completed',conclusion='success',repository={'full_name':repo},head_repository={'full_name':repo})
        jobs=dict(total_count=1,jobs=[dict(id=2,name='test',status='completed',conclusion='success',steps=[dict(
            name='UK read-only inspection candidate affected scope (no site execution)',status='completed',conclusion='success')])])
        artifacts=dict(total_count=1,artifacts=[dict(id=3,name='community-phase-integration-evidence',expired=False,
            expires_at='2030-01-01T00:00:00Z',size_in_bytes=100,digest='sha256:'+'a'*64,workflow_run=dict(
                id=1,head_sha='a'*40,head_branch=branch,repository_id=1413132159,head_repository_id=1413132159))])
        self.assertEqual(ns['validate'](run,jobs,artifacts,'a'*40,1,4,100)['status'],'EXACT_SHA_HOSTED_TEST_EVIDENCE_REUSED')
        jobs['jobs'][0]['steps'][0]['conclusion']='skipped'
        with self.assertRaises(ValueError):ns['validate'](run,jobs,artifacts,'a'*40,1,4,100)
        self.assertIn('needs: [test, mini-sdk]',workflow)
        self.assertIn('contents: read',workflow)
        self.assertIn("!contains(github.event.head_commit.message, '[preview-inspection-scope]')",workflow)
        self.assertIn('if-no-files-found: error',workflow)
    def test_original_source_zip_requires_complete_candidate_inputs(self):
        from scripts.community_stage_package import build
        import zipfile
        raw,_=build(ROOT)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in ('scripts/community_preview_version_inspect.py','deploy/community-preview/inspect-version-readonly.sh',
                         'deploy/community-preview/readonly-version-manifest.json'):
                self.assertEqual(archive.read(name),(ROOT/name).read_bytes())


if __name__=='__main__':unittest.main()

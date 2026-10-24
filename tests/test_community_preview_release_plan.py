"""Offline synthetic evidence and state transitions; no site/old updater calls."""
import ast
import copy
import unittest
from pathlib import Path
from scripts import community_preview_release_plan as p


def source():
    return dict(source_sha='a'*40,tree_sha='b'*40,source_zip_sha256='c'*64,artifact_id=1,
                artifact_sha256='d'*64,run_id=2,ocr_source_sha=p.OCR_SHA)


def current():
    return dict(container_id='e'*64,image_id='sha256:'+'f'*64,oci_revision=p.OBSERVED_OCI,
        running=True,user='10001:1008',observed_at=1000,config_identity_sha256='1'*64,
        data_identity_sha256='2'*64,routing_sha256='3'*64,isolation_sha256='4'*64,backup_reference_sha256='5'*64)


def image():
    s=source()
    return dict(source_sha=s['source_sha'],tree_sha=s['tree_sha'],source_zip_sha256=s['source_zip_sha256'],
        oci_revision=s['source_sha'],image_id='sha256:'+'6'*64,repo_digest=None,
        image_archive_sha256='7'*64,artifact_sha256='8'*64,artifact_id=3,run_id=s['run_id'])


class ReleaseCandidate(unittest.TestCase):
    def test_actual_missing_image_or_current_never_produces_fake_actions_or_authority(self):
        s=source();r=p.prepare(s)
        self.assertEqual(r['state'],'HOLD_MISSING_EVIDENCE');self.assertEqual(r['actions'],[])
        self.assertIsNone(r['image']);self.assertFalse(r['executable']);self.assertFalse(r['execution_approved'])
        self.assertFalse(r['manual_preview']['preview_enabled']);self.assertFalse(r['ocr_enabled'])
        self.assertEqual(p.prepare(s,current())['actions'],[])
    def test_complete_synthetic_metadata_compiles_only_exact_review_arrays(self):
        r=p.prepare(source(),current(),image())
        self.assertEqual(r['state'],'REVIEW_CANDIDATE_NOT_AUTHORIZED');self.assertFalse(r['executable'])
        run=r['actions'][3]['argv'];self.assertIn('10001:1008',run);self.assertIn('--pull',run)
        self.assertEqual(run[run.index('--pull')+1],'never');self.assertIn(image()['image_id'],run)
        for forbidden in ('--env','--publish','--privileged','--volume'):
            self.assertNotIn(forbidden,run)
        self.assertEqual(r['rollback']['old_start_argv'][-1],current()['container_id'])
        self.assertNotEqual(r['rollback_name'],'xuanjun-community-preview-before-2330dd55')
        self.assertIn('/var/lib/xuanjun-community-preview/config',run[-5])
    def test_image_source_tree_archive_and_oci_cannot_mix_versions(self):
        for key in ('source_sha','tree_sha','source_zip_sha256','run_id','oci_revision'):
            v=image();v[key]='0'*64 if key!='run_id' else 999
            with self.assertRaises(ValueError):p.prepare(source(),current(),v)
    def test_exact_metadata_no_paths_or_permission_flags_from_request(self):
        for entry in (source(),current(),image()):
            v=copy.deepcopy(entry);v['approved']=True
            with self.assertRaises(ValueError):
                if 'running' in v:p.prepare(source(),v,image())
                elif 'image_archive_sha256' in v:p.prepare(source(),current(),v)
                else:p.prepare(v)
        for key,value in (('container_id',';rm -rf /'),('user','0'),('running',1),('observed_at',True),('config_identity_sha256','/secret'),('oci_revision','a'*40)):
            v=current();v[key]=value
            with self.assertRaises(ValueError):p.prepare(source(),v,image())
    def test_bool_ids_and_missing_reference_digests_rejected(self):
        for key in ('run_id','artifact_id'):
            v=source();v[key]=True
            with self.assertRaises(ValueError):p.prepare(v)
        for value in (True,2.0,'2'):
            v=image();v['run_id']=value
            with self.assertRaises(ValueError):p.prepare(source(),current(),v)
        for key in ('image_archive_sha256','artifact_sha256','repo_digest'):
            v=image();v[key]='UNKNOWN'
            with self.assertRaises(ValueError):p.prepare(source(),current(),v)
    def test_receipt_names_bind_current_identity_and_new_source_without_touching_old_history(self):
        r=p.prepare(source(),current(),image());c=current();c['container_id']='9'*64
        other=p.prepare(source(),c,image())
        self.assertNotEqual(r['attempt'],other['attempt']);self.assertNotEqual(r['plan_sha256'],other['plan_sha256'])
        self.assertEqual(r['rollback']['database_restore'],'NOT_AUTOMATIC_NOT_PROVEN')
    def test_success_requires_actual_new_receipt_and_exact_health(self):
        state='PREPARED'
        for event in ('OLD_STOPPED','OLD_RENAMED','NEW_RECEIPT','EXACT_HEALTH'):state=p.next_phase(state,event)
        self.assertEqual(state,'COMMITTED')
        with self.assertRaises(ValueError):p.next_phase('OLD_RETAINED','EXACT_HEALTH')
    def test_failure_recovery_requires_new_stopped_socket_absent_and_old_exact(self):
        state=p.next_phase('NEW_KNOWN','KNOWN_FAILURE')
        with self.assertRaises(ValueError):p.next_phase(state,'OLD_EXACT_READY')
        for event in ('NEW_STOPPED','NEW_RENAMED_SOCKET_ABSENT','OLD_EXACT_READY'):state=p.next_phase(state,event)
        self.assertEqual(state,'ROLLED_BACK_PREVIEW_HOLD')
    def test_unknown_at_every_stage_never_starts_old_or_new(self):
        for state in ('PREPARED','OLD_STOPPED','OLD_RETAINED','NEW_KNOWN','ROLLBACK_STOP_NEW','ROLLBACK_RENAME_NEW'):
            hold=p.next_phase(state,'UNKNOWN');self.assertEqual(hold,'HOLD_INSPECT_SAME_ATTEMPT')
            with self.assertRaises(ValueError):p.next_phase(hold,'OLD_EXACT_READY')
    def test_exact_health_source_image_and_freshness_all_required(self):
        s=source()['source_sha'];v=dict(http_status=200,url=p.URL,status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',
            production_acceptance=False,runtime_source_sha=s,version_source='IMAGE_BUILD_STAMP',observed_at=1000)
        self.assertTrue(p.exact_health(v,s,s,1000))
        for key,bad in (('http_status',200.0),('runtime_source_sha',None),('version_source',None),('observed_at',True),('observed_at',399),
                        ('observed_at',1031),('url','https://other/'),('production_acceptance',True)):
            r={**v,key:bad};self.assertFalse(p.exact_health(r,s,s,1000))
        self.assertFalse(p.exact_health(v,s,p.OBSERVED_OCI,1000))
    def test_original_current_health_without_stamp_stays_hold(self):
        self.assertFalse(p.exact_health(dict(http_status=200,url=p.URL,status='READY',scope='PROCESS_AND_DATABASE_CONNECTIVITY',production_acceptance=False),
                                       source()['source_sha'],p.OBSERVED_OCI,1000))
    def test_compiler_cannot_execute_or_reach_network_or_import_old_upgrader(self):
        tree=ast.parse(Path(p.__file__).read_text())
        imports={n.names[0].name for n in ast.walk(tree) if isinstance(n,ast.Import)}
        self.assertEqual(imports,{'hashlib','json','re'})
        self.assertFalse(any(isinstance(n,ast.ImportFrom) for n in ast.walk(tree)))
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {'open','exec','eval','__import__'} for n in ast.walk(tree)))

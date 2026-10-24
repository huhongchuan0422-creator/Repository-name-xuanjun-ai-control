"""Isolated original Queue -> OAuth -> Receiver lifecycle, no live authority."""
import contextlib
import hashlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE=pathlib.Path(__file__).parent
sys.path.insert(0,str(HERE/'reused-6825'))
sys.path.insert(0,str(HERE/'successor_controller'))
sys.path.insert(0,str(HERE/'new19-source'))
from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
from production.cloud_connection.oauth_resource import OAuthProjectResource
from production.cloud_connection.private_transfer import stamp
from production.cloud_connection.private_transfer import directory, Hold as SourceHold
from production.cloud_connection.queue import Queue,canonical
from production.cloud_connection.worker import Github,Cloud,Network
from pr17_b5_deployment_composition import OriginalComposition
from pr17_b5_successor_authority import ExistingRequestAuthority
from pr17_b5_successor_backend import R2HostBackend
from pr17_b5_successor_fixed_io import FixedR2IO
import pr17_b5_successor_review as c53

NOW=1000
RECIPIENT='github-332398908';PROJECT='p2-b5-material-analysis'

class Auth:
    def authenticate(self,header,scope,project,now):
        if (header,scope,project,now)!=('Bearer fixture-only','project.files.read',PROJECT,NOW):
            raise AssertionError('UNTRUSTED_FIXTURE_AUTH')
        return RECIPIENT

class OriginalLifecycle(unittest.TestCase):
    def setUp(self):
        # Original descriptor readers reject every world-writable ancestor.
        # /tmp is not a valid source root even for an isolated CI fixture.
        parent=('/root' if os.geteuid()==0 else
                os.environ.get('B5_PROTECTED_TEST_PARENT',str(pathlib.Path.home())))
        temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(temp.cleanup)
        root=pathlib.Path(temp.name)
        self.root=root
        archive_root=root/'archive';archive_root.mkdir(mode=0o700)
        packages=root/'packages';packages.mkdir(mode=0o700)
        dest=root/'receiver';dest.mkdir(mode=0o700)
        sizes=[53969]+[2201]*17+[2206]
        self.data=[bytes([i])*size for i,size in enumerate(sizes,1)]
        objects=[]
        for i,raw in enumerate(self.data,1):
            name='file%02d.bin'%i;ref='b5-material-%02d'%i
            archive=i<=5
            if not archive:
                p=packages/name;p.write_bytes(raw);p.chmod(0o600)
            objects.append({'ref':ref,'root_ref':'archive' if archive else 'packages',
                            'relative_path':name,'bytes':len(raw),
                            'sha256':hashlib.sha256(raw).hexdigest()})
        tar=archive_root/'source.tar'
        with tarfile.open(str(tar),'w') as t:
            for i in range(5):
                info=tarfile.TarInfo('file%02d.bin'%(i+1));info.size=len(self.data[i])
                t.addfile(info,io.BytesIO(self.data[i]))
        tar.chmod(0o600)
        digest=hashlib.sha256(tar.read_bytes()).hexdigest()
        catalog={'schema':1,'project':PROJECT,'approval_ref':'fixture-only',
            'source_commit':'a'*40,'executor_sha256':'b'*64,
            'target':'uk','valid_from':900,'valid_until':2000,
            'recipients':[RECIPIENT],'objects':objects}
        catsha=hashlib.sha256(canonical(catalog).encode()).hexdigest()
        policy={'project':PROJECT,'max_objects':19,'max_object_bytes':53969,
                'max_total_bytes':93592,'recipients':[RECIPIENT],
                'root_refs':['archive','packages']}
        roots={'archive':[str(archive_root),os.geteuid()],
               'packages':[str(packages),os.geteuid()]}
        requests={x['ref']:'fixture-%02d'%i for i,x in enumerate(objects,1)}
        binding={'schema':1,'catalog':catalog,'catalog_sha256':catsha,
            'policy':policy,'roots':roots,'recipient_id':RECIPIENT,'requests':requests,
            'execution_user':'fixture','execution_uid':os.geteuid(),
            'reader_sha256':hashlib.sha256((HERE/'new19-source'/'production/cloud_connection/private_transfer.py').read_bytes()).hexdigest(),
            'archive_reader_sha256':hashlib.sha256((HERE/'new19-source'/'production/cloud_connection/archive_reader.py').read_bytes()).hexdigest(),
            'archives':{'archive':{'filename':'source.tar','identity':list(stamp(tar.stat())),
                'member_prefix':'','max_headers':64,'max_read_bytes':1048576,
                'sha256':digest}}}
        raw=canonical(binding).encode()
        self.binding_raw=raw
        self.policy=ApprovedObjectsPolicy(raw,hashlib.sha256(raw).hexdigest())
        self.queue=Queue(str(root/'queue.sqlite'),'b'*64,[332398908],
                         approved_objects=self.policy)
        (root/'queue.sqlite').chmod(0o600)
        self.addCleanup(self.queue.close)
        self.requests=[{'schema':1,'request_id':requests[x['ref']],
            'project':PROJECT,'target':'uk','operation':'fetch_approved_object',
            'executor_sha256':'b'*64,'expires_unix':1500,
            'arguments':{'manifest_sha256':catsha,'object_ref':x['ref'],
                         'recipient_id':RECIPIENT}} for x in objects]
        self.resource=OAuthProjectResource(self.queue.db,
            {catsha:(self.policy.catalog,roots)},Auth(),enabled=True,
            clock=lambda:NOW,custodies={catsha:(str(dest),os.geteuid())})
        network=Network()
        original=OriginalComposition(queue=None,resource=None,
            github=Github('/etc/xuanjun-development/github-intake-token',network,1003),
            cloud=Cloud('/etc/xuanjun-cloud-executor/credentials.json',network),
            policy=self.policy,requests=self.requests,archive_root_ref='archive',
            destination_root=str(dest),destination_owner=os.geteuid(),
            authorization_from_request=lambda:'Bearer fixture-only',clock=lambda:NOW,
            request_publisher=lambda request:None,test_only=True)
        import pr17_b5_successor_binder as frozen_binder
        spec=frozen_binder.verify_spec_bytes((HERE/'SUCCESSOR_SPEC.json').read_bytes())
        auth=ExistingRequestAuthority(authenticator=None,
            active_resource_reader=lambda:b'{}',expected_resource_raw=b'{}',
            prepared_settings={},catalog_raw=original.catalog_raw,
            catalog_sha=original.catalog_sha,request_ids=original.request_ids,
            authorization_from_request=original.authorization_from_request,
            original=original,runtime_attachment=lambda phase:(self.queue,self.resource))
        self.backend=R2HostBackend(legacy_io=object(),spec=spec,
            source_blobs={},observed_bytes={},authority=auth)
        self.backend.tried_start=True;self.backend.bundle={'catalog_sha':catsha}
        self.backend.activation_committed=True
        self.backend.expected_ids=tuple(requests.values())
        self.backend.job='/opt/xuanjun-cloud-connection/l2-b5-staged-f0fe0d3978b7'
        self.backend.window_open=True
        self.backend.verify_window_admission=lambda *args:None  # explicit offline grant fixture
        self.archive_size=tar.stat().st_size;self.archive_sha=digest
        self.journal=root/'job';self.journal.mkdir(mode=0o700)

    def test_protected_parent_accepts_home_and_rejects_tmp(self):
        fd=directory(str(self.root/'packages'),os.geteuid())
        os.close(fd)
        with tempfile.TemporaryDirectory(dir=tempfile.gettempdir()) as unsafe:
            with self.assertRaisesRegex(SourceHold,'ROOT_PARENT'):
                directory(unsafe,os.geteuid())

    def test_full_19_original_read_custody_body_chain(self):
        b=self.backend
        self.assertTrue(b.attach_original_after_worker_start())
        comments=[]
        def publisher(request):
            comments.append(request['request_id'])
            self.queue.submit(canonical(request),332398908,NOW)
            from production.cloud_connection.worker import PREFIX
            return {'id':len(comments),'user':{'id':332398908},
                    'body':PREFIX+canonical(request),
                    'created_at':'fixture-time','updated_at':'fixture-time'}
        b.authority.original.publisher=publisher
        class RecordedFixedIO(FixedR2IO):
            def __init__(self,spec,root,ids):
                super().__init__(spec)
                self.root=root
                # The disposable policy uses synthetic IDs; the release
                # constructor above still validates the real fixed spec.
                self.ids=frozenset(ids)
            def local(self,path):
                super()._path(path)
                return self.root/path.rsplit('/',1)[-1]
            def absent(self,path):
                if self.local(path).exists():raise AssertionError('REPOST_ATTEMPT')
            def newfile(self,path,raw):
                with self.local(path).open('xb') as f:
                    f.write(raw);f.flush();os.fsync(f.fileno())
            def read(self,path):return self.local(path).read_bytes(),None
        b.legacy=RecordedFixedIO(b.spec,self.journal,b.expected_ids);b.reserved=True;b.seq=0
        b.witness_action=lambda:contextlib.nullcontext()  # offline scope only
        b.bundle={'catalog_sha':self.policy.catalog.sha,
                  'requests':self.requests,
                  'envelopes':['XJ_CLOUD_TASK_V1\n'+canonical(x) for x in self.requests]}
        b.bundle.update(batch_id='fixture-batch',generation_seal='f'*64,
                        window_start=900,window_end=4500)
        b.legacy.newfile(b.job+'/reservation.json',c53.canon({
            'batch':'fixture-batch','ids':list(b.expected_ids),
            'catalog_sha256':b.bundle['catalog_sha'],
            'request_set_sha256':c53.sha(c53.canon(self.requests)),
            'generation_seal':b.bundle['generation_seal'],
            'window_start':900,'window_end':4500,'release':c53.COMMIT,
            'state':'RESERVED_NOT_SUBMITTED'})+b'\n')
        b.legacy.newfile(b.job+'/window-open.json',c53.canon({
            'catalog_sha256':b.bundle['catalog_sha'],
            'window_start':900,'window_end':4500,
            'state':'ACTIVE_NOT_DELIVERED'})+b'\n')
        b.bundle['files']={name:b'' for name in c53.CONFIGS+c53.SLOTS}
        tx=c53.Transaction(b.spec,b.bundle,b)
        tx.stage='WINDOW_ENABLED'
        intake=tx.run_19_after_window()
        self.assertEqual(intake['state'],'INTAKE_SENT_AWAITING_READY',intake)
        self.assertEqual(len(comments),19)
        self.assertEqual(tx.continue_after_original_ready()['state'],
                         'WAIT_ORIGINAL_SUCCESS_NO_REPOST')
        for i,request in enumerate(self.requests,1):
            self.assertEqual(b._auth('observe_original_intake_ready',request)['state'],'ACCEPTED')
            self.queue.begin_dispatch(request['request_id'],NOW)
            invoke='fixture-invoke-%02d'%i
            self.queue.record_invoke(request['request_id'],invoke)
            item=self.policy.catalog.objects[request['arguments']['object_ref']]
            receipt={'state':'SUCCESS','invoke_id':invoke,'target':'uk',
                     'manifest_sha256':self.policy.catalog.sha,'object_ref':item['ref'],
                     'recipient_id':RECIPIENT,'bytes':item['bytes'],
                     'sha256':item['sha256'],'action_binding_sha256':self.policy.sha}
            self.queue.terminal(request['request_id'],invoke,receipt)
        # A new interpreter reopens the actual file-backed original Queue and
        # reads the protected intent/SENT journal. No publisher is available to
        # that interpreter, so a recovery regression cannot silently repost.
        fixture={'binding':self.binding_raw.decode(),'requests':self.requests,
                 'queue':str(self.root/'queue.sqlite'),
                 'receiver':str(self.root/'receiver'),
                 'owner':os.geteuid(),
                 'bundle':{k:v for k,v in b.bundle.items() if k!='files'}}
        (self.root/'fresh-process.json').write_text(json.dumps(fixture))
        child=r'''import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);here=pathlib.Path(sys.argv[2])
sys.path[:0]=[str(here),str(here/'reused-6825'),str(here/'new19-source'),str(here/'successor_controller')]
from production.cloud_connection.fixed_actions import ApprovedObjectsPolicy
from production.cloud_connection.queue import Queue
from production.cloud_connection.oauth_resource import OAuthProjectResource
from production.cloud_connection.worker import Github,Cloud,Network
from pr17_b5_deployment_composition import OriginalComposition
from pr17_b5_successor_authority import ExistingRequestAuthority
from pr17_b5_successor_backend import R2HostBackend
from test_successor_release_gate import fixture_gate
import pr17_b5_successor_binder as binder
f=json.loads((root/'fresh-process.json').read_text())
policy=ApprovedObjectsPolicy(f['binding'].encode(),__import__('hashlib').sha256(f['binding'].encode()).hexdigest())
q=Queue(f['queue'],'b'*64,[332398908],approved_objects=policy,existing_readonly=True)
class Auth:
 def authenticate(self,*args):raise AssertionError('BODY_AUTH_NOT_USED_IN_RECOVERY')
resource=OAuthProjectResource(q.db,{policy.catalog.sha:(policy.catalog,policy.binding['roots'])},Auth(),enabled=True,clock=lambda:1000,custodies={policy.catalog.sha:(f['receiver'],f['owner'])})
network=Network()
authorization=lambda:'Bearer fixture-only'
o=OriginalComposition(queue=None,resource=None,github=Github('/etc/xuanjun-development/github-intake-token',network,1003),cloud=Cloud('/etc/xuanjun-cloud-executor/credentials.json',network),policy=policy,requests=f['requests'],archive_root_ref='archive',destination_root=f['receiver'],destination_owner=f['owner'],authorization_from_request=authorization,clock=lambda:1000,request_publisher=lambda _:None,test_only=True)
o.attach_after_worker_start(q,resource)
a=object.__new__(ExistingRequestAuthority);a.original=o;a.catalog_raw=o.catalog_raw;a.catalog_sha=o.catalog_sha;a.request_ids=o.request_ids;a.authorization_from_request=o.authorization_from_request
b=object.__new__(R2HostBackend);b.authority=a;b.expected_ids=o.request_ids;b.job=str(root/'job');b.legacy=type('Legacy',(),{'read':lambda self,p:((root/'job'/p.rsplit('/',1)[-1]).read_bytes(),None)})()
b.spec=binder.verify_spec_bytes((here/'SUCCESSOR_SPEC.json').read_bytes());b.release_gate=fixture_gate(b.spec,'recover')
try:print(json.dumps(b.recover_intake_readonly(f['bundle']),sort_keys=True))
finally:q.close()
'''
        proc=subprocess.run([sys.executable,'-B','-c',child,str(self.root),str(HERE)],
                            capture_output=True,text=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stderr)
        observed=json.loads(proc.stdout)
        self.assertEqual((observed['state'],observed['success_count'],
                          observed['mutation_allowed']),
                         ('SUCCESS_OBSERVED_READONLY',19,False))
        # The entry's observer must correlate the actual SQLite rows with
        # protected intent/SENT records before it offers custody continuation.
        from test_successor_release_gate import fixture_gate
        import pr17_b5_successor_binder as frozen_binder
        b.spec=frozen_binder.verify_spec_bytes((HERE/'SUCCESSOR_SPEC.json').read_bytes())
        b.release_gate=fixture_gate(b.spec,'recover')
        original=b.authority.original
        original.release_observer_for_closeout()
        def pair(readonly):
            queue=Queue(str(self.root/'queue.sqlite'),'b'*64,[332398908],
                        approved_objects=self.policy,existing_readonly=readonly,
                        existing_custody=not readonly)
            self.addCleanup(queue.close)
            resource=OAuthProjectResource(queue.db,
                {self.policy.catalog.sha:(self.policy.catalog,self.policy.binding['roots'])},
                Auth(),enabled=True,clock=lambda:NOW,
                custodies={self.policy.catalog.sha:(str(self.root/'receiver'),os.geteuid())})
            return queue,resource
        original.attach_after_worker_start(*pair(True))
        self.assertEqual(b.observe_poststart_canonical_readonly(b.bundle)['state'],
                         'SUCCESS_SNAPSHOT_READONLY')
        import pr17_b5_successor_entry as entry
        b.recovered_from_protected=True
        b.authority.runtime_attachment=lambda phase:(original.queue,original.resource)
        with patch.object(entry,'_recover',return_value=tx):
            self.assertEqual(entry.dispatch('query')['state'],
                             'SUCCESS_SNAPSHOT_READONLY')
        original.replace_runtime_phase(*pair(False),'observe','custody')
        # The production pinned archive is 559 MB. This explicit local fixture
        # substitutes only that fixed archive identity, then calls the same
        # original whole-hash/member algorithm with its own bounded tar.
        b.verify_original_archive_identity_and_whole_digest=lambda size,digest: b._receipt(
            'verify_original_archive_custody',self.archive_size,self.archive_sha)
        self.assertEqual(tx.continue_after_original_ready()['state'],
                         'CUSTODY_COMPLETE_DELIVERY_NOT_PROVEN')
        self.assertEqual(tx.stage,'READY_FOR_B5_HTTP_NOT_RECEIVED')
        original.replace_runtime_phase(*pair(True),'custody','observe')
        self.assertEqual(b.observe_poststart_canonical_readonly(b.bundle)['state'],
                         'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY')
        with patch.object(entry,'_recover',return_value=tx):
            self.assertEqual(entry.dispatch('recover')['state'],
                             'B5_HTTP_AWAITING_PROVENANCE_NO_REPLAY')
        original.replace_runtime_phase(*pair(False),'observe','custody')
        from successor_analyst_read import receive_all
        with self.assertRaisesRegex(c53.Hold,'B5_HTTP_REQUEST_LOCAL_ONLY'):
            tx.receive_and_verify_19()
        custody_receipt=b._receipt('custody_once',b.job,self.policy.catalog.sha)
        invokes={r['request_id']:'fixture-invoke-%02d'%i
                 for i,r in enumerate(self.requests,1)}
        # This direct original OAuthResource fixture still authenticates every
        # request, but it is not the deployed B5 window or real cloud grant.
        result=receive_all(requests=self.requests,
             objects=[self.policy.catalog.objects[r['arguments']['object_ref']]
                      for r in self.requests],
             catalog_sha=self.policy.catalog.sha,project=PROJECT,
             recipient=RECIPIENT,success_invokes=invokes,
             custody=custody_receipt,
             read_project_chunk=lambda **args:original.resource.read(
                 'Bearer fixture-only',args,NOW))
        self.assertEqual(result['state'],
             'B5_HTTP_BYTES_VALIDATED_SOURCE_ATTESTATION_PENDING')
        with self.assertRaisesRegex(c53.Hold,'B5_ORIGINAL_TOOL_PROVENANCE_SOURCE_UNKNOWN'):
            tx.close_after_b5_http(result)
        self.assertEqual(len(comments),19)
        self.assertEqual(b._auth('observe_original_success_progress',
            b.expected_ids,self.policy.catalog.sha),19)
        success=b._receipt('verify_nineteen_original_success_receipts',
            b.expected_ids,self.policy.catalog.sha)
        self.assertEqual(success['invoke_bound_count'],19)
        archive=b._receipt('verify_original_archive_custody',
            self.archive_size,self.archive_sha)
        self.assertTrue(archive['whole_sha_verified'])
        custody=b._receipt('custody_once',b.job,self.policy.catalog.sha)
        self.assertEqual((custody['state'],custody['objects'],custody['bytes']),
                         ('MATERIAL_CUSTODY_COMPLETE',19,93592))
        for request,data in zip(self.requests,self.data):
            item=self.policy.catalog.objects[request['arguments']['object_ref']]
            self.assertEqual(b._auth('read_project_chunk_complete',
                request,self.policy.catalog.sha,item),data)

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(OriginalLifecycle)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

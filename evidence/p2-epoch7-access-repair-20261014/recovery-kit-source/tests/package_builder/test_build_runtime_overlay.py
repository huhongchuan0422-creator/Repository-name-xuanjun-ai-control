"""Isolated local fixture packages/Git objects only; no final source publication."""
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[1]
WORK=ROOT.parents[1]
FROZEN=WORK/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package'
sys.path.insert(0,str(ROOT))
import build_runtime_overlay as b


def git(repo,*args):
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','LANG':'C','GIT_CONFIG_NOSYSTEM':'1',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_NO_REPLACE_OBJECTS':'1',
         'GIT_AUTHOR_DATE':'2001-01-01T00:00:00+0000','GIT_COMMITTER_DATE':'2001-01-01T00:00:00+0000'}
    result=subprocess.run(['git','-C',str(repo)]+list(args),stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,env=env,timeout=30,check=False)
    if result.returncode:raise AssertionError(result.stderr.decode())
    return result.stdout.decode().strip()


class BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=tempfile.TemporaryDirectory(prefix='FIXTURE_ONLY_',dir=str(ROOT/'tests'))
        cls.base=pathlib.Path(cls.fixture.name)
        cls.changed=cls.base/'native_peer_identity.py'
        cls.changed.write_bytes((FROZEN/'stage1/native_peer_identity.py').read_bytes()+b'\n# LOCAL TEST FIXTURE ONLY\n')
        cls.added=cls.base/'fixture_overlay_helper.py';cls.added.write_bytes(b'FIXTURE_ONLY = True\n')
        cls.overlays={
            'stage1/native_peer_identity.py':{'source_path':str(cls.changed),'sha256':b.sha(cls.changed.read_bytes())},
            'stage1/fixture_overlay_helper.py':{'source_path':str(cls.added),'sha256':b.sha(cls.added.read_bytes())}}
        cls.prepared=b.prepare(str(FROZEN),cls.overlays)
        cls.repo=cls.base/'fixture-git';cls.repo.mkdir()
        files=dict(cls.prepared['payload']);files[b.MANIFEST]=cls.prepared['manifest_bytes'];files[b.VERIFIER]=cls.prepared['freezer_bytes']
        for path,raw in files.items():
            p=cls.repo/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        git(cls.repo,'init','-q');git(cls.repo,'add','--all')
        git(cls.repo,'-c','core.hooksPath=/dev/null','-c','user.name=P2 local fixture',
            '-c','user.email=p2-fixture@example.invalid','commit','-qm','LOCAL FIXTURE ONLY - NOT SOURCE PROVENANCE')
        cls.commit=git(cls.repo,'rev-parse','HEAD');cls.tree=git(cls.repo,'rev-parse','HEAD^{tree}')
        cls.local=dict(schema=1,kind='local_git_objects',repository=b.REPOSITORY,
                       commit_sha=cls.commit,tree_sha=cls.tree,local_repository=str(cls.repo))
        prefix='https://api.github.com/repos/'+b.REPOSITORY
        entries=[]
        for line in git(cls.repo,'ls-tree','-r',cls.commit).splitlines():
            metadata,path=line.split('\t',1);mode,kind,sha1=metadata.split()
            entries.append(dict(path=path,mode=mode,type=kind,sha=sha1))
        cls.external=dict(schema=1,kind='github_api_readback',repository=b.REPOSITORY,
            commit_sha=cls.commit,tree_sha=cls.tree,
            commit_readback=dict(sha=cls.commit,tree_sha=cls.tree,api_url=prefix+'/git/commits/'+cls.commit),
            tree_readback=dict(sha=cls.tree,truncated=False,api_url=prefix+'/git/trees/'+cls.tree+'?recursive=1',entries=entries),
            file_readbacks={path:dict(commit_sha=cls.commit,git_blob_sha1=b.git_blob_sha1(files[path]),
                content_sha256=b.sha(files[path]),api_url=prefix+'/contents/'+path+'?ref='+cls.commit)
                for path in set(cls.overlays)|{b.MANIFEST}})
    def test_explicit_evidence_runtime_prefix(self):
        evidence=copy.deepcopy(self.external)
        prefix='evidence/p2-epoch7-access-repair-20261014/runtime'
        evidence['source_prefix']=prefix
        for entry in evidence['tree_readback']['entries']:entry['path']=prefix+'/'+entry['path']
        for path,item in evidence['file_readbacks'].items():
            item['api_url']=item['api_url'].replace('/contents/'+path+'?', '/contents/'+prefix+'/'+path+'?')
        proof=b.verify_provenance(self.prepared,evidence,self.commit,self.tree)
        self.assertEqual(proof['source_prefix'],prefix)
    def test_wrong_or_unmapped_source_prefix_rejected(self):
        for prefix in ('../escape','arbitrary/other','evidence/p2-epoch7-access-repair-20261014/runtime'):
            evidence=copy.deepcopy(self.external);evidence['source_prefix']=prefix
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)
    @classmethod
    def tearDownClass(cls):cls.fixture.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=str(self.base));self.root=pathlib.Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def build(self,output='out',evidence=None,overlays=None,frozen=None):
        return b.build(str(frozen or FROZEN),self.overlays if overlays is None else overlays,
            self.external if evidence is None else evidence,self.commit,self.tree,str(self.root/output))
    def copied_frozen(self):
        target=self.root/'frozen';shutil.copytree(str(FROZEN),str(target));return target

    def test_all_frozen_102_bytes_verified_and_dynamic_final_count(self):
        self.assertEqual(self.prepared['counts'],dict(base=102,changed=1,unchanged=101,added=1,deleted=0,final=103))
        self.assertEqual(set(self.prepared['payload']),set(self.prepared['base']['files'])|{'stage1/fixture_overlay_helper.py'})

    def test_manifest_metadata_and_renderer_contract_unchanged(self):
        before=self.prepared['base'];after=self.prepared['manifest']
        self.assertEqual({k:v for k,v in before.items() if k!='files'},
                         {k:v for k,v in after.items() if k!='files'})
        self.assertEqual(set(self.prepared['rendered_identity_sha256']),set(before['rendering']['identity_files']))

    def test_external_readbacks_supported_without_local_git_or_network(self):
        with mock.patch.object(b,'_git',side_effect=AssertionError('external route must not require local Git')):
            receipt=self.build()
        self.assertEqual(receipt['counts']['final'],103)
        self.assertIn('SUPPLIED_GITHUB',receipt['provenance']['method'])
        self.assertEqual(receipt['provenance']['independent_provenance_review'],'PENDING')
        self.assertEqual(receipt['install_admission'],'NOT_GRANTED')
        self.assertFalse(receipt['host_changes']);self.assertFalse(receipt['network_calls'])

    def test_optional_local_git_object_proof_build(self):
        receipt=self.build(evidence=self.local)
        self.assertEqual(receipt['provenance']['method'],'LOCAL_GIT_OBJECTS_AND_ALL_RUNTIME_BYTES_CHECKED')
        self.assertEqual(receipt['provenance']['source_commit'],self.commit)

    def test_identical_inputs_produce_byte_identical_archives_and_receipts(self):
        first=self.build('one');second=self.build('two')
        self.assertEqual(first,second)
        for name in ('runtime-overlay-candidate.tar.gz','build-receipt.json','source-evidence.json'):
            self.assertEqual((self.root/'one'/name).read_bytes(),(self.root/'two'/name).read_bytes())

    def test_reuses_pinned_freezer_verify_and_exact_archive_metadata(self):
        receipt=self.build();path=self.root/'out/runtime-overlay-candidate.tar.gz'
        checked=self.prepared['freezer']['verify'](str(path),receipt['archive_sha256'],self.commit,self.tree)
        self.assertEqual(checked['file_count'],103)
        with tarfile.open(str(path),'r:gz') as archive:
            entries=archive.getmembers();self.assertEqual(len(entries),106)
            for entry in entries:
                self.assertTrue(entry.isfile());self.assertEqual((entry.uid,entry.gid,entry.mtime),(0,0,0))
                self.assertEqual(entry.mode,0o555 if entry.name.endswith('/'+b.VERIFIER) else 0o444)
            self.assertNotIn('source-evidence.json',{x.name for x in entries})

    def test_no_deletions_and_noop_overlay_counts(self):
        original=FROZEN/'stage1/native_peer_identity.py'
        prepared=b.prepare(str(FROZEN),{'stage1/native_peer_identity.py':{'source_path':str(original),'sha256':b.sha(original.read_bytes())}})
        self.assertEqual(prepared['counts'],dict(base=102,changed=0,unchanged=102,added=0,deleted=0,final=102))
        self.assertEqual(b.sha(prepared['manifest_bytes']),b.BASE_MANIFEST_SHA256)
        with self.assertRaises(ValueError):b.prepare(str(FROZEN),{'stage1/native_peer_identity.py':None})

    def test_new_helpers_are_explicit_and_only_stage1_python(self):
        spec=self.overlays['stage1/fixture_overlay_helper.py']
        for path in ('deploy/new.service','stage1/deep/new.py','stage1/helper.txt','tools/helper.py'):
            with self.assertRaises(ValueError):b.prepare(str(FROZEN),{path:spec})

    def test_rejects_unsafe_runtime_paths(self):
        spec=self.overlays['stage1/fixture_overlay_helper.py']
        for path in ('/stage1/x.py','../stage1/x.py','stage1/../x.py','stage1//x.py','stage1/./x.py','stage1\\x.py','stage1/x\0.py','stage1/x\n.py'):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):b.prepare(str(FROZEN),{path:spec})

    def test_rejects_metadata_installer_and_renderer_overrides(self):
        spec=self.overlays['stage1/fixture_overlay_helper.py']
        for path in (b.MANIFEST,b.VERIFIER,b.PROVENANCE,b.INSTALLER,'scripts/uk-owner-workbench-config.py'):
            with self.assertRaises(ValueError):b.prepare(str(FROZEN),{path:spec})
        for field in ('mode','owner_uid','delete','rendering','required_renderers'):
            changed=dict(spec);changed[field]=0
            with self.assertRaises(ValueError):b.prepare(str(FROZEN),{'stage1/new_helper.py':changed})

    def test_wrong_overlay_hash_rejected_before_output(self):
        overlays=copy.deepcopy(self.overlays);overlays['stage1/native_peer_identity.py']['sha256']='0'*64
        with self.assertRaises(ValueError):self.build(overlays=overlays)
        self.assertFalse((self.root/'out').exists())

    def test_overlay_syntax_error_rejected_without_execution(self):
        path=self.root/'invalid.py';path.write_bytes(b'def invalid(:\n')
        with self.assertRaises(SyntaxError):b.prepare(str(FROZEN),{'stage1/invalid.py':{'source_path':str(path),'sha256':b.sha(path.read_bytes())}})

    def test_overlay_code_is_compiled_never_executed(self):
        path=self.root/'never_execute.py';path.write_bytes(b'raise RuntimeError("MUST_NOT_EXECUTE")\n')
        prepared=b.prepare(str(FROZEN),{'stage1/never_execute.py':{'source_path':str(path),'sha256':b.sha(path.read_bytes())}})
        self.assertEqual(prepared['counts']['added'],1)

    def test_symlink_source_and_symlink_parent_rejected(self):
        link=self.root/'linked.py';link.symlink_to(self.added)
        parent=self.root/'linkdir';parent.symlink_to(self.base,target_is_directory=True)
        for path in (link,parent/self.added.name):
            spec={'source_path':str(path),'sha256':b.sha(self.added.read_bytes())}
            with self.assertRaises(ValueError):b.prepare(str(FROZEN),{'stage1/new_helper.py':spec})

    def test_hardlinked_source_rejected(self):
        path=self.root/'regular.py';path.write_bytes(b'x=1\n');os.link(str(path),str(self.root/'other.py'))
        with self.assertRaises(ValueError):b.read_regular(str(path))

    def test_relative_source_and_directory_source_rejected(self):
        for path in ('relative.py',str(self.root)):
            with self.assertRaises(ValueError):b.read_regular(path)

    def test_frozen_changed_manifest_verifier_provenance_or_runtime_rejected(self):
        for relative in (b.MANIFEST,b.VERIFIER,b.PROVENANCE,'stage1/native_peer_identity.py'):
            root=self.copied_frozen();path=root/relative;path.chmod(0o644);path.write_bytes(path.read_bytes()+b'\n')
            with self.assertRaises(ValueError):b.prepare(str(root),self.overlays)
            shutil.rmtree(str(root))

    def test_frozen_unexpected_file_and_symlink_directory_rejected(self):
        root=self.copied_frozen();(root/'undeclared.txt').write_bytes(b'extra')
        with self.assertRaises(ValueError):b.prepare(str(root),self.overlays)
        (root/'undeclared.txt').unlink();(root/'linked').symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(ValueError):b.prepare(str(root),self.overlays)

    def test_frozen_root_symlink_rejected(self):
        link=self.root/'frozen-alias';link.symlink_to(FROZEN,target_is_directory=True)
        with self.assertRaises(ValueError):b.prepare(str(link),self.overlays)

    def test_unknown_placeholder_rejects_changed_rendered_unit(self):
        source=FROZEN/'deploy/xuanjun-ledger.service';path=self.root/'bad.service'
        path.write_bytes(source.read_bytes()+b'# @@UNREVIEWED@@\n')
        with self.assertRaises(ValueError):b.prepare(str(FROZEN),{'deploy/xuanjun-ledger.service':{'source_path':str(path),'sha256':b.sha(path.read_bytes())}})

    def test_existing_or_symlink_output_rejected(self):
        path=self.root/'out';path.mkdir()
        with self.assertRaises(ValueError):self.build()
        path.rmdir();path.symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(ValueError):self.build()

    def test_output_cannot_be_within_frozen_tree(self):
        root=self.copied_frozen()
        with self.assertRaises(ValueError):b.build(str(root),self.overlays,self.external,self.commit,self.tree,str(root/'new-output'))
        self.assertFalse((root/'new-output').exists())

    def test_no_provenance_or_wrong_commit_tree_fails_before_output(self):
        for evidence in ({},dict(self.external,commit_sha='0'*40),dict(self.external,tree_sha='0'*40),dict(self.external,repository='other/repo')):
            with self.assertRaises(ValueError):self.build(evidence=evidence)
            self.assertFalse((self.root/'out').exists())

    def test_git_commit_readback_must_bind_exact_tree_and_api(self):
        for field,value in (('sha','0'*40),('tree_sha','0'*40),('api_url','https://example.invalid')):
            evidence=copy.deepcopy(self.external);evidence['commit_readback'][field]=value
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_truncated_or_mismatched_tree_rejected(self):
        for field,value in (('truncated',True),('truncated',0),('sha','0'*40),('api_url','bad')):
            evidence=copy.deepcopy(self.external);evidence['tree_readback'][field]=value
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_duplicate_or_unsafe_git_tree_entry_rejected(self):
        evidence=copy.deepcopy(self.external);evidence['tree_readback']['entries'].append(evidence['tree_readback']['entries'][0])
        with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)
        evidence=copy.deepcopy(self.external);evidence['tree_readback']['entries'][0]['path']='../escape'
        with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_all_runtime_git_blobs_checked_including_unchanged_files(self):
        for path in ('stage1/native_child_adapter.py','stage1/native_peer_identity.py',b.MANIFEST,b.VERIFIER):
            evidence=copy.deepcopy(self.external)
            next(x for x in evidence['tree_readback']['entries'] if x['path']==path)['sha']='0'*40
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_git_symlink_or_submodule_runtime_entry_rejected(self):
        for mode,kind in (('120000','blob'),('160000','commit'),('040000','tree')):
            evidence=copy.deepcopy(self.external)
            entry=next(x for x in evidence['tree_readback']['entries'] if x['path']=='stage1/native_child_adapter.py')
            entry.update(mode=mode,type=kind)
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_per_overlay_file_sha256_gitblob_and_ref_must_match(self):
        path='stage1/native_peer_identity.py'
        for field,value in (('content_sha256','0'*64),('git_blob_sha1','0'*40),('commit_sha','0'*40),('api_url','bad')):
            evidence=copy.deepcopy(self.external);evidence['file_readbacks'][path][field]=value
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_every_overlay_and_generated_manifest_requires_file_readback(self):
        for path in set(self.overlays)|{b.MANIFEST}:
            evidence=copy.deepcopy(self.external);del evidence['file_readbacks'][path]
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,evidence,self.commit,self.tree)

    def test_local_wrong_commit_tree_rejected(self):
        with mock.patch.object(b,'_git',side_effect=[b'commit\n',b'0'*40+b'\n']):
            with self.assertRaises(ValueError):b.verify_provenance(self.prepared,self.local,self.commit,self.tree)

    def test_failed_archive_verification_publishes_no_success_receipt(self):
        prepared=dict(self.prepared);prepared['freezer']=dict(prepared['freezer'])
        prepared['freezer']['verify']=mock.Mock(side_effect=ValueError('fixture verification failure'))
        with mock.patch.object(b,'prepare',return_value=prepared):
            with self.assertRaises(ValueError):self.build()
        self.assertTrue((self.root/'out/BUILD_FAILED.json').exists())
        self.assertFalse((self.root/'out/build-receipt.json').exists())
        self.assertFalse((self.root/'out/runtime-overlay-candidate.tar.gz').exists())

    def test_source_oversize_and_duplicate_json_rejected(self):
        path=self.root/'data';path.write_bytes(b'12345')
        with self.assertRaises(ValueError):b.read_regular(str(path),maximum=4)
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}'):
            with self.assertRaises(ValueError):b.load_json(raw)

    def test_nonstring_overlay_key_and_overlong_archive_name_rejected(self):
        with self.assertRaises(ValueError):b.prepare(str(FROZEN),{1:{},'stage1/x.py':{}})
        spec=self.overlays['stage1/fixture_overlay_helper.py']
        with self.assertRaises(ValueError):b.prepare(str(FROZEN),{'stage1/'+'x'*200+'.py':spec})

    def test_source_metadata_change_during_read_rejected_and_closed(self):
        path=self.root/'source';path.write_bytes(b'data')
        original=os.stat(str(path));names=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        values={name:getattr(original,name) for name in names};values['st_ctime_ns']+=1
        after=types.SimpleNamespace(**values)
        close=os.close
        with mock.patch.object(b.os,'fstat',side_effect=[original,after]),mock.patch.object(b.os,'close',wraps=close) as closed:
            with self.assertRaises(ValueError):b.read_regular(str(path))
            self.assertEqual(closed.call_count,1)

    def test_source_special_mode_rejected_without_reading(self):
        path=self.root/'source';path.write_bytes(b'data');original=os.stat(str(path))
        names=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
        values={name:getattr(original,name) for name in names};values['st_mode']|=0o4000
        with mock.patch.object(b.os,'fstat',return_value=types.SimpleNamespace(**values)),mock.patch.object(b.os,'read') as read:
            with self.assertRaises(ValueError):b.read_regular(str(path))
            read.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)

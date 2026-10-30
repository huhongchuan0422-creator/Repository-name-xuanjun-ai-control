"""Synthetic archives and network doubles; never Docker, real download or site I/O."""
import copy
import gzip
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import time
import unittest
import zipfile
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from scripts import community_fixed_4f_image_evidence as m
import test_community_image_build_entry as gates

def encoded(value):return json.dumps(value,sort_keys=True).encode()

def tar_bytes(files):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as t:
        for name,raw,mode in files:
            item=tarfile.TarInfo(name);item.mode=mode
            if isinstance(raw,tuple):
                item.type=tarfile.SYMTYPE if raw[0]=='symlink' else tarfile.LNKTYPE;item.linkname=raw[1];t.addfile(item)
            elif raw is None:item.type=tarfile.DIRTYPE;t.addfile(item)
            else:item.size=len(raw);t.addfile(item,io.BytesIO(raw))
    return out.getvalue()

def fixture(*,stamp=None,stamp_mode=0o444,env=None,tag=None,bad_blob=False,whiteout=False,wrong_file=False,ancestor=None):
    payload=b'SYNTHETIC PUBLIC SOURCE'
    tracked='app/scripts/community_reviewer_web_bridge.py'
    layer_files=[('app',None,0o755),(tracked,b'wrong' if wrong_file else payload,0o644),
        ('app/COMMUNITY_SOURCE_SHA',stamp if stamp is not None else (m.PRODUCT+'\n').encode(),stamp_mode)]
    if whiteout:layer_files.append(('app/.wh.scripts',b'',0o644))
    if ancestor is not None:layer_files.append(('app/scripts',ancestor,0o777))
    layer=tar_bytes(layer_files);layerhash=m.sha(layer);layerpath='blobs/sha256/'+layerhash
    config=encoded(dict(os='linux',architecture='amd64',rootfs=dict(type='layers',diff_ids=['sha256:'+layerhash]),
        config=dict(User='10001:1008',Entrypoint=['python','-B','-m','scripts.community_platform_host'],
          Env=env if env is not None else ['COMMUNITY_SOURCE_SHA='+m.PRODUCT],
          Labels={'org.opencontainers.image.revision':m.PRODUCT})))
    confighash=m.sha(config);configpath='blobs/sha256/'+confighash
    oci=encoded(dict(schemaVersion=2,config=dict(digest='sha256:'+confighash,size=len(config)),
        layers=[dict(digest='sha256:'+layerhash,size=len(layer))]))
    ocihash=m.sha(oci)
    index=encoded(dict(schemaVersion=2,manifests=[dict(digest='sha256:'+ocihash,size=len(oci))]))
    manifest=encoded([dict(Config=configpath,Layers=[layerpath],RepoTags=[tag or 'community-preview:'+m.PRODUCT])])
    docker=tar_bytes([('blobs',None,0o755),('blobs/sha256',None,0o755),
        (layerpath,layer+b'x' if bad_blob else layer,0o644),(configpath,config,0o644),
        ('blobs/sha256/'+ocihash,oci,0o644),('manifest.json',manifest,0o644),('index.json',index,0o644),
        ('oci-layout',encoded({'imageLayoutVersion':'1.0.0'}),0o644)])
    compressed=gzip.compress(docker,mtime=0)
    members={'community-image-id.txt':('sha256:'+confighash+'\n').encode(),
        'community-backend-image.tar.gz':compressed,'community-image-tests.log':b'SYNTHETIC TEST LOG\n',
        'community-backend-image.sha256':(m.sha(compressed)+'  community-backend-image.tar.gz\n').encode()}
    return members,{tracked:m.sha(payload)},docker

def zip_bytes(members):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,raw in members.items():
            item=zipfile.ZipInfo(name);item.external_attr=0o100644<<16;z.writestr(item,raw)
    return out.getvalue()

class Archives(unittest.TestCase):
    def inspect(self,*,change=None,**kwargs):
        members,pins,raw_tar=fixture(**kwargs)
        if change:change(members)
        raw=zip_bytes(members)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'outer.zip';p.write_bytes(raw)
            with patch.multiple(m,OUTER_BYTES=len(raw),OUTER_SHA=m.sha(raw),SOURCE_FILES=pins):
                return m.inspect_outer(p,root)
    def test_full_synthetic_outer_inner_oci_layers_and_source_stamp(self):
        reports,config,manifest=self.inspect()
        layout=reports['ACTUAL_DOCKER_ARCHIVE_LAYOUT.json']
        self.assertTrue(layout['all_oci_blob_path_hashes_verified'])
        self.assertEqual(layout['source_env'],m.PRODUCT)
        self.assertEqual(len(layout['source_stamp']),1)
        self.assertEqual(layout['source_stamp'][0]['mode'],0o444)
        self.assertEqual(m.sha(config),layout['image_id'].split(':')[1])
        self.assertEqual(json.loads(manifest)[0]['RepoTags'],['community-preview:'+m.PRODUCT])
    def test_actual_fixed_constants_are_not_operator_inputs(self):
        self.assertEqual(m.ARTIFACT,13002167810);self.assertEqual(m.IMAGE_RUN,41108321174)
        self.assertEqual(m.OUTER_BYTES,532467544);self.assertEqual(m.CHUNK,262144)
        self.assertEqual(m.OUTER_SHA,'e3cd59f1d12d3e1a5386e42c71b2e75f03749a6db7cb985a5758f3e1169d4f82')
        self.assertEqual(len(m.SOURCE_FILES),5)
    def test_corrupt_outer_rejected_before_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'outer';p.write_bytes(b'not original')
            with self.assertRaises(ValueError):m.inspect_outer(p,Path(tmp))
    def test_missing_extra_and_traversal_zip_members_rejected(self):
        for mode in ('missing','extra','traversal'):
            def change(d):
                if mode=='missing':d.pop('community-image-tests.log')
                else:d['../escape' if mode=='traversal' else 'unexpected']=b'x'
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.inspect(change=change)
    def test_wrong_gzip_hash_id_tag_and_source_rejected(self):
        with self.assertRaises(ValueError):self.inspect(change=lambda d:d.update({'community-backend-image.sha256':b'0'*64+b'  community-backend-image.tar.gz\n'}))
        with self.assertRaises(ValueError):self.inspect(change=lambda d:d.update({'community-image-id.txt':b'sha256:'+b'0'*64+b'\n'}))
        for args in [dict(tag='other'),dict(stamp=b'old\n'),dict(stamp_mode=0o644),
                     dict(env=['COMMUNITY_SOURCE_SHA=wrong']),dict(env=['COMMUNITY_SOURCE_SHA='+m.PRODUCT]*2),
                     dict(bad_blob=True),dict(whiteout=True),dict(wrong_file=True)]:
            with self.subTest(args=args),self.assertRaises(ValueError):self.inspect(**args)
    def test_protected_parent_rebinding_rejected_without_banning_unrelated_base_links(self):
        for ancestor in (b'file',('symlink','/tmp/other'),('hardlink','elsewhere')):
            with self.subTest(ancestor=ancestor),self.assertRaisesRegex(ValueError,'SOURCE_ANCESTOR_NOT_DIRECTORY'):
                self.inspect(ancestor=ancestor)
    def test_chunking_is_exact_even_with_short_reads(self):
        data=b'a'*(m.CHUNK*2+7)
        class Short(io.BytesIO):
            def read(self,n=-1):return super().read(min(n,17))
        result=m.copy_hash(Short(data),limit=len(data),chunks=True)
        self.assertEqual([x['bytes'] for x in result['chunks']],[m.CHUNK,m.CHUNK,7])
        self.assertEqual(result['sha256'],m.sha(data))
        self.assertEqual([x['offset'] for x in result['chunks']],[0,m.CHUNK,m.CHUNK*2])
        with self.assertRaises(ValueError):m.copy_hash(io.BytesIO(data),limit=len(data)-1)
    def test_duplicate_json_and_unsafe_path_denied(self):
        with self.assertRaises(ValueError):m.strict_json('{"a":1,"a":2}')
        for n in ('../a','/a','a/../b','a\\b'):
            with self.assertRaises(ValueError):m.safe_name(n)

class Metadata(unittest.TestCase):
    def setUp(self):
        self.run=dict(id=m.IMAGE_RUN,head_sha=m.IMAGE_CONTROL,head_branch=m.BRANCH,path=m.WORKFLOW,
            event='workflow_dispatch',status='completed',conclusion='success',
            repository={'full_name':m.REPO},head_repository={'full_name':m.REPO})
        self.jobs=dict(total_count=1,jobs=[dict(id=m.IMAGE_JOB,name='community-backend-image',run_id=m.IMAGE_RUN,
            head_sha=m.IMAGE_CONTROL,status='completed',conclusion='success')])
        self.artifacts=dict(total_count=1,artifacts=[dict(id=m.ARTIFACT,name='community-backend-image-candidate',
            expired=False,expires_at='2030-01-01T00:00:00Z',size_in_bytes=m.OUTER_BYTES,digest='sha256:'+m.OUTER_SHA,
            workflow_run=dict(id=m.IMAGE_RUN,head_sha=m.IMAGE_CONTROL,head_branch=m.BRANCH,
                repository_id=1413132159,head_repository_id=1413132159))])
    def test_exact_success_is_bytes_only_not_site_or_image_execution(self):
        report=m.provenance(self.run,self.jobs,self.artifacts)
        self.assertFalse(report['image_executed']);self.assertFalse(report['site_access'])
        self.assertEqual(report['product_source_sha'],m.PRODUCT)
    def test_failed_skipped_wrong_control_run_and_job_rejected(self):
        for key,value in [('head_sha',m.PRODUCT),('event','push'),('id',1),('conclusion','failure')]:
            run=dict(self.run,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):m.provenance(run,self.jobs,self.artifacts)
        for key,value in [('id',1),('head_sha',m.PRODUCT),('run_id',1),('conclusion','skipped'),('status','in_progress')]:
            jobs=copy.deepcopy(self.jobs);jobs['jobs'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.provenance(self.run,jobs,self.artifacts)
    def test_artifact_wrong_hash_size_expired_id_and_incomplete_page_rejected(self):
        for key,value in [('id',1),('expired',True),('size_in_bytes',1),('digest','sha256:'+'0'*64),('expires_at','2020-01-01T00:00:00Z')]:
            artifacts=copy.deepcopy(self.artifacts);artifacts['artifacts'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.provenance(self.run,self.jobs,artifacts)
        jobs=dict(self.jobs,total_count=2)
        with self.assertRaises(ValueError):m.provenance(self.run,jobs,self.artifacts)

class Network(unittest.TestCase):
    def response(self,raw,url):
        r=io.BytesIO(raw);r.status=200;r.geturl=lambda:url;return r
    def test_token_only_goes_to_exact_api_then_clean_signed_storage(self):
        location='https://fixture.blob.core.windows.net/image?sig=synthetic'
        redirect=HTTPError('https://api.github.com/',302,'redirect',{'Location':location},None)
        o=Mock();o.open.side_effect=[redirect,self.response(b'fixture',location)]
        with tempfile.TemporaryDirectory() as tmp,patch.object(m,'opener',return_value=o),patch.multiple(m,OUTER_BYTES=7,OUTER_SHA=m.sha(b'fixture')):
            report=m.download(Path(tmp)/'out','TEST_ONLY_TOKEN')
        calls=o.open.call_args_list;self.assertEqual(len(calls),2)
        first,second=calls[0].args[0],calls[1].args[0]
        self.assertEqual(first.full_url,'https://api.github.com/repos/'+m.REPO+'/actions/artifacts/13002167810/zip')
        self.assertEqual(first.get_header('Authorization'),'Bearer TEST_ONLY_TOKEN')
        self.assertIsNone(second.get_header('Authorization'))
        self.assertEqual(report['sha256'],m.sha(b'fixture'))
    def test_foreign_redirect_or_http_is_denied_without_second_request(self):
        for location in ['https://evil.invalid/x','http://fixture.blob.core.windows.net/x','https://u:p@fixture.blob.core.windows.net/x']:
            o=Mock();o.open.side_effect=HTTPError('https://api.github.com/',302,'redirect',{'Location':location},None)
            with patch.object(m,'opener',return_value=o),self.assertRaises(ValueError):m.download('unused','token')
            self.assertEqual(o.open.call_count,1)

class Workflow(unittest.TestCase):
    def setUp(self):
        self.workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/chatgpt-community-wechat-sp-offline.yml').read_text()
    def test_fixed_read_job_requires_scope_and_exact_branch_without_build(self):
        header=self.workflow.split('  community-fixed-image-evidence:\n',1)[1].split('    steps:',1)[0]
        expr=header.split('    if: ',1)[1].splitlines()[0]
        base={'github.event_name':'push','github.ref':'refs/heads/'+m.BRANCH,
              'github.event.head_commit.message':m.READ_MARKER+' '+m.SCOPE_MARKER}
        self.assertTrue(gates.condition(expr,base))
        for change in [{'github.event_name':'workflow_dispatch'},{'github.ref':'refs/heads/main'},
                       {'github.event.head_commit.message':m.READ_MARKER},{'github.event.head_commit.message':m.SCOPE_MARKER}]:
            self.assertFalse(gates.condition(expr,dict(base,**change)))
        self.assertIn('needs: test',header)
        job=self.workflow.split('  community-fixed-image-evidence:\n',1)[1].split('\n  community-backend-image:',1)[0]
        for forbidden in ('docker ', 'self-hosted','secrets.', 'actions: write', 'scp ', 'ssh '):self.assertNotIn(forbidden,job)
        gates.exact_readonly_permissions(self.workflow)
    def test_scope_actually_runs_this_test_before_evidence(self):
        step=self.workflow.split('      - name: Fixed existing image evidence affected scope (no image execution)\n',1)[1].split('      - name:',1)[0]
        self.assertIn('python -B -m unittest test_community_fixed_4f_image_evidence -v',step)
        self.assertIn(m.SCOPE_MARKER,step)
if __name__=='__main__':unittest.main()

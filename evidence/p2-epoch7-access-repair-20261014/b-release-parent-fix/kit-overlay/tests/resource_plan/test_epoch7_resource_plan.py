"""Actual local files and frozen serializers for all17 resource checkpoints.

Host ownership and named-UID ACL reads are mapped at this test boundary only.
Kernel ACL behavior has separate actual-xattr tests; no systemd/host effects run.
Source payloads and the identity renderer are the authenticated public runtime.
"""
import copy
import json
import os
import pwd
import grp
import pathlib
import shutil
import tempfile
import types
import unittest
from unittest import mock

import activation_control
import epoch7_delta as d
import epoch7_host_phases as h
import epoch7_resource_plan as p
import epoch7_resource_observer as r
import epoch7_exact_access as acl
from epoch7_recovery_sequence import PHASES
from epoch7_runtime_effects import JOURNALS,BOOT_UNITS
from test_epoch7_delta import fixture
from test_epoch7_acceptance_rows import fixture as source_fixture


class SeventeenCheckpointTests(unittest.TestCase):
    def setUp(self):
        base=str(pathlib.Path(__import__('epoch7_protected_fs').__file__).resolve().parent/'fixtures')
        self.root=tempfile.mkdtemp(prefix='resource17-',dir=base);os.chmod(self.root,0o700)
        self.raw={};self.acls={};self.snapshot,self.candidate=fixture()
        self.compiled,identities,manifest_raw,hashes,facts=source_fixture()
        self.manifest_raw=manifest_raw;runtime=pathlib.Path(activation_control.__file__).resolve().parent.parent
        self.payloads={path:(runtime/path).read_bytes() for path in json.loads(manifest_raw.decode())['files']}
        self.installer=(runtime/'scripts/uk-integration-install.py').read_bytes()
        namespace={};exec(compile(self.installer,'<pinned-test-renderer>','exec'),namespace)
        self.rendered={path:namespace['render_identity_bytes'](path,raw,h.MANIFEST,json.loads(manifest_raw.decode()))
                       for path,raw in self.payloads.items()}
        self.identity_payloads=identities;self.binding={'review_id':7000000001,'approval_body_sha256':'a'*64}
        self.context={'context_sha256':'b'*64,'snapshot_sha256':'c'*64}
        self.authority=types.SimpleNamespace(receipt=lambda:True,binding=self.binding,context=self.context,
            verifier=types.SimpleNamespace(wanted={'recovery_plan_sha256':'d'*64}))
        self.oldprofile=h.packed({'agents':{'entries':{'developer':{},'platform-engineer':{}}}})
        newprofile=json.loads(self.oldprofile.decode())
        from p2_sandbox_profile import IMAGE,policy
        for name,access in (('developer','rw'),('platform-engineer','ro')):
            newprofile['agents']['entries'][name]['sandbox']={'mode':'all','workspaceAccess':access,'scope':'agent',
                'docker':{'image':IMAGE,'user':'1002:1002','network':'none','readOnlyRoot':True,
                          'capDrop':['ALL'],'binds':[],'tmpfs':[]}}
        policy(json.loads(self.oldprofile.decode()),newprofile);self.profile_candidate=h.packed(newprofile)
        self.native_before=b'{"fixture":"retained native identity"}\n';self.native_after=b'{"fixture":"new native identity"}\n'
        config={'release_sha256':d.OLD_MANIFEST,'transaction_id':d.TX,'root':h.snap.TLS}
        tls={'state':h.READY,'config':config,'certificate_sha256':d.digest('fixture certificate'),
             'fingerprint':d.digest('fixture tree'),'history':{'retained_ready':True}}
        self.tls_before=h.packed(tls);self.compiled['tls_config_bytes']=h.packed(dict(config,release_sha256=h.MANIFEST))
        self.compiled['rendered_targets']['/etc/xuanjun-development/tls-renewal.json']=self.compiled['tls_config_bytes']
        self.snapshot['tls'].update(journal_sha256=h.sha(self.tls_before),certificate_sha256=tls['certificate_sha256'],
            tree_fingerprint_sha256=tls['fingerprint'],config_identity_sha256=d.digest({k:v for k,v in config.items() if k!='release_sha256'}))
        self.compiled['activation_proposal']=self.candidate['activation']
        self.compiled['runtime'].update(sandbox_policy={'sha256':h.sha(self.profile_candidate)},
            plugin={'binding_file':'/etc/xuanjun-development/p2-native-controller.binding.json','binding_sha256':'e'*64})
        self.files={}
        for path in sorted(d.TARGETS):
            if path in d.OWNER_MASKS:
                self.mask(path);info=h.fs.metadata(os.lstat(self.root+path))
                self.snapshot['targets'][path]=dict(info,kind='MASK',link='/dev/null',uid=0,gid=0)
            else:
                mode=0o640 if path==p.CLIENT else 0o644
                self.snapshot['targets'][path]=self.file(path,('old fixture '+path).encode(),mode)
            self.candidate['targets'][path]={'kind':'FILE','sha256':h.sha(self.compiled['rendered_targets'][path]),'uid':0,'gid':0,
                'mode':0o640 if path==p.CLIENT else 0o644}
        for row in self.compiled['runtime']['provisioning']:
            row.update(owner_uid=0,group_gid=0,mode=self.candidate['targets'][row['target']]['mode'],
                       rendered_sha256=self.candidate['targets'][row['target']]['sha256'])
        # Preserve every declared old receipt, and create only the freshly owned
        # inner attempt that necessarily precedes the first outer checkpoint.
        for name in self.snapshot['receipts']:
            raw=self.tls_before if name=='tls-lifecycle.json' else h.packed({'fixture':name})
            self.files[h.fs.TRANSACTION+'/'+name]=self.file(h.fs.TRANSACTION+'/'+name,raw,0o600)
            self.snapshot['receipts'][name]=h.sha(raw)
        self.inner('epoch7-recovery-execution.json',{'stage':'ADMITTED'})
        self.files[h.snap.NATIVE]=self.file(h.snap.NATIVE,self.native_before,0o644)
        self.files[h.snap.PROFILE]=self.file(h.snap.PROFILE,self.oldprofile,0o600,1002,1002)
        self.snapshot['sandbox']['profile_sha256']=h.sha(self.oldprofile)
        self.files[h.TLS_JOURNAL]=self.file(h.TLS_JOURNAL,self.tls_before,0o600)
        self.mkdir(d.GENERATION,0o750)
        self.snapshot['generation']=dict(self.directory(d.GENERATION),path=d.GENERATION,kind='DIRECTORY',uid=1003,gid=1006)
        dbrow=self.file(d.DB,b'fixture canonical database',0o600)
        self.files[d.DB]=dbrow;self.snapshot['database'].update({k:dbrow[k] for k in ('uid','gid','mode','dev','ino','nlink','sha256')})
        databases={d.DB:{'file':dbrow,'sidecars':{}}}
        for path in h.snap.DATABASES:
            if path!=d.DB:databases[path]={'file':self.file(path,b'fixture retained database',0o600),'sidecars':{}}
        base=next(path for path in h.snap.DATABASES if path!=d.DB)
        databases[base]['sidecars']['-wal']=self.file(base+'-wal',b'',0o600)
        databases[base]['sidecars']['-shm']=self.file(base+'-shm',b'x'*32768,0o600)
        self.mkdir('/opt/xuanjun-control-releases',0o750)
        self.legacy={'units':{}}
        for unit in ('xuanjun-uk-openclaw.service','xuanjun-uk-stage1-minimal.service'):
            path='/etc/systemd/system/'+unit;raw=('[Unit]\nDescription=fixture '+unit+'\n').encode()
            self.legacy['units'][unit]={'path':path,'uid':0,'gid':0,'mode':0o644,'sha256':h.sha(raw)}
            self.raw['gateway:'+unit]=raw;self.mask(path)
        self.additions=[]
        for path,raw in identities.items():
            self.mkdir(os.path.dirname(path));self.additions.append({'path':path,'after':{'kind':'FILE','uid':0,'gid':0,'mode':0o644,'sha256':h.sha(raw)}})
        self.mkdir(os.path.dirname(h.snap.PLUGIN_PATH))
        oldroot='/opt/xuanjun-control-releases/integration-'+d.OLD_MANIFEST[:16]
        oldmanifest=b'{"fixture":"historical manifest"}\n'
        self.file(oldroot+'/INTEGRATION_MANIFEST.json',oldmanifest,0o444)
        oldfile=self.file(oldroot+'/old.py',b'# old immutable source\n',0o444)
        oldcache=self.file(oldroot+'/__pycache__/old.cpython-36.pyc',b'fixture retained pyc',0o444)
        # Genuine frozen activation serializer and durable append/hash chain.
        self.mkdir(os.path.dirname(h.snap.ACTIVE))
        lock=self.file(h.snap.ACTIVATION_LOCK,b'',0o644)
        actual=dict(lock,uid=os.geteuid(),gid=os.getegid())
        self.store=h.BoundedActivationStore(actual,self.root)
        for epoch in range(1,8):self.store._append(dict(self.snapshot['activation'],epoch=epoch),self.store._journal(),{'fixture':True})
        self.store._write_descriptor(self.snapshot['activation'])
        for path in (h.snap.ACTIVE,h.snap.EPOCHS):self.files[path]=self.record(path)
        self.snapshot['epoch_journal_sha256']=self.files[h.snap.EPOCHS]['sha256']
        executable=self.file('/usr/bin/fixture-tool',b'\x7fELFfixture',0o755)
        self.exes={'/usr/bin/fixture-tool':p.file_spec('/usr/bin/fixture-tool',executable)}
        import reviewed_publisher
        rows=[]
        for index,target in enumerate(sorted(h.snap.PUBLISHERS)):
            self.file(target+'/config',b'fixture publisher auth/source bytes',0o600)
            row=self.directory(target)
            rows.append({'target':target,'stage':os.path.dirname(target)+'/.p2-publisher-fixture%d'%index,
                'state':'PUBLISHED','dev':row['dev'],'ino':row['ino'],
                'fingerprint':reviewed_publisher.fingerprint(self.root+target,owner_uid=os.geteuid(),owner_gid=os.getegid())})
        self.publisher_raw=h.packed({'schema':1,'directories':rows})
        self.files[h.fs.TRANSACTION+'/publisher-bootstrap.json']=self.file(h.fs.TRANSACTION+'/publisher-bootstrap.json',self.publisher_raw)
        self.snapshot['receipts']['publisher-bootstrap.json']=h.sha(self.publisher_raw)
        retained={'files':self.files,'native_components':{'components':{}},'prerequisites':{'binaries':{},
            'directories':{}},
            'release_evidence':{oldroot:{'manifest_sha256':h.sha(oldmanifest),'files':{'old.py':oldfile},
                'caches':{'__pycache__/old.cpython-36.pyc':{'file':oldcache}}}},'database_sets':databases,
            'tls':{'file_metadata':{}}}
        self.support={'retained':retained};self.snapshot['retained_resource_sha256']=d.digest(retained)
        self.fresh_parent=self.directory('/opt/xuanjun-control-releases')
        self.security=p.build_access_rows(self.support,self.compiled,release_parent=self.fresh_parent)
        self.policy={'directories':{},'scheduler_files':{}}
        for directory,dirs,files in os.walk(self.root):
            logical=directory[len(self.root):] or '/';row=self.directory(logical)
            self.policy['directories'][logical]={k:row[k] for k in ('uid','gid','mode')}
        account=pwd.getpwuid(os.geteuid());group=grp.getgrgid(os.getegid())
        self.nss={'path':'/etc/passwd','kind':'NSS_BINDINGS','prerequisites':{},
            'accounts':{account.pw_name:{'uid':account.pw_uid,'primary_gid':account.pw_gid,
                'global_group_gids':sorted(set(os.getgrouplist(account.pw_name,account.pw_gid)))}},
            'group_ids':{group.gr_name:group.gr_gid},'nss_by_primary':{account.pw_name:{str(account.pw_gid):
                sorted(set(os.getgrouplist(account.pw_name,account.pw_gid)))}}}
        self.views=p.build_resource_views(self.snapshot,self.support,self.compiled,self.additions,self.security,
            self.manifest_raw,self.payloads,self.installer,self.native_after,self.tls_before,self.profile_candidate,
            self.legacy,release_parent=self.fresh_parent,executable_specs=self.exes,policy=self.policy,publisher_journal_raw=self.publisher_raw,nss_projection=self.nss)
        self.dirs=p.build_resource_directories(self.policy,self.views)
    def tearDown(self):
        for root,dirs,files in os.walk(self.root):os.chmod(root,0o700)
        shutil.rmtree(self.root)
    def mkdir(self,path,mode=0o700):
        os.makedirs(self.root+path,mode=0o700,exist_ok=True);os.chmod(self.root+path,mode)
    def file(self,path,raw,mode=0o600,uid=0,gid=0):
        self.mkdir(os.path.dirname(path)) if not os.path.isdir(self.root+os.path.dirname(path)) else None
        if os.path.islink(self.root+path):os.unlink(self.root+path)
        with open(self.root+path,'wb') as stream:stream.write(raw)
        os.chmod(self.root+path,mode);self.raw[path]=raw
        row=self.record(path);row.update(uid=uid,gid=gid);return row
    def record(self,path):
        return dict(h.fs.metadata(os.lstat(self.root+path)),kind='FILE',sha256=h.sha(pathlib.Path(self.root+path).read_bytes()),uid=0,gid=0)
    def directory(self,path):
        row=h.fs.metadata(os.lstat(self.root+path));return dict(row,uid=0,gid=0,access_acl=acl.decode_acl(None,row['mode']),default_acl='')
    def mask(self,path):
        self.mkdir(os.path.dirname(path)) if not os.path.isdir(self.root+os.path.dirname(path)) else None
        if os.path.lexists(self.root+path):os.unlink(self.root+path)
        os.symlink('/dev/null',self.root+path)
    def inner(self,name,state):
        return self.file(h.fs.TRANSACTION+'/'+name,h.packed({'schema':1,'name':name,'transaction_id':d.TX,
            'binding':self.binding,'state':state}),0o600)
    def runtime_journal(self,name,**fields):
        self.file(h.fs.TRANSACTION+'/'+name,h.packed(dict(fields,schema=1,context_sha256=self.context['context_sha256'])),0o600)
    def mapped(self,spec):
        value=copy.deepcopy(spec)
        if 'uid' in value:value['uid']=os.geteuid()
        if 'gid' in value:value['gid']=os.getegid()
        return value
    def check_view(self,index):
        directories={path:[self.mapped(row) for row in rows] for path,rows in self.dirs.items()}
        reader=r.ResourceReader(directories,self.authority,self.root);reader.start()
        def attr(fd,name):
            if name==acl.DEFAULT:return None
            logical=os.readlink('/proc/self/fd/'+str(fd))[len(self.root):] or '/'
            value=self.acls.get(logical)
            return acl.encode_acl(value) if value is not None else None
        with mock.patch.object(r,'get_attr',side_effect=attr):
            for section,rows in sorted(self.views[index].items()):
                for spec in rows:
                    try:self.assertEqual(reader.observe(self.mapped(spec)),self.mapped(spec))
                    except Exception as error:raise AssertionError('checkpoint%d section%s path%s: %s'%(index,section,spec['path'],error))
    def mutate(self,phase):
        tx=h.fs.TRANSACTION
        if phase=='stage_exact_release':
            for path,raw in self.rendered.items():
                mode=0o555 if path in ('scripts/xj-root-broker-client','scripts/uk-owner-workbench-config.py') else 0o444
                self.file(p.RELEASE+'/'+path,raw,mode)
            self.file(p.RELEASE+'/INTEGRATION_MANIFEST.json',self.manifest_raw,0o444)
            for root,dirs,files in os.walk(self.root+p.RELEASE):os.chmod(root,0o555)
        elif phase=='rebind_prepared_epoch':
            before=self.snapshot['activation'];after=self.candidate['activation']
            proof={'controller_transition_sha256':d.digest(d.controller_transition(before,after)),
                'approval_body_sha256':self.binding['approval_body_sha256'],'snapshot_sha256':self.context['snapshot_sha256'],
                'recovery_plan_sha256':'d'*64,'old_descriptor_sha256':self.store.head(before),'new_descriptor_sha256':self.store.head(after),
                'all_writers_excluded':True,'install_lock_held':True,'retained_resources_verified':True}
            h.rebind_prepared_epoch7(self.store,before,after,proof)
            self.file(tx+'/epoch7-prior-native-binding.json',self.native_before)
            self.file(h.snap.NATIVE,self.native_after,0o644);self.file(h.TLS_CANDIDATE,self.compiled['tls_config_bytes'])
        elif phase=='quiesce_exact_epoch':
            proof={k:True for k in ('identity_verified','coordinator_inactive','parent_unit_inactive','cgroups_empty','restart_inhibited')}
            self.store.transition('PREPARED','QUIESCED',8,self.candidate['activation']['instance'],proof)
        elif phase=='replace_retained_targets':
            for path,old in self.snapshot['targets'].items():
                backup=self.raw[path] if old['kind']=='FILE' else d.canonical(old)
                self.file(tx+'/epoch7-target-before-'+h.sha(path.encode())+'.private',backup)
                self.file(path,self.compiled['rendered_targets'][path],self.candidate['targets'][path]['mode'])
            self.inner('epoch8-runtime-provisioning.json',{'stage':'TARGET_DELTA_COMPLETE'})
        elif phase=='publish_reviewed_identities':
            for path,raw in self.identity_payloads.items():self.file(path,raw,0o644)
            for name in ('epoch7-owner-identity-publication.json','epoch7-server-identity-publication.json'):
                self.inner(name,{'stage':'ADDITIVE_PUBLICATION_DONE'})
        elif phase=='change_generation_access':
            os.chmod(self.root+d.GENERATION,0o700);self.inner('epoch7-generation-access.json',{'stage':'GENERATION_ACCESS_DONE'})
        elif phase=='apply_reviewed_access':
            for row in self.security:self.acls[row['path']]=row['proposal']['after_acl']
        elif phase=='rebind_tls_metadata_only':
            self.file(tx+'/epoch7-prior-tls-lifecycle.json',self.tls_before)
            self.file(h.TLS_JOURNAL,h.tls_metadata_candidate(self.tls_before,self.compiled['tls_config_bytes'],self.snapshot['tls']))
        elif phase=='apply_fresh_sandbox':
            self.file(h.snap.PROFILE,self.profile_candidate,0o600)
            self.file(tx+'/'+JOURNALS[1],self.oldprofile);self.file(tx+'/'+JOURNALS[2],self.profile_candidate)
            self.runtime_journal(JOURNALS[0],state='APPLIED',original_sha256=h.sha(self.oldprofile),candidate_sha256=h.sha(self.profile_candidate))
        elif phase=='install_verified_plugin':
            profile=h.decode(self.profile_candidate);plugin=self.compiled['runtime']['plugin']
            profile['plugins']={'entries':{'xuanjun-p2-native-controller':{'enabled':True,'config':{'bindingFile':plugin['binding_file'],'bindingSha256':plugin['binding_sha256']}}}}
            self.file(h.snap.PROFILE,h.packed(profile),0o600)
            for path,raw in self.rendered.items():
                if path.startswith('plugins/p2-native-controller/'):
                    self.file(h.snap.PLUGIN_PATH+'/'+path[len('plugins/p2-native-controller/'):],raw,0o444)
            self.runtime_journal(JOURNALS[0],state='CLI_CAPTURED',original_sha256=h.sha(self.oldprofile),candidate_sha256=h.sha(self.profile_candidate))
            self.runtime_journal(JOURNALS[3],state='INSTALLED',previous='ABSENT')
        elif phase=='reopen_existing_database':self.runtime_journal('ledger-access.json',state='REOPENED')
        elif phase=='activate_exact_epoch':self.store.transition('QUIESCED','ACTIVE',8,self.candidate['activation']['instance'],{'database_reopened':True})
        elif phase=='activate_new_services':
            row=self.legacy['units']['xuanjun-uk-openclaw.service']
            self.file(row['path'],self.raw['gateway:xuanjun-uk-openclaw.service'],0o644)
            self.runtime_journal('runtime-boot.json',state='ENABLED',units=list(BOOT_UNITS),successful_commands={})
    def test_all17_views_match_actual_bytes_and_activation_chain(self):
        self.check_view(0)
        for index,phase in enumerate(PHASES,1):
            self.mutate(phase);self.check_view(index)
    def test_exact_public107_source_renderer_and_extra_payload_rejection(self):
        self.assertEqual(len(self.rendered),107)
        self.assertEqual(p.rendered_release_hashes(self.manifest_raw,self.payloads,self.installer),{k:h.sha(v) for k,v in self.rendered.items()})
        bad=dict(self.payloads);bad['unexpected.pyc']=b'cache'
        with self.assertRaises(ValueError):p.rendered_release_hashes(self.manifest_raw,bad,self.installer)
    def test_future_runtime_review_id_never_enters_compiled_specs(self):
        encoded=d.canonical(self.views)
        self.assertNotIn(b'7000000001',encoded);self.assertNotIn(self.context['context_sha256'].encode(),encoded)
        self.assertEqual(len(self.views),17)
        self.assertEqual(self.views[15]['boot'],self.views[16]['boot'])
    def test_source_sidecar_and_command_bytes_have_fixed_coverage(self):
        for view in self.views:
            historical={row['path']:row for row in view['historical']}
            self.assertIn('/usr/bin/fixture-tool',historical)
            for base in h.snap.DATABASES:
                if base!=d.DB:
                    for suffix in ('-wal','-shm','-journal'):self.assertIn(base+suffix,historical)

    def advance(self,phase):
        for name in PHASES:
            self.mutate(name)
            if name==phase:return PHASES.index(name)+1
    def test_forged_actual_append_proof_rejects_without_future_raw_pin(self):
        index=self.advance('rebind_prepared_epoch')
        path=self.root+h.snap.EPOCHS;lines=pathlib.Path(path).read_bytes().splitlines()
        row=h.decode(lines[-1]);row['proof']['controller_transition_sha256']='f'*64
        pathlib.Path(path).write_bytes(b'\n'.join(lines[:-1]+[d.canonical(row)])+b'\n')
        with self.assertRaisesRegex(AssertionError,'EPOCH_REVIEW_BINDING'):self.check_view(index)
    def test_unknown_cli_profile_mutation_refuses_after_capture(self):
        index=self.advance('install_verified_plugin')
        value=h.decode(pathlib.Path(self.root+h.snap.PROFILE).read_bytes());value['unsafe_extra']=True
        self.file(h.snap.PROFILE,h.packed(value),0o600)
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(index)
    def test_untracked_plugin_payload_and_new_release_cache_refuse(self):
        index=self.advance('install_verified_plugin')
        self.file(h.snap.PLUGIN_PATH+'/unexpected.pyc',b'not in manifest',0o444)
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(index)
        os.unlink(self.root+h.snap.PLUGIN_PATH+'/unexpected.pyc')
        os.chmod(self.root+p.RELEASE,0o755)
        self.file(p.RELEASE+'/unexpected.pyc',b'not in manifest',0o444)
        os.chmod(self.root+p.RELEASE,0o555)
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(index)
    def test_private_generated_journal_mode_cannot_broaden(self):
        index=self.advance('reopen_existing_database')
        os.chmod(self.root+h.fs.TRANSACTION+'/ledger-access.json',0o644)
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(index)
    def test_exact_acl_transition_cannot_gain_another_identity(self):
        index=self.advance('apply_reviewed_access')
        self.acls[p.CLIENT]=self.acls[p.CLIENT].replace('user:1003:r--','user:1003:rw-')
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(index)

    def test_publisher_content_change_or_new_scheduler_file_refuses(self):
        target=next(iter(h.snap.PUBLISHERS));self.file(target+'/config',b'changed source or auth',0o600)
        with self.assertRaisesRegex(AssertionError,'SPEC_DRIFT'):self.check_view(0)
        self.file(target+'/config',b'fixture publisher auth/source bytes',0o600)
        # The full fingerprint includes timestamps, so restore a separately
        # created fixture before testing unrelated scheduler appearance.
    def test_scheduler_appearance_is_detected_after_active(self):
        index=self.advance('activate_new_services')
        self.file('/etc/cron.d/unreviewed',b'* * * * * root unsafe\n',0o644)
        with self.assertRaisesRegex(AssertionError,'SCHEDULER_DRIFT'):self.check_view(index)
    def test_nss_drift_is_rejected_by_every_checkpoint(self):
        name=next(iter(self.nss['accounts']));account=pwd.getpwnam(name)
        changed=types.SimpleNamespace(pw_uid=account.pw_uid+1,pw_gid=account.pw_gid)
        with mock.patch.object(r.pwd,'getpwnam',return_value=changed):
            with self.assertRaisesRegex(AssertionError,'NSS_ACCOUNT_DRIFT'):self.check_view(0)

if __name__=='__main__':unittest.main()

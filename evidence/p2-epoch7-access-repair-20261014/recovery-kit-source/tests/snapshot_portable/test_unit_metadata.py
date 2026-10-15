"""Finite unit metadata fixtures; no UK reads, NSS or commands."""
import contextlib
import copy
import pathlib
import stat
import sys
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import epoch7_snapshot as c
import epoch7_delta as d
import snapshot_io as s
import unit_metadata as u
from test_probe_metadata import Fake as ProbeFake,packed,h
from test_snapshot import native_transition_fixture,native_pin_context

PREFIXES=('/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system')
NODE='/home/xuanjun_dev/.nvm/versions/node/v22.16.0/bin/node'
ENTRY='/home/xuanjun_dev/.openclaw/lib/openclaw.mjs'
SECRET='fixture-secret-never-returned'

class Fake(ProbeFake):
    def __init__(self):
        super(Fake,self).__init__()
        self.native={'gatewayIdentity':{'user':'xuanjun_dev','exe':NODE,'sha256':h('node'),
            'cgroup':'/system.slice/'+u.GATEWAY}}
        original=c.decode(native_transition_fixture()[2]);original['gatewayIdentity']=self.native['gatewayIdentity']
        self.native_raws=native_transition_fixture(original)
        self.native=c.decode(self.native_raws[0])
        for path,raw in zip((c.NATIVE,c.NATIVE_PRIOR,c.NATIVE_ORIGINAL,c.NATIVE_ATTEMPT),self.native_raws):
            self.add(path,raw,mode=0o644 if path==c.NATIVE else 0o600)
        self.backup=c.TRANSACTION+'/'+u.GATEWAY+'.backup'
        self.add(self.backup,('[Service]\nType=simple\nUser=xuanjun_dev\nGroup=xuanjun_dev\n'
            'SupplementaryGroups=docker\nEnvironment=TOKEN='+SECRET+'\nExecStart='+u.LAUNCHER+' gateway --port 18789\n').encode())
        self.bind_backup()
        self.add(u.LAUNCHER,('#!/bin/bash\nset -e\nexport TOKEN='+SECRET+'\nexec '+NODE+' '+ENTRY+' "$@"\n').encode(),uid=1002,gid=1002,mode=0o755)
        self.add(ENTRY,b'fixture entry bytes never execute or return',uid=1002,gid=1002,mode=0o644)
        self.add(u.NGINX_CONFIG,b'user nginx;\nworker_processes auto;\n',mode=0o644)
        self.bind_nginx()
        dispatcher='/etc/systemd/system/xuanjun-development-dispatcher.service'
        self.add(dispatcher,b'[Service]\nEnvironment=LANG=C\nExecStart=/usr/bin/python3 -B /fixed/dispatcher.py\n',mode=0o644)
        receipt=c.decode(self.files[u.PROVISION]);pin=next(row for row in receipt['targets'] if row['target']==dispatcher)
        pin['rendered_sha256']=c.sha(self.files[dispatcher]);self.add(u.PROVISION,packed(receipt))
        self.dropins={unit:{prefix+'/'+unit+'.d':{'present':False,'files':{}} for prefix in PREFIXES} for unit in u.UNITS}
        self.unit_accounts={'accounts':{'xuanjun-dispatcher':{'uid':1003,'primary_gid':1003,'global_group_gids':[1003]}},
            'named_groups':{'xuanjun-control-db':1006,'xuanjun-dispatcher':1003,'nginx':997},
            'nss_by_primary':{'xuanjun-dispatcher':{'1003':[1003],'1006':[1006]}},
            'unit_pairs':[],'unsupported':{}}
    def bind_backup(self):
        receipt={'schema':1,'units':{u.GATEWAY:{'path':'/etc/systemd/system/'+u.GATEWAY,'backup':self.backup,
            'sha256':c.sha(self.files[self.backup]),'uid':0,'gid':0,'mode':0o644,'was_active':True},
            'xuanjun-uk-stage1-minimal.service':{}}}
        self.add(c.TRANSACTION+'/legacy-units.json',packed(receipt))
    def bind_nginx(self):
        receipt=c.decode(self.files[u.PROVISION]);pin=next(row for row in receipt['targets'] if row['target']==u.NGINX_CONFIG)
        pin['rendered_sha256']=c.sha(self.files[u.NGINX_CONFIG]);self.add(u.PROVISION,packed(receipt))
    def boot_links(self):return {'units':sorted((u.GATEWAY,'xuanjun-uk-owner-callback.service','xuanjun-uk-owner-dashboard.service')),'roots':{root:{'present':False,'directories':{},'links':[]} for root in u.BOOT_ROOTS},'unsupported_roots':[],'restored_enablement':'NOT_INFERRED','runtime_alias_semantics':'REQUIRES_SYSTEMD239_REVIEW'}
    def dispatcher_manager_path(self):return {'command':'git','path_environment':'/usr/bin','entries':[{'directory':'/usr/bin','uid':0,'gid':0,'mode':0o755,'dev':1,'ino':2,'git':{'path':'/usr/bin/git','sha256':h('git'),'dev':1,'ino':3}}],'provenance':{'source':'SYSTEM_MANAGER_CHILD_ENVIRONMENT','systemctl_sha256':h('systemctl'),'manager_sha256':h('manager'),'upstream_version':'239','distro_matching_build':'NOT_VERIFIED'}}
    def unit_nss(self):return copy.deepcopy(self.unit_accounts)
    def python_reference(self):return self.executable_reference('/usr/bin/python3')
    def executable_reference(self,path):
        target='/usr/bin/python3.6' if path=='/usr/bin/python3' else path
        return {'reference_path':path,'links':[],'final':{'path':target,'sha256':h(target),'format':'ELF',
            'metadata':{'uid':0,'gid':0,'mode':0o755,'nlink':1}}}
    def online_cpus(self):return 2
    def unit_dropins(self,units):return copy.deepcopy(self.dropins)

class UnitFactsTests(unittest.TestCase):
    def setUp(self):self.io=Fake()
    def collect(self):
        with native_pin_context(self.io.native_raws):return u.collect_unit_facts(self.io)
    def evidence(self,r,name):return r['sections'][name]['evidence']
    def test_native_completed_transition_is_measured_not_admitted(self):
        report=self.collect();proof=self.evidence(report,'native_gateway')['native_binding_transition']
        self.assertEqual(proof['kind'],'EPOCH5_NATIVE_REBIND_COMPLETED')
        self.assertEqual(proof['after_sha256'],c.sha(self.io.files[c.NATIVE]))
        self.assertEqual(proof['before_release_sha256'],c.RETAINED_NATIVE_RELEASE)
        self.assertEqual(proof['after_release_sha256'],d.OLD_MANIFEST)
        self.assertEqual(report['install_admission'],'NOT_GRANTED')
    def test_native_all_three_archives_are_read_at_fixed_bounds(self):
        self.collect()
        for path,bound in ((c.NATIVE_PRIOR,65536),(c.NATIVE_ORIGINAL,65536),(c.NATIVE_ATTEMPT,1048576)):
            self.assertEqual(self.io.reads.count((path,bound)),2)
    def test_native_archive_authority_must_remain_private(self):
        for path in (c.NATIVE_PRIOR,c.NATIVE_ORIGINAL,c.NATIVE_ATTEMPT):
            self.io=Fake();self.io.metadata[path]['mode']=0o644
            self.assertEqual(self.collect()['sections']['native_gateway']['reason'],'UNIT_NATIVE_RECEIPT_AUTHORITY')
    def test_native_current_mode_must_remain_exact(self):
        self.io.metadata[c.NATIVE]['mode']=0o600
        self.assertEqual(self.collect()['sections']['native_gateway']['reason'],'UNIT_NATIVE_CURRENT_AUTHORITY')
    def test_native_wrong_owned_journal_is_unknown(self):
        raw=self.io.files[c.NATIVE_ATTEMPT]+b' ';self.io.add(c.NATIVE_ATTEMPT,raw)
        self.assertEqual(self.collect()['sections']['native_gateway']['reason'],'NATIVE_OWNED_ATTEMPT_PIN')
    def test_native_missing_archive_is_unknown_not_old_pin_fallback(self):
        del self.io.files[c.NATIVE_PRIOR]
        self.assertIn('native_gateway',self.collect()['unsupported_sections'])
    def test_group_writable_home_ancestors_still_rejected(self):
        import observe_epoch7 as observe
        for path in ('/home/xuanjun_dev/.openclaw/bin','/home/xuanjun_dev/.openclaw/tools'):
            row=types.SimpleNamespace(st_mode=stat.S_IFDIR|0o775,st_uid=1002,st_gid=1002)
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_AUTHORITY'):
                observe.authority(path,row)
    def test_complete_finite_sections(self):
        r=self.collect();self.assertEqual(r['state'],'COMPLETE_UNREVIEWED');self.assertEqual(r['unsupported_sections'],[])
        self.assertEqual(set(r['sections']),{'unit_nss','python_reference','native_gateway','legacy_gateway','launcher',
            'nginx_binary','runuser_binary','nginx_config','online_cpus','dropins','boot_links','command_resolutions'})
        self.assertEqual(r['install_admission'],'NOT_GRANTED');self.assertEqual(r['source_execution'],'NOT_PERFORMED')
    def test_no_raw_source_environment_or_future_argv(self):
        r=self.collect();raw=packed(r)
        for forbidden in (SECRET.encode(),b'fixture entry bytes',b'export TOKEN=',b'Environment='):
            self.assertNotIn(forbidden,raw)
        self.assertEqual(self.evidence(r,'launcher')['recipe']['environment_names'],['TOKEN'])
        self.assertEqual(r['future_argv_hashes'],'NOT_INFERRED')
    def test_startup_closure_always_explicit_unverified_gate(self):
        r=self.collect();self.assertEqual(r['source_closure'],'NOT_VERIFIED')
        recipes=r['startup_recipes'];openclaw=recipes['openclaw'];nginx=recipes['nginx']
        self.assertEqual(openclaw['topology_state'],'ISOLATED_STARTUP_VERIFICATION_REQUIRED')
        self.assertEqual(len(openclaw['missing_semantics']),6)
        self.assertEqual(openclaw['launcher_sha256'],c.sha(self.io.files[u.LAUNCHER]))
        self.assertEqual(openclaw['literal_unit_argv'],[[u.LAUNCHER,'gateway','--port','18789']])
        self.assertEqual(nginx['topology_state'],'OFFICIAL_MATCHING_SOURCE_REVIEW_REQUIRED')
        self.assertEqual(nginx['online_cpu_count'],2)
        self.assertEqual(nginx['installed_version_and_build_provenance']['state'],'UNKNOWN')
    def test_missing_metadata_does_not_invent_recipe_hash(self):
        del self.io.files[u.LAUNCHER];r=self.collect()
        self.assertIsNone(r['startup_recipes']['openclaw']['launcher_sha256'])
        self.assertIsNone(r['startup_recipes']['openclaw']['entry_script_sha256'])
        self.assertEqual(r['source_closure'],'NOT_VERIFIED')
    def test_unsupported_launcher_retains_measured_hash_without_source(self):
        self.io.add(u.LAUNCHER,b'#!/usr/bin/env node\nfixture unsupported JS launcher\n',uid=1002,gid=1002,mode=0o755)
        r=self.collect();self.assertIn('launcher',r['unsupported_sections'])
        self.assertEqual(r['startup_recipes']['openclaw']['launcher_sha256'],c.sha(self.io.files[u.LAUNCHER]))
        self.assertIsNone(r['startup_recipes']['openclaw']['entry_script_sha256'])
        self.assertNotIn(b'fixture unsupported JS launcher',packed(r))
    def test_unsupported_unit_retains_measured_bound_hash(self):
        self.io.add(self.io.backup,b'[Service]\nExecStart=/bin/sh -c secret\n');self.io.bind_backup()
        r=self.collect();self.assertIn('legacy_gateway',r['unsupported_sections'])
        self.assertEqual(r['startup_recipes']['openclaw']['unit_sha256'],c.sha(self.io.files[self.io.backup]))
        self.assertIsNone(r['startup_recipes']['openclaw']['literal_unit_argv'])
    def test_exact_override_groups_not_passwd_primary_union(self):
        e=self.evidence(self.collect(),'unit_nss')
        self.assertEqual(e['nss_by_primary']['xuanjun-dispatcher']['1006'],[1006])
        self.assertEqual(e['accounts']['xuanjun-dispatcher']['global_group_gids'],[1003])
    def test_all_dropin_roots_explicit_empty(self):
        e=self.evidence(self.collect(),'dropins');self.assertEqual(set(e['units']),set(u.UNITS))
        for unit,roots in e['units'].items():
            self.assertEqual(set(roots),{prefix+'/'+unit+'.d' for prefix in PREFIXES})
            for row in roots.values():self.assertEqual(row,{'present':False,'files':{}})
    def test_dropin_group_reset_append_preserved(self):
        root=PREFIXES[0]+'/'+u.GATEWAY+'.d';path=root+'/20-p2-docker.conf'
        raw=b'[Service]\nSupplementaryGroups=\nSupplementaryGroups=docker xuanjun-ledger-client\n'
        self.io.add(path,raw,mode=0o644);self.io.dropins[u.GATEWAY][root]={'present':True,'files':{path:self.io.read(path)}}
        e=self.evidence(self.collect(),'dropins')['units'][u.GATEWAY][root]['files'][path]
        self.assertEqual(e['public_service_fields']['SupplementaryGroups'],['','docker xuanjun-ledger-client'])
    def test_unknown_dropin_directive_aggregates_without_secret(self):
        root=PREFIXES[0]+'/'+u.GATEWAY+'.d';path=root+'/20-other.conf'
        self.io.add(path,('[Service]\nEnvironment=TOKEN='+SECRET+'\n').encode(),mode=0o644)
        self.io.dropins[u.GATEWAY][root]={'present':True,'files':{path:self.io.read(path)}}
        r=self.collect();self.assertIn('dropins',r['unsupported_sections']);self.assertNotIn(SECRET.encode(),packed(r))
        self.assertEqual(len(self.evidence(r,'dropins')['units']),len(u.UNITS))
    def test_all_missing_facts_reported_together(self):
        del self.io.files[c.NATIVE];del self.io.files[self.io.backup];del self.io.files[u.NGINX_CONFIG]
        self.io.unit_accounts['unsupported']={'group:nginx':'EXPECTED_FIELD_OR_NSS_RECORD_MISSING'}
        with mock.patch.object(self.io,'online_cpus',side_effect=OSError('secret details')):
            r=self.collect()
        self.assertEqual(r['unsupported_sections'],['launcher','legacy_gateway','native_gateway','nginx_config','online_cpus','unit_nss'])
        self.assertEqual(r['sections']['python_reference']['state'],'MEASURED_UNREVIEWED')
        self.assertNotIn(b'secret details',packed(r))
    def test_missing_unit_or_root_rejects_completeness(self):
        for remove_root in (False,True):
            self.io=Fake()
            if remove_root:self.io.dropins[u.GATEWAY].pop(PREFIXES[0]+'/'+u.GATEWAY+'.d')
            else:self.io.dropins.pop(u.GATEWAY)
            self.assertIn('dropins',self.collect()['unsupported_sections'])
    def test_unknown_root_and_other_roots_survive(self):
        root=PREFIXES[1]+'/'+u.GATEWAY+'.d'
        self.io.dropins[u.GATEWAY][root]={'present':None,'files':{},'state':'UNKNOWN','reason':'READ_PERMISSION_UNAVAILABLE'}
        r=self.collect();self.assertIn(root,self.evidence(r,'dropins')['unsupported'])
        self.assertEqual(self.evidence(r,'dropins')['units'][u.GATEWAY][PREFIXES[0]+'/'+u.GATEWAY+'.d']['present'],False)
    def test_absent_with_files_and_scope_escape_fail(self):
        root=PREFIXES[0]+'/'+u.GATEWAY+'.d'
        self.io.dropins[u.GATEWAY][root]['files']={'/etc/shadow':(b'x',{})}
        self.assertIn('dropins',self.collect()['unsupported_sections'])
    def test_native_wrong_hash_or_shape(self):
        self.io.files[c.NATIVE]+=b' ';self.assertIn('native_gateway',self.collect()['unsupported_sections'])
        self.io=Fake();self.io.native['gatewayIdentity']['extra']='bad';self.io.add(c.NATIVE,packed(self.io.native))
        self.assertIn('native_gateway',self.collect()['unsupported_sections'])
    def test_backup_binding_metadata_and_unapproved_path(self):
        original=self.evidence(self.collect(),'legacy_gateway')['original_unit']
        self.assertEqual(original,dict(path='/etc/systemd/system/'+u.GATEWAY,
            sha256=c.sha(self.io.files[self.io.backup]),uid=0,gid=0,mode=0o644))
        for change in ('hash','mode','path'):
            self.io=Fake()
            if change=='hash':self.io.files[self.io.backup]+=b' '
            elif change=='mode':self.io.metadata[self.io.backup]['mode']=0o644
            else:
                name=c.TRANSACTION+'/legacy-units.json';v=c.decode(self.io.files[name]);v['units'][u.GATEWAY]['backup']='/etc/shadow';self.io.add(name,packed(v))
            self.assertIn('legacy_gateway',self.collect()['unsupported_sections'])
    def test_launcher_owner_mode_and_entry_path(self):
        for key,value in (('uid',0),('mode',0o777),('nlink',2)):
            self.io=Fake();self.io.metadata[u.LAUNCHER][key]=value
            self.assertIn('launcher',self.collect()['unsupported_sections'])
        self.io=Fake();self.io.add(u.LAUNCHER,('#!/bin/bash\nexec '+NODE+' /etc/secret.js "$@"\n').encode(),uid=1002)
        self.assertIn('launcher',self.collect()['unsupported_sections']);self.assertNotIn('/etc/secret.js',[x for x,m in self.io.reads])
    def test_nginx_config_exact_rendered_pin_and_user(self):
        self.io.files[u.NGINX_CONFIG]+=b' ';self.assertIn('nginx_config',self.collect()['unsupported_sections'])
        self.io=Fake();self.io.add(u.NGINX_CONFIG,b'user root;\nworker_processes auto;\n',mode=0o644);self.io.bind_nginx()
        self.assertIn('nginx_config',self.collect()['unsupported_sections'])
    def test_cpu_race_and_invalid_value(self):
        for values in ([2,3],[0],[True],[4097]):
            with mock.patch.object(self.io,'online_cpus',side_effect=values):self.assertIn('online_cpus',self.collect()['unsupported_sections'])
    def test_partial_read_race_and_interrupt(self):
        original=self.io.read;calls=[]
        def changed(path,maximum=16777216):
            raw,row=original(path,maximum)
            if path==self.io.backup:
                calls.append(path)
                if len(calls)==2:row['ctime_ns']+=1
            return raw,row
        with mock.patch.object(self.io,'read',side_effect=changed):self.assertIn('legacy_gateway',self.collect()['unsupported_sections'])
        with mock.patch.object(self.io,'unit_nss',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.collect()

class ParserTests(unittest.TestCase):
    def test_gateway_dynamic_or_wrong_launcher_rejected(self):
        for cmd in (u.LAUNCHER+' $SECRET',u.LAUNCHER+' %i',u.LAUNCHER+'; true','/bin/sh -c true','+'+u.LAUNCHER):
            with self.assertRaises(ValueError):u.service_fields(('[Service]\nExecStart='+cmd+'\n').encode(),True)
    def test_gateway_secret_environment_not_returned(self):
        fields=u.service_fields(('[Service]\nEnvironment=TOKEN='+SECRET+'\nExecStart='+u.LAUNCHER+' gateway\n').encode(),True)
        self.assertEqual(fields['ExecStart'],[[u.LAUNCHER,'gateway']]);self.assertNotIn(SECRET.encode(),packed(fields))
    def test_dropin_continuation_account_specifier_unknown_rejected(self):
        for raw in (b'[Service]\nUser=%i\n',b'[Service]\nGroup=root\\\nroot\n',b'[Service]\nExecStart=/bin/true\n'):
            with self.assertRaises(ValueError):u.service_fields(raw)
    def test_launcher_dynamic_shell_or_unquoted_forward_rejected(self):
        for line in ('export X=$(id)','export X=a && id','export X=`id`','exec '+NODE+' '+ENTRY+' $@','exec '+NODE+' '+ENTRY+' "$@" ; id','source /etc/secret'):
            raw=('#!/bin/bash\n'+line+'\n').encode()
            with self.assertRaises(ValueError):u.launcher_recipe(raw,NODE)
    def test_launcher_only_exact_fixed_exec(self):
        r=u.launcher_recipe(('#!/bin/bash\nexport TOKEN='+SECRET+'\nexec '+NODE+' '+ENTRY+' "$@"\n').encode(),NODE)
        self.assertEqual(r['entry_script'],ENTRY);self.assertNotIn(SECRET.encode(),packed(r))

class ConcreteNssTests(unittest.TestCase):
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO)
        self.groups={'root':0,'xuanjun-dispatcher':1003,'xuanjun-control-db':1006,'xuanjun-ledger-client':1007,'xuanjun_dev':1002,'docker':994,'nginx':997}
        self.users={name:types.SimpleNamespace(pw_name=name,pw_uid=uid,pw_gid=uid) for name,uid in
            [('root',0),('xuanjun-dispatcher',1003),('xuanjun-callback',1004),('xuanjun_dev',1002),('nginx',997)]}
    def collect(self,groupfn=None):
        def group(name):return types.SimpleNamespace(gr_name=name,gr_gid=self.groups[name])
        with mock.patch.object(s.grp,'getgrnam',side_effect=group),mock.patch.object(s.pwd,'getpwnam',side_effect=lambda name:self.users[name]),mock.patch.object(s.pwd,'getpwuid',side_effect=lambda uid:next(r for r in self.users.values() if r.pw_uid==uid)),mock.patch.object(s.os,'getgrouplist',side_effect=groupfn or (lambda user,gid:[gid])) as calls:
            result=self.io.unit_nss();return result,calls.call_args_list
    def test_exact_unit_primary_gid_calls_and_no_union(self):
        r,calls=self.collect();self.assertEqual(r['unsupported'],{})
        self.assertEqual(r['nss_by_primary']['xuanjun-dispatcher'],{'1003':[1003],'1006':[1006]})
        self.assertIn(mock.call('xuanjun-callback',1006),calls)
        self.assertEqual(set(r['named_groups']),set(self.groups))
    def test_missing_group_and_user_aggregate(self):
        self.groups.pop('nginx');self.users.pop('root');r,unused=self.collect()
        self.assertIn('group:nginx',r['unsupported']);self.assertIn('nginx:nginx',r['unsupported']);self.assertIn('root:root',r['unsupported'])
        self.assertIn('xuanjun_dev',r['nss_by_primary'])
    def test_wrong_uid_and_pair_race_reported(self):
        self.users['xuanjun-callback'].pw_uid=123;r,unused=self.collect();self.assertIn('xuanjun-callback:xuanjun-control-db',r['unsupported'])
        n=[0]
        def changing(user,gid):n[0]+=1;return [gid,n[0]+2000]
        r,unused=self.collect(changing);self.assertTrue(r['unsupported'])

class ExecutableAliasTests(unittest.TestCase):
    def setUp(self):
        self.io=object.__new__(s.LocalReadOnlyIO);self.links={'/usr/bin/python3':'python3.6'};self.stats={};self.read_paths=[]
        for path in ('/usr/bin/python3','/usr/bin/python3.6','/usr/sbin/nginx','/usr/sbin/runuser'):
            self.stats[path]=types.SimpleNamespace(st_dev=1,st_ino=len(self.stats)+1,st_mode=(stat.S_IFLNK|0o777) if path in self.links else (stat.S_IFREG|0o755),st_uid=0,st_gid=0,st_nlink=1,st_size=8,st_mtime_ns=1,st_ctime_ns=2)
        @contextlib.contextmanager
        def parent(path):yield 99,path
        self.io.parent=parent
        def read(path,maximum):
            self.read_paths.append(path);raw=b'\x7fELFdata';return raw,dict(s.metadata(self.stats[path]),kind='FILE',sha256=c.sha(raw))
        self.io.read=read
    def collect(self,path='/usr/bin/python3'):
        with mock.patch.object(s.os,'stat',side_effect=lambda name,**kwargs:self.stats[name]),mock.patch.object(s.os,'readlink',side_effect=lambda name,**kwargs:self.links[name]):
            return self.io.executable_reference(path)
    def test_ordered_alias_and_final_elf_twice(self):
        r=self.collect();self.assertEqual(r['links'][0]['path'],'/usr/bin/python3');self.assertEqual(r['final']['path'],'/usr/bin/python3.6')
        self.assertEqual(self.read_paths,['/usr/bin/python3.6']*2)
    def test_exact_nginx_runuser_scope(self):
        for path in ('/usr/sbin/nginx','/usr/sbin/runuser'):self.assertEqual(self.collect(path)['final']['path'],path)
        with self.assertRaises(ValueError):self.collect('/bin/sh')
    def test_alias_escape_loop_and_wrong_owner_rejected(self):
        for link in ('/etc/shadow','python3'):
            self.links['/usr/bin/python3']=link
            with self.assertRaises(ValueError):self.collect()
        self.links['/usr/bin/python3']='python3.6';self.stats['/usr/bin/python3'].st_uid=1002
        with self.assertRaises(ValueError):self.collect()
    def test_nonelf_and_nonexecutable_rejected(self):
        self.io.read=lambda path,maximum:(b'not ELF',dict(s.metadata(self.stats[path]),sha256=h(path)))
        with self.assertRaises(ValueError):self.collect()
    def test_alias_race_rejected(self):
        def link(name,**kwargs):self.stats[name].st_ctime_ns+=1;return self.links[name]
        with mock.patch.object(s.os,'stat',side_effect=lambda name,**kwargs:copy.copy(self.stats[name])),mock.patch.object(s.os,'readlink',side_effect=link):
            with self.assertRaises(ValueError):self.io.python_reference()
    def test_final_stat_to_open_race_rejected(self):
        read=self.io.read
        def changed(path,maximum):
            raw,row=read(path,maximum);row['ino']+=1;return raw,row
        self.io.read=changed
        with self.assertRaisesRegex(ValueError,'FINAL_RACE'):self.collect()

class ConcreteDropinTests(unittest.TestCase):
    def setUp(self):self.io=object.__new__(s.LocalReadOnlyIO)
    def test_exact_eight_units_and_twenty_four_absence_roots(self):
        self.io.absent=mock.Mock(return_value=True)
        result=self.io.unit_dropins(u.UNITS)
        expected={prefix+'/'+unit+'.d' for unit in u.UNITS for prefix in PREFIXES}
        self.assertEqual(len(expected),24);self.assertEqual(set(result),set(u.UNITS))
        self.assertEqual({row[0][0] for row in self.io.absent.call_args_list},expected)
        self.assertIn('xj-root-broker.service',result)
        for roots in result.values():
            for value in roots.values():self.assertEqual(value,{'present':False,'files':{}})
    def test_one_unreadable_root_keeps_all_remaining_roots(self):
        broken=PREFIXES[0]+'/'+u.GATEWAY+'.d'
        def absent(root):
            if root==broken:raise PermissionError('private error')
            return True
        self.io.absent=absent;result=self.io.unit_dropins(u.UNITS)
        self.assertEqual(result[u.GATEWAY][broken]['state'],'UNKNOWN')
        self.assertEqual(result[u.GATEWAY][broken]['reason'],'READ_PERMISSION_UNAVAILABLE')
        self.assertEqual(sum(len(roots) for roots in result.values()),24)
    def test_unknown_or_missing_unit_rejected_before_any_read(self):
        self.io.absent=mock.Mock(return_value=True)
        for units in (u.UNITS[:-1],u.UNITS+('arbitrary.service',)):
            with self.assertRaises(ValueError):self.io.unit_dropins(units)
        self.io.absent.assert_not_called()

if __name__=='__main__':unittest.main()

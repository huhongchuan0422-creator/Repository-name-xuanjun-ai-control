"""Exact retained-plan directory metadata fixtures; no private plan or host IO.

The 20 tuples below were extracted from the protected original plan, 22468 bytes,
SHA ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a.
No configuration/credential bytes are included; metadata is not live-host proof.
"""
import copy
import json
import os
import pathlib
import shutil
import stat
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import observe_epoch7 as o

DECLARED=json.loads(r'''{"/etc/xuanjun-development":{"gid":0,"mode":493,"uid":0},"/etc/xuanjun-owner-callback":{"gid":1006,"mode":488,"uid":0},"/opt/xuanjun-runtime":{"gid":0,"mode":493,"uid":0},"/opt/xuanjun-runtime/codex-0.160.0":{"gid":0,"mode":493,"uid":0},"/opt/xuanjun-runtime/gh":{"gid":0,"mode":493,"uid":0},"/var/lib/xuanjun-development":{"gid":0,"mode":493,"uid":0},"/var/lib/xuanjun-development/activation":{"gid":0,"mode":493,"uid":0},"/var/lib/xuanjun-development/backups":{"gid":0,"mode":448,"uid":0},"/var/lib/xuanjun-development/codex-home":{"gid":1005,"mode":448,"uid":1005},"/var/lib/xuanjun-development/generations":{"gid":1006,"mode":488,"uid":0},"/var/lib/xuanjun-development/generations/1":{"gid":1006,"mode":488,"uid":1003},"/var/lib/xuanjun-development/nginx-home":{"gid":1008,"mode":448,"uid":1008},"/var/lib/xuanjun-development/service-home":{"gid":1003,"mode":448,"uid":1003},"/var/lib/xuanjun-development/service-home/.config":{"gid":1003,"mode":448,"uid":1003},"/var/lib/xuanjun-development/users":{"gid":0,"mode":493,"uid":0},"/var/lib/xuanjun-development/users/xj_codex_worker":{"gid":1005,"mode":448,"uid":1005},"/var/lib/xuanjun-development/users/xuanjun-callback":{"gid":1004,"mode":448,"uid":1004},"/var/lib/xuanjun-development/users/xuanjun-dispatcher":{"gid":1003,"mode":448,"uid":1003},"/var/lib/xuanjun-development/worker-home":{"gid":1005,"mode":448,"uid":1005},"/var/lib/xuanjun-development/worktrees":{"gid":1003,"mode":493,"uid":1003}}''')
ROOT='/var/lib/xuanjun-development'
CONFIG='/home/xuanjun_dev/.config'
ENV=CONFIG+'/openclaw/gateway.env'
# Public metadata projection of the sole JSON line in the Owner's readback.
# Raw transcript SHA ef17f3098b77430566c2f5974f02eaa1c71e28d6d08f16bf13e4b7c92ab2aeae.
# It did not expose inode/timestamps, so fixtures below do not invent them as
# measured facts. The stat helper's extra fields are synthetic test values.
OBSERVED_ANCESTORS={
    '/':{'kind':'DIRECTORY','uid':0,'gid':0,'mode':0o555,'nlink':18},
    '/home':{'kind':'DIRECTORY','uid':0,'gid':0,'mode':0o755,'nlink':6},
    '/home/xuanjun_dev':{'kind':'DIRECTORY','uid':1002,'gid':1002,'mode':0o700,'nlink':42},
    CONFIG:{'kind':'DIRECTORY','uid':0,'gid':0,'mode':0o755,'nlink':3}}
OBSERVED_ABSENCE={'path':CONFIG+'/openclaw','state':'ABSENT',
                  'leaf':{'path':ENV,'state':'UNAVAILABLE','reason':'MISSING_ANCESTOR'}}


def info(row):
    return types.SimpleNamespace(st_mode=stat.S_IFDIR|row['mode'],st_uid=row['uid'],st_gid=row['gid'],
                                 st_dev=1,st_ino=2,st_nlink=2,st_size=4096,
                                 st_mtime_ns=3,st_ctime_ns=4)


class DeclaredDirectoryTests(unittest.TestCase):
    def test_exact20_original_plan_rows_are_accepted_without_metadata_changes(self):
        self.assertEqual(len(DECLARED),20)
        self.assertEqual(o.ORIGINAL_PLAN_SHA,'ec1d617857845c43eff6bed2b70a0c00a5dad8dc52df95785bed3ee3d775335a')
        for path,row in DECLARED.items():
            self.assertEqual(o.authority(path,info(row),DECLARED),{k:row[k] for k in ('uid','gid','mode')})
    def test_only_exact_root_added_no_prefix_siblings(self):
        for path in (ROOT+'-other',ROOT+'2',ROOT+'_other','/var/lib/xuanjun','/var/lib','/tmp/xuanjun-development'):
            row=dict(DECLARED[ROOT],path=path)
            with self.assertRaisesRegex(ValueError,'OBSERVATION_DECLARED_DIRECTORY_AUTHORITY'):
                o.authority(path,info(row),{path:row})
    def test_every_declared_owner_group_or_mode_mismatch_is_rejected(self):
        for path,row in DECLARED.items():
            for field in ('uid','gid','mode'):
                changed=dict(row);changed[field]^=1
                with self.assertRaisesRegex(ValueError,'OBSERVATION_DECLARED_DIRECTORY_AUTHORITY'):
                    o.authority(path,info(changed),DECLARED)
    def test_nondirectory_and_special_or_writable_declared_modes_reject(self):
        row=DECLARED[ROOT];value=info(row);value.st_mode=stat.S_IFREG|row['mode']
        with self.assertRaises(ValueError):o.authority(ROOT,value,DECLARED)
        for mode in (0o775,0o757,0o4755,0o2755,0o1755):
            bad=dict(row,mode=mode)
            with self.assertRaises(ValueError):o.authority(ROOT,info(bad),{ROOT:bad})
        bad=dict(row,uid=1002)
        with self.assertRaises(ValueError):o.authority(ROOT,info(bad),{ROOT:bad})
    def test_initial_measurement_then_declared_map_keeps_same_root_pin(self):
        # Exercise the real reader authority boundary in measured_policy order:
        # initial mandatory-file traversal, then assigning the retained plan map.
        reader=object.__new__(o.ObservationReader);reader.pins={}
        value=info(DECLARED[ROOT])
        with mock.patch.object(o.os,'fstat',return_value=value),mock.patch.object(o.concrete,'xattr',return_value=None):
            self.assertIs(reader._authority(42,ROOT),value)
            first=copy.deepcopy(reader.pins);reader.declared_directories=copy.deepcopy(DECLARED)
            self.assertIs(reader._authority(42,ROOT),value)
            self.assertEqual(reader.pins,first)
    def test_map_activation_does_not_accept_an_initial_pin_or_actual_stat_drift(self):
        reader=object.__new__(o.ObservationReader);reader.pins={}
        value=info(DECLARED[ROOT])
        with mock.patch.object(o.os,'fstat',return_value=value),mock.patch.object(o.concrete,'xattr',return_value=None):
            reader._authority(42,ROOT);reader.declared_directories=copy.deepcopy(DECLARED)
            value.st_gid=1003
            with self.assertRaisesRegex(ValueError,'OBSERVATION_DECLARED_DIRECTORY_AUTHORITY'):reader._authority(42,ROOT)
            value.st_gid=0;reader.pins[ROOT]['mode']=0o700
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_CHANGED'):reader._authority(42,ROOT)
    def test_acl_and_independent_user_home_rules_are_unchanged(self):
        reader=object.__new__(o.ObservationReader);reader.pins={};reader.declared_directories=DECLARED
        with mock.patch.object(o.os,'fstat',return_value=info(DECLARED[ROOT])),mock.patch.object(o.concrete,'xattr',return_value=b'unknown'):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_UNREVIEWED_ACL'):reader._authority(42,ROOT)
        for path in ('/home/xuanjun_dev/.config-other','/home/xuanjun_dev/.config/openclaw'):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_AUTHORITY'):
                o.authority(path,info({'uid':0,'gid':0,'mode':0o755}),DECLARED)
    def test_retained_generation_is_still0750_not_future0700(self):
        path=ROOT+'/generations/1';row=DECLARED[path]
        self.assertEqual((row['uid'],row['gid'],row['mode']),(1003,1006,0o750))
        with self.assertRaises(ValueError):o.authority(path,info(dict(row,mode=0o700)),DECLARED)


class HomeConfigAuthorityTests(unittest.TestCase):
    def test_actual_metadata_projection_is_accepted_and_missing_path_not_pinned(self):
        pins={}
        for path,row in OBSERVED_ANCESTORS.items():
            pins[path]=o.authority(path,info(row),DECLARED)
            self.assertEqual(pins[path],{k:row[k] for k in ('uid','gid','mode')})
        self.assertEqual(OBSERVED_ABSENCE['state'],'ABSENT')
        self.assertEqual(OBSERVED_ABSENCE['leaf']['reason'],'MISSING_ANCESTOR')
        self.assertNotIn(CONFIG+'/openclaw',pins)
    def test_root_profile_is_exact_owner_group_and0755(self):
        for uid,gid,mode in ((0,1002,0o755),(1,0,0o755),(1003,1003,0o755),
                             (0,0,0o700),(0,0,0o750),(0,0,0o775),(0,0,0o757),
                             (0,0,0o4755),(0,0,0o2755),(0,0,0o1755)):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_AUTHORITY'):
                o.authority(CONFIG,info(dict(uid=uid,gid=gid,mode=mode)),DECLARED)
    def test_existing_specific_user_profile_is_preserved(self):
        for mode in (0o700,0o750,0o755):
            row=dict(uid=1002,gid=1002,mode=mode)
            self.assertEqual(o.authority(CONFIG,info(row),DECLARED),row)
    def test_exception_does_not_apply_to_siblings_descendants_or_other_homes(self):
        for path in (CONFIG+'-old',CONFIG+'2',CONFIG+'/openclaw',
                     '/home/xuanjun_dev/.openclaw','/home/xuanjun_dev/config'):
            with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_AUTHORITY'):
                o.authority(path,info(OBSERVED_ANCESTORS[CONFIG]),DECLARED)
        value=info(OBSERVED_ANCESTORS[CONFIG]);value.st_mode=stat.S_IFREG|0o755
        with self.assertRaises(ValueError):o.authority(CONFIG,value,DECLARED)
    def test_root_config_acls_refuse_and_recorded_identity_cannot_drift(self):
        reader=object.__new__(o.ObservationReader);reader.pins={}
        value=info(OBSERVED_ANCESTORS[CONFIG])
        with mock.patch.object(o.os,'fstat',return_value=value):
            for attr in ('system.posix_acl_access','system.posix_acl_default'):
                with mock.patch.object(o.concrete,'xattr',side_effect=lambda fd,name:b'acl' if name==attr else None):
                    with self.assertRaisesRegex(ValueError,'OBSERVATION_UNREVIEWED_ACL'):reader._authority(42,CONFIG)
            with mock.patch.object(o.concrete,'xattr',return_value=None):
                reader._authority(42,CONFIG)
                value.st_uid=1002;value.st_gid=1002
                with self.assertRaisesRegex(ValueError,'OBSERVATION_ANCESTOR_CHANGED'):reader._authority(42,CONFIG)
    def test_strict_replay_uses_measured_root_profile_without_user_exception(self):
        pins={CONFIG:o.authority(CONFIG,info(OBSERVED_ANCESTORS[CONFIG]),DECLARED)}
        reader=object.__new__(o.concrete.DescriptorReader);reader.pins=pins
        value=info(OBSERVED_ANCESTORS[CONFIG])
        with mock.patch.object(o.os,'fstat',return_value=value),mock.patch.object(o.concrete,'xattr',return_value=None):
            self.assertIs(reader._authority(42,CONFIG),value)
            value.st_gid=1002
            with self.assertRaisesRegex(ValueError,'ANCESTOR_UNMEASURED_OR_CHANGED'):reader._authority(42,CONFIG)


class MissingAncestorTests(unittest.TestCase):
    """Real local descriptor traversal; never reads or changes a host path."""
    def setUp(self):
        self.container=tempfile.mkdtemp(prefix='epoch7-absence-fixture-')
        self.root=self.container+'/root';os.mkdir(self.root,0o700)
        pins={'/':dict(uid=os.getuid(),gid=os.getgid(),mode=0o700)}
        for path in ('/home','/home/xuanjun_dev',CONFIG):
            os.mkdir(self.root+path,0o700)
            pins[path]=dict(uid=os.getuid(),gid=os.getgid(),mode=0o700)
        self.reader=o.concrete.DescriptorReader(pins,self.root)
    def tearDown(self):shutil.rmtree(self.container)
    def test_missing_parent_proves_leaf_absent_without_fabricated_directory_pin(self):
        before=copy.deepcopy(self.reader.pins)
        self.assertTrue(self.reader.absent(ENV));self.assertTrue(self.reader.absent(ENV))
        self.assertEqual(self.reader.pins,before);self.assertNotIn(CONFIG+'/openclaw',before)
    def test_missing_parent_read_is_not_misrepresented_as_empty_file(self):
        with self.assertRaisesRegex(ValueError,'ANCESTOR_MISSING'):self.reader.read(ENV)
    def test_parent_appearance_during_absence_rejects(self):
        with self.assertRaisesRegex(ValueError,'ABSENCE_PARENT_CHANGED'):
            with self.reader.parent(ENV,missing=True) as value:
                self.assertEqual(value,(None,None));os.mkdir(self.root+CONFIG+'/openclaw')
    def test_held_higher_ancestor_replacement_during_absence_rejects(self):
        with self.assertRaisesRegex(ValueError,'ANCESTOR_REPLACED'):
            with self.reader.parent(ENV,missing=True):
                os.rename(self.root+'/home/xuanjun_dev',self.root+'/home/old')
                os.mkdir(self.root+'/home/xuanjun_dev',0o700)
    def test_root_replacement_during_absence_rejects(self):
        with self.assertRaisesRegex(ValueError,'READER_ROOT_REPLACED'):
            with self.reader.parent(ENV,missing=True):
                os.rename(self.root,self.container+'/oldroot');os.mkdir(self.root,0o700)
    def test_missing_parent_symlink_is_not_absence(self):
        os.symlink('/nonexistent',self.root+CONFIG+'/openclaw')
        with self.assertRaises(OSError):self.reader.absent(ENV)
    def test_unknown_ancestor_and_acl_still_reject(self):
        saved=self.reader.pins.pop(CONFIG)
        with self.assertRaisesRegex(ValueError,'ANCESTOR_UNMEASURED_OR_CHANGED'):self.reader.absent(ENV)
        self.reader.pins[CONFIG]=saved
        with mock.patch.object(o.concrete,'xattr',return_value=b'acl'):
            with self.assertRaisesRegex(ValueError,'UNREVIEWED_ANCESTOR_ACL'):self.reader.absent(ENV)
    def test_permission_failure_is_not_absence(self):
        original=o.os.stat
        def denied(path,*args,**kwargs):
            if path=='openclaw':raise PermissionError('fixture')
            return original(path,*args,**kwargs)
        with mock.patch.object(o.os,'stat',side_effect=denied):
            with self.assertRaises(PermissionError):self.reader.absent(ENV)


class ParentCleanupTests(unittest.TestCase):
    setUp=MissingAncestorTests.setUp
    tearDown=MissingAncestorTests.tearDown
    def closer(self,failures):
        original=o.os.close;self.closed=[]
        def close(fd):
            self.closed.append(fd);original(fd)
            if len(self.closed) in failures:raise failures[len(self.closed)]
        return mock.patch.object(o.os,'close',side_effect=close)
    def closed_once(self,error):
        self.assertEqual(len(self.closed),4)
        self.assertEqual(len(set(self.closed)),4)
        for fd in self.closed:
            with self.assertRaises(OSError):os.fstat(fd)
        self.assertEqual(str(error.__cause__),'READER_PARENT_CLEANUP_UNKNOWN')
    def test_missing_parent_return_cannot_hide_first_close_interrupt(self):
        failure=KeyboardInterrupt('fixture close')
        with self.closer({1:failure}):
            with self.assertRaises(KeyboardInterrupt) as caught:self.reader.absent(ENV)
        self.assertIs(caught.exception,failure);self.closed_once(caught.exception)
    def test_nonfirst_close_failure_does_not_skip_remaining_fds(self):
        failure=OSError('fixture second close')
        with self.closer({2:failure}):
            with self.assertRaises(OSError) as caught:self.reader.absent(ENV)
        self.assertIs(caught.exception,failure);self.closed_once(caught.exception)
    def test_multiple_cleanup_failures_preserve_first_cleanup_exception(self):
        failure=OSError('fixture first close')
        with self.closer({1:failure,2:KeyboardInterrupt('fixture interrupt'),4:SystemExit('fixture exit')}):
            with self.assertRaises(OSError) as caught:self.reader.absent(ENV)
        self.assertIs(caught.exception,failure);self.closed_once(caught.exception)
    def test_body_primary_survives_independent_cleanup_interrupts(self):
        primary=PermissionError('fixture primary')
        with self.closer({1:KeyboardInterrupt('fixture close'),3:OSError('fixture later close')}):
            with self.assertRaises(PermissionError) as caught:
                with self.reader.parent(ENV,missing=True):raise primary
        self.assertIs(caught.exception,primary);self.closed_once(caught.exception)
    def test_setup_primary_survives_all_fd_cleanup(self):
        primary=ValueError('fixture authority');original=self.reader._authority
        def authority(fd,path):
            if path==CONFIG:raise primary
            return original(fd,path)
        with mock.patch.object(self.reader,'_authority',side_effect=authority),self.closer({2:KeyboardInterrupt('fixture close')}):
            with self.assertRaises(ValueError) as caught:self.reader.absent(ENV)
        self.assertIs(caught.exception,primary);self.closed_once(caught.exception)
    def test_absence_race_remains_primary_when_cleanup_fails(self):
        with self.closer({1:OSError('fixture close')}):
            with self.assertRaisesRegex(ValueError,'ABSENCE_PARENT_CHANGED') as caught:
                with self.reader.parent(ENV,missing=True):os.mkdir(self.root+CONFIG+'/openclaw')
        self.closed_once(caught.exception)
    def test_ambient_handled_exception_is_not_the_context_primary(self):
        ambient=ValueError('unrelated already handled');failure=OSError('fixture close')
        try:raise ambient
        except ValueError:
            with self.closer({1:failure}):
                with self.assertRaises(OSError) as caught:self.reader.absent(ENV)
        self.assertIs(caught.exception,failure);self.closed_once(caught.exception)
        self.assertIsNone(ambient.__cause__)
    def test_existing_leaf_context_has_same_cleanup_contract(self):
        with self.closer({2:OSError('fixture close')}):
            with self.assertRaises(OSError) as caught:
                with self.reader.parent(CONFIG+'/not-present') as pair:
                    self.assertEqual(pair[1],'not-present')
        self.closed_once(caught.exception)


if __name__=='__main__':unittest.main()

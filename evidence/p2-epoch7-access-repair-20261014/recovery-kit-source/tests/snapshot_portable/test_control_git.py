"""Injected read-only retained publisher source proof; never calls host Git."""
import copy
import pathlib
import sys
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate'),str(HERE/'tests')]
import epoch7_snapshot as c
import epoch7_delta as d
import snapshot_io as io
import test_snapshot as fixtures

class ControlGitTests(unittest.TestCase):
    def setUp(self):
        self.backend=object.__new__(io.LocalReadOnlyIO)
        self.backend.check_locks=mock.Mock()
        self.backend.publisher=mock.Mock(return_value={'root_identity_matches':True,'content_fingerprint_matches':True})
        self.backend.absent=mock.Mock(return_value=True)
        self.backend.command=mock.Mock(return_value=(('a'*40)+'\n'+('b'*40)+'\n').encode())
        self.backend.policy={'executables':{'git':{'path':'/usr/bin/git','sha256':fixtures.h('git')}}}
        self.reference={'path':c.BASE+'/publisher-realm-38503014520/protected-publisher-inputs.json',
            'sha256':fixtures.h('publisher input'),'source_commit':'a'*40,'source_tree':'b'*40}
        self.row={'target':io.CONTROL_GIT,'fingerprint':fixtures.h('publisher fingerprint')}
        self.journal=fixtures.h('publisher journal')
    def collect(self):return self.backend.control_git_source(self.reference,self.row,self.journal)
    def test_exact_proof_and_command(self):
        result=self.collect()
        self.assertEqual(set(result),{'schema','path','head_commit','head_tree','publisher_reference_sha256',
            'publisher_journal_sha256','publisher_fingerprint_sha256','git_sha256'})
        self.assertEqual(result['head_commit'],'a'*40);self.assertEqual(result['head_tree'],'b'*40)
        self.assertEqual(result['publisher_reference_sha256'],d.digest(self.reference))
        self.backend.command.assert_called_once_with('git',io.CONTROL_GIT_ARGS)
        self.assertEqual(self.backend.publisher.call_count,2)
        self.assertEqual(self.backend.absent.call_count,4)
    def test_measurement_does_not_choose_or_reconcile_head(self):
        self.reference['source_commit']='c'*40
        self.assertEqual(self.collect()['head_commit'],'a'*40)
    def test_wrong_publisher_path_before_command(self):
        self.row['target']='/tmp/repo'
        with self.assertRaisesRegex(ValueError,'TARGET'):self.collect()
        self.backend.command.assert_not_called()
    def test_external_object_store_fails_before_command(self):
        self.backend.absent.return_value=False
        with self.assertRaisesRegex(ValueError,'EXTERNAL_OBJECT'):self.collect()
        self.backend.command.assert_not_called()
    def test_post_query_external_object_store_is_race(self):
        self.backend.absent.side_effect=[True,True,False]
        with self.assertRaisesRegex(ValueError,'EXTERNAL_OBJECT'):self.collect()
    def test_publisher_fingerprint_checked_before_and_after(self):
        self.backend.publisher.side_effect=[{'fingerprint':'before'},{'fingerprint':'after'}]
        with self.assertRaisesRegex(ValueError,'QUERY_RACE'):self.collect()
    def test_protected_fingerprint_failure_blocks_query(self):
        self.backend.publisher.side_effect=ValueError('PUBLISHER_CONTENT_CHANGED')
        with self.assertRaisesRegex(ValueError,'PUBLISHER_CONTENT_CHANGED'):self.collect()
        self.backend.command.assert_not_called()
    def test_git_error_and_malformed_output_fail(self):
        for output in (b'',b'secret or URL\n',b'a'*40+b'\n',b'a'*40+b'\n'+b'b'*40+b'\nextra\n'):
            self.backend.command.return_value=output
            with self.assertRaisesRegex(ValueError,'OUTPUT'):self.collect()
        self.backend.command.side_effect=OSError('unavailable')
        with self.assertRaises(OSError):self.collect()
    def test_git_environment_is_closed_and_read_only(self):
        class StopBeforeSpawn(Exception):pass
        with mock.patch.object(io.subprocess,'Popen',side_effect=StopBeforeSpawn) as call:
            with self.assertRaises(StopBeforeSpawn):
                io.bounded_query(['/usr/bin/git']+io.CONTROL_GIT_ARGS,git_environment=True)
        args,kw=call.call_args
        self.assertEqual(kw['env'],io.CONTROL_GIT_ENV);self.assertEqual(kw['cwd'],'/')
        self.assertEqual(kw['stdin'],io.subprocess.DEVNULL)
        for key,value in (('GIT_CONFIG_GLOBAL','/dev/null'),('GIT_CONFIG_SYSTEM','/dev/null'),
            ('GIT_CONFIG_NOSYSTEM','1'),('GIT_NO_REPLACE_OBJECTS','1'),('GIT_TERMINAL_PROMPT','0'),
            ('GIT_OPTIONAL_LOCKS','0'),('GIT_NO_LAZY_FETCH','1'),('GIT_ALLOW_PROTOCOL','')):
            self.assertEqual(kw['env'][key],value)
        for bad in ('fetch','push','checkout','config','status','gc','clone'):
            self.assertNotIn(bad,io.CONTROL_GIT_ARGS)
    def test_git_environment_cannot_run_other_commands(self):
        with mock.patch.object(io.subprocess,'Popen') as call:
            with self.assertRaisesRegex(ValueError,'EXACT_READ_ONLY_GIT_QUERY'):
                io.bounded_query(['/usr/bin/git','fetch'],git_environment=True)
            call.assert_not_called()
    def test_snapshot_binds_head_proof(self):
        policy,backend=fixtures.fixture()
        with mock.patch.object(c,'RETAINED_NATIVE_SHA',c.sha(backend.raw[c.NATIVE])):
            snapshot,evidence=c.collect(policy,backend)
        proof=evidence['retained']['control_git']
        self.assertEqual(proof['path'],io.CONTROL_GIT)
        self.assertEqual(proof['publisher_journal_sha256'],snapshot['receipts']['publisher-bootstrap.json'])
        self.assertEqual(d.digest(evidence['retained']),snapshot['retained_resource_sha256'])
    def test_second_head_read_drift_fails(self):
        policy,backend=fixtures.fixture();original=backend.control_git_source;count=[0]
        def changed(*args):
            value=original(*args);count[0]+=1
            if count[0]>1:value['head_commit']='c'*40
            return value
        backend.control_git_source=changed
        with mock.patch.object(c,'RETAINED_NATIVE_SHA',c.sha(backend.raw[c.NATIVE])):
            with self.assertRaisesRegex(ValueError,'CONTROL_GIT_SCAN_RACE'):c.collect(policy,backend)
    def test_git_pin_mandatory(self):
        policy,backend=fixtures.fixture();policy['executables'].pop('git')
        with self.assertRaisesRegex(ValueError,'EXECUTABLE_PINS'):c.collect(policy,backend)

if __name__=='__main__':unittest.main()

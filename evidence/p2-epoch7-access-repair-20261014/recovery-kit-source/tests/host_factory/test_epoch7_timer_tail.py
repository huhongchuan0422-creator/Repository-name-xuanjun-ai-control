"""Boundary-mock scheduling/receipt tests. No systemd or host effects."""
import copy
import os
import pathlib
import subprocess
import tempfile
import types
import unittest
from unittest import mock
import epoch7_timer_tail as t
import epoch7_delta as d
from epoch7_recovery_sequence import BoundedDiagnostics
from epoch7_runtime_effects import Epoch7RuntimeEffects


def baseline():
    return {t.TIMER:b'NextElapseUSecMonotonic=0\nLastTriggerUSecMonotonic=0\nActiveEnterTimestampMonotonic=0\n',
            t.SERVICE:b'ActiveEnterTimestampMonotonic=0\nExecMainStartTimestampMonotonic=0\n'}


class TailTests(unittest.TestCase):
    def make(self,margin=300,trigger=False):
        context={'context_sha256':'a'*64};authority=mock.Mock();diagnostics=BoundedDiagnostics(mock.Mock())
        executable=mock.Mock(return_value=True);controls=types.SimpleNamespace(open_phase='post_install_checks',phase_deadline=700)
        value=t.RetainedRenewalTail(context,authority,diagnostics,executable,baseline(),
                                   d.digest(t.compile_timer_contract(baseline())),controls)
        state={'started':False};calls=[]
        def run(key):
            value._guard();calls.append(key)
            if key=='start':state['started']=True;raw=b''
            elif key=='show_1':raw=baseline()[t.SERVICE]
            elif not state['started']:raw=baseline()[t.TIMER]
            else:
                raw=('NextElapseUSecMonotonic=%ds\nLastTriggerUSecMonotonic=%s\nActiveEnterTimestampMonotonic=100000000\n'%
                     (100+margin,'1s' if trigger else '0')).encode()
            return subprocess.CompletedProcess(None,0,raw,b'')
        value.runner=types.SimpleNamespace(run=run)
        return value,context,diagnostics,calls
    def test_last_mutation_has_only_two_bounded_final_queries(self):
        with mock.patch.object(t.time,'monotonic',return_value=100):
            value,context,diag,calls=self.make();result=value.activate(context,diag)
        self.assertEqual(calls,['show_0','show_1','start','show_0','show_1'])
        self.assertFalse(result['timer_or_service_trigger_advanced'])
        self.assertEqual(result['minimum_observed_margin_seconds'],180)
    def test_insufficient_margin_or_trigger_advancement_holds(self):
        for margin,trigger,label in ((179,False,'EXPIRY_MARGIN'),(300,True,'RENEWAL_EXECUTION')):
            with mock.patch.object(t.time,'monotonic',return_value=100):
                value,context,diag,calls=self.make(margin,trigger)
                with self.assertRaisesRegex(ValueError,label):value.activate(context,diag)
    def test_no_retry_or_wrong_context_can_start_timer(self):
        with mock.patch.object(t.time,'monotonic',return_value=100):
            value,context,diag,calls=self.make()
            with self.assertRaises(ValueError):value.activate({},diag)
            self.assertEqual(calls,[]);value.activate(context,diag)
            with self.assertRaises(ValueError):value.activate(context,diag)
            self.assertEqual(calls.count('start'),1)
    def test_expired_outer_phase_cannot_start_timer(self):
        with mock.patch.object(t.time,'monotonic',return_value=100):
            value,context,diag,calls=self.make();value.controls.phase_deadline=99
            with self.assertRaisesRegex(ValueError,'DEADLINE'):value.activate(context,diag)
            self.assertEqual(calls,[])


class SuccessReceiptTests(unittest.TestCase):
    def make(self,directory):
        value=object.__new__(t.DeferredRenewalRuntime)
        value.phase='activate_new_services';value.context={'context_sha256':'a'*64}
        value.successful_commands={};value.diagnostics=types.SimpleNamespace(sequence=91)
        value.directory=directory
        value.contract={'start':{'operation':'service_start','argv':['/usr/bin/systemctl','start','nginx.service']}}
        return value
    def test_success_is_captured_before_guarded_journal_publication(self):
        with tempfile.TemporaryDirectory() as root:
            pathlib.Path(root+'/runtime-boot.json').write_bytes(b'fixture')
            value=self.make(root)
            def read(name):
                self.assertIn('nginx.service',value.successful_commands)
                return {'state':'ENABLED'}
            value._read=mock.Mock(side_effect=read);value._save=mock.Mock()
            with mock.patch.object(Epoch7RuntimeEffects,'_command',return_value=subprocess.CompletedProcess(None,0,b'',b'')):
                value._command('start')
            receipt=value.successful_commands['nginx.service']
            self.assertEqual(receipt['sequence'],91);self.assertEqual(receipt['returncode'],0)
            self.assertEqual(receipt['argv_sha256'],__import__('epoch7_service_roles').argv_hash(value.contract['start']['argv']))
            value._save.assert_called_once()
    def test_failed_command_never_becomes_success_evidence(self):
        value=self.make('/unused-fixture-no-read')
        with mock.patch.object(Epoch7RuntimeEffects,'_command',side_effect=ValueError('fixture failure')):
            with self.assertRaises(ValueError):value._command('start')
        self.assertEqual(value.successful_commands,{})

    def test_boot_publication_includes_owned_gateway_proof(self):
        value=self.make('/unused-fixture-no-read')
        restored={'context_sha256':'a'*64,'reload':{'sequence':70},'observed_after':{'fixture':'full stamped row'}}
        value.legacy=types.SimpleNamespace(restoration_evidence=lambda:copy.deepcopy(restored))
        row=value._boot_evidence({'state':'ENABLED'})
        self.assertEqual(row['gateway_restoration'],restored)
        self.assertEqual(row['successful_commands'],{})
        restored['reload']=None
        with self.assertRaisesRegex(ValueError,'RESTORE_COMPLETE'):value._boot_evidence({})

if __name__=='__main__':unittest.main()

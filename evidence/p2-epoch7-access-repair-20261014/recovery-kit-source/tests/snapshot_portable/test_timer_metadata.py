"""Synthetic v239-style property output only; no timer/service operations."""
import copy
import pathlib
import sys
import time
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate'),str(HERE/'tests')]
import snapshot_io as io
import probe_metadata as p
import epoch7_snapshot as c
import test_probe_metadata as fixtures

TIMER='xuanjun-p2-tls-renew.timer'
SERVICE='xuanjun-p2-tls-renew.service'

class TimerMetadataTests(unittest.TestCase):
    def setUp(self):
        self.backend=fixtures.Fake();self.base=self.backend.timer_schedule()
        self.base['raw'][TIMER]['NextElapseUSecMonotonic']='5min 123ms'
        self.base['raw'][TIMER]['LastTriggerUSecMonotonic']='2h 1min 4.5s'
        self.base['raw'][TIMER]['ActiveEnterTimestampMonotonic']='1000000'
        self.base['raw'][SERVICE]['ExecMainStartTimestampMonotonic']='987654321'
        self.backend.timer_schedule=lambda:copy.deepcopy(self.base)
    def test_five_properties_preserve_raw_and_separate_encodings(self):
        r=p.timer_properties(self.backend)
        self.assertEqual(sum(len(x) for x in r['raw'].values()),5)
        self.assertEqual(r['raw'],self.base['raw']);self.assertEqual(r['missing_fields'],[])
        self.assertEqual(r['unsupported_fields'],[])
        self.assertIsNone(r['typed'][TIMER]['NextElapseUSecMonotonic']['value'])
        self.assertEqual(r['typed'][TIMER]['NextElapseUSecMonotonic']['encoding'],'SYSTEMD239_FORMAT_TIMESPAN')
        self.assertEqual(r['typed'][SERVICE]['ExecMainStartTimestampMonotonic']['value'],987654321)
        self.assertEqual(r['timer_actions'],0)
    def test_usec_digits_are_not_assumed_to_mean_microseconds(self):
        self.base['raw'][TIMER]['NextElapseUSecMonotonic']='123456'
        r=p.timer_properties(self.backend)
        self.assertIn(TIMER+':NextElapseUSecMonotonic',r['unsupported_fields'])
        self.assertIsNone(r['typed'][TIMER]['NextElapseUSecMonotonic']['value'])
    def test_zero_is_measured_not_fabricated(self):
        self.base['raw'][TIMER]['LastTriggerUSecMonotonic']='0'
        r=p.timer_properties(self.backend)
        self.assertEqual(r['raw'][TIMER]['LastTriggerUSecMonotonic'],'0')
        self.assertNotIn(TIMER+':LastTriggerUSecMonotonic',r['unsupported_fields'])
        del self.base['raw'][TIMER]['LastTriggerUSecMonotonic']
        r=p.timer_properties(self.backend)
        self.assertIn(TIMER+':LastTriggerUSecMonotonic',r['missing_fields'])
        self.assertNotIn('LastTriggerUSecMonotonic',r['raw'][TIMER])
    def test_infinity_unknown_and_overflow_are_explicit(self):
        self.base['raw'][TIMER]['NextElapseUSecMonotonic']='infinity'
        self.base['raw'][TIMER]['LastTriggerUSecMonotonic']='unknown'
        self.base['raw'][SERVICE]['ExecMainStartTimestampMonotonic']=str(2**64)
        r=p.timer_properties(self.backend)
        self.assertEqual(r['state'],'INCOMPLETE');self.assertEqual(len(r['unsupported_fields']),2)
        self.assertEqual(r['typed'][TIMER]['NextElapseUSecMonotonic']['encoding'],'INACTIVE_BASELINE_NOT_SCHEDULED')
    def test_timestamp_timespan_is_not_assumed_decimal(self):
        self.base['raw'][SERVICE]['ExecMainStartTimestampMonotonic']='1h'
        self.assertIn(SERVICE+':ExecMainStartTimestampMonotonic',p.timer_properties(self.backend)['unsupported_fields'])
    def test_exact_unit_property_scope(self):
        self.base['raw'][TIMER]['Environment']='not allowed'
        with self.assertRaisesRegex(ValueError,'PROPERTY_SCOPE'):p.timer_properties(self.backend)
    def test_missing_and_unsupported_aggregate_in_private_bundle(self):
        del self.base['raw'][TIMER]['LastTriggerUSecMonotonic']
        self.base['raw'][SERVICE]['ExecMainStartTimestampMonotonic']='n/a'
        r=p.collect_probe_ingredients(self.backend,fixtures.ROOT)
        self.assertIn('retained_tls_schedule',r['unsupported_sections'])
        self.assertEqual(len(r['retained_tls_schedule']['missing_fields']),1)
        self.assertEqual(len(r['retained_tls_schedule']['unsupported_fields']),1)
        self.assertEqual(set(r['ingredients']),p.INGREDIENT_FIELDS)
    def test_query_unavailable_keeps_other_components(self):
        self.backend.timer_schedule=mock.Mock(side_effect=PermissionError('private unavailable'))
        r=p.collect_probe_ingredients(self.backend,fixtures.ROOT)
        self.assertIsNone(r['retained_tls_schedule'])
        self.assertEqual(r['sections']['retained_tls_schedule']['reason'],'READ_PERMISSION_UNAVAILABLE')
        self.assertNotIn('private unavailable',str(r))
        self.assertEqual(r['ingredient_state'],'COMPLETE_UNREVIEWED')

class ConcreteTimerTests(unittest.TestCase):
    def setUp(self):
        self.backend=object.__new__(io.LocalReadOnlyIO)
        self.backend.check_locks=mock.Mock();self.backend.deadline=time.monotonic()+60
        self.tool={'uid':0,'gid':0,'mode':0o755,'sha256':c.sha(b'fixture tool')}
        self.backend.read=mock.Mock(return_value=(b'fixture tool',self.tool))
    def response(self,args,**unused):
        unit=args[2];return ('Id='+unit+'\n'+''.join(k+'=0\n' for k in io.TLS_TIMER_FIELDS[unit])).encode()
    def test_exact_bounded_show_only_and_repeat(self):
        with mock.patch.object(io,'bounded_query',side_effect=self.response) as query:
            result=self.backend.timer_schedule()
        self.assertEqual(query.call_count,4);self.assertEqual(self.backend.read.call_count,2)
        for args,kwargs in query.call_args_list:
            argv=args[0];unit=argv[2]
            self.assertEqual(argv,['/usr/bin/systemctl','show',unit,'--property=Id,'+','.join(io.TLS_TIMER_FIELDS[unit]),'--no-pager'])
            self.assertEqual(kwargs['maximum'],4096);self.assertLessEqual(kwargs['timeout'],5)
        self.assertEqual(set(result['raw']),{TIMER,SERVICE})
    def test_changed_properties_reject(self):
        calls=[0]
        def changed(args,**kw):
            calls[0]+=1;out=self.response(args,**kw)
            return out.replace(b'=0',b'=1') if calls[0]==2 else out
        with mock.patch.object(io,'bounded_query',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'PROPERTY_RACE'):self.backend.timer_schedule()
    def test_wrong_unit_or_unknown_key_reject(self):
        for output in (b'Id=wrong.service\n',('Id='+SERVICE+'\nEnvironment=secret\n').encode()):
            with mock.patch.object(io,'bounded_query',return_value=output):
                with self.assertRaises(ValueError):self.backend.timer_schedule()
    def test_systemctl_changed_after_queries_reject(self):
        other=dict(self.tool,sha256=c.sha(b'changed'))
        self.backend.read.side_effect=[(b'fixture tool',self.tool),(b'changed',other)]
        with mock.patch.object(io,'bounded_query',side_effect=self.response):
            with self.assertRaisesRegex(ValueError,'SYSTEMCTL_RACE'):self.backend.timer_schedule()

if __name__=='__main__':unittest.main()

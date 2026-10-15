"""Typed systemd239 fixtures; actual selected metadata, no UK query or effects.

ACTUAL_UNIT_ROWS is the approved diagnostic's selected-property projection.
It is not original systemctl stdout. Fragment/drop-in path projections are
excluded; parser tests add explicit synthetic query-only fields.
"""
import copy
import json
import pathlib
import sys
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE.parent/'recovery-design-candidate')]
import epoch7_snapshot as c
import snapshot_io as s
from test_snapshot import writer_fixture,fixture,native_pin_context,native_raws

DIAGNOSTIC_SOURCE_SHA256='699b2a75228e6af2040a481b96a20c07e2b62ab3ba1eefc6726fe8bb20eceab2'
ACTUAL_UNIT_ROWS=json.loads(r'''{"actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.iZd7oeikknn1z21sq6ji6zZ.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"actions.runner.huhongchuan0422-creator-Repository-name-xuanjun-ai-control.iZd7oeikknn1z21sq6ji6zZ.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"enabled"},"nginx.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"nginx.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xj-root-broker.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xj-root-broker.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xj-root-broker.socket":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xj-root-broker.socket","LoadState":"loaded","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xj-uk-owner-notify.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xj-uk-owner-notify.service","LoadState":"masked","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"},"xj-uk-owner-notify.timer":{"ActiveState":"inactive","ConditionResult":"no","Id":"xj-uk-owner-notify.timer","LoadState":"masked","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"},"xuanjun-development-dispatcher.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-development-dispatcher.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-github-intake.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-github-intake.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"static"},"xuanjun-github-intake.timer":{"ActiveState":"inactive","ConditionResult":"no","Id":"xuanjun-github-intake.timer","LoadState":"loaded","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-ledger.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-ledger.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-ledger.socket":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-ledger.socket","LoadState":"loaded","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-p2-gateway-relay.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-p2-gateway-relay.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-p2-gateway-relay.socket":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-p2-gateway-relay.socket","LoadState":"loaded","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-p2-tls-renew.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-p2-tls-renew.service","LoadState":"loaded","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"static"},"xuanjun-p2-tls-renew.timer":{"ActiveState":"inactive","ConditionResult":"no","Id":"xuanjun-p2-tls-renew.timer","LoadState":"loaded","NeedDaemonReload":"no","SubState":"dead","UnitFileState":"disabled"},"xuanjun-uk-openclaw.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-uk-openclaw.service","LoadState":"masked","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"},"xuanjun-uk-owner-callback.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-uk-owner-callback.service","LoadState":"masked","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"},"xuanjun-uk-owner-dashboard.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-uk-owner-dashboard.service","LoadState":"masked","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"},"xuanjun-uk-stage1-minimal.service":{"ActiveState":"inactive","ConditionResult":"no","ControlGroup":"","ControlPID":0,"Id":"xuanjun-uk-stage1-minimal.service","LoadState":"masked","MainPID":0,"NeedDaemonReload":"no","SubState":"dead","UnitFileState":"masked"}}''')


def actual_unit_rows(pid_type=str):
    rows=copy.deepcopy(ACTUAL_UNIT_ROWS)
    if pid_type is str:
        for row in rows.values():
            for key in ('MainPID','ControlPID'):
                if key in row:row[key]=str(row[key])
    return rows


def actual_writer_fixture():
    # Only the state rows are actual metadata. Remaining evidence is explicitly
    # synthetic and goes through the real independent writer validator.
    value=writer_fixture()
    for unit,row in actual_unit_rows().items():value['units'][unit]['state']=row
    return value


class UnitProcessFieldsTests(unittest.TestCase):
    def test_actual19_projection_preserves_all_absences_in_both_pid_representations(self):
        for representation in (str,int):
            rows=actual_unit_rows(representation);before=copy.deepcopy(rows)
            self.assertEqual(set(rows),c.WRITER_UNITS)
            for unit,row in rows.items():
                self.assertEqual(c.validate_unit_process_fields(unit,row,representation),(0,0))
                missing=c.UNIT_PROCESS_FIELDS-set(row)
                expected=c.UNIT_PROCESS_FIELDS if unit in c.TIMER_UNITS else (
                    {'MainPID'} if unit in c.SOCKET_UNITS else set())
                self.assertEqual(missing,expected)
            self.assertEqual(rows,before)
    def test_exact_three_timer_and_three_socket_contract(self):
        self.assertEqual(len(c.TIMER_UNITS),3);self.assertEqual(len(c.SOCKET_UNITS),3)
        for unit in c.WRITER_UNITS:
            required,optional=c.unit_process_fields(unit)
            self.assertEqual(required|optional,c.UNIT_PROCESS_FIELDS);self.assertFalse(required&optional)
        for unit in ('unreviewed.timer','unreviewed.socket','unreviewed.service','../x.timer',None):
            with self.assertRaises(ValueError):c.unit_process_fields(unit)
    def test_required_service_and_socket_properties_cannot_disappear(self):
        for unit,row in actual_unit_rows().items():
            required,unused=c.unit_process_fields(unit)
            for key in required:
                changed=copy.deepcopy(row);changed.pop(key)
                with self.assertRaises(ValueError):c.validate_unit_process_fields(unit,changed)
    def test_optional_present_zero_or_empty_is_checked_without_rewriting(self):
        for unit in c.TIMER_UNITS|c.SOCKET_UNITS:
            row=actual_unit_rows()[unit];unused,optional=c.unit_process_fields(unit)
            for key in optional:row[key]='' if key=='ControlGroup' else '0'
            before=copy.deepcopy(row)
            self.assertEqual(c.validate_unit_process_fields(unit,row),(0,0));self.assertEqual(row,before)
            for key in optional:
                changed=copy.deepcopy(row);changed[key]='/system.slice/'+unit if key=='ControlGroup' else '1'
                with self.assertRaises(ValueError):c.validate_unit_process_fields(unit,changed)
    def test_pid_types_format_bounds_and_bool_are_rejected(self):
        unit='xuanjun-ledger.service'
        for representation,bad in ((str,None),(str,0),(str,'00'),(str,'-1'),(str,'+1'),(str,'1\n'),
                (str,'10000000000'),(int,True),(int,'0'),(int,-1),(int,10000000000)):
            row=actual_unit_rows(representation)[unit];row['MainPID']=bad
            with self.assertRaises(ValueError):c.validate_unit_process_fields(unit,row,representation)
        with self.assertRaises(ValueError):c.validate_unit_process_fields(unit,actual_unit_rows()[unit],bool)
    def test_controlgroup_null_nonstrings_foreign_and_timer_canonical_are_rejected(self):
        for unit,row in actual_unit_rows().items():
            for bad in (None,False,0,[],{},'/foreign','/system.slice/other.service'):
                changed=copy.deepcopy(row);changed['ControlGroup']=bad
                with self.assertRaises(ValueError):c.validate_unit_process_fields(unit,changed)
    def test_service_pid_semantics_do_not_replace_phase_state_validation(self):
        row=actual_unit_rows()['xuanjun-ledger.service'];row.update(MainPID='42',ControlPID='7')
        self.assertEqual(c.validate_unit_process_fields('xuanjun-ledger.service',row),(42,7))


class CollectorUnitShapeTests(unittest.TestCase):
    def backend(self,row):
        # FragmentPath/DropInPaths are synthetic query fields; the diagnostic
        # contains structured path projections, not recoverable raw stdout.
        values=dict(row,FragmentPath='',DropInPaths='')
        raw=''.join(key+'='+value+'\n' for key,value in sorted(values.items())).encode()
        io=object.__new__(s.LocalReadOnlyIO);io.command=mock.Mock(return_value=raw);io.absent=mock.Mock(return_value=False)
        return io,values
    def test_actual19_selected_shapes_pass_query_without_insertions(self):
        for unit,row in actual_unit_rows().items():
            io,expected=self.backend(row);self.assertEqual(io._unit(unit),expected)
            self.assertEqual(io.command.call_count,1)
    def test_active_or_activating_timer_never_passes_exclusion(self):
        for unit in c.TIMER_UNITS:
            for state in ('active','activating','deactivating','unknown'):
                row=actual_unit_rows()[unit];row['ActiveState']=state;io,unused=self.backend(row)
                with self.assertRaises(ValueError):io._unit(unit)
    def test_every_applicable_query_property_is_required(self):
        for unit,row in actual_unit_rows().items():
            io,complete=self.backend(row);unused,optional=c.unit_process_fields(unit)
            for key in set(complete)-optional:
                value=dict(complete);value.pop(key)
                io.command.return_value=''.join(k+'='+v+'\n' for k,v in value.items()).encode()
                with self.assertRaises(ValueError):io._unit(unit)
    def test_unknown_and_duplicate_properties_are_rejected(self):
        unit='xuanjun-p2-tls-renew.timer';io,unused=self.backend(actual_unit_rows()[unit])
        for suffix in (b'UnknownProperty=\n',b'Id='+unit.encode()+b'\n'):
            original=io.command.return_value;io.command.return_value=original+suffix
            with self.assertRaises(ValueError):io._unit(unit)
            io.command.return_value=original
    def test_reload_and_supplied_nonzero_service_control_pid_hold(self):
        for unit in c.WRITER_UNITS:
            row=actual_unit_rows()[unit];row['NeedDaemonReload']='yes';io,unused=self.backend(row)
            with self.assertRaises(ValueError):io._unit(unit)
        unit='xuanjun-ledger.service';row=actual_unit_rows()[unit];row['ControlPID']='123';io,unused=self.backend(row)
        with self.assertRaises(ValueError):io._unit(unit)


class WriterBoundaryTests(unittest.TestCase):
    def test_full_writer_validator_retains_actual_projection(self):
        value=actual_writer_fixture();before=copy.deepcopy(value)
        self.assertIs(c.validate_writers(value),value);self.assertEqual(value,before)
    def test_all_associated_services_are_still_checked(self):
        for timer in c.TIMER_UNITS:
            value=actual_writer_fixture();service=timer[:-6]+'.service'
            value['units'][service]['state'].update(MainPID='42',ActiveState='active')
            with self.assertRaises(ValueError):c.validate_writers(value)
    def test_nonempty_timer_cgroup_mask_and_missing_unit_hold(self):
        for timer in c.TIMER_UNITS:
            value=actual_writer_fixture();value['units'][timer]['cgroup_entries']={
                '/sys/fs/cgroup/systemd/system.slice/'+timer+'/cgroup.procs':c.sha(b'42\n')}
            with self.assertRaises(ValueError):c.validate_writers(value)
        value=actual_writer_fixture();value['masks'][next(iter(c.LEGACY_MASKS))]['link']='/tmp/other'
        with self.assertRaises(ValueError):c.validate_writers(value)
        value=actual_writer_fixture();value['units'].pop(next(iter(c.TIMER_UNITS)))
        with self.assertRaises(ValueError):c.validate_writers(value)
    def test_full_collect_detects_absence_to_empty_and_zero_appearance_race(self):
        timer='xuanjun-p2-tls-renew.timer'
        for field,value in (('ControlGroup',''),('MainPID','0'),('ControlPID','0')):
            policy,io=fixture();before=actual_writer_fixture();after=copy.deepcopy(before)
            after['units'][timer]['state'][field]=value
            io.writers=mock.Mock(side_effect=[before,after])
            with native_pin_context(native_raws(io)):
                with self.assertRaisesRegex(ValueError,'WRITER_OBSERVATION_CHANGED'):c.collect(policy,io)
    def test_full_collect_propagates_process_or_database_fd_failure(self):
        policy,io=fixture();io.writers=mock.Mock(side_effect=ValueError('DATABASE_OR_WRITER_PROCESS_OBSERVED'))
        with native_pin_context(native_raws(io)):
            with self.assertRaisesRegex(ValueError,'DATABASE_OR_WRITER_PROCESS_OBSERVED'):c.collect(policy,io)


if __name__=='__main__':unittest.main()

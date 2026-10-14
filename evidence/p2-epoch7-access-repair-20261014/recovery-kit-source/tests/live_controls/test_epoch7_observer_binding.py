"""Cross-candidate binding API tests; synthetic components, no host reads."""
import copy
import os
import pathlib
import sys
import types
import unittest
from unittest import mock

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent.parent
sys.path[:0]=[str(HERE),str(HERE.parent/'host-driver-candidate'),
    str(HERE.parent/'command-candidate'),str(HERE.parent/'approval-candidate'),
    str(HERE.parent/'snapshot-candidate'),str(HERE.parent/'recovery-design-candidate'),
    str(HERE.parent/'diagnostics-candidate'),
    str(ROOT/'p2-epoch5-repair/runtime-v4-extracted/xuanjun-p2-package/stage1')]

import epoch7_host_observer as host
import epoch7_live_controls as live
from test_epoch7_live_controls import fixture,Observer,Lock,Verifier,Authority,process_view


class BoundFixture(Observer):
    bind_plan=host.Epoch7HostObserver.bind_plan
    begin_guard=host.Epoch7HostObserver.begin_guard
    _bound=host.Epoch7HostObserver._bound
    def __init__(self,rig,context,contract,views):
        super(BoundFixture,self).__init__(rig,context,contract,views)
        self.resource_reader=types.SimpleNamespace(digest=live.digest(views),views=copy.deepcopy(views),
            reader=types.SimpleNamespace(directories={'/':[]},guard_deadline=None))
        self.census=types.SimpleNamespace(manager_pin=copy.deepcopy(contract['manager']),
            database_identities=copy.deepcopy(contract['database_identities']),
            retained_sidecars=copy.deepcopy(contract['retained_sidecar_pins']),guard_deadline=None)
        self.tls=types.SimpleNamespace(guard_deadline=None)
        self.policy_sha=live.digest({'fixture':'policy'})
        self.bound_plan=None;self.live_contract=None;self.guard_deadline=None


def setup():
    rig,context,contract,views=fixture()
    observer=BoundFixture(rig,context,contract,views)
    plan={'live_controls':contract,'resource_observer':{
        'views_sha256':observer.resource_reader.digest,
        'directories_sha256':live.digest(observer.resource_reader.reader.directories),
        'snapshot_policy_sha256':observer.policy_sha}}
    return rig,context,contract,observer,plan


class ObserverBindingTests(unittest.TestCase):
    def test_real_observer_plan_binding_composes_with_controls(self):
        rig,context,contract,observer,plan=setup();raw=live.canonical(plan)
        lock=Lock();verifier=Verifier(raw,context);authority=Authority(lock)
        control=live.FiniteLiveControls(raw,context,verifier,lock,authority,observer)
        self.assertEqual(observer.live_contract,control.contract)
        observer._bound()

    def test_observer_component_hashes_must_match_approved_plan(self):
        for key in ('views_sha256','directories_sha256','snapshot_policy_sha256'):
            rig,context,contract,observer,plan=setup()
            plan['resource_observer'][key]=live.digest('different component')
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'EXACT_PLAN_BINDING'):
                observer.bind_plan(plan)

    def test_all_checkpoint_resource_hashes_match_actual_spec_views(self):
        for index in range(17):
            rig,context,contract,observer,plan=setup()
            plan['live_controls']['checkpoints'][index]['resources']['historical']=live.digest('unmeasured')
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'CHECKPOINT_VIEW_BINDING'):
                observer.bind_plan(plan)

    def test_manager_database_pins_and_binding_reuse_refused(self):
        for key in ('manager','database_identities'):
            rig,context,contract,observer,plan=setup()
            if key=='manager':plan['live_controls'][key]['starttime']+=1
            else:plan['live_controls'][key][live.d.DB]['ino']+=1
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'PROCESS_PIN_BINDING'):
                observer.bind_plan(plan)
        rig,context,contract,observer,plan=setup();observer.bind_plan(plan)
        with self.assertRaisesRegex(ValueError,'REVIEWED_PLAN_REQUIRED'):observer.bind_plan(plan)

    def test_bound_ancestor_policy_cannot_mutate_later(self):
        rig,context,contract,observer,plan=setup();observer.bind_plan(plan)
        observer.resource_reader.reader.directories['/new']=[]
        with self.assertRaisesRegex(ValueError,'PLAN_MUTATED'):observer._bound()

    def test_guard_deadline_propagates_without_new_resource_budget(self):
        rig,context,contract,observer,plan=setup();observer.bind_plan(plan)
        with mock.patch.object(host.time,'monotonic',return_value=100):observer.begin_guard(110)
        self.assertEqual(observer.guard_deadline,110)
        self.assertEqual(observer.census.guard_deadline,110)
        self.assertEqual(observer.resource_reader.reader.guard_deadline,110)
        self.assertEqual(observer.tls.guard_deadline,110)
        with mock.patch.object(host.time,'monotonic',return_value=100):
            with self.assertRaisesRegex(ValueError,'DEADLINE'):observer.begin_guard(131)


if __name__=='__main__':unittest.main()

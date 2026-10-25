"""Run the R5 scoped suite with explicit legacy-environment exclusions."""
from __future__ import print_function

import sys
import unittest


MODULES = (
    'tests.test_task_supervisor', 'tests.test_task_writer_fence',
    'tests.test_entry_review_gate', 'tests.test_reusable_task_gateway',
    'tests.test_reusable_scheduler_cli', 'tests.test_task_center_app',
    'tests.test_task_center_execution_contract',
    'tests.test_execution_policy_gateway', 'tests.test_model_orchestration',
    'tests.test_task_center_full_journey')
EXCLUDED = frozenset((
    'tests.test_task_supervisor.SupervisorTests.'
    'test_v2_active_attempt_migrates_to_unknown_hold',
    'tests.test_task_supervisor.SupervisorTests.'
    'test_v2_migration_failpoints_rollback_and_restart_cleanly',
    'tests.test_task_supervisor.SupervisorTests.'
    'test_v2_normal_open_is_zero_write_then_explicit_migration'))


def flatten(suite):
    result=[]
    for item in suite:
        if isinstance(item,unittest.TestSuite):result.extend(flatten(item))
        else:result.append(item)
    return result


def main():
    loaded=unittest.TestSuite()
    for module in MODULES:
        loaded.addTests(unittest.defaultTestLoader.loadTestsFromName(module))
    tests=flatten(loaded)
    selected=[test for test in tests if test.id() not in EXCLUDED]
    excluded=[test.id() for test in tests if test.id() in EXCLUDED]
    print('SCOPED_EXECUTIONS=%d'%len(selected))
    print('SCOPED_DISTINCT_IDS=%d'%len(set(test.id() for test in selected)))
    print('EXCLUDED_LEGACY_MIGRATION=%d'%len(excluded))
    for test_id in sorted(excluded):print('NOT_EXECUTED='+test_id)
    result=unittest.TextTestRunner(verbosity=2,stream=sys.stdout).run(
        unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())

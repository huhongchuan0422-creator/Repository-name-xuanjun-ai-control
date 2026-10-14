"""Run actual existing ACL planner regression; not host/whole-release acceptance."""
import importlib.util
from pathlib import Path
import sys
import unittest


def load_tests(loader, tests, pattern):
    root = Path(__file__).resolve().parents[1]
    source = root / 'evidence/p2-epoch7-access-repair-20261014'
    previous = list(sys.path)
    previous_module = sys.modules.pop('exact_access_plan', None)
    try:
        sys.path.insert(0, str(source))
        spec = importlib.util.spec_from_file_location(
            '_p2_retained_acl_regression', str(source / 'test_exact_access_plan.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return loader.loadTestsFromModule(module)
    finally:
        sys.path[:] = previous
        sys.modules.pop('exact_access_plan', None)
        if previous_module is not None:
            sys.modules['exact_access_plan'] = previous_module


if __name__ == '__main__':
    unittest.main()

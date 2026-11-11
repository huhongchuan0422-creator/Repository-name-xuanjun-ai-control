"""Discoverable entry for the migration closeout acceptance suite."""
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migration-prep"
sys.path.insert(0, str(MIGRATION))
SPEC = importlib.util.spec_from_file_location(
    "migration_closeout_acceptance", MIGRATION / "test_closeout_package.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CloseoutPackageTests = MODULE.CloseoutPackageTests

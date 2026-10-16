"""Run the established transaction suite against the generated next publisher."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.pr122_site_hub_release_delta import publisher_source
from tests import test_pr122_website_release as legacy

def main():
    with tempfile.TemporaryDirectory(prefix='hub-publisher-regression-') as td:
        root=Path(td);root.chmod(0o755)
        code=root/'scripts/pr122_website_release.py';code.parent.mkdir();code.write_bytes(publisher_source())
        spec=importlib.util.spec_from_file_location('hub_generated_publisher',code)
        candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
        # Both direct calls and actual CLI subprocesses use the candidate bytes.
        legacy.release=candidate;legacy.ROOT=root
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(legacy.ReleaseTest))
        receipt={'scope':'Generated publisher in disposable temporary directories only','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'production_effects':0}
        print('HUB_GENERATED_PUBLISHER_REGRESSION='+json.dumps(receipt),flush=True)
        return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())

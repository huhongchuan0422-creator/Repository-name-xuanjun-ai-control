"""Cross-module contract: real bootstrap plan/install output, Owner enrollment,
and helper verification against the same local filesystem transaction.
Only external ownership/host/interpreter identity/approval transport are fixtures.
No host command is invoked.
"""
import ast
import contextlib
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_domestic_bootstrap as fixtures
import test_domestic_owner as owner_fixture

b=fixtures.b
m=owner_fixture.m
h=owner_fixture.h

class CrossModuleTests(unittest.TestCase):
    def test_real_plan_owner_enrollment_and_continuity(self):
        fixture=fixtures.BootstrapTests('runTest');fixture.setUp();self.addCleanup(fixture.doCleanups)
        actual_plan=b.plan()  # Real baseline()/bundle()/filesystem, no invented baseline.
        b.install()
        persisted=json.loads((b.CONTROL/'plan.json').read_bytes())
        self.assertEqual(actual_plan,persisted)
        self.assertIn('interpreter',persisted['baseline'])
        with contextlib.ExitStack() as stack:
            for module in (h,m):
                for name,val in {'BASE':str(b.BASE),'CONTROL':str(b.CONTROL),'HELPER':str(b.HELPER),
                                 'TRUST':str(b.BASE/'READONLY_ADMISSION_TRUST.json'),
                                 'RECEIPT':str(b.BASE/'readonly-admission-20261017')}.items():
                    if hasattr(module,name):stack.enter_context(patch.object(module,name,val))
            stack.enter_context(patch.object(h,'CHANNEL',str(b.BASE/'channel.py')))
            stack.enter_context(patch.object(h,'WRAPPER',str(b.EXEC)))
            stack.enter_context(patch.object(h,'POLICY',str(b.POLICY)))
            stack.enter_context(patch.object(h,'CHANNEL_SHA',b.OLD_CODE))
            stack.enter_context(patch.object(m,'INTENT',str(b.CONTROL/'OWNER_EXECUTE_INTENT.json')))
            def read(path,mode,limit=2097152):
                p=Path(path);raw=b.read(p,mode);s=p.stat();return raw,(s.st_dev,s.st_ino)
            stack.enter_context(patch.object(h,'secure_read',side_effect=read))
            stack.enter_context(patch.object(m,'read_fixed',side_effect=lambda p,mode:read(p,mode)[0]))
            stack.enter_context(patch.object(m,'owner'))
            stack.enter_context(patch.object(m,'load_helper',return_value=h))
            # Execute the actual callback AST from Owner source, not a reimplementation
            # or a fabricated per-module baseline. External module loading is isolated.
            tree=ast.parse((Path(__file__).parents[1]/'domestic_owner.py').read_text())
            callback=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='owner_check_baseline')
            callback_globals={'owner':m.owner,'need':m.need,'read_fixed':m.read_fixed,
                              'CONTROL':m.CONTROL,'expected_plan_raw':(b.CONTROL/'plan.json').read_bytes(),
                              'bootstrap':b,'plan':persisted}
            exec(compile(ast.fix_missing_locations(ast.Module(body=[callback],type_ignores=[])),'actual-owner-baseline-callback','exec'),callback_globals)
            baseline_check=callback_globals['owner_check_baseline']
            stack.enter_context(patch.object(h,'_owner_check_baseline',side_effect=baseline_check,create=True))
            permit,comment,_=owner_fixture.sample()
            permit.update(helper_sha256=b.sha(b.HELPER.read_bytes()),wrapper_sha256=b.sha(b.EXEC.read_bytes()),
                          policy_sha256=b.sha(b.POLICY.read_bytes()),channel_sha256=b.OLD_CODE)
            comment['body']=h.PREFIX+json.dumps(permit)
            body_sha=hashlib.sha256(comment['body'].encode()).hexdigest()
            stack.enter_context(patch.object(h,'fetch_comment',return_value=comment))
            stack.enter_context(patch.object(h,'now',return_value=h.timestamp('2026-10-17T10:10:00Z')))
            run=stack.enter_context(patch.object(m.subprocess,'run',side_effect=AssertionError('NO_HOST_COMMAND')))
            result=m.enroll(123,body_sha,'a'*64)
            self.assertEqual(result['state'],'OWNER_PIN_ENROLLED')
            pin=json.loads(Path(m.TRUST).read_bytes());h.check_files(pin)
            baseline_check();run.assert_not_called()
            # Actual inode changes, not a second manufactured baseline fixture.
            original=b.BASE/'channel.py';backup=b.BASE/'saved-original-channel';original.rename(backup)
            fixture.put(original,backup.read_bytes(),0o444)
            with self.assertRaises(ValueError):h.check_files(pin)
            with self.assertRaises(ValueError):baseline_check()
            original.unlink();backup.rename(original)
            oldgrant=(b.BASE/'grant-state.json').read_bytes()
            fixture.put(b.BASE/'grant-state.json',b'{"state":"GRANTED","drift":true}',0o600)
            with self.assertRaises(ValueError):h.check_files(pin)
            with self.assertRaises(ValueError):baseline_check()
            fixture.put(b.BASE/'grant-state.json',oldgrant,0o600)
            with patch.object(b,'interpreter_identity',return_value={'fixture':'drifted-python'}):
                with self.assertRaises(ValueError):baseline_check()
                with self.assertRaises((ValueError,RuntimeError)):b.verify()
            h.check_files(pin);baseline_check()

if __name__=='__main__':unittest.main()

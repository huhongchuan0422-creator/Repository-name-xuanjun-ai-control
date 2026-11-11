import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock
import zipfile
import continue_dependencies as m


def wheel(name, version, extra=None):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr(name+'.dist-info/METADATA', 'Name: '+name+'\nVersion: '+version+'\n')
        if extra:
            z.writestr(extra, 'bad')
    return b.getvalue()


class ContinuationTests(unittest.TestCase):
    def test_expected_pins_and_transitive_wheels(self):
        rows = {n+'-1-py3-none-any.whl':wheel(n,v) for n,v in
                {'requests':'2', 'cryptography':'3','sqlalchemy':'4','certifi':'5'}.items()}
        self.assertEqual(m.inspect_wheels(rows, {'requests':'2','cryptography':'3','sqlalchemy':'4'})['certifi'], '5')

    def test_wrong_version_refused(self):
        rows = {n+'-1-py3-none-any.whl':wheel(n,'1') for n in ('requests','cryptography','sqlalchemy')}
        with self.assertRaisesRegex(RuntimeError, 'PINNED_WHEEL_VERSION'):
            m.inspect_wheels(rows, {'requests':'2'})

    def test_nonwheel_path_or_embedded_traversal_refused(self):
        for name in ('../a.whl', '/a.whl', 'a.tar.gz'):
            with self.assertRaisesRegex(RuntimeError, 'WHEEL_FILENAME'):
                m.wheel_identity(name, wheel('requests','1'))
        with self.assertRaisesRegex(RuntimeError, 'WHEEL_MEMBER_PATH'):
            m.wheel_identity('a.whl', wheel('requests','1','../escape'))

    def test_unexpected_or_duplicate_package_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_WHEEL_PACKAGE'):
            m.wheel_identity('a.whl', wheel('unapproved-package','1'))
        rows={'a.whl':wheel('requests','1'), 'b.whl':wheel('requests','2'), 'c.whl':wheel('idna','1')}
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_PACKAGE'):
            m.inspect_wheels(rows, {})

    def test_wrong_original_code_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_INSTALLER_CHANGED'):
            m.load_old(b'raise AssertionError("must not execute")')

    def fixture(self, d):
        base=Path(d)/'base'; attempt=Path(d)/'prior'; attempt.mkdir(); (base/'app').mkdir(parents=True)
        files={('x'+str(i)+'.py'):b'# original\n' for i in range(79)}
        manifest={n:{'bytes':len(b), 'sha256':m.digest(b)} for n,b in files.items()}
        for n,b in files.items(): (base/'app'/n).write_bytes(b)
        (base/'source-manifest.json').write_text(json.dumps(manifest))
        (attempt/'failure.json').write_text(json.dumps({'status':'HOLD_PRESERVE_PARTIAL_INSTALL',
            'reason':'DEPENDENCY_STEP_TIMEOUT','retry_allowed':False}))
        (attempt/'started.json').write_text(json.dumps({'package_sha256':'fixed'}))
        old={'BASE':base,'ATTEMPT':attempt,'DOMESTIC':'synthetic',
             'stable':lambda p,limit:Path(p).read_bytes()}
        header={'sources':manifest,'package_sha256':'fixed'}
        return old,header,base,attempt

    def validate(self, old, header):
        with mock.patch.object(m.os,'geteuid',return_value=0), \
             mock.patch.object(m.os,'uname',return_value=types.SimpleNamespace(nodename='synthetic')), \
             mock.patch.object(m.sys,'version_info',(3,11)), \
             mock.patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=1,stdout='')):
            return m.verify_existing(old,header)

    def test_actual_file_hashes_and_old_failure_retained(self):
        with tempfile.TemporaryDirectory() as d:
            old,h,base,a=self.fixture(d); raw=(a/'failure.json').read_bytes()
            self.assertEqual(len(self.validate(old,h)),79)
            self.assertEqual((a/'failure.json').read_bytes(),raw)
            (base/'app/x0.py').write_bytes(b'drift')
            with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'): self.validate(old,h)
            self.assertEqual((a/'failure.json').read_bytes(),raw)

    def test_wrong_prior_failure_or_package_refused(self):
        with tempfile.TemporaryDirectory() as d:
            old,h,base,a=self.fixture(d)
            h['package_sha256']='wrong'
            with self.assertRaisesRegex(RuntimeError,'ORIGINAL_PACKAGE_CHANGED'): self.validate(old,h)
            (a/'failure.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'WRONG_PRIOR_FAILURE'): self.validate(old,h)

    def test_existing_success_refuses_replay(self):
        with tempfile.TemporaryDirectory() as d:
            old,h,base,a=self.fixture(d); (a/'receipt.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'ORIGINAL_ALREADY_SUCCEEDED'): self.validate(old,h)

    def test_corrupted_transfer_rejected_before_continuation_creation(self):
        old={'PINS':{},'interrupted':lambda *a:None,'absent':mock.Mock()}
        with mock.patch.object(m,'load_old',return_value=old), mock.patch.object(m,'verify_existing',return_value={}), \
             mock.patch.object(m.signal,'signal'), mock.patch.object(m.os,'umask'):
            with self.assertRaisesRegex(RuntimeError,'TRANSFER_DIGEST'):
                m.receive({'original':'','tar_sha256':'0'*64},io.BytesIO(b'bad'))


if __name__=='__main__': unittest.main()

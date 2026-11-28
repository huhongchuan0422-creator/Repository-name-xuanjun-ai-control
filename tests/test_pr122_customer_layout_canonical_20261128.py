"""Synthetic direct-boundary tests for the verified-host layout adaptations (20261128).

Covers exactly three pinned layout facts, fail-closed elsewhere:
1. /usr/bin/sudo canonical 0o4111 (AL8/Anolis) instead of the old 0755/4755-only tuple.
2. __pycache__/*.pyc with st_nlink==2 (dnf hardlink dedup) tolerated ONLY inside
   declared fixed roots / declared vendor package directories; every other file
   stays nlink==1 and the closure equality is unchanged.
3. ldd alias paths normalize only through /lib64->usr/lib64 and /lib->usr/lib.
No host mutation, no root, all fixtures synthetic.
"""
import ast
import hashlib
import os
import pathlib
import stat
import tempfile
import types
import unittest
from scripts.pr122_customer_runtime import Denied as RuntimeDenied
from scripts.pr122_customer_runtime import _is_declared_pyc,_protected_input_ok,canonical_system_path
from scripts.pr122_account_admission.approved_account_prepare import tool_shape_ok,TOOL_CANONICAL_MODES

def frow(mode,nlink=1,uid=0,gid=0,kind=stat.S_IFREG,size=10):
    return types.SimpleNamespace(st_uid=uid,st_gid=gid,st_mode=kind|mode,st_nlink=nlink,st_size=size)

class SudoPasswdShape(unittest.TestCase):
    def test_canonical_sudo_4111_accepted(self):
        self.assertTrue(tool_shape_ok('/usr/bin/sudo',frow(0o4111)))
        self.assertTrue(tool_shape_ok('/usr/bin/sudo',frow(0o4755)))
        self.assertTrue(tool_shape_ok('/usr/bin/sudo',frow(0o755)))
        self.assertTrue(tool_shape_ok('/usr/bin/passwd',frow(0o4755)))
        self.assertTrue(tool_shape_ok('/usr/bin/passwd',frow(0o755)))
    def test_not_a_general_setuid_permission(self):
        self.assertFalse(tool_shape_ok('/usr/bin/passwd',frow(0o4111)))   # pinned per path
        self.assertFalse(tool_shape_ok('/usr/bin/sudo',frow(0o4255)))     # any extra bit
        self.assertFalse(tool_shape_ok('/usr/bin/sudo',frow(0o4111,nlink=2)))  # hardlink still no
        self.assertFalse(tool_shape_ok('/usr/bin/sudo',frow(0o4111,uid=1000)))
        self.assertFalse(tool_shape_ok('/usr/bin/sudo',frow(0o4111,gid=1)))
        self.assertFalse(tool_shape_ok('/usr/bin/sudo',frow(0o4111,kind=stat.S_IFDIR)))
    def test_allowlist_covers_only_the_two_tools(self):
        self.assertEqual(set(TOOL_CANONICAL_MODES),{'/usr/bin/sudo','/usr/bin/passwd'})

class ProtectedInputShape(unittest.TestCase):
    def test_nlink2_only_for_declared_pyc(self):
        self.assertTrue(_protected_input_ok(frow(0o644),1000))
        self.assertTrue(_protected_input_ok(frow(0o644,nlink=2),1000,declared_pyc=True))
        self.assertFalse(_protected_input_ok(frow(0o644,nlink=2),1000))
        self.assertFalse(_protected_input_ok(frow(0o644,nlink=3),1000,declared_pyc=True))
        self.assertFalse(_protected_input_ok(frow(0o664,nlink=2),1000,declared_pyc=True))
        self.assertFalse(_protected_input_ok(frow(0o4644,nlink=2),1000,declared_pyc=True))
        self.assertFalse(_protected_input_ok(frow(0o644,nlink=2,uid=1000),1000,declared_pyc=True))
        self.assertFalse(_protected_input_ok(frow(0o644,size=1001),1000))
    def test_pyc_pattern_shape(self):
        self.assertTrue(_is_declared_pyc('/usr/lib/python3.11/site-packages/urllib3/util/__pycache__/retry.cpython-311.pyc'))
        self.assertTrue(_is_declared_pyc('/usr/lib/python3.11/json/__pycache__/decoder.cpython-311.pyc'))
        self.assertFalse(_is_declared_pyc('/usr/lib/python3.11/site-packages/urllib3/util/retry.py'))
        self.assertFalse(_is_declared_pyc('/usr/lib/python3.11/site-packages/__pycache__'))
        self.assertFalse(_is_declared_pyc('/usr/lib/python3.11/site-packages/x/__pycache__/y.so'))

class SystemLibraryAlias(unittest.TestCase):
    def test_non_alias_paths_unchanged(self):
        self.assertEqual(canonical_system_path('/usr/lib64/libc.so.6'),pathlib.Path('/usr/lib64/libc.so.6'))
        self.assertEqual(canonical_system_path('/etc/shadow'),pathlib.Path('/etc/shadow'))
    def test_alias_normalizes_to_canonical(self):
        if not pathlib.Path('/lib64').is_symlink():self.skipTest('environment without /lib64 alias')
        self.assertEqual(canonical_system_path('/lib64/libc.so.6'),pathlib.Path('/usr/lib64/libc.so.6'))
        self.assertEqual(str(canonical_system_path('/lib64')),str(pathlib.Path('/usr/lib64')))
    def test_alias_traversal_fails_closed(self):
        if not pathlib.Path('/lib64').is_symlink():self.skipTest('environment without /lib64 alias')
        with self.assertRaises(RuntimeDenied):canonical_system_path('/lib64/../../etc/shadow')
        with self.assertRaises(RuntimeDenied):canonical_system_path('/lib64/x/../../../etc/shadow')
    def test_unexpected_alias_shape_fails_closed(self):
        # /lib (not present as the expected symlink in every environment) must never
        # be trusted blindly: either absent (OSError from lstat) or SYSTEM_ALIAS_SHAPE.
        p=pathlib.Path('/lib')
        if not p.is_symlink() or os.readlink(p)!='usr/lib':
            if p.exists() or p.is_symlink():
                with self.assertRaises((RuntimeDenied,OSError)):canonical_system_path('/lib/x.so')
            self.skipTest('/lib is not the fixed distribution alias here')
        self.assertEqual(canonical_system_path('/lib/x.so'),pathlib.Path('/usr/lib/x.so'))

class IsolatedRuntimeGuardBehaviour(unittest.TestCase):
    """Executes the real guard source literal from channel_binding against a synthetic
    site-packages tree with the fixed site path substituted; secure()/need() trust
    stubs only replace the root-ownership probe that needs uid 0."""
    def guard(self):
        import scripts.pr122_customer_channel_binding as cb
        src=open(cb.__file__).read()
        lit=next(n for n in ast.walk(ast.parse(src)) if isinstance(n,ast.Constant)
                 and isinstance(n.value,str) and 'def verify_isolated_runtime' in n.value).value
        return lit
    def run_guard(self,root,expected,nlinks):
        lit=self.guard()
        site=pathlib.Path(root)/'venv/lib/python3.11/site-packages'
        code=lit.replace("'/usr/local/lib/xuanjun-customer-runtime/venv/lib/python3.11/site-packages'",repr(str(site)))
        real=os.lstat
        class P(pathlib.PosixPath):
            def lstat(self):
                s=real(self)
                rel=str(self.relative_to(site)).replace(os.sep,'/')
                return types.SimpleNamespace(st_uid=0,st_gid=0,
                    st_mode=(stat.S_IFDIR if stat.S_ISDIR(s.st_mode) else stat.S_IFREG)|0o644,
                    st_nlink=nlinks.get(rel,s.st_nlink),st_size=s.st_size)
            def relative_to(self,*a):
                return P(super().relative_to(*a))
            def read_bytes(self):return super().read_bytes()
        ns={'Path':P,'os':types.SimpleNamespace(walk=lambda p,followlinks=False:os.walk(str(p),followlinks=followlinks)),
            'stat':stat,'sys':types.SimpleNamespace(path=[]),'EXPECTED_VENDOR_FILES':expected,
            'secure':lambda p,directory=False:None,
            'need':lambda c,r='DENIED':c or (_ for _ in ()).throw(RuntimeError(r)),
            'sha':lambda b:hashlib.sha256(b).hexdigest(),'expected':expected}
        exec(compile(ast.parse(code),'guard-test','exec'),ns)
        ns['verify_isolated_runtime']()
    def tree(self,root,files,pycache):
        site=pathlib.Path(root)/'venv/lib/python3.11/site-packages'
        for rel,data in {**files,**pycache}.items():
            p=site/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    def sha(self,root,rel):
        return hashlib.sha256((pathlib.Path(root)/'venv/lib/python3.11/site-packages'/rel).read_bytes()).hexdigest()
    def test_declared_pycache_nlink2_tolerated_closure_intact(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init','urllib3-2.0.7.dist-info/RECORD':b'rec'}
            pyc={'urllib3/__pycache__/__init__.cpython-311.pyc':b'cache'}
            self.tree(root,files,pyc)
            expected={k:self.sha(root,k) for k in files}
            self.run_guard(root,expected,{'urllib3/__pycache__/__init__.cpython-311.pyc':2})
    def test_non_pyc_hardlink_still_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init'}
            self.tree(root,files,{})
            with self.assertRaises(RuntimeError):
                self.run_guard(root,{k:self.sha(root,k) for k in files},{'urllib3/__init__.py':2})
    def test_rogue_source_file_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init'}
            self.tree(root,files,{})
            (pathlib.Path(root)/'venv/lib/python3.11/site-packages'/'urllib3'/'evil.py').write_bytes(b'x')
            with self.assertRaises(RuntimeError):
                self.run_guard(root,{k:self.sha(root,k) for k in files},{})
    def test_pyc_under_undeclared_package_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init'}
            pyc={'rogue/__pycache__/x.cpython-311.pyc':b'cache'}
            self.tree(root,files,pyc)
            with self.assertRaises(RuntimeError):
                self.run_guard(root,{k:self.sha(root,k) for k in files},
                               {'rogue/__pycache__/x.cpython-311.pyc':2})
    def test_top_level_orphan_pycache_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init'}
            pyc={'__pycache__/x.cpython-311.pyc':b'cache'}
            self.tree(root,files,pyc)
            with self.assertRaises(RuntimeError):
                self.run_guard(root,{k:self.sha(root,k) for k in files},
                               {'__pycache__/x.cpython-311.pyc':2})
    def test_tampered_pinned_bytes_rejected_despite_pycache(self):
        with tempfile.TemporaryDirectory() as root:
            files={'urllib3/__init__.py':b'init'}
            pyc={'urllib3/__pycache__/__init__.cpython-311.pyc':b'cache'}
            self.tree(root,files,pyc)
            with self.assertRaises(RuntimeError):
                self.run_guard(root,{'urllib3/__init__.py':'0'*64},{'urllib3/__pycache__/__init__.cpython-311.pyc':2})

if __name__=='__main__':unittest.main()

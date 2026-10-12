import importlib.util
import pathlib
import os
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('syntax',pathlib.Path(__file__).parents[1]/'scripts/native_syntax_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


class SyntaxTests(unittest.TestCase):
    def test_python_quotes_brackets_indent_return(self):
        for code in (b'x="oops\n',b'x=[1,2\n',b'def f():\npass\n',b'return 1\n'):
            r=gate.check_bytes('src/a.py',code)
            self.assertEqual(r['state'],'REJECT_SYNTAX');self.assertFalse(r['code_executed'])

    def test_shell_quotes_and_block(self):
        for code in (b'echo "oops\n',b'if true; then\necho hi\n'):
            self.assertEqual(gate.check_bytes('src/a.sh',code)['state'],'REJECT_SYNTAX')

    def test_javascript_quotes_and_brackets(self):
        for code in (b'const x="oops\n',b'const x=[1,2;'):
            self.assertEqual(gate.check_bytes('src/a.js',code)['state'],'REJECT_SYNTAX')

    def test_valid_languages(self):
        for path,raw in [('a.py',b'x=1\n'),('a.sh',b'echo "ok"\n'),('a.js',b'export const x=1;\n'),('a.cjs',b'module.exports=1;\n'),('a.json',b'{"x":1}\n')]:
            self.assertEqual(gate.check_bytes(path,raw)['state'],'PASS_SYNTAX')

    def test_no_submitted_side_effect(self):
        with tempfile.TemporaryDirectory() as d:
            target=pathlib.Path(d)/'must-not-exist'
            for path,raw in [('a.py',('open(%r,"w").write("bad")\n'%str(target)).encode()),('a.sh',('echo "$(touch %s)"\n'%target).encode()),('a.js',('require("fs").writeFileSync(%r,"bad");\n'%str(target)).encode())]:
                self.assertEqual(gate.check_bytes(path,raw)['state'],'PASS_SYNTAX')
                self.assertFalse(target.exists())

    def test_json_duplicates_and_trailing_comma(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":1,}',b'{"x":NaN}'):
            self.assertEqual(gate.check_bytes('a.json',raw)['state'],'REJECT_SYNTAX')

    def test_invalid_encoding_and_limits(self):
        for raw in (b'\xff',b'x=1\r\n',b'x=\x00'):
            self.assertEqual(gate.check_bytes('a.py',raw)['state'],'REJECT_ENCODING')
        for path,raw in [('../a.py',b'x=1'),('/a.py',b'x=1'),('a.py',b'x'*131073)]:
            with self.assertRaises(ValueError):gate.check_bytes(path,raw)

    def test_typescript_missing_checker_is_hold(self):
        self.assertEqual(gate.check_bytes('a.ts',b'const a: number = 1;')['state'],'HOLD_TYPESCRIPT_CHECKER_UNAVAILABLE')

    @unittest.skipUnless(os.environ.get('XJ_TYPESCRIPT_MODULE'),'operator-owned TypeScript dependency not installed locally')
    def test_typescript_real_checker(self):
        module=os.environ['XJ_TYPESCRIPT_MODULE']
        self.assertEqual(gate.check_bytes('a.ts',b'const a: number = 1;',module)['state'],'PASS_SYNTAX')
        self.assertEqual(gate.check_bytes('a.ts',b'const a: number = ;',module)['state'],'REJECT_SYNTAX')

    def test_typescript_arbitrary_module_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            module=pathlib.Path(root)/'evil.js'
            module.write_text('throw new Error("must not load")')
            self.assertEqual(gate.check_bytes('a.ts',b'const x=1;',str(module))['state'],'HOLD_TYPESCRIPT_CHECKER_UNAVAILABLE')

    def test_hash_changes_when_code_changes(self):
        self.assertNotEqual(gate.check_bytes('a.py',b'x=1')['sha256'],gate.check_bytes('a.py',b'x=2')['sha256'])


if __name__=='__main__':unittest.main()

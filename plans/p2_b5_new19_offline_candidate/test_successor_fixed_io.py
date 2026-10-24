"""Fixed IO boundary tests; no host mutation or systemctl execution."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT),str(ROOT/'reused-6825'),
                str(ROOT/'successor_controller')]
from pr17_b5_successor_fixed_io import FixedR2IO
import pr17_b5_successor_review as c53


class FixedIOTests(unittest.TestCase):
    def setUp(self):
        self.spec=json.loads((ROOT/'SUCCESSOR_SPEC.json').read_bytes())
        self.io=FixedR2IO(self.spec)

    def test_exact_journal_and_runtime_paths(self):
        job=self.io.job
        self.assertEqual(self.io._path(job+'/reservation.json'),
                         job+'/reservation.json')
        self.assertEqual(self.io._path(job+'/checkpoint-001.json'),
                         job+'/checkpoint-001.json')
        rid=next(iter(self.io.ids))
        self.assertEqual(self.io._path(job+'/intake-'+rid+'.intent.json'),
                         job+'/intake-'+rid+'.intent.json')
        name=next(iter(self.io.runtime_files))
        self.assertEqual(self.io._path(self.io.stage[0]+'/'+name),
                         self.io.stage[0]+'/'+name)

    def test_arbitrary_child_and_command_rejected_without_side_effect(self):
        for path in (self.io.job+'/arbitrary',
                     self.io.job+'/checkpoint-9999.json',
                     self.io.stage[0]+'/etc/passwd',
                     self.io.target[0]+'/arbitrary',
                     self.io.job+'/../other'):
            with self.subTest(path=path),self.assertRaises(c53.Hold):
                self.io._path(path)
        for argv in (['/bin/sh','-c','true'],
                     ['/usr/bin/systemctl','restart','unrelated.service']):
            with self.subTest(argv=argv),self.assertRaisesRegex(
                    c53.Hold,'FIXED_IO_COMMAND_SCOPE'):
                self.io.command(argv,1)
        with self.assertRaisesRegex(c53.Hold,'FIXED_IO_WRITE_SCOPE'):
            self.io.newfile(self.io.job+'/reservation.json',b'{}',0o644)
        with self.assertRaisesRegex(c53.Hold,'FIXED_IO_DIR_MODE'):
            self.io.mkdir(self.io.job,0o755)


if __name__ == '__main__':
    unittest.main()

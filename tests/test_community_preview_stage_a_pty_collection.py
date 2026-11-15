"""Exercise the original PTY collector AST with fake OS/clock objects only.

No PTY, socket, fork, process, file-permission, or production calls are made.
The original completion and exit assertions execute, not a rewritten collector.
"""
import ast
import errno
import json
from pathlib import Path
import types
import unittest


SOURCE = Path(__file__).with_name('test_community_preview_stage_a.py')
TREE = ast.parse(SOURCE.read_text())
METHOD = next(n for n in ast.walk(TREE)
              if isinstance(n, ast.FunctionDef) and n.name == 'production_confirm_pty')
START = next(i for i, n in enumerate(METHOD.body)
             if isinstance(n, ast.Assign)
             and any(isinstance(x, ast.Name) and x.id == 'data' for x in n.targets))
BODY = METHOD.body[START:]
SCOPE = 'a' * 64


def output(mode='cleanup'):
    phases = ('INSTALL',) if mode in ('eof', 'wrong', 'timeout', 'exception') else ('INSTALL', 'IMAGE_LOAD')
    prompts = ''.join('APPROVE_' + phase + ' ' + SCOPE + '\n' for phase in phases)
    completion = {'state': 'HOLD_STAGE_A_INPUT_CONTEXT_OR_COMPLETION',
                  'child_exit': 2, 'stage_a_result_valid': False}
    child = {'record': 'SUDO_CHILD_EXIT', 'child_exit': 2}
    return (prompts + 'TTY_FD_CLOSED\n' + json.dumps(completion) + '\n'
            + json.dumps(child) + '\nPARENT_ALIVE\n').encode()


class CollectorFixture:
    def __init__(self, case, ending='EIO', ready_after=3, mode='cleanup',
                 status=0, raw=None, kill_missing=False, reap_error=False):
        self.case = case
        self.ending = ending
        self.ready_after = ready_after
        self.mode = mode
        self.status = status
        self.raw = output(mode) if raw is None else raw
        self.kill_missing = kill_missing
        self.reap_error = reap_error
        self.now = 0
        self.reads = 0
        self.polls = 0
        self.events = []
        self.sleeps = []
        self.writes = []

    def monotonic(self):
        self.now += .001
        return self.now

    def sleep(self, duration):
        self.case.assertGreaterEqual(duration, 0)
        self.case.assertLessEqual(duration, .01)
        self.sleeps.append((self.now, duration))
        self.now += duration

    def read(self, fd, size):
        self.case.assertEqual((fd, size), (9, 65536))
        self.reads += 1
        if self.reads == 1:
            return self.raw
        if self.reads > 2:
            raise AssertionError('Read attempted again after stream closure')
        if self.ending == 'EIO':
            raise OSError(errno.EIO, 'synthetic PTY closure')
        if self.ending == 'ERROR':
            raise OSError(errno.EBADF, 'synthetic unrelated read error')
        return b''

    def waitpid(self, pid, flags):
        self.case.assertEqual(pid, 123)
        self.events.append(('waitpid', flags))
        if flags == 0:
            if self.reap_error:
                raise ChildProcessError('synthetic cleanup reap failure')
            return pid, self.status
        self.case.assertEqual(flags, 1)
        self.polls += 1
        if self.ready_after is not None and self.polls >= self.ready_after:
            return pid, self.status
        return 0, 0

    def kill(self, pid, sig):
        self.case.assertEqual((pid, sig), (123, 9))
        self.events.append(('kill', pid))
        if self.kill_missing:
            raise ProcessLookupError('synthetic child-exit race')

    def run(self):
        fakeos = types.SimpleNamespace(
            WNOHANG=1, read=self.read, waitpid=self.waitpid, kill=self.kill,
            close=lambda fd: self.events.append(('close', fd)),
            write=lambda fd, value: self.writes.append((fd, value)),
            waitstatus_to_exitcode=lambda status: status >> 8)
        ns = {'self': self.case, 'pid': 123, 'master': 9, 'scope': SCOPE,
              'mode': self.mode, 'os': fakeos, 'errno': errno,
              'signal': types.SimpleNamespace(SIGKILL=9), 'json': json,
              'time': types.SimpleNamespace(monotonic=self.monotonic, sleep=self.sleep),
              'select': types.SimpleNamespace(select=lambda *args: ([9], [], []))}
        function = ast.FunctionDef(
            name='collect', args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                                               kw_defaults=[], defaults=[]),
            body=BODY, decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        exec(compile(module, str(SOURCE) + ' [original collector AST]', 'exec'), ns)
        return ns['collect']()


class StageAPtyCollection(unittest.TestCase):
    def test_eio_before_reap_waits_within_original_budget(self):
        f = CollectorFixture(self)
        self.assertEqual(f.run(), 2)
        self.assertEqual(f.reads, 2)
        self.assertEqual(f.polls, 3)
        self.assertTrue(f.sleeps)
        self.assertLess(f.now, 4)
        self.assertEqual(f.events[-1], ('close', 9))
        self.assertFalse(any(e[0] == 'kill' for e in f.events))

    def test_eof_before_reap_waits_without_reading_closed_stream(self):
        f = CollectorFixture(self, ending='EOF', ready_after=5)
        self.assertEqual(f.run(), 2)
        self.assertEqual(f.reads, 2)
        self.assertEqual(f.polls, 5)
        self.assertLess(f.now, 4)

    def test_eof_mode_keeps_exact_eot_answer(self):
        f = CollectorFixture(self, ending='EOF', mode='eof')
        self.assertEqual(f.run(), 1)
        self.assertEqual(f.writes, [(9, b'\x04')])

    def test_timeout_mode_does_not_inject_answers(self):
        f = CollectorFixture(self, mode='timeout')
        self.assertEqual(f.run(), 0)
        self.assertEqual(f.writes, [])

    def test_no_prompt_means_no_answer(self):
        raw = output().split(b'TTY_FD_CLOSED', 1)[1]
        f = CollectorFixture(self, raw=b'TTY_FD_CLOSED' + raw)
        self.assertEqual(f.run(), 0)
        self.assertEqual(f.writes, [])

    def test_true_timeout_still_fails_and_cleans_up(self):
        f = CollectorFixture(self, ready_after=None)
        with self.assertRaises(AssertionError):
            f.run()
        self.assertGreaterEqual(f.now, 4)
        self.assertLess(f.now, 4.01)
        self.assertTrue(all(start + duration <= 4.001 for start, duration in f.sleeps))
        self.assertEqual(f.events[-3:], [('kill', 123), ('waitpid', 0), ('close', 9)])

    def test_exit_race_during_kill_still_reaps_and_closes(self):
        f = CollectorFixture(self, ready_after=None, kill_missing=True)
        with self.assertRaises(AssertionError):
            f.run()
        self.assertEqual(f.events[-3:], [('kill', 123), ('waitpid', 0), ('close', 9)])

    def test_reap_error_still_closes_master(self):
        f = CollectorFixture(self, ready_after=None, reap_error=True)
        with self.assertRaises(ChildProcessError):
            f.run()
        self.assertEqual(f.events[-1], ('close', 9))

    def test_nonzero_exit_is_not_success(self):
        f = CollectorFixture(self, status=256)
        with self.assertRaisesRegex(AssertionError, '1 != 0'):
            f.run()
        self.assertEqual(f.events[-1], ('close', 9))
        self.assertFalse(any(e[0] == 'kill' for e in f.events))

    def test_unrelated_read_error_is_not_treated_as_eof(self):
        f = CollectorFixture(self, ending='ERROR')
        with self.assertRaises(OSError) as caught:
            f.run()
        self.assertEqual(caught.exception.errno, errno.EBADF)
        self.assertEqual(f.events[-3:], [('kill', 123), ('waitpid', 0), ('close', 9)])

    def test_missing_receipt_still_fails(self):
        f = CollectorFixture(self, raw=b'TTY_FD_CLOSED\nPARENT_ALIVE\n')
        with self.assertRaises(AssertionError):
            f.run()

    def test_wrong_child_receipt_still_fails(self):
        f = CollectorFixture(self, raw=output().replace(b'"SUDO_CHILD_EXIT"', b'"OTHER"'))
        with self.assertRaises(AssertionError):
            f.run()

    def test_missing_parent_marker_still_fails(self):
        f = CollectorFixture(self, raw=output().replace(b'PARENT_ALIVE', b'OTHER'))
        with self.assertRaises(AssertionError):
            f.run()

    def test_original_four_second_deadline_is_unchanged(self):
        end = next(n.value for n in BODY if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'end' for t in n.targets))
        self.assertEqual(ast.dump(end), ast.dump(ast.parse('time.monotonic()+4', mode='eval').body))


if __name__ == '__main__':
    unittest.main()

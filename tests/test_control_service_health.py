import subprocess
import unittest
from scripts.control_service_health import UNITS, PROPERTIES, observe_service, parse_properties


def raw(unit=UNITS[0], **changes):
    values = dict(Id=unit, LoadState='loaded', ActiveState='active',
                  SubState='running', MainPID='123', Result='success')
    values.update(changes)
    return ('\n'.join(key + '=' + values[key] for key in PROPERTIES) + '\n').encode()


class Result:
    returncode = 0
    stdout = raw()


class Tests(unittest.TestCase):
    def test_fixed_readonly_command(self):
        calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs)); return Result()
        result = observe_service(UNITS[0], run=run, clock=lambda: 100)
        args, kw = calls[0]
        self.assertEqual(args[:3], ['/usr/bin/systemctl', 'show', UNITS[0]])
        self.assertEqual(args[-1], '--property=' + ','.join(PROPERTIES))
        self.assertNotIn('shell', kw)
        self.assertEqual(kw['timeout'], 3)
        self.assertEqual(set(kw['env']), {'PATH','LC_ALL','SYSTEMD_COLORS','SYSTEMD_PAGER'})
        self.assertEqual(result['state'], 'OBSERVED')
        self.assertFalse(result['service_mutation_performed'])

    def test_activity_not_progress(self):
        result = observe_service(UNITS[0], run=lambda *a, **k: Result(), clock=lambda: 100)
        self.assertEqual(result['model_readiness'], 'UNKNOWN')
        self.assertEqual(result['task_progress'], 'UNKNOWN')

    def test_unknown_unit_never_runs(self):
        calls = []
        for unit in ('bad.service', '--help', UNITS[0] + ';reboot', '../a', ''):
            with self.assertRaises(ValueError):
                observe_service(unit, run=lambda *a, **k: calls.append(a))
        self.assertEqual(calls, [])

    def test_every_unit(self):
        for unit in UNITS:
            self.assertEqual(parse_properties(unit, raw(unit))['Id'], unit)

    def test_pid_type(self):
        self.assertEqual(parse_properties(UNITS[0], raw())['MainPID'], 123)

    def test_invalid_pid(self):
        for value in ('-1', '1.2', 'true', '１', '9'*100, str(2**31), ''):
            with self.assertRaises(ValueError):
                parse_properties(UNITS[0], raw(MainPID=value))

    def test_missing_properties(self):
        for key in PROPERTIES:
            data=b'\n'.join(line for line in raw().splitlines() if not line.startswith(key.encode()+b'='))
            with self.assertRaises(ValueError):parse_properties(UNITS[0], data)

    def test_duplicate_properties(self):
        with self.assertRaises(ValueError):parse_properties(UNITS[0], raw()+b'MainPID=123\n')

    def test_unknown_property(self):
        with self.assertRaises(ValueError):parse_properties(UNITS[0], raw()+b'Environment=SECRET\n')

    def test_wrong_identity(self):
        with self.assertRaises(ValueError):parse_properties(UNITS[0], raw(UNITS[1]))

    def test_bad_enum(self):
        for key in ('LoadState','ActiveState','SubState','Result'):
            with self.assertRaises(ValueError):parse_properties(UNITS[0], raw(**{key:'SECRET'}))

    def test_failed_state_is_not_success(self):
        parsed=parse_properties(UNITS[0], raw(ActiveState='failed',SubState='failed',Result='exit-code'))
        self.assertEqual(parsed['ActiveState'], 'failed')

    def test_input_bounds(self):
        for data in (b'x'*8193, b'\xff', 'not bytes', b''):
            with self.assertRaises((ValueError, UnicodeError)):parse_properties(UNITS[0], data)

    def test_timeout_sanitized(self):
        def fail(*a, **k):raise subprocess.TimeoutExpired('SECRET', 3)
        result=observe_service(UNITS[0],run=fail,clock=lambda:100)
        self.assertEqual(result['reason'],'SYSTEMCTL_TIMEOUT')
        self.assertNotIn('SECRET',repr(result))

    def test_oserror_sanitized(self):
        def fail(*a, **k):raise OSError('SECRET')
        self.assertNotIn('SECRET',repr(observe_service(UNITS[0],run=fail,clock=lambda:100)))

    def test_nonzero_exit(self):
        result=Result();result.returncode=1;result.stdout=b'SECRET'
        value=observe_service(UNITS[0],run=lambda *a,**k:result,clock=lambda:100)
        self.assertEqual(value['state'],'UNKNOWN');self.assertNotIn('SECRET',repr(value))

    def test_invalid_start_clock(self):
        for value in (True, -1, float('nan'), 10**1000):
            self.assertEqual(observe_service(UNITS[0],clock=lambda:value)['reason'],'INVALID_CLOCK')

    def test_clock_drift(self):
        for final in (99, 106, float('inf')):
            times=iter([100,final])
            result=observe_service(UNITS[0],run=lambda *a,**k:Result(),clock=lambda:next(times))
            self.assertEqual(result['state'],'UNKNOWN')


if __name__=='__main__':unittest.main()

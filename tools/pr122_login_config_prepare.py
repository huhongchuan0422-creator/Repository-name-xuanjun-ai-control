"""Offline LOGIN_ONLY configuration preparation; never an installer or acceptance.

No application imports, network, processes, key generation, or production paths.
Real-secret use is for the Owner's own terminal after separate authorization.
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import errno
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
import uuid
import warnings

PROFILE = 'OFFICIAL_LOGIN_ONLY_V1'
ADMIN_FIELDS = frozenset(('deployment_profile', 'keys', 'active_key', 'providers',
                         'backup_key', 'backup_key_ref', 'authority_verify_key'))
RUNTIME_FIELDS = frozenset(('deployment_profile', 'keys', 'active_key', 'providers'))
SMTP_FIELDS = frozenset(('host', 'port', 'tls_mode', 'username', 'sender', 'password'))
BUNDLE_FILES = frozenset(('config.json', 'runtime.json', 'PREPARATION.json'))
MAX_FILE_BYTES = 1_048_576
ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
EMAIL = re.compile(r'[^\s@]{1,100}@[^\s@.]{1,150}\.[^\s@]{2,40}\Z')
DNS_LABEL = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z')
OUTPUT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z')
ERROR_CODES = frozenset(('ADMIN_SCHEMA', 'PROFILE', 'DATA_KEYS', 'ACTIVE_KEY',
    'KEY_ENCODING', 'KEY_LENGTH', 'BACKUP_REFERENCE', 'SMTP_SCHEMA', 'SMTP_HOST',
    'SMTP_PORT', 'SMTP_TLS_MODE', 'SMTP_ADDRESS', 'SMTP_PASSWORD', 'RUNTIME_SCHEMA',
    'PAIR_MISMATCH', 'TTY_REQUIRED', 'HIDDEN_INPUT_UNAVAILABLE', 'INPUT_MISMATCH',
    'INPUT_INTERRUPTED', 'INPUT_FAILED', 'PORT_INPUT', 'PATH_POLICY', 'NONROOT_ONLY',
    'DIRECTORY_POLICY', 'FILE_POLICY', 'BUNDLE_MEMBERS', 'BUNDLE_JSON',
    'BUNDLE_INCOMPLETE', 'BUNDLE_DIGEST', 'OUTPUT_EXISTS', 'ATOMIC_PUBLISH_UNAVAILABLE',
    'OUTPUT_FAILED', 'OUTPUT_INTERRUPTED', 'PUBLISH_DURABILITY_UNKNOWN',
    'ARGUMENTS_INVALID', 'PREPARATION_FAILED'))


class ConfigError(ValueError):
    """Only fixed error codes can cross the CLI boundary; never input/exception text."""
    def __init__(self, code):
        self.code = code if type(code) is str and code in ERROR_CODES else 'PREPARATION_FAILED'
        super().__init__(self.code)


def require(condition, code):
    if not condition:
        raise ConfigError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value, limit):
    return (type(value) is str and 0 < len(value) <= limit and
            not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _key(value):
    require(type(value) is str, 'KEY_ENCODING')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        raise ConfigError('KEY_ENCODING') from None
    require(len(raw) == 32, 'KEY_LENGTH')
    require(base64.b64encode(raw).decode('ascii') == value, 'KEY_ENCODING')


def _host(value):
    require(_text(value, 253) and value.isascii(), 'SMTP_HOST')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        require(all(DNS_LABEL.fullmatch(label) for label in value.split('.')), 'SMTP_HOST')


def derive_pair(admin):
    """Validate the bounded minimal schema and derive two separate plain dicts.

    This checks syntax, not key provenance, provider service, backup recovery or
    authority. No new values or keys are generated. Optional contexts are outside
    this deliberately minimal preparation interface, not forbidden in production.
    """
    require(type(admin) is dict and set(admin) == ADMIN_FIELDS, 'ADMIN_SCHEMA')
    require(type(admin['deployment_profile']) is str and admin['deployment_profile'] == PROFILE, 'PROFILE')
    keys = admin['keys']
    require(type(keys) is dict and bool(keys), 'DATA_KEYS')
    for key_id, value in keys.items():
        require(type(key_id) is str and ID.fullmatch(key_id), 'DATA_KEYS')
        _key(value)
    require(type(admin['active_key']) is str and admin['active_key'] in keys, 'ACTIVE_KEY')
    _key(admin['backup_key'])
    _key(admin['authority_verify_key'])
    require(_text(admin['backup_key_ref'], 1024), 'BACKUP_REFERENCE')
    providers = admin['providers']
    require(type(providers) is dict and set(providers) == {'smtp'}, 'SMTP_SCHEMA')
    smtp = providers['smtp']
    require(type(smtp) is dict and set(smtp) == SMTP_FIELDS, 'SMTP_SCHEMA')
    _host(smtp['host'])
    require(type(smtp['port']) is int and 1 <= smtp['port'] <= 65535, 'SMTP_PORT')
    require(type(smtp['tls_mode']) is str and smtp['tls_mode'] in ('starttls', 'implicit_tls'), 'SMTP_TLS_MODE')
    for field in ('username', 'sender'):
        require(_text(smtp[field], 293) and EMAIL.fullmatch(smtp[field]), 'SMTP_ADDRESS')
    require(_text(smtp['password'], 4096), 'SMTP_PASSWORD')
    # JSON cloning follows exact-type checks and never imports production modules.
    try:
        raw = canonical(admin)
    except (ValueError, TypeError, UnicodeError):
        raise ConfigError('ADMIN_SCHEMA') from None
    require(len(raw) <= MAX_FILE_BYTES, 'ADMIN_SCHEMA')
    config = json.loads(raw)
    runtime = json.loads(canonical({k: config[k] for k in RUNTIME_FIELDS}))
    return config, runtime


def validate_pair(admin, runtime):
    _, expected = derive_pair(admin)
    require(type(runtime) is dict and set(runtime) == RUNTIME_FIELDS, 'RUNTIME_SCHEMA')
    try:
        matches = canonical(runtime) == canonical(expected)
    except (ValueError, TypeError, UnicodeError):
        matches = False
    require(matches, 'PAIR_MISMATCH')
    return True


def redacted_report(admin, runtime):
    validate_pair(admin, runtime)
    return {'state': 'OFFLINE_SCHEMA_VALID', 'profile': PROFILE,
            'configuration_pair': 'MATCH', 'secret_values': 'NOT_DISPLAYED',
            'key_provenance': 'NOT_VERIFIED', 'smtp_delivery': 'NOT_VERIFIED',
            'target_acceptance': 'NOT_VERIFIED', 'production': 'NOT_INSTALLABLE'}


def _hidden(prompt):
    require(sys.stdin.isatty() and sys.stdout.isatty(), 'TTY_REQUIRED')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise ConfigError('HIDDEN_INPUT_UNAVAILABLE') from None
    except (EOFError, KeyboardInterrupt):
        raise ConfigError('INPUT_INTERRUPTED') from None
    except Exception:
        raise ConfigError('INPUT_FAILED') from None


def _confirmed(prompt):
    first = _hidden(prompt)
    second = _hidden('Repeat the previous secret: ')
    require(first == second, 'INPUT_MISMATCH')
    return first


def collect_interactive():
    """Hidden TTY only, one existing active data key; never read files or env."""
    require(sys.stdin.isatty() and sys.stdout.isatty(), 'TTY_REQUIRED')
    key_id = _hidden('Existing active data key ID: ')
    data_key = _confirmed('Existing data key (Base64, 32 bytes): ')
    backup_key = _confirmed('Existing backup key (Base64, 32 bytes): ')
    backup_ref = _hidden('Existing backup custody reference: ')
    authority = _confirmed('Existing authority HMAC key (Base64, 32 bytes): ')
    host = _hidden('SMTP host: ')
    port_text = _hidden('SMTP port (decimal integer): ')
    require(type(port_text) is str and re.fullmatch(r'[0-9]{1,5}', port_text), 'PORT_INPUT')
    mode = _hidden('SMTP TLS mode (implicit_tls or starttls): ')
    username = _hidden('SMTP complete login email: ')
    sender = _hidden('SMTP complete sender email: ')
    password = _confirmed('Existing SMTP client password: ')
    return derive_pair({'deployment_profile': PROFILE, 'keys': {key_id: data_key},
        'active_key': key_id, 'backup_key': backup_key, 'backup_key_ref': backup_ref,
        'authority_verify_key': authority, 'providers': {'smtp': {
            'host': host, 'port': int(port_text), 'tls_mode': mode,
            'username': username, 'sender': sender, 'password': password}}})


def _path(path):
    try:
        raw = os.fspath(path)
        require(type(raw) is str and raw.startswith('/') and not raw.startswith('//'), 'PATH_POLICY')
        require('\\' not in raw and not any(ord(c) < 32 or ord(c) == 127 for c in raw), 'PATH_POLICY')
        p = Path(raw)
    except (TypeError, ValueError):
        raise ConfigError('PATH_POLICY') from None
    require(p.is_absolute() and p.anchor == '/' and '..' not in p.parts and str(p) == raw, 'PATH_POLICY')
    require(OUTPUT_NAME.fullmatch(p.name), 'PATH_POLICY')
    # This is a user-local preparer, not an alternate production writer. Reject
    # these roots before opening anything, including candidates below them.
    require(not any(p == root or root in p.parents for root in
                    (Path('/etc'), Path('/var'), Path('/usr'), Path('/run'),
                     Path('/proc'), Path('/sys'), Path('/dev'), Path('/root'))), 'PATH_POLICY')
    return p


def _directory_policy(st, *, private=False):
    uid = os.geteuid()
    require(stat.S_ISDIR(st.st_mode) and st.st_uid in (0, uid) and not st.st_mode & 0o022,
            'DIRECTORY_POLICY')
    if private:
        require(st.st_uid == uid and stat.S_IMODE(st.st_mode) == 0o700, 'DIRECTORY_POLICY')


def _directory_fd(path, *, private=False):
    """Walk with directory FDs/O_NOFOLLOW; never resolve a symlink or chown/chmod."""
    require(os.geteuid() != 0, 'NONROOT_ONLY')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        _directory_policy(os.fstat(fd))
        for component in path.parts[1:]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
            _directory_policy(os.fstat(fd))
        _directory_policy(os.fstat(fd), private=private)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _file_bytes(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                 dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid() and
                stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1 and
                0 < before.st_size <= MAX_FILE_BYTES, 'FILE_POLICY')
        raw = bytearray()
        while len(raw) <= MAX_FILE_BYTES:
            block = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) and
                len(raw) == before.st_size, 'FILE_POLICY')
        return bytes(raw)
    finally:
        os.close(fd)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'BUNDLE_JSON')
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ConfigError('BUNDLE_JSON')))
    except (UnicodeError, ValueError, TypeError):
        raise ConfigError('BUNDLE_JSON') from None


def _receipt(config_raw, runtime_raw):
    return {'format': 'OFFLINE_CONFIGURATION_PREPARATION_V1',
            'config_sha256': digest(config_raw), 'runtime_sha256': digest(runtime_raw),
            'production': 'NOT_INSTALLABLE', 'target_acceptance': 'NOT_VERIFIED'}


def _inspect_fd(fd):
    _directory_policy(os.fstat(fd), private=True)
    require(set(os.listdir(fd)) == BUNDLE_FILES, 'BUNDLE_MEMBERS')
    config_raw = _file_bytes(fd, 'config.json')
    runtime_raw = _file_bytes(fd, 'runtime.json')
    receipt_raw = _file_bytes(fd, 'PREPARATION.json')
    config, runtime, receipt = _json(config_raw), _json(runtime_raw), _json(receipt_raw)
    require(type(receipt) is dict and receipt == _receipt(config_raw, runtime_raw), 'BUNDLE_DIGEST')
    validate_pair(config, runtime)
    require(canonical(config) == config_raw and canonical(runtime) == runtime_raw and
            canonical(receipt) == receipt_raw, 'BUNDLE_JSON')
    return redacted_report(config, runtime)


def inspect_bundle(path):
    """Read only an explicitly selected private offline bundle; no acceptance."""
    p = _path(path)
    fd = None
    try:
        fd = _directory_fd(p, private=True)
        return _inspect_fd(fd)
    except ConfigError:
        raise
    except Exception:
        raise ConfigError('BUNDLE_INCOMPLETE') from None
    finally:
        if fd is not None:
            os.close(fd)


def _write_file(fd, name, raw):
    require(0 < len(raw) <= MAX_FILE_BYTES, 'FILE_POLICY')
    out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                  0o600, dir_fd=fd)
    try:
        st = os.fstat(out)
        require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_uid == os.geteuid() and
                stat.S_IMODE(st.st_mode) == 0o600, 'FILE_POLICY')
        view = memoryview(raw)
        while view:
            count = os.write(out, view)
            require(count > 0, 'OUTPUT_FAILED')
            view = view[count:]
        os.fsync(out)
    finally:
        os.close(out)


def _rename_noreplace(parent_fd, source, destination):
    """Linux atomic directory publication; refuse unsupported platforms, no fallback."""
    require(sys.platform.startswith('linux'), 'ATOMIC_PUBLISH_UNAVAILABLE')
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError:
        raise ConfigError('ATOMIC_PUBLISH_UNAVAILABLE') from None
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(parent_fd, os.fsencode(source), parent_fd, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        if number in (errno.EEXIST, errno.ENOTEMPTY):
            raise ConfigError('OUTPUT_EXISTS')
        if number in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise ConfigError('ATOMIC_PUBLISH_UNAVAILABLE')
        raise ConfigError('OUTPUT_FAILED')


def _preflight_output(output_path):
    """Read metadata only before prompting; writing repeats checks under dir FDs."""
    p = _path(output_path)
    require(sys.platform.startswith('linux'), 'ATOMIC_PUBLISH_UNAVAILABLE')
    fd = None
    try:
        fd = _directory_fd(p.parent, private=True)
        try:
            os.stat(p.name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ConfigError('OUTPUT_EXISTS')
    except ConfigError:
        raise
    except Exception:
        raise ConfigError('DIRECTORY_POLICY') from None
    finally:
        if fd is not None:
            os.close(fd)


def write_bundle(output_path, admin):
    """Create a new private offline candidate, never overwrite or install.

    Failures before rename leave only a private staging directory. Do not remove
    evidence or unknown files. A failure after rename reports durability UNKNOWN,
    never an unqualified success; do not retry/overwrite that existing target.
    """
    config, runtime = derive_pair(admin)
    p = _path(output_path)
    parent_fd = stage_fd = None
    published = False
    publication_attempted = False
    try:
        parent_fd = _directory_fd(p.parent, private=True)
        try:
            os.stat(p.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ConfigError('OUTPUT_EXISTS')
        # UUID is a collision-resistant directory name, not a credential/key.
        stage = '.offline-config-incomplete-' + uuid.uuid4().hex
        os.mkdir(stage, 0o700, dir_fd=parent_fd)
        stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                           dir_fd=parent_fd)
        _directory_policy(os.fstat(stage_fd), private=True)
        config_raw, runtime_raw = canonical(config), canonical(runtime)
        _write_file(stage_fd, 'config.json', config_raw)
        _write_file(stage_fd, 'runtime.json', runtime_raw)
        _write_file(stage_fd, 'PREPARATION.json', canonical(_receipt(config_raw, runtime_raw)))
        report = _inspect_fd(stage_fd)
        os.fsync(stage_fd)
        # The syscall may succeed before Python regains control or records its
        # return. An interruption from this point is conservatively UNKNOWN.
        publication_attempted = True
        _rename_noreplace(parent_fd, stage, p.name)
        published = True
        os.fsync(parent_fd)
        return report
    except ConfigError as exc:
        # These helper codes mean an explicit refusal or nonzero syscall result;
        # none are emitted on its successful-return path. Other failures after
        # entering publication have no reliable not-published acknowledgement.
        known_rename_refusal = exc.code in ('OUTPUT_EXISTS', 'ATOMIC_PUBLISH_UNAVAILABLE', 'OUTPUT_FAILED')
        if published or (publication_attempted and not known_rename_refusal):
            raise ConfigError('PUBLISH_DURABILITY_UNKNOWN') from None
        raise
    except (KeyboardInterrupt, EOFError):
        raise ConfigError('PUBLISH_DURABILITY_UNKNOWN' if publication_attempted else 'OUTPUT_INTERRUPTED') from None
    except Exception:
        raise ConfigError('PUBLISH_DURABILITY_UNKNOWN' if publication_attempted else 'OUTPUT_FAILED') from None
    finally:
        close_failed = False
        for fd in (stage_fd, parent_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except BaseException:
                    close_failed = True
        if close_failed:
            raise ConfigError('PUBLISH_DURABILITY_UNKNOWN' if publication_attempted else 'OUTPUT_FAILED') from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ConfigError('ARGUMENTS_INVALID')


def main(argv=None):
    """Default validates in memory. --output explicitly prepares a new local bundle."""
    write_started = False
    try:
        parser = _Parser(description=__doc__)
        parser.add_argument('--output', help='new directory under an existing private user directory')
        args = parser.parse_args(argv)
        # Fail on protected paths before prompting for any real secret.
        if args.output is not None:
            _preflight_output(args.output)
        config, runtime = collect_interactive()
        if args.output:
            write_started = True
            report = write_bundle(args.output, config)
        else:
            report = redacted_report(config, runtime)
        print(json.dumps(report, sort_keys=True))
        return 0
    except ConfigError as exc:
        print(json.dumps({'state': 'UNKNOWN' if exc.code == 'PUBLISH_DURABILITY_UNKNOWN' else 'NOT_PREPARED', 'error': exc.code,
                          'production': 'NOT_INSTALLABLE'}, sort_keys=True), file=sys.stderr)
        return 130 if exc.code in ('INPUT_INTERRUPTED', 'OUTPUT_INTERRUPTED') else 2
    except KeyboardInterrupt:
        code = 'PUBLISH_DURABILITY_UNKNOWN' if write_started else 'INPUT_INTERRUPTED'
        print(json.dumps({'error': code, 'production': 'NOT_INSTALLABLE', 'state': 'UNKNOWN' if code == 'PUBLISH_DURABILITY_UNKNOWN' else 'NOT_PREPARED'}, sort_keys=True), file=sys.stderr)
        return 130
    except Exception:
        code = 'PUBLISH_DURABILITY_UNKNOWN' if write_started else 'PREPARATION_FAILED'
        print(json.dumps({'error': code, 'production': 'NOT_INSTALLABLE', 'state': 'UNKNOWN' if code == 'PUBLISH_DURABILITY_UNKNOWN' else 'NOT_PREPARED'}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

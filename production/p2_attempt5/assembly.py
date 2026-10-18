"""Linux local production adapters; no permit issuance or automatic deployment.

Use only inside the separately SHA-pinned Attempt5 Kit import context. All
service files and every parent must be root-owned and not group/world writable.
No database initialization, grant registration, key generation or cloud dispatch.
"""
import fcntl
import hashlib
import json
import os
import socket
import stat
import struct
import subprocess
import types

LIMIT = 262144


def require(ok, code):
    if not ok:
        raise RuntimeError('P2_PRODUCTION_' + code)


def parent(path):
    require(os.geteuid() == 0, 'ROOT_SERVICE_IDENTITY')
    require(type(path) is str and path.startswith('/') and
            os.path.normpath(path) == path and path != '/', 'ABSOLUTE_PATH')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in path.strip('/').split('/')[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                            os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            require(info.st_uid == 0 and not info.st_mode & 0o022,
                    'PARENT_PROTECTION')
        return fd, path.rsplit('/', 1)[1]
    except BaseException:
        os.close(fd)
        raise


def protected_file(path, private=False):
    directory, leaf = parent(path)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                info.st_uid == 0 and not info.st_mode & 0o022 and
                (not private or stat.S_IMODE(info.st_mode) == 0o600),
                'FILE_PROTECTION')
        return fd
    except BaseException:
        os.close(fd)
        raise


def pinned_module(path, expected_sha256):
    """Only independently approved, standalone deployment adapter code.

    Pin provenance is external approval, never inferred from a file's own hash.
    No sys.path insertion or import from a writable deployment directory.
    """
    fd = protected_file(path)
    try:
        raw = os.read(fd, 1048577)
        require(len(raw) <= 1048576 and
                hashlib.sha256(raw).hexdigest() == expected_sha256, 'ADAPTER_SHA')
    finally:
        os.close(fd)
    module = types.ModuleType('_p2_independently_pinned_deployment_adapter')
    module.__file__ = path
    exec(compile(raw, path, 'exec'), module.__dict__)
    return module


class OpenSSLSigner(object):
    """Real RSA signing through an already provisioned private key FD."""
    def __init__(self, key_path, public_der_sha256):
        self.fd = protected_file(key_path, private=True)
        try:
            public = self._openssl(['pkey', '-pubout', '-outform', 'DER'])
            require(hashlib.sha256(public).hexdigest() == public_der_sha256,
                    'PUBLIC_KEY_TRUST_PIN')
            raw = self._openssl(['rsa', '-noout', '-modulus'])
            self.modulus = int(raw.decode('ascii').strip().split('=')[1], 16)
            require(2048 <= self.modulus.bit_length() <= 4096, 'RSA_WIDTH')
            # The reviewed ReceiptProvider requires exponent 65537. Verify it
            # with a real signature before accepting this signer instance.
            from receipt_provider import ReceiptProvider, canonical
            verifier = ReceiptProvider(lambda unused: None, self.modulus,
                                       65537, 'KEY_SELF_CHECK')
            import base64
            body = {'key_self_check': public_der_sha256}
            verifier._signature(body, base64.b64encode(self(canonical(body))).decode('ascii'))
        except BaseException:
            self.close()
            raise

    def _openssl(self, arguments, raw=None):
        command = ['/usr/bin/openssl'] + arguments
        if arguments[0] in ('pkey', 'rsa'):
            command += ['-in', '/proc/self/fd/' + str(self.fd),
                        '-passin', 'pass:']
        else:
            command += ['-sign', '/proc/self/fd/' + str(self.fd),
                        '-passin', 'pass:']
        return subprocess.check_output(command, input=raw, pass_fds=(self.fd,),
                                       stderr=subprocess.DEVNULL, timeout=10,
                                       env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})

    def __call__(self, raw):
        require(type(raw) is bytes and len(raw) <= LIMIT, 'SIGNING_BOUND')
        return self._openssl(['dgst', '-sha256'], raw)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def receive(connection):
    def exact(size):
        parts = []
        while size:
            raw = connection.recv(size)
            require(bool(raw), 'RPC_INCOMPLETE_UNKNOWN')
            parts.append(raw)
            size -= len(raw)
        return b''.join(parts)
    size = struct.unpack('!I', exact(4))[0]
    require(0 < size <= LIMIT, 'RPC_BOUND')
    raw = exact(size)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda unused: require(False, 'NONFINITE_JSON'))


def send(connection, value):
    from receipt_provider import canonical
    raw = canonical(value)
    require(0 < len(raw) <= LIMIT, 'RPC_BOUND')
    connection.sendall(struct.pack('!I', len(raw)) + raw)


def peer(connection):
    return struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET,
                                                   socket.SO_PEERCRED, 12))


class UnixTransport(object):
    """Authenticated local channel; never retries an ambiguous request."""
    def __init__(self, path, timeout=10):
        require(type(timeout) in (int, float) and 0 < timeout <= 30, 'TIMEOUT')
        self.path, self.timeout = path, timeout

    def __call__(self, request):
        directory, leaf = parent(self.path)
        try:
            info = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and
                    stat.S_IMODE(info.st_mode) == 0o600, 'SOCKET_PROTECTION')
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                connection.settimeout(self.timeout)
                connection.connect('/proc/self/fd/' + str(directory) + '/' + leaf)
                require(peer(connection)[1] == 0, 'SERVER_PEER_IDENTITY')
                send(connection, request)
                return receive(connection)
            finally:
                connection.close()
        finally:
            os.close(directory)


class ProductionIssuer(object):
    """One service/process per existing DB. OS identity supplies principal.

    All root clients are the same explicitly approved execution identity; root
    itself is the trust boundary. This is not remote/multi-user authentication.
    A local socket lock is *additional* exclusion, not global Writer proof.
    """
    def __init__(self, database, socket_path, principal, signer, issuer,
                 host_readback, grant):
        from authority_store import AuthorityStore
        from issuer_service import IssuerService
        require(type(principal) is dict and set(principal) ==
                {'actor_id', 'host', 'writer_id'} and
                all(type(v) is str and 0 < len(v) <= 256 for v in principal.values()),
                'PRINCIPAL')
        require(principal['host'] == os.uname().nodename, 'SERVICE_HOST_BINDING')
        fd = protected_file(database, private=True)
        os.close(fd)
        directory, leaf = parent(database + '.issuer-lock')
        try:
            self.lock = os.open(leaf, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                                0o600, dir_fd=directory)
        finally:
            os.close(directory)
        self.store = self.listener = self.directory = None
        self.socket_identity = None
        try:
            info = os.fstat(self.lock)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                    info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
                    'ISSUER_LOCK_PROTECTION')
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.store = AuthorityStore(database, initialize=False)
            # Existing independently registered Grant only; never register or
            # silently bind an empty/cloned store during service startup.
            self.store._grant(grant)
            from receipt_provider import digest
            self.grant_binding = digest(grant)
            self.service = IssuerService(self.store, host_readback, signer, issuer)
            self.principal = dict(principal)
            self.directory, self.leaf = parent(socket_path)
            try:
                os.stat(self.leaf, dir_fd=self.directory, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('P2_PRODUCTION_SOCKET_EXISTS_HOLD')
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind('/proc/self/fd/' + str(self.directory) + '/' + self.leaf)
            os.chmod(self.leaf, 0o600, dir_fd=self.directory, follow_symlinks=False)
            info = os.stat(self.leaf, dir_fd=self.directory, follow_symlinks=False)
            self.socket_identity = (info.st_dev, info.st_ino)
            self.listener.listen(4)
            self.listener.settimeout(1)
        except BaseException:
            self.close()
            raise

    def serve_one(self):
        connection, unused = self.listener.accept()
        try:
            connection.settimeout(10)
            require(peer(connection)[1] == 0, 'CLIENT_PEER_IDENTITY')
            request = receive(connection)
            try:
                require(type(request) is dict and
                        request.get('grant_sha256') == self.grant_binding,
                        'SERVICE_GRANT_BINDING')
                response = self.service.handle(request, dict(self.principal))
            except Exception:
                # Nothing is rolled back here: commit may already be durable.
                # Client gets HOLD, then uses original signed query/reconcile.
                response = {'hold': 'SERVICE_RESULT_UNKNOWN'}
            send(connection, response)
        finally:
            connection.close()

    def close(self):
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        if self.directory is not None:
            try:
                info = os.stat(self.leaf, dir_fd=self.directory, follow_symlinks=False)
                if self.socket_identity == (info.st_dev, info.st_ino):
                    os.unlink(self.leaf, dir_fd=self.directory)
            except FileNotFoundError:
                pass
            os.close(self.directory)
            self.directory = None
        if self.store is not None:
            self.store.close()
            self.store = None
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None


def native_cycle(driver_factory, ledger_directory, grant, socket_path,
                 modulus, issuer, review_id, source_identity, approved_policy):
    """Assemble real core objects; NativeRecovery enforces concrete Driver
    and independent PR58 approval. No fixture switch or approval injection.
    Call run(command_sha) on the result only under the exact installation permit.
    """
    from attempt_ledger import Ledger
    from native_recovery import NativeRecovery
    from receipt_provider import ReceiptProvider
    from permit_cycle import PermitCycle
    directory, unused = parent(ledger_directory + '/attempts.json')
    try:
        info = os.fstat(directory)
        require(stat.S_IMODE(info.st_mode) == 0o700, 'LEDGER_DIRECTORY')
    finally:
        os.close(directory)
    require(grant['target_host'] == os.uname().nodename and
            grant['target_host'] != 'TEST_ONLY' and issuer != 'TEST_ONLY',
            'LIVE_HOST_BINDING')
    provider = ReceiptProvider(UnixTransport(socket_path), modulus, 65537, issuer)
    def factory():
        return NativeRecovery(driver_factory(), Ledger(ledger_directory, grant),
                              provider, source_identity=source_identity,
                              fixture_mode=False, approval_review_id=review_id,
                              cycle_policy=approved_policy)
    return PermitCycle(factory, approved_policy)

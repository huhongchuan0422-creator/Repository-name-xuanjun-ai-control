"""Private source adapter. No CLI, transport, sudo grant or service mutations.

The default guard refuses unless root on Tokyo observes the fixed Portal unit
inactive and port18080 refused. Admission and all-writer custody remain the
responsibility of a separately reviewed root orchestrator, not caller JSON.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess

from custody import Hold, IDENTIFIER, SOURCE_HOST, SOURCE_SHA256, TARGET_HOST, REFS, require

STATE_ROOT = Path('/opt/trading-system/runtime/secure-secrets-portal')
OPERATIONS_ROOT = Path('/opt/trading-system/runtime/v8-domestic-operations/operations-secretref-store')
ENTRY = Path('/opt/trading-system/scripts/secure_secrets_portal_server.py')


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'DUPLICATE_PRIVATE_JSON_KEY')
        result[key] = value
    return result


class PortalFence:
    """Actual fixed-host service/socket/version checks; does not stop anything."""
    def check(self):
        require(os.geteuid() == 0 and os.uname().nodename == SOURCE_HOST, 'TOKYO_ROOT_REQUIRED')
        try:
            result = subprocess.run(['/usr/bin/systemctl', 'show', 'secure-secrets-portal.service',
                '-p', 'ActiveState', '-p', 'SubState', '-p', 'MainPID'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                check=True, timeout=10, env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C'})
            info = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
            require(info == {'ActiveState':'inactive','SubState':'dead','MainPID':'0'}, 'PORTAL_NOT_FENCED')
            try:
                with socket.create_connection(('127.0.0.1', 18080), timeout=2):
                    raise Hold('PORTAL_LISTENER_REMAINS')
            except OSError as error:
                require(error.errno == errno.ECONNREFUSED, 'PORTAL_SOCKET_FENCE_UNKNOWN')
            fd = os.open(ENTRY, os.O_RDONLY|os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as handle:
                identity = os.fstat(handle.fileno())
                require(stat.S_ISREG(identity.st_mode) and identity.st_uid == 1000
                        and identity.st_nlink == 1 and stat.S_IMODE(identity.st_mode) == 0o755,
                        'PORTAL_SOURCE_IDENTITY_CHANGED')
                data = handle.read(200001)
            require(hashlib.sha256(data).hexdigest() == SOURCE_SHA256, 'PORTAL_SOURCE_VERSION_CHANGED')
            return info
        except Hold:
            raise
        except Exception:
            raise Hold('PORTAL_FENCE_VERIFICATION_UNKNOWN') from None


class PrivateFiles:
    """Read bounded selected files through checked directory descriptors.

    Custom roots/UID exist only for synthetic offline tests or a trusted library
    caller; this class is NOT a privileged command/capability interface.
    """
    def __init__(self, state_root=STATE_ROOT, operations_root=OPERATIONS_ROOT, *, uid=1000):
        self.roots = {'state': Path(state_root).absolute(), 'operations': Path(operations_root).absolute()}
        self.uid = uid
        self.total_bytes = 0
        self.index = []

    def _directory(self, group, parts=()):
        root = self.roots[group]
        require(all(not path.is_symlink() for path in (root, *root.parents)), 'PRIVATE_SOURCE_SYMLINK')
        descriptor = os.open(root, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            self._check_directory(descriptor)
            for part in parts:
                require(part and '/' not in part and part not in ('.','..'), 'PRIVATE_PATH_INVALID')
                child = os.open(part, os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
                self._check_directory(descriptor)
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def _check_directory(self, descriptor):
        info = os.fstat(descriptor)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == self.uid
                and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_SOURCE_DIRECTORY_IDENTITY')

    def read(self, group, parts, *, optional=False, json_object=True):
        require(group in self.roots and isinstance(parts, (tuple, list)) and bool(parts)
                and all(isinstance(part,str) and part and '/' not in part
                        and part not in ('.','..') for part in parts), 'PRIVATE_PATH_INVALID')
        try:
            directory = self._directory(group, parts[:-1])
        except FileNotFoundError:
            if optional:
                return None
            raise Hold('PRIVATE_REQUIRED_DIRECTORY_MISSING') from None
        try:
            try:
                descriptor = os.open(parts[-1], os.O_RDONLY|os.O_NOFOLLOW, dir_fd=directory)
            except FileNotFoundError:
                if optional:
                    return None
                raise Hold('PRIVATE_REQUIRED_FILE_MISSING') from None
            with os.fdopen(descriptor, 'rb') as handle:
                before = os.fstat(handle.fileno())
                require(stat.S_ISREG(before.st_mode) and before.st_uid == self.uid
                        and before.st_nlink == 1 and stat.S_IMODE(before.st_mode) == 0o600,
                        'PRIVATE_SOURCE_FILE_IDENTITY')
                data = handle.read(131073)
                after = os.fstat(handle.fileno())
            fields = ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
            require(all(getattr(before,k) == getattr(after,k) for k in fields), 'PRIVATE_SOURCE_CHANGED_DURING_READ')
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            require(all(getattr(current,k) == getattr(after,k) for k in fields), 'PRIVATE_SOURCE_PATH_REPLACED')
            self.total_bytes += len(data)
            require(len(data) <= 131072 and self.total_bytes <= 2000000, 'PRIVATE_READ_SIZE_LIMIT')
            self.index.append({'group':group, 'parts':list(parts),
                'identity':{k:getattr(after,k) for k in fields}, 'sha256':hashlib.sha256(data).hexdigest()})
            try:
                text = data.decode('utf-8')
                if not json_object:
                    return text
                value = json.loads(text, object_pairs_hook=pairs,
                                   parse_constant=lambda unused: (_ for _ in ()).throw(Hold('NONFINITE_PRIVATE_JSON')))
                require(isinstance(value, dict), 'PRIVATE_JSON_OBJECT_REQUIRED')
                return value
            except (UnicodeError, ValueError, RecursionError):
                raise Hold('PRIVATE_JSON_FORMAT_INVALID') from None
        finally:
            os.close(directory)

    def state_names(self, provider):
        try:
            descriptor = self._directory('state', (provider+'-oauth-state',))
        except FileNotFoundError:
            return []
        try:
            names = os.listdir(descriptor)
            require(len(names) <= 2000, 'PRIVATE_STATE_FILE_LIMIT')
            require(all(re.fullmatch(r'[0-9a-f]{64}\.json', name) for name in names), 'PRIVATE_STATE_DIRECTORY_UNEXPECTED_ENTRY')
            return sorted(names)
        finally:
            os.close(descriptor)

    def revalidate(self):
        # Re-open every selected path after the final guard; reject replacement.
        saved = list(self.index)
        for record in saved:
            descriptor = self._directory(record['group'], tuple(record['parts'][:-1]))
            try:
                info = os.stat(record['parts'][-1], dir_fd=descriptor, follow_symlinks=False)
                require(all(getattr(info,k) == v for k,v in record['identity'].items()), 'PRIVATE_SOURCE_GENERATION_CHANGED')
            finally:
                os.close(descriptor)


def read_fenced_snapshot(*, cutover_id, session_ids, providers, account_identity_hashes,
                         files=None, guard=None):
    """Return private in-memory data; never print, archive or transport it here.

    Root admission must bind this exact reader, selected session IDs/providers,
    expected account hashes and the scope of every writer. The default guard
    covers the fixed Portal only; it does not certify other writers absent.
    The caller MUST retain other sessions/routes and historical private audits.
    """
    require(isinstance(cutover_id, str) and IDENTIFIER.fullmatch(cutover_id), 'CUTOVER_ID_INVALID')
    require(isinstance(session_ids, (list, tuple)) and len(session_ids) <= 1000
            and all(isinstance(x,str) and IDENTIFIER.fullmatch(x) for x in session_ids)
            and len(set(session_ids)) == len(session_ids), 'PRIVATE_SESSION_SCOPE_INVALID')
    require(isinstance(providers, (list, tuple))
            and all(isinstance(x,str) and x in ('douyin','tiktok') for x in providers)
            and len(set(providers)) == len(providers), 'PRIVATE_PROVIDER_SCOPE_INVALID')
    require(isinstance(account_identity_hashes, dict)
            and all(isinstance(k,str) and k in providers and isinstance(v,str)
                    and re.fullmatch('[0-9a-f]{64}',v) for k,v in account_identity_hashes.items()),
            'PRIVATE_ACCOUNT_ANCHOR_SCOPE_INVALID')
    files = files or PrivateFiles()
    guard = guard or PortalFence()
    before = guard.check()
    try:
        snapshot = dict(schema_version=1, source_generation='', cutover_id=cutover_id,
                        sessions=[], secrets={}, oauth_states={}, lifecycles={}, legacy_bindings={})
        for session_id in session_ids:
            session = files.read('state', ('sessions', session_id+'.json'))
            require(session.get('submission_id') == session_id, 'PRIVATE_SESSION_FILENAME_MISMATCH')
            require(set(session.get('required_credential_types', [])) <= set(providers), 'PRIVATE_SESSION_PROVIDER_SCOPE_MISMATCH')
            snapshot['sessions'].append(session)
        for provider in providers:
            for ref in sorted(ref for ref in REFS if REFS[ref] == provider):
                value = files.read('operations', ('values', ref+'.secret'), optional=True, json_object=False)
                metadata = files.read('operations', ('metadata', ref+'.json'), optional=True)
                require((value is None) == (metadata is None), 'PRIVATE_SECRET_PAIR_INCOMPLETE')
                if value is not None:
                    require(metadata.get('ref') == ref and metadata.get('provider') == provider
                            and metadata.get('configured') is True, 'PRIVATE_SECRET_METADATA_MISMATCH')
                    snapshot['secrets'][ref] = dict(metadata, value=value)
            names = files.state_names(provider)
            snapshot['oauth_states'][provider] = []
            for name in names:
                state = files.read('state', (provider+'-oauth-state',name))
                require(state.get('state_hash')+'.json' == name, 'PRIVATE_STATE_FILENAME_MISMATCH')
                snapshot['oauth_states'][provider].append(state)
            require(names == files.state_names(provider), 'PRIVATE_STATE_GENERATION_CHANGED')
            lifecycle = files.read('state', (provider+'-token-state',provider+'_token_lifecycle.json'), optional=True)
            if lifecycle is not None:
                snapshot['lifecycles'][provider] = lifecycle
            if provider == 'tiktok':
                binding = files.read('state', ('tiktok-token-state','tiktok_account_binding.json'), optional=True)
                if binding is not None:
                    snapshot['legacy_bindings'][provider] = binding
        require(guard.check() == before, 'PORTAL_FENCE_CHANGED')
        files.revalidate()
        generation = hashlib.sha256(json.dumps(files.index,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        snapshot['source_generation'] = generation
        # Only Portal checks are proven here. A separate all-writer admission
        # must upgrade this explicitly; passing this directly to normalise fails.
        fence = dict(source_host=SOURCE_HOST, target_host=TARGET_HOST, source_sha256=SOURCE_SHA256,
            source_generation=generation, cutover_id=cutover_id, writer_fenced=False,
            portal_service_fenced=True, inflight_requests=0, account_identity_hashes=account_identity_hashes,
            all_writer_custody='EXTERNAL_APPROVED_ORCHESTRATOR_REQUIRED')
        return snapshot, fence, {'selected_file_count':len(files.index),
            'selected_bytes':files.total_bytes, 'data_publication':False, 'source_mutation':False}
    except Hold:
        raise
    except Exception:
        raise Hold('PRIVATE_SNAPSHOT_READ_UNKNOWN_PRESERVE_SOURCE') from None

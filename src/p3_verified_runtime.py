"""Candidate controlled Python entry loader. No external process support.

Modules are compiled directly from the opened source fd before registration.
This reduces import/path substitution, but does not defend against in-process
monkeypatching or hostile code after loading. Caller must protect ancestors,
trust anchors and the interpreter. Unsupported external processes fail closed.
"""
import hashlib
import os
import stat
import sys
import types

class VerifiedRuntimeRegistry:
    def __init__(self):
        self.modules = {}

    def _read(self, path):
        if not os.path.isabs(path) or not hasattr(os, 'O_NOFOLLOW'):
            raise PermissionError('ABSOLUTE_NOFOLLOW_SOURCE_REQUIRED')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > 4*1024*1024:
                raise PermissionError('UNTRUSTED_MODULE_FILE')
            chunks = []
            total = 0
            while True:
                chunk = os.read(fd, 65536)
                if not chunk: break
                total += len(chunk)
                if total > 4*1024*1024: raise ValueError('MODULE_TOO_LARGE')
                chunks.append(chunk)
            data = b''.join(chunks)
            return data, {'sha256':hashlib.sha256(data).hexdigest(), 'dev':info.st_dev,
                          'ino':info.st_ino, 'uid':info.st_uid, 'gid':info.st_gid,
                          'mode':stat.S_IMODE(info.st_mode)}
        finally:
            os.close(fd)

    def load(self, name, path, expected_digest, bindings):
        if not isinstance(bindings, dict) or not bindings:
            raise ValueError('TRUSTED_RUNTIME_BINDINGS_REQUIRED')
        if name in sys.modules or name in self.modules:
            raise ValueError('MODULE_NAME_ALREADY_LOADED')
        data, observed = self._read(path)
        if observed['sha256'] != expected_digest:
            raise PermissionError('MODULE_DIGEST_MISMATCH')
        module = types.ModuleType(name)
        module.__file__ = path
        module.__package__ = name.rpartition('.')[0]
        code = compile(data, path, 'exec', dont_inherit=True)
        sys.modules[name] = module
        try:
            exec(code, module.__dict__)
        except BaseException:
            del sys.modules[name]
            raise
        self.modules[name] = (module, observed, path, dict(bindings))
        return module

    def observe(self, obj, statement):
        cls = type(obj)
        record = self.modules.get(cls.__module__)
        if not record:
            raise PermissionError('CONTROLLED_LOADER_REQUIRED')
        module, original, path, bindings = record
        if sys.modules.get(cls.__module__) is not module or getattr(module, cls.__name__, None) is not cls:
            raise PermissionError('LOADED_CLASS_IDENTITY_MISMATCH')
        binding = bindings.get(cls.__name__)
        if binding != (statement.get('id'), statement.get('instance'), statement.get('epoch')):
            raise PermissionError('RUNTIME_PRINCIPAL_MISMATCH')
        _, current = self._read(path)
        metadata = {key: current[key] for key in ('dev','ino','uid','gid','mode')}
        if (current != original or current['sha256'] != statement.get('binary_digest')
                or statement.get('runtime') != metadata):
            raise PermissionError('LOADED_MODULE_CHANGED')
        return dict(current, module=cls.__module__, class_name=cls.__name__,
                    instance=statement['instance'], epoch=statement['epoch'],
                    component_id=statement['id'])

    def observe_external(self, pid, starttime, exe_digest, service_identity):
        # No reviewed launcher/OS attestation integration is present. Never
        # accept caller-supplied PID or process metadata as an observation.
        raise PermissionError('CONTROLLED_EXTERNAL_LAUNCHER_UNAVAILABLE')

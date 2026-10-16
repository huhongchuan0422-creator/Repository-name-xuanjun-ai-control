"""Isolated loopback candidate; no production CLI, unit or provider activation."""
import json
import os
import stat
import urllib.parse
from pathlib import Path
from pr122_oauth_candidate import http_candidate


class MigrationHandler(http_candidate.Handler):
    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path == '/integrations/tiktok/disconnect':
            self.reply(403, {'status': 'REJECTED', 'operation_performed': False,
                             'reason': 'TIKTOK_DISCONNECT_TEMPORARILY_DISABLED'})
            return
        super().do_POST()


def make_isolated_server(generation_root, *, port=0):
    root = Path(generation_root).absolute()
    for part in (root, *root.parents):
        if part.is_symlink():
            raise RuntimeError('GENERATION_SYMLINK_REJECTED')
    info = root.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700 or os.path.lexists(root/'FAILED.json')):
        raise RuntimeError('OFFLINE_GENERATION_NOT_READY')
    fd = os.open(root/'READY.json', os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError('READY_IDENTITY_INVALID')
        data = handle.read(4097)
    if len(data) > 4096:
        raise RuntimeError('READY_SIZE_LIMIT')
    ready = json.loads(data)
    if (ready.get('meaning') != 'OFFLINE_PREPARATION_ONLY_NOT_PRODUCTION_AUTHORITY'
            or root.name != 'handoff-'+ready.get('cutover_id', '')):
        raise RuntimeError('READY_BINDING_INVALID')
    server = http_candidate.make_server(root, root/'operations', port=port,
                                        provider_calls_enabled=False)
    server.RequestHandlerClass = MigrationHandler
    return server

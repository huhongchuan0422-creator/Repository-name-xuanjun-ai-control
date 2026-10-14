"""Backup-first callback schema migration rehearsal; never switches live DB."""
import argparse
import json
import os
import sys

from ledger_backup import backup, stage_restore
from uk_owner_callback_core import install_schema, validate_schema


def prepare(live, backup_path, staged):
    if any(os.path.exists(path) for path in (backup_path, staged)):
        raise ValueError('BACKUP_OR_STAGE_ALREADY_EXISTS')
    original = backup(live, backup_path)
    restored = stage_restore(backup_path, staged, original['sha256'])
    install_schema(staged)
    validate_schema(staged)
    # The live DB is never opened writable by this gate. Activation is a later,
    # separately approved single-writer atomic switch.
    return {'backup_sha256': original['sha256'], 'staged_pre_migration_sha256': restored['sha256'],
            'migration': 'STAGED_ONLY', 'live_switched': False}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',required=True)
    parser.add_argument('--backup',required=True)
    parser.add_argument('--staged',required=True)
    args=parser.parse_args(argv)
    print(json.dumps(prepare(args.live,args.backup,args.staged),sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())

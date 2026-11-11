"""Decode complete, exact-commit Git raw -z data for existing path preflight.

Caller obtains bytes using git diff --raw -z --no-abbrev --no-ext-diff
--no-textconv BASE HEAD --, authenticates the repository and pins both commits.
This adapter executes no commands and grants no writer or runtime lease.
"""
import re


SHA = re.compile(r'[a-f0-9]{40}')
HEADER = re.compile(rb':([0-7]{6}) ([0-7]{6}) ([a-f0-9]{40}) ([a-f0-9]{40}) ([AMD]|R(?:100|[1-9]?[0-9]))')


def collect_source_diff(receipt, base_sha, head_sha):
    if any(not isinstance(x, str) or SHA.fullmatch(x) is None for x in (base_sha, head_sha)):
        raise ValueError('EXACT_COMMITS_REQUIRED')
    if (not isinstance(receipt, dict) or set(receipt) != {'base_sha', 'head_sha', 'complete', 'raw'} or
            receipt['base_sha'] != base_sha or receipt['head_sha'] != head_sha or receipt['complete'] is not True):
        raise ValueError('COMPLETE_EXACT_DIFF_REQUIRED')
    raw = receipt['raw']
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 1048576 or not raw.endswith(b'\0'):
        raise ValueError('BOUNDED_NUL_DIFF_REQUIRED')
    tokens = raw[:-1].split(b'\0')
    changes, index, seen = [], 0, set()
    def path(token):
        try:
            value = token.decode('ascii')
        except UnicodeDecodeError:
            raise ValueError('CANONICAL_PATH_REQUIRED')
        if (not 1 <= len(value) <= 300 or re.fullmatch(r'[A-Za-z0-9_./-]+', value) is None or
                any(p in ('', '.', '..', '.git') for p in value.split('/'))):
            raise ValueError('CANONICAL_PATH_REQUIRED')
        return value
    while index < len(tokens):
        match = HEADER.fullmatch(tokens[index]); index += 1
        if match is None:
            raise ValueError('INVALID_RAW_DIFF_HEADER')
        oldmode, newmode, oldsha, newsha, status = match.groups()
        if any(mode not in (b'000000', b'100644', b'100755') for mode in (oldmode, newmode)):
            raise ValueError('LINK_SUBMODULE_OR_SPECIAL_MODE')
        kind = status[:1]
        if ((kind == b'A' and (oldmode != b'000000' or newmode == b'000000')) or
                (kind == b'D' and (newmode != b'000000' or oldmode == b'000000')) or
                (kind in (b'M', b'R') and b'000000' in (oldmode, newmode))):
            raise ValueError('STATUS_MODE_MISMATCH')
        if ((oldmode == b'000000') != (oldsha == b'0' * 40) or
                (newmode == b'000000') != (newsha == b'0' * 40)):
            raise ValueError('MODE_BLOB_MISMATCH')
        needed = 2 if kind == b'R' else 1
        if index + needed > len(tokens):
            raise ValueError('TRUNCATED_RAW_DIFF')
        first = path(tokens[index]); index += 1
        previous = None
        if kind == b'R':
            previous, first = first, path(tokens[index]); index += 1
            if previous == first:
                raise ValueError('INVALID_RENAME')
        if first in seen:
            raise ValueError('DUPLICATE_TARGET')
        seen.add(first)
        changes.append({'status': {b'A':'added', b'M':'modified', b'D':'removed', b'R':'renamed'}[kind],
                        'path': first, 'previous_path': previous})
        if len(changes) > 256:
            raise ValueError('TOO_MANY_CHANGED_PATHS')
    return {'base_sha': base_sha, 'head_sha': head_sha, 'changes': changes,
            'complete': True, 'source_authentication': 'CALLER_REQUIRED',
            'execution_granted': False}

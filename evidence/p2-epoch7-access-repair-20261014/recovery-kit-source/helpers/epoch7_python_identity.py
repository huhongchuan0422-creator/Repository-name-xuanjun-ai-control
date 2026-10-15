"""Pure contract for the measured retained Python two-name hardlink pair.

No I/O, path discovery, authority grant, or generic nlink exception occurs here.
Adapters must obtain two independent no-follow, descriptor-stable read rounds,
hash both files, inspect all three ancestors and reject xattr read errors. They
must pass those rounds to validate_pair_reread at every use of a pinned proof.
The package database claim is bound to the Owner metadata report; this is not
vendor signature verification. Live inode numbers are never RPM inode tags.
"""
import copy
import hashlib
import json

PYTHON_PATHS = ('/usr/libexec/platform-python3.6', '/usr/libexec/platform-python3.6m')
ANCESTOR_PATHS = ('/', '/usr', '/usr/libexec')
RETAINED_SHA256 = 'ba19929d7038d0c2304f528213fa11e5f10c1ce65f0a891afa459bd167c7e5f6'
RETAINED_SIZE = 15352
OWNER_REPORT_SHA256 = '88cc60f8c3bc465c4025eeda297f98a0b00d5ca5e0a80d3266e52e00f997e2f3'
PACKAGE_CLAIM_SHA256 = '36aa67e302e6c0b3a9494128aa184a46ba06edbfbf3828209682caa7c7559b8d'
METADATA_FIELDS = ('uid', 'gid', 'mode', 'dev', 'ino', 'nlink', 'size', 'mtime_ns', 'ctime_ns')
XATTR_FIELDS = ('access_acl', 'default_acl', 'capability')
FILE_FIELDS = frozenset(METADATA_FIELDS + XATTR_FIELDS + ('kind', 'sha256', 'elf_header'))
DIRECTORY_FIELDS = frozenset(METADATA_FIELDS + XATTR_FIELDS + ('kind',))
PROOF_FIELDS = frozenset(('schema', 'kind', 'retained_sha256', 'owner_report_sha256',
    'package_claim_sha256', 'package_signature_authenticity', 'sample', 'reread'))


def _need(condition, label):
    if not condition:
        raise ValueError('PYTHON_PAIR_' + label)


def _keys(value, fields, label):
    _need(type(value) is dict and set(value) == set(fields), label)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def package_claim():
    """Return the exact metadata-only claim measured in the pinned Owner report.

    This public, fixed projection may seed a fresh proof only after live checks;
    it does not replace those checks or assert an RPM vendor signature.
    """
    group = [{'path': path, 'package_device': 1, 'package_inode': 14,
              'file_mode': 0o100755, 'size': RETAINED_SIZE,
              'sha256': RETAINED_SHA256, 'link_target': ''} for path in PYTHON_PATHS]
    return {'schema': 1, 'kind': 'RPM_DECLARED_PYTHON_HARDLINK_GROUP',
        'authority': 'PACKAGE_METADATA_ONLY_NOT_FILESYSTEM_PROOF',
        'queried_path': PYTHON_PATHS[0],
        'package': {'name': 'platform-python', 'epoch': 0, 'version': '3.6.8',
                    'release': '69.0.1.1.al8', 'arch': 'x86_64', 'file_digest_algorithm': 8},
        'response_sha256': 'c8b0d7077a7534d8a50afdc2d5799cc3b0e78304ac1ac4a3521d982f27f932aa',
        'inventory_sha256': 'a5cb0634d5548c46e0899d58351f8e4252afe2fe029fd7dd753450aebd4936df',
        'inventory_count': 18, 'selected': dict(group[0]), 'hardlink_group': group}


def _validate_claim(value):
    expected = package_claim()
    _need(type(value) is dict and value == expected, 'EXACT_MEASURED_PACKAGE_CLAIM')
    # Canonical bytes also reject bool/int equality tricks anywhere in the row.
    _need(_canonical(value) == _canonical(expected) and
          hashlib.sha256(_canonical(value)).hexdigest() == PACKAGE_CLAIM_SHA256,
          'PACKAGE_CLAIM_TYPED_DIGEST')
    return copy.deepcopy(value)


def _metadata(row, fields, kind):
    _keys(row, fields, 'EXACT_' + kind + '_FIELDS')
    _need(row['kind'] == kind, 'EXACT_' + kind + '_KIND')
    _need(all(type(row[key]) is int and 0 <= row[key] < 2**64
              for key in METADATA_FIELDS), 'TYPED_FULL_STAMP')
    _need(row['dev'] > 0 and row['ino'] > 0 and row['nlink'] > 0, 'LIVE_INODE_STAMP')
    _need(row['uid'] == row['gid'] == 0, 'ROOT_AUTHORITY')
    _need(all(row[key] is False for key in XATTR_FIELDS), 'ACL_OR_CAPABILITY_UNKNOWN_OR_PRESENT')


def validate_pair_sample(sample):
    """Validate one fresh sample, returning an independent canonical-shaped copy."""
    _keys(sample, ('files', 'ancestors'), 'EXACT_SAMPLE_FIELDS')
    _keys(sample['files'], PYTHON_PATHS, 'EXACT_TWO_FIXED_PATHS')
    _keys(sample['ancestors'], ANCESTOR_PATHS, 'EXACT_PROTECTED_ANCESTORS')
    for path in PYTHON_PATHS:
        row = sample['files'][path]
        _metadata(row, FILE_FIELDS, 'FILE')
        _need(row['mode'] == 0o755 and row['nlink'] == 2 and row['size'] == RETAINED_SIZE,
              'EXACT_RETAINED_FILE_METADATA')
        _need(row['sha256'] == RETAINED_SHA256 and row['elf_header'] is True,
              'EXACT_RETAINED_ELF')
    _need(sample['files'][PYTHON_PATHS[0]] == sample['files'][PYTHON_PATHS[1]],
          'SAME_INODE_AND_FULL_STAMP')
    for path in ANCESTOR_PATHS:
        row = sample['ancestors'][path]
        _metadata(row, DIRECTORY_FIELDS, 'DIRECTORY')
        # These are the measured protected, client-searchable directory modes.
        _need(row['mode'] == (0o555 if path == '/' else 0o755), 'PROTECTED_ANCESTOR_MODE')
    identities = [(sample['ancestors'][path]['dev'], sample['ancestors'][path]['ino'])
                  for path in ANCESTOR_PATHS]
    _need(len(set(identities)) == len(ANCESTOR_PATHS), 'DISTINCT_ANCESTOR_IDENTITIES')
    return copy.deepcopy(sample)


def _proof(sample):
    return {'schema': 1, 'kind': 'EXACT_RETAINED_PYTHON_TWO_NAME_V1',
        'retained_sha256': RETAINED_SHA256, 'owner_report_sha256': OWNER_REPORT_SHA256,
        'package_claim_sha256': PACKAGE_CLAIM_SHA256,
        'package_signature_authenticity': 'NOT_VERIFIED',
        'sample': copy.deepcopy(sample), 'reread': 'EXACT_PRE_POST'}


def build_pair_proof(before, after, package_claim):
    """Build a proof only from equal independently collected pre/post samples."""
    _validate_claim(package_claim)
    first = validate_pair_sample(before)
    last = validate_pair_sample(after)
    _need(first == last, 'PRE_POST_CHANGED')
    return _proof(first)


def validate_pair_proof(proof):
    """Check the exact proof schema and source pins; this performs no live read."""
    _keys(proof, PROOF_FIELDS, 'EXACT_PROOF_FIELDS')
    sample = validate_pair_sample(proof['sample'])
    expected = _proof(sample)
    _need(type(proof['schema']) is int and proof == expected and
          _canonical(proof) == _canonical(expected), 'EXACT_PROOF_BINDING')
    return copy.deepcopy(proof)


def validate_pair_reread(proof, before, after):
    """Require both fresh complete rounds to match the already bound proof."""
    result = validate_pair_proof(proof)
    first = validate_pair_sample(before)
    last = validate_pair_sample(after)
    _need(first == last == result['sample'], 'PINNED_PRE_POST_CHANGED')
    return result

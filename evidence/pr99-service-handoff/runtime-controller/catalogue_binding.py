"""Bind an externally verified effective catalogue; never issue its authority.

Source-default paths and /proc samples cannot satisfy this contract. The original
trusted authority must bind effective configuration, recursive data coverage,
writer/activator coverage and retained objects to these exact bytes.
"""
import hashlib
import json
import re
from pathlib import PurePosixPath

SOURCE_HOST = 'iZ6wee8q9z4t03hvqumwfhZ'
ROLES = ('portal', 'contact', 'customer_service')
SHA = re.compile('[0-9a-f]{64}')
PROTECTED_UNITS = frozenset(('provider-neutral-domestic-bridge.service',
                            'windows-interaction-http.service'))


class CatalogueHold(RuntimeError):
    pass


def need(condition, code):
    if not condition:
        raise CatalogueHold(code)


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def fields(value, keys):
    need(type(value) is dict and set(value) == set(keys.split()), 'CATALOGUE_SCHEMA')


def integer(value, positive=False):
    need(type(value) is int and (0 < value if positive else 0 <= value) and value < 2**64,
         'CATALOGUE_INTEGER')


def hash_value(value):
    need(type(value) is str and SHA.fullmatch(value), 'CATALOGUE_DIGEST')


def bind_catalogue(value, expected_digest, verify_evidence):
    """Return an immutable-by-encoding copy only after original trust validation.

    verify_evidence(kind, digest) is supplied by the admitted original trust
    channel. It must resolve real records; fixture booleans are not production
    evidence. No path reads or host operations occur in this function.
    """
    hash_value(expected_digest)
    need(digest(value) == expected_digest and callable(verify_evidence), 'CATALOGUE_BINDING')
    value = json.loads(encode(value))
    fields(value, 'schema host configurations objects origins coverage_proofs')
    need(type(value['schema']) is int and value['schema'] == 1 and value['host'] == SOURCE_HOST,
         'CATALOGUE_HOST_SCHEMA')
    fields(value['configurations'], 'portal contact customer_service')
    for role in ROLES:
        record = value['configurations'][role]
        fields(record, 'unit source_sha256 effective_configuration_sha256 runtime_identity_proof data_objects writer_origins')
        need(type(record['unit']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,179}\.service', record['unit']),
             'CONFIGURATION_UNIT')
        for key in ('source_sha256', 'effective_configuration_sha256', 'runtime_identity_proof'):
            hash_value(record[key])
        need(verify_evidence('effective_configuration:'+role, digest(record)) is True,
             'EFFECTIVE_CONFIGURATION_NOT_VERIFIED')
    fields(value['coverage_proofs'], 'data_membership writers_and_activators protected_objects')
    for kind, proof in value['coverage_proofs'].items():
        hash_value(proof)
        need(verify_evidence(kind, proof) is True, 'CATALOGUE_COVERAGE_NOT_VERIFIED')
    need(type(value['objects']) is list and 0 < len(value['objects']) <= 12000, 'CATALOGUE_OBJECTS')
    objects = {}
    paths = set()
    identities = set()
    for item in value['objects']:
        fields(item, 'id path kind classification device inode uid nlink original_flags children writers')
        name = item['id']
        need(type(name) is str and re.fullmatch('[A-Za-z0-9_-]{1,80}', name) and name not in objects,
             'CATALOGUE_OBJECT_ID')
        path = item['path']
        need(type(path) is str and 1 <= len(path) <= 500 and '\x00' not in path and
             path.startswith('/opt/trading-system/') and str(PurePosixPath(path)) == path and
             '..' not in PurePosixPath(path).parts and path not in paths, 'CATALOGUE_PATH')
        need(item['kind'] in ('FILE', 'DIRECTORY') and item['classification'] in ('COPY_FENCED', 'PRESERVE_SHARED'),
             'CATALOGUE_CLASSIFICATION')
        for key in ('device', 'inode', 'uid', 'nlink', 'original_flags'):
            integer(item[key], positive=key in ('inode', 'nlink'))
        if item['kind'] == 'FILE':
            need(item['nlink'] == 1 and item['children'] == [], 'FILE_LINK_OR_CHILDREN')
        need(type(item['children']) is list and len(set(item['children'])) == len(item['children']), 'CHILDREN_SCHEMA')
        need(type(item['writers']) is list and item['writers'] and len(set(item['writers'])) == len(item['writers']),
             'WRITER_MEMBERSHIP_MISSING')
        identity = (item['device'], item['inode'])
        need(identity not in identities, 'ALIASED_DATA_OBJECT')
        identities.add(identity); paths.add(path); objects[name] = item
    need(type(value['origins']) is list and value['origins'], 'WRITER_ORIGINS_MISSING')
    origins = {}
    for origin in value['origins']:
        fields(origin, 'id kind unit retained objects proof_sha256')
        name = origin['id']
        need(type(name) is str and re.fullmatch('[A-Za-z0-9_-]{1,80}', name) and name not in origins,
             'WRITER_ORIGIN_ID')
        need(origin['kind'] in ('SERVICE','TIMER','SOCKET','PATH','MANUAL') and type(origin['retained']) is bool,
             'WRITER_ORIGIN_KIND')
        if origin['kind'] == 'MANUAL':
            need(origin['unit'] is None, 'MANUAL_UNIT')
        else:
            need(type(origin['unit']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,179}\.(?:service|timer|socket|path)',origin['unit']),
                 'WRITER_ORIGIN_UNIT')
        need(type(origin['objects']) is list and origin['objects'] and len(set(origin['objects'])) == len(origin['objects']),
             'ORIGIN_OBJECTS')
        hash_value(origin['proof_sha256'])
        need(verify_evidence('writer_origin:'+name, digest(origin)) is True, 'WRITER_ORIGIN_NOT_VERIFIED')
        origins[name] = origin
    for item in objects.values():
        for child_id in item['children']:
            need(child_id in objects and PurePosixPath(objects[child_id]['path']).parent == PurePosixPath(item['path']),
                 'DATA_CHILD_MEMBERSHIP')
            need(objects[child_id]['classification'] == item['classification'], 'SHARED_SUBTREE_CANNOT_FENCE')
        # Every direct descendant present in the catalogue must be accounted for.
        direct = {key for key, obj in objects.items() if PurePosixPath(obj['path']).parent == PurePosixPath(item['path'])}
        if item['kind'] == 'DIRECTORY':
            need(set(item['children']) == direct, 'DATA_DIRECTORY_MEMBERSHIP')
        for writer in item['writers']:
            need(writer in origins and item['id'] in origins[writer]['objects'], 'WRITER_OBJECT_CROSS_BINDING')
            if item['classification'] == 'COPY_FENCED':
                need(not origins[writer]['retained'] and origins[writer]['unit'] not in PROTECTED_UNITS,
                     'RETAINED_WRITER_CONFLICT')
    for origin in origins.values():
        for object_id in origin['objects']:
            need(object_id in objects and origin['id'] in objects[object_id]['writers'], 'ORIGIN_OBJECT_CROSS_BINDING')
    # A configuration hash without its actual object edges is not a data map.
    for record in value['configurations'].values():
        data = record['data_objects']; writers = record['writer_origins']
        need(type(data) is list and data and len(set(data)) == len(data) and
             all(name in objects for name in data), 'CONFIGURATION_DATA_BINDING')
        need(type(writers) is list and len(set(writers)) == len(writers), 'CONFIGURATION_WRITER_BINDING')
        for name in writers:
            need(name in origins and origins[name]['unit'] == record['unit'] and
                 set(origins[name]['objects']).issubset(data), 'CONFIGURATION_WRITER_OBJECT_BINDING')
    need(any(obj['classification'] == 'COPY_FENCED' for obj in objects.values()), 'NO_MIGRATION_DATA')
    return value

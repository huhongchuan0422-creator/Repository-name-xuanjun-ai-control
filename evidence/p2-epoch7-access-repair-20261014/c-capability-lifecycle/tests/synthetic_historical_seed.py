"""Emit the original public synthetic seed in an isolated baseline namespace.

This is fixture construction only, not a test-suite run or host observation.
The successor test reads the JSON values and runs the actual successor compiler.
"""
import base64
import json
import pathlib
import sys

BASELINE = pathlib.Path(__file__).resolve().parents[1] / 'baseline'
paths = [BASELINE / 'helpers', BASELINE / 'xuanjun-p2-package/stage1']
paths += sorted(path for path in (BASELINE / 'tests').iterdir() if path.is_dir())
sys.path[:0] = [str(path) for path in paths]
sys.dont_write_bytecode = True
from test_epoch7_full_factory_fixture import make_seed
from test_epoch7_additive_server import server_fixture
from test_epoch7_additive_identity import additive_fixture
import epoch7_additive_server as server
import epoch7_additive_identity as owner
import epoch7_delta as delta


def complete_seed():
    # Replace the old compiler-only placeholder rows with outputs of the real
    # additive compilers, still using explicitly synthetic private observations.
    seed = make_seed()
    manifest = seed['source_manifest_raw']
    manifest_hash = owner.raw_sha(manifest)
    raw = seed['identity_payloads'][owner.PATH]
    config = json.loads(raw)
    config.update(schema=1, cgroup=owner.CGROUP)
    raw = delta.canonical(config) + b'\n'
    seed['identity_payloads'][owner.PATH] = raw
    unused, unused, unused, interpreter, absence = additive_fixture()
    interpreter.update(path=config['python_exe'], sha256=config['python_sha256'])
    own = owner.compile_addition(raw, owner.raw_sha(raw), manifest, manifest_hash,
        seed['compiled']['rendered_targets'][owner.UNIT], interpreter, absence)
    policy, unused, sources, proof, review, absent, unused = server_fixture()
    policy['activation_binding'] = {key: seed['compiled']['activation_proposal'][key]
                                    for key in server.BINDING_KEYS}
    for path in sources:
        if path in seed['compiled']['rendered_targets']:
            sources[path] = seed['compiled']['rendered_targets'][path]
    policy['files'] = {path: owner.raw_sha(payload) for path, payload in sources.items()}
    raw = delta.canonical(policy) + b'\n'
    serve = server.compile_addition(raw, owner.raw_sha(raw), manifest, manifest_hash,
        sources, proof, review, absent)
    seed['identity_payloads'][server.PATH] = raw
    seed['additive_deltas'] = sorted((own, serve), key=lambda value: value['path'])
    return seed


def encode(value):
    if type(value) is bytes:
        return ['bytes', base64.b64encode(value).decode('ascii')]
    if type(value) is dict:
        return ['dict', [[key, encode(child)] for key, child in value.items()]]
    if type(value) is list:
        return ['list', [encode(child) for child in value]]
    if type(value) is tuple:
        return ['tuple', [encode(child) for child in value]]
    if type(value) not in (str, int, bool, type(None)):
        raise ValueError('SYNTHETIC_FIXTURE_FINITE_TYPES_ONLY')
    return [type(value).__name__, value]


if __name__ == '__main__':
    print(json.dumps(encode(complete_seed()), sort_keys=True))

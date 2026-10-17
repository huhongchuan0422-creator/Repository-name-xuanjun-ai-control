"""Offline deterministic builder; generates artifacts only, never installs them."""
import base64
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def build():
    spec = importlib.util.spec_from_file_location('domestic_bootstrap_build', ROOT / 'domestic_bootstrap.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    raw = (ROOT / 'domestic_helper.py').read_bytes()
    for token, filename in ((b'__PAYLOAD_B64__', 'approved_account_prepare.py'), (b'__PROBE_B64__', 'readonly_probe.py')):
        if raw.count(token) != 1: raise ValueError('Expected exactly one helper embedding token: ' + token.decode())
        raw = raw.replace(token, base64.b64encode((ROOT / filename).read_bytes()))
    compile(raw, 'domestic-readonly-helper.py', 'exec')
    files = {'domestic-readonly-helper.py': raw, 'wrapper': module.new_wrapper(), 'sudoers': module.new_policy(), 'domestic_bootstrap.py': (ROOT / 'domestic_bootstrap.py').read_bytes(), 'domestic_owner.py': (ROOT / 'domestic_owner.py').read_bytes()}
    compile(files['domestic_owner.py'], 'domestic_owner.py', 'exec')
    manifest = {'schema': 1, 'scope': 'DOMESTIC_READONLY_BOOTSTRAP_20261017', 'files': {n: {'sha256': module.sha(b), 'size': len(b)} for n, b in files.items()}}
    output = ROOT / 'domestic-install-package'
    output.mkdir(exist_ok=True)
    (output / 'domestic_bootstrap.py').write_bytes(files['domestic_bootstrap.py'])
    (output / 'domestic_owner.py').write_bytes(files['domestic_owner.py'])
    (output / 'domestic-readonly-helper.py').write_bytes(raw)
    (output / 'domestic-bootstrap-manifest.json').write_bytes(module.canonical(manifest) + b'\n')
    return manifest
if __name__ == '__main__': build()

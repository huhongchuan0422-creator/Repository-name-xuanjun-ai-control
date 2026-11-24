"""Truthful native provenance: process baseline is NOT an overlay Git revision."""
import hashlib
import json
import os
from pathlib import Path
import re

def native_snapshot(application_root):
    baseline = os.environ.get('COMMUNITY_SOURCE_SHA', '')
    if re.fullmatch('[0-9a-f]{40}', baseline) is None:
        return None
    root = Path(application_root)
    # Snapshot at handler construction, never recomputed to mislabel later disk edits.
    pins = {}
    for path in sorted((root/'scripts').glob('*.py')):
        if path.is_symlink():
            return None
        try:
            pins['scripts/'+path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None
    if not pins:
        return None
    manifest = json.dumps(pins, sort_keys=True, separators=(',', ':')).encode()
    return dict(runtime_source_sha=baseline,
        version_source='NATIVE_PROCESS_ENV_BASELINE_WITH_STARTUP_SOURCE_PINS',
        source_coverage='BASELINE_COMMIT_PLUS_UNCOMMITTED_OVERLAYS_NOT_A_SINGLE_GIT_REVISION',
        startup_source_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
        startup_source_pins=pins)

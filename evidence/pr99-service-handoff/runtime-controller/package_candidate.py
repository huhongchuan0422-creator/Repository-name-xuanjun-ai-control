"""Deterministic review artifact bound to commit/tree; no deployment entry."""
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


def package(commit, tree, run_id, dependency_root, destination):
    if not all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (commit,tree)):
        raise ValueError('COMMIT_TREE_REQUIRED')
    if type(run_id) is not str or not re.fullmatch('[0-9]{1,30}',run_id):
        raise ValueError('RUN_ID_REQUIRED')
    base=Path(__file__).parent
    members={name:(base/name).read_bytes() for name in (
        'catalogue_binding.py','existing_fd_controller.py','source_fence.py','held_proof.py',
        'stage_history.py','capture_session.py','ingress_gate.py','final_handoff.py','owner_contract.py','test_final_handoff.py','test_ingress_gate.py','test_capture_session.py','test_runtime_controller.py','README.md','dependency-pins.json','package_candidate.py')}
    pins=json.loads(members['dependency-pins.json'])
    if {name:hashlib.sha256((Path(dependency_root)/name).read_bytes()).hexdigest() for name in pins} != pins:
        raise ValueError('UNCHANGED_ORIGINAL_DEPENDENCY_DRIFT')
    manifest={'code_commit':commit,'code_tree':tree,'hosted_run_id':run_id,'scope':'REVIEW_CANDIDATE_NOT_PRODUCTION_ADMITTED',
        'source_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in members.items()},'unchanged_original_dependencies':pins,
        'ordinary_tests':113,'m99_dynamic':'NOT_RUN','production_actions':0}
    members['candidate-manifest.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    destination=Path(destination)
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_STORED) as archive:
        for name,raw in sorted(members.items()):
            info=zipfile.ZipInfo(name,(2026,10,18,0,0,0));info.external_attr=0o100644<<16
            archive.writestr(info,raw)
    raw=destination.read_bytes()
    receipt={**manifest,'archive_bytes':len(raw),'archive_sha256':hashlib.sha256(raw).hexdigest(),'archive_members':len(members)}
    destination.with_suffix('.receipt.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps(receipt,sort_keys=True))


if __name__=='__main__':
    package(*sys.argv[1:])

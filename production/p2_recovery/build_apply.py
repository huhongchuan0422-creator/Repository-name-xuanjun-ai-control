"""Exact recovery assembly; original production runtime remains byte inherited."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
BASE = '6041c7458dce7c83c49c5a9eafa0e20cef52d1c0'
CORE = 'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'


def main():
    def git(*args):
        return subprocess.check_output(['git'] + list(args), cwd=str(ROOT))
    head = git('rev-parse','HEAD').decode().strip()
    tree = git('rev-parse','HEAD^{tree}').decode().strip()
    assert head == os.environ.get('GITHUB_SHA',head)
    original = git('ls-tree','-r','--name-only',BASE,'--','production/p2_attempt5',CORE).decode().splitlines()
    for name in original:
        previous = git('show',BASE+':'+name)
        if name == 'production/p2_attempt5/entry.py':
            assert hashlib.sha1(b'blob '+str(len(previous)).encode()+b'\0'+previous).hexdigest() == '5c6c8da9a5cf82f0a6da285b27dbbf02bab90d07'
            expected=previous.replace(b'def main():\n', b'_RECOVERY_GATE = None  # Bound only by the pinned controlled recovery entry.\n\n\ndef main():\n',1)
            expected=expected.replace(b'    cfg = configuration(args.config, args.config_sha256)\n',b'    cfg = configuration(args.config, args.config_sha256)\n    require(_RECOVERY_GATE is not None, \'CONTROLLED_RECOVERY_ENTRY_REQUIRED\')\n    unused_record, recovered_cfg, unused_manifest = _RECOVERY_GATE.verify()\n    require(recovered_cfg == cfg, \'RECOVERY_CONFIG_CHANGED\')\n',1)
            assert (ROOT/name).read_bytes()==expected,'EXACT_ENTRY_DELTA'
        else:
            assert (ROOT/name).read_bytes() == previous, name
    files = original + git('ls-tree','-r','--name-only','HEAD','--','production/p2_recovery',
        'tests/p2_recovery/test_apply.py','.github/workflows/p2-recovery-apply.yml').decode().splitlines()
    files = sorted(set(files))
    manifest = {'schema':1,'source_commit':head,'source_tree':tree,
        'runtime_source_commit':BASE,'runtime_source_tree':'8e27d077d22af392108568ac06d284df4dd4b35e',
        'inherited_manifest_sha256':'243bc01b1e9c7d2cb302f800556002abcebcfa9f96c298e4275e15d8b1346e1e',
        'inherited_kit_sha256':'2fdc934a336414086361764a4a77894a597a51a53c7693420eaed5cefed3e1d3',
        'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
        'scope':'CONTROLLED_RECOVERY_APPLY_AND_FORMAL_ENTRY',
        'production_isolation':'WAITING_REAL_EVIDENCE','uk_execution':'NOT_EXECUTED',
        'release':'HOLD'}
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    (out/'MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    with tarfile.open(str(out/'p2-recovery-assembly.tar.gz'),'w:gz') as archive:
        for p in files:archive.add(str(ROOT/p),arcname=p,recursive=False)
        archive.add(str(out/'MANIFEST.json'),arcname='MANIFEST.json',recursive=False)
    sums={p:hashlib.sha256((out/p).read_bytes()).hexdigest() for p in ('MANIFEST.json','p2-recovery-assembly.tar.gz')}
    (out/'SHA256SUMS').write_text(''.join(sums[p]+'  '+p+'\n' for p in sorted(sums)))
    print('RECOVERY_APPLY_ARTIFACT='+json.dumps({'commit':head,'tree':tree,'artifacts':sums,
                                              'files':manifest['files']},sort_keys=True))

if __name__=='__main__':main()

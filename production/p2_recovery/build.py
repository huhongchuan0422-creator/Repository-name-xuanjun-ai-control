"""Build source-only recovery add-on; no production facts or runtime kit rewrite."""
import hashlib,json,os,subprocess,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FILES=['production/p2_recovery/recovery.py','production/p2_recovery/README.md',
       'production/p2_recovery/build.py','tests/p2_recovery/test_recovery.py','tests/p2_recovery/cli_acceptance.py',
       '.github/workflows/p2-authority-recovery.yml']
def main():
    out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(ROOT)).decode().strip()
    tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=str(ROOT)).decode().strip()
    assert head==os.environ.get('GITHUB_SHA',head)
    # Explicit inheritance check: do not accidentally change accepted runtime.
    for prefix in ('production/p2_attempt5',
        'evidence/p2-epoch7-access-repair-20261014/c-capability-lifecycle/attempt5'):
        paths=subprocess.check_output(['git','ls-tree','-r','--name-only','6041c7458dce7c83c49c5a9eafa0e20cef52d1c0','--',prefix],cwd=str(ROOT)).decode().splitlines()
        for p in paths:
            assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show','6041c7458dce7c83c49c5a9eafa0e20cef52d1c0:'+p],cwd=str(ROOT)),p
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
    manifest={'schema':1,'source_commit':head,'source_tree':tree,
        'inherited_runtime_commit':'6041c7458dce7c83c49c5a9eafa0e20cef52d1c0',
        'inherited_runtime_tree':'8e27d077d22af392108568ac06d284df4dd4b35e',
        'files':hashes,'tests':41,'scope':'RECOVERY_EVIDENCE_AND_CHECKPOINT_ONLY',
        'production_isolation':'NOT_EXECUTED','authority_initialized':False,
        'activation':'NOT_IMPLEMENTED_IN_THIS_ADDON','production_release':'HOLD'}
    raw=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    (out/'MANIFEST.json').write_bytes(raw)
    with tarfile.open(str(out/'p2-recovery-addon.tar.gz'),'w:gz') as archive:
        for p in sorted(FILES):archive.add(str(ROOT/p),arcname=p,recursive=False)
        archive.add(str(out/'MANIFEST.json'),arcname='MANIFEST.json',recursive=False)
    sums={p:hashlib.sha256((out/p).read_bytes()).hexdigest() for p in ('MANIFEST.json','p2-recovery-addon.tar.gz')}
    (out/'SHA256SUMS').write_text(''.join(sums[p]+'  '+p+'\n' for p in sorted(sums)))
    print('RECOVERY_ARTIFACT='+json.dumps({'commit':head,'tree':tree,'files':hashes,'artifacts':sums},sort_keys=True))
if __name__=='__main__':main()

"""Disposable Hosted Docker E2E, not a UK server command."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
h=module('host',REPO/'scripts/p2_b3_owner_finalize_20261020.py')
b=module('bundle',REPO/'scripts/build_p2_b3_final_bundle.py')
a=module('activation',REPO/'evidence/p2-epoch7-access-repair-20261014/runtime/stage1/activation_control.py')


class DockerE2E(unittest.TestCase):
    def test_actual_readonly_observer_and_same_request_recovery(self):
        self.assertEqual(os.geteuid(),0,'Hosted test requires its existing sudo, not UK permissions')
        info=subprocess.check_output(['/bin/docker','image','inspect','python:3.11.2-slim','--format','{{.Id}}'])
        image=info.decode().strip()
        measure="import hashlib,json,os,sys;p=os.path.realpath(sys.executable);r=open(p,'rb').read();print(json.dumps({'path':p,'bytes':len(r),'sha256':hashlib.sha256(r).hexdigest()}))"
        binary=json.loads(subprocess.check_output(['/bin/docker','run','--rm','--network=none','--cap-drop=ALL',
                         '--security-opt=no-new-privileges','--read-only',image,'/usr/local/bin/python3.11','-I','-B','-S','-c',measure]))
        # Preserve all CI failure state for the evidence artifact.
        d=tempfile.mkdtemp(prefix='p2-b3-test-host-',dir='/tmp')
        if True:
            os.umask(0o077)  # Same creation policy as the real host main.
            base=Path(d);root=base/'b3-initialize';root.mkdir(mode=0o700)
            activation=root/'activation';activation.mkdir(mode=0o700)
            cfg={'installation_id':'p2-host-test','initial_state':'PREPARED','initial_epoch':1,
                 'release_manifest_sha256':'a'*64,'instance':'0891a51b-feea-520e-850a-c8fc7c840d94',
                 'ledger_uuid':'093955da-4b7d-5c8d-b85e-3adaa304c675','generation':1,
                 'db_path':str(root/'data/ledger.sqlite3'),'ledger_socket':str(root/'run/ledger.sock')}
            config=h.canonical(cfg);h.publish(root/'binding-config.json',config,0o400)
            h.publish(root/'intent.json',h.canonical({'scope':'ISOLATED_TEST_ONLY'}),0o400)
            for name in ('data','run'):(root/name).mkdir(mode=0o700)
            store=a.ActivationStore(str(activation/'active.json'),str(activation/'epochs.jsonl'),str(activation/'activation.lock'))
            store.prepare(release_sha256='a'*64,config_sha256=h.digest(config),binary_sha256=binary['sha256'],
                ledger_uuid=cfg['ledger_uuid'],generation=1,instance=cfg['instance'],db_path=cfg['db_path'],
                ledger_socket=cfg['ledger_socket'],expected_epoch=0)
            receipt={'schema':1,'scope':'ISOLATED_TEST_ONLY','origin':'ISOLATED_NEW','status':'COMMITTED',
                'installation_id':cfg['installation_id'],'config_sha256':h.digest(config),'binary_sha256':binary['sha256'],
                'full_b3_complete':False,'descriptor_file_sha256':h.digest((activation/'active.json').read_bytes()),
                'journal_sha256':h.digest((activation/'epochs.jsonl').read_bytes())}
            h.publish(root/'commit-receipt.json',h.canonical(receipt),0o400)
            (root/'.initialize.lock').write_bytes(b'');(root/'.initialize.lock').chmod(0o600)
            for p in list(root.rglob('*'))+[root]:os.chown(str(p),1002,1002)
            app=REPO/'evidence/p2-epoch7-access-repair-20261014/runtime/stage1'
            request={'schema':1,'scope':'ISOLATED_TEST_ONLY','root':str(root),'application':'/application/stage1',
                'binary':binary,'sources':{n:h.digest((app/n).read_bytes()) for n in
                  ('ledger_service.py','ledger_prepared.py','activation_control.py')},
                'operation_id':'p2-host-test:b3-prepare-a1','cp03_receipt_sha256':h.digest(h.canonical(receipt))}
            work=base/'work';h.directory(work);logs=work/'logs';h.directory(logs)
            raw=b.build(REPO,request_override=request);stage=work/'sources';h.unpack(raw,h.digest(raw),stage)
            producer=h.digest((REPO/'scripts/p2_b3_owner_finalize_20261020.py').read_bytes())
            try:first=h.install(stage,work,logs,root,image,binary['path'],producer,fixture=True)
            except Exception:
                for p in logs.glob('logs-observe-*.stdout'):
                    print('RAW_OBSERVER='+p.read_text()[-16384:])
                raise
            self.assertEqual(first['status'],'PREPARATION_COMMITTED')
            proof=json.loads((work/'proof.json').read_bytes())
            self.assertEqual(proof['probe']['uid'],65534)
            self.assertIn(proof['probe']['errno'],(1,13))
            before=(work/'proof.json').stat();second=h.install(stage,work,logs,root,image,binary['path'],producer,fixture=True)
            self.assertEqual(first,second)
            self.assertEqual(before.st_ino,(work/'proof.json').stat().st_ino)
            self.assertFalse((root/'data/ledger.sqlite3').exists());self.assertFalse((root/'run/ledger.sock').exists())
            # Identical bytes at a replacement inode must not be accepted by
            # replaying the old exited containers' success logs.
            cp07=root/'prepared/CP07-committed.json';old=cp07.read_bytes()
            cp07.rename(root/'prepared/CP07-held-original.json')
            cp07.write_bytes(old);cp07.chmod(0o400);os.chown(str(cp07),1002,1002)
            with self.assertRaisesRegex(ValueError,'OBSERVATION_TARGET_CHANGED'):
                h.install(stage,work,logs,root,image,binary['path'],producer,fixture=True)
            config_path=root/'binding-config.json';config_path.write_bytes(config_path.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'IMMUTABLE_CONFLICT'):
                h.install(stage,work,logs,root,image,binary['path'],producer,fixture=True)
            # This disposable Hosted-only cleanup is never present in the UK
            # wrapper. Inspect each owned label before deleting TEST containers.
            for name in ('execute','observe','recover-1','inspect','recover-2'):
                c=h.inspect_container('p2-b3-final-'+name,logs)
                self.assertEqual(c['Config']['Labels']['xuanjun.b3.producer'],producer)
                subprocess.check_call(['/bin/docker','rm',c['Id']],stdout=subprocess.DEVNULL)


if __name__=='__main__':unittest.main()

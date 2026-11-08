"""Audit-only artifact manifest, backup plan and recovery/rotation validation."""
import argparse, hashlib, json, os, shutil, stat, tempfile, time

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def manifest(artifact,commit,tree):
    return {'schema':1,'artifact':os.path.basename(artifact),'artifact_sha256':sha256(artifact),
      'commit':commit,'tree':tree,'created_at':int(time.time()),'deployment_authorized':False}

def main(argv=None):
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command')
    m=sub.add_parser('manifest'); m.add_argument('--artifact',required=True); m.add_argument('--commit',required=True); m.add_argument('--tree',required=True)
    v=sub.add_parser('verify'); v.add_argument('--artifact',required=True); v.add_argument('--manifest',required=True)
    a=p.parse_args(argv)
    if a.command is None: p.error('a command is required')
    if a.command=='manifest': print(json.dumps(manifest(a.artifact,a.commit,a.tree),sort_keys=True)); return 0
    data=json.load(open(a.manifest)); ok=data.get('artifact_sha256')==sha256(a.artifact)
    print(json.dumps({'verified':ok,'artifact_sha256':sha256(a.artifact)},sort_keys=True)); return 0 if ok else 69

if __name__=='__main__': raise SystemExit(main())

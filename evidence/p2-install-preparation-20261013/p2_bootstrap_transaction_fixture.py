"""Real filesystem transaction prototype; restricted to disposable fixture paths."""
import hashlib, json, os, pathlib, shutil, socket, stat, sys, tempfile
def digest(data):return hashlib.sha256(data).hexdigest()
class Transaction:
    def __init__(self,root):
        assert root.startswith('/tmp/xj-p2-bootstrap-txn-fixture-') and os.path.realpath(root)==root
        self.root=root;self.journal=root+'/journal.json'
    def save(self,rows):
        raw=json.dumps(rows,sort_keys=True).encode()
        fd,name=tempfile.mkstemp(dir=self.root)
        try:
            with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
            os.replace(name,self.journal)
            fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        finally:
            if os.path.exists(name):os.unlink(name)
    def apply(self,crash_after=None,uid=None):
        assert not os.path.lexists(self.journal)
        assert all(not os.path.lexists(self.root+'/targets/file-'+str(i)) for i in range(7))
        rows=[]
        for i in range(7):
            target=self.root+'/targets/file-'+str(i)
            assert not os.path.lexists(target)
            data=('SYNTHETIC_BOOTSTRAP_'+str(i)+'\n').encode()
            fd,temp=tempfile.mkstemp(dir=self.root)
            with os.fdopen(fd,'wb') as f:
                f.write(data);f.flush();os.fchmod(f.fileno(),0o600)
                if uid is not None:os.fchown(f.fileno(),uid,uid)
                os.fsync(f.fileno());info=os.fstat(f.fileno())
            row={'target':target,'temp':temp,'sha256':digest(data),'dev':info.st_dev,'ino':info.st_ino,
              'uid':info.st_uid,'gid':info.st_gid,'mode':0o600,'state':'PUBLISH_INTENT'}
            rows.append(row);self.save(rows)
            # No overwrite; durable inode identity precedes publication.
            os.link(temp,target,follow_symlinks=False)
            fd=os.open(self.root+'/targets',os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            if crash_after==i:raise RuntimeError('INJECTED_AFTER_PUBLISH_BEFORE_ACK')
            os.unlink(temp);row['state']='PUBLISHED';self.save(rows)
        return rows
    def rollback(self):
        rows=json.loads(pathlib.Path(self.journal).read_text())
        # Validate every target before removing any: refuse changed bytes/identity.
        for row in rows:
            target=row['target'];assert os.path.dirname(target)==self.root+'/targets'
            if not os.path.lexists(target):continue
            fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as f:
                s=os.fstat(f.fileno());raw=f.read(4097)
                assert stat.S_ISREG(s.st_mode) and (s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(row['dev'],row['ino'],row['uid'],row['gid'],row['mode'])
                assert digest(raw)==row['sha256'],'HOLD_CHANGED_TARGET'
        for row in reversed(rows):
            for key in ('target','temp'):
                p=row[key]
                assert p.startswith(self.root+'/') and os.path.realpath(os.path.dirname(p))==os.path.dirname(p)
                if os.path.lexists(p):
                    s=os.lstat(p);assert (s.st_dev,s.st_ino)==(row['dev'],row['ino']);os.unlink(p)
            row['state']='RESTORED_ABSENT';self.save(rows)
        fd=os.open(self.root+'/targets',os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        return rows
def fixture():
    root=tempfile.mkdtemp(prefix='xj-p2-bootstrap-txn-fixture-');os.mkdir(root+'/targets',0o700)
    return root,Transaction(root)
def main():
    cases=[]
    for crash in [None,0,3,6]:
        root,t=fixture()
        try:
            try:t.apply(crash_after=crash,uid=1004 if '--uk' in sys.argv else None)
            except RuntimeError:assert crash is not None
            # Reconstruct from disk, not the apply object's in-memory state.
            fresh=Transaction(root);fresh.rollback();fresh.rollback()
            assert not os.listdir(root+'/targets');cases.append({'crash_after':crash,'rollback_and_replay':'PASS'})
        finally:shutil.rmtree(root)
    root,t=fixture()
    try:
        t.apply();path=root+'/targets/file-0';pathlib.Path(path).write_bytes(b'MODIFIED')
        try:t.rollback()
        except AssertionError:pass
        else:raise AssertionError('MUTATION_ACCEPTED')
        assert len(os.listdir(root+'/targets'))==7;cases.append({'modified_target':'HOLD_NO_TARGET_REMOVED'})
    finally:shutil.rmtree(root)
    root,t=fixture()
    try:
        t.apply();path=root+'/targets/file-0';raw=pathlib.Path(path).read_bytes()
        os.unlink(path);pathlib.Path(path).write_bytes(raw)
        try:t.rollback()
        except AssertionError:pass
        else:raise AssertionError('REPLACEMENT_INODE_ACCEPTED')
        assert len(os.listdir(root+'/targets'))==7;cases.append({'replacement_same_bytes':'HOLD_NO_TARGET_REMOVED'})
    finally:shutil.rmtree(root)
    root,t=fixture()
    try:
        os.symlink('/etc/passwd',root+'/targets/file-0')
        try:t.apply()
        except AssertionError:pass
        else:raise AssertionError('SYMLINK_ACCEPTED')
        assert os.path.islink(root+'/targets/file-0');cases.append({'preexisting_symlink':'REJECTED'})
    finally:shutil.rmtree(root)
    print(json.dumps({'state':'BOOTSTRAP_TRANSACTION_FIXTURE_PASS','cases':cases,'production_paths':False,
      'runtime_integration':'NOT_IMPLEMENTED','install':False,'model_calls':0},sort_keys=True))
if __name__=='__main__':
    if '--uk' in sys.argv:assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
    main()

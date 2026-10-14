import hashlib,json,os,stat,tempfile,unittest
from unittest import mock
import verify_retained_publisher as subject

class RetainedPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=self.temp.name
        self.path=self.root+'/private'
        with open(self.path,'wb') as f:f.write(b'never disclose this')
        os.chmod(self.path,0o600)
    def tearDown(self):self.temp.cleanup()
    def run_scan(self):return subject.fingerprint(self.root,os.getuid(),os.getgid())
    def test_matches_original_journal_format(self):
        os.mkdir(self.root+'/empty',0o700)
        entries=[]
        for parent,dirs,files in os.walk(self.root):
            s=os.lstat(parent);entries.append([os.path.relpath(parent,self.root),'DIR',s.st_dev,s.st_ino])
            for name in sorted(files):
                path=parent+'/'+name;s=os.lstat(path)
                with open(path,'rb') as f:h=hashlib.sha256(f.read()).hexdigest()
                entries.append([os.path.relpath(path,self.root),h,s.st_dev,s.st_ino,s.st_mtime_ns,s.st_ctime_ns])
        expected=hashlib.sha256(json.dumps(sorted(entries),separators=(',',':')).encode()).hexdigest()
        self.assertEqual(self.run_scan(),expected)
    def test_file_change_changes_fingerprint(self):
        old=self.run_scan()
        with open(self.path,'wb') as f:f.write(b'changed')
        self.assertNotEqual(old,self.run_scan())
    def test_symlink_file_rejected(self):
        os.symlink(self.path,self.root+'/alias')
        with self.assertRaises(ValueError):self.run_scan()
    def test_symlink_directory_rejected(self):
        os.symlink(self.root,self.root+'/alias')
        with self.assertRaises(ValueError):self.run_scan()
    def test_root_alias_rejected(self):
        alias=self.root+'-alias';os.symlink(self.root,alias)
        try:
            with self.assertRaises(ValueError):subject.fingerprint(alias,os.getuid(),os.getgid())
        finally:os.unlink(alias)
    def test_loose_file_rejected(self):
        os.chmod(self.path,0o644)
        with self.assertRaises(ValueError):self.run_scan()
    def test_loose_directory_rejected(self):
        os.chmod(self.root,0o755)
        with self.assertRaises(ValueError):self.run_scan()
    def test_hardlink_rejected(self):
        os.link(self.path,self.root+'/hard')
        with self.assertRaises(ValueError):self.run_scan()
    def test_fifo_rejected(self):
        os.mkfifo(self.root+'/fifo')
        with self.assertRaises(ValueError):self.run_scan()
    def test_scan_permission_error_propagates(self):
        with mock.patch.object(subject.os,'listdir',side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):self.run_scan()
    def test_missing_child_error_propagates(self):
        original=os.stat
        def changed(name,*args,**kwargs):
            if name=='private':raise FileNotFoundError('race')
            return original(name,*args,**kwargs)
        with mock.patch.object(subject.os,'stat',side_effect=changed):
            with self.assertRaises(FileNotFoundError):self.run_scan()
    def test_content_read_error_propagates(self):
        with mock.patch.object(subject.os,'read',side_effect=OSError('read failed')):
            with self.assertRaises(OSError):self.run_scan()
    def test_directory_listing_change_rejected(self):
        original=os.listdir;calls=[0]
        def changed(fd):
            calls[0]+=1
            return original(fd) if calls[0]==1 else []
        with mock.patch.object(subject.os,'listdir',side_effect=changed):
            with self.assertRaises(ValueError):self.run_scan()
    def test_unknown_target_rejected_before_read(self):
        with self.assertRaises(ValueError):subject.verify_row({'target':'/tmp/wrong','state':'PUBLISHED'})
    def test_unpublished_journal_rejected(self):
        with self.assertRaises(ValueError):subject.verify_row({'target':'/var/lib/xuanjun-development/control.git','state':'PUBLISH_INTENT'})
    def test_owner_mismatch_rejected(self):
        with self.assertRaises(ValueError):subject.fingerprint(self.root,os.getuid()+1,os.getgid())

if __name__=='__main__':unittest.main()

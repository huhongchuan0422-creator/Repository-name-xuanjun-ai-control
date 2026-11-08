import hashlib,importlib.util,io,json,os,sys,tarfile,tempfile,unittest
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','bootstrap'))
import secure_bootstrap as b
class BindingArtifactTests(unittest.TestCase):
 def test_fd_binding_and_path_replacement(self):
  with tempfile.TemporaryDirectory(dir=os.getcwd()) as d:
   scope=b.canonical({'schema':1,'default_off':True,'default_mode':'READ_ONLY','allowed_write_tools':[],'unknown_dynamic_tools':'DENY'})
   archive=io.BytesIO()
   with tarfile.open(fileobj=archive,mode='w') as t:
    m=tarfile.TarInfo('TOOL_SCOPE.json');m.size=len(scope);t.addfile(m,io.BytesIO(scope))
   carrier=archive.getvalue();manifest=b.canonical({'artifact_sha256':b.sha(carrier),'tool_scope_sha256':b.sha(scope),'members':[{'path':'TOOL_SCOPE.json','type':'file','size':len(scope),'sha256':b.sha(scope)}]})
   binding={'carrier_archive_sha256':b.sha(carrier),'carrier_manifest_sha256':b.sha(manifest),'tool_scope_sha256':b.sha(scope)}
   fds=[]
   def fd(name,data):
    p=os.path.join(d,name)
    with open(p,'wb') as f:f.write(data)
    os.chmod(p,0o600);x=os.open(p,os.O_RDONLY);fds.append(x);return x
   try:
    a=fd('archive',carrier);m=fd('manifest',manifest);s=fd('scope',scope)
    self.assertEqual(b.verify_bound_artifacts(a,m,s,binding,os.getuid()).archive,carrier)
    os.rename(os.path.join(d,'archive'),os.path.join(d,'original'));fd('archive',b'evil')
    self.assertEqual(b.verify_bound_artifacts(a,m,s,binding,os.getuid()).archive,carrier)
    for values in ((fd('wrong-archive',carrier+b'x'),m,s),(a,fd('wrong-manifest',manifest+b' '),s),(a,m,fd('wrong-scope',scope+b' '))):
     with self.assertRaisesRegex(b.Hold,'BINDING_ARTIFACT_MISMATCH'):b.verify_bound_artifacts(*values,binding,os.getuid())
    changed=dict(binding,carrier_archive_sha256='0'*64)
    with self.assertRaisesRegex(b.Hold,'BINDING_ARTIFACT_MISMATCH'):b.verify_bound_artifacts(a,m,s,changed,os.getuid())
   finally:
    for x in fds:os.close(x)
if __name__=='__main__':unittest.main()

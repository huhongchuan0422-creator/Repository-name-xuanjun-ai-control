"""Public bootstrap/pin tests. No host or network request is executed."""
import hashlib,importlib.util,pathlib,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('verify_bootstrap_binding',str(ROOT/'verify_bootstrap_binding.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def load():
    raw=(ROOT/'OWNER_DIAGNOSTIC_UNBOUND.txt').read_text();body=raw.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    m=types.ModuleType('test_diagnostic_bootstrap');exec(compile(body,'<diagnostic-bootstrap-fixture>','exec'),m.__dict__);return m
class BootstrapTests(unittest.TestCase):
    def test_unbound_template_stops_before_host_or_network(self):
        m=load()
        for key in ('DELIVERY_COMMIT','DELIVERY_SHA256','DELIVERY_BYTES'):self.assertIsNone(getattr(m,key))
        with mock.patch.object(m.os,'geteuid') as uid,mock.patch.object(m.urllib.request,'build_opener') as opener,mock.patch.object(m,'output') as output:
            self.assertEqual(m.main(),2);uid.assert_not_called();opener.assert_not_called()
        self.assertEqual(output.call_args[0][0]['phase'],'BINDING_CHECK')
    def test_bound_fixture_changes_only_three_exact_publication_fields(self):
        raw=v.expected('a'*40);row=v.verify('a'*40,raw)
        self.assertEqual(row['delta'],'EXACT_THREE_PUBLICATION_PINS');self.assertEqual(row['host_execution'],'NOT_RUN')
        self.assertIn(b'OBSERVATION_SHA256=\'b961df049e2861e4706f28f29fcf994a14fe28e153263a23ec82d4e822b9b246\'',raw)
    def test_wrong_commit_hash_size_and_additional_body_changes_reject(self):
        raw=v.expected('a'*40)
        for changed in (raw.replace(b"'"+b'a'*40+b"'",b"'"+b'b'*40+b"'"),raw.replace(b'DELIVERY_BYTES=',b'DELIVERY_BYTES=1#'),raw+b'\n',raw.replace(b'return module.main([])',b'return module.entrypoint([])')):
            with self.assertRaises(ValueError):v.verify('a'*40,changed)
        for commit in (None,'z'*40,'a'*39):
            with self.assertRaises(ValueError):v.expected(commit)
    def test_bounded_fetch_dispatches_only_readonly_main(self):
        m=load();raw=(ROOT/'diagnose_preparation.py').read_bytes();m.DELIVERY_COMMIT='a'*40
        m.DELIVERY_SHA256=hashlib.sha256(raw).hexdigest();m.DELIVERY_BYTES=len(raw)
        url=m.URL_PREFIX+m.DELIVERY_COMMIT+'/'+m.SOURCE_PATH
        response=types.SimpleNamespace(status=200,geturl=lambda:url,headers={'Content-Length':str(len(raw))},read=mock.Mock(return_value=raw),close=mock.Mock())
        opener=types.SimpleNamespace(open=mock.Mock(return_value=response));calls=[]
        def no_diagnostic_execution(code,namespace):namespace['main']=lambda args:(calls.append(args) or 0)
        with mock.patch.object(m.os,'geteuid',return_value=0),mock.patch.object(m.os,'getegid',return_value=0),\
             mock.patch.object(m.socket,'gethostname',return_value='iZd7oeikknn1z21sq6ji6zZ'),\
             mock.patch.object(m.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),mock.patch.object(m.sys,'dont_write_bytecode',True),\
             mock.patch.object(m.urllib.request,'build_opener',return_value=opener),\
             mock.patch.object(m,'exec',side_effect=no_diagnostic_execution,create=True),mock.patch.object(m,'output') as output:
            self.assertEqual(m.main(),0)
        self.assertEqual(calls,[[]]);output.assert_not_called();response.read.assert_called_once_with(len(raw)+1);response.close.assert_called_once_with()
        self.assertEqual(opener.open.call_args[0][0].full_url,url)
        self.assertEqual(m.SOURCE_PATH,'evidence/p2-epoch7-access-repair-20261014/preparation-diagnostic-r6/diagnose_preparation.py')
if __name__=='__main__':unittest.main(verbosity=2)

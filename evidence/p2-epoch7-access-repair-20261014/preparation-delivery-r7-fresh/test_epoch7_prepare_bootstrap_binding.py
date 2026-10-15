"""Pin-only Owner bootstrap checks; no host/network calls or helper execution."""
import hashlib,pathlib,types,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parent
# Synthetic commit is confined to this in-memory test; no publication is asserted.
COMMIT='a'*40
RAW=(ROOT/'epoch7_prepare_delivery.py').read_bytes()
DIGEST=hashlib.sha256(RAW).hexdigest()
SIZE=len(RAW)


def load(name):
    raw=(ROOT/'OWNER_PREPARATION_UNBOUND.txt').read_text()
    if name=='TEST_BOUND_IN_MEMORY':
        for key,value in (('DELIVERY_COMMIT',COMMIT),('DELIVERY_SHA256',DIGEST),('DELIVERY_BYTES',SIZE),('TOPOLOGY_REVIEW_ID',123456789),('RETAINED_RENEWAL_TIMER','enable-after-reviewed-checks')):
            raw=raw.replace(key+'=None',key+'='+repr(value))
    body=raw.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    module=types.ModuleType('test_owner_bootstrap_binding')
    exec(compile(body,'<owner-bootstrap-pin-test>','exec'),module.__dict__)
    return module


class BootstrapBindingTests(unittest.TestCase):
    def test_three_publication_fields_are_unbound_and_first_comment_is_neutral(self):
        raw=(ROOT/'OWNER_PREPARATION_UNBOUND.txt').read_text();module=load('UNBOUND')
        self.assertEqual(raw.splitlines()[0],'# Verify all three delivery publication pins before use; observation is fixed.')
        for name in ('DELIVERY_COMMIT','DELIVERY_SHA256','DELIVERY_BYTES'):
            self.assertIsNone(getattr(module,name));self.assertEqual(raw.count(name+'=None'),1)
        self.assertFalse((ROOT/'OWNER_PREPARATION_BOUND.txt').exists())
    def test_test_only_binding_authenticates_exact_local_helper_bytes(self):
        module=load('TEST_BOUND_IN_MEMORY');raw=(ROOT/'epoch7_prepare_delivery.py').read_bytes()
        self.assertEqual((module.DELIVERY_COMMIT,module.DELIVERY_SHA256,module.DELIVERY_BYTES),(COMMIT,DIGEST,SIZE))
        self.assertEqual((len(raw),hashlib.sha256(raw).hexdigest()),(SIZE,DIGEST))
    def test_genuine_observation_unchanged(self):
        prior=load('OWNER_PREPARATION_UNBOUND.txt');bound=load('TEST_BOUND_IN_MEMORY')
        for name in ('OBSERVATION_PATH','OBSERVATION_SHA256','SOURCE_PATH','CAND'):
            self.assertEqual(getattr(prior,name),getattr(bound,name))
        self.assertEqual(bound.OBSERVATION_PATH,bound.CAND+'/epoch7-observation-8df3b22b3762070f.private.json')
        self.assertEqual(bound.OBSERVATION_SHA256,'a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68')
    def test_missing_own_publication_pin_refuses_before_host_or_network(self):
        for name in ('DELIVERY_COMMIT','DELIVERY_SHA256','DELIVERY_BYTES'):
            module=load('TEST_BOUND_IN_MEMORY');setattr(module,name,None)
            with self.subTest(name=name),mock.patch.object(module.os,'geteuid') as uid,\
                 mock.patch.object(module.urllib.request,'build_opener') as opener,mock.patch.object(module,'output') as output:
                self.assertEqual(module.main(),2)
                uid.assert_not_called();opener.assert_not_called()
                self.assertEqual(output.call_args[0][0]['phase'],'BINDING_CHECK')
    def test_missing_review_or_timer_refuses_before_host_or_network(self):
        for name in ('TOPOLOGY_REVIEW_ID','RETAINED_RENEWAL_TIMER'):
            module=load('TEST_BOUND_IN_MEMORY');setattr(module,name,None)
            with mock.patch.object(module.os,'geteuid') as uid,mock.patch.object(module.urllib.request,'build_opener') as opener,mock.patch.object(module,'output'):
                self.assertEqual(module.main(),2)
            uid.assert_not_called();opener.assert_not_called()
    def test_invalid_review_id_or_timer_refuses_before_host_or_network(self):
        for name,value in (('TOPOLOGY_REVIEW_ID',True),('TOPOLOGY_REVIEW_ID',0),('TOPOLOGY_REVIEW_ID',-1),('TOPOLOGY_REVIEW_ID',10**20),('TOPOLOGY_REVIEW_ID','123'),('RETAINED_RENEWAL_TIMER','disable')):
            module=load('TEST_BOUND_IN_MEMORY');setattr(module,name,value)
            with mock.patch.object(module.os,'geteuid') as uid,mock.patch.object(module.urllib.request,'build_opener') as opener,mock.patch.object(module,'output'):
                self.assertEqual(module.main(),2)
            uid.assert_not_called();opener.assert_not_called()
    def test_unbound_review_fields_and_fixed_source_are_explicit(self):
        module=load('UNBOUND');self.assertIsNone(module.TOPOLOGY_REVIEW_ID);self.assertIsNone(module.RETAINED_RENEWAL_TIMER)
        self.assertEqual(module.SOURCE_PATH,'evidence/p2-epoch7-access-repair-20261014/preparation-delivery-r7-fresh/epoch7_prepare_delivery.py')
    def invoke_download(self,tamper=False):
        module=load('TEST_BOUND_IN_MEMORY');raw=(ROOT/'epoch7_prepare_delivery.py').read_bytes()
        if tamper:raw=b'X'+raw[1:]
        url=module.URL_PREFIX+COMMIT+'/'+module.SOURCE_PATH
        response=types.SimpleNamespace(status=200,geturl=lambda:url,headers={'Content-Length':str(SIZE)},
            read=mock.Mock(return_value=raw),close=mock.Mock())
        opener=types.SimpleNamespace(open=mock.Mock(return_value=response));calls=[]
        def no_helper_execution(code,namespace):
            self.assertEqual(code.co_filename,'<verified-preparation-delivery>')
            namespace['entrypoint']=lambda args:(calls.append(args) or 0)
        with mock.patch.object(module.os,'geteuid',return_value=0),mock.patch.object(module.os,'getegid',return_value=0),\
             mock.patch.object(module.socket,'gethostname',return_value='iZd7oeikknn1z21sq6ji6zZ'),\
             mock.patch.object(module.sys,'flags',types.SimpleNamespace(isolated=1,no_site=1)),\
             mock.patch.object(module.sys,'dont_write_bytecode',True),\
             mock.patch.object(module.urllib.request,'build_opener',return_value=opener),\
             mock.patch.object(module,'exec',side_effect=no_helper_execution,create=True) as executed,\
             mock.patch.object(module,'output') as output:
            result=module.main()
        return module,result,opener,response,executed,calls,output
    def test_exact_bounded_fetch_dispatches_only_fixed_observation_arguments(self):
        module,result,opener,response,executed,calls,output=self.invoke_download()
        self.assertEqual(result,0);output.assert_not_called();self.assertEqual(executed.call_count,1)
        self.assertEqual(calls,[['--observation',module.OBSERVATION_PATH,'--observation-sha256',module.OBSERVATION_SHA256,'--topology-review-id','123456789','--retained-renewal-timer','enable-after-reviewed-checks']])
        request=opener.open.call_args[0][0]
        self.assertEqual(request.full_url,module.URL_PREFIX+COMMIT+'/'+module.SOURCE_PATH)
        self.assertEqual(request.get_header('Accept-encoding'),'identity')
        response.read.assert_called_once_with(SIZE+1);response.close.assert_called_once_with()
    def test_changed_download_never_executes_or_dispatches(self):
        module,result,opener,response,executed,calls,output=self.invoke_download(tamper=True)
        self.assertEqual(result,2);executed.assert_not_called();self.assertEqual(calls,[])
        response.close.assert_called_once_with();self.assertEqual(output.call_args[0][0]['phase'],'DOWNLOAD_VERIFIED_DELIVERY')


if __name__=='__main__':unittest.main(verbosity=2)

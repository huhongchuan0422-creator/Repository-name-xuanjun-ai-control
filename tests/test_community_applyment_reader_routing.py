"""Synthetic provider routing; no real keys, DB, HTTP, account or submissions.

Crypto is unchanged. AST-extracted existing host/service methods permit narrow
routing tests in the author runtime without its unavailable cryptography wheel;
these method-unit tests do not claim a full host/crypto integration run.
"""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from scripts.community_applyment_readers import ApplymentReaders

ROOT=Path(__file__).resolve().parents[1]
OLD='1234562863';NEW='1234563578'


def method(file,name,namespace=None,owner=None):
    tree=ast.parse((ROOT/'scripts'/file).read_text())
    nodes=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==owner).body if owner else tree.body
    node=copy.deepcopy(next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name==name))
    node.decorator_list=[]
    scope={} if namespace is None else dict(namespace)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),file,'exec'),scope)
    return scope[name]


class Routing(unittest.TestCase):
    def setUp(self):
        self.old=SimpleNamespace(_mchid=OLD)
        self.new=SimpleNamespace(_mchid=NEW)
        self.routes=ApplymentReaders(self.old,{NEW:self.new},NEW)

    def test_unbound_draft_uses_new_without_writing_or_binding_record(self):
        for record in ({},{'state':'DRAFT','provider_sp_mchid':None},{'state':'INTERNAL_APPROVED','profile':{}}):
            before=copy.deepcopy(record)
            self.assertIs(self.routes.for_record(record,submission=True),self.new)
            self.assertEqual(record,before)

    def test_accepted_old_and_finished_old_keep_original_reader(self):
        for state in ('SUBMITTED_TO_PROVIDER','SUBMISSION_UNKNOWN','CORRECTION','FINISHED'):
            r={'state':state,'provider_sp_mchid':OLD,'business_code':'original','applyment_id':'1'}
            self.assertIs(self.routes.for_record(r),self.old)
            self.assertIs(self.routes.for_record(r,submission=True),self.old)

    def test_new_accepted_record_keeps_new_reader(self):
        self.assertIs(self.routes.for_record({'provider_sp_mchid':NEW,'applyment_id':'2'}),self.new)

    def test_untrusted_legacy_trace_cannot_be_guessed_or_fall_back(self):
        for key,value in [('business_code','old'),('applyment_id','1'),('submission_receipts',[{}]),('submission_recovery_receipt',{'signed_at':1}),('submission_intent_token','pending')]:
            for submission in (False,True):
                with self.subTest(key=key,submission=submission),self.assertRaisesRegex(PermissionError,'OWNERSHIP_UNCONFIRMED'):
                    self.routes.for_record({key:value},submission=submission)

    def test_orphan_accepted_state_and_missing_explicit_default_fail_closed(self):
        for record in ({'state':'SUBMITTED_TO_PROVIDER'},{'state':'SUBMISSION_UNKNOWN'},{'provider_state':'APPLYMENT_STATE_FINISHED'},{'provider_sign_url':'untrusted'}):
            with self.subTest(record=record),self.assertRaisesRegex(PermissionError,'OWNERSHIP_UNCONFIRMED'):
                self.routes.for_record(record)
        with self.assertRaisesRegex(ValueError,'SUBMISSION_PROVIDER_READER_REQUIRED'):
            ApplymentReaders(self.old,{NEW:self.new})

    def test_unknown_provider_and_missing_new_reader_fail_closed(self):
        with self.assertRaisesRegex(PermissionError,'READER_UNAVAILABLE'):
            self.routes.for_record({'provider_sp_mchid':'1234560000'})
        with self.assertRaisesRegex(ValueError,'SUBMISSION_PROVIDER_READER_REQUIRED'):
            ApplymentReaders(self.old,{},NEW)
        with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):
            ApplymentReaders(self.old,{NEW:self.old},NEW)

    def test_registry_cannot_be_changed_by_request_or_other_draft(self):
        with self.assertRaises(TypeError):self.routes.readers[NEW]=self.old
        a=self.routes.for_record({});b=self.routes.for_record({'provider_sp_mchid':OLD})
        self.assertIs(a,self.new);self.assertIs(b,self.old);self.assertEqual(self.old._mchid,OLD)

    def test_single_reader_original_legacy_query_contract_is_preserved(self):
        routes=ApplymentReaders(self.old)
        self.assertIs(routes.for_record({'business_code':'legacy'}),self.old)
        with self.assertRaisesRegex(PermissionError,'DOMAIN_UNCONFIRMED'):
            routes.for_record({'business_code':'legacy'},submission=True)

    def open_registry(self,config,opened=None):
        def load(path):self.assertEqual(path,'/protected/registry.json');return config
        def open_reader(path,clock):
            self.assertEqual(path,'/protected/new-reader.json')
            if opened is not None:opened.append(path)
            return self.new
        f=method('community_platform_host.py','_open_applyment_readers',{'Path':Path,'load_protected':load,'_open_provider_reader':open_reader})
        return f('/protected/registry.json',self.old,lambda:0)

    def test_protected_host_assembly_keeps_commerce_legacy_reader(self):
        readers,default=self.open_registry({'version':1,'submission_provider':NEW,'additional_readers':{NEW:'/protected/new-reader.json'}})
        self.assertIs(readers[NEW],self.new);self.assertEqual(default,NEW);self.assertEqual(self.old._mchid,OLD)

    def test_protected_host_bad_role_or_reference_never_falls_back(self):
        for config in [
            {'version':1,'submission_provider':NEW,'additional_readers':{}},
            {'version':1,'submission_provider':NEW,'additional_readers':{NEW:'relative.json'}},
            {'version':1,'submission_provider':NEW,'additional_readers':{OLD:'/protected/new-reader.json'}},
            {'version':1,'submission_provider':NEW,'additional_readers':{},'public_key_id':'guessed'},
        ]:
            with self.subTest(config=config),self.assertRaises(ValueError):self.open_registry(config)

    def test_observer_and_owner_completion_network_use_exact_trusted_provider(self):
        for file,owner,binding in [('community_wechat_observer.py','ApplymentObserver',{'provider_merchant':OLD,'business_code':'old'}),('community_owner_submit_recovery.py','OwnerSubmissionRecovery',{'merchant':OLD,'code':'old'})]:
            calls=[]
            def request(reader,*args,**kwargs):calls.append(reader);return 'synthetic verified result'
            need=method(file,'need')
            network=method(file,'network',{'need':need,'request':request},owner)
            self.assertEqual(network(self.old,binding),'synthetic verified result')
            with self.assertRaises(PermissionError):network(self.new,binding)
            self.assertEqual(calls,[self.old])

    def test_cross_provider_query_completion_rejected_before_record_commit(self):
        service=SimpleNamespace(center=None,reader_for_record=self.routes.for_record)
        commit=method('community_wechat_applyment.py','_commit_provider_query',owner='WechatApplyment')
        with self.assertRaisesRegex(PermissionError,'SERVICE_MERCHANT_CHANGED'):
            commit(service,'synthetic','owner',{'provider_sp_mchid':OLD},NEW,({},'',{}),'owner',lambda:'owner')

    def test_service_domain_decision_does_not_mutate_global_commerce_reader(self):
        service=SimpleNamespace(provider_readers=self.routes,reader=self.old)
        service.reader_for_record=method('community_wechat_applyment.py','reader_for_record',owner='WechatApplyment').__get__(service)
        domain=method('community_wechat_applyment.py','_provider_domain',owner='WechatApplyment')
        self.assertEqual(domain(service,{},submission=True),NEW)
        self.assertEqual(domain(service,{'provider_sp_mchid':OLD}),OLD)
        self.assertIs(service.reader,self.old)

    def test_media_receipts_cannot_cross_provider_even_on_same_application(self):
        canonical=method('pr122_customer_core.py','canonical',{'json':json})
        validate=method('community_wechat_applyment.py','_validate_media',{'hashlib':hashlib,'canonical':canonical,'json':json},'WechatApplyment')
        source='a'*64;application='synthetic';kind='business_license';media='synthetic-media'
        oldkey=hashlib.sha256(canonical([OLD,application,kind,source])).hexdigest()
        class DB:
            def execute(self,*args):return self
            def fetchall(self):return [(oldkey,json.dumps({'kind':kind,'sha256':source,'media_id':media}))]
        center=SimpleNamespace(db=DB(),decrypt=lambda payload,label:payload,now=lambda:1)
        meta={'materials':{kind:{'sha256':source,'expires_at':None}}}
        service=SimpleNamespace(center=center,reader_for_record=self.routes.for_record,_read=lambda a:{'provider_sp_mchid':OLD})
        validate(service,{'business_license_copy':media},application,meta)
        service._read=lambda a:{}
        with self.assertRaisesRegex(PermissionError,'CURRENT_ORIGINAL_APPLICATION_MEDIA_REQUIRED'):
            validate(service,{'business_license_copy':media},application,meta)
        oldkey=hashlib.sha256(canonical([NEW,application,kind,source])).hexdigest()
        validate(service,{'business_license_copy':media},application,meta)

    def test_sensitive_field_encryption_uses_selected_reader_recursively(self):
        self.old._public='old-synthetic-key';self.new._public='new-synthetic-key'
        def load(key):return SimpleNamespace(key_size=2048,encrypt=lambda value,algorithm:key.encode())
        encrypt=method('community_wechat_applyment.py','_encrypt',{
            'SENSITIVE':{'account_number'},'serialization':SimpleNamespace(load_pem_public_key=load),
            'padding':SimpleNamespace(OAEP=lambda **kwargs:None,MGF1=lambda value:None),
            'hashes':SimpleNamespace(SHA1=lambda:None),'base64':base64},'WechatApplyment')
        service=SimpleNamespace(reader=self.old);service._encrypt=encrypt.__get__(service)
        result=service._encrypt({'nested':[{'account_number':'synthetic'}]},reader=self.new)
        self.assertEqual(base64.b64decode(result['nested'][0]['account_number']),b'new-synthetic-key')
        self.assertIs(service.reader,self.old)

    def test_actual_transport_call_sites_use_selected_reader_without_global_switch(self):
        tree=ast.parse((ROOT/'scripts/community_wechat_applyment.py').read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='request']
        self.assertTrue(calls)
        self.assertTrue(all(isinstance(n.args[0],ast.Name) and n.args[0].id=='reader' for n in calls))
        tree=ast.parse((ROOT/'scripts/community_platform_host.py').read_text())
        host=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PlatformHost')
        body=ast.unparse(host)
        self.assertIn('_open_applyment_readers',body)
        self.assertIn('provider_readers=applyment_readers',body)
        self.assertIn('_wire_commerce(owner.application, reader, commerce_policy)',body)


if __name__=='__main__':unittest.main()

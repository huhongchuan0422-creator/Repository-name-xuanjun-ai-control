import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from owner_feishu_https import OwnerFeishuHTTPS,NoRedirect


class HTTPSTests(unittest.TestCase):
    def setUp(self):
        self.api=OwnerFeishuHTTPS.__new__(OwnerFeishuHTTPS)
        self.api.binding={'chat_id':'oc_fixture','app_id':'cli_fixture','package_sha256':'a'*64}
        self.api.token='fixture-not-a-credential';self.calls=[]
        def http(path,body,token):self.calls.append(path);return {'code':0,'data':{}}
        self.api._http=http

    def test_history_only_fixed_chat_and_route(self):
        path='im/v1/messages?container_id_type=chat&container_id=oc_fixture&page_size=50&sort_type=ByCreateTimeAsc'
        self.api.get(path);self.assertEqual(self.calls,[path])
        for changed in (path.replace('oc_fixture','oc_other'),path+'&container_id=oc_fixture',
                        path+'&unexpected=1','https://invalid/im/v1/messages',path+'#fragment'):
            with self.assertRaises(ValueError):self.api.get(changed)
        self.assertEqual(len(self.calls),1)

    def test_get_receipt_route_and_redirect_rejected(self):
        self.api.get('im/v1/messages/om_fixture')
        with self.assertRaises(ValueError):self.api.get('im/v1/messages/om_fixture/../other')
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,'',{},'https://invalid')

    def test_send_no_arbitrary_destination_or_http_operation(self):
        body={'receive_id':'oc_fixture','msg_type':'text','content':'{"text":"fixture"}','uuid':'fixture'}
        self.api('im/v1/messages?receive_id_type=chat_id',body)
        for changed in ({**body,'receive_id':'oc_other'}, {**body,'msg_type':'image'}, {**body,'extra':'ignored'}):
            with self.assertRaises(ValueError):self.api('im/v1/messages?receive_id_type=chat_id',changed)
        with self.assertRaises(ValueError):self.api('auth/v3/tenant_access_token/internal',body)
        self.assertEqual(len(self.calls),1)

    def test_private_owner_reverified_and_group_rejected(self):
        replies=[{'code':0,'bot':{'app_name':'玄钧云汇开发总管'}}, {'code':0,'data':{'chat_mode':'p2p'}}]
        self.api._http=lambda *args:replies.pop(0)
        self.api.verify_private_owner(dict(self.api.binding))
        replies[:]=[{'code':0,'bot':{'app_name':'玄钧云汇开发总管'}}, {'code':0,'data':{'chat_mode':'group'}}]
        with self.assertRaises(ValueError):self.api.verify_private_owner(dict(self.api.binding))

    def test_credential_owner_mismatch_before_config_read(self):
        class User:pw_uid=42
        with patch('owner_feishu_https.pwd.getpwnam',return_value=User()),patch('owner_feishu_https.os.geteuid',return_value=43),patch('owner_feishu_https.protected_json') as read:
            with self.assertRaises(ValueError):OwnerFeishuHTTPS(self.api.binding)
            read.assert_not_called()

    def test_http_errors_never_export_credential_strings(self):
        api=OwnerFeishuHTTPS.__new__(OwnerFeishuHTTPS)
        with patch('owner_feishu_https.urllib.request.build_opener',side_effect=RuntimeError('FIXTURE_PRIVATE_EXCEPTION')):
            with self.assertRaisesRegex(RuntimeError,'^FEISHU_API_UNCONFIRMED_NO_RETRY$'):
                api._http('bot/v3/info',None,'fixture-not-a-credential')

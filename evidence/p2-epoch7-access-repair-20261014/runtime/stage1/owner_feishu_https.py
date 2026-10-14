"""Fixed-host Feishu transport for the xuanjun_dev credential-owning bridge only."""
import json
import os
import pwd
import re
import stat
import urllib.parse
import urllib.request

PROFILE='/home/xuanjun_dev/.openclaw/openclaw.json'
BINDING='/etc/xuanjun-development/p2-owner-feishu-binding.json'
MAXIMUM=2097152


def protected_json(path, owner_uid, maximum):
    if not os.path.isabs(path) or os.path.realpath(path)!=path:
        raise ValueError('PROTECTED_FILE_REQUIRED')
    if owner_uid==0:
        parent=os.path.dirname(path)
        while True:
            info=os.lstat(parent)
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
                raise ValueError('PROTECTED_PARENT_REQUIRED')
            if parent=='/':break
            parent=os.path.dirname(parent)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid!=owner_uid or info.st_mode&0o022 or
                info.st_size>maximum or (path==PROFILE and info.st_mode&0o077)):
            raise ValueError('PROTECTED_FILE_REJECTED')
        raw=os.read(fd,maximum+1)
        if len(raw)>maximum:raise ValueError('PROTECTED_FILE_BOUND')
        return json.loads(raw.decode('utf-8'))
    finally:os.close(fd)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('FEISHU_REDIRECT_REJECTED')


class OwnerFeishuHTTPS:
    def __init__(self, binding):
        uid=pwd.getpwnam('xuanjun_dev').pw_uid
        if uid<1 or os.geteuid()!=uid:raise ValueError('FEISHU_CREDENTIAL_OWNER_REQUIRED')
        config=protected_json(PROFILE,uid,MAXIMUM)['channels']['feishu']
        if (config.get('enabled') is not True or config.get('appId')!=binding['app_id'] or
                not isinstance(config.get('appSecret'),str) or not config['appSecret']):
            raise ValueError('FEISHU_PROFILE_BINDING_REQUIRED')
        self.binding=dict(binding)
        auth=self._http('auth/v3/tenant_access_token/internal',
            {'app_id':config['appId'],'app_secret':config['appSecret']},None)
        if type(auth.get('code')) is not int or auth['code']!=0 or not isinstance(auth.get('tenant_access_token'),str) or not auth['tenant_access_token']:
            raise ValueError('FEISHU_AUTH_UNCONFIRMED')
        self.token=auth['tenant_access_token']

    def _http(self,path,body,token):
        headers={'Content-Type':'application/json; charset=utf-8'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request('https://open.feishu.cn/open-apis/'+path,
            data=json.dumps(body).encode('utf-8') if body is not None else None,headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=10) as response:
                raw=response.read(MAXIMUM+1)
            if len(raw)>MAXIMUM:raise ValueError('FEISHU_RESPONSE_BOUND')
            value=json.loads(raw.decode('utf-8'))
            if not isinstance(value,dict):raise ValueError('FEISHU_RESPONSE_SHAPE')
            return value
        except Exception:
            raise RuntimeError('FEISHU_API_UNCONFIRMED_NO_RETRY')

    def verify_private_owner(self,binding):
        if binding!=self.binding:raise ValueError('FEISHU_BINDING_CHANGED')
        bot=self._http('bot/v3/info',None,self.token)
        chat=self._http('im/v1/chats/'+self.binding['chat_id'],None,self.token)
        if (type(bot.get('code')) is not int or bot['code']!=0 or
                bot.get('bot',{}).get('app_name')!='玄钧云汇开发总管' or
                type(chat.get('code')) is not int or chat['code']!=0 or
                chat.get('data',{}).get('chat_mode')!='p2p'):
            raise ValueError('VERIFIED_PRIVATE_OWNER_REQUIRED')

    def __call__(self,path,body):
        if (path!='im/v1/messages?receive_id_type=chat_id' or not isinstance(body,dict) or
                set(body)!={'receive_id','msg_type','content','uuid'} or
                body['receive_id']!=self.binding['chat_id'] or body['msg_type']!='text'):
            raise ValueError('FEISHU_SEND_ENDPOINT_REJECTED')
        return self._http(path,body,self.token)

    def get(self,path):
        if re.fullmatch(r'im/v1/messages/om_[A-Za-z0-9_-]{1,128}',path):
            return self._http(path,None,self.token)
        parsed=urllib.parse.urlsplit(path)
        pairs=urllib.parse.parse_qsl(parsed.query,strict_parsing=True)
        params=dict(pairs)
        if (parsed.scheme or parsed.netloc or parsed.fragment or parsed.path!='im/v1/messages' or
                len(params)!=len(pairs) or set(params)-{'container_id_type','container_id','page_size','sort_type','page_token'} or
                params.get('container_id_type')!='chat' or params.get('container_id')!=self.binding['chat_id'] or
                params.get('page_size')!='50' or params.get('sort_type')!='ByCreateTimeAsc' or
                ('page_token' in params and (not params['page_token'] or len(params['page_token'])>4096))):
            raise ValueError('FEISHU_HISTORY_ENDPOINT_REJECTED')
        return self._http(path,None,self.token)


def installed_binding():
    value=protected_json(BINDING,0,65536)
    if not isinstance(value,dict) or set(value)!={'chat_id','app_id','package_sha256'}:
        raise ValueError('PROTECTED_OWNER_BINDING_REQUIRED')
    if (not isinstance(value['chat_id'],str) or re.fullmatch(r'oc_[A-Za-z0-9_-]{1,128}',value['chat_id']) is None or
            not isinstance(value['app_id'],str) or re.fullmatch(r'cli_[A-Za-z0-9_-]{1,128}',value['app_id']) is None or
            not isinstance(value['package_sha256'],str) or re.fullmatch(r'[a-f0-9]{64}',value['package_sha256']) is None):
        raise ValueError('PROTECTED_OWNER_BINDING_REJECTED')
    return value

import os,sys,stat,json,hashlib,socket,re,urllib.request,urllib.error,urllib.parse
assert os.geteuid()==0 and socket.gethostname().split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
assert len(sys.argv)==2 and sys.argv[1].isdigit()
base='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1'
s=os.lstat(base);assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o700 and os.path.realpath(base)==base
root=base+'/owner-canary-pagination-'+sys.argv[1];os.mkdir(root,0o700)
def read(path,uid,maximum=2097152):
    assert os.path.realpath(path)==path
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        assert stat.S_ISREG(s.st_mode) and s.st_uid==uid and not s.st_mode&0o077 and s.st_size<=maximum
        raw=f.read(maximum+1)
        assert len(raw)<=maximum
        return raw,s
def api(path,token=None,body=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=urllib.request.Request('https://open.feishu.cn/open-apis/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=15) as f:raw=f.read(2097153)
        assert len(raw)<=2097152
        return json.loads(raw.decode())
    except urllib.error.HTTPError as e:return {'code':e.code}
private={'schema':1,'artifact_id':11819078922,'runtime_release_sha256':'27b8d6c61f5cf4590cfbe87299c334c6231ad259b9088259470bafaecd0b2424','auth_references':[]}
public={'schema':1,'state':'OWNER_BINDING_INPUTS_HOLD','credential_values_exported':False,'notification_sends':0,'model_calls':0,'services_changed':False,'canonical_mutation':False}
try:
    profile='/home/xuanjun_dev/.openclaw/openclaw.json'
    raw,s=read(profile,1002);config=json.loads(raw.decode())['channels']['feishu']
    private['auth_references'].append({'path':profile,'sha256':hashlib.sha256(raw).hexdigest(),'owner_uid':1002,'mode':stat.S_IMODE(s.st_mode)})
    authpath='/home/xuanjun_dev/.openclaw/agents/developer/agent/openclaw-agent.sqlite'
    raw,s=read(authpath,1002,16777216)
    private['auth_references'].append({'path':authpath,'sha256':hashlib.sha256(raw).hexdigest(),'owner_uid':1002,'mode':stat.S_IMODE(s.st_mode)})
    routes=set()
    agents='/home/xuanjun_dev/.openclaw/agents'
    for agent in sorted(os.listdir(agents))[:32]:
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',agent):continue
        path=agents+'/'+agent+'/sessions/sessions.json'
        try:raw,s=read(path,1002);records=json.loads(raw.decode())
        except (OSError,ValueError,AssertionError):continue
        if not isinstance(records,dict) or len(records)>10000:continue
        for key in records:
            match=re.search(r':feishu:(?:group|direct):(oc_[A-Za-z0-9_-]+)$',key)
            if match:routes.add(match.group(1))
    if not routes:
        import subprocess
        cli='/home/xuanjun_dev/.openclaw/bin/openclaw'
        with open(cli,'rb') as f:assert hashlib.sha256(f.read()).hexdigest()=='b6aff1f40be0d46330c167e44525ef9080d66e40bb36dbb66c3811b4103fe3f2'
        p=subprocess.run(['/usr/sbin/runuser','-u','xuanjun_dev','--',cli,'sessions','--json','--all-agents'],env={'HOME':'/home/xuanjun_dev','PATH':'/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C','NO_COLOR':'1'},stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30)
        public['native_session_query_exit']=p.returncode
        assert p.returncode==0 and len(p.stdout)<=2097152
        text=p.stdout.decode('utf-8')
        records=json.loads(text[text.index('{'):]).get('sessions',[])
        assert isinstance(records,list) and len(records)<=10000
        for record in records:
            match=re.search(r':feishu:(?:group|direct):(oc_[A-Za-z0-9_-]+)$',record.get('key',''))
            if match:routes.add(match.group(1))
    public['existing_chat_candidate_count']=len(routes)
    assert len(routes)==1 and re.fullmatch(r'cli_[A-Za-z0-9_-]{1,128}',config.get('appId',''))
    chat_id=next(iter(routes))
    auth=api('auth/v3/tenant_access_token/internal',body={'app_id':config['appId'],'app_secret':config['appSecret']})
    public['auth_code']=auth.get('code');assert auth.get('code')==0
    token=auth['tenant_access_token']
    bot=api('bot/v3/info',token)
    public['expected_bot_name_match']=bot.get('bot',{}).get('app_name')=='玄钧云汇开发总管'
    chat=api('im/v1/chats/'+chat_id,token)
    public['chat_is_p2p']=chat.get('code')==0 and chat.get('data',{}).get('chat_mode')=='p2p'
    matches=[];seen=set();cursor=None
    public.update(history_pages=0,history_items=0,history_exhausted=False)
    for page in range(20):
        query={'container_id_type':'chat','container_id':chat_id,'sort_type':'ByCreateTimeDesc','page_size':'50'}
        if cursor:query['page_token']=cursor
        history=api('im/v1/messages?'+urllib.parse.urlencode(query),token)
        public['history_api_code']=history.get('code')
        if history.get('code')!=0:raise ValueError('HISTORY_API_REJECTED')
        data=history.get('data');assert isinstance(data,dict)
        items=data.get('items');assert isinstance(items,list) and len(items)<=50 and isinstance(data.get('has_more'),bool)
        public['history_pages']+=1;public['history_items']+=len(items)
        for item in items:
            try:
                value=json.loads(item.get('body',{}).get('content','')).get('text','')
                if isinstance(value,str) and 'XJ_P2_FEISHU_CANARY_11787198841_20261013' in value and item.get('chat_id')==chat_id:
                    matches.append(item['message_id'])
            except (ValueError,TypeError,KeyError):pass
        if matches:
            public['canary_found_page']=page+1;break
        if not data['has_more']:
            public['history_exhausted']=True;break
        cursor=data.get('page_token')
        if not isinstance(cursor,str) or not cursor or len(cursor)>4096 or cursor in seen:raise ValueError('HISTORY_CURSOR_INVALID')
        seen.add(cursor)
    if not matches:public['history_hold_reason']='HISTORY_EXHAUSTED_CANARY_NOT_FOUND' if public['history_exhausted'] else 'HISTORY_PAGE_LIMIT_CANARY_NOT_FOUND'
    public['prior_canary_readback_match']=bool(matches)
    assert public['expected_bot_name_match'] and public['chat_is_p2p'] and matches
    private['feishu_binding']={'app_id':config['appId'],'chat_id':chat_id,'package_sha256':private['runtime_release_sha256']}
    private['prior_canary_message_ids']=matches
    public['state']='EXISTING_FEISHU_CHAT_BINDING_INPUTS_VERIFIED'
except Exception as e:public['hold_reason']=type(e).__name__
private['public_receipt']=public
raw=(json.dumps(private,sort_keys=True,separators=(',',':'))+'\n').encode()
path=root+'/protected-owner-binding-inputs.json'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
print(json.dumps(public,sort_keys=True))
print('OWNER_BINDING_INPUTS_PATH='+path)
print('OWNER_BINDING_INPUTS_SHA256='+hashlib.sha256(raw).hexdigest())

assert public['state']=='EXISTING_FEISHU_CHAT_BINDING_INPUTS_VERIFIED','OWNER_CANARY_PAGINATION_HOLD'

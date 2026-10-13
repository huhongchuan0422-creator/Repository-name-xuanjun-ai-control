"""Fixed UK Feishu metadata preflight; no credential output or sends."""
import json, os, pwd, socket, stat, subprocess, re
HOME_ROOT='/home/xuanjun_dev/.openclaw'
CANARY_SEND_ENABLED=False  # One authorized canary completed; future scans stay read-only.
def read_json(path):
    if os.path.realpath(path)!=path: raise ValueError('NONCANONICAL')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024*1024: raise ValueError('BOUND')
        data=os.read(fd,2*1024*1024+1)
        if len(data)>2*1024*1024: raise ValueError('BOUND')
        return json.loads(data.decode('utf-8'))
    finally: os.close(fd)
def collect():
    result={'state':'P2_FEISHU_METADATA_ONLY','model_calls':0,'send_performed':False,'configs':[]}
    for path in (HOME_ROOT+'/openclaw.json',HOME_ROOT+'/config.json'):
        item={'path':path}
        try:
            data=read_json(path)
            channels=data.get('channels',{})
            feishu=channels.get('feishu') if isinstance(channels,dict) else None
            item['feishu_configured']=isinstance(feishu,dict)
            if isinstance(feishu,dict):
                item['enabled']=feishu.get('enabled') if type(feishu.get('enabled')) is bool else None
                item['app_id_present']=bool(feishu.get('appId'))
                item['app_secret_present']=bool(feishu.get('appSecret'))
                accounts=feishu.get('accounts')
                item['account_count']=len(accounts) if isinstance(accounts,dict) else None
                item['allow_from_count']=len(feishu.get('allowFrom')) if isinstance(feishu.get('allowFrom'),list) else None
                item['connection_mode']=feishu.get('connectionMode') if feishu.get('connectionMode') in ('websocket','webhook') else 'UNKNOWN'
                item['dm_policy']=feishu.get('dmPolicy') if feishu.get('dmPolicy') in ('pairing','allowlist','open','disabled') else 'UNKNOWN'
                if isinstance(accounts,dict):
                    item['accounts_metadata']=[{'enabled':a.get('enabled') if type(a.get('enabled')) is bool else None,
                      'app_id_present':bool(a.get('appId')),'app_secret_present':bool(a.get('appSecret')),
                      'allow_from_count':len(a.get('allowFrom')) if isinstance(a.get('allowFrom'),list) else None}
                      for a in accounts.values() if isinstance(a,dict)][:20]
            item['status']='READ_METADATA_ONLY'
        except (OSError,ValueError,TypeError,UnicodeError): item['status']='UNAVAILABLE_OR_INVALID'
        result['configs'].append(item)
    result['session_inventory']=[]
    agents=HOME_ROOT+'/agents'
    try: names=sorted(os.listdir(agents))
    except OSError: names=[]
    if len(names)>32: raise ValueError('AGENT_BOUND')
    targets={}
    for name in names:
        if re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',name) is None: continue
        path=agents+'/'+name+'/sessions/sessions.json'
        try: records=read_json(path)
        except (OSError,ValueError,TypeError,UnicodeError): continue
        if not isinstance(records,dict) or len(records)>10000: raise ValueError('SESSION_BOUND')
        for record in records.values():
            if not isinstance(record,dict): continue
            context=record.get('deliveryContext',{})
            origin=record.get('origin',{})
            if not isinstance(context,dict): context={}
            if not isinstance(origin,dict): origin={}
            channel=context.get('channel') or record.get('lastChannel') or origin.get('provider')
            if channel!='feishu': continue
            target=context.get('to') or record.get('lastTo')
            account=context.get('accountId') or record.get('lastAccountId')
            shape='UNKNOWN'
            if isinstance(target,str):
                if re.fullmatch(r'(?:user:|feishu:)?ou_[A-Za-z0-9_-]+',target): shape='DIRECT_USER'
                elif re.fullmatch(r'(?:chat:|feishu:)?oc_[A-Za-z0-9_-]+',target): shape='CHAT_ID'
            result['session_inventory'].append({'channel':'feishu','target_shape':shape,
                'chat_type':origin.get('chatType') if origin.get('chatType') in ('direct','group') else 'UNKNOWN',
                'account_present':bool(account),'updated_at':record.get('updatedAt') if type(record.get('updatedAt')) in (int,float) else None})
            if shape=='DIRECT_USER' and origin.get('chatType')=='direct':
                targets[(target,account if isinstance(account,str) else None)]=True
    result['distinct_direct_targets']=len(targets)
    result['live_send_performed']=False
    cli=HOME_ROOT+'/bin/openclaw'
    for args in (['message','send','--help'],['channels','--help']):
        proc=subprocess.run([cli]+args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,
          env={'HOME':'/home/xuanjun_dev','PATH':HOME_ROOT+'/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C','NO_COLOR':'1'})
        lines=proc.stdout.decode('utf-8','replace').splitlines()
        # Emit only known option spellings, never raw CLI/config output.
        flags=sorted(set(flag for line in lines for flag in re.findall(r'--[a-z][a-z-]*',line)
          if flag in ('--channel','--target','--account','--message','--json','--dry-run','--help')))
        result['cli_'+'_'.join(args[:-1])]={'exit_code':proc.returncode,'known_flags':flags}
    proc=subprocess.run([cli,'sessions','--help'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,
      env={'HOME':'/home/xuanjun_dev','PATH':HOME_ROOT+'/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C','NO_COLOR':'1'})
    help_text=proc.stdout.decode('utf-8','replace')
    flags=set(re.findall(r'--[a-z][a-z-]*',help_text))
    result['sessions_cli_flags']=sorted(flags & {'--json','--all-agents','--agent','--store'})
    if proc.returncode==0 and '--json' in flags:
        args=[cli,'sessions','--json']
        if '--all-agents' in flags: args.append('--all-agents')
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=30,
          env={'HOME':'/home/xuanjun_dev','PATH':HOME_ROOT+'/tools/node-v24.21.0/bin:/usr/bin:/bin','LANG':'C','NO_COLOR':'1'})
        result['sessions_cli_exit_code']=p.returncode
        try:
            text=p.stdout.decode('utf-8'); start=text.find('{')
            data=json.loads(text[start:])
            sessions=data.get('sessions',[])
            result['sessions_cli_total']=len(sessions) if isinstance(sessions,list) else None
            result['sessions_cli_feishu']=[]
            for a in sessions if isinstance(sessions,list) else []:
                if not isinstance(a,dict):continue
                key=a.get('key','')
                if isinstance(key,str) and ':feishu:' in key:
                    result['sessions_cli_feishu'].append({'kind':a.get('kind') if a.get('kind') in ('direct','group') else 'UNKNOWN',
                      'key_direct_user_shape':bool(re.search(r':feishu:direct:ou_[A-Za-z0-9_-]+$',key)),
                      'updated_at':a.get('updatedAt') if type(a.get('updatedAt')) in (int,float) else None})
        except (ValueError,UnicodeError,TypeError):
            result['sessions_cli_status']='UNPARSEABLE_NOT_EXPORTED'
    import urllib.request, urllib.error
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): raise ValueError('REDIRECT_REFUSED')
    def feishu_api(path,token=None,body=None):
        headers={'Content-Type':'application/json; charset=utf-8'}
        if token:headers['Authorization']='Bearer '+token
        req=urllib.request.Request('https://open.feishu.cn/open-apis/'+path,
            data=json.dumps(body).encode('utf-8') if body is not None else None,headers=headers)
        try:
            response=urllib.request.build_opener(NoRedirect()).open(req,timeout=15)
            raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:raise ValueError('HTTP_BOUND')
            return json.loads(raw.decode('utf-8'))
        except urllib.error.HTTPError as error:return {'code':error.code}
    try:
        config=read_json(HOME_ROOT+'/openclaw.json')['channels']['feishu']
        if not isinstance(config.get('appId'),str) or not isinstance(config.get('appSecret'),str):
            raise ValueError('CREDENTIAL_REFERENCE_REQUIRES_NATIVE_RESOLUTION')
        auth=feishu_api('auth/v3/tenant_access_token/internal',body={'app_id':config['appId'],'app_secret':config['appSecret']})
        result['feishu_auth_code']=auth.get('code') if type(auth.get('code')) is int else None
        token=auth.get('tenant_access_token')
        if auth.get('code')==0 and isinstance(token,str):
            bot=feishu_api('bot/v3/info',token)
            result['bot_identity_code']=bot.get('code') if type(bot.get('code')) is int else None
            result['bot_matches_owner_screenshot']=bot.get('bot',{}).get('app_name')=='玄钧云汇开发总管'
            routes=[]
            for session in sessions if isinstance(sessions,list) else []:
                key=session.get('key','') if isinstance(session,dict) else ''
                match=re.search(r':feishu:(?:group|direct):(oc_[A-Za-z0-9_-]+)$',key)
                if match:routes.append(match.group(1))
            routes=sorted(set(routes))
            result['native_chat_target_count']=len(routes)
            result['api_chat_observations']=[]
            for target in routes[:3]:
                chat=feishu_api('im/v1/chats/'+target,token)
                mode=chat.get('data',{}).get('chat_mode')
                history=feishu_api('im/v1/messages?container_id_type=chat&container_id='+target+'&sort_type=ByCreateTimeDesc&page_size=10',token)
                items=history.get('data',{}).get('items',[])
                kinds=sorted(set(a.get('chat_type') for a in items if isinstance(a,dict) and a.get('chat_type') in ('p2p','group')))
                screenshot_match=False
                for item in items if isinstance(items,list) else []:
                    body=item.get('body',{}) if isinstance(item,dict) else {}
                    content=body.get('content','') if isinstance(body,dict) else ''
                    if isinstance(content,str) and 'P2 脚本监督' in content:screenshot_match=True
                result['api_chat_observations'].append({'chat_info_code':chat.get('code') if type(chat.get('code')) is int else None,
                    'chat_mode':mode if mode in ('p2p','group','topic') else 'UNKNOWN',
                    'history_code':history.get('code') if type(history.get('code')) is int else None,
                    'message_chat_types':kinds,'matches_owner_screenshot_notification':screenshot_match})
            # Read-only integration facts: inspect ONLY the already delivered canary.
            # Never send, print IDs/content/credentials, or use this as production ACK.
            result['existing_canary_readonly']={'state':'NOT_FOUND_NOT_PROOF_OF_ABSENCE'}
            if result.get('bot_matches_owner_screenshot') is True and len(routes)==1 and mode=='p2p':
                import time, urllib.parse
                event='XJ_P2_FEISHU_CANARY_11787198841_20261013'
                expected_text='P2飞书机械核验：已确认本会话为「玄钧云汇开发总管」私聊。当前包11787198841，SHA256前缀3ff24ecc。零模型调用；此消息仅验证通知发送，不代表安装完成。核验标识：'+event
                expected_original=json.dumps({'text':expected_text},ensure_ascii=False)
                expected_compact=json.dumps({'text':expected_text},ensure_ascii=False,separators=(',',':'))
                next_token=None; seen_tokens=set(); found={}; complete=False; started=time.monotonic()
                for unused in range(10):
                    if time.monotonic()-started>60:break
                    params={'container_id_type':'chat','container_id':routes[0],'page_size':50,'sort_type':'ByCreateTimeDesc'}
                    if next_token is not None:params['page_token']=next_token
                    page=feishu_api('im/v1/messages?'+urllib.parse.urlencode(params),token)
                    data=page.get('data')
                    if type(page.get('code')) is not int or page['code']!=0 or not isinstance(data,dict):break
                    batch=data.get('items')
                    if not isinstance(batch,list) or len(batch)>50 or type(data.get('has_more')) is not bool:break
                    for item in batch:
                        if not isinstance(item,dict) or item.get('chat_id')!=routes[0] or item.get('msg_type')!='text':continue
                        sender=item.get('sender');body=item.get('body')
                        if not isinstance(sender,dict) or sender.get('sender_type')!='app' or not isinstance(body,dict):continue
                        try:matched=json.loads(body.get('content',''))=={'text':expected_text}
                        except (ValueError,TypeError):matched=False
                        ident=item.get('message_id')
                        if matched and isinstance(ident,str) and re.fullmatch(r'om_[A-Za-z0-9_-]+',ident):found[ident]=item
                    if not data['has_more']:complete=True;break
                    next_token=data.get('page_token')
                    if not isinstance(next_token,str) or not next_token or next_token in seen_tokens:break
                    seen_tokens.add(next_token)
                observation={'state':'UNKNOWN','complete_scan':complete,'distinct_canary_receipts':len(found)}
                if complete and len(found)==1:
                    ident=next(iter(found));original=found[ident]
                    response=feishu_api('im/v1/messages/'+ident,token)
                    records=response.get('data',{}).get('items',[])
                    if type(response.get('code')) is int and response['code']==0 and isinstance(records,list) and len(records)==1:
                        reread=records[0]
                        if (isinstance(reread,dict) and reread.get('message_id')==ident and reread.get('chat_id')==routes[0] and
                            reread.get('msg_type')=='text' and reread.get('body')==original.get('body') and
                            reread.get('sender')==original.get('sender') and reread.get('deleted') is not True):
                            sender=reread['sender'];actual=reread['body']['content']
                            observation.update({'state':'EXISTING_CANARY_READBACK_VERIFIED_NOT_RUNTIME_ACK',
                              'exact_original_serialization':actual==expected_original,
                              'exact_compact_serialization':actual==expected_compact,
                              'sender_id_type':sender.get('id_type') if sender.get('id_type') in ('open_id','app_id','user_id','union_id') else 'UNKNOWN',
                              'sender_matches_bot_open_id':isinstance(bot.get('bot',{}).get('open_id'),str) and sender.get('id')==bot['bot']['open_id'],
                              'sender_matches_configured_app_id':sender.get('id')==config['appId']})
                result['existing_canary_readonly']=observation
            if (CANARY_SEND_ENABLED and result.get('bot_matches_owner_screenshot') is True and len(routes)==1 and
                len(result['api_chat_observations'])==1 and
                result['api_chat_observations'][0]['chat_mode']=='p2p' and
                result['api_chat_observations'][0]['matches_owner_screenshot_notification'] is True):
                import uuid
                event='XJ_P2_FEISHU_CANARY_11787198841_20261013'
                text='P2飞书机械核验：已确认本会话为「玄钧云汇开发总管」私聊。当前包11787198841，SHA256前缀3ff24ecc。零模型调用；此消息仅验证通知发送，不代表安装完成。核验标识：'+event
                content=json.dumps({'text':text},ensure_ascii=False)
                existing=None
                for a in items:
                    try:
                        if json.loads(a.get('body',{}).get('content','')).get('text')==text:
                            existing=a.get('message_id')
                    except (ValueError,TypeError):pass
                if existing:
                    sent={'code':0,'data':{'message_id':existing}}
                    result['canary_send_state']='EXISTING_MESSAGE_RECONCILED'
                else:
                    sent=feishu_api('im/v1/messages?receive_id_type=chat_id',token,body={
                        'receive_id':routes[0],'msg_type':'text','content':content,
                        'uuid':str(uuid.uuid5(uuid.NAMESPACE_URL,event))})
                    result['live_send_performed']=True
                    result['send_performed']=True
                    result['canary_send_state']='POST_ATTEMPTED_NO_AUTOMATIC_RETRY'
                result['canary_event']=event
                result['canary_api_code']=sent.get('code') if type(sent.get('code')) is int else None
                message_id=sent.get('data',{}).get('message_id')
                result['canary_receipt_present']=isinstance(message_id,str) and bool(message_id)
                if sent.get('code')==0 and isinstance(message_id,str) and re.fullmatch(r'om_[A-Za-z0-9_-]+',message_id):
                    receipt=feishu_api('im/v1/messages/'+message_id,token)
                    read_items=receipt.get('data',{}).get('items',[])
                    matched=False
                    for a in read_items:
                        try:
                            matched=matched or (a.get('message_id')==message_id and
                                a.get('chat_id')==routes[0] and
                                json.loads(a.get('body',{}).get('content','')).get('text')==text)
                        except (ValueError,TypeError):pass
                    result['canary_server_readback_match']=matched
                    result['owner_read_ack']='NOT_VERIFIED'
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        result['authoritative_chat_check']='HOLD_NO_SECRET_OUTPUT'
    return result
if __name__=='__main__':
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:
        raise SystemExit('HOLD_FIXED_UK_IDENTITY')
    print(json.dumps(collect(),sort_keys=True))

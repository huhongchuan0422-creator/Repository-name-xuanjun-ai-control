"""Fixed UK Feishu metadata preflight; no credential output or sends."""
import json, os, pwd, socket, stat, subprocess, re
HOME_ROOT='/home/xuanjun_dev/.openclaw'
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
    return result
if __name__=='__main__':
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:
        raise SystemExit('HOLD_FIXED_UK_IDENTITY')
    print(json.dumps(collect(),sort_keys=True))

"""Fixed UK readiness/source read: zero inference, no execution or mutation."""
import os,pwd,socket,stat,json,hashlib,re
def read(path,maximum=1048576):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:raise ValueError("SHAPE")
        raw=os.read(fd,maximum+1)
        if len(raw)>maximum:raise ValueError("LIMIT")
        return raw,info
    finally:os.close(fd)
def safe(value):
    if value is None or type(value) in (bool,int):return value
    if isinstance(value,str) and len(value)<150 and re.fullmatch(r"[A-Za-z0-9_./:@+-]*",value):return value
    return "REDACTED_UNEXPECTED_VALUE"
def main():
    if socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid:raise SystemExit('HOLD_FIXED_UK_NONROOT')
    output={'state':'READONLY_NATIVE_READINESS','model_calls':0,'authority_mutation':'NONE','sources':[]}
    code='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/context-DyPstb2Q.mjs'
    raw,info=read(code)
    output['sources'].append({'path':code,'sha256':hashlib.sha256(raw).hexdigest(),'uid':info.st_uid,'source':raw.decode('utf-8')})
    config='/home/xuanjun_dev/.openclaw/openclaw.json'
    try:
        raw,info=read(config)
        cfg=json.loads(raw.decode('utf-8'))
        agents=cfg.get('agents',{})
        defaults=agents.get('defaults',{})
        main_agent=next((a for a in agents.get('list',[]) if a.get('id')=='main'),{})
        profiles=cfg.get('auth',{}).get('profiles',{})
        model=defaults.get('model',{})
        entries=agents.get('entries',{})
        roster=[dict(v,id=k) for k,v in list(entries.items())[:32] if isinstance(v,dict)] if isinstance(entries,dict) else []
        roster+= [v for v in agents.get('list',[])[:32] if isinstance(v,dict)]
        output['agent_metadata']=[{'id':safe(v.get('id')),'agentDir':safe(v.get('agentDir')),
          'sandbox':{k:safe(v.get('sandbox',{}).get(k)) for k in ('mode','backend','scope','workspaceAccess')},
          'model_primary':safe(v.get('model',{}).get('primary') if isinstance(v.get('model'),dict) else v.get('model'))} for v in roster]
        providers=cfg.get('models',{}).get('providers',{})
        provider=providers.get('openai',{})
        output['provider_metadata']={'api':safe(provider.get('api')),'auth':safe(provider.get('auth')),'api_key_value_type':type(provider.get('apiKey')).__name__}
        output['policy']={'config_uid':info.st_uid,'config_mode':oct(stat.S_IMODE(info.st_mode)),
          'primary':safe(model.get('primary') if isinstance(model,dict) else model),
          'fallbacks':[safe(v) for v in model.get('fallbacks',[])][:16] if isinstance(model,dict) else None,
          'auth_modes':[{'provider':safe(v.get('provider')),'mode':safe(v.get('mode'))} for v in list(profiles.values())[:32] if isinstance(v,dict)],
          'sandbox_defaults':{k:safe(defaults.get('sandbox',{}).get(k)) for k in ('mode','backend','scope','workspaceAccess')},
          'sandbox_main':{k:safe(main_agent.get('sandbox',{}).get(k)) for k in ('mode','backend','scope','workspaceAccess')},
          'cli_backend_keys':[safe(k) for k in defaults.get('cliBackends',{})][:16]}
    except FileNotFoundError:output['policy']={'state':'CONFIG_PATH_MISSING'}
    output['oauth_metadata']=[]
    auth='/home/xuanjun_dev/.openclaw/agents/main/agent/auth-profiles.json'
    try:
        raw,info=read(auth)
        data=json.loads(raw.decode('utf-8'))
        output['oauth_metadata']=[{'type':safe(v.get('type')),'provider':safe(v.get('provider'))} for v in list(data.get('profiles',{}).values())[:32] if isinstance(v,dict)]
    except FileNotFoundError:output['oauth_metadata']=[{'state':'PROFILE_PATH_MISSING'}]
    extra='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/loader-runtime-load-DpgEqnzx.mjs'
    raw,info=read(extra)
    output['sources'].append({'path':extra,'sha256':hashlib.sha256(raw).hexdigest(),'uid':info.st_uid,'source':raw.decode('utf-8')})
    store_source='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/dist/store-BVWJOVBa.mjs'
    raw,info=read(store_source)
    output['sources'].append({'path':store_source,'sha256':hashlib.sha256(raw).hexdigest(),'uid':info.st_uid,'source':raw.decode('utf-8')})
    output['engines']=[]
    for binary in ('/usr/bin/docker','/usr/bin/podman'):
        try:
            i=os.lstat(binary)
            output['engines'].append({'path':binary,'regular':stat.S_ISREG(i.st_mode),'uid':i.st_uid,'mode':oct(stat.S_IMODE(i.st_mode))})
        except FileNotFoundError:output['engines'].append({'path':binary,'state':'MISSING'})
    print(json.dumps(output,sort_keys=True))
if __name__=='__main__':main()

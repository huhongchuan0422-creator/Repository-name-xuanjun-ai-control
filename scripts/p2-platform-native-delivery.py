"""One bounded native coordination delivery; never attests child STARTED by text."""
import hashlib
import json
import os
import pwd
import re
import selectors
import signal
import socket
import stat
import subprocess
import time
import uuid

HOME_PATH='/home/xuanjun_dev'
CLI=HOME_PATH+'/.openclaw/bin/openclaw'
ENV={'HOME':HOME_PATH,'PATH':HOME_PATH+'/.openclaw/tools/node-v24.21.0/bin:/usr/local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
TASK='XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1'
MODEL='openai/gpt-5.6-sol'
KEY=hashlib.sha256((TASK+'\nP2_PLATFORM_ENGINEER\n6121230482').encode()).hexdigest()


def capture(argv,seconds=20,limit=131072):
    process=subprocess.Popen(argv,env=ENV,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             start_new_session=True)
    reader=selectors.DefaultSelector()
    reader.register(process.stdout,selectors.EVENT_READ);reader.register(process.stderr,selectors.EVENT_READ)
    out=bytearray();err=bytearray();deadline=time.monotonic()+seconds
    try:
        while reader.get_map():
            if time.monotonic()>=deadline:raise ValueError('HOLD_TRANSPORT_TIMEOUT_EFFECT_UNKNOWN')
            for key,unused in reader.select(min(0.2,max(0,deadline-time.monotonic()))):
                chunk=os.read(key.fd,8192)
                if not chunk:reader.unregister(key.fileobj);continue
                (out if key.fileobj is process.stdout else err).extend(chunk)
                if len(out)+len(err)>limit:raise ValueError('HOLD_TRANSPORT_OUTPUT_LIMIT_EFFECT_UNKNOWN')
        code=process.wait(timeout=max(0.01,deadline-time.monotonic()))
        return code,bytes(out)
    finally:
        reader.close()
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)


def unique(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('DUPLICATE_JSON_KEY')
        value[key]=item
    return value


def parse(raw):
    return json.loads(raw.decode('utf-8'),object_pairs_hook=unique)


def main():
    if os.geteuid()!=pwd.getpwnam('xuanjun_dev').pw_uid or os.geteuid()==0 or socket.gethostname().split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ':
        raise SystemExit('STOP_FIXED_NONROOT_UK_DELIVERY')
    receipt={'task_id':TASK,'role_requested':'PLATFORM_ENGINEER','receiver':'EXISTING_OPENCLAW_MAIN',
             'authority_comment':6121230482,'dispatch_key':KEY,'model_calls_requested':0,
             'child_started':'NOT_PROVEN','lease_fence_epoch_mutation':'NONE','install':'NO'}
    try:
        code,raw=capture([CLI,'agent','--help'])
        if code:raise ValueError('HOLD_NATIVE_AGENT_HELP_UNAVAILABLE')
        help_text=raw.decode('utf-8','replace')
        if not all(option in help_text for option in ('--agent','--message','--json')):
            raise ValueError('HOLD_NATIVE_AGENT_CONTRACT_UNSUPPORTED')
        code,raw=capture([CLI,'models','--status-json'],30)
        if code:raise ValueError('HOLD_NATIVE_MODEL_STATUS_UNAVAILABLE')
        status=parse(raw)
        default=status.get('resolvedDefault') or status.get('defaultModel')
        auth=status.get('auth')
        modes=[]
        def walk(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in ('type','mode','authMode') and item in ('oauth','api_key','apiKey','token'):
                        modes.append(item)
                    elif isinstance(item,(list,dict)) and key not in ('tokens','credentials','secrets'):walk(item)
            elif isinstance(value,list):
                for item in value[:100]:walk(item)
        walk(auth)
        if not modes or any(mode!='oauth' for mode in modes):raise ValueError('HOLD_OAUTH_ROUTE_UNCONFIRMED')
        has_model='--model' in help_text
        if status.get('fallbacks')!=[]:
            raise ValueError('HOLD_NATIVE_FALLBACK_POLICY_NOT_BINDABLE')
        if not has_model and (default!=MODEL or status.get('fallbacks')!=[]):
            raise ValueError('HOLD_NATIVE_MODEL_POLICY_NOT_BINDABLE')
        receipt['verified_default_model']=default if default in (MODEL,'openai/gpt-6.1-sol') else 'UNKNOWN'
        if '--session-key' in help_text:
            session_args=['--session-key','agent:main:p2-platform-'+KEY]
        elif '--session-id' in help_text:
            session_args=['--session-id',str(uuid.uuid5(uuid.NAMESPACE_URL,KEY))]
        else:raise ValueError('HOLD_NATIVE_SESSION_BINDING_UNAVAILABLE')
        # A transport receipt journal, not an execution queue/lease or task DB.
        directory=HOME_PATH+'/p2-platform-delivery-receipts'
        if not os.path.lexists(directory):os.mkdir(directory,0o700)
        info=os.lstat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
            raise ValueError('HOLD_UNSAFE_DELIVERY_JOURNAL')
        path=directory+'/'+KEY+'.json'
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:raise ValueError('HOLD_EXISTING_DELIVERY_RECONCILE_NO_REPLAY')
        with os.fdopen(fd,'w') as stream:
            json.dump(dict(receipt,state='REQUESTED_EFFECT_UNKNOWN_NO_AUTORETRY'),stream,sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        parent_fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        os.fsync(parent_fd);os.close(parent_fd)
        message='''Owner explicitly authorized P2 PLATFORM_ENGINEER stage via PR17 comment6121230482. Same task XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1, original spec/checkpoint/budget, candidate502ec666/artifact11734982903. Do not create a second queue, reset budget or start a competing writer.
As the existing main coordinator, first reconcile actual original P2 writer/session/descendants/lease/fence/epoch and unknown effects. Use your supported native child-session mechanism to dispatch PLATFORM_ENGINEER for bounded READONLY platform preparation: actual native OAuth/gh consumer identity, exact verify-only/install/rollback plan and real adapter capability diagnosis. Do not install, switch old Coordinator, modify production/config/DB/Webhook/trading/customer channels, copy tokens/auth.json, change account/models or invoke paid API. Keep openai/gpt-5.6-sol with fallbacks=[] and existing OAuth. If original execution authority or native child entry is not available, return exact HOLD; do not claim STARTED from a comment or audit job.
Only if PLATFORM_ENGINEER actually diagnoses a native adapter gap and finishes/stops with reconciled authority, serially dispatch Developer on the same task to implement it; do not start both as writers. Return one bounded JSON object: role_requested, state, native_tool, run_id, session_key, process_or_unit, checkpoint, lease, fence, epoch, blocker. STARTED requires a real native child plus independent session/process evidence. Do the authorized stage now, not a status-only acknowledgement.'''
        argv=[CLI,'agent','--agent','main']+session_args
        if has_model:argv+=['--model',MODEL]
        argv+=['--message',message,'--thinking','low','--timeout','90','--json']
        receipt['model_calls_requested']=1
        receipt['transport_started_at']=time.time()
        print(json.dumps(dict(receipt,state='MAIN_COORDINATOR_REQUEST_STARTED_NOT_PLATFORM_STARTED'),sort_keys=True),flush=True)
        code,raw=capture(argv,105)
        if code:raise ValueError('HOLD_NATIVE_TRANSPORT_FAILED_EFFECT_UNKNOWN')
        data=parse(raw)
        meta=data.get('result',{}).get('meta',{}).get('agentMeta',{})
        if data.get('status')!='ok' or meta.get('provider')!='openai' or meta.get('model') not in (MODEL,'gpt-5.6-sol'):
            raise ValueError('HOLD_NATIVE_RETURN_ROUTE_NOT_VERIFIED')
        receipt['native_model']='openai/gpt-5.6-sol'
        receipt['native_provider']='openai'
        for key in ('sessionId','runId'):
            value=meta.get(key)
            if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}',value):receipt['main_'+key]=value
        receipt['state']='MAIN_COORDINATOR_DELIVERY_COMPLETED_CHILD_START_NEEDS_INDEPENDENT_PROBE'
        # A model's claimed role receipt cannot attest native child STARTED.
        payloads=data.get('result',{}).get('payloads',[])
        if len(payloads)==1 and isinstance(payloads[0],dict):
            try:
                reported=parse(payloads[0].get('text','').encode('utf-8'))
                if isinstance(reported,dict):
                    for key in ('state','native_tool','run_id','session_key','process_or_unit'):
                        value=reported.get(key)
                        if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:/ -]{1,180}',value):
                            receipt['reported_'+key]=value
            except (ValueError,TypeError):pass
    except Exception as error:
        receipt['state']=str(error) if isinstance(error,ValueError) and re.fullmatch(r'HOLD_[A-Z_]+',str(error)) else 'HOLD_DELIVERY_ERROR_NO_RAW_OUTPUT'
    if receipt['model_calls_requested'] and 'path' in locals():
        terminal=path+'.terminal'
        fd=os.open(terminal,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(receipt,stream,sort_keys=True);stream.flush();os.fsync(stream.fileno())
        parent_fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        os.fsync(parent_fd);os.close(parent_fd)
    print(json.dumps(receipt,sort_keys=True))


if __name__=='__main__':main()

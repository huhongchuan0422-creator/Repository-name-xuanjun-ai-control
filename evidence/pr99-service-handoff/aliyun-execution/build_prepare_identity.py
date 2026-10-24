"""Build the fixed Owner-authorized account prerequisite in the original channel."""
import ast
from pathlib import Path

base=Path(__file__).parent
old=(base/'config_flow_probe.py').read_text()
host=(base/'prepare_identity_host.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('IDENTITY_PREPARATION_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    fields(d,'scope hostname nonce observed_at identity protected_before protected_after protected_state_unchanged target_units releases service_actions database_opened route_changed migration_started production_started')
    need(d['scope']=='PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    a=d['identity'];fields(a,'created creation_attempted name uid gid login_shell_disabled home_created shared_primary_identity')
    need(a['name']=='xuanjun-s07' and type(a['created']) is type(a['creation_attempted']) is bool and a['created']==a['creation_attempted'])
    for k in ('uid','gid'):need(type(a[k])is int and 0<a[k]<65534 and a[k]not in (1000,1001))
    need(a['login_shell_disabled']is True and a['home_created']is False and a['shared_primary_identity']is False)
    protected={'provider-neutral-domestic-bridge.service','windows-interaction-http.service','nginx.service'}
    targets={'xuanjun-pr99-domestic-'+r+'.service' for r in ('portal','contact','customer-service')}
    for key,names in (('protected_before',protected),('protected_after',protected),('target_units',targets)):
        need(type(d[key])is dict and set(d[key])==names)
        for row in d[key].values():
            fields(row,'LoadState ActiveState SubState MainPID')
            need(all(type(row[k])is str and re.fullmatch('[A-Za-z0-9_-]{1,80}',row[k]) for k in ('LoadState','ActiveState','SubState')))
            need(type(row['MainPID'])is int and 0<=row['MainPID']<2**31)
    need(type(d['protected_state_unchanged'])is bool and d['protected_state_unchanged']==(d['protected_before']==d['protected_after']))
    paths=['/opt/xuanjun-migration-s07/releases/domestic-r2','/opt/xuanjun-migration-s07/releases/domestic-r2/rootfs','/opt/xuanjun-migration-s07/releases/domestic-final-v1','/opt/xuanjun-migration-s07/releases/domestic-final-v1/rootfs']
    need(type(d['releases'])is list and len(d['releases'])==4)
    for row,path in zip(d['releases'],paths):
        need(type(row)is dict and row.get('path')==path and type(row.get('exists'))is bool)
        fields(row,'path exists directory uid gid mode device inode' if row['exists'] else 'path exists')
        if row['exists']:
            need(type(row['directory'])is bool)
            need(all(type(row[k])is int and 0<=row[k]<2**64 for k in ('uid','gid','mode','device','inode')))
    need(type(d['service_actions'])is int and d['service_actions']==0)
    for k in ('database_opened','route_changed','migration_started','production_started'):need(d[k]is False)
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=16000:raise ValueError()
        try:d=json.loads(output)
        except ValueError:d=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(d,expected,nonce)
    except Exception:raise Hold('IDENTITY_PREPARATION_OUTPUT_REJECTED') from None
'''
test='''def self_test():
    from types import SimpleNamespace as NS
    n={'__name__':'identity_fixture'};exec(compile(HOST_PROGRAM,'fixed_identity_program','exec'),n)
    state={};calls=[]
    u=NS(pw_name='xuanjun-s07',pw_uid=987,pw_gid=986,pw_shell='/usr/sbin/nologin',pw_dir='/nonexistent')
    g=NS(gr_name='xuanjun-s07',gr_gid=986,gr_mem=[])
    def getuser(name):
        if not state.get('user'):raise KeyError()
        return u
    def getgroup(name):
        if not state.get('group'):raise KeyError()
        return g
    def run(args,**kwargs):calls.append(args);state.update(user=True,group=True);return NS(returncode=0)
    def call(r=run):return n['prepare_identity'](getuser,getgroup,lambda:[u] if state.get('user') else [],lambda:[g] if state.get('group') else [],r)
    a=call();assert a['created']is True and calls==[n['COMMAND']]
    assert call()['created']is False and len(calls)==1
    for key in ('user','group'):
        state.clear();state[key]=True
        try:call()
        except RuntimeError:pass
        else:raise AssertionError('PARTIAL_ACCOUNT_ADOPTED')
    state.update(user=True,group=True);u.pw_uid=0
    try:call()
    except RuntimeError:pass
    else:raise AssertionError('ROOT_IDENTITY_ADOPTED')
    u.pw_uid=987;u.pw_shell='/bin/bash'
    try:call()
    except RuntimeError:pass
    else:raise AssertionError('LOGIN_ACCOUNT_ADOPTED')
    u.pw_shell='/usr/sbin/nologin';state.clear()
    def fail(args,**kwargs):calls.append(args);return NS(returncode=1)
    try:call(fail)
    except RuntimeError:pass
    else:raise AssertionError('NATIVE_FAILURE_ACCEPTED')
    assert len(calls)==2
    unit={'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','MainPID':0}
    protected={k:unit for k in n['PROTECTED']};targets={k:unit for k in n['TARGETS']}
    d={'scope':'PR99_OWNER_DOMESTIC_IDENTITY_PREPARATION_ONLY','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T00:00:00Z',
      'identity':a,'protected_before':protected,'protected_after':protected,'protected_state_unchanged':True,
      'target_units':targets,'releases':[{'path':p,'exists':False} for p in n['RELEASES']],
      'service_actions':0,'database_opened':False,'route_changed':False,'migration_started':False,'production_started':False}
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(json.dumps(d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    for change in (lambda x:x.update(production_started=True),lambda x:x.update(private='TOKEN'),lambda x:x['identity'].update(uid=0),lambda x:x.update(service_actions=1)):
        bad=json.loads(json.dumps(d));change(bad)
        try:decode_receipt(json.dumps(bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('OVERSCOPE_OR_PRIVATE_OUTPUT_ACCEPTED')
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    assert n['COMMAND']==['/usr/sbin/useradd','--system','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin','--user-group','xuanjun-s07']
    print('PR99_OWNER_IDENTITY_NATIVE_ONCE_CONFLICT_PRIVACY_NO_ACTIVATION_TESTS_PASS_NO_CLOUD',flush=True)
'''
replacements=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
        if node.targets[0].id=='HOST_PROGRAM':replacements.append((node.lineno,node.end_lineno,'HOST_PROGRAM='+repr(host)))
        if node.targets[0].id=='HOSTS':replacements.append((node.lineno,node.end_lineno,"HOSTS=(('domestic',CN,'cn-shanghai','3a22c458934142eea89ec6e3bf481a57','iZvt5t8tlrm8oiZ'),)"))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','decode_receipt','self_test'):
        replacements.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else '' if node.name=='decode_receipt' else test))
lines=old.splitlines()
for begin,end,text in reversed(replacements):lines[begin-1:end]=text.splitlines()
program='\n'.join(lines)+'\n'
program=program.replace('pr99-config-flow-','pr99-prepare-identity-').replace('PR99_CONFIG_FLOW_','PR99_IDENTITY_PREP_')
program=program.replace('CONFIG_FLOW_OBSERVED_NOT_EFFECTIVE_ATTESTATION','DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED').replace('CONFIG_FLOW_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','OWNER_IDENTITY_PREPARATION_BATCH_NOT_PRODUCTION_START')
program=program.replace('READONLY_DISPATCH_INTENT','DEDICATED_ACCOUNT_PREPARATION_INTENT').replace('READONLY_COMMAND_FAILED_NO_RETRY','IDENTITY_PREPARATION_FAILED_NO_RETRY').replace('READONLY_RESULT_UNKNOWN_NO_RETRY','IDENTITY_PREPARATION_RESULT_UNKNOWN_NO_RETRY')
program=program.replace("'production_actions':0", "'production_service_actions':0")
program=program.replace("row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)","row['receipt']=decode_receipt(detail.get('Output'),expected,nonce)\n            if row['receipt']['protected_state_unchanged'] is not True:raise Hold('PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')")
program=program.replace("'''Two-host PR99 writer-descriptor observation. No command input or automatic dispatch retry.'''", "'''Owner-authorized fixed dedicated account preparation, no automatic retry.'''" )
(base/'prepare_identity_probe.py').write_text(program)
workflow=(base/'pr99-config-flow.yml').read_text()
embedded='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
replacement='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(embedded)==2
workflow=workflow.replace(embedded,replacement).replace('pr99-config-flow-','pr99-prepare-identity-')
workflow=workflow.replace('PR99 redacted startup configuration flow','PR99 Owner domestic identity preparation').replace('Read fixed redacted startup source flow once','Prepare fixed domestic dedicated identity once')
workflow=workflow.replace('recover-readonly:', 'prepare-identity:').replace('Validate exact read-only program without cloud credentials','Validate fixed preparation program without cloud credentials')
(base/'pr99-prepare-identity.yml').write_text(workflow)
compile(program,'prepare_identity_probe.py','exec')
print('OWNER_IDENTITY_PREPARATION_BUILD_COMPLETE')

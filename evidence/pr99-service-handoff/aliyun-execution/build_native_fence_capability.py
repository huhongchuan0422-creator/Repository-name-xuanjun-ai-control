import ast
from pathlib import Path
base=Path(__file__).parent
old=(base/'prepare_identity_probe.py').read_text()
host=(base/'native_fence_capability_host.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('NATIVE_FENCE_CAPABILITY_CONTRACT')
    need(type(d)is dict and set(d)==set('scope hostname nonce observed_at result fixture_cleaned source_data_selected source_writer_stopped production_fence_enforced database_opened service_actions writer_acquired route_changed'.split()))
    need(d['scope']=='PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    x=d['result'];need(type(x)is dict and set(x)==set('held_writable_fd_write_blocked file_unlink_blocked directory_create_blocked original_flags_restored write_after_restore_pass same_filesystem_as_project_root fixture_bytes filesystem_device'.split()))
    for key in set(x)-{'fixture_bytes','filesystem_device'}:need(x[key]is True)
    need(type(x['filesystem_device'])is int and 0<x['filesystem_device']<2**64 and x['fixture_bytes']==46)
    need(d['fixture_cleaned']is True and type(d['service_actions'])is int and d['service_actions']==0)
    for key in ('source_data_selected','source_writer_stopped','production_fence_enforced','database_opened','writer_acquired','route_changed'):need(d[key]is False)
    return d
'''
test='''def self_test():
    n={'__name__':'capability_definitions'};exec(compile(HOST_PROGRAM,'capability','exec'),n)
    assert len(n['PAYLOAD'])==46
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    d={'scope':'PR99_NATIVE_FENCE_CAPABILITY_ONLY_NOT_SOURCE_FENCED','hostname':HOSTS[0][4],'nonce':'a'*32,
       'observed_at':'2026-10-19T00:00:00Z','result':{k:True for k in ('held_writable_fd_write_blocked','file_unlink_blocked','directory_create_blocked','original_flags_restored','write_after_restore_pass','same_filesystem_as_project_root')},
       'fixture_cleaned':True,'source_data_selected':False,'source_writer_stopped':False,'production_fence_enforced':False,
       'database_opened':False,'service_actions':0,'writer_acquired':False,'route_changed':False}
    d['result'].update(fixture_bytes=46,filesystem_device=64771)
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    for key in ('source_writer_stopped','production_fence_enforced','writer_acquired'):
        x=json.loads(json.dumps(d));x[key]=True
        try:decode_receipt(json.dumps(x),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('FALSE_PRODUCTION_EVIDENCE_ACCEPTED')
    for key in ('held_writable_fd_write_blocked','original_flags_restored'):
        x=json.loads(json.dumps(d));x['result'][key]=False
        try:decode_receipt(json.dumps(x),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('FAILED_CAPABILITY_ACCEPTED')
    print('PR99_NATIVE_FENCE_CAPABILITY_SCOPE_AND_SCHEMA_PASS_NO_CLOUD',flush=True)
'''
changes=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
        if node.targets[0].id=='HOST_PROGRAM':changes.append((node.lineno,node.end_lineno,'HOST_PROGRAM='+repr(host)))
        if node.targets[0].id=='HOSTS':changes.append((node.lineno,node.end_lineno,"HOSTS=(('tokyo',CN,'ap-northeast-1','68985c531add4e90a131aef703a389e6','iZ6wee8q9z4t03hvqumwfhZ'),)"))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','self_test'):
        changes.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else test))
lines=old.splitlines()
for begin,end,value in reversed(changes):lines[begin-1:end]=value.splitlines()
program='\n'.join(lines)+'\n'
for a,b in (('pr99-prepare-identity-','pr99-native-fence-capability-'),('PR99_IDENTITY_PREP_','PR99_NATIVE_FENCE_'),
 ('DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED','KERNEL_CAPABILITY_VERIFIED_NOT_PRODUCTION_FENCE'),
 ('OWNER_IDENTITY_PREPARATION_BATCH_NOT_PRODUCTION_START','NATIVE_FENCE_CAPABILITY_NOT_PRODUCTION_FENCE'),
 ('DEDICATED_ACCOUNT_PREPARATION_INTENT','NATIVE_FENCE_CAPABILITY_INTENT'),
 ('IDENTITY_PREPARATION_FAILED_NO_RETRY','NATIVE_FENCE_CAPABILITY_FAILED_NO_RETRY')):program=program.replace(a,b)
# Expose safe native error projection immediately; never print arbitrary raw output.
program=program.replace("raise Hold('NATIVE_FENCE_CAPABILITY_FAILED_NO_RETRY')",'''output=detail.get('Output','')
                try:
                    try:failure=json.loads(output)
                    except ValueError:failure=json.loads(base64.b64decode(output,validate=True))
                    if type(failure)is dict and set(failure)=={'status','exception','code','errno','retry_allowed'}:
                        row['host_error_type']=safe(failure['exception']);row['host_error_code']=safe(failure['code'])
                        if type(failure['errno'])is int:row['host_errno']=failure['errno']
                except Exception:pass
                row['exit_code']=detail.get('ExitCode')
                raise Hold('NATIVE_FENCE_CAPABILITY_FAILED_NO_RETRY')''')
program=program.replace("if row['receipt']['protected_state_unchanged'] is not True:raise Hold('PROTECTED_STATE_CHANGED_NO_FURTHER_ACTION')","if row['receipt']['fixture_cleaned'] is not True:raise Hold('FIXTURE_NOT_CLEANED')")
(base/'native_fence_capability_probe.py').write_text(program)
workflow=(base/'pr99-prepare-identity.yml').read_text()
a='\n'.join('          '+l for l in old.rstrip('\n').split('\n'))
b='\n'.join('          '+l for l in program.rstrip('\n').split('\n'))
assert workflow.count(a)==2
workflow=workflow.replace(a,b).replace('pr99-prepare-identity-','pr99-native-fence-capability-')
workflow=workflow.replace('PR99 Owner domestic identity preparation','PR99 native Fence and recovery capability').replace('prepare-identity:', 'native-fence-capability:')
workflow=workflow.replace('Prepare fixed domestic dedicated identity once','Verify kernel capability on private fixtures once')
(base/'pr99-native-fence-capability.yml').write_text(workflow)
compile(program,'native_fence_capability_probe','exec')
print('NATIVE_FENCE_CAPABILITY_BUILD_COMPLETE')

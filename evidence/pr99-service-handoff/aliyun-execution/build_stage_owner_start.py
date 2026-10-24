"""Use the original fixed transport to stage inert, already validated code."""
import ast
from pathlib import Path

base=Path(__file__).parent
old=(base/'prepare_identity_probe.py').read_text()
source=(base.parent/'pr99-dev/owner-start/owner_production_start.py').read_text()
host=(base/'stage_owner_start_host.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('OWNER_START_STAGE_CONTRACT')
    need(type(d)is dict and set(d)==set('scope hostname nonce observed_at path source_sha256 bytes mode created directory_created compiled protected_state_unchanged service_actions start_called writer_acquired production_data_copied production_started route_changed production_state_exists'.split()))
    need(d['scope']=='PR99_STAGE_OWNER_START_PROGRAM_ONLY' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    need(d['path']=='/opt/xuanjun-migration-s07/bin/owner_production_start.py' and d['source_sha256']=='7936650e5911f71216c1dfe1873754bcf09ddac45894df3214018dd5f21ace40')
    need(type(d['bytes'])is int and d['bytes']==34425 and type(d['mode'])is int and d['mode']==256)
    for k in ('created','directory_created','production_state_exists'):need(type(d[k])is bool)
    for k in ('compiled','protected_state_unchanged'):need(d[k]is True)
    for k in ('start_called','writer_acquired','production_data_copied','production_started','route_changed'):need(d[k]is False)
    need(type(d['service_actions'])is int and d['service_actions']==0)
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=16000:raise ValueError()
        try:d=json.loads(output)
        except ValueError:d=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(d,expected,nonce)
    except Exception:raise Hold('OWNER_START_STAGE_OUTPUT_REJECTED') from None
'''
test='''def self_test():
    import tempfile
    n={'__name__':'stage_fixture'};exec(compile(HOST_PROGRAM,'stage_fixture','exec'),n)
    raw=TEST_START_SOURCE.encode()
    assert len(raw)==34425 and hashlib.sha256(raw).hexdigest()==n['SOURCE_SHA']
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)
        assert n['stage_file'](p,raw)is True
        assert n['stage_file'](p,raw)is False
        target=p/'owner_production_start.py';target.chmod(0o600);target.write_bytes(b'partial')
        try:n['stage_file'](p,raw)
        except RuntimeError:pass
        else:raise AssertionError('PARTIAL_CODE_OVERWRITTEN')
        assert target.read_bytes()==b'partial'
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<16000
    d={'scope':'PR99_STAGE_OWNER_START_PROGRAM_ONLY','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T01:00:00Z',
      'path':'/opt/xuanjun-migration-s07/bin/owner_production_start.py','source_sha256':n['SOURCE_SHA'],'bytes':34425,'mode':256,
      'created':True,'directory_created':True,'compiled':True,'protected_state_unchanged':True,'service_actions':0,
      'start_called':False,'writer_acquired':False,'production_data_copied':False,'production_started':False,'route_changed':False,'production_state_exists':False}
    assert decode_receipt(json.dumps(d),HOSTS[0][4],'a'*32)==d
    for change in (lambda x:x.update(start_called=True),lambda x:x.update(private='TOKEN'),lambda x:x.update(mode=511)):
        bad=json.loads(json.dumps(d));change(bad)
        try:decode_receipt(json.dumps(bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('UNSAFE_RECEIPT_ACCEPTED')
    print('PR99_OWNER_START_STAGE_EXACT_BYTES_CONFLICT_NO_ACTIVATION_PASS_NO_CLOUD',flush=True)
'''
changes=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='HOST_PROGRAM':changes.append((node.lineno,node.end_lineno,'TEST_START_SOURCE='+repr(source)+'\nHOST_PROGRAM='+repr(host)))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','decode_receipt','self_test'):
        changes.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else '' if node.name=='decode_receipt' else test))
lines=old.splitlines()
for begin,end,value in reversed(changes):lines[begin-1:end]=value.splitlines()
program='\n'.join(lines)+'\n'
for a,b in (
 ('pr99-prepare-identity-','pr99-stage-owner-start-'),('PR99_IDENTITY_PREP_','PR99_OWNER_STAGE_'),
 ('DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED','OWNER_START_HELPER_STAGED_NOT_STARTED'),
 ('OWNER_IDENTITY_PREPARATION_BATCH_NOT_PRODUCTION_START','OWNER_START_CODE_STAGE_BATCH_NOT_PRODUCTION'),
 ('DEDICATED_ACCOUNT_PREPARATION_INTENT','OWNER_START_CODE_STAGE_INTENT'),
 ('IDENTITY_PREPARATION_FAILED_NO_RETRY','CODE_STAGE_FAILED_NO_RETRY'),('IDENTITY_PREPARATION_RESULT_UNKNOWN_NO_RETRY','CODE_STAGE_RESULT_UNKNOWN_NO_RETRY'),
 ('Two-host PR99 writer-descriptor observation. No command input or automatic dispatch retry.','Fixed Owner start code staging, no activation or automatic retry.'),
 ('Only this exact new read-only scope is authorized.','Only this exact inert code staging is authorized.'),
 ('<pr99-readonly-recovery>','<pr99-owner-start-code-stage>')):program=program.replace(a,b)
(base/'stage_owner_start_probe.py').write_text(program)
workflow=(base/'pr99-prepare-identity.yml').read_text()
before='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
after='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(before)==2
workflow=workflow.replace(before,after).replace('pr99-prepare-identity-','pr99-stage-owner-start-')
workflow=workflow.replace('PR99 Owner domestic identity preparation','PR99 Owner start helper code staging').replace('Prepare fixed domestic dedicated identity once','Install fixed inert Owner start helper once')
workflow=workflow.replace('prepare-identity:', 'stage-owner-start:').replace('New fixed read-only recovery scope.','Fixed inert Owner start helper staging scope.')
(base/'pr99-stage-owner-start.yml').write_text(workflow)
compile(program,'stage_owner_start_probe.py','exec')
print('OWNER_START_CODE_STAGE_BUILD_COMPLETE')

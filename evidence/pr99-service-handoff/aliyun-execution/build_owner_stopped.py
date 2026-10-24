"""Build Owner-direct original stopped installation with fixed cloud transport."""
import ast
from pathlib import Path

base=Path(__file__).parent
old=(base/'prepare_identity_probe.py').read_text()
frozen=(base.parent/'pr99-dev/published-controller/stopped_transaction.py').read_text()
host='FROZEN_SOURCE='+repr(frozen)+'\n'+(base/'owner_stopped_entry.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    def need(ok):
        if not ok:raise ValueError('STOPPED_INSTALL_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    fields(d,'scope hostname nonce observed_at installation acceptance_permission protected_state_unchanged production_started migration_complete')
    need(d['scope']=='PR99_OWNER_ORIGINAL_STOPPED_INSTALL_ONLY' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for k in ('protected_state_unchanged','production_started','migration_complete'):need(d[k]is (k=='protected_state_unchanged'))
    c=d['acceptance_permission'];fields(c,'earlier_terminal_invoke_id earlier_error previous_mode final_mode permission_tightened bytes_unchanged original_install_state_absent_before_correction')
    need(c['earlier_terminal_invoke_id']=='t-sh070fgsorn44cg' and c['earlier_error']=='PRIVATE_INPUT_MODE')
    need(type(c['previous_mode'])is int and c['previous_mode']in (384,420) and c['final_mode']==384)
    need(c['permission_tightened']is (c['previous_mode']!=384) and c['bytes_unchanged']is True and c['original_install_state_absent_before_correction']is True)
    a=d['installation'];fields(a,'status installed_units created_this_invocation original_state_reused starts enables data_restored route_changed unit_sha256')
    need(a['status']=='QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION' and type(a['created_this_invocation'])is bool and a['original_state_reused']is True)
    need(type(a['installed_units'])is int and a['installed_units']==3)
    for k in ('starts','enables'):need(type(a[k])is int and a[k]==0)
    for k in ('data_restored','route_changed'):need(a[k]is False)
    n={'__name__':'contract_only'};exec(compile(HOST_PROGRAM,'fixed_stopped_program','exec'),n)
    need(a['unit_sha256']==n['frozen_library']()['manifest']()['unit_hashes'])
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=16000:raise ValueError()
        try:d=json.loads(output)
        except ValueError:d=json.loads(base64.b64decode(output,validate=True))
        return validate_observation(d,expected,nonce)
    except Exception:raise Hold('STOPPED_INSTALL_OUTPUT_REJECTED') from None
'''
test='''def self_test():
    import tempfile
    from types import SimpleNamespace as NS
    from unittest.mock import patch
    n={'__name__':'stopped_fixture'};exec(compile(HOST_PROGRAM,'fixed_stopped_program','exec'),n)
    lib=n['frozen_library']();manifest=lib['manifest']()
    assert manifest['activation_supported']is False and manifest['production_cutover']is False
    assert lib['STATE']=='/var/lib/xuanjun-pr99-s09-stopped-install-v1'
    assert 'windows-interaction-http.service' in lib['PROTECTED']
    calls=[]
    def show(args,**kwargs):
        calls.append(args)
        return NS(returncode=1,stdout=b'LoadState=not-found\\nActiveState=inactive\\nSubState=dead\\nMainPID=0\\nFragmentPath=\\n')
    with patch.object(n['subprocess'],'run',show):
        assert 'LoadState=not-found' in n['fixed_systemctl']('show','winctl.service','--property=LoadState,ActiveState,SubState,MainPID,FragmentPath','--no-pager')
        for op in ('start','enable','stop','restart'):
            try:n['fixed_systemctl'](op,'nginx.service')
            except RuntimeError:pass
            else:raise AssertionError('UNAUTHORIZED_SERVICE_OPERATION')
    assert len(calls)==1
    # Execute the original installer against actual temporary files. Native
    # service control is replaced with a recording stub, never called in CI.
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);units=root/'units';state=root/'state';release=root/'release'
        for p in (units,state,release):p.mkdir()
        acceptance=release/'callback-restart-acceptance-v1';acceptance.mkdir()
        (acceptance/'receipt.json').write_text(json.dumps({'status':'R2_CALLBACK_REJECTION_RESTART_CLEANUP_PASS_NOT_PRODUCTION','application_processes_stopped':True}))
        lib['RELEASE']=str(release)
        snap={u:'LoadState=not-found\\n' for u in lib['ORIGINAL']}
        lib['snapshot']=lambda:dict(snap);lib['stopped']=lambda name:True
        lib['read_regular']=lambda path,**kw:Path(path).read_bytes()
        operations=[];lib['systemctl']=lambda *a:operations.append(a) or ''
        lib['install'](units,state,{'nonce':'a'*32},'b'*64)
        assert operations==[('daemon-reload',)]
        saved=json.loads((state/'receipt.json').read_text())
        assert saved['starts']==saved['enables']==0
        assert saved['status']=='QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION'
        assert all((units/name).read_bytes()==data for name,data in lib['unit_bytes']().items())
        preserved={p.name:p.read_bytes() for p in units.iterdir()}
        try:lib['install'](units,state,{'nonce':'c'*32},'d'*64)
        except RuntimeError as e:assert str(e)=='TARGET_UNIT_PRESENT'
        else:raise AssertionError('CONFLICT_REPLAY_ACCEPTED')
        assert preserved=={p.name:p.read_bytes() for p in units.iterdir()} and len(operations)==1
        # Missing prior acceptance refuses before writing target units.
        (acceptance/'receipt.json').write_text('{}')
        for p in units.iterdir():p.unlink()
        try:lib['install'](units,state,{'nonce':'e'*32},'f'*64)
        except (RuntimeError,KeyError):pass
        else:raise AssertionError('MISSING_ACCEPTANCE_ACCEPTED')
        assert not list(units.iterdir()) and len(operations)==1
    receipt={'scope':'PR99_OWNER_ORIGINAL_STOPPED_INSTALL_ONLY','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T00:00:00Z',
      'installation':{'status':'QUARANTINE_UNITS_INSTALLED_STOPPED_NOT_PRODUCTION','installed_units':3,'created_this_invocation':True,'original_state_reused':True,'starts':0,'enables':0,'data_restored':False,'route_changed':False,'unit_sha256':manifest['unit_hashes']},
      'acceptance_permission':{'earlier_terminal_invoke_id':'t-sh070fgsorn44cg','earlier_error':'PRIVATE_INPUT_MODE','previous_mode':420,'final_mode':384,'permission_tightened':True,'bytes_unchanged':True,'original_install_state_absent_before_correction':True},
      'protected_state_unchanged':True,'production_started':False,'migration_complete':False}
    assert decode_receipt(json.dumps(receipt),HOSTS[0][4],'a'*32)==receipt
    assert decode_receipt(base64.b64encode(json.dumps(receipt).encode()).decode(),HOSTS[0][4],'a'*32)==receipt
    for change in (lambda x:x.update(production_started=True),lambda x:x.update(private='TOKEN'),lambda x:x['installation'].update(starts=1),lambda x:x['installation']['unit_sha256'].update({'extra':'a'*64})):
        bad=json.loads(json.dumps(receipt));change(bad)
        try:decode_receipt(json.dumps(bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('OVERSCOPE_OR_DRIFT_ACCEPTED')
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<16000
    print('PR99_OWNER_STOPPED_EXACT_BYTES_CONFLICT_ACCEPTANCE_NO_ACTIVATION_PASS_NO_CLOUD',flush=True)
'''
replacements=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='HOST_PROGRAM':
        replacements.append((node.lineno,node.end_lineno,'HOST_PROGRAM='+repr(host)))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','decode_receipt','self_test'):
        replacements.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else '' if node.name=='decode_receipt' else test))
lines=old.splitlines()
for begin,end,value in reversed(replacements):lines[begin-1:end]=value.splitlines()
program='\n'.join(lines)+'\n'
for a,b in (
 ('pr99-prepare-identity-','pr99-owner-stopped-'),('PR99_IDENTITY_PREP_','PR99_OWNER_STOPPED_'),
 ('DOMESTIC_IDENTITY_PREPARED_NOT_PRODUCTION_STARTED','OWNER_STOPPED_INSTALL_COMPLETE_NOT_PRODUCTION'),
 ('OWNER_IDENTITY_PREPARATION_BATCH_NOT_PRODUCTION_START','OWNER_STOPPED_INSTALL_BATCH_NOT_PRODUCTION'),
 ('DEDICATED_ACCOUNT_PREPARATION_INTENT','ORIGINAL_STOPPED_INSTALL_INTENT'),
 ('IDENTITY_PREPARATION_FAILED_NO_RETRY','STOPPED_INSTALL_FAILED_NO_RETRY'),
 ('IDENTITY_PREPARATION_RESULT_UNKNOWN_NO_RETRY','STOPPED_INSTALL_RESULT_UNKNOWN_NO_RETRY'),
 ('EXACT_WRITER_OBSERVATION_LABEL_REQUIRED','EXACT_OWNER_STOPPED_LABEL_REQUIRED'),
 ('Two-host PR99 writer-descriptor observation. No command input or automatic dispatch retry.','Owner-direct original stopped installer, fixed domestic target, no activation or automatic retry.'),
 ('Only this exact new read-only scope is authorized.','Only this exact Owner-direct stopped-install scope is authorized.'),
 ('<pr99-readonly-recovery>','<pr99-owner-stopped-install>')):program=program.replace(a,b)
program=program.replace("if state!='Success' or detail.get('ExitCode')!=0:\n                raise Hold('STOPPED_INSTALL_FAILED_NO_RETRY')", "if state!='Success' or detail.get('ExitCode')!=0:\n                row['exit_code']=detail.get('ExitCode')\n                raw=detail.get('Output','')\n                try:\n                    try:failed=json.loads(raw)\n                    except ValueError:failed=json.loads(base64.b64decode(raw,validate=True))\n                    if set(failed)=={'status','error_type','code','retry_allowed'} and failed['status']=='OWNER_STOPPED_INSTALL_HOLD' and failed['retry_allowed']is False:\n                        row['host_error_code']=safe(failed['code']);row['host_error_type']=safe(failed['error_type'])\n                except Exception:pass\n                raise Hold('STOPPED_INSTALL_FAILED_NO_RETRY')")
(base/'owner_stopped_probe.py').write_text(program)
workflow=(base/'pr99-prepare-identity.yml').read_text()
embedded='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
replacement='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(embedded)==2
workflow=workflow.replace(embedded,replacement).replace('pr99-prepare-identity-','pr99-owner-stopped-')
workflow=workflow.replace('New fixed read-only recovery scope.','Owner-direct original stopped-install scope.')
workflow=workflow.replace('PR99 Owner domestic identity preparation','PR99 Owner original stopped installation').replace('Prepare fixed domestic dedicated identity once','Install original fixed stopped candidate once')
workflow=workflow.replace('prepare-identity:', 'install-stopped:').replace('Validate fixed preparation program without cloud credentials','Validate stopped installation program without cloud credentials')
(base/'pr99-owner-stopped.yml').write_text(workflow)
compile(program,'owner_stopped_probe.py','exec')
print('OWNER_ORIGINAL_STOPPED_BUILD_COMPLETE')

"""Build one new fixed source-only observer, retaining original one-shot channel."""
import ast
from pathlib import Path

base=Path(__file__).parent
old=(base/'credential_writer_probe.py').read_text()
host=(base/'config_flow_host.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    import ast
    def need(ok):
        if not ok:raise ValueError('CONFIG_FLOW_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    context={'__name__':'config_syntax_contract'};exec(compile(HOST_PROGRAM,'fixed_config_definitions','exec'),context)
    fields(d,'scope hostname nonce observed_at sources raw_private_literals_disclosed environment_read database_opened business_imports service_actions effective_runtime_configuration_proven')
    need(d['scope']=='PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for key in ('raw_private_literals_disclosed','environment_read','database_opened','effective_runtime_configuration_proven'):need(d[key]is False)
    for key in ('business_imports','service_actions'):need(type(d[key])is int and d[key]==0)
    need(type(d['sources'])is list and len(d['sources'])==4)
    for row,(path,pin) in zip(d['sources'],context['PINS']):
        fields(row,'path sha256 functions redacted_syntax');need(row['path']==path and row['sha256']==pin)
        need(type(row['functions'])is list and len(row['functions'])<=120)
        for f in row['functions']:
            fields(f,'name line');need(type(f['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,100}',f['name']))
            need(type(f['line'])is int and 0<f['line']<100000)
        code=row['redacted_syntax'];need(type(code)is str and len(code.encode())<=55000)
        tree=ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant):
                need((type(node.value)is str and node.value in context['LITERALS']) or node.value is None or type(node.value)is bool or (type(node.value)is int and node.value in (0,1,2)))
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=32768:raise ValueError()
        try:wire=json.loads(output)
        except ValueError:wire=json.loads(base64.b64decode(output,validate=True))
        assert type(wire)is dict and set(wire)=={'encoding','bytes','sha256','payload'}
        assert wire['encoding']=='PR99_CONFIG_FLOW_ZLIB_V1' and type(wire['bytes'])is int and 0<wire['bytes']<=180000
        packed=base64.b64decode(wire['payload'],validate=True);decoder=zlib.decompressobj();raw=decoder.decompress(packed,180001)
        assert decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
        assert len(raw)==wire['bytes'] and hashlib.sha256(raw).hexdigest()==wire['sha256']
        return validate_observation(json.loads(raw),expected,nonce)
    except Exception:raise Hold('CONFIG_FLOW_OUTPUT_REJECTED') from None
'''
test='''def self_test():
    n={'__name__':'config_fixture'};exec(compile(HOST_PROGRAM,'fixed_config_source','exec'),n)
    raw='import missing_business_module\\nPRIVATE="DO_NOT_DISCLOSE_TOKEN"\\ndef load_env(path):\\n token="DO_NOT_DISCLOSE_TOKEN"\\n return os.environ.get("TRADING_DATABASE_URL")\\ndef irrelevant():\\n return "PRIVATE_OTHER"'
    clean=n['excerpt'](raw)
    assert 'DO_NOT_DISCLOSE_TOKEN' not in json.dumps(clean) and 'PRIVATE_OTHER' not in json.dumps(clean)
    assert 'TRADING_DATABASE_URL' in clean['redacted_syntax'] and 'return os.environ' in clean['redacted_syntax']
    assert len(clean['functions'])==2 and 'def irrelevant' not in clean['redacted_syntax']
    d={'scope':'PR99_REDACTED_STARTUP_CONFIGURATION_FLOW_NOT_RUNTIME_ATTESTATION','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-18T15:40:00Z',
       'sources':[{'path':p,'sha256':h,**clean} for p,h in n['PINS']],'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}
    assert decode_receipt(n['wire'](d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(n['wire'](d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    changes=(lambda x:x.update(effective_runtime_configuration_proven=True),lambda x:x.update(environment_read=True),
        lambda x:x.update(private='TOKEN'),lambda x:x['sources'][0].update(sha256='0'*64),
        lambda x:x['sources'][0].update(redacted_syntax='token="PRIVATE_SECRET"'),
        lambda x:x.update(service_actions=True),lambda x:x['sources'][0]['functions'][0].update(name='X=PRIVATE'),
        lambda x:x['sources'][0].update(redacted_syntax='X=123456789'))
    for change in changes:
        v=json.loads(json.dumps(d));change(v)
        try:decode_receipt(n['wire'](v),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('PRIVATE_OR_FALSE_CONFIG_PROOF_ACCEPTED')
    for raw in ('X=b"SECRET"','X=987654321','X="secret"','X=f"PRIVATE_SECRET{variable}"'):
        assert 'SECRET' not in n['excerpt'](raw)['redacted_syntax']
    shell=shell_for(HOSTS[0][4],'a'*32)
    assert 'systemctl' not in HOST_PROGRAM and 'sqlite3' not in HOST_PROGRAM and 'subprocess' not in HOST_PROGRAM
    print('PR99_CONFIG_FLOW_8_REJECTIONS_REDACTION_WIRE_AND_ONE_SHOT_BOUNDARIES_PASS_NO_CLOUD',flush=True)
'''
replacements=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='HOST_PROGRAM':
        replacements.append((node.lineno,node.end_lineno,'HOST_PROGRAM='+repr(host)))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','decode_receipt','self_test'):
        replacements.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else '' if node.name=='decode_receipt' else test))
lines=old.splitlines()
for begin,end,text in reversed(replacements):lines[begin-1:end]=text.splitlines()
program='\n'.join(lines)+'\n'
program=program.replace('WRITER_METADATA_OBSERVED_NOT_FENCE_OR_DRAIN','CONFIG_FLOW_OBSERVED_NOT_EFFECTIVE_ATTESTATION').replace('WRITER_METADATA_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','CONFIG_FLOW_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION')
program=program.replace('pr99-credential-writer-','pr99-config-flow-').replace('PR99_CREDENTIAL_WRITER_', 'PR99_CONFIG_FLOW_')
(base/'config_flow_probe.py').write_text(program)
workflow=(base/'pr99-credential-writer.yml').read_text()
embedded='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
replacement='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(embedded)==2
workflow=workflow.replace(embedded,replacement).replace('pr99-credential-writer-','pr99-config-flow-').replace('PR99 exact credential database candidate handles','PR99 redacted startup configuration flow')
workflow=workflow.replace('Observe fixed migration writer descriptors once','Read fixed redacted startup source flow once')
(base/'pr99-config-flow.yml').write_text(workflow)
compile(program,'config_flow_probe.py','exec')
print('CONFIG_FLOW_BUILD_COMPLETE')

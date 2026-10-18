"""New fixed source inspection through the original one-shot channel."""
import ast
from pathlib import Path
base=Path(__file__).parent
old=(base/'config_flow_probe.py').read_text()
host=(base/'repository_semantics_host.py').read_text()
contract='''def validate_observation(d,expected,nonce):
    import ast
    def need(ok):
        if not ok:raise ValueError('REPOSITORY_SEMANTICS_CONTRACT')
    def fields(x,keys):need(type(x)is dict and set(x)==set(keys.split()))
    n={'__name__':'semantics_contract'};exec(compile(HOST_PROGRAM,'fixed_semantics_definitions','exec'),n)
    fields(d,'scope hostname nonce observed_at sources raw_private_literals_disclosed environment_read database_opened business_imports service_actions effective_runtime_configuration_proven')
    need(d['scope']=='PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION' and d['hostname']==expected and d['nonce']==nonce)
    need(type(d['observed_at'])is str and re.fullmatch('[0-9T:.Z-]{19,40}',d['observed_at']))
    for key in ('raw_private_literals_disclosed','environment_read','database_opened','effective_runtime_configuration_proven'):need(d[key]is False)
    for key in ('business_imports','service_actions'):need(type(d[key])is int and d[key]==0)
    need(type(d['sources'])is list and len(d['sources'])==len(n['TARGETS']))
    for row,(path,classes) in zip(d['sources'],n['TARGETS']):
        fields(row,'path sha256 definitions selected_classes redacted_syntax')
        need(row['path']==path and row['selected_classes']==list(classes))
        need(type(row['sha256'])is str and re.fullmatch('[0-9a-f]{64}',row['sha256']))
        if path in n['PINS']:need(row['sha256']==n['PINS'][path])
        need(type(row['definitions'])is list and len(row['definitions'])<=160)
        for f in row['definitions']:
            fields(f,'name line kind')
            need(type(f['name'])is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,100}',f['name']))
            need(type(f['line'])is int and 0<f['line']<100000 and f['kind']in('ClassDef','FunctionDef','AsyncFunctionDef'))
        code=row['redacted_syntax'];need(type(code)is str and len(code.encode())<=170000)
        tree=ast.parse(code)
        need(set(x.name for x in tree.body if isinstance(x,ast.ClassDef))==set(classes))
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant):
                need((type(node.value)is str and node.value=='PRIVATE_LITERAL_WITHHELD') or node.value is None or type(node.value)is bool or (type(node.value)is int and node.value in (0,1,2)))
    return d

def decode_receipt(output,expected,nonce):
    try:
        if type(output)is not str or len(output.encode())>=32768:raise ValueError()
        try:wire=json.loads(output)
        except ValueError:wire=json.loads(base64.b64decode(output,validate=True))
        assert type(wire)is dict and set(wire)=={'encoding','bytes','sha256','payload'}
        assert wire['encoding']=='PR99_STORAGE_SEMANTICS_ZLIB_V1' and type(wire['bytes'])is int and 0<wire['bytes']<=360000
        packed=base64.b64decode(wire['payload'],validate=True);decoder=zlib.decompressobj();raw=decoder.decompress(packed,360001)
        assert decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
        assert len(raw)==wire['bytes'] and hashlib.sha256(raw).hexdigest()==wire['sha256']
        return validate_observation(json.loads(raw),expected,nonce)
    except Exception:raise Hold('REPOSITORY_SEMANTICS_OUTPUT_REJECTED') from None
'''
test='''def self_test():
    import ast
    import tempfile
    n={'__name__':'semantics_fixture'};exec(compile(HOST_PROGRAM,'fixed_semantics_source','exec'),n)
    raw='import missing_business_module\\nPRIVATE="DO_NOT_DISCLOSE_TOKEN"\\nclass CredentialStore:\\n "PRIVATE_DOCSTRING"\\n def empty(self):\\n  "PRIVATE_DOCSTRING"\\n def put(self,value):\\n  return f"PRIVATE_TEMPLATE{value}"\\ndef helper():\\n return b"PRIVATE_BYTES"'
    clean=n['excerpt'](raw,('CredentialStore',))
    for private in ('DO_NOT_DISCLOSE_TOKEN','PRIVATE_DOCSTRING','PRIVATE_TEMPLATE','PRIVATE_BYTES'):
        assert private not in json.dumps(clean)
    assert 'class CredentialStore' in clean['redacted_syntax'] and 'pass' in clean['redacted_syntax']
    try:n['excerpt'](raw,('NotPresent',))
    except RuntimeError:pass
    else:raise AssertionError('MISSING_REQUIRED_CLASS_ACCEPTED')
    sources=[]
    for path,classes in n['TARGETS']:
        text='\\n'.join('class '+x+':\\n pass' for x in classes) or 'import missing_business_module'
        sources.append({'path':path,'sha256':n['PINS'].get(path,'b'*64),**n['excerpt'](text,classes)})
    d={'scope':'PR99_STORAGE_IMPLEMENTATIONS_NOT_RUNTIME_ATTESTATION','hostname':HOSTS[0][4],'nonce':'a'*32,'observed_at':'2026-10-19T00:00:00Z',
       'sources':sources,'raw_private_literals_disclosed':False,'environment_read':False,'database_opened':False,'business_imports':0,'service_actions':0,'effective_runtime_configuration_proven':False}
    assert decode_receipt(n['wire'](d),HOSTS[0][4],'a'*32)==d
    assert decode_receipt(base64.b64encode(n['wire'](d).encode()).decode(),HOSTS[0][4],'a'*32)==d
    changes=(lambda x:x.update(effective_runtime_configuration_proven=True),lambda x:x.update(database_opened=True),
        lambda x:x.update(private='TOKEN'),lambda x:x['sources'][-1].update(sha256='0'*64),
        lambda x:x['sources'][0].update(redacted_syntax='token="PRIVATE_SECRET"'),
        lambda x:x.update(service_actions=True),lambda x:x['sources'][0].update(selected_classes=[]))
    for change in changes:
        bad=json.loads(json.dumps(d));change(bad)
        try:decode_receipt(n['wire'](bad),HOSTS[0][4],'a'*32)
        except Hold:pass
        else:raise AssertionError('PRIVATE_OR_FALSE_STORAGE_PROOF_ACCEPTED')
    # Real descriptor reads reject links and parent-directory links, without
    # opening a business database or executing any of the inspected imports.
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);(root/'sub').mkdir();(root/'sub/a.py').write_text(raw)
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            assert n['read_source'](fd,'sub/a.py')==raw.encode()
            (root/'sub/link.py').symlink_to('a.py')
            (root/'linked').symlink_to('sub',target_is_directory=True)
            for path in ('sub/link.py','linked/a.py'):
                try:n['read_source'](fd,path)
                except OSError:pass
                else:raise AssertionError('SOURCE_LINK_ACCEPTED')
        finally:os.close(fd)
    assert len(shell_for(HOSTS[0][4],'a'*32).encode())<11000
    assert 'subprocess' not in HOST_PROGRAM and 'systemctl' not in HOST_PROGRAM
    print('PR99_REPOSITORY_SEMANTICS_REDACTION_REQUIRED_CLASSES_SAFE_READS_CONTRACT_PASS_NO_CLOUD',flush=True)
'''
changes=[]
for node in ast.parse(old).body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='HOST_PROGRAM':
        changes.append((node.lineno,node.end_lineno,'HOST_PROGRAM='+repr(host)))
    if isinstance(node,ast.FunctionDef) and node.name in ('validate_observation','decode_receipt','self_test'):
        changes.append((node.lineno,node.end_lineno,contract if node.name=='validate_observation' else '' if node.name=='decode_receipt' else test))
lines=old.splitlines()
for begin,end,value in reversed(changes):lines[begin-1:end]=value.splitlines()
program='\n'.join(lines)+'\n'
program=program.replace('pr99-config-flow-','pr99-repository-semantics-').replace('PR99_CONFIG_FLOW_','PR99_REPOSITORY_SEMANTICS_')
program=program.replace('CONFIG_FLOW_OBSERVED_NOT_EFFECTIVE_ATTESTATION','STORAGE_IMPLEMENTATIONS_OBSERVED_NOT_RUNTIME_ATTESTATION')
program=program.replace('CONFIG_FLOW_BATCH_COMPLETE_NOT_PRODUCTION_ADMISSION','STORAGE_IMPLEMENTATIONS_BATCH_NOT_PRODUCTION_ADMISSION')
(base/'repository_semantics_probe.py').write_text(program)
workflow=(base/'pr99-config-flow.yml').read_text()
embedded='\n'.join('          '+line for line in old.rstrip('\n').split('\n'))
replacement='\n'.join('          '+line for line in program.rstrip('\n').split('\n'))
assert workflow.count(embedded)==2
workflow=workflow.replace(embedded,replacement).replace('pr99-config-flow-','pr99-repository-semantics-')
workflow=workflow.replace('PR99 redacted startup configuration flow','PR99 exact storage implementation binding')
workflow=workflow.replace('Read fixed redacted startup source flow once','Read exact storage implementation definitions once')
(base/'pr99-repository-semantics.yml').write_text(workflow)
compile(program,'repository_semantics_probe.py','exec')
print('REPOSITORY_SEMANTICS_BUILD_COMPLETE')

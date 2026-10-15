"""Synthetic topology evidence and real pure validators; no host/network effects."""
import copy
import json
import pathlib
import unittest
from unittest import mock

import activation_control
import epoch7_topology_projection as t
import node_sqlite_probe as n
import probe_driver as p
import probe_helpers as h
from test_probe_driver import fixture as policy_fixture
from test_node_sqlite_probe import fixture_attempt, fixture_receipt, fixture_node


def status(uid, gid, capability=0):
    return {'Uid':'\t'.join([str(uid)]*4),'Gid':'\t'.join([str(gid)]*4),
        'Groups':str(gid),'CapEff':'%016x'%capability,'CapBnd':'%016x'%capability,
        'CapAmb':'%016x'%capability,'NoNewPrivs':'1','Seccomp':'2'}


def process(pid, uid, gid, capability=0):
    return {'pid':pid,'starttime':123,'status':status(uid,gid,capability),'cgroup_sha256':'7'*64}


def resource(path, sha, size=100):
    return {'path':path,'kind':'FILE','sha256':sha,
        'identity':dict(fixture_node()['metadata'],uid=0,gid=0,mode=0o644,size=size)}


def unit(policy, suffix):
    paths=p.scope(policy);name=paths[suffix+'_unit']
    value={'Id':name,'LoadState':'loaded','NeedDaemonReload':'no',
        'FragmentPath':'/run/systemd/system/'+name,'DropInPaths':'',
        'ActiveState':'active','SubState':'listening' if suffix=='socket' else 'running'}
    if suffix=='socket':
        value.update(Listen=paths['socket']+' (Stream)',Accept='no',Triggers=paths['service_unit'],
            SocketUser='xuanjun-dispatcher',SocketGroup='xuanjun-ledger-client',SocketMode='0660',
            DirectoryMode='0755',RemoveOnStop='yes')
    else:
        command=policy['python']['path']+' -B '+paths['root']+'/probe_helpers.py --config '+paths['root']+'/helper-ledger-server.json --mode server'
        value.update(User='xuanjun-dispatcher',Group='xuanjun-control-db',WorkingDirectory=paths['root'],
            TriggeredBy=paths['socket_unit'],MainPID='900',InvocationID='f'*32,
            ExecStart='{ path='+policy['python']['path']+' ; argv[]='+command+
            ' ; ignore_errors=no ; start_time=[] ; stop_time=[] ; pid=900 ; code=(null) ; status=0 }')
    return value


def fixture():
    root=pathlib.Path(activation_control.__file__).resolve().parent.parent
    policy=policy_fixture(root)[0]
    sources={name:pathlib.Path(module.__file__).read_bytes() for name,module in
             (('probe_driver.py',p),('probe_helpers.py',h),('node_sqlite_probe.py',n))}
    sources['deploy/integration-manifest.json']=(root/'deploy/integration-manifest.json').read_bytes()
    policy['driver_sha256']=t.digest(sources['probe_driver.py']);policy['helper_sha256']=t.digest(sources['probe_helpers.py'])
    attempt,policy,observation,policy_sha=fixture_attempt(policy);paths=p.scope(policy)
    receipt=n.parse(fixture_receipt(attempt));cases=[];servers=[]
    namespace='pid:[4026531836]';manager=process(1,0,0)
    endpoint={'dev':12,'ino':34,'uid':1003,'gid':1007,'mode':0o660}
    denials={'child_memory_unchanged':True,'target':'OWN_NONSECRET_FORK_CHILD',
        'denied_callers':'THREE_TRACKED_FORK_CHILDREN','cleanup_errors':[],'cleanup_state':'REAPED',
        'results':[{'syscall':name,'status':'PASS_OBSERVED','return':-1,'errno':1,'cleanup_errors':[],
                    'cleanup_state':'REAPED'} for name in ('ptrace','process_vm_readv','process_vm_writev')]}
    servers.append({'event':'SERVER_READY','own':process(900,1003,1006,1<<19),
        'listener':dict(endpoint,acl_sha256='1'*64),'syscall_denials':denials})
    for number,role,kind in p.CASES:
        row={'case':number,'status':'FAIL_OBSERVED' if number in (6,8) else 'PASS_OBSERVED',
            'production_verifier_admission':'NOT_VERIFIED',
            'owner_process_gate':'NOT_VERIFIED_FIXED_PRODUCTION_PROCESS_PINS_NOT_REMAPPED',
            'namespace_proof':{'pid':1000+number,'namespace':namespace,'manager_namespace':namespace,
                              'helper_proc_view':namespace,'same_pid_namespace':True,'same_proc_namespace':True}}
        if number in (6,8): row.update(reason='ConnectionResetError',bound_before_failure=True,expected_rejection_observed=True)
        else: row.update(mechanism='INHERITED_MANAGER_CHALLENGE',peer=[1,0,0])
        context=t.types.SimpleNamespace(policy=policy,paths=paths,policy_sha=policy_sha)
        config=p.HostOps.helper_config(context,role,number)
        values={'manager-process':copy.deepcopy(manager),'boot-id':{'sha256':'a'*64},
            'self-pid-namespace':{'link':namespace},'manager-unit:socket':unit(policy,'socket'),
            'manager-unit:service':unit(policy,'service')}
        for pin in config['public_files']: values['public:'+pin['path']]={'sha256':pin['sha256'],'size':100}
        for name in ('fixture-activation.lock','fixture-dispatcher.json'):
            values['metadata-only:'+name]={'uid':0,'gid':0,'mode':0o644,'acl_sha256':'b'*64,'content_opened':False}
        for path in ('/run/dbus/system_bus_socket',)+ (('/run/systemd/private',) if role=='broker' else ()):
            values['manager-channel:'+path]={'dev':12,'ino':35,'acl_sha256':'c'*64}
        row['readpaths']=[{'path_class':key,'status':'PASS_OBSERVED','evidence':value} for key,value in sorted(values.items())]
        if role=='native': row['sdk']=[{'path':x['path'],'status':'PASS_OBSERVED','sha256':x['sha256'],'size':x['size']} for x in policy['sdk_bindings']]
        cases.append(row)
        argv=[policy['python']['path'],'-B',paths['root']+'/probe_helpers.py','--config',
              paths['root']+'/helper-'+role+'-client.json','--mode','client']
        if number not in (6,8):
            servers.append({'event':'PEER_ACCESS_PROOF','case':number,'proof':{
                'status':'PASS_OBSERVED','pid':1000+number,'uid':policy['profiles'][role]['uid'],
                'argv_sha256':t.digest(b'\0'.join(x.encode() for x in argv)+b'\0'),
                'cgroup_sha256':'e'*64,'owner_fixture_criterion':role=='callback','production_owner_verifier':'NOT_VERIFIED'}})
        receipt['events'] += [{'event':'CASE_INTENT','detail':{'case':number,'role':role,'kind':kind}},
                              {'event':'CASE_OBSERVED','detail':row}]
    output=b''.join(t.canonical(x)+b'\n' for x in servers)
    receipt['events'].append({'event':'OUTPUT_CAPTURED','detail':{'path':paths['root']+'/output-ledger.jsonl',
        'sha256':t.digest(output),'bytes':len(output),'observations':servers}})
    receipt['socket_identity']=endpoint
    files={paths['root']+'/probe_helpers.py':sources['probe_helpers.py'],
           paths['root']+'/probe-policy.json':t.canonical(policy)+b'\n',
           '/run/systemd/system/'+paths['socket_unit']:p.render_socket(policy)}
    for role in p.ROLES:
        name,raw=p.render_unit(policy,role);files['/run/systemd/system/'+name]=raw
    receipt['resources'] += [resource(path,t.digest(raw),len(raw)) for path,raw in files.items()]
    receipt['resources'] += [resource(paths['root']+'/candidate-'+path.rsplit('/',1)[1],pin) for path,pin in policy['candidate_sources'].items()]
    attempt['result'].update(cases=cases,server_observations=servers)
    observation['finite_probe']=attempt
    info=dict(fixture_node()['metadata'],uid=0,gid=0,mode=0o755,nlink=2)
    dropins={'schema':1,'unit':'xuanjun-ledger.socket','reread':'EXACT_PRE_POST',
        'roots':{path:{'present':False,'metadata':None,'parent_metadata':copy.deepcopy(info),'files':{}}
                 for path in t.SOCKET_DROPIN_PATHS}}
    return {'observation':observation,'receipt':receipt,'sources':sources,'kit_sha':'f'*64,'dropins':dropins}


def bind(value):
    raw=t.canonical(value['receipt'])+b'\n'
    reported=value['observation']['finite_probe']['result']['created_receipt']
    reported['sha256']=t.digest(raw);reported['metadata']['size']=len(raw)
    return raw,copy.deepcopy(reported['metadata'])


def project(value):
    raw,metadata=bind(value)
    return t.project_topology(value['observation'],raw,metadata,value['kit_sha'],value['sources'],value['dropins'],'d'*64)


def response(proposal, review_id=7000000001):
    return t.canonical({'id':review_id,'user':{'id':332398908,'login':'huhongchuan0422-creator'},
        'issue_url':'https://api.github.com/repos/'+t.approval.REPO+'/issues/58',
        'body':t.approval.MARKER+t.canonical(proposal['expected_review_body']).decode()})


class ProjectionTests(unittest.TestCase):
    def test_complete_synthetic_projection_is_deterministic_and_no_io(self):
        value=fixture();before=copy.deepcopy(value)
        with mock.patch.object(t.approval,'fetch',side_effect=AssertionError('NETWORK_FORBIDDEN')):
            proposal=project(value);other=project(value)
        self.assertEqual(proposal,other);self.assertEqual(value['receipt'],before['receipt'])
        self.assertEqual(proposal['topology']['creator']['pid'],1)
        self.assertEqual(proposal['topology']['endpoint_identity'],{'uid':1003,'gid':1007,'mode':0o660})
        self.assertFalse(proposal['expected_review_body']['production_resume_authorized'])
        self.assertNotIn('recovery_plan_sha256',proposal['expected_review_body'])
        self.assertNotIn('review_id',proposal['expected_review_body'])
        self.assertIn('PINNED_DRIVER_CHECK_HOST',proposal['expected_review_body']['systemd_version_evidence'])
    def test_receipt_policy_and_source_buffers_are_required(self):
        for mutation in ('driver','helper','node','runtime','extra','policy'):
            value=fixture()
            if mutation=='extra':value['sources']['extra.py']=b'x'
            elif mutation=='policy':value['observation']['finite_probe']['policy_sha256']='0'*64
            else:
                name={'driver':'probe_driver.py','helper':'probe_helpers.py','node':'node_sqlite_probe.py','runtime':'deploy/integration-manifest.json'}[mutation]
                value['sources'][name]+=b' '
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_every_case_namespace_and_readpath_must_pass(self):
        for number in range(8):
            for mutation in ('missing_namespace','false_namespace','readpath_failed','readpath_missing'):
                value=fixture();row=value['observation']['finite_probe']['result']['cases'][number]
                if mutation=='missing_namespace':row.pop('namespace_proof')
                elif mutation=='false_namespace':row['namespace_proof']['same_proc_namespace']=False
                elif mutation=='readpath_failed':row['readpaths'][0]['status']='NOT_VERIFIED'
                else:row['readpaths'].pop()
                with self.subTest(number=number,mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_namespace_links_and_peer_kernel_ids_reject_drift(self):
        for mutation in ('link','self','peer_uid','peer_pid','peer_gid','peer_bool'):
            value=fixture();row=value['observation']['finite_probe']['result']['cases'][0]
            if mutation=='link':row['namespace_proof']['helper_proc_view']='pid:[3]'
            elif mutation=='self':next(x for x in row['readpaths'] if x['path_class']=='self-pid-namespace')['evidence']['link']='pid:[3]'
            else: row['peer'][{'peer_uid':1,'peer_pid':0,'peer_gid':2,'peer_bool':0}[mutation]]=False if mutation=='peer_bool' else 2
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_manager_lifetime_and_all_uid_slots_are_exact(self):
        for mutation in ('start','cgroup','uid','gid','missing'):
            value=fixture();row=next(x for x in value['observation']['finite_probe']['result']['cases'][0]['readpaths'] if x['path_class']=='manager-process')['evidence']
            if mutation=='start':row['starttime']+=1
            elif mutation=='cgroup':row['cgroup_sha256']='0'*64
            elif mutation=='missing':row['status'].pop('Seccomp')
            else:row['status']['Uid' if mutation=='uid' else 'Gid']='0 0 1002 0'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_source_readpaths_and_loaded_unit_mechanism_bind(self):
        for mutation in ('hash','dropin','socket_mode','command','private_open'):
            value=fixture();rows=value['observation']['finite_probe']['result']['cases'][0]['readpaths']
            if mutation=='hash':next(x for x in rows if x['path_class'].startswith('public:'))['evidence']['sha256']='0'*64
            elif mutation=='private_open':next(x for x in rows if x['path_class'].startswith('metadata-only:'))['evidence']['content_opened']=True
            else:
                target='socket' if mutation=='socket_mode' else 'service'
                data=next(x for x in rows if x['path_class']=='manager-unit:'+target)['evidence']
                data[{'dropin':'DropInPaths','socket_mode':'SocketMode','command':'ExecStart'}[mutation]]='unexpected'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_missing_broker_private_channel_and_duplicate_paths_reject(self):
        for mutation in ('missing','duplicate'):
            value=fixture();rows=value['observation']['finite_probe']['result']['cases'][1]['readpaths']
            if mutation=='missing':rows[:]=[x for x in rows if x['path_class']!='manager-channel:/run/systemd/private']
            else:rows[0]=copy.deepcopy(rows[1])
            with self.assertRaises(ValueError):project(value)
    def test_sdk_hash_size_or_failure_cannot_be_hidden(self):
        for key,bad in (('status','NOT_VERIFIED'),('size',999),('sha256','0'*64)):
            value=fixture();value['observation']['finite_probe']['result']['cases'][0]['sdk'][0][key]=bad
            with self.assertRaises(ValueError):project(value)
    def test_case_receipt_and_output_capture_cannot_be_forged_in_result(self):
        for mutation in ('case','output','order','duplicate','missing'):
            value=fixture()
            if mutation=='case':value['observation']['finite_probe']['result']['cases']=copy.deepcopy(value['observation']['finite_probe']['result']['cases']);value['observation']['finite_probe']['result']['cases'][0]['peer'][2]=1
            elif mutation=='output':value['observation']['finite_probe']['result']['server_observations']=[]
            elif mutation=='order':value['receipt']['events'][1:3]=list(reversed(value['receipt']['events'][1:3]))
            elif mutation=='duplicate':value['receipt']['events'].append(copy.deepcopy(value['receipt']['events'][2]))
            else:value['receipt']['events'].pop(2)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_created_sources_units_and_duplicate_resources_reject(self):
        for mutation in ('hash','mode','duplicate','missing'):
            value=fixture();rows=value['receipt']['resources']
            if mutation=='hash':rows[1]['sha256']='0'*64
            elif mutation=='mode':rows[1]['identity']['mode']=0o666
            elif mutation=='duplicate':rows.append(copy.deepcopy(rows[1]))
            else:rows.pop(1)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_server_capability_syscall_and_cleanup_results_must_be_verified(self):
        for mutation in ('cap','denial','cleanup','memory','extra'):
            value=fixture();row=value['observation']['finite_probe']['result']['server_observations'][0]
            if mutation=='cap':row['own']['status']['CapEff']='0000000000000000'
            elif mutation=='denial':row['syscall_denials']['results'][0]['status']='NOT_VERIFIED'
            elif mutation=='cleanup':row['syscall_denials']['results'][0]['cleanup_state']='UNKNOWN'
            elif mutation=='memory':row['syscall_denials']['child_memory_unchanged']=False
            else:row['syscall_denials']['extra']=True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_signal_denial_requires_actual_sigsys(self):
        value=fixture();row=value['observation']['finite_probe']['result']['server_observations'][0]['syscall_denials']['results'][0]
        row.pop('return');row.pop('errno');row['signal']=31;project(value)
        row['signal']=9
        with self.assertRaises(ValueError):project(value)
    def test_peer_access_failed_missing_or_wrong_identity_rejects(self):
        for mutation in ('status','pid','uid','argv_sha256','owner_fixture_criterion','missing'):
            value=fixture();rows=value['observation']['finite_probe']['result']['server_observations']
            if mutation=='missing':rows.pop(1)
            else:rows[1]['proof'][mutation]={'status':'NOT_VERIFIED','pid':999,'uid':0,'argv_sha256':'0'*64,'owner_fixture_criterion':True}[mutation]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)
    def test_unknown_diagnostic_rejects_even_aggregate_success(self):
        value=fixture();value['observation']['finite_probe']['result']['server_observations'].append({'event':'SERVER_REJECT','reason':'ValueError'})
        with self.assertRaises(ValueError):project(value)
    def test_endpoint_measured_owner_group_and_mode_are_exact(self):
        for key,bad in (('uid',0),('gid',1006),('mode',0o666),('ino',True)):
            value=fixture();value['receipt']['socket_identity'][key]=bad
            with self.assertRaises(ValueError):project(value)
    def test_bound_to_protected_receipt_metadata_and_hash(self):
        value=fixture();raw,info=bind(value);info['ino']+=1
        with self.assertRaises(ValueError):t.project_topology(value['observation'],raw,info,value['kit_sha'],value['sources'],value['dropins'],'d'*64)
    def test_topology_matches_existing_server_compiler_contract(self):
        import epoch7_additive_server as server
        value=project(fixture())['topology']
        self.assertEqual(set(value['clients']),server.PROFILES)
        self.assertEqual(set(value['creator']),server.CREATOR_KEYS-{'topology_evidence_sha256'})
        self.assertEqual(set(value['endpoint_identity']),server.ENDPOINT_KEYS-{'path'})

    def test_socket_dropins_bind_exact_three_protected_roots(self):
        value=fixture();absent=project(value)
        first=value['dropins']['roots'][t.SOCKET_DROPIN_PATHS[0]]
        first.update(present=True,metadata=copy.deepcopy(first['parent_metadata']))
        present=project(value)
        self.assertNotEqual(absent['bindings']['socket_dropins_sha256'],present['bindings']['socket_dropins_sha256'])
        self.assertNotEqual(absent['topology_sha256'],present['topology_sha256'])
    def test_socket_dropin_missing_unknown_content_or_authority_reject(self):
        for mutation in ('missing','extra','file','mode','uid','bool','reread','absent_metadata'):
            value=fixture();proof=value['dropins'];first=proof['roots'][t.SOCKET_DROPIN_PATHS[0]]
            if mutation=='missing':proof['roots'].pop(t.SOCKET_DROPIN_PATHS[1])
            elif mutation=='extra':proof['roots']['/other/unit.d']=copy.deepcopy(first)
            elif mutation=='file':first['files']['unexpected.conf']={'sha256':'a'*64}
            elif mutation=='mode':first['parent_metadata']['mode']=0o775
            elif mutation=='uid':first['parent_metadata']['uid']=1002
            elif mutation=='bool':first['present']=1
            elif mutation=='reread':proof['reread']='NOT_VERIFIED'
            else:first['metadata']=copy.deepcopy(first['parent_metadata'])
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):project(value)


class ReviewTests(unittest.TestCase):
    def setUp(self):self.proposal=project(fixture())
    def test_real_validator_accepts_only_exact_synthetic_response(self):
        value=t.authenticate_topology_review(response(self.proposal),7000000001,self.proposal)
        self.assertEqual(set(value),{'review_id','approval_body_sha256','evidence_sha256'})
        self.assertEqual(value['evidence_sha256'],self.proposal['topology_sha256'])
        self.assertEqual(value['approval_body_sha256'],t.digest(json.loads(response(self.proposal).decode())['body'].encode()))
    def test_wrong_author_destination_id_consumed_and_marker_reject(self):
        for mutation in ('author_id','author_login','destination','id','consumed','marker'):
            value=json.loads(response(self.proposal).decode());rid=7000000001
            if mutation=='author_id':value['user']['id']=1
            elif mutation=='author_login':value['user']['login']='other'
            elif mutation=='destination':value['issue_url']=value['issue_url'].replace('/58','/59')
            elif mutation=='id':value['id']+=1
            elif mutation=='consumed':rid=next(iter(t.approval.CONSUMED));value['id']=rid
            else:value['body']='APPROVED\n'+value['body']
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):t.authenticate_topology_review(t.canonical(value),rid,self.proposal)
    def test_review_body_unknown_missing_bool_and_resume_authority_reject(self):
        for mutation in ('extra','missing','typed','resume','plan'):
            value=json.loads(response(self.proposal).decode());body=copy.deepcopy(self.proposal['expected_review_body'])
            if mutation=='extra':body['extra']=True
            elif mutation=='missing':body.pop('probe_receipt_sha256')
            elif mutation=='typed':body['schema']=True
            elif mutation=='resume':body['production_resume_authorized']=True
            else:body['recovery_plan_sha256']='1'*64
            value['body']=t.approval.MARKER+t.canonical(body).decode()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):t.authenticate_topology_review(t.canonical(value),7000000001,self.proposal)
    def test_duplicate_body_key_rejects(self):
        value=json.loads(response(self.proposal).decode());body=t.canonical(self.proposal['expected_review_body']).decode()
        value['body']=t.approval.MARKER+'{"schema":1,'+body[1:]
        with self.assertRaises(ValueError):t.authenticate_topology_review(t.canonical(value),7000000001,self.proposal)
    def test_proposal_tamper_rejects_before_fetch(self):
        for key in ('topology_raw','topology_sha256','expected_review_body','bindings'):
            value=copy.deepcopy(self.proposal)
            if key=='topology_raw':value[key]+=b' '
            elif key=='topology_sha256':value[key]='0'*64
            else:value[key]['probe_receipt_sha256']='0'*64
            with mock.patch.object(t.approval,'fetch',side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 self.assertRaises(ValueError):t.fetch_topology_review(7000000001,value)
    def test_projected_receipt_flows_through_actual_current_server_compiler(self):
        import epoch7_additive_server as server
        from test_epoch7_additive_server import server_fixture
        config,manifest,sources,unused,unused2,absence,context=server_fixture()
        config['creator']=dict(self.proposal['topology']['creator'],topology_evidence_sha256=self.proposal['topology_sha256'])
        config['endpoint']=dict(self.proposal['topology']['endpoint_identity'],path=server.SOCKET_PATH)
        raw=t.canonical(config)
        result=[]
        for review_id in (7000000001,7000000002):
            review=t.authenticate_topology_review(response(self.proposal,review_id),review_id,self.proposal)
            addition=server.compile_addition(raw,t.digest(raw),manifest,t.digest(manifest),sources,
                self.proposal['topology_raw'],review,absence)
            server.validate_compiled(addition,t.digest(manifest));result.append(addition)
            self.assertEqual(addition['provenance']['topology_review'],review)
            self.assertEqual(addition['install_admission'],'NOT_GRANTED')
        self.assertNotEqual(t.digest(t.canonical(result[0])),t.digest(t.canonical(result[1])))
        self.assertEqual(result[0]['provenance']['topology_evidence_sha256'],result[1]['provenance']['topology_evidence_sha256'])
    def test_preparation_source_digest_is_required_and_binds_first_review(self):
        value=fixture();raw,info=bind(value)
        args=(value['observation'],raw,info,value['kit_sha'],value['sources'],value['dropins'])
        with self.assertRaises(ValueError):t.project_topology(*(args+(None,)))
        first=t.project_topology(*(args+('a'*64,)));second=t.project_topology(*(args+('b'*64,)))
        self.assertEqual(first['topology_raw'],second['topology_raw'])
        self.assertNotEqual(first['expected_review_body'],second['expected_review_body'])
        with self.assertRaises(ValueError):t.authenticate_topology_review(response(first),7000000001,second)
    def test_explicit_fetch_delegates_existing_authenticated_mechanism(self):
        raw=response(self.proposal)
        with mock.patch.object(t.approval,'fetch',side_effect=lambda rid,wanted:t.approval.validate(raw,rid,wanted)) as fetch:
            value=t.fetch_topology_review(7000000001,self.proposal)
        fetch.assert_called_once_with(7000000001,self.proposal['expected_review_body'])
        self.assertEqual(value['review_id'],7000000001)


if __name__=='__main__':unittest.main()

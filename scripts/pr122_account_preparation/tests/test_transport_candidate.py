"""Offline only: AST loads declarations; all I/O, cloud RPC and event reads mocked."""
import ast, base64, copy, datetime, hashlib, json, os, pathlib, subprocess, tempfile, unittest, zlib
from unittest.mock import patch
ROOT = pathlib.Path(__file__).resolve().parents[1]
YAML = (ROOT/'transport-candidate.yml').read_text()
INLINE = YAML.split("          python3 - <<'PY'\n",1)[1].split('\n          PY\n',1)[0]
SOURCE = '\n'.join(line[10:] for line in INLINE.splitlines())
TREE = ast.parse(SOURCE)
# Do not load imports, assignment side effects, or executable main guard. Only
# literal configuration, function/class declarations and injected stdlib names.
import urllib.request, urllib.parse, urllib.error, time, uuid, re, hmac
NS = dict(base64=base64,datetime=datetime,hashlib=hashlib,hmac=hmac,json=json,os=os,re=re,time=time,
          urllib=__import__('urllib'),uuid=uuid,zlib=zlib,Path=pathlib.Path)
for node in TREE.body:
    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
        exec(compile(ast.Module(body=[node],type_ignores=[]),'transport-declarations','exec'),NS)
    elif isinstance(node,ast.Assign):
        try: value=ast.literal_eval(node.value)
        except (ValueError,TypeError): continue
        NS[node.targets[0].id]=value

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.saved=NS.copy()
        NS['row']={'status':'HOLD','stage':'GATE','retry_allowed':False}
        NS['persist']=lambda: None
        NS['ARMED']=True
        NS['EXPIRES']=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)).isoformat()
        self.sha='a'*40; self.label=NS['PREFIX']+self.sha
        self.pr={'number':122,'state':'open','draft':True,'head':{'sha':self.sha,'ref':NS['BRANCH'],'repo':{'full_name':NS['REPO']}},'base':{'ref':NS['BASE']},'labels':[{'name':self.label}],'mergeable':True,'mergeable_state':'draft'}
        self.event={'action':'labeled','pull_request':copy.deepcopy(self.pr),'label':{'name':self.label},'repository':{'full_name':NS['REPO']},'sender':{'login':NS['ACTOR']}}
        self.run={'id':200,'event':'pull_request','run_attempt':1,'path':NS['WORKFLOW_PATH'],'display_title':self.label,'actor':{'login':NS['ACTOR']},'head_branch':NS['BRANCH'],'workflow_id':20,'head_sha':self.sha}
        self.runs=[self.run]
        self.env=patch.dict(os.environ,{'GITHUB_EVENT_NAME':'pull_request','GITHUB_REPOSITORY':NS['REPO'],'GITHUB_ACTOR':NS['ACTOR'],'GITHUB_TRIGGERING_ACTOR':NS['ACTOR'],'GITHUB_RUN_ATTEMPT':'1','GITHUB_RUN_ID':'200','GITHUB_EVENT_PATH':'/mock/event','ALIYUN_ACCESS_KEY_ID':'mock-id','ALIYUN_ACCESS_KEY_SECRET':'mock-secret'},clear=True)
        self.env.start()
        self.read=patch.object(pathlib.Path,'read_text',side_effect=lambda:json.dumps(self.event));self.read.start()
        NS['github']=self.github
        self.output=patch('builtins.print');self.output.start()
    def tearDown(self):
        self.output.stop();self.read.stop();self.env.stop();NS.clear();NS.update(self.saved)
    def github(self,path):
        if path.endswith('/pulls/122'): return copy.deepcopy(self.pr)
        if path.endswith('/actions/runs/200'): return copy.deepcopy(self.run)
        return {'workflow_runs':copy.deepcopy(self.runs),'total_count':len(self.runs)}
    def hold(self,fn,reason):
        with self.assertRaises(NS['Hold']) as c: fn()
        self.assertEqual(str(c.exception),reason)
    def test_disabled(self):
        NS['ARMED']=False;self.hold(NS['gate'],'DISABLED_PENDING_INDEPENDENT_REVIEW')
    def test_expired(self):
        NS['EXPIRES']='1970-01-01T00:00:00+00:00';self.hold(NS['gate'],'EXPIRED_OR_INVALID_WINDOW')
    def test_overlong_window(self):
        NS['EXPIRES']=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).isoformat();self.hold(NS['gate'],'EXPIRED_OR_INVALID_WINDOW')
    def test_draft_and_new_head_label_allowed(self):
        self.assertEqual(hashlib.sha256(NS['gate']()).hexdigest(),NS['PAYLOAD_SHA'])
    def test_stale_label(self):
        self.event['label']['name']=NS['PREFIX']+'b'*40;self.hold(NS['gate'],'EXACT_SHA_LABEL')
    def test_actor(self):
        os.environ['GITHUB_ACTOR']='other';self.hold(NS['gate'],'ACTOR')
    def test_trigger_actor(self):
        os.environ['GITHUB_TRIGGERING_ACTOR']='other';self.hold(NS['gate'],'ACTOR')
    def test_rerun(self):
        os.environ['GITHUB_RUN_ATTEMPT']='2';self.hold(NS['gate'],'RERUN_DENIED')
    def test_fork(self):
        self.event['pull_request']['head']['repo']['full_name']='other/repo';self.hold(NS['gate'],'BRANCH')
    def test_live_head_drift(self):
        self.pr['head']['sha']='c'*40;self.hold(NS['gate'],'PR_DRIFT')
    def test_unknown_mergeability(self):
        self.pr['mergeable']=None;self.hold(NS['gate'],'PR_NOT_CLEAN')
    def test_duplicate_older(self):
        self.runs.append(dict(self.run,id=100));self.hold(NS['gate'],'OTHER_ONE_SHOT_RUN_NO_RETRY')
    def test_duplicate_newer_non_fifo(self):
        self.runs.append(dict(self.run,id=300));self.hold(NS['gate'],'OTHER_ONE_SHOT_RUN_NO_RETRY')
    def test_duplicate_same_label_other_head(self):
        self.runs.append(dict(self.run,id=300,head_sha='c'*40));self.hold(NS['gate'],'OTHER_ONE_SHOT_RUN_NO_RETRY')
    def test_incomplete_history(self):
        old=self.github
        NS['github']=lambda p: dict(old(p),total_count=999) if '/runs?' in p else old(p)
        self.hold(NS['gate'],'INCOMPLETE_HISTORY')
    def test_github_api_failure(self):
        NS['github']=self.saved['github'];os.environ['GH_TOKEN']='mock'
        with patch.object(urllib.request,'build_opener',side_effect=OSError('mock')):
            self.hold(NS['gate'],'GITHUB_GATE_UNKNOWN')
    def test_payload_hash_mismatch(self):
        NS['PAYLOAD_SHA']='0'*64;self.hold(NS['gate'],'PAYLOAD_HASH')
    def detail(self,invoke,nonce):
        account={'state':'ACCOUNT_CREATED_VERIFIED','account':'xuanjun-customer','uid':999,'gid':999,'retry_allowed':False,'sudo_privileges':'DENIED','polkit_global_policy':'NOT_AUDITED','privilege_policy_changes':False}
        output={'hostname':NS['HOST'],'nonce':nonce,'payload_sha256':NS['PAYLOAD_SHA'],'result':account}
        return {'InstanceId':NS['INSTANCE'],'InvokeId':invoke,'InvocationStatus':'Success','ExitCode':0,'Output':json.dumps(output)}
    def fake_main(self,mode):
        calls=[]; order=[]
        NS['gate']=lambda:zlib.decompress(base64.b64decode(NS['PAYLOAD_Z64']))
        NS['persist']=lambda:order.append(('persist',NS['row'].get('stage')))
        NS['command']=lambda payload,nonce:'fixed mock command'
        def rpc(endpoint,version,action,credentials,**params):
            calls.append(action);order.append(('rpc',action))
            if action=='AssumeRole':return {'Credentials':{'AccessKeyId':'mock','AccessKeySecret':'mock','SecurityToken':'mock'}}
            if action=='RunCommand':
                if mode=='unknown': raise NS['Hold']('RPC_RESULT_UNKNOWN_NO_RETRY')
                if mode=='missing':return {}
                return {'InvokeId':'mock-invoke'}
            if mode=='pending': return {'InvocationResult':{'InstanceId':NS['INSTANCE'],'InvokeId':'mock-invoke','InvocationStatus':'Running'}}
            if mode=='query_mismatch': return {'InvocationResult':{'InstanceId':'wrong','InvokeId':'mock-invoke'}}
            if mode=='query_unknown':raise NS['Hold']('RPC_RESULT_UNKNOWN_NO_RETRY')
            return {'InvocationResult':{'InstanceId':NS['INSTANCE'],'InvokeId':'mock-invoke','InvocationStatus':'Success','ExitCode':0,'Output':'{}'}}
        NS['rpc']=rpc
        result=NS['main']()
        self.assertEqual(result,2);self.assertEqual(calls.count('RunCommand'),1)
        self.assertLess(order.index(('persist','INTENT_BEFORE_RUN_NO_RETRY')),order.index(('rpc','RunCommand')))
        if 'DescribeInvocationResult' in calls:
            self.assertLess(order.index(('persist','DISPATCHED_NO_RETRY')),order.index(('rpc','DescribeInvocationResult')))
        return calls
    def test_unknown_run_no_retry(self):self.assertNotIn('DescribeInvocationResult',self.fake_main('unknown'))
    def test_missing_invoke_no_retry(self):self.assertNotIn('DescribeInvocationResult',self.fake_main('missing'))
    def test_query_identity_mismatch_no_retry(self):self.fake_main('query_mismatch')
    def test_query_unknown_no_retry(self):self.fake_main('query_unknown')
    def test_terminal_bad_schema_no_retry(self):self.fake_main('schema')
    def test_bounded_poll_no_redispatch(self):
        with patch.object(time,'monotonic',side_effect=[0,0,181]),patch.object(time,'sleep'):
            self.fake_main('pending')
        self.assertEqual(NS['row']['reason'],'POLL_TIMEOUT_HOLD_NO_RETRY')
    def test_rpc_transport_error_one_attempt(self):
        with patch.object(urllib.request,'build_opener',side_effect=OSError('mock')) as opener:
            self.hold(lambda:NS['rpc'](NS['ENDPOINT'],'2020-06-01','RunCommand',('mock','mock','mock')),'RPC_RESULT_UNKNOWN_NO_RETRY')
            self.assertEqual(opener.call_count,1)
    def test_rpc_unknown_endpoint(self):
        self.hold(lambda:NS['rpc']('example.com','2020-06-01','RunCommand',('mock','mock','mock')),'RPC_ENDPOINT_ACTION')
    def test_terminal_validated(self):self.assertEqual(NS['validate'](self.detail('i','n'),'i','n')['state'],'ACCOUNT_CREATED_VERIFIED')
    def test_terminal_nonzero_exit(self):
        d=self.detail('i','n');d['ExitCode']=1;self.hold(lambda:NS['validate'](d,'i','n'),'REMOTE_NOT_SUCCESS')
    def test_terminal_wrong_nonce(self):self.hold(lambda:NS['validate'](self.detail('i','bad'),'i','n'),'OUTPUT_BINDING')
    def test_terminal_extra_output_field(self):
        d=self.detail('i','n');v=json.loads(d['Output']);v['secret']='mock';d['Output']=json.dumps(v);self.hold(lambda:NS['validate'](d,'i','n'),'OUTPUT_SCHEMA')
    def test_terminal_wrong_invoke(self):self.hold(lambda:NS['validate'](self.detail('wrong','n'),'i','n'),'RESULT_IDENTITY')
    def test_compressed_command_size_and_syntax_only(self):
        payload=zlib.decompress(base64.b64decode(NS['PAYLOAD_Z64']))
        script=NS['command'](payload,'0'*32)
        self.assertLessEqual(len(base64.b64encode(script.encode())),16384)
        # Parse only; never invoke the generated remote command.
        subprocess.run(['bash','-n'],input=script,text=True,check=True,capture_output=True)
        import shlex
        code=shlex.split(script.split('\n',2)[2])[-1];ast.parse(code)
        tree=ast.parse(code); packed=tree.body[1].value.args[0].args[0].value
        self.assertEqual(zlib.decompress(base64.b64decode(packed)),payload)
    def test_workflow_disarmed_and_no_checkout(self):
        self.assertIn('${{ false &&',YAML);self.assertIn('ARMED = False',SOURCE)
        self.assertNotIn('uses: actions/checkout',YAML);self.assertNotIn('pull_request_target:',YAML)
        self.assertIn('types: [labeled]',YAML)
if __name__=='__main__':unittest.main()

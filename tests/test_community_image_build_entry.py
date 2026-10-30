"""Execute actual workflow gate/conditions offline; no dispatch, Docker or I/O."""
import ast
import re
import textwrap
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'.github/workflows/chatgpt-community-wechat-sp-offline.yml'
BRANCH='refs/heads/feature/chatgpt-community-wechat-sp-offline-20261017'
HEAD='a'*40


def condition(expression,values):
    # Token-based evaluation of this workflow's simple GitHub boolean grammar.
    # Strings stay literal tokens, so messages never become executable code.
    tokens=re.findall(r"'(?:[^']*)'|\&\&|\|\||==|!=|!|[(),]|[A-Za-z_][A-Za-z0-9_.]*",expression)
    require=''.join(tokens)
    if re.sub(r'\s+','',expression)!=re.sub(r'\s+','',require):raise AssertionError('UNSUPPORTED_EXPRESSION')
    translated=[]
    for token in tokens:
        if token.startswith("'"):translated.append(repr(ast.literal_eval(token)))
        elif token in ('&&','||','!'):translated.append({'&&':'and','||':'or','!':'not'}[token])
        elif token in ('(',')',',','==','!=','contains'):translated.append(token)
        elif token in ('true','false'):translated.append('True' if token=='true' else 'False')
        else:translated.append(repr(values.get(token,'')))
    return bool(eval(' '.join(translated),{'__builtins__':{},'contains':lambda value,part:part in (value or '')}))


def exact_readonly_permissions(workflow):
    # Scan mapping-key tokens as well as line keys: YAML flow/quoted overrides
    # must not evade the exact top-level two-scope allowlist.
    token_pattern=r'''(?<![\w-])(?:permissions|"(?:[^"\\]|\\[\s\S])*"|'(?:[^']|'')*')\s*:'''
    blocks=[]
    for match in re.finditer(token_pattern,workflow):
        token=match.group().rsplit(':',1)[0].strip()
        try:key=ast.literal_eval(token) if token.startswith('"') else token[1:-1].replace("''", "'") if token.startswith("'") else token
        except (SyntaxError,ValueError):raise AssertionError('UNSUPPORTED_QUOTED_WORKFLOW_KEY')
        if key=='permissions':blocks.append(match)
    if len(blocks)!=1 or blocks[0].group()!='permissions:' or (blocks[0].start() and workflow[blocks[0].start()-1]!='\n'):
        raise AssertionError('ONE_TOP_LEVEL_PERMISSION_BLOCK_REQUIRED')
    block=workflow[blocks[0].start():].split('\njobs:',1)[0]
    if block!='permissions:\n  contents: read\n  actions: read':
        raise AssertionError('EXACT_CONTENTS_ACTIONS_READ_ONLY_REQUIRED')


class HostedImageEntry(unittest.TestCase):
    def setUp(self):
        self.workflow=PATH.read_text()
        code=textwrap.dedent(self.workflow.split("python - <<'EVIDENCE'\n",1)[1].split('          EVIDENCE',1)[0])
        self.ns={'__name__':'offline_image_entry'};exec(compile(code,'actual-evidence-gate','exec'),self.ns)
    def env(self,**changes):
        v=dict(IMAGE_BUILD_ENABLED='true',PREVIEW_ENABLED='false',IMAGE_SOURCE_SHA=HEAD,IMAGE_EVIDENCE_RUN_ID='101',
            GITHUB_SHA=HEAD,GITHUB_REF=BRANCH,GITHUB_REPOSITORY='huhongchuan0422-creator/Repository-name-xuanjun-ai-control')
        v.update(changes);return v
    def job(self,name):
        return self.workflow.split('  '+name+':\n',1)[1].split('    steps:',1)[0]
    def enabled(self,name,**changes):
        v={'github.event_name':'workflow_dispatch','github.ref':BRANCH,'github.sha':HEAD,
           'inputs.backend_image_enabled':True,'inputs.preview_enabled':False,'inputs.backend_image_source_sha':HEAD,
           'inputs.preview_source_sha':HEAD,'inputs.preview_target':'uk-path-candidate',
           'github.event.head_commit.message':''}
        v.update(changes);expr=self.job(name).split('    if: ',1)[1].splitlines()[0]
        return condition(expr,v)
    def test_explicit_image_context_accepts_only_its_own_exact_inputs(self):
        self.assertEqual(self.ns['validate_context'](self.env()),(HEAD,'101'))
        for change in ({'IMAGE_SOURCE_SHA':''},{'IMAGE_SOURCE_SHA':'b'*40},{'GITHUB_SHA':'A'*40},
                       {'GITHUB_REF':'refs/heads/main'},{'GITHUB_REPOSITORY':'other/repo'},
                       {'IMAGE_EVIDENCE_RUN_ID':''},{'IMAGE_EVIDENCE_RUN_ID':'01'},
                       {'IMAGE_BUILD_ENABLED':'false'},{'PREVIEW_ENABLED':'true'},
                       {'IMAGE_BUILD_ENABLED':'1'},{'IMAGE_BUILD_ENABLED':'True'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.ns['validate_context'](self.env(**change))
    def test_preview_values_cannot_fill_missing_image_values(self):
        with self.assertRaises(ValueError):self.ns['validate_context'](self.env(IMAGE_SOURCE_SHA='',IMAGE_EVIDENCE_RUN_ID='',PREVIEW_SOURCE_SHA=HEAD,PREVIEW_EVIDENCE_RUN_ID='101'))
    def test_original_preview_context_still_works_without_enabling_image(self):
        v=self.env(IMAGE_BUILD_ENABLED='false',PREVIEW_ENABLED='true',PREVIEW_SOURCE_SHA=HEAD,PREVIEW_EVIDENCE_RUN_ID='202',PREVIEW_TARGET='uk-path-candidate')
        self.assertEqual(self.ns['validate_context'](v),(HEAD,'202'))
        with self.assertRaises(ValueError):self.ns['validate_context']({**v,'PREVIEW_TARGET':'legacy'})
    def test_defaults_remain_disabled_and_existing_permissions_only(self):
        inputs=self.workflow.split('  workflow_dispatch:\n',1)[1].split('permissions:',1)[0]
        for name in ('backend_image_enabled','preview_enabled'):
            body=re.split(r'\n {6}[a-z_]+:',inputs.split('      '+name+':\n',1)[1],maxsplit=1)[0]
            self.assertIn('type: boolean',body);self.assertIn('default: false',body)
        exact_readonly_permissions(self.workflow)
        self.assertNotIn('actions: write',self.workflow)
    def test_permissions_reject_write_extra_scope_and_any_job_override(self):
        for changed in (
            self.workflow.replace('  actions: read','  actions: write',1),
            self.workflow.replace('  contents: read','  contents: write',1),
            self.workflow.replace('  actions: read','  actions: read\n  id-token: write',1),
            self.workflow.replace('  actions: read','  actions: read\n  packages: read',1),
            self.workflow.replace('  test:\n','  test:\n    permissions: {}\n',1),
            self.workflow.replace('  test:\n','  test:\n    "permissions": {contents: write}\n',1),
            self.workflow.replace('permissions:\n','"permissions":\n',1),
            self.workflow+'\n  inline_override: {permissions: {contents: write}, runs-on: ubuntu-latest, steps: [{run: "true"}]}\n',
            self.workflow+'\n  inline_override: {'+r'"\u0070ermissions": {contents: write}, runs-on: ubuntu-latest}'+'\n',

        ):
            with self.subTest(changed=changed[:70]),self.assertRaises(AssertionError):
                exact_readonly_permissions(changed)

    def test_image_job_requires_original_branch_exact_sha_explicit_true_and_test_gate(self):
        self.assertTrue(self.enabled('community-backend-image'))
        for change in ({'github.ref':'refs/heads/main'},{'inputs.backend_image_source_sha':'b'*40},
                       {'inputs.backend_image_enabled':False},{'inputs.backend_image_enabled':''},
                       {'inputs.preview_enabled':True},{'github.event_name':'pull_request'}):
            with self.subTest(change=change):self.assertFalse(self.enabled('community-backend-image',**change))
        header=self.job('community-backend-image');self.assertIn('needs: test',header)
        self.assertIn('runs-on: ubuntu-latest',header);self.assertIn('timeout-minutes: 12',header)
    def test_original_push_build_retained_without_dummy_push_requirement(self):
        self.assertTrue(self.enabled('community-backend-image',**{'github.event_name':'push','github.event.head_commit.message':'real change [community-image]'}))
        self.assertFalse(self.enabled('community-backend-image',**{'github.event_name':'push'}))
        self.assertFalse(self.enabled('community-backend-image',**{'github.event_name':'push','github.ref':'refs/heads/main','github.event.head_commit.message':'[community-image]'}))
    def test_image_dispatch_cannot_run_sdk_preview_or_any_runtime_even_with_conflicting_preview(self):
        for both in (False,True):
            for name in ('mini-sdk','mini-preview','mini-runtime','mini-python-runtime'):
                with self.subTest(name=name,both=both):self.assertFalse(self.enabled(name,**{'inputs.preview_enabled':both}))
    def test_image_dispatch_cannot_repeat_complete_old_regression_or_browser_install(self):
        for name in ('Complete Phase1 and Phase2 source regression','Install exact browser test runner'):
            step=self.workflow.split('      - name: '+name+'\n',1)[1].split('        run:',1)[0]
            expr=step.split('        if: ',1)[1].strip().strip('"')
            self.assertFalse(condition(expr,{'github.event_name':'workflow_dispatch','inputs.backend_image_enabled':True,'inputs.preview_enabled':False}))
        gate=self.workflow.split('      - name: Reuse exact successful push Hosted evidence before preview\n',1)[1].split('        env:',1)[0]
        self.assertIn('inputs.backend_image_enabled',gate)
    def test_no_secret_or_site_action_added_to_hosted_build(self):
        image=self.workflow.split('  community-backend-image:\n',1)[1].split('\n  mini-python-runtime:',1)[0]
        for token in ('secrets.','self-hosted','ssh ','scp ','workflow_dispatch','docker push','docker load','community_preview_upgrade.py'):
            if token=='workflow_dispatch':continue  # job-selection expression only
            self.assertNotIn(token,image)
        self.assertIn('docker build --network=none --target verify --build-arg SOURCE_SHA="$COMMUNITY_IMAGE_SOURCE_SHA"',image)
        self.assertIn('docker image save "community-preview:$COMMUNITY_IMAGE_SOURCE_SHA"',image)
        self.assertIn("manifest['purpose']=='OFFLINE_SOURCE_CANDIDATE_NOT_INSTALLABLE'",image)
    def test_evidence_validate_still_requires_exact_push_and_unique_live_artifact(self):
        # The complete actual validator negative matrices run in HostedEvidence.
        names=set(self.ns['validate'].__code__.co_consts)
        for token in ('EXACT_SUCCESSFUL_PUSH_EVIDENCE_REQUIRED','ONE_SOURCE_ARTIFACT_REQUIRED','UNEXPIRED_EXACT_SOURCE_ARTIFACT_REQUIRED'):
            self.assertIn(token,names)

    def test_original_ocr_download_id_keeps_named_directory_and_exact_validator_path(self):
        import shlex
        download=self.workflow.split('      - name: Read original successful PR139 offline OCR artifact (no rebuild)\n',1)[1].split('      - name:',1)[0]
        self.assertIn('uses: actions/download-artifact@v4',download)
        self.assertIn("artifact-ids: '12553737114'",download)
        self.assertIn("run-id: '40076963020'",download)
        self.assertIn('path: original-ocr-evidence',download)
        self.assertNotIn('merge-multiple: true',download)
        step=self.workflow.split('      - name: Verify fixed original OCR bundle and preserve community vendor pins\n',1)[1].split('      - name:',1)[0]
        command=shlex.split(step.split('        run: |\n',1)[1].strip())
        # download-artifact with artifact-ids and the default merge=false keeps
        # the exact original artifact name, even when there is only one match.
        name='xuanjun-ocr-linux-x86_64-cp311-cb28f605291cde6dc48a2d6431166211059dc595'
        expected=Path('original-ocr-evidence')/name/'xuanjun-ocr-linux-x86_64-cp311.tar.gz'
        self.assertEqual(command,['python','community-image-context/scripts/community_ocr_image_inputs.py',str(expected),'community-image-context/ocr-runtime'])

    def test_missing_original_ocr_bundle_rejects_before_destination_write(self):
        import tempfile
        from scripts.community_ocr_image_inputs import prepare
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);destination=root/'ocr-runtime'
            with self.assertRaisesRegex(ValueError,'ORIGINAL_OCR_BUNDLE_REQUIRED'):
                prepare(root/'original-ocr-evidence/xuanjun-ocr-linux-x86_64-cp311.tar.gz',destination)
            self.assertFalse(destination.exists())

    def test_evidence_errors_expose_only_fixed_codes_not_provider_content(self):
        from urllib.error import HTTPError,URLError
        import json
        sentinel='DO_NOT_PRINT_PRIVATE_RESPONSE_OR_TOKEN'
        cases=[(HTTPError('https://api.github.com/'+sentinel,403,sentinel,{},None),'HTTP_403'),
               (URLError(sentinel),'NETWORK_ERROR'),(TimeoutError(sentinel),'NETWORK_TIMEOUT'),
               (json.JSONDecodeError(sentinel,sentinel,0),'INVALID_JSON'),
               (ValueError('SUCCESSFUL_TEST_GATE_REQUIRED'),'SUCCESSFUL_TEST_GATE_REQUIRED'),
               (ValueError(sentinel),'UNCLASSIFIED_ERROR'),(RuntimeError(sentinel),'UNCLASSIFIED_ERROR')]
        for error,expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self.ns['safe_error'](error),expected)
                self.assertNotIn(sentinel,self.ns['safe_error'](error))

    def test_evidence_reader_preserves_anonymous_fixed_origin_and_bounds(self):
        from unittest.mock import patch
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return 'https://api.github.com/repos/'+self_repo+'/actions/runs/101'
            def read(self,size):
                self_size.append(size)
                return b'{"id":101}'
        self_repo='huhongchuan0422-creator/Repository-name-xuanjun-ai-control'
        self_size=[];seen=[]
        class Opener:
            def open(self,request,timeout):
                seen.append((request,timeout));return Response()
        with patch.dict(self.ns,build_opener=lambda *args:Opener()):
            self.assertEqual(self.ns['read']('/actions/runs/101'),{'id':101})
        self.assertEqual(self_size,[1048577]);self.assertEqual(seen[0][1],10)
        self.assertFalse(any(key.lower()=='authorization' for key in seen[0][0].headers))
        self.assertEqual(self.ns['NoRedirect']().redirect_request(None,None,None,None,None,None),None)

    def test_main_failure_reports_stage_and_never_writes_success_receipt(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        code=textwrap.dedent(self.workflow.split("python - <<'EVIDENCE'\n",1)[1].split('          EVIDENCE',1)[0])
        main=code.split("if __name__=='__main__':\n",1)[1]
        values={**self.env(), 'GITHUB_RUN_ID':'102'}
        for stage,reads in [('RUN',0),('JOBS',1),('ARTIFACTS',2)]:
            seen=[]
            def read(path):
                if len(seen)==reads:raise HTTPError('https://api.github.com/private',403,'secret',{},None)
                seen.append(path);return {}
            with patch.dict(self.ns,read=read),patch.dict(self.ns['os'].environ,values,clear=True),patch('builtins.open') as output:
                with self.assertRaises(SystemExit) as caught:exec(compile(textwrap.dedent(main),'actual-main','exec'),self.ns)
                self.assertEqual(str(caught.exception),'HOSTED_EVIDENCE_NOT_VERIFIED_NO_PREVIEW:'+stage+':HTTP_403')
                output.assert_not_called()


class FixedProductImage(unittest.TestCase):
    """Exact original archived bytes replace only missing list steps, never failure."""
    def setUp(self):
        import tempfile,hashlib,copy
        entry=HostedImageEntry();entry.setUp();self.entry=entry;self.ns=entry.ns
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        # Synthetic byte fixtures only. Actual pinned artifacts are independently
        # exercised by the local real-artifact proof; production pins remain literal.
        self.original_pins=dict(self.ns['FIXED_MEMBERS'])
        self.ns['FIXED_MEMBERS']={}
        for name in self.original_pins:
            raw=('SYNTHETIC ONLY '+name).encode();(self.root/name).write_bytes(raw)
            self.ns['FIXED_MEMBERS'][name]=(len(raw),hashlib.sha256(raw).hexdigest())
        self.run=dict(id=self.ns['FIXED_RUN'],head_sha=self.ns['FIXED_PRODUCT'],
            head_branch=self.ns['BRANCH'],path=self.ns['WORKFLOW'],event='push',
            status='completed',conclusion='success',repository={'full_name':self.ns['REPO']},
            head_repository={'full_name':self.ns['REPO']})
        self.jobs=dict(total_count=1,jobs=[dict(id=self.ns['FIXED_JOB'],name='test',
            run_id=self.ns['FIXED_RUN'],head_sha=self.ns['FIXED_PRODUCT'],
            status='completed',conclusion='success',steps=[])])
        self.artifacts=dict(total_count=1,artifacts=[dict(id=13000357097,
            name='community-phase-integration-evidence',expired=False,expires_at='2030-01-01T00:00:00Z',
            size_in_bytes=13028520,digest='sha256:b6c49a917abe9bb07683ad41b9b98d2975a79a0be8e6f59714db05debf8c0560',
            workflow_run=dict(id=self.ns['FIXED_RUN'],head_sha=self.ns['FIXED_PRODUCT'],
                head_branch=self.ns['BRANCH'],repository_id=1413132159,head_repository_id=1413132159))])
    def validate(self,**changes):
        import time
        args=dict(run=self.run,jobs=self.jobs,artifacts=self.artifacts,head=self.ns['FIXED_PRODUCT'],
            evidence_id=self.ns['FIXED_RUN'],current_id=99999999999,now=time.time(),fixed_inputs=self.root)
        args.update(changes);return self.ns['validate'](**args)
    def test_exact_fixed_source_preserves_separate_control_and_build(self):
        env=self.entry.env(IMAGE_SOURCE_SHA=self.ns['FIXED_PRODUCT'],IMAGE_EVIDENCE_RUN_ID=str(self.ns['FIXED_RUN']))
        self.assertEqual(self.ns['validate_context'](env),(self.ns['FIXED_PRODUCT'],str(self.ns['FIXED_RUN'])))
        self.assertEqual(env['GITHUB_SHA'],HEAD)
        self.assertTrue(self.entry.enabled('community-backend-image',**{
            'inputs.backend_image_source_sha':self.ns['FIXED_PRODUCT'],
            'inputs.backend_image_evidence_run_id':str(self.ns['FIXED_RUN'])}))
        self.assertFalse(self.entry.enabled('community-backend-image',**{
            'inputs.backend_image_source_sha':self.ns['FIXED_PRODUCT'],
            'inputs.backend_image_evidence_run_id':'101'}))
        self.assertIn('cp --no-clobber fixed-4f-evidence/community-stage-source.zip community-stage-source.zip',self.entry.workflow)
        self.assertNotIn('GITHUB_SHA=',self.entry.job('community-backend-image'))
    def test_absent_steps_requires_exact_successful_original_bytes(self):
        value=self.validate();self.assertTrue(value['fixed_payload_bytes_reverified'])
        self.assertFalse(value['artifact_bytes_reverified'])
        self.assertEqual(value['source_package'],'VERIFIED_FIXED_4F_ARCHIVE')
        with self.assertRaises(ValueError):self.validate(fixed_inputs=None)
    def test_missing_changed_and_symlinked_original_bytes_rejected(self):
        for name in self.original_pins:
            path=self.root/name;raw=path.read_bytes()
            path.unlink()
            with self.assertRaises((ValueError,OSError)):self.validate()
            path.write_bytes(raw+b'wrong')
            with self.assertRaises(ValueError):self.validate()
            path.unlink();path.symlink_to(self.root/'absent')
            with self.assertRaises(ValueError):self.validate()
            path.unlink();path.write_bytes(raw)
    def test_failed_skipped_unknown_steps_cannot_use_original_bytes(self):
        import copy
        for status in ('failure','skipped','cancelled',None):
            jobs=copy.deepcopy(self.jobs)
            jobs['jobs'][0]['steps']=[dict(name='Complete Phase1 and Phase2 source regression',status='completed',conclusion=status)]
            with self.subTest(status=status),self.assertRaises(ValueError):self.validate(jobs=jobs)
        jobs=copy.deepcopy(self.jobs);jobs['jobs'][0].pop('steps')
        with self.assertRaises(ValueError):self.validate(jobs=jobs)
    def test_wrong_job_run_commit_and_artifact_rejected(self):
        import copy
        for field,value in [('id',1),('conclusion','skipped'),('status','queued'),('name','other'),('run_id',1),('head_sha',HEAD)]:
            jobs=copy.deepcopy(self.jobs);jobs['jobs'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(jobs=jobs)
        for field,value in [('head_sha',HEAD),('conclusion','failure'),('event','workflow_dispatch')]:
            run=copy.deepcopy(self.run);run[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(run=run)
        for field,value in [('id',1),('digest','sha256:'+'0'*64),('expired',True),('size_in_bytes',1)]:
            artifacts=copy.deepcopy(self.artifacts);artifacts['artifacts'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.validate(artifacts=artifacts)
    def test_arbitrary_source_still_cannot_use_missing_steps(self):
        with self.assertRaises(ValueError):
            self.ns['validate_context'](self.entry.env(IMAGE_SOURCE_SHA='b'*40,IMAGE_EVIDENCE_RUN_ID=str(self.ns['FIXED_RUN'])))
        with self.assertRaises(ValueError):self.validate(head=HEAD)

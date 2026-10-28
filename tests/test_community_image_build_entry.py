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
        self.assertIn('docker build --network=none --target verify --build-arg SOURCE_SHA="$GITHUB_SHA"',image)
        self.assertIn('docker image save "community-preview:$GITHUB_SHA"',image)
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

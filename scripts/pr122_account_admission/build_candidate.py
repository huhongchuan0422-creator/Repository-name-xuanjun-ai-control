"""Offline deterministic packaging. Does not execute either host caller or transport."""
import ast, base64, hashlib, json, pathlib, zlib
HERE=pathlib.Path(__file__).resolve().parent
OLD=HERE.parent/'pr122_account_preparation'
workflow=(OLD/'transport-candidate.yml').read_text()
assert hashlib.sha256(workflow.encode('utf-8')).hexdigest()=='c0db7caa615abee1b5cc2db973ea889a507f1317a3edc411bfee873e7da27e2f'
start="          python3 - <<'PY'\n"
end="          PY\n"
assert workflow.count(start)==1 and workflow.count(end)==1
prefix_before, body=workflow.split(start,1)
inline, _=body.split(end,1)
assert all(line.startswith('          ') for line in inline.splitlines())
source=''.join(line[10:]+'\n' for line in inline.splitlines())
workflow_prefix=prefix_before+start
raw=(HERE/'approved_account_prepare.py').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818'
caller=(HERE/'readonly_probe.py').read_bytes()
bundle=json.dumps({'approved':raw.decode('utf-8'),'caller':caller.decode('utf-8')},sort_keys=True,separators=(',',':')).encode()
sha=hashlib.sha256(bundle).hexdigest()
tree=ast.parse(source)
# Copy reviewed helpers verbatim; do not import or execute the old main/command.
functions=('need','persist','github','gate','quote','rpc')
pieces=[ast.get_source_segment(source,n) for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
for n in tree.body:
    if isinstance(n,ast.Assign):
        name=n.targets[0].id if isinstance(n.targets[0],ast.Name) else ''
        if name in ('PAYLOAD_SHA','PAYLOAD_Z64','row'):continue
        text=ast.get_source_segment(source,n)
        text=text.replace('aliyun-account-prepare-once-20261017.yml','aliyun-account-readonly-admission-once-20261017.yml').replace('xuanjun-account-prepare-once-20261017-','xj-ro-').replace("Path('account-prepare-receipt.json')","Path('readonly-admission-evidence.json')")
        pieces.append(text)
    if isinstance(n,ast.ClassDef):pieces.append(ast.get_source_segment(source,n))
pieces += [f'PAYLOAD_SHA = {sha!r}',f'PAYLOAD_Z64 = {base64.b64encode(zlib.compress(bundle,9)).decode()!r}',f'CALLER_SHA = {hashlib.sha256(caller).hexdigest()!r}',"EXECUTION_ADMISSION = False", "EXPECTED_WORKFLOW_REF = REPO + '/' + WORKFLOW_PATH + '@refs/pull/122/merge'", "row = {'schema':1,'status':'HOLD','stage':'GATE','retry_allowed':False,'purpose':'READONLY_ADMISSION','payload_sha256':PAYLOAD_SHA}"]
pieces += [ast.get_source_segment(source,n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in functions]
pieces.append((HERE/'permit_gate.py').read_text())
pieces.append((HERE/'transport_delta.py.txt').read_text())
transport='\n\n'.join(pieces)+'\n'
(HERE/'readonly_transport.py').write_text(transport)
prefix=workflow_prefix.replace('Alibaba Cloud account preparation once','Alibaba Cloud read-only admission once').replace('xuanjun-domestic-account-prepare-once','xuanjun-domestic-account-readonly-admission-once').replace('prepare-account-once:','readonly-admission-once:').replace('xuanjun-account-prepare-once-20261017-','xj-ro-').replace('Fixed reviewed account-only transport','Fixed reviewed read-only admission transport')
suffix="""          PY
      - name: Preserve sanitized read-only evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02
        with:
          name: readonly-admission-evidence-${{ github.run_id }}-${{ github.run_attempt }}
          path: readonly-admission-evidence.json
          if-no-files-found: error
          retention-days: 90
          overwrite: false
"""
# Admission step has no Alibaba credentials. Cloud step cannot run until the
# protected durable reservation succeeds; it independently rechecks/claims it.
inline=''.join('          '+line+'\n' for line in transport.splitlines())
first=prefix.replace('      - name: Fixed reviewed read-only admission transport', '      - name: Verify and consume protected independent permit\n        id: admission').replace('          ALIYUN_ACCESS_KEY_ID: ${{ secrets.ALIYUN_ACCESS_KEY_ID }}\n','').replace('          ALIYUN_ACCESS_KEY_SECRET: ${{ secrets.ALIYUN_ACCESS_KEY_SECRET }}\n','').replace('        env:\n','        env:\n          ADMISSION_PHASE: ADMIT\n')
second=prefix[prefix.index('      - name: Fixed reviewed read-only admission transport'):].replace('      - name: Fixed reviewed read-only admission transport','      - name: Execute admitted fixed read-only transport\n        if: ${{ steps.admission.outputs.ready == \'true\' }}').replace('        env:\n','        env:\n          ADMISSION_PHASE: EXECUTE\n')
(HERE/'readonly-transport-candidate.yml').write_text(first+inline+'          PY\n'+second+inline+suffix)

(HERE/'bundle.json').write_bytes(bundle)
print(json.dumps({'bundle_sha256':sha,'caller_sha256':hashlib.sha256(caller).hexdigest(),'approved_bytes':len(raw)},sort_keys=True))

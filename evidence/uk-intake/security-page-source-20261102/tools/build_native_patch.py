"""Offline pinned-public-source patch builder. Never touches installed OpenClaw."""
from pathlib import Path
import hashlib,json,difflib,shutil
ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=Path('/workspace/shared/safe-input-original-runtime/package/dist')
OUT=ROOT/'patched-source'; OUT.mkdir(exist_ok=True)
changes=[]
def patch(name,fn):
 src=(ROOT/'original-source'/name) if (ROOT/'original-source'/name).exists() else ORIGINAL/name
 before=src.read_text();after=fn(before)
 if before==after:raise AssertionError('NO_CHANGE '+name)
 (OUT/name).write_text(after)
 changes.append({'path':name,'original_sha256':hashlib.sha256(before.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(after.encode()).hexdigest()})
 return ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
def replace(s,a,b):
 if s.count(a)!=1:raise AssertionError('ANCHOR_COUNT '+a[:100])
 return s.replace(a,b)
def handler(s):
 s='import { isAcceptanceQuestions } from "./acceptance_questions.mjs";\n'+s
 s=replace(s,'function createQuestionHandlers(manager, storeWriteService, scheduler) {','function createQuestionHandlers(manager, storeWriteService, scheduler, acceptanceBridge) {')
 s=replace(s,'const record = manager.request(managerRequest);','''if (isAcceptanceQuestions(managerRequest.questions) && (!acceptanceBridge || managerRequest.timeoutMs !== 600000)) {
                        respond(false, void 0, errorShape(ErrorCodes.INVALID_REQUEST, "Acceptance request requires its native durable adapter and 600-second expiry."));
                        return;
                    }
                    const record = manager.request(managerRequest);
                    if (isAcceptanceQuestions(record.questions)) try {
                        acceptanceBridge.register(record, client, authority.assertCurrent);
                    } catch {
                        manager.cancel(record.id, "acceptance-registration-unconfirmed");
                        respond(false, void 0, errorShape(ErrorCodes.UNAVAILABLE, "Acceptance request registration is unconfirmed; do not recreate or submit secrets."));
                        return;
                    }''')
 s=replace(s,'if ("cancel" in request) {\n\t\t\t\t\t\trespond(true, manager.cancel', '''if ("cancel" in request) {
                        if (isAcceptanceQuestions(question.questions)) try {
                            acceptanceBridge.cancel(question, client, authorize.assertCurrent);
                        } catch {
                            respond(false, void 0, errorShape(ErrorCodes.UNAVAILABLE, "Acceptance cancellation is unconfirmed; query the original request."));
                            return;
                        }
                        respond(true, manager.cancel''')
 s=replace(s,'const secretQuestion = question.questions[0];','''if (isAcceptanceQuestions(question.questions)) {
                        try { reload = acceptanceBridge.resolve(question, client, request, authorize.assertCurrent); }
                        catch { respond(false, void 0, errorShape(ErrorCodes.UNAVAILABLE, "Acceptance submission is unconfirmed or rejected; query the original request, do not resubmit.")); }
                        return;
                    }
                    const secretQuestion = question.questions[0];''')
 s=replace(s,'await storeWriteService.reloadReference(reload.name);','for (const name of (reload.names ?? [reload.name])) await storeWriteService.reloadReference(name);')
 anchor='const selected = prepareSelectedQuestion(options, params.id, "read");'
 fallback='''// Durable metadata fallback: never fabricate a live manager observation.
            if (!manager.get(params.id) && acceptanceBridge && !usesOwnRunQuestionAccess(options.client)) {
                const authority = readGatewayRequestMutationAuthority(options);
                authority.assertCurrent();
                const persisted = acceptanceBridge.persistedRecord(params.id);
                if (persisted) {
                    await withPreparedQuestionSessions(options, [persisted], ([prepared]) => {
                        authority.assertCurrent();
                        if (!isGatewayAdmin(options.client) && hasOperatorBoundary(options.client, options.context.getRuntimeConfig()) &&
                            !prepared?.canAccess(options.client, "read", false)) {
                            respond(false, void 0, questionNotFound(params.id)); return;
                        }
                        respond(true, {question:persisted}, void 0);
                    }, {assertCurrent:authority.assertCurrent});
                    return;
                }
            }
            '''+anchor
 s=replace(s,anchor,fallback)
 s=replace(s,'respond(true, { question: observation.record }, void 0);','const committed = isAcceptanceQuestions(observation.record.questions) ? acceptanceBridge?.persistedRecord(params.id) : null;\n                respond(true, { question: committed?.status === \"answered\" ? committed : observation.record }, void 0);')
 return s
def validation(s):
 s='import { isAcceptanceQuestions } from "./acceptance_questions.mjs";\n'+s
 return replace(s,'if (questions.length !== 1 || question.options.length !== 0 || question.multiSelect)', 'if ((questions.length !== 1 && !isAcceptanceQuestions(questions)) || question.options.length !== 0 || question.multiSelect)')
def composer(s):
 return replace(s,'return createQuestionHandlers(questionManager, storeWriteService, params.scheduler);','''const [{createGatewayAcceptanceBridge}, state, readonly, store, redaction, receipt] = await Promise.all([
            import("./gateway_acceptance_bridge.mjs"), import("./openclaw-state-db-Dh2awMJ8.mjs"),
            import("./openclaw-state-db-readonly-BUOubhzc.mjs"), import("./secret-store-CuSJMUWv.mjs"),
            import("./redact-Bw4Oqcda.mjs"), import("./receipt_schema.mjs")
        ]);
        const acceptanceBridge = createGatewayAcceptanceBridge({manager:questionManager,
            runWriteTransaction:state.l, withReadSnapshot:readonly.f,
            writeSecretStoreEntries:store.l,
            resolveUpdatedBy:client=>storeWriteService.resolveUpdatedBy(client),
            registerRedaction:redaction.registerSecretValueForRedaction,
            ensureReceiptSchema:receipt.ensureAcceptanceReceiptSchema
        });
        return createQuestionHandlers(questionManager, storeWriteService, params.scheduler, acceptanceBridge);''')
# Composer redaction import is resolved from original handler's exact alias below.
original_handler=(ROOT/'original-source'/'question-2U20Yooq.mjs').read_text()
import re
redaction=re.search(r'import \{ ([^}]+) \} from "(\./[^\"]+)";',original_handler)
redline=next(line for line in original_handler.splitlines() if ' as registerSecretValueForRedaction ' in line)
redmod=re.search(r'from "([^"]+)"',redline).group(1)
redalias=re.search(r'(\w+) as registerSecretValueForRedaction',redline).group(1)
def actual_composer(s):
 return composer(s).replace('./redact-Bw4Oqcda.mjs',redmod).replace('redaction.registerSecretValueForRedaction','redaction.'+redalias)
diff=''
for name,fn in [('question-validation-C3R346Mf.mjs',validation),('question-2U20Yooq.mjs',handler),('server-aux-handlers-ZAnivsB0.mjs',actual_composer)]:diff+=patch(name,fn)
def contract(s):return replace(s,'\t"secret_store_entries",','\t"secret_store_entries",\n\t"safe_input_request_receipts",')
diff+=patch('openclaw-state-db-contract-CQDemVBb.mjs',contract)
# Schema SQL shares the exact receipt definition with transaction-time first-use.
sql=re.search(r'export const MIGRATION_SQL\s*=\s*`([\s\S]*?)`', (ROOT/'durable_receipt_adapter.mjs').read_text()).group(1)
def canonical(s):
 # Original canonical SQL is a JSON-compatible quoted literal in this fixed build.
 m=re.search(r'const OPENCLAW_STATE_SCHEMA_SQL = ("(?:[^"\\]|\\.)*");',s)
 if not m:raise AssertionError('SCHEMA_SQL_ANCHOR')
 value=json.loads(m.group(1))+'\n'+sql+'\n'
 return s[:m.start(1)]+json.dumps(value,ensure_ascii=False)+s[m.end(1):]
diff+=patch('openclaw-state-db-legacy-backfills-BSKqroDt.mjs',canonical)
(ROOT/'native-framework.patch').write_text(diff)
(ROOT/'NATIVE_PATCH_MANIFEST.json').write_text(json.dumps(changes,indent=2)+'\n')
print('PATCHED_FILES',len(changes))
# Native Control UI same component/client, not a second web service/auth layer.
ui=ROOT/'original-source'/'ui';uiout=OUT/'control-ui'/'assets';uiout.mkdir(parents=True,exist_ok=True)
def uipatch(name,fn):
 global diff
 before=(ui/name).read_text();after=fn(before)
 (uiout/name).write_text(after)
 changes.append({'path':'control-ui/assets/'+name,'original_sha256':hashlib.sha256(before.encode()).hexdigest(),'candidate_sha256':hashlib.sha256(after.encode()).hexdigest()})
 diff+=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/control-ui/assets/'+name,tofile='b/control-ui/assets/'+name))
def submit_ui(s):
 start=s.index('function Mu(');end=s.index('function ',start+10)
 original=s[start:end]
 needle='},a=t[0]?.secretStore?t[0]:void 0'
 replacement='};if(isCommunityAcceptanceBundle(t))return{requestParams:{id:e,answers:i},submittedAnswers:{answers:Object.fromEntries(t.map(q=>[q.questionId,[`stored`]]))}};let a=t[0]?.secretStore?t[0]:void 0'
 if needle not in original:raise AssertionError('UI_SUBMIT_ANCHOR')
 out='import{isAcceptanceQuestions as isCommunityAcceptanceBundle}from"./acceptance-signature.js";\n'+s[:start]+original.replace(needle,replacement)+s[end:]
 return replace(out,'if(!r||r.status!==`pending`||r.submitting)return;', 'if(!r||r.status!==`pending`||r.submitting||isCommunityAcceptanceBundle(r.questions)&&r.error)return;')
def render_ui(s):
 needle=':G;return this.collapsed?H`'
 branch=''' :G;if(isCommunityAcceptanceBundle(t.questions))return H`
      <section class="chat-question-panel" role="group" aria-label="社区后台验收账号安全输入"
        style="box-sizing:border-box;width:100%;max-width:100%;padding-bottom:env(safe-area-inset-bottom)">
        <h1>社区后台验收账号安全输入</h1>
        <p>此请求 10 分钟到期，只能提交一次。请勿在聊天中发送账号或密码。</p>
        <p>凭据保存到现有 Protected Store；输入链接过期不删除凭据。当前禁止对外使用，浏览器授权接线完成后才能验收。</p>
        ${t.questions.map(q=>H`<div style="min-width:0;scroll-margin-bottom:6rem">
          <h2>${q.header}</h2>
          ${q.secretStoreExisting?H`<p role="note">提交将更新已有同名凭据。</p>`:G}
          ${Bm({question:q,value:t.drafts.get(q.questionId)?.freeText??``,selected:!!t.drafts.get(q.questionId)?.freeText,disabled:r,onInput:v=>this.setFreeText(t,q,v)})}
        </div>`)}
        ${t.error?H`<p role="alert">提交状态未确认或已被拒绝。请刷新查询原请求，不要重复提交或新建链接。</p><button type="button" style="min-height:48px" @click=${()=>this.dispatchEvent(new CustomEvent(`acceptance-recheck`,{bubbles:!0,composed:!0}))}>查询原请求</button>`:G}
        <button type="button" style="min-height:48px;width:100%;margin-top:16px"
          ?disabled=${r||!!t.error||!t.questions.every(q=>this.answerValues(t,q).length>0)}
          @click=${()=>this.resolve(t,`submit`)}>安全提交</button>
        <button type="button" style="min-height:48px;width:100%;margin-top:8px"
          ?disabled=${r||!!t.error} @click=${()=>this.resolve(t,`skip`)}>取消此请求</button>
      </section>`;return this.collapsed?H`'''
 if s.count(needle)!=1:raise AssertionError('UI_RENDER_ANCHOR')
 return 'import{isAcceptanceQuestions as isCommunityAcceptanceBundle}from"./acceptance-signature.js";\n'+s.replace(needle,branch)
uipatch('control-ui-boot-shared-_B6VNra2.js',submit_ui)
uipatch('control-ui-boot-shared-mtfVQ24Y.js',render_ui)
(uiout/'acceptance-signature.js').write_text((ROOT/'acceptance_questions.mjs').read_text())
(ROOT/'native-framework.patch').write_text(diff)
(ROOT/'NATIVE_PATCH_MANIFEST.json').write_text(json.dumps(changes,indent=2)+'\n')
print('NATIVE_PATCH_TOTAL',len(changes),'NEW_UI_ASSET',1)
# Exact native Store revision: opaque non-secret version, not timestamp/value hash.
def revision_store(s):
 s='import {randomUUID as createSecretRevision} from "node:crypto";\n'+s
 count=s.count('updated_at_ms: now')
 if count!=6:raise AssertionError('STORE_MUTATION_COUNT '+str(count))
 return s.replace('updated_at_ms: now','updated_at_ms: now, revision_token: createSecretRevision()')
diff+=patch('secret-store-CuSJMUWv.mjs',revision_store)
def revision_schema(s):
 return replace(s,'ensureColumn(database, "secret_store_entries", "allowed_hosts TEXT");','ensureColumn(database, "secret_store_entries", "allowed_hosts TEXT");\n    ensureColumn(database, "secret_store_entries", "revision_token TEXT");')
diff+=patch('openclaw-state-db-schema-additive-DAFjL3MG.mjs',revision_schema)
# Canonical new installs share nullable metadata column; old entries require an
# ordinary authorized update before new consumer use, no automatic secret rewrite.
name='openclaw-state-db-legacy-backfills-BSKqroDt.mjs';before=(OUT/name).read_text()
m=re.search(r'const OPENCLAW_STATE_SCHEMA_SQL = ("(?:[^"\\]|\\.)*");',before);value=json.loads(m.group(1))
start=value.index('CREATE TABLE IF NOT EXISTS secret_store_entries');end=value.index(';',start)
segment=value[start:end]
if segment.count('allowed_hosts TEXT')!=1:raise AssertionError('STORE_CANONICAL_COLUMN')
segment=segment.replace('allowed_hosts TEXT','revision_token TEXT,\n  allowed_hosts TEXT')
value=value[:start]+segment+value[end:];after=before[:m.start(1)]+json.dumps(value,ensure_ascii=False)+before[m.end(1):];(OUT/name).write_text(after)
# Rebuild final diff from originals to avoid stacked conflicting hunks.
diff=''
for item in changes:
 name=item['path'];candidate=OUT/name
 if name.startswith('control-ui/assets/'):original=ui/Path(name).name
 else:original=(ROOT/'original-source'/name) if (ROOT/'original-source'/name).exists() else ORIGINAL/name
 b=original.read_text();a=candidate.read_text();item['candidate_sha256']=hashlib.sha256(a.encode()).hexdigest()
 diff+=''.join(difflib.unified_diff(b.splitlines(True),a.splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(ROOT/'native-framework.patch').write_text(diff);(ROOT/'NATIVE_PATCH_MANIFEST.json').write_text(json.dumps(changes,indent=2)+'\n')
print('WITH_STORE_REVISION_PATCHES',len(changes))

# Recheck uses the ORIGINAL page client and keeps local uncertain/error state until
# the original request returns a confirmed terminal outcome. No second resolve.
def page_recheck(s):
 return replace(s,'<openclaw-chat-question-panel .props=${t}></openclaw-chat-question-panel>', '<openclaw-chat-question-panel .props=${t} @acceptance-recheck=${()=>this.client&&this.loadQuestion(this.client)}></openclaw-chat-question-panel>')
uipatch('question-page-registration-Ci9YglNL.js',page_recheck)
(ROOT/'native-framework.patch').write_text(diff);(ROOT/'NATIVE_PATCH_MANIFEST.json').write_text(json.dumps(changes,indent=2)+'\n')
print('FINAL_NATIVE_PATCH_FILES',len(changes))

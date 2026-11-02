/** Static original-source fences + executed original shape validator. Not Gateway. */
import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';import {buildAcceptanceRequest,isAcceptanceQuestions} from '../acceptance_questions.mjs';
import {ensureAcceptanceReceiptSchema} from '../receipt_schema.mjs';
let checks=0;const check=b=>{assert.ok(b);checks++;};
const read=n=>fs.readFileSync(new URL('../patched-source/'+n,import.meta.url),'utf8');
const v=read('question-validation-C3R346Mf.mjs');const body=v.slice(v.indexOf('function questionShapeError'),v.indexOf('//#endregion'));
const shape=vm.runInNewContext(body+';questionShapeError',{isAcceptanceQuestions,ENV_SECRET_REF_ID_RE:/^[A-Z][A-Z0-9_]*$/,Set});
const questions=buildAcceptanceRequest('test').questions;check(shape(questions,{})===undefined);
const wrong=structuredClone(questions);wrong[0].secretStore.reason='other';check(typeof shape(wrong,{})==='string');
check(shape([questions[0]],{})===undefined); // Retain ORIGINAL single-secret behavior.
const h=read('question-2U20Yooq.mjs');check(h.includes('authorize.authorize(prepared)'));check(h.includes('acceptanceBridge.resolve(question, client, request, authorize.assertCurrent)'));
check(h.includes('committed?.status === "answered" ? committed : observation.record'));
check(h.includes('!usesOwnRunQuestionAccess(options.client)'));check(h.includes('prepared?.canAccess(options.client, "read", false)'));
check(h.includes('managerRequest.timeoutMs !== 600000'));check(h.includes('for (const name of (reload.names ?? [reload.name]))'));
const source=read('openclaw-state-db-legacy-backfills-BSKqroDt.mjs');const literal=source.match(/const OPENCLAW_STATE_SCHEMA_SQL = ("(?:[^"\\]|\\.)*");/)[1];
const schema=JSON.parse(literal);const receipt=schema.slice(schema.lastIndexOf('CREATE TABLE IF NOT EXISTS safe_input_request_receipts'));
const db=new DatabaseSync(':memory:');db.exec(receipt);ensureAcceptanceReceiptSchema(db);check(true);db.close();
const compose=read('server-aux-handlers-ZAnivsB0.mjs');check(compose.includes('withReadSnapshot:readonly.f'));check(compose.includes('ensureReceiptSchema:receipt.ensureAcceptanceReceiptSchema'));
console.log(JSON.stringify({checks,status:'PASS',scope:'static native fences + actual validator + SQLite receipt DDL',fullGateway:false}));

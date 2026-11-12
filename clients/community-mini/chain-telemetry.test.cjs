'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {SUBMIT_STAGES,OCR_STAGES,SUBMIT_READBACK_COOLDOWN_MS,errorBucket,shortCorrelation,createChainTelemetry,shouldBlockResubmit,readbackReconciled,classifyOcrEmptyResponse}=require('./chain-telemetry');

test('chain stage codes: 6段提交链与5段OCR链码固定白名单',()=>{
 assert.deepEqual([...SUBMIT_STAGES],['SUBMIT_01','SUBMIT_02','SUBMIT_03','SUBMIT_04','SUBMIT_05','SUBMIT_06']);
 assert.deepEqual([...OCR_STAGES],['OCR_01','OCR_02','OCR_03','OCR_04','OCR_05']);
 assert.equal(SUBMIT_READBACK_COOLDOWN_MS,300000);
});

test('shortCorrelation: SHA256 32hex 截 16；非 hex/正文一律拒绝',()=>{
 assert.equal(shortCorrelation('A1B2C3D4E5F607182736455A6B7C8D9E'),'a1b2c3d4e5f60718');
 assert.equal(shortCorrelation('a'.repeat(32)),'a'.repeat(16));
 assert.equal(shortCorrelation('zz'.repeat(16)),'');
 assert.equal(shortCorrelation('真实姓名张三'),'');
 assert.equal(shortCorrelation(undefined),'');
 assert.equal(shortCorrelation({toString(){return 'f'.repeat(32);}}),'');
});

test('errorBucket: 白名单错误码归桶，未知码归 unclassified，绝不泄露原文',()=>{
 assert.equal(errorBucket('PROVIDER_RESULT_UNKNOWN'),'result_unknown');
 assert.equal(errorBucket('OCR_EMPTY_RESPONSE'),'empty_response');
 assert.equal(errorBucket('PROVIDER_EMPTY_RESPONSE'),'empty_response');
 assert.equal(errorBucket('RATE_LIMITED'),'throttle');
 assert.equal(errorBucket('OK'),'ok');
 assert.equal(errorBucket('请上传身份证照片原件正面'),'unclassified');
 assert.equal(errorBucket(123),'unclassified');
});

test('createChainTelemetry: 仅记录链/阶段/桶/截短关联号/时间戳，零正文零证件零密钥',()=>{
 const t=createChainTelemetry(4);
 const event=t.record('submit','SUBMIT_04',{code:'PROVIDER_RESULT_UNKNOWN',correlation_id:'0123456789abcdef0123456789abcdef',body:'营业执照号码91330100MA27XXXXXX',id_number:'110101199003074541'});
 assert.deepEqual(Object.keys(event).sort(),['bucket','chain','correlation','stage','ts']);
 assert.equal(event.bucket,'result_unknown');
 assert.equal(event.correlation,'0123456789abcdef');
 assert.ok(!JSON.stringify(t.snapshot()).includes('91330100'));
 assert.ok(!JSON.stringify(t.snapshot()).includes('110101'));
 assert.equal(t.record('submit','SUBMIT_99',null),null);
 assert.equal(t.record('sms','OCR_01',null),null);
 for(let i=0;i<10;i++)t.record('ocr','OCR_03',{reason:'JOB_NOT_FOUND'});
 assert.equal(t.snapshot().length,4);
});

test('shouldBlockResubmit: 5分钟冷却窗口内禁止自动重发，窗口外放行；只允许回读收敛',()=>{
 const now=1_700_000_000_000;
 assert.equal(shouldBlockResubmit({until:now+299999,application:'APP-1'},now),true);
 assert.equal(shouldBlockResubmit({until:now+300000,application:'APP-1'},now),true);
 assert.equal(shouldBlockResubmit({until:now,application:'APP-1'},now),false);
 assert.equal(shouldBlockResubmit(null,now),false);
 assert.equal(shouldBlockResubmit({until:'x'},now),false);
});

test('readbackReconciled: 回读到真实状态即收敛，SUBMISSION_UNKNOWN 不算收敛',()=>{
 assert.equal(readbackReconciled({reviewState:'SUBMITTED_TO_PROVIDER'}),true);
 assert.equal(readbackReconciled({reviewState:'CORRECTION'}),true);
 assert.equal(readbackReconciled({reviewState:'SUBMISSION_UNKNOWN'}),false);
 assert.equal(readbackReconciled(null),false);
});

test('classifyOcrEmptyResponse: 空响应识别为可重试空结果而非缺件',()=>{
 assert.equal(classifyOcrEmptyResponse(undefined),true);
 assert.equal(classifyOcrEmptyResponse(null),true);
 assert.equal(classifyOcrEmptyResponse(''),true);
 assert.equal(classifyOcrEmptyResponse('   '),true);
 assert.equal(classifyOcrEmptyResponse({}),true);
 assert.equal(classifyOcrEmptyResponse({result:{job_id:'J1'}}),false);
 assert.equal(classifyOcrEmptyResponse('{"ok":1}'),false);
});

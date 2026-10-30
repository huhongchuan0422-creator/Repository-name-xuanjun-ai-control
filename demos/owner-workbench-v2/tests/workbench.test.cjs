'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
require(path.join(root,'data.js'));
const app=require(path.join(root,'app.js'));
const data=globalThis.XJ_WORKBENCH_FIXTURE;

function test(name,fn){try{fn();process.stdout.write('ok - '+name+'\n');}catch(error){process.stderr.write('not ok - '+name+'\n'+error.stack+'\n');process.exitCode=1;}}

test('fixture is explicitly candidate-only',()=>{
  assert.equal(data.mode,'UI_CANDIDATE');
  assert.match(data.source_notice,/合成数据/);
  assert.ok(data.projects.length>=3);
});

test('routes are bounded and encoded',()=>{
  assert.equal(app.route('#project/PRJ-XJ-042').id,'PRJ-XJ-042');
  assert.deepEqual(app.route('#review/PRJ-XJ-042/PAGE-004/v2.3-r2'),{view:'review',id:'PRJ-XJ-042',project_id:'PRJ-XJ-042',page_id:'PAGE-004',version:'v2.3-r2'});
  assert.equal(app.route('#unknown').view,'overview');
  assert.equal(app.route('#project/%E0%A4%A').view,'overview');
  assert.equal(app.link('project','a/b'),'#project/a%2Fb');
  assert.equal(app.reviewLink('P/A','PAGE 1','v/2'),'#review/P%2FA/PAGE%201/v%2F2');
});

test('project filter does not synthesize missing records',()=>{
  assert.equal(app.filterProjects(data,'统一','').length,1);
  assert.equal(app.filterProjects(data,'不存在','').length,0);
  assert.equal(app.filterProjects(data,'','BLOCKED')[0].id,'PRJ-BIN-007');
});

test('overview and project preserve evidence boundaries',()=>{
  const overview=app.render(data,{view:'overview',id:null});
  assert.match(overview,/合成候选/);
  assert.match(overview,/心跳、ACK/);
  const detail=app.render(data,{view:'project',id:'PRJ-XJ-042'});
  assert.match(detail,/页面确认不等于项目已安装/);
  assert.match(detail,/旧入口保持不变/);
});

test('review separates artifact layers and evidence',()=>{
  const html=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-004/v2.3-r2'));
  for(const label of ['设计稿','合成演示','开发版本','已安装','已验收'])assert.match(html,new RegExp(label));
  assert.match(html,/NOT_EXECUTED/);
  assert.match(html,/无 iframe/);
});

test('review starts with a project queue and remains project scoped',()=>{
  const queue=app.render(data,app.route('#review'));
  assert.match(queue,/筛选项目/);
  assert.match(queue,/进入项目审核/);
  const detail=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-003/v2.3'));
  assert.match(detail,/PRJ-XJ-042/);
  assert.match(detail,/PAGE-003/);
  assert.match(detail,/v2.3/);
  assert.match(detail,/返回项目详情/);
  assert.match(detail,/返回审核列表/);
  const missing=app.render(data,app.route('#review/PRJ-NOT-THERE'));
  assert.match(missing,/没有跨项目回退/);
  assert.doesNotMatch(missing,/PAGE-004/);
});

test('trace fixture and review expose required source keys',()=>{
  const project=data.projects[0];
  for(const key of ['tenant_id','project_id','ui_version','environment','task_id','attempt_id','commit','artifact_sha','evidence_ref'])assert.ok(Object.hasOwn(project,key),key);
  assert.ok(Object.hasOwn(project.pages[0],'page_id'));
  const html=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-001/v2.3'));
  for(const key of ['tenant_id','project_id','page_id','ui_version','environment','task_id','attempt_id','commit','artifact_sha','evidence_ref'])assert.match(html,new RegExp(key));
  assert.match(html,/UNKNOWN/);
});

test('task view separates heartbeat from progress',()=>{
  const html=app.render(data,{view:'tasks',id:null});
  assert.match(html,/ACK ≠ 开工/);
  assert.match(html,/心跳 ≠ 成果/);
  assert.match(html,/真实进展/);
});

test('Binance appears only as Xuanjun self-operated domain',()=>{
  const html=app.render(data,{view:'business',id:null});
  assert.match(html,/玄钧AI新生态内的自营板块/);
  assert.match(html,/不冒充币安官方/);
  assert.doesNotMatch(html,/币安官方客服/);
});

test('all required exception states are visible',()=>{
  const html=app.render(data,{view:'states',id:null});
  for(const value of ['加载中','空状态','读取失败','无权限','版本冲突','未接入','NOT_CONNECTED'])assert.match(html,new RegExp(value));
});

test('navigation includes unified product domains',()=>{
  const html=app.navHtml('overview',false);
  for(const value of ['工作台','客户与项目','预览与审核','应用与生态','开发与执行','客户运营','商业与财务','自营业务','平台治理'])assert.match(html,new RegExp(value));
  assert.match(html,/aria-current="page"/);
});

test('unconnected domains are explicit placeholders',()=>{
  for(const view of ['ecosystem','operations','finance']){
    const html=app.render(data,{view});
    assert.match(html,/NOT_CONNECTED/);
    assert.match(html,/NONE_FOUND/);
  }
});

test('static candidate has no iframe or external dependency',()=>{
  const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const css=fs.readFileSync(path.join(root,'styles.css'),'utf8');
  assert.doesNotMatch(index,/<iframe/i);
  assert.doesNotMatch(index,/https?:\/\//i);
  assert.doesNotMatch(css,/@import|url\(https?:/i);
  assert.match(index,/UI_CANDIDATE/);
  assert.match(index,/不连接真实服务/);
});

test('mobile and reduced-motion contracts exist',()=>{
  const css=fs.readFileSync(path.join(root,'styles.css'),'utf8');
  assert.match(css,/@media\(max-width:820px\)/);
  assert.match(css,/@media\(max-width:560px\)/);
  assert.match(css,/prefers-reduced-motion/);
  assert.match(css,/bottom-nav/);
  assert.match(css,/mobile-review-actions/);
  const review=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-004/v2.3-r2'));
  assert.match(review,/aria-label="移动审核动作"/);
});

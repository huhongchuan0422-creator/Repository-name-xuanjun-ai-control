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
  assert.deepEqual(app.route('#project/PRJ-XJ-042'),{view:'project',id:'PRJ-XJ-042'});
  assert.equal(app.route('#unknown').view,'overview');
  assert.deepEqual(app.route('#project/%E0%A4%A'),{view:'overview',id:null});
  assert.equal(app.link('project','a/b'),'#project/a%2Fb');
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
  const html=app.render(data,{view:'review',id:null});
  for(const label of ['设计稿','合成演示','开发版本','已安装','已验收'])assert.match(html,new RegExp(label));
  assert.match(html,/NOT_EXECUTED/);
  assert.match(html,/无 iframe/);
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
  for(const value of ['工作台','客户与项目','预览与审核','任务与 AI','自营业务','权限与设置'])assert.match(html,new RegExp(value));
  assert.match(html,/aria-current="page"/);
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
});

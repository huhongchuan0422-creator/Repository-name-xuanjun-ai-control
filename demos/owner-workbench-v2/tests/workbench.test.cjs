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

test('explicit unknown page is rejected without first-page fallback',()=>{
  const html=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-NOT-THERE/v9'));
  assert.match(html,/审核页面不存在/);
  assert.match(html,/UNKNOWN/);
  assert.match(html,/返回审核列表/);
  assert.doesNotMatch(html,/工作台总览/);
  assert.doesNotMatch(html,/提交审核/);
});

test('wrong explicit version is a blocking conflict',()=>{
  const html=app.render(data,app.route('#review/PRJ-XJ-042/PAGE-004/v0-wrong'));
  assert.match(html,/VERSION_CONFLICT/);
  assert.match(html,/v0-wrong/);
  assert.match(html,/v2.3-r2/);
  assert.doesNotMatch(html,/提交审核/);
});

test('encoded review identity round-trips and malformed encoding fails closed',()=>{
  const href=app.reviewLink('PRJ/A','PAGE B','v/2');
  assert.deepEqual(app.route(href),{view:'review',id:'PRJ/A',project_id:'PRJ/A',page_id:'PAGE B',version:'v/2'});
  const malformed=app.route('#review/PRJ-XJ-042/%E0%A4%A/v2');
  assert.equal(malformed.view,'overview');
  assert.equal(malformed.id,null);
});

test('synthetic fixture never claims the frozen git baseline as its commit',()=>{
  assert.equal(data.projects[0].commit,'SYNTHETIC_UI_FIXTURE_NOT_GIT_COMMIT');
  assert.equal(data.review.commit,'SYNTHETIC_UI_FIXTURE_NOT_GIT_COMMIT');
  assert.equal(data.projects[0].artifact_sha,'UNKNOWN');
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
  for(const value of ['总览','运营','客户','研发','验收交付','维护','共享生态','财务','自营业务','预览审核','配置'])assert.match(html,new RegExp(value));
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

test('login and shell visibility are strictly exclusive',()=>{
  assert.deepEqual(app.shellVisibility(false),{loginHidden:false,shellHidden:true});
  assert.deepEqual(app.shellVisibility(true),{loginHidden:true,shellHidden:false});
  const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const css=fs.readFileSync(path.join(root,'styles.css'),'utf8');
  assert.match(css,/\[hidden\]\{display:none!important\}/);
  assert.match(index,/id="loginScreen"/);
  assert.match(index,/id="shell" hidden/);
  assert.match(index,/id="logoutButton"/);
  assert.match(app.shellVisibility.toString(),/loginHidden/);
});

test('candidate session supports logout refresh history and mobile overlay cleanup without formal auth',()=>{
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  const css=fs.readFileSync(path.join(root,'styles.css'),'utf8');
  assert.match(source,/sessionStorage\.getItem\('XJ_UI_CANDIDATE_SESSION'\)/);
  assert.match(source,/sessionStorage\.removeItem\('XJ_UI_CANDIDATE_SESSION'\)/);
  assert.match(source,/logout\.addEventListener\('click'/);
  assert.match(source,/win\.addEventListener\('hashchange'/);
  assert.match(source,/function closeMenu\(returnFocus\)/);
  assert.match(css,/@media\(max-width:820px\)/);
  assert.match(css,/\[hidden\]\{display:none!important\}/);
  assert.doesNotMatch(source,/fetch\(|XMLHttpRequest|Authorization/);
});

test('mobile menu closes by Escape and restores focus deterministically',()=>{
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  assert.match(source,/function closeMenu\(returnFocus\)/);
  assert.match(source,/if\(returnFocus&&wasOpen\)menu\.focus\(\)/);
  assert.match(source,/function openMenu\(\)/);
  assert.match(source,/side\.querySelector\('\.nav-parent,\.nav-child'\)/);
  assert.match(source,/if\(first\)first\.focus\(\)/);
  assert.match(source,/e\.key==='Escape'/);
  assert.match(source,/scrim\.addEventListener\('click',function\(\)\{closeMenu\(true\)/);
  assert.match(source,/if\(e\.target\.closest\('a'\)\)closeMenu\(false\)/);
});

test('review tab resets only when project identity changes',()=>{
  assert.deepEqual(app.reviewStateForProject(null,'PRJ-A','diff'),{project:'PRJ-A',tab:'feedback'});
  assert.deepEqual(app.reviewStateForProject('PRJ-A','PRJ-A','evidence'),{project:'PRJ-A',tab:'evidence'});
  assert.deepEqual(app.reviewStateForProject('PRJ-A','PRJ-B','diff'),{project:'PRJ-B',tab:'feedback'});
  assert.deepEqual(app.reviewStateForProject('PRJ-B',null,'evidence'),{project:null,tab:'feedback'});
});

test('all eleven domains expose expandable second-level navigation',()=>{
  const html=app.navHtml('overview',false);
  const domains=['overview','operations','customer','research-development','acceptance-delivery','maintenance','shared-ecosystem','finance','business','review','settings'];
  for(const id of domains){
    assert.match(html,new RegExp('data-domain="'+id+'"'));
    assert.match(html,new RegExp('data-nav-toggle="'+id+'"'));
  }
  for(const child of ['目标与计划','运营任务','渠道与活动','经营指标','异常与人工待办','客户与租户','CRM线索','需求与SOW','客户项目','合同与权益','客户反馈','开发任务','仓库与版本','构建与制品','测试与质量','独立审核','模块产品化','测试证据','发布与安装','客户验收','交付与归档','服务与运行时','健康与告警','事件与故障','检查点与恢复','备份与演练','到期与安全退出','生态成员','贡献记录','声誉与凭证','生态权益','伙伴与推荐','方案知识与产品化','产品与价格','成本与利润','报价与订单','钱包与用量','账单与付款','对账退款','推荐结算','自营项目','运行证据','审核队列','页面与版本','验收记录','身份与RBAC','模块接入','平台设置','操作日志'])assert.match(html,new RegExp(child));
});

test('detail and deep routes highlight their owning domain and child',()=>{
  assert.equal(app.domainForView('project'),'customer');
  assert.equal(app.domainForView('review-pages'),'review');
  assert.equal(app.domainForView('research-builds'),'research-development');
  const projectNav=app.navHtml('project',false);
  assert.match(projectNav,/data-domain="customer"[^]*?class="nav-child" href="#projects" aria-current="page"/);
  const reviewNav=app.navHtml('review',false);
  assert.match(reviewNav,/data-domain="review"[^]*?aria-expanded="true"/);
});

test('route parsing is stable across repeated navigation and refresh inputs',()=>{
  const hashes=['#overview','#project/PRJ-XJ-042','#review/PRJ-XJ-042/PAGE-004/v2.3-r2','#tasks','#overview'];
  const first=hashes.map(app.route);
  const second=hashes.map(app.route);
  assert.deepEqual(first,second);
  assert.equal(first[1].id,'PRJ-XJ-042');
  assert.equal(first[2].page_id,'PAGE-004');
});

test('cross-project review does not retain the previous project page',()=>{
  const clone=JSON.parse(JSON.stringify(data));
  clone.projects[1].pages=[{id:'PAGE-B-001',page_id:'PAGE-B-001',name:'B 项目页面',status:'PENDING_REVIEW',label:'待审核',version:'b-v1',ui_version:'b-v1',previous:'NONE_FOUND',changes:1}];
  const first=app.render(clone,app.route('#review/PRJ-XJ-042/PAGE-004/v2.3-r2'));
  const second=app.render(clone,app.route('#review/PRJ-CUS-118/PAGE-B-001/b-v1'));
  assert.match(first,/PAGE-004/);
  assert.match(second,/PAGE-B-001/);
  assert.doesNotMatch(second,/PAGE-004/);
});

test('permission denial and unconnected children remain explicit',()=>{
  const denied=app.render(data,{view:'states'});
  assert.match(denied,/无权限/);
  for(const view of ['project-help','review-help','app-versions','twin','tickets','billing','business-evidence','audit']){
    const html=app.render(data,{view});
    assert.match(html,/NOT_CONNECTED/);
    assert.match(html,/UNKNOWN/);
  }
});

test('dashboard is synthetic, unknown-safe, and deep-linked',()=>{
  const html=app.render(data,{view:'overview'});
  for(const label of ['项目进度','AI 任务','待审核','异常阻塞','关键业务指标'])assert.match(html,new RegExp(label));
  assert.match(html,/SYNTHETIC/);
  assert.match(html,/UNKNOWN/);
  assert.match(html,/NOT_CONNECTED · 不显示为 0/);
  for(const href of ['#projects','#tasks','#review','#project/PRJ-BIN-007','#finance-profit'])assert.match(html,new RegExp('href="'+href+'"'));
});

test('common framework components are local-only',()=>{
  const index=fs.readFileSync(path.join(root,'index.html'),'utf8');
  const projects=app.render(data,{view:'projects'});
  assert.match(index,/id="demoDialog"/);
  assert.match(index,/SYNTHETIC STEP FLOW/);
  assert.match(index,/NO_PRODUCTION_WRITE/);
  assert.match(projects,/aria-label="项目分页"/);
  assert.match(projects,/第 1 \/ 1 页 · SYNTHETIC/);
});

const ADMIN_MODULES={
  operations:['operations-plan','operations-tasks','operations-channels','operations-metrics','operations-exceptions'],
  customer:['customer-tenants','customer-leads','customer-requirements','projects','customer-contracts','customer-feedback'],
  'research-development':['tasks','research-repositories','research-builds','research-tests','research-audit','research-products'],
  'acceptance-delivery':['acceptance-evidence','acceptance-release','acceptance-customer','acceptance-archive'],
  maintenance:['maintenance-services','maintenance-alerts','maintenance-incidents','maintenance-recovery','maintenance-backup','maintenance-expiry'],
  'shared-ecosystem':['ecosystem-members','ecosystem-contributions','ecosystem-reputation','ecosystem-rights','ecosystem-partners','ecosystem-knowledge'],
  finance:['finance-products','finance-profit','finance-orders','finance-usage','finance-billing','finance-refunds','finance-referrals']
};

test('seven fixed management modules and every secondary route are registered',()=>{
  assert.deepEqual(Object.keys(data.management_modules),Object.keys(ADMIN_MODULES));
  for(const [moduleId,views] of Object.entries(ADMIN_MODULES)){
    for(const view of views){
      const parsed=app.route('#'+view);
      assert.equal(parsed.view,view,moduleId+' '+view);
      assert.equal(app.domainForView(view),moduleId,moduleId+' owner');
      const nav=app.navHtml(view,false);
      assert.match(nav,new RegExp('data-domain="'+moduleId+'"[^]*?aria-expanded="true"'));
    }
  }
});

test('generic management pages contain overview filter list detail capability and logs',()=>{
  for(const views of Object.values(ADMIN_MODULES))for(const view of views){
    if(view==='projects'){
      const list=app.render(data,app.route('#projects'));
      for(const label of ['搜索项目','项目分页','权限范围操作','SERVER_AUTHORITATIVE','操作日志'])assert.match(list,new RegExp(label));
      const detail=app.render(data,app.route('#project/PRJ-XJ-042'));
      for(const label of ['PRJ-XJ-042','权限范围操作','SERVER_AUTHORITATIVE','操作日志','disabled'])assert.match(detail,new RegExp(label));
      continue;
    }
    if(view==='tasks'){
      const list=app.render(data,app.route('#tasks'));
      for(const label of ['筛选任务','任务分页','#tasks/TASK-2042','权限范围操作','SERVER_AUTHORITATIVE','操作日志'])assert.match(list,new RegExp(label));
      const detail=app.render(data,app.route('#tasks/TASK-2042'));
      for(const label of ['详情摘要','TASK-2042','ATT-03','权限范围操作','操作日志','disabled'])assert.match(detail,new RegExp(label));
      continue;
    }
    const list=app.render(data,app.route('#'+view));
    for(const label of ['UNKNOWN','NOT_CONNECTED','筛选关键词','对象','权限范围操作','操作日志','页码 UNKNOWN'])assert.match(list,new RegExp(label),view+' '+label);
    const detail=app.render(data,app.route('#'+view+'/OBJECT-UNKNOWN'));
    assert.match(detail,/对象摘要/);
    assert.match(detail,/OBJECT-UNKNOWN/);
    assert.match(detail,/SERVER_AUTHORITATIVE/);
    assert.match(detail,/disabled/);
    assert.match(detail,/操作日志/);
  }
});

test('unconnected management projections never infer zero or success',()=>{
  for(const module of Object.values(data.management_modules))assert.equal(module.status,'NOT_CONNECTED');
  const html=app.render(data,app.route('#operations-plan'));
  assert.match(html,/不用 0 或成功替代 UNKNOWN/);
  assert.doesNotMatch(html,/metric-value">0</);
  assert.doesNotMatch(html,/REAL_VERIFIED|已成功/);
});

test('digital twin is only a TEST_ONLY object jump card',()=>{
  const html=app.render(data,app.route('#tasks'));
  assert.match(html,/数字孪生对象入口/);
  assert.match(html,/object_ref: UNKNOWN/);
  assert.match(html,/target_route: \/task-center-test\//);
  assert.match(html,/href="\/task-center-test\/"/);
  assert.doesNotMatch(html,/target_route: \/task-center-test\/digital-twin\//);
  assert.doesNotMatch(html,/href="\/task-center-test\/digital-twin\//);
  assert.match(html,/TEST_ONLY/);
  assert.match(html,/NOT_CONNECTED/);
  assert.doesNotMatch(html,/拓扑|连线|健康大屏/);
});

test('unknown task deep link fails closed without cross-task fallback',()=>{
  const html=app.render(data,app.route('#tasks/TASK-NOT-THERE'));
  assert.match(html,/开发任务不存在/);
  assert.match(html,/UNKNOWN/);
  assert.match(html,/不回退到其他任务/);
  assert.doesNotMatch(html,/TASK-2042 · ATT-03/);
});

test('permission actions remain disabled without server capability',()=>{
  const html=app.render(data,app.route('#finance-orders/OBJECT-UNKNOWN'));
  assert.match(html,/服务端 capability 未接入/);
  assert.match(html,/前端隐藏按钮不构成授权/);
  assert.match(html,/disabled>执行操作（无 capability）/);
});

test('cross-module navigation clears review-scoped state',()=>{
  assert.equal(app.clearScopedState('review'),'review');
  assert.equal(app.clearScopedState('finance-orders'),'finance-orders');
  assert.deepEqual(app.reviewStateForProject(null,'PRJ-XJ-042','diff'),{project:'PRJ-XJ-042',tab:'feedback'});
});

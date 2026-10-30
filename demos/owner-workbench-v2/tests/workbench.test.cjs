'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
require(path.join(root,'data.js'));
const app=require(path.join(root,'app.js'));
const data=globalThis.XJ_WORKBENCH_FIXTURE;

const TESTS=[];
function test(name,fn){TESTS.push({name,fn});}

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

test('OpenAI channel preference preview is manual truthful and no fallback',()=>{
  const html=app.render(data,{view:'config-models'});
  for(const text of ['API优先','订阅OAuth优先','Owner 选择','实际生效通道','fallback','赠额是否适用'])assert.match(html,new RegExp(text));
  assert.match(html,/SUBSCRIPTION_OAUTH_FIRST/);
  assert.match(html,/NOT_CONFIGURED/);
  assert.match(html,/UI候选 · 不写服务端/);
  assert.match(html,/不自动切换、不自动充值、不静默 fallback/);
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  assert.match(source,/SET_OPENAI_CHANNEL_PREFERENCE/);
  assert.match(source,/X-CSRF-Token/);
  assert.match(source,/CHANNEL_PREFERENCE_SAVED/);
  assert.doesNotMatch(source,/api[_-]?key\s*[:=]\s*['"][^'"]+/i);
});

test('unified admin shows concise model-service summary instead of customer forms',()=>{
  const html=app.render(data,{view:'config-models'});
  for(const text of ['模型服务','客户侧服务方式','同一后台','已验证平台','真实业务接线','查看客户侧选择流程'])assert.match(html,new RegExp(text));
  for(const text of ['Provider 与受保护引用','OpenAI 执行通道偏好','模型用量与估算成本'])assert.match(html,new RegExp('<summary>'+text));
  assert.match(html,/href="#customer-model-service"/);
  assert.doesNotMatch(html,/data-customer-model-mode|你希望如何使用模型/);
});

test('two model-service modes are customer-side choices in the same admin shell',()=>{
  const html=app.render(data,{view:'customer-model-service'});
  for(const text of ['这是统一管理台中的客户侧开通流程','不是第二套后台','我已有上游账号','购买玄钧AI新 API 服务','客户直接向上游平台付款','查看费用、凭据与权益边界'])assert.match(html,new RegExp(text));
  assert.match(html,/data-customer-model-mode="BYO_ACCOUNT"/);
  assert.match(html,/data-customer-model-mode="XUANJUN_API_SERVICE"/);
  assert.match(html,/不会创建连接、订单或权益/);
  assert.match(html,/待 Owner 确认/);
  assert.equal(app.domainForView('customer-model-service'),'customer');
  assert.doesNotMatch(html,/免费接入|自动切换到/);
});

test('provider candidates stay unavailable until platform and channel verification',()=>{
  const html=app.render(data,{view:'customer-model-service'});
  for(const platform of ['硅基流动','OpenAI','DeepSeek','百炼'])assert.match(html,new RegExp(platform));
  assert.equal(data.model_service_dual_entry_preview.byo_account.platforms.every(p=>p.state==='PENDING_VERIFICATION'),true);
  assert.equal(data.model_service_dual_entry_preview.byo_account.platforms.every(p=>p.verified_channels.length===0),true);
  assert.match(html,/已验证通道[^]*NONE_FOUND/);
  assert.match(html,/模型列表[^]*NOT_LOADED/);
  assert.doesNotMatch(html,/开始 OAuth 授权|已验证可用/);
});

test('customer mode interaction remains local candidate without write capability',()=>{
  const html=app.render(data,{view:'customer-model-service'});
  assert.match(html,/data-customer-model-mode="BYO_ACCOUNT"/);
  assert.match(html,/data-customer-model-mode="XUANJUN_API_SERVICE"/);
  assert.match(html,/继续（候选未接线）/);
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  assert.match(source,/selectedCustomerModelMode=button\.getAttribute\('data-customer-model-mode'\)/);
  assert.doesNotMatch(source,/CREATE_MODEL_SERVICE_CONNECTION|CREATE_API_ORDER|ACTIVATE_PROJECT_ENTITLEMENT/);
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

test('local candidate session supports logout refresh history and mobile overlay cleanup without formal auth',()=>{
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  const css=fs.readFileSync(path.join(root,'styles.css'),'utf8');
  assert.match(source,/sessionStorage\.getItem\('XJ_UI_CANDIDATE_SESSION'\)/);
  assert.match(source,/sessionStorage\.removeItem\('XJ_UI_CANDIDATE_SESSION'\)/);
  assert.match(source,/logout\.addEventListener\('click'/);
  assert.match(source,/win\.addEventListener\('hashchange'/);
  assert.match(source,/function closeMenu\(returnFocus\)/);
  assert.match(css,/@media\(max-width:820px\)/);
  assert.match(css,/\[hidden\]\{display:none!important\}/);
  assert.match(source,/win\.location\.protocol!==\x27file:\x27/);
});

test('hosted mode uses same-origin session and projection without fixture fallback',()=>{
  const source=fs.readFileSync(path.join(root,'app.js'),'utf8');
  assert.match(source,/options\.fetch\('\.\.\/api\/session'/);
  assert.match(source,/options\.fetch\('\.\.\/api\/admin\/workbench'/);
  assert.match(source,/credentials:'same-origin'/);
  assert.match(source,/没有保留或回退旧数据/);
  assert.match(source,/function bootHosted[^]*globalSearch[^]*win\.location\.hash='#projects'/);
  assert.doesNotMatch(source,/fetch\(['"]https?:/);
  const hosted=app.normalizeHostedProjection({projection:'UNIFIED_ADMIN_PROJECTION_V1',mode:'TEST_ONLY',tenant_id:'t',observed_at:1,source_observed_at:0,sources:{social_media:{status:'NOT_CONNECTED',source_level:'CANDIDATE_ONLY_UNVERIFIED',source_candidates:['Channel Registry'],evidence_refs:['NONE_FOUND'],gaps:['RBAC']},servers:{status:'NOT_CONNECTED',source_level:'CANDIDATE_ONLY_UNVERIFIED',source_candidates:['Infrastructure Registry'],evidence_refs:['NONE_FOUND'],gaps:['CURRENT_INVENTORY']}},modules:{overview:{summary:{task_count:1,research_task_count:1}},'research-development':{status:'CONNECTED_TEST_ONLY',records:[{task_id:'T1',project_id:'P1',state:'RUNNING',runtime_status:'LIVENESS_UNKNOWN',responsible_party:'writer',next_action:'review',last_real_progress_at:5,blocker:null}],advanced:{audit_records:[{task_id:'T1',attempt_id:'A1',run_id:'R1',session_id:'S1',epoch:2,evidence:[]}]}},configuration:{status:'CONNECTED_TEST_ONLY',records:[{provider_id:'p1',display_name:'Provider',enabled:true,price_state:'UNKNOWN',secret:{state:'CONFIGURED',ref:'PROTECTED_PROVIDER_SECRET:p1'}}],advanced:{model_usage_semantic:'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE',model_usage:[{provider_id:'p1',model_id:'m1',request_count:2,input_tokens:10,output_tokens:4,cost_state:'KNOWN_ZERO',estimated_cost:0,cost_unit:'UNKNOWN',semantic:'MODEL_ESTIMATE_NOT_BILLING_OR_ACTUAL_CHARGE'}],openai_channel_preference:{selected_preference:'API_FIRST',selected_channel:'API',effective_channel:'NONE',effective_connection_id:null,config_version:3,status:'HOLD',reason:'NO_API_CONNECTION',fallback:'DISABLED',channels:{API:{state:'NOT_CONFIGURED',connection_id:null,reason:'NO_API_CONNECTION'},SUBSCRIPTION_OAUTH:{state:'ACTIVE',connection_id:'oauth-1',reason:'AVAILABLE'}}}}},finance:{status:'NOT_CONNECTED'}}});
  assert.equal(hosted.mode,'HOSTED_TEST_ONLY');
  assert.equal(hosted.tasks[0].id,'T1');
  assert.equal(hosted.tasks[0].advanced.attempt_id,'A1');
  assert.equal(hosted.metrics[2].value,'UNKNOWN');
  const overview=app.render(hosted,{view:'overview'});
  for(const label of ['数据读取时间','源数据时间','tenant','TASK_CENTER_ADMIN / READ_ONLY'])assert.match(overview,new RegExp(label));
  const detail=app.render(hosted,{view:'tasks',id:'T1'});
  assert.match(detail,/高级详情 \/ 审计证据/);
  assert.match(detail,/attempt_id/);
  assert.doesNotMatch(detail.split('<details')[0],/attempt_id|artifact_sha|epoch/);
  const models=app.render(hosted,{view:'config-models'});
  assert.match(models,/PROTECTED_PROVIDER_SECRET:p1/);
  assert.match(models,/SET_OPENAI_CHANNEL_PREFERENCE/);
  assert.match(models,/模型用量与估算成本/);
  assert.match(models,/m1/);
  assert.match(models,/不是财务账本、实际扣费或付款凭证/);
  assert.match(models,/API_FIRST/);
  assert.match(models,/实际生效通道/);
  assert.match(models,/NONE/);
  assert.match(models,/不自动切换、不自动充值、不静默 fallback/);
  const media=app.render(hosted,{view:'config-media'}),servers=app.render(hosted,{view:'config-servers'});
  for(const pair of [[media,'Channel Registry','RBAC'],[servers,'Infrastructure Registry','CURRENT_INVENTORY']]){assert.match(pair[0],new RegExp(pair[1]));assert.match(pair[0],new RegExp(pair[2]));assert.match(pair[0],/NOT_CONNECTED/);assert.match(pair[0],/allowed_actions/);}
  for(const html of [overview,app.render(hosted,{view:'tasks'}),models,media,servers])assert.doesNotMatch(html,/SYNTHETIC|合成|演示/);
  assert.throws(()=>app.normalizeHostedProjection(data),/HOSTED_PROJECTION_REQUIRED/);
});

test('hosted controller refreshes each route/manual cycle and fails closed',async()=>{
  let projectionNumber=0,failProjection=false;const calls=[],states=[];
  function projection(){projectionNumber+=1;return{projection:'UNIFIED_ADMIN_PROJECTION_V1',mode:'TEST_ONLY',tenant_id:'t',observed_at:projectionNumber,modules:{overview:{summary:{}},'research-development':{records:[]},configuration:{records:[]},finance:{status:'NOT_CONNECTED'}}};}
  const fakeFetch=(url,options)=>{calls.push([url,options]);if(url.includes('/session'))return Promise.resolve({ok:true,status:200});if(failProjection)return Promise.resolve({ok:false,status:503});return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(projection())});};
  const controller=app.createHostedController({fetch:fakeFetch,onLoading:reason=>states.push('LOADING:'+reason),onData:value=>states.push('READY:'+value.observed_at),onError:error=>states.push('ERROR:'+error.message),onLoginRequired:()=>states.push('LOGIN')});
  await controller.refresh('INITIAL');await controller.refresh('ROUTE_CHANGE');await controller.refresh('MANUAL_REFRESH');
  assert.deepEqual(calls.map(x=>x[0]),['../api/session','../api/admin/workbench','../api/session','../api/admin/workbench','../api/session','../api/admin/workbench']);
  assert.ok(calls.every(x=>x[1].credentials==='same-origin'&&x[1].cache==='no-store'));
  assert.equal(controller.current().observed_at,3);
  failProjection=true;const failed=await controller.refresh('RETRY');
  assert.equal(failed.state,'ERROR');assert.equal(controller.current(),null);assert.match(states.join('|'),/LOADING:RETRY.*ERROR:HOSTED_HTTP_503/);

  let releaseFirst;const firstSession=new Promise(resolve=>{releaseFirst=resolve;}),fresh=[];let sessionCalls=0;
  const staleController=app.createHostedController({fetch:url=>{if(url.includes('/session')){sessionCalls+=1;return sessionCalls===1?firstSession:Promise.resolve({ok:true,status:200});}return Promise.resolve({ok:true,status:200,json:()=>Promise.resolve(projection())});},onLoading:()=>{},onData:value=>fresh.push(value.observed_at),onError:()=>assert.fail('stale request must not error'),onLoginRequired:()=>assert.fail('unexpected login')});
  const old=staleController.refresh('OLD'),latest=staleController.refresh('NEW');await latest;releaseFirst({ok:true,status:200});const stale=await old;
  assert.equal(stale.state,'STALE');assert.equal(fresh.length,1);
});

test('all finance children remain unknown without a finance ledger',()=>{
  for(const view of ['finance-products','finance-profit','finance-orders','finance-usage','finance-billing','finance-refunds','finance-referrals']){
    const html=app.render(data,{view});
    assert.match(html,/NOT_CONNECTED/);
    assert.match(html,/UNKNOWN/);
  }
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
  for(const child of ['目标与计划','运营任务','渠道与活动','经营指标','异常与人工待办','客户与租户','CRM线索','需求与SOW','客户项目','合同与权益','客户反馈','开发任务','仓库与版本','构建与制品','测试与质量','独立审核','模块产品化','测试证据','发布与安装','客户验收','交付与归档','服务与运行时','健康与告警','事件与故障','检查点与恢复','备份与演练','到期与安全退出','生态成员','贡献记录','声誉与凭证','生态权益','伙伴与推荐','方案知识与产品化','产品与价格','成本与利润','报价与订单','钱包与用量','账单与付款','对账退款','推荐结算','自营项目','运行证据','审核队列','页面与版本','验收记录','身份与RBAC','大模型','自媒体','服务器','操作日志'])assert.match(html,new RegExp(child));
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

(async()=>{
  let failures=0;
  for(const item of TESTS){
    try{await item.fn();process.stdout.write('ok - '+item.name+'\n');}
    catch(error){failures+=1;process.stderr.write('not ok - '+item.name+'\n'+error.stack+'\n');}
  }
  if(failures){process.stderr.write('failures: '+failures+' / '+TESTS.length+'\n');process.exitCode=1;}
  else process.stdout.write('tests: '+TESTS.length+' passed, 0 failed\n');
})();

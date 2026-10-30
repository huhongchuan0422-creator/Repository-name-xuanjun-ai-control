(function(root){
  'use strict';
  root.XJ_WORKBENCH_FIXTURE={
    schema:3,
    tenant_id:'TENANT-SYNTHETIC-XJ',
    mode:'UI_CANDIDATE',
    observed_at:'2026-10-30 13:30 CST',
    source_notice:'合成数据，仅验证信息架构和交互；不代表部署、安装或客户验收。',
    metrics:[
      {label:'项目进度',value:'3',delta:'SYNTHETIC · 1 个开发中',tone:'info',href:'#projects'},
      {label:'AI 任务',value:'2',delta:'SYNTHETIC · 心跳与成果分开',tone:'success',href:'#tasks'},
      {label:'待审核',value:'2',delta:'SYNTHETIC · 按项目进入',tone:'warning',href:'#review'},
      {label:'异常阻塞',value:'1',delta:'SYNTHETIC · 证据不足',tone:'danger',href:'#project/PRJ-BIN-007'},
      {label:'关键业务指标',value:'UNKNOWN',delta:'NOT_CONNECTED · 不显示为 0',tone:'unknown',href:'#finance'}
    ],
    projects:[
      {
        id:'PRJ-XJ-042',project_id:'PRJ-XJ-042',tenant_id:'TENANT-SYNTHETIC-XJ',name:'玄钧统一管理台',customer:'玄钧AI实验室',kind:'平台产品',
        stage:'PENDING_REVIEW',stage_label:'待 Owner 审核',owner:'产品与交付组',updated:'12 分钟前',
        next_action:'审核首页与项目详情候选',ui_version:'ui-v2.3-candidate',environment:'SYNTHETIC_PREVIEW',task_id:'TASK-2042',attempt_id:'ATT-03',commit:'SYNTHETIC_UI_FIXTURE_NOT_GIT_COMMIT',artifact_sha:'UNKNOWN',evidence_ref:'demos/owner-workbench-v2',
        progress:{done:4,total:8},risk:'LOW',legacy_entry_ref:'/task-center-test/admin.html',
        pages:[
          {id:'PAGE-001',page_id:'PAGE-001',name:'工作台总览',status:'PENDING_REVIEW',label:'待审核',version:'v2.3',ui_version:'v2.3',previous:'v2.2',changes:6},
          {id:'PAGE-002',page_id:'PAGE-002',name:'项目列表',status:'CONFIRMED',label:'已确认',version:'v2.3',ui_version:'v2.3',previous:'v2.2',changes:3},
          {id:'PAGE-003',page_id:'PAGE-003',name:'项目详情',status:'PENDING_CHANGE',label:'待修改',version:'v2.3',ui_version:'v2.3',previous:'v2.2',changes:4},
          {id:'PAGE-004',page_id:'PAGE-004',name:'预览审核工作区',status:'PENDING_RECHECK',label:'待复验',version:'v2.3-r2',ui_version:'v2.3-r2',previous:'v2.3',changes:2}
        ]
      },
      {
        id:'PRJ-CUS-118',project_id:'PRJ-CUS-118',tenant_id:'TENANT-SYNTHETIC-A',name:'客户项目中心升级',customer:'合成客户 A',kind:'定制项目',
        stage:'IN_DEVELOPMENT',stage_label:'开发中',owner:'交付工程组',updated:'1 小时前',
        next_action:'等待 Identity adapter',ui_version:'customer-center-v1',environment:'UNKNOWN',task_id:'TASK-2118',attempt_id:'ATT-01',commit:'UNKNOWN',artifact_sha:'NONE_FOUND',evidence_ref:'NONE_FOUND',
        progress:{done:3,total:9},risk:'MEDIUM',legacy_entry_ref:'/customer/center/',pages:[]
      },
      {
        id:'PRJ-BIN-007',project_id:'PRJ-BIN-007',tenant_id:'TENANT-SYNTHETIC-XJ',name:'币安自营客服隔离',customer:'玄钧AI新 · 自营',kind:'自营业务',
        stage:'BLOCKED',stage_label:'证据不足',owner:'自营业务组',updated:'昨天',
        next_action:'补真实模型语义证据',ui_version:'support-rules-v1',environment:'NOT_CONNECTED',task_id:'TASK-2207',attempt_id:'UNKNOWN',commit:'UNKNOWN',artifact_sha:'NONE_FOUND',evidence_ref:'NONE_FOUND',
        progress:{done:2,total:6},risk:'HIGH',legacy_entry_ref:null,pages:[]
      }
    ],
    review:{
      tenant_id:'TENANT-SYNTHETIC-XJ',project_id:'PRJ-XJ-042',page_id:'PAGE-004',page_name:'预览审核工作区',version:'v2.3-r2',ui_version:'v2.3-r2',environment:'SYNTHETIC_PREVIEW',task_id:'TASK-2042',attempt_id:'ATT-03',
      artifact_sha:'UNKNOWN',commit:'SYNTHETIC_UI_FIXTURE_NOT_GIT_COMMIT',evidence_ref:'demos/owner-workbench-v2',responsible:'UI Writer',next_action:'Owner 逐页确认',
      layers:[
        {id:'design',label:'设计稿',state:'DONE',detail:'布局与信息层级候选'},
        {id:'demo',label:'合成演示',state:'DONE',detail:'无后端、无生产写入'},
        {id:'development',label:'开发版本',state:'CURRENT',detail:'当前候选，仅本地'},
        {id:'installed',label:'已安装',state:'NOT_EXECUTED',detail:'没有安装回执'},
        {id:'accepted',label:'已验收',state:'NOT_EXECUTED',detail:'没有客户/Owner验收'}
      ],
      feedback:[
        {id:'FB-017',actor:'Owner（合成）',scope:'PAGE-003',text:'项目阶段与下一责任方要放在首屏。',state:'RESOLVED_IN_CANDIDATE',version:'v2.3'},
        {id:'FB-021',actor:'产品审核（合成）',scope:'PAGE-004',text:'版本对比不可把未安装写成完成。',state:'PENDING_RECHECK',version:'v2.3-r2'}
      ],
      evidence:[
        {kind:'源码候选',ref:'demos/owner-workbench-v2',state:'AVAILABLE'},
        {kind:'JS 测试',ref:'tests/workbench.test.cjs',state:'AVAILABLE'},
        {kind:'真实安装',ref:'NONE_FOUND',state:'NOT_EXECUTED'},
        {kind:'客户验收',ref:'NONE_FOUND',state:'NOT_EXECUTED'}
      ]
    },
    tasks:[
      {id:'TASK-2042',project:'PRJ-XJ-042',node:'UI-CANDIDATE',name:'统一管理台 UI 候选',state:'EXECUTING',owner:'UI Writer',ai:'AI-UI-01',attempt:'ATT-03',progress_at:'13:28',artifact:'UNKNOWN'},
      {id:'TASK-2043',project:'PRJ-XJ-042',node:'INDEPENDENT-QA',name:'同版 UI 联合验收',state:'PENDING_CLAIM',owner:'独立 QA',ai:'UNASSIGNED',attempt:'UNKNOWN',progress_at:'UNKNOWN',artifact:'UNKNOWN'},
      {id:'TASK-2118',project:'PRJ-CUS-118',node:'IDENTITY-ADAPTER',name:'客户身份生产适配',state:'BLOCKED',owner:'Identity 责任方',ai:'NONE',attempt:'ATT-01',progress_at:'UNKNOWN',artifact:'NONE_FOUND'},
      {id:'TASK-2207',project:'PRJ-BIN-007',node:'MODEL-EVIDENCE',name:'客服真实语义隔离复测',state:'UNKNOWN',owner:'客服模型责任方',ai:'UNKNOWN',attempt:'UNKNOWN',progress_at:'UNKNOWN',artifact:'NONE_FOUND'}
    ],
    ai:[
      {id:'AI-UI-01',role:'UI 实现',state:'EXECUTING',heartbeat:'13:29',progress:'13:28 · 文件增量',task:'TASK-2042',writer:'YES'},
      {id:'AI-QA-02',role:'独立审核',state:'IDLE',heartbeat:'13:20',progress:'NONE',task:'NONE',writer:'NO'},
      {id:'AI-MCP-03',role:'MCP 执行',state:'UNKNOWN',heartbeat:'UNKNOWN',progress:'UNKNOWN',task:'TASK-2207',writer:'NO'}
    ],
    permissions:[
      {role:'平台 Owner',projects:'获授权范围',review:'允许',deploy:'需原发布门禁',secret:'仅 SecretRef'},
      {role:'项目 Writer',projects:'分配项目',review:'不可自审',deploy:'不可',secret:'不可见'},
      {role:'独立审核',projects:'同版候选',review:'允许',deploy:'不可',secret:'不可见'},
      {role:'客户验收人',projects:'本人项目',review:'正式授权后',deploy:'不可',secret:'不可见'}
    ],
    events:[
      {time:'13:28',kind:'PROGRESS',title:'候选文件产生增量',actor:'UI Writer',ref:'TASK-2042 / ATT-03'},
      {time:'13:12',kind:'REVIEW_REQUESTED',title:'提交项目详情差异确认',actor:'产品集成',ref:'FB-021'},
      {time:'12:58',kind:'SOURCE_FROZEN',title:'任务中心底层版本固定',actor:'集成负责人',ref:'a801a8d5'},
      {time:'UNKNOWN',kind:'INSTALL',title:'现场安装回执缺失',actor:'安装责任方',ref:'NONE_FOUND'}
    ]
  };
})(typeof window!=='undefined'?window:globalThis);

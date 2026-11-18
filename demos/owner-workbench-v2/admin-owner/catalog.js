window.CATALOG={
  "version": "R2.0",
  "status": "PRODUCT_CONTRACT_NOT_OWNER_ACCEPTED",
  "pages": [
    {
      "id": "H01",
      "domain": "工作台总览",
      "group": null,
      "name": "工作台总览",
      "template": "dashboard",
      "depth": 2,
      "fields": [
        "进行项目",
        "关键任务/逾期异常",
        "待决定/验收",
        "近期交付",
        "问题/下一步",
        "服务概况",
        "Owner专属组件简况"
      ],
      "search": "项目范围/负责人（有实际范围才给选项）",
      "actions": "项目→PD、关键任务→TD、待验收→PA、近期交付→PR/DL、服务器→S05；组件无跳转",
      "source": "Project/Task/Finance/Monitoring；未接/待核，不用假0/健康分",
      "detail": "GD"
    },
    {
      "id": "H02",
      "domain": "工作台总览",
      "group": null,
      "name": "待我处理",
      "template": "list",
      "depth": 2,
      "fields": [
        "事项",
        "所属业务",
        "需本人动作",
        "状态",
        "责任人",
        "约定时间"
      ],
      "search": "关键词/类型/状态/项目",
      "actions": "进入原对象；处理后保留该对象真实状态，不手动“全部完成”",
      "source": "原Task/Event/审核待办；待决定/待接件/受阻/待验收/未知",
      "detail": "GD"
    },
    {
      "id": "O01",
      "domain": "工作台总览",
      "group": "经营运营",
      "name": "目标与计划",
      "template": "list",
      "depth": 3,
      "fields": [
        "目标",
        "所属项目",
        "负责人",
        "目标期",
        "当前进度",
        "下一节点"
      ],
      "search": "名称/周期/项目/状态",
      "actions": "目标详情：指标口径、计划节点、关联任务；编辑目标/计划（有原授权）",
      "source": "原Project/Node/Goal Plan；计划/进行/受阻/暂停/完成/未知",
      "detail": "GD"
    },
    {
      "id": "O02",
      "domain": "工作台总览",
      "group": "经营运营",
      "name": "渠道与活动",
      "template": "list",
      "depth": 3,
      "fields": [
        "渠道",
        "活动",
        "负责人",
        "内容版本",
        "发布状态",
        "线索关联"
      ],
      "search": "渠道/活动/状态",
      "actions": "内容详情、预览、修改、发布记录；不模拟真实外发",
      "source": "原Channel/CRM；草稿/待发布/发布失败/已发布/未知，发布须真实回执",
      "detail": "GD"
    },
    {
      "id": "O03",
      "domain": "工作台总览",
      "group": "经营运营",
      "name": "经营指标",
      "template": "metrics",
      "depth": 3,
      "fields": [
        "指标名",
        "期间",
        "单位",
        "实际值",
        "目标",
        "口径"
      ],
      "search": "指标/周期/项目",
      "actions": "明细/关联事件；不承诺收益",
      "source": "原Analytics/Finance；未接/待核；不同币种不相加",
      "detail": "GD"
    },
    {
      "id": "O04",
      "domain": "工作台总览",
      "group": "经营运营",
      "name": "运营异常",
      "template": "list",
      "depth": 3,
      "fields": [
        "问题",
        "影响对象",
        "程度",
        "负责人",
        "下一动作",
        "状态"
      ],
      "search": "项目/状态/类型",
      "actions": "进入原任务/服务/客户对象、查看处置记录",
      "source": "原Event/Task；待处理/处理中/已核实解决/未知，不把消除显示等同修复",
      "detail": "GD"
    },
    {
      "id": "P01",
      "domain": "项目与交付",
      "group": "项目管理",
      "name": "项目列表",
      "template": "list",
      "depth": 3,
      "fields": [
        "名称",
        "客户/内部",
        "负责人及AI角色",
        "阶段",
        "下一节点",
        "更新",
        "预览/交付状态"
      ],
      "search": "名称/客户/阶段/负责人/自营类型",
      "actions": "PD：阶段与当前阻塞、需求范围、版本成果、关联任务、合同及交付、预览/意见/验收入口；客户各项目预览集中P08",
      "source": "原Project/CRM/Task；进行中/待确认/已交付/暂停/未知独立，暂停不因点击恢复",
      "detail": "PD"
    },
    {
      "id": "P02",
      "domain": "项目与交付",
      "group": "项目管理",
      "name": "自营项目",
      "template": "list",
      "depth": 3,
      "fields": [
        "名称",
        "客户/内部",
        "负责人及AI角色",
        "阶段",
        "下一节点",
        "更新",
        "预览/交付状态"
      ],
      "search": "名称/客户/阶段/负责人/自营类型",
      "actions": "PD：阶段与当前阻塞、需求范围、版本成果、关联任务、合同及交付、预览/意见/验收入口；客户各项目预览集中P08",
      "source": "原Project/CRM/Task；进行中/待确认/已交付/暂停/未知独立，暂停不因点击恢复",
      "detail": "PD"
    },
    {
      "id": "P03",
      "domain": "项目与交付",
      "group": "研发与版本",
      "name": "仓库与版本",
      "template": "list",
      "depth": 3,
      "fields": [
        "仓库名称",
        "项目",
        "版本",
        "负责人",
        "变更摘要",
        "状态"
      ],
      "search": "项目/版本/状态",
      "actions": "PV：版本说明、关联页面/任务/证据；查看原授权成果",
      "source": "Git/Registry；候选/已固定/待核；不从提交推验收",
      "detail": "PV"
    },
    {
      "id": "P04",
      "domain": "项目与交付",
      "group": "研发与版本",
      "name": "构建与制品",
      "template": "list",
      "depth": 3,
      "fields": [
        "制品名称",
        "版本",
        "项目",
        "构建结果",
        "测试结果"
      ],
      "search": "项目/版本/结果",
      "actions": "PV：构建过程摘要、产物、失败下一步、受控下载",
      "source": "Artifact/CI；待构建/构建中/成功/失败/未知",
      "detail": "PV"
    },
    {
      "id": "P05",
      "domain": "项目与交付",
      "group": "研发与版本",
      "name": "测试与质量",
      "template": "list",
      "depth": 3,
      "fields": [
        "测试名称",
        "项目",
        "版本",
        "覆盖范围",
        "结论",
        "责任人"
      ],
      "search": "项目/版本/结论",
      "actions": "测试详情、证据、关联问题任务；提交测试记录",
      "source": "原QA；未执行/通过/未通过/部分完成/未知",
      "detail": "GD"
    },
    {
      "id": "P06",
      "domain": "项目与交付",
      "group": "研发与版本",
      "name": "独立审核",
      "template": "list",
      "depth": 3,
      "fields": [
        "审核项",
        "项目",
        "版本",
        "审核人",
        "结论",
        "阻塞"
      ],
      "search": "项目/审核状态",
      "actions": "完整审查结论、修改意见/复验记录；作者不自批",
      "source": "原Audit；待审核/修改中/待复验/通过/不通过/未知",
      "detail": "GD"
    },
    {
      "id": "P07",
      "domain": "项目与交付",
      "group": "研发与版本",
      "name": "模块产品化",
      "template": "list",
      "depth": 3,
      "fields": [
        "模块",
        "项目",
        "负责人",
        "当前版本",
        "产品化阶段"
      ],
      "search": "名称/阶段",
      "actions": "模块详情：依赖兼容、文档、权利范围、产品/价格引用；修改/提交产品化结果",
      "source": "Module Registry；研发/待核权利/待验证/可产品化/未知，不因源码存在公开上架",
      "detail": "GD"
    },
    {
      "id": "P08",
      "domain": "项目与交付",
      "group": "客户预览与验收",
      "name": "客户项目预览",
      "template": "list",
      "depth": 3,
      "fields": [
        "客户",
        "项目",
        "可看页面数",
        "当前版本",
        "预览状态",
        "下一步"
      ],
      "search": "客户/项目/可预览状态",
      "actions": "PR：选项目版本/页面、受权预览、意见、历史；地址未核提示“预览入口待核实”",
      "source": "原PR122/Project；可预览/待准备/无权限/未接入，不猜URL",
      "detail": "PR"
    },
    {
      "id": "P09",
      "domain": "项目与交付",
      "group": "客户预览与验收",
      "name": "页面与版本",
      "template": "list",
      "depth": 3,
      "fields": [
        "页面名",
        "项目",
        "当前版本",
        "确认状态",
        "修改摘要"
      ],
      "search": "项目/页面/版本/状态",
      "actions": "PV/PR：版本比较、历史意见和确认记录",
      "source": "原Page/Version；待确认/已确认/修改中/待复验/未知",
      "detail": "PV"
    },
    {
      "id": "P10",
      "domain": "项目与交付",
      "group": "客户预览与验收",
      "name": "审核队列",
      "template": "list",
      "depth": 3,
      "fields": [
        "待审项目页面",
        "版本",
        "事项",
        "责任人",
        "状态"
      ],
      "search": "项目/责任人/状态",
      "actions": "PR：意见→原任务修订→同版复验；不另开Writer",
      "source": "原Preview/Changes；评论已提交≠已接任务≠修复完成",
      "detail": "PR"
    },
    {
      "id": "P11",
      "domain": "项目与交付",
      "group": "客户预览与验收",
      "name": "测试证据",
      "template": "list",
      "depth": 3,
      "fields": [
        "证据名",
        "项目",
        "版本",
        "类型",
        "验证结论"
      ],
      "search": "项目/版本/类型",
      "actions": "受控证据摘要/查看，返回原页面",
      "source": "原Evidence/QA；未执行/部分/有效/待核，不将本地合成测试当现场证据",
      "detail": "GD"
    },
    {
      "id": "P12",
      "domain": "项目与交付",
      "group": "客户预览与验收",
      "name": "客户验收",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目",
        "验收范围/版本",
        "验收主体",
        "结论",
        "未完成项"
      ],
      "search": "项目/版本/结论",
      "actions": "PA：整体验收清单、逐项结果、同版证据、意见；通过/退回仅有原有效主体权限的示例流程",
      "source": "原Acceptance；待验收/未通过/已验收/未核权，Owner后台身份不自动成为客户合同验收主体",
      "detail": "PA"
    },
    {
      "id": "P13",
      "domain": "项目与交付",
      "group": "交付与维护",
      "name": "发布与安装",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目",
        "发布/安装版本",
        "环境",
        "结果",
        "负责人"
      ],
      "search": "项目/环境/结果",
      "actions": "DL：安装回执、验证结果、影响与原记录",
      "source": "原Release/Install；未执行/执行中/失败/已安装/未知；本轮不执行",
      "detail": "DL"
    },
    {
      "id": "P14",
      "domain": "项目与交付",
      "group": "交付与维护",
      "name": "交付与归档",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目",
        "交付版本",
        "交付状态",
        "验收状态",
        "交付物"
      ],
      "search": "项目/状态",
      "actions": "DL：交付清单、归档、关联验收/尾款/上线状态各列",
      "source": "原Delivery；待交付/已交付/已归档/未知；交付≠上线",
      "detail": "DL"
    },
    {
      "id": "P15",
      "domain": "项目与交付",
      "group": "交付与维护",
      "name": "维护与退出",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目",
        "服务范围",
        "维护负责人",
        "服务状态",
        "到期/退出状态"
      ],
      "search": "项目/状态",
      "actions": "维护记录、续费引用、退出申请及导出/移交证据；不实际删数据",
      "source": "原Maintenance/Contract；维护中/暂停/退出处理中/已退出/未知",
      "detail": "GD"
    },
    {
      "id": "P16",
      "domain": "项目与交付",
      "group": "交付与维护",
      "name": "运行证据",
      "template": "list",
      "depth": 3,
      "fields": [
        "自营项目",
        "运行事项",
        "责任人",
        "结果摘要",
        "证据"
      ],
      "search": "项目/结果",
      "actions": "业务运行证据详情，只读查看原受控材料",
      "source": "原自营业务执行源；未执行/待核/失败/已核实，非自动组件运行记录",
      "detail": "GD"
    },
    {
      "id": "T01",
      "domain": "任务调度中心",
      "group": "任务调度",
      "name": "任务总览",
      "template": "dashboard",
      "depth": 3,
      "fields": [
        "关键/受阻/待接件/待验收任务",
        "负责人分布",
        "下一步"
      ],
      "search": "项目/责任人/任务类型",
      "actions": "所有卡→T02相应筛选/TD",
      "source": "原Task，不从心跳和接件自动推执行",
      "detail": "GD"
    },
    {
      "id": "T02",
      "domain": "任务调度中心",
      "group": "任务调度",
      "name": "任务列表",
      "template": "list",
      "depth": 3,
      "fields": [
        "任务名称",
        "项目",
        "负责人/角色编号",
        "状态",
        "进度",
        "最后有效回执",
        "下一步/阻塞"
      ],
      "search": "名称/业务编号/项目/角色/状态/类型",
      "actions": "TD：指令原业务正文、过程、依赖、结果链接、交接记录；发送指令/接件/提交结果/暂停恢复/验收仅按已有权限设计，暂停项目不提供自动恢复",
      "source": "原Registry/Supervisor/Task；未发送/已发送待接/已接未执行/进行中/受阻/失败/暂停/结果待验/已验收/未知",
      "detail": "TD"
    },
    {
      "id": "T03",
      "domain": "任务调度中心",
      "group": "任务调度",
      "name": "执行记录",
      "template": "list",
      "depth": 3,
      "fields": [
        "任务",
        "执行主体",
        "尝试记录",
        "执行状态",
        "有效回执",
        "结果"
      ],
      "search": "项目/任务/主体/状态",
      "actions": "TE：本次执行上下文、当前/下一阶段、阻塞、结果与证据；不展示未脱敏日志",
      "source": "原Attempt/Execution；排队/执行/失败/暂停/结束待验/未知",
      "detail": "TE"
    },
    {
      "id": "T04",
      "domain": "任务调度中心",
      "group": "角色与执行主体",
      "name": "固定角色",
      "template": "list",
      "depth": 3,
      "fields": [
        "固定角色编号",
        "名称",
        "职责",
        "项目",
        "任务",
        "状态"
      ],
      "search": "编号/名称/项目/状态",
      "actions": "RD：实际职责、关联任务、已知配置和原授权范围只读；编辑配置仅实际能力",
      "source": "原Role/Identity，编号待核；可用/忙碌/暂停/未知不代表权限",
      "detail": "RD"
    },
    {
      "id": "T05",
      "domain": "任务调度中心",
      "group": "角色与执行主体",
      "name": "临时实例",
      "template": "list",
      "depth": 3,
      "fields": [
        "临时实例编号",
        "原角色",
        "项目",
        "任务",
        "状态"
      ],
      "search": "编号/原角色/项目/状态",
      "actions": "RD：实例来源、当前任务、释放记录及结果关联；释放模拟保留历史不销毁任务",
      "source": "原Instance；待接/执行/已释放/失败/未知，编号样例不能证明真实创建",
      "detail": "RD"
    },
    {
      "id": "T06",
      "domain": "任务调度中心",
      "group": "角色与执行主体",
      "name": "执行器与服务",
      "template": "list",
      "depth": 3,
      "fields": [
        "执行器/服务名称",
        "编号",
        "职责",
        "项目",
        "连接/任务状态"
      ],
      "search": "名称/类型/项目/状态",
      "actions": "RD：配置状态、关联角色任务、原服务链接",
      "source": "原Executor/Service；未接/可用/异常/停用/未知，不把五分钟备份等自动组件混入",
      "detail": "RD"
    },
    {
      "id": "C01",
      "domain": "客户与业务",
      "group": "客户关系",
      "name": "客户与联系人",
      "template": "list",
      "depth": 3,
      "fields": [
        "客户名称",
        "脱敏联系人",
        "负责人",
        "关联项目/产品",
        "服务状态"
      ],
      "search": "客户/联系人/负责人/状态",
      "actions": "CD：客户概况、联系人、项目、需求、合同/订单/服务引用；查看/编辑已有客户资料",
      "source": "CRM，客户不是后台账号；联系信息仅合成/脱敏",
      "detail": "CD"
    },
    {
      "id": "C02",
      "domain": "客户与业务",
      "group": "客户关系",
      "name": "CRM线索",
      "template": "list",
      "depth": 3,
      "fields": [
        "线索名称",
        "渠道",
        "负责人",
        "需求概要",
        "阶段"
      ],
      "search": "名称/渠道/阶段",
      "actions": "线索详情、跟进记录、关联客户/需求；录入/编辑/跟进",
      "source": "CRM；新线索/跟进/已转需求/关闭/未知",
      "detail": "GD"
    },
    {
      "id": "C03",
      "domain": "客户与业务",
      "group": "客户关系",
      "name": "需求与范围",
      "template": "list",
      "depth": 3,
      "fields": [
        "需求名称",
        "客户",
        "范围版本",
        "负责人",
        "确认状态"
      ],
      "search": "客户/版本/状态",
      "actions": "RQ：架构方案、功能清单、范围变化与确认记录；编辑版本/记录客户意见，AI不代签",
      "source": "Requirement/SOW；草稿/待客户确认/已确认/变更待确认/未知",
      "detail": "RQ"
    },
    {
      "id": "C04",
      "domain": "客户与业务",
      "group": "客户关系",
      "name": "客户反馈",
      "template": "list",
      "depth": 3,
      "fields": [
        "反馈事项",
        "客户项目",
        "页面版本",
        "状态",
        "原任务"
      ],
      "search": "项目/版本/状态",
      "actions": "意见详情/关联PR/TD；修改意见回原任务",
      "source": "PR122/CRM；已提交/已接件/修订中/待复验/已复验/未知，复验≠项目验收",
      "detail": "GD"
    },
    {
      "id": "C05",
      "domain": "客户与业务",
      "group": "产品与服务",
      "name": "产品目录",
      "template": "list",
      "depth": 3,
      "fields": [
        "产品名",
        "模块版本",
        "负责人",
        "服务/交付状态"
      ],
      "search": "名称/版本/状态",
      "actions": "依赖、适用范围、教程支持/价格引用；编辑产品信息/查看交付",
      "source": "Registry，版本可用性待核；不默认新模块关闭",
      "detail": "GD"
    },
    {
      "id": "C06",
      "domain": "客户与业务",
      "group": "产品与服务",
      "name": "订阅与交付",
      "template": "list",
      "depth": 3,
      "fields": [
        "客户",
        "产品版本",
        "合同",
        "订阅期/单位",
        "权益",
        "交付/续费状态"
      ],
      "search": "客户/产品/状态",
      "actions": "订阅详情、当前服务期、续费规则/来源、开通和交付各列；编辑已有配置仅授权",
      "source": "Subscription/Entitlement；待开通/有效/即将到期/暂停/取消续期/未知；不自行设期限",
      "detail": "GD"
    },
    {
      "id": "C07",
      "domain": "客户与业务",
      "group": "产品与服务",
      "name": "套餐与价格",
      "template": "list",
      "depth": 3,
      "fields": [
        "产品套餐",
        "价格版本",
        "币种金额/周期",
        "适用范围",
        "生效状态"
      ],
      "search": "产品/币种/状态",
      "actions": "价格详情：一次性/固定/用量/第三方分列、政策影响预览；编辑草案/预览变化",
      "source": "原Price Book/Commercial；草稿/预览/已批准/生效/退役/未知按原规则；不新增审批",
      "detail": "GD"
    },
    {
      "id": "C08",
      "domain": "客户与业务",
      "group": "产品与服务",
      "name": "合同与权益",
      "template": "list",
      "depth": 3,
      "fields": [
        "合同名称/编号",
        "客户项目",
        "版本",
        "范围",
        "状态/权益"
      ],
      "search": "客户/项目/合同状态",
      "actions": "CT：合同正文受控摘要、费用条款、权益、确认记录、订单关联；查看/编辑已有草稿",
      "source": "Contract/Entitlement；草案/待确认/生效/终止/未知；草案不可作为已生效收费依据",
      "detail": "CT"
    },
    {
      "id": "F01",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "报价与订单",
      "template": "list",
      "depth": 3,
      "fields": [
        "报价/订单编号",
        "客户项目",
        "类型",
        "原币金额",
        "履约/付款状态"
      ],
      "search": "编号/客户/类型/币种/状态",
      "actions": "OD：范围/合同/价格快照、一次性与周期费用、首尾款分项、退款/收款关联；查看/编辑报价草稿",
      "source": "Commercial/Order；草稿/待确认/待付款/部分付款/已付款/取消/未知，付款不等于履约",
      "detail": "OD"
    },
    {
      "id": "F02",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "账单与付款",
      "template": "list",
      "depth": 3,
      "fields": [
        "账单编号",
        "客户订单",
        "账期",
        "币种应付/实收",
        "付款状态"
      ],
      "search": "客户/账期/币种/状态",
      "actions": "FD：金额分项、支付回执、核销/退款引用；查看原凭证，不手工标记真实到账",
      "source": "Finance/Payment/Invoice；待付款/部分/已收/待核销/已核销/未知",
      "detail": "FD"
    },
    {
      "id": "F03",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "钱包与用量",
      "template": "list",
      "depth": 3,
      "fields": [
        "客户/合同",
        "账期",
        "币种",
        "余额状态",
        "用量单位及费用状态"
      ],
      "search": "客户/合同/期间/币种",
      "actions": "FD：账本流水与用量来源分别区块；余额只读、不直接改账；充值不是收入",
      "source": "Wallet/Usage/Ledger；已核实/估算/待核；模型估算不是扣费",
      "detail": "FD"
    },
    {
      "id": "F04",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "成本与利润",
      "template": "metrics",
      "depth": 3,
      "fields": [
        "项目产品",
        "期间币种",
        "收入确认",
        "实际/估计成本",
        "利润口径"
      ],
      "search": "项目/期间/币种/结算状态",
      "actions": "成本类别/证据、分摊依据与收入对应；钻取原账单/订单",
      "source": "Finance；暂估/待核算/已结算，不同币种分组；不把营业流水当净利润",
      "detail": "GD"
    },
    {
      "id": "F05",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "对账与退款",
      "template": "list",
      "depth": 3,
      "fields": [
        "对账/退款事项",
        "原订单",
        "币种金额",
        "差异",
        "负责人",
        "状态"
      ],
      "search": "订单/类型/状态",
      "actions": "FD：原支付引用、原因、已存在处理流程/回执；申请/处理为原型状态，不真付款",
      "source": "Finance/Ledger；待核对/差异待处理/处理中/已核实/未知，不抹历史分录",
      "detail": "FD"
    },
    {
      "id": "F06",
      "domain": "客户与业务",
      "group": "订单与财务",
      "name": "推荐与结算",
      "template": "list",
      "depth": 3,
      "fields": [
        "伙伴脱敏名",
        "政策版本",
        "期间币种",
        "佣金基数/调整",
        "结算状态"
      ],
      "search": "伙伴/期间/币种/状态",
      "actions": "FD：收入/成本/毛利/比例/累计差额/冲回和依据、原付款回执；查看/对账",
      "source": "原Settlement/Referral Ledger；预估/待确认/可结算/已结算/付款待核；不本轮套固定门槛",
      "detail": "FD"
    },
    {
      "id": "E01",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "生态成员",
      "template": "list",
      "depth": 3,
      "fields": [
        "成员/组织",
        "身份类型",
        "关联产品/项目",
        "状态"
      ],
      "search": "名称/类型/状态",
      "actions": "ED：来源/合作资料、原客户/伙伴引用；查看/编辑既有资料",
      "source": "Identity/Contribution；待核/有效/暂停；不是自动开后台账号",
      "detail": "ED"
    },
    {
      "id": "E02",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "贡献记录",
      "template": "list",
      "depth": 3,
      "fields": [
        "贡献事件",
        "成员",
        "项目产品",
        "类别",
        "已核贡献值/单位",
        "依据"
      ],
      "search": "成员/项目/类别",
      "actions": "ED：归属、比例、证据/纠错历史；查看原记录",
      "source": "Contribution，不由充值订单金额推贡献",
      "detail": "ED"
    },
    {
      "id": "E03",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "声誉与凭证",
      "template": "list",
      "depth": 3,
      "fields": [
        "成员",
        "声誉类别/凭证",
        "签发/有效状态"
      ],
      "search": "成员/类别/状态",
      "actions": "ED：来源、验证/纠错记录；受权查看",
      "source": "Reputation/Credential，声誉不等于现金或权限",
      "detail": "ED"
    },
    {
      "id": "E04",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "生态权益",
      "template": "list",
      "depth": 3,
      "fields": [
        "成员",
        "权益名称/政策版本",
        "范围",
        "有效状态"
      ],
      "search": "成员/类型/状态",
      "actions": "ED：来源、适用条款、关联事件；编辑草稿契约按原授权",
      "source": "Entitlement/ECV；待核/有效/暂停/已失效，未核不默认可交易",
      "detail": "ED"
    },
    {
      "id": "E05",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "伙伴与推荐",
      "template": "list",
      "depth": 3,
      "fields": [
        "伙伴",
        "合作/归因状态",
        "关联客户脱敏数",
        "政策"
      ],
      "search": "名称/状态",
      "actions": "ED：伙伴合同、绑定依据、关联F06；查看/更正申请按原规则",
      "source": "CRM/Referral，不推多级推荐",
      "detail": "ED"
    },
    {
      "id": "E06",
      "domain": "客户与业务",
      "group": "共享生态",
      "name": "方案知识",
      "template": "list",
      "depth": 3,
      "fields": [
        "方案名称",
        "版本",
        "来源项目",
        "权利范围",
        "产品化状态"
      ],
      "search": "名称/版本/状态",
      "actions": "ED：知识摘要、来源/复用许可、关联P07；查看/编辑",
      "source": "Solution Graph/Provenance，不公开客户私有资料",
      "detail": "ED"
    },
    {
      "id": "W01",
      "domain": "官网管理",
      "group": "导航与页面",
      "name": "导航管理",
      "template": "tree-list",
      "depth": 3,
      "fields": [
        "导航名称",
        "层级",
        "目标",
        "排序",
        "显隐"
      ],
      "search": "名称/层级/显隐",
      "actions": "WN编辑名称/父项/原合法目标/排序/显隐，预览/保存；拖排有上下移动替代",
      "source": "原站点内容源；草稿/已保存/待发布/发布失败/已发布/未知",
      "detail": "WN"
    },
    {
      "id": "W02",
      "domain": "官网管理",
      "group": "导航与页面",
      "name": "页面模块",
      "template": "editor-list",
      "depth": 3,
      "fields": [
        "页面标题",
        "模块摘要",
        "更新时间",
        "发布状态"
      ],
      "search": "标题/状态",
      "actions": "WE完整页：模块顺序、标题文案、素材、按钮文字链接；编辑/保存草稿/预览/发布记录/历史版本",
      "source": "原CMS，日常内容更新不整站重发，真实能力待核",
      "detail": "WE"
    },
    {
      "id": "W03",
      "domain": "官网管理",
      "group": "定制与交付",
      "name": "开发中项目展示",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目/案例名",
        "公开标题",
        "展示状态",
        "预览",
        "授权状态"
      ],
      "search": "名称/展示/授权状态",
      "actions": "编辑公开摘要/素材/排序/上下架/预览；公开内容与内部材料分开",
      "source": "原Project+原公开授权+Content；未经确认不公开，既有双授权不是新增审批",
      "detail": "GD"
    },
    {
      "id": "W04",
      "domain": "官网管理",
      "group": "定制与交付",
      "name": "已完成案例",
      "template": "list",
      "depth": 3,
      "fields": [
        "项目/案例名",
        "公开标题",
        "展示状态",
        "预览",
        "授权状态"
      ],
      "search": "名称/展示/授权状态",
      "actions": "编辑公开摘要/素材/排序/上下架/预览；公开内容与内部材料分开",
      "source": "原Project+原公开授权+Content；未经确认不公开，既有双授权不是新增审批",
      "detail": "GD"
    },
    {
      "id": "W05",
      "domain": "官网管理",
      "group": null,
      "name": "站点设置",
      "template": "settings",
      "depth": 2,
      "fields": [
        "站点名称",
        "品牌素材",
        "公开联系",
        "站点基本设置"
      ],
      "search": "设置分区",
      "actions": "完整设置页查看/编辑/保存/取消；不把服务器凭据塞站点设置",
      "source": "原Site Settings；未接/待核/已保存/失败",
      "detail": "GD"
    },
    {
      "id": "W06",
      "domain": "官网管理",
      "group": null,
      "name": "发布记录",
      "template": "list",
      "depth": 2,
      "fields": [
        "发布对象",
        "内容版本",
        "操作者",
        "发布时间",
        "结果"
      ],
      "search": "对象/版本/结果",
      "actions": "发布详情、历史版本对比、回到编辑；恢复旧内容先预览，不真实回滚",
      "source": "原Publication；待发布/失败/已发布/未知，模拟成功不当真实上线",
      "detail": "GD"
    },
    {
      "id": "S01",
      "domain": "平台设置",
      "group": null,
      "name": "管理员设置",
      "template": "settings",
      "depth": 2,
      "fields": [
        "管理员名称",
        "角色",
        "项目范围",
        "功能范围",
        "操作范围",
        "状态",
        "通知偏好"
      ],
      "search": "管理员/角色/项目/状态",
      "actions": "AD完整页编辑实际授权范围、偏好、操作记录；明确当前范围和变更差异；保存为模拟，不创建真实账号",
      "source": "原Identity/RBAC/Audit；待Owner确定/已核授权/未知；不是任何内部人员自动全权",
      "detail": "AD"
    },
    {
      "id": "S02",
      "domain": "平台设置",
      "group": null,
      "name": "模型接入",
      "template": "settings",
      "depth": 2,
      "fields": [
        "供应商",
        "模型",
        "用途",
        "连接状态",
        "最近检测",
        "负责人",
        "费用来源",
        "密钥配置状态"
      ],
      "search": "供应商/模型/用途/状态",
      "actions": "MD完整页添加/编辑连接、测试/启停、模型用途绑定；查看历史检测结果；字段只显示“已配置/未配置/待核实”，无值、掩码、SecretRef串或复制按钮",
      "source": "原ModelControl/ConnectionManager；未接入/待检测/可用/异常/停用/未知；当前凭据不收集，测试仅演示",
      "detail": "MD"
    },
    {
      "id": "S03",
      "domain": "平台设置",
      "group": null,
      "name": "通知设置",
      "template": "settings",
      "depth": 2,
      "fields": [
        "通知事项",
        "渠道",
        "接收范围",
        "通知偏好/送达状态"
      ],
      "search": "类型/渠道",
      "actions": "完整页编辑已有偏好/查看送达；不默认静默或强关",
      "source": "原Notification/Outbox；未接/待发送/已送达/失败/未知",
      "detail": "GD"
    },
    {
      "id": "S04",
      "domain": "平台设置",
      "group": null,
      "name": "操作记录",
      "template": "list",
      "depth": 2,
      "fields": [
        "操作者",
        "操作对象",
        "动作",
        "结果",
        "时间"
      ],
      "search": "对象/人员/动作/期间/结果",
      "actions": "脱敏操作详情/关联对象；无密钥/客户原始日志",
      "source": "原Audit；成功/失败/待核，记录“按钮点击”不冒操作落库",
      "detail": "GD"
    },
    {
      "id": "S05",
      "domain": "平台设置",
      "group": "服务与维护",
      "name": "服务器及服务概况",
      "template": "list",
      "depth": 3,
      "fields": [
        "服务器/服务名称",
        "用途项目",
        "负责人",
        "连接/健康状态"
      ],
      "search": "名称/项目/状态",
      "actions": "SD：服务摘要、关联告警/故障/维护，不放自动组件记录",
      "source": "原Service Catalog/Monitoring；正常/异常/未知；不从“存在”推健康",
      "detail": "SD"
    },
    {
      "id": "S06",
      "domain": "平台设置",
      "group": "服务与维护",
      "name": "健康与告警",
      "template": "list",
      "depth": 3,
      "fields": [
        "服务告警",
        "影响",
        "级别",
        "负责人",
        "状态"
      ],
      "search": "服务/级别/状态",
      "actions": "告警详情/原处置任务关联",
      "source": "原Monitoring，未接≠无告警",
      "detail": "GD"
    },
    {
      "id": "S07",
      "domain": "平台设置",
      "group": "服务与维护",
      "name": "事件与故障",
      "template": "list",
      "depth": 3,
      "fields": [
        "事件故障",
        "项目服务",
        "影响",
        "处置人",
        "下一步"
      ],
      "search": "对象/状态",
      "actions": "处置记录、关联任务/证据",
      "source": "原Incident；待处理/处理中/待核实恢复/已恢复/未知",
      "detail": "GD"
    },
    {
      "id": "S08",
      "domain": "平台设置",
      "group": "服务与维护",
      "name": "检查点与恢复",
      "template": "list",
      "depth": 3,
      "fields": [
        "服务项目",
        "检查点/恢复事项",
        "版本",
        "验证结论"
      ],
      "search": "服务/项目/结论",
      "actions": "原恢复方案/授权和演练证据，不提供自动组件备份运行时间/错误/仓列表",
      "source": "原Checkpoint/Recovery，未验证/验证中/已核实/未知；本轮不恢复",
      "detail": "GD"
    },
    {
      "id": "S09",
      "domain": "平台设置",
      "group": "服务与维护",
      "name": "到期与安全退出",
      "template": "list",
      "depth": 3,
      "fields": [
        "服务资源",
        "合同到期",
        "负责人",
        "续期/退出状态"
      ],
      "search": "资源/项目/状态",
      "actions": "原合同条款、退出移交记录；不自动停机/删资源",
      "source": "原Service/Contract；日期未知待核实，不编期限",
      "detail": "GD"
    },
    {
      "id": "S10",
      "domain": "平台设置",
      "group": "接入配置",
      "name": "模块接入",
      "template": "list",
      "depth": 3,
      "fields": [
        "模块名称",
        "版本",
        "用途",
        "项目",
        "接入状态"
      ],
      "search": "模块/项目/状态",
      "actions": "模块详情/配置状态/关联产品，不新建Registry",
      "source": "原Module Registry；未接/待核/已核接入/异常",
      "detail": "GD"
    },
    {
      "id": "S11",
      "domain": "平台设置",
      "group": "接入配置",
      "name": "渠道接入",
      "template": "list",
      "depth": 3,
      "fields": [
        "渠道名称",
        "用途",
        "负责人",
        "授权配置状态",
        "送达状态"
      ],
      "search": "渠道/用途/状态",
      "actions": "原连接配置状态/通知关联；不展示Token/临时码",
      "source": "原Connector/Channel；未接/授权待核/可用/异常/未知",
      "detail": "GD"
    }
  ],
  "detailPages": [
    [
      "PD",
      "项目详情",
      "P01/P02"
    ],
    [
      "PV",
      "版本成果详情",
      "P03/P04/P09"
    ],
    [
      "PR",
      "项目预览与意见工作区",
      "P08/P10"
    ],
    [
      "PA",
      "整项目验收详情",
      "P12"
    ],
    [
      "DL",
      "交付详情",
      "P13/P14"
    ],
    [
      "TD",
      "任务详情（含业务交接记录）",
      "T02"
    ],
    [
      "TE",
      "执行记录详情",
      "T03"
    ],
    [
      "RD",
      "角色/实例/执行主体详情",
      "T04/T05/T06"
    ],
    [
      "CD",
      "客户详情",
      "C01"
    ],
    [
      "RQ",
      "需求与范围详情",
      "C03"
    ],
    [
      "CT",
      "合同与权益详情",
      "C08"
    ],
    [
      "OD",
      "报价/订单详情",
      "F01"
    ],
    [
      "FD",
      "财务对象详情",
      "F02/F03/F05/F06"
    ],
    [
      "ED",
      "生态对象详情",
      "E01—E06"
    ],
    [
      "WE",
      "官网页面完整编辑页",
      "W02"
    ],
    [
      "WN",
      "导航项编辑",
      "W01"
    ],
    [
      "MD",
      "模型连接配置完整页",
      "S02"
    ],
    [
      "AD",
      "管理员范围完整编辑页",
      "S01"
    ],
    [
      "SD",
      "服务器/服务详情",
      "S05"
    ],
    [
      "GD",
      "其余对象详情",
      "所属列表"
    ]
  ]
};
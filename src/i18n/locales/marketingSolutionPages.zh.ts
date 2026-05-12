/**
 * Solution landing copy sourced from static HTML under docs/marketing reference
 * (user-provided exports from solutions/*.html).
 */

export const marketingSolutionPagesZh = {
  securityTeam: {
    docTitle: "安全运营团队 — Security Manus",
    navTitle: "安全运营团队",
    heroEyebrow: "面向",
    heroTitle: "你在 SOC 里的 AI 搭档。",
    lead: "把分类、范围界定与剧本执行交给智能体；你保留掌控权——审核裁定、引用证据、落地处置动作。",
    benefitsHeading: "你能获得什么",
    benefits: [
      {
        title: "少琐事，多判断",
        desc: "重复的初判与范围界定由智能体完成，你把时间花在决策上。",
      },
      {
        title: "有引用的裁定，而非直觉",
        desc: "每条结论都附带证据与明确的下一步。",
      },
      {
        title: "同一控制台，三类工作",
        desc: "分类、应急响应与狩猎共用同一智能体与同一条调查脉络。",
      },
      {
        title: "默认满足审计友好",
        desc: "动作可追溯、可回放，便于复核与汇报。",
      },
    ],
    stepsHeading: "一个班次如何运转",
    steps: [
      { title: "收件箱汇聚", body: "告警、用户上报与 IOC 进入同一队列。" },
      { title: "智能体初判", body: "自动生成裁定、证据与建议动作草稿。" },
      { title: "你复核", body: "批准、修订或升级；你的决定塑造下一轮调查。" },
      { title: "智能体执行", body: "在你授权下执行遏制、线索扩展与工单草稿。" },
      { title: "干净交接", body: "结案沉淀为可复用、带引用的剧本，供下一班使用。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "班次摘要 — 18:00–02:00",
    sampleBody: `已由智能体结案（经你批准）
  · 47 封用户上报邮件 → 3 封钓鱼，44 封无害
  · 12 条 SIEM 告警 → 10 条关闭，2 条升级
  · 6 次 IOC 扩展 → 1 台主机确认感染（HOSTNAME）

升级至应急响应
  ·「不可能差旅 + 新 OAuth 授权」（Okta）— 确认账户接管
  · HOSTNAME 可疑二进制 — 沙箱评分 9.4/10

知识沉淀
  · 由今夜调查生成 2 份新剧本
  · 建议评审 4 条检测规则

本班次节省工时   约 4.8 小时人工分类工作量`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "更少琐事", label: "常规分类从「小时」降到「分钟」" },
      { kpi: "更快定界", label: "默认跨日志联动扩展" },
      { kpi: "知识留存", label: "每个案件都成为带引用的剧本" },
    ],
    trustHeading: "贴合团队真实工作方式",
    trustBullets: [
      "一线/二线分析师：自动分类、证据支撑的裁定、一键升级。",
      "应急响应：单一 IOC 即可产出范围、时间线与报告草稿。",
      "威胁狩猎：自然语言扩展线索，结案时可生成新检测草稿。",
    ],
  },
  msspMdr: {
    docTitle: "MSSP 与 MDR — Security Manus",
    navTitle: "MSSP 与 MDR",
    heroEyebrow: "面向",
    heroTitle: "在不降低交付标准的前提下，让每位分析师服务更多租户。",
    lead: "原生多租户设计。智能体按租户完成分类、范围界定与报告——团队始终在闭环内并保持品牌一致。",
    benefitsHeading: "你能获得什么",
    benefits: [
      {
        title: "多租户隔离",
        desc: "每个租户独立的上下文、数据与审计轨迹，杜绝跨租户串扰。",
      },
      {
        title: "交付标准化",
        desc: "跨租户一致的结构化报告——用你的模板与语气。",
      },
      {
        title: "可白标",
        desc: "分析师控制台与客户门户均可品牌化。",
      },
      {
        title: "算得清的毛利",
        desc: "每位分析师承载更多租户，单位服务成本更低。",
      },
    ],
    stepsHeading: "如何运作",
    steps: [
      { title: "接入租户", body: "按租户配置连接器、数据驻留与策略。" },
      { title: "路由告警", body: "每个租户的告警进入其隔离的智能体上下文。" },
      { title: "智能体调查", body: "在该租户内完成分类与范围界定，并保留引用。" },
      { title: "分析师复核", body: "在同一控制台跨租户批准、编辑或升级。" },
      { title: "交付", body: "品牌化报告与工单草稿推送到租户门户。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "每周租户简报 — Acme Bank",
    sampleBody: `周概览
  · 告警接入     1,284
  · 新建工单     38
  · 已结案       35
  · SLA 达标率   99.4%

重点事件
  · OAuth 路径账户接管尝试 — 已遏制（Okta + M365）
  · HOSTNAME 恶意软件 — 已处置（EDR 隔离 + 清理）

覆盖与卫生
  · 邮件钓鱼：2 类发件模式检测改进
  · 终端：3 条策略建议

未来 7 天建议
  · 强制 12 个特权账号启用 MFA
  · 新增 2 条检测（附草稿查询）`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "更多租户", label: "不加人头的前提下提升人均承载" },
      { kpi: "可辩护的交付", label: "每次都有证据引用" },
      { kpi: "稳定 SLA", label: "跨租户与班次的一致性" },
    ],
    trustHeading: "信任与部署",
    trustBullets: [
      "租户隔离：连接器、策略与审计历史按租户拆分。",
      "客户自控的报告与证据留存与导出策略。",
      "多租户 SaaS 或单租户私有化部署（VPC / 本地）。",
    ],
  },
  securityLeader: {
    docTitle: "安全管理者 — Security Manus",
    navTitle: "安全管理者",
    heroEyebrow: "面向",
    heroTitle: "可辩护的决策，证据在背后支撑。",
    lead: "把调查转化为可辩护的决策——高管叙事、审计级历史记录，以及清晰的下月风险敞口。",
    benefitsHeading: "你能获得什么",
    benefits: [
      {
        title: "董事会级叙事",
        desc: "按月呈现管理层可复述的故事——每条叙述有据可查。",
      },
      {
        title: "审计级历史",
        desc: "决策、证据与动作随时间可追溯、可回放。",
      },
      {
        title: "覆盖可见性",
        desc: "覆盖了什么、遗漏了什么，以及原因。",
      },
      {
        title: "更低的服务成本",
        desc: "减少手工报告与频繁上下文切换。",
      },
    ],
    stepsHeading: "如何运作",
    steps: [
      { title: "选择窗口", body: "选定时间范围（周 / 月 / 季）与范围。" },
      { title: "智能体聚合", body: "跨栈汇总工单、证据、动作与结果。" },
      { title: "起草简报", body: "把运营产出转为带引用的高管叙事。" },
      { title: "你编辑", body: "调整侧重点、补充上下文，对齐你的汇报风格。" },
      { title: "导出", body: "PDF / 文档输出，必要时附带审计附录。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "高管简报 — 2026 年 4 月",
    sampleBody: `关键结果
  · MTTD  8 分钟 → 6 分钟
  · MTTR  62 分钟 → 41 分钟
  · 一线结案率  78% → 91%

重大事件（附引用）
  · 基于 OAuth 的账户接管尝试 — 已遏制；未发现确认的数据外泄
  · HOSTNAME 恶意软件 — 23 分钟内隔离并完成处置

开放风险
  · 12 个特权账号尚未强制 MFA
  · 约 8% 终端覆盖不完整

投资建议
  · 关闭 MFA 缺口（优先级 1）
  · 新增 2 条检测（附草稿查询）
  · 改进终端接入剧本（由智能体生成）

下月重点
  · 借自动化与培训闭环降低重复分类类别`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "可辩护", label: "每条结论背后都有证据" },
      { kpi: "可对比", label: "月度指标与趋势一目了然" },
      { kpi: "更低服务成本", label: "更少手工汇报负担" },
    ],
    trustHeading: "信任与部署",
    trustBullets: [
      "默认只读：先做汇报而不改动生产系统。",
      "可回放审计附录：决策、证据与动作均有引用。",
      "监管场景可选本地 / VPC 部署。",
    ],
  },
  phishingEmail: {
    docTitle: "钓鱼与邮件 — Security Manus",
    navTitle: "钓鱼与邮件",
    heroEyebrow: "场景",
    heroTitle: "几秒完成钓鱼分类，而不是几小时。",
    lead: "拖入 .eml 或粘贴 URL。获得裁定、IOC 与遏制方案——每条论断都有证据引用。",
    benefitsHeading: "它能做什么",
    benefits: [
      {
        title: "用户上报邮件分类",
        desc: "将可疑邮件转发到共享收件箱，智能体分类并返回带证据的裁定。",
      },
      {
        title: "高管邮箱筛查",
        desc: "为高价值邮箱优先识别高风险邮件——快速、一致、可审计。",
      },
      {
        title: "活动聚类",
        desc: "相似邮件归为同一活动，一次调查覆盖大量上报。",
      },
      {
        title: "URL 与附件安全检测",
        desc: "粘贴 URL 或上传附件，约一分钟内给出基于沙箱行为的裁定。",
      },
    ],
    stepsHeading: "如何运作",
    steps: [
      { title: "提交", body: "拖入 .eml、转发到智能体收件箱，或粘贴 URL。" },
      { title: "解析", body: "提取邮件头、SPF/DKIM/DMARC、链接与附件。" },
      { title: "沙箱引爆", body: "附件与 URL 在隔离沙箱中执行，形成行为证据。" },
      { title: "关联", body: "IOC 在你的环境中扩展，并与历史活动与情报对齐。" },
      { title: "结论", body: "主智能体撰写裁定、引用证据并提出遏制步骤。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "钓鱼裁定 — 证据引用",
    sampleBody: `裁定        钓鱼 — 高置信度（0.94）
活动簇       「薪资诱饵」簇 · 自 2024-11 活跃
关键证据
  · SPF / DKIM / DMARC 均未通过并被隔离
  · 发件域 secure-payroll-alerts.com（注册仅 4 天）
  · 附件 Payroll_Update.js — 混淆下载器
  · C2  mal-c2[.]xyz  → 185.x.x.x
建议动作
  · 隔离用户邮箱中 7 封同类邮件
  · 在邮件网关封禁发件域
  · 对 2 名点击链接的用户重置凭证`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "约 25 分钟 → 约 2 分钟", label: "常规上报的裁定耗时" },
      { kpi: "3–5 倍", label: "每班次每位分析师可处理更多上报" },
      { kpi: "审计友好", label: "每次裁定均附带引用证据" },
    ],
    trustHeading: "信任与部署",
    trustBullets: [
      "附件在隔离沙箱引爆；邮件正文可选零留存模式。",
      "SSO + RBAC + 智能体动作全链路审计。",
      "监管环境可选本地 / VPC 部署。",
    ],
  },
  malwareAnalysis: {
    docTitle: "恶意软件分析 — Security Manus",
    navTitle: "恶意软件分析",
    heroEyebrow: "场景",
    heroTitle: "裁定任意二进制——从沙箱到 ATT&CK 映射。",
    lead: "提交样本。获得裁定、行为证据与 ATT&CK 矩阵——无需自建沙箱环境。",
    benefitsHeading: "它能做什么",
    benefits: [
      {
        title: "可疑文件分类",
        desc: "快速裁定来自 EDR、邮件或用户上传的文件，并以证据支撑。",
      },
      {
        title: "应急响应样本裁定",
        desc: "在事件中秒级拿到裁定——无需等待手工逆向排期。",
      },
      {
        title: "红队样本分析",
        desc: "对照测试环境验证载荷行为与 TTP 覆盖。",
      },
      {
        title: "供应链组件检查",
        desc: "上线前对第三方组件给出一致的裁定报告。",
      },
    ],
    stepsHeading: "如何运作",
    steps: [
      { title: "上传", body: "上传文件或哈希；压缩包在安全流程中解压。" },
      { title: "静态分析", body: "检查字符串、导入、签名、熵与签名状态。" },
      { title: "动态引爆", body: "在隔离沙箱执行，记录时间线与衍生工件。" },
      { title: "映射", body: "观察到的行为映射到 MITRE ATT&CK 技法与战术。" },
      { title: "结论", body: "主智能体返回裁定、评分、ATT&CK 图与完整执行日志。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "恶意软件裁定 — ATT&CK 映射",
    sampleBody: `裁定        恶意 — Loader → Cobalt Strike beacon
评分          9.4 / 10
家族          Bumblebee（高置信）

ATT&CK 技法
  T1027   混淆文件或信息
  T1055   进程注入
  T1071.001  应用层协议：Web

观察到的行为
  · 以可疑 DLL 路径拉起 rundll32.exe
  · 每 60 秒（带抖动）向 185.x.x.x 回连
  · 通过计划任务「WindowsUpdateAssist」持久化

建议动作
  · 在 EDR 封禁哈希
  · 在最近 30 天代理日志中对 C2 IP 一键狩猎`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "约 45 分钟 → 约 4 分钟", label: "常规样本人均耗时" },
      { kpi: "ATT&CK-ready", label: "TTP 自动映射，无需手工打标" },
      { kpi: "可辩护", label: "默认附带执行日志与工件" },
    ],
    trustHeading: "信任与部署",
    trustBullets: [
      "沙箱运行在隔离 VPC；样本不跨租户混用。",
      "样本与工件留存策略由客户控制。",
      "敏感环境可选私有化部署。",
    ],
  },
  threatInvestigation: {
    docTitle: "威胁调查 — Security Manus",
    navTitle: "威胁调查",
    heroEyebrow: "场景",
    heroTitle: "从告警或 IOC，到完整攻击故事。",
    lead: "向智能体提供 SIEM 告警、IOC 或自然语言问题；它跨栈调查并返回可结案的报告。",
    benefitsHeading: "调查从何开始",
    benefits: [
      {
        title: "从告警入手",
        desc: "把嘈杂的 SIEM/EDR 告警变成范围清晰、动作明确的结案工单。",
      },
      {
        title: "从 IOC 入手",
        desc: "单一指标跨日志与终端扩展，构建完整攻击图。",
      },
      {
        title: "从问题入手",
        desc: "用自然语言提问，获得可执行、带引用的答案与定制剧本。",
      },
      {
        title: "可结案报告",
        desc: "裁定、攻击时间线、影响范围与遏制方案——端到端引用。",
      },
    ],
    stepsHeading: "如何运作",
    steps: [
      {
        title: "接入",
        body: "从告警、IOC 或自然语言问题开始（界面、API 或 SIEM Webhook）。",
      },
      { title: "规划", body: "主智能体决定调度哪些子智能体及采集哪些证据。" },
      {
        title: "扩展",
        body: "溯源子智能体跨身份、终端、代理、DNS 与邮件界定影响范围。",
      },
      {
        title: "证据",
        body: "发现附带时间戳、来源与工件，便于复核。",
      },
      { title: "结论", body: "输出裁定、攻击时间线、影响范围与遏制计划。" },
    ],
    sampleHeading: "示例输出",
    sampleCardTitle: "调查报告 — 范围清晰、引用完整、可执行",
    sampleBody: `来自告警（Okta）—「不可能差旅登录」
裁定     确认账户接管

攻击时间线
  14:02   自 NL 的 VPS 登录成功
  14:04   MFA 推送被批准（用户后否认）
  14:09   为「邮件备份」应用创建 OAuth 授权
  14:12   经 Graph API 外泄约 1.2 GB 邮箱内容

范围     1 名用户 · 2 个 OAuth 授权 · 1 条转发规则
动作     吊销会话、移除转发规则、强制重置密码与 MFA、对 VPS IP 做 14 天狩猎

---

来自 IOC — 185.x.x.x

跨栈命中
  代理   近 7 天 3 台内网主机回连
  DNS    mal-c2[.]xyz 解析 14 次到此 IP
  EDR    1 台主机：rundll32.exe 回连

影响     1 台主机确认感染（HOSTNAME）；2 台疑似接触
动作     EDR 隔离主机 · 边界封禁 IP/域 · 抓取内存镜像

---

来自自然语言问题
问   「我们的 Confluence 是否暴露于 CVE-2024-XXXX？」

答   附 NVD 与厂商公告的直白结论
    面向你们栈的分步处置剧本
    资产清单一键狩猎
    给资产负责人的工单草稿`,
    whyHeading: "为什么重要",
    metrics: [
      { kpi: "小时 → 分钟", label: "常规调查结案用时" },
      { kpi: "完整范围", label: "默认跨日志联动扩展" },
      { kpi: "可复用", label: "每个案件沉淀为带引用剧本" },
    ],
    trustHeading: "信任与部署",
    trustBullets: [
      "连接器默认只读；写操作需显式批准。",
      "智能体动作全记录、可回放，满足审计与复盘。",
      "监管环境可选本地 / VPC 部署。",
    ],
  },
} as const;

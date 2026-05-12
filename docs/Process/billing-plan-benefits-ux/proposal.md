# Proposal: Billing plan catalog & benefits UX

## Problem

用户对「套餐」的感知弱于市面主流 AI 订阅产品：

1. **`Billing.tsx` / `OfficialPricing.tsx` / `AccountOverview.tsx` 仅突出「包含 token 数」**（`included_tokens_per_period` 本地化数字），缺少**可按场景理解的权益叙事**（例如模型档位、优先级、工作台能力、导出/协作等）。
2. **数据结构侧 `billing_plans` 仅有** `slug, display_name, included_tokens_per_period, monthly_price_usd, stripe_price_id, sort_order`**，没有可下发的「权益条目」**，导致前后端都只能展示计费原子单位而非产品价值。
3. 与 **`billing-token-stripe-usage`** 已落地的 Stripe + token 门禁相比，本次缺口在**产品线与法务/运营可控的套餐说明层**，不涉及替换计费内核。

## Goals

- **G-01** 用户对每个套餐能获得什么有清晰、可比较的描述（对齐 **通用对话/IDE** 类产品，以及 **Manus、Lovable** 等 **Agent·应用生成器** 的典型「**额度 + 并列能力/限制**」心智）。
- **G-02** Token 仍可作为「高级 / 技术指标」或可折叠说明存在，但**不作为唯一卖点**。
- **G-03** 营销页（`/pricing`）与站内账单页（`/billing`）、账户概览的**话术结构一致**，避免外站承诺与站内不符。
- **G-04** 权益内容可由**产品与运营迭代**（避免每次改文案都发版全站 hardcode — 须有明确策略）。

## Non-goals

- 不改变 Stripe 商品价格与订阅生命周期（若无单独决策）。
- 不重新设计整条 Usage 流水线（`/usage` 已有明细）；仅在必要时增加「与套餐相关的说明入口」联动。
- 不在本交付内承诺具体第三方模型名录的最终法律文案（可由运营填入）。

## Users & stakeholders

- **终端用户**：选套餐、续费前决策。
- **产品 / 运营**：维护套餐卖点与对比口径。
- **工程**：扩展 `billing_plans` API 与安全发布策略。

## Scope tier

按 **delivery-pipeline**：**Standard**（多页面 + API/schema + i18n + E2E）。

## Dependencies / related work

- 既有实现：**`docs/Process/billing-token-stripe-usage/`**（计费、Stripe、token 门禁、`GET /billing/plans`）。
- 当前 **`GET /billing/plans`** 返回字段：`slug`, `display_name`, `included_tokens_per_period`, `monthly_price_usd`, `sort_order`（不含权益载荷）。

## Success metrics（建议）

- 定价/Billing 页跳出后「未下单但返回帮助/FAQ」类支持问题减少（需后续工单埋点）。
- 套餐卡片上**至少展示 N 条可验证权益**（N 由 `acceptance-ui.md` 约定，默认 ≥4 条结构化项 + 技术指标区）。

## Market reference (简述)

主流产品共同点（可作 UX 对齐目标，而非功能承诺）：

| 维度 | 常见做法 |
|------|----------|
| 计价 | 月费/年费 + 「Most popular」角标 |
| 用量表述 | **用户语言**优先（messages、requests、credits、`~xh` Codex-style），技术细节脚注或 expandable |
| 权益 | **项目符号列表**：模型访问、新功能尝鲜、优先级、上传/上下文、Agents/Projects 等 |
| 决策支持 | **多档对比表**（Free vs Plus vs Pro）；企业档单独询价 CTA |
| 边界说明 | 「订阅不含 API」「高峰动态限制」等 **一行免责声明** |

**OpenAI**：分层多档，强调模型能力、Agents/Projects/Codex 等 bundled 能力说明（见其 [pricing / plans](https://openai.com/pricing/)）。  
**Anthropic**：分层 + 「Max nx」倍数容量叙事，辅以功能列表与支持渠道说明（见其 [pricing](https://www.anthropic.com/pricing)）。  
**IDE 类（Cursor 等）**：常混合「产品能力条款 + 请求/配额说明 + Pro/Business 分栏」，并强调离线/隐私或团队条款（本产品可选对齐信息架构而非逐字照抄）。

### Agent / 应用构建类（Manus、Lovable）— 更贴近本产品的范式

这类产品与「纯聊天」不同：**Credits/用量**仍展示，但几乎总是和 **模式/能力档位、协作与发布边界、结构化配额** 写在一起；用户一眼看到的是「能做什么事」「和同档差在哪」，其次才是「每月多少点」。

| 维度 | **Manus**（典型结构） | **Lovable**（典型结构） | 对 SecManus 的可借鉴点 |
|------|------------------------|-------------------------|-------------------------|
| 额度叙事 | **月额度 +（免费档）每日额度**；文档中说明 Credits 随任务复杂度变化 | **月额度 + 每日 bonus credits** 等复合口径；免费档「日额度封顶到月」 | 除周期内 token 外，可增加 **「约等于」说明**或 **折叠区解释**（复杂任务消耗更高）；若产品有 **日限额** 可同屏展示 |
| 能力分层 | **Chat vs Agent**、**模型档位**（如 Lite / 标准 / Max）、进阶能力（研究、部署、幻灯片等）| **Free / Pro / Business / Enterprise** 以 **可见权益差** 驱动升级（域名、徽章、角色、SSO、审计等） | 将 **工作区能力** 写成 bullet：**推理/工具链、报告导出、分享、（若有）沙箱/E2B、知识库**；与 **`billing-token-stripe-usage` 的 token 计费**用「技术明细」区承接 |
| 结构化限制 | **并发任务数、定时/计划任务配额**（文档型披露） | **公开 vs 工作区、团队席位、发布边界**（产品型披露） | 若后端将来有 **并发分析、队列优先级**，建议在套餐上 **用数字行**展示（与 Manus 的 concurrent 类似），避免用户只盯着 token |
| 商业插件 | **加购额度、长期有效**等说明 | **按需加购 credits、学生/校园价**入口 | 若有 **加购 / top-up**，在 Billing 二级区或 FAQ 链一行；本交付可先留 **「用量与加购」** 文档链接位 |
| 团队 | **Team**：共享额度池、管理、协作 | **Business**：SSO、角色、安全中心 | Enterprise 行强调 **席位、共享策略、支持渠道**（与现 `enterprise` CTA 一致） |

**官方参考（结构会随产品迭代变化，以页面为准）：**

- Manus：[Plans & Pricing](https://www.manus.ai/pricing)、[Plans 文档](https://manus.im/docs/introduction/plans)、[Help Center 定价说明](https://help.manus.im/en/articles/11711111-what-is-the-current-membership-pricing-for-manus)
- Lovable：[Pricing](https://lovable.dev/pricing/)、[Plans and credits 文档](https://docs.lovable.dev/introduction/plans-and-credits)、[Billing FAQ](https://lovable.dev/faq/billing/plans)

**结论（写进方案）：** SecManus 不应停留在「一排 token」；应借鉴 Manus/Lovable 的 **「额度条 + 能力 bullet +（可选）硬配额行 + 团队/企业差异」** 组合，与已有 ChatGPT/Claude 类叙事互补。

## Decisions / confirmations（持续更新）

- **结构化配额（quota）**：产品将提供 **并发分析、支持的文件类型、支持的安全日志类型** 等可对用户展示的真值；以 **`quota_hints`**（见 [design.md](./design.md) § `quota_hints` 稳定 ID）下发，对齐 Manus「并发任务」式披露；另可扩展 **队列优先级、知识库容量、沙箱** 等。
- **Credits 计量基线（locked, 2026-05-07）**：采用 **A + C 折叠**——主显「**Credits / 月（≈ $N AI 用量）**」与 USD 等价（与 `gate.py` 的 USD cap 同单位），折叠区保留 token 与 USD 明细。**B 抽象点、D 参考模型等价本期不做。** 详见 [design.md](./design.md) § **Metering semantics**。
- **`included_tokens_per_period` 清退（locked, 2026-05-07）**：本字段**全面退役**。本交付分两阶段执行（详见 [design.md](./design.md) § **Tokens retirement plan**）——
  - **Stage 1（本期实现）**：API（`GET /billing/plans`、`GET /billing/summary`）**停止返回**；前端 `BillingPlanRow` 与 UI **删除引用**；`tokens_used_period` 由 `tokens_used_period_estimate` 取代，主进度条切到 USD。
  - **Stage 2（紧随的小交付）**：DB 列 `billing_plans.included_tokens_per_period` **drop**；clean up `_list_plans_*` SQL select、迁移注释中的 「Ultra included_tokens = 3x Pro at seed time」描述。
- **Credits 默认值（locked, 2026-05-07）**：与现有 `monthly_price_usd` 对齐，第一版以 1:1 USD 等价为基线（运营可后续在 DB 调整）：

  | slug | `monthly_price_usd` | `included_credits_usd` | 说明 |
  |------|---------------------|------------------------|-------|
  | `free` | 0 | **5** | 给免费用户可见的「Credits / 月」起点；与 spend cap 行为不冲突 |
  | `pro` | 40 | **40** | 1:1 |
  | `ultra` | 100 | **100** | 1:1（保持与现 Stripe 价一致；不再 3× token） |
  | `enterprise` | 0 | **0** | 走联系销售 / 定制 |

- **权益数据源（locked, 2026-05-07）**：**JSONB（`features_json` / `tagline_json` / `quota_hints`）+ 代码 i18n 兜底**——运营可热改 DB；DB 缺失时按 `slug` 走前端 i18n bundle，不返回空白卡片。

## Open questions（需你在 Phase 2→3 gate 确认）

1. **权益数据源**：更倾向于 **JSONB（运营可 DB 编辑）** 还是 **代码内 i18n + slug 映射（强类型、审计友好）**，或二者混合？
2. **Ultra vs Pro**：除 Credits/USD 额度倍数外，**硬性能力差异**是否固定为 **`quota_hints` + benefit_lines**（并发、文件/日志类型、沙箱等具体数值由运营填入）？
3. **Enterprise**：标准条款（SLA、审计、VPC、专属模型路由）是否已有对外一页话述？
4. **token 硬闸**：当前实现以 **USD 封顶** 为硬闸（见 `gate.py`）；是否需在后续迭代增加 **token 配额** 硬闸，与「Credits 估算」更严格绑定？

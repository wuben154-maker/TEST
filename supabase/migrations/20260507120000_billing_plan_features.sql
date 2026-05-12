-- Billing plan benefits UX (billing-plan-benefits-ux).
-- Stage 1 of tokens retirement plan: add Credits/USD primary fields and structured benefit
-- payloads on billing_plans. Legacy column included_tokens_per_period is RETAINED here and
-- marked DEPRECATED; it will be dropped in Stage 2 (slug: billing-tokens-column-drop).

-- ---------------------------------------------------------------------------
-- New columns on billing_plans
-- ---------------------------------------------------------------------------
ALTER TABLE public.billing_plans
  ADD COLUMN IF NOT EXISTS included_credits_usd NUMERIC(10, 2) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS credits_label TEXT NOT NULL DEFAULT 'credits',
  ADD COLUMN IF NOT EXISTS features_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS tagline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS quota_hints JSONB NOT NULL DEFAULT '[]'::jsonb;

-- DEPRECATED: included_tokens_per_period will be removed in a follow-up migration
-- (slug: billing-tokens-column-drop). New code MUST NOT read or write this column.
COMMENT ON COLUMN public.billing_plans.included_tokens_per_period IS
  'DEPRECATED — removed in Stage 2 (billing-tokens-column-drop). Use included_credits_usd.';

COMMENT ON COLUMN public.billing_plans.included_credits_usd IS
  'Primary user-facing AI usage budget for the plan, in USD-equivalent (Credits = USD baseline).';

COMMENT ON COLUMN public.billing_plans.features_json IS
  'Ordered list of benefit lines: [{"id":"...","text":{"en":"...","zh":"..."}}].';

COMMENT ON COLUMN public.billing_plans.tagline_json IS
  'Optional short subtitle, per-locale: {"en":"...","zh":"..."}.';

COMMENT ON COLUMN public.billing_plans.quota_hints IS
  'Structured numeric/list limits: [{"id":"concurrent_analyses","value":"3","label":{"en":"...","zh":"..."}}].';

-- ---------------------------------------------------------------------------
-- Seed Credits + benefits for the four canonical plans.
-- These rows can be edited in Supabase Studio after deployment without a code release.
-- ---------------------------------------------------------------------------
UPDATE public.billing_plans SET
  included_credits_usd = 5,
  credits_label = 'credits',
  tagline_json = jsonb_build_object(
    'en', 'For exploring SecManus on a small budget',
    'zh', '小额度试用 SecManus 的入门方案'
  ),
  features_json = jsonb_build_array(
    jsonb_build_object('id','workspace_basic','text', jsonb_build_object('en','Full SecManus workspace with reasoning panel and tools','zh','完整 SecManus 工作区，含推理面板与工具')),
    jsonb_build_object('id','models_basic','text', jsonb_build_object('en','Access to standard analysis models','zh','可使用标准分析模型')),
    jsonb_build_object('id','exports_basic','text', jsonb_build_object('en','Export reports to Markdown / DOCX','zh','导出报告为 Markdown / DOCX')),
    jsonb_build_object('id','community_support','text', jsonb_build_object('en','Community support','zh','社区支持'))
  ),
  quota_hints = jsonb_build_array(
    jsonb_build_object('id','concurrent_analyses','value','1','label', jsonb_build_object('en','Concurrent analyses','zh','并发分析数')),
    jsonb_build_object('id','queue_priority','value','standard','label', jsonb_build_object('en','Queue priority','zh','排队优先级')),
    jsonb_build_object('id','supported_file_types','value','PDF, DOCX, TXT, common code','label', jsonb_build_object('en','Supported file types','zh','文件类型')),
    jsonb_build_object('id','supported_security_log_types','value','Syslog, common JSON alerts','label', jsonb_build_object('en','Supported security log types','zh','安全日志类型'))
  )
WHERE slug = 'free';

UPDATE public.billing_plans SET
  included_credits_usd = 40,
  credits_label = 'credits',
  tagline_json = jsonb_build_object(
    'en', 'For security teams running daily investigations',
    'zh', '面向每天做安全调查的小团队'
  ),
  features_json = jsonb_build_array(
    jsonb_build_object('id','models_pro','text', jsonb_build_object('en','Access to frontier-class analysis models','zh','可使用旗舰级分析模型')),
    jsonb_build_object('id','deep_research','text', jsonb_build_object('en','Deep research subagent and tool chains','zh','可调用 Deep Research 子代理与工具链')),
    jsonb_build_object('id','exports_pro','text', jsonb_build_object('en','Markdown, DOCX, PDF and image exports','zh','支持 Markdown / DOCX / PDF / 图片导出')),
    jsonb_build_object('id','share_pro','text', jsonb_build_object('en','Shared reports via signed links','zh','支持签名链接共享报告')),
    jsonb_build_object('id','knowledge_pro','text', jsonb_build_object('en','Knowledge base for project context','zh','项目级知识库上下文')),
    jsonb_build_object('id','priority_pro','text', jsonb_build_object('en','Priority queue during peak load','zh','高峰时段优先排队'))
  ),
  quota_hints = jsonb_build_array(
    jsonb_build_object('id','concurrent_analyses','value','3','label', jsonb_build_object('en','Concurrent analyses','zh','并发分析数')),
    jsonb_build_object('id','queue_priority','value','high','label', jsonb_build_object('en','Queue priority','zh','排队优先级')),
    jsonb_build_object('id','supported_file_types','value','PDF, Office, code, PCAP, EVTX, ZIP','label', jsonb_build_object('en','Supported file types','zh','文件类型')),
    jsonb_build_object('id','supported_security_log_types','value','Syslog, CEF, LEEF, JSON alerts, EVTX','label', jsonb_build_object('en','Supported security log types','zh','安全日志类型'))
  )
WHERE slug = 'pro';

UPDATE public.billing_plans SET
  included_credits_usd = 100,
  credits_label = 'credits',
  tagline_json = jsonb_build_object(
    'en', 'For heavy-duty research and high-volume analysis',
    'zh', '面向高强度研究与大体量分析'
  ),
  features_json = jsonb_build_array(
    jsonb_build_object('id','models_ultra','text', jsonb_build_object('en','Everything in Pro, plus extended-thinking models where available','zh','包含 Pro 全部能力；可优先使用扩展推理模型')),
    jsonb_build_object('id','sandbox_ultra','text', jsonb_build_object('en','E2B / cloud sandbox for malware and dynamic checks','zh','可使用 E2B / 云沙箱进行恶意样本与动态分析')),
    jsonb_build_object('id','concurrency_ultra','text', jsonb_build_object('en','Higher concurrency for parallel investigations','zh','更高并发用于并行调查')),
    jsonb_build_object('id','exports_ultra','text', jsonb_build_object('en','All exports plus large-report assembly','zh','全部导出格式，含长篇报告组装')),
    jsonb_build_object('id','knowledge_ultra','text', jsonb_build_object('en','Larger knowledge base capacity','zh','更大的知识库容量')),
    jsonb_build_object('id','priority_ultra','text', jsonb_build_object('en','Top-priority queue and faster turnaround','zh','最高优先级队列与更快响应'))
  ),
  quota_hints = jsonb_build_array(
    jsonb_build_object('id','concurrent_analyses','value','10','label', jsonb_build_object('en','Concurrent analyses','zh','并发分析数')),
    jsonb_build_object('id','queue_priority','value','top','label', jsonb_build_object('en','Queue priority','zh','排队优先级')),
    jsonb_build_object('id','supported_file_types','value','PDF, Office, code, PCAP, EVTX, ZIP, raw memory','label', jsonb_build_object('en','Supported file types','zh','文件类型')),
    jsonb_build_object('id','supported_security_log_types','value','Syslog, CEF, LEEF, JSON alerts, EVTX, custom SIEM','label', jsonb_build_object('en','Supported security log types','zh','安全日志类型')),
    jsonb_build_object('id','e2b_sandbox','value','enabled','label', jsonb_build_object('en','Cloud sandbox','zh','云沙箱'))
  )
WHERE slug = 'ultra';

UPDATE public.billing_plans SET
  included_credits_usd = 0,
  credits_label = 'credits',
  tagline_json = jsonb_build_object(
    'en', 'Custom usage, controls, and support',
    'zh', '定制用量、安全控制与服务支持'
  ),
  features_json = jsonb_build_array(
    jsonb_build_object('id','custom_usage','text', jsonb_build_object('en','Custom monthly Credits / usage budget','zh','定制每月 Credits / 用量额度')),
    jsonb_build_object('id','sso_audit','text', jsonb_build_object('en','SSO, audit logs, and admin controls','zh','SSO、审计日志与管理员控制')),
    jsonb_build_object('id','dedicated_support','text', jsonb_build_object('en','Dedicated support and onboarding','zh','专属支持与导入')),
    jsonb_build_object('id','vpc_or_byok','text', jsonb_build_object('en','VPC / private routing or BYO LLM keys (on request)','zh','可申请 VPC 私有路由 / 自带 LLM 密钥')),
    jsonb_build_object('id','custom_quotas','text', jsonb_build_object('en','Custom concurrency, queue priority, and KB capacity','zh','定制并发、队列优先级与知识库容量'))
  ),
  quota_hints = jsonb_build_array(
    jsonb_build_object('id','concurrent_analyses','value','custom','label', jsonb_build_object('en','Concurrent analyses','zh','并发分析数')),
    jsonb_build_object('id','queue_priority','value','dedicated','label', jsonb_build_object('en','Queue priority','zh','排队优先级')),
    jsonb_build_object('id','supported_file_types','value','custom','label', jsonb_build_object('en','Supported file types','zh','文件类型')),
    jsonb_build_object('id','supported_security_log_types','value','custom','label', jsonb_build_object('en','Supported security log types','zh','安全日志类型'))
  )
WHERE slug = 'enterprise';

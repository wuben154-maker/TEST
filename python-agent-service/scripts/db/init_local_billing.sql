-- Local billing tables (profiles FK). Run after scripts/db/init_local_db.sql if not merged.
-- Aligns with supabase/migrations/*billing* for app/billing/* logic.

CREATE TABLE IF NOT EXISTS billing_plans (
  slug TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  -- DEPRECATED: included_tokens_per_period is removed in Stage 2 (billing-tokens-column-drop).
  -- Kept here so existing local databases continue to satisfy NOT NULL during Stage 1.
  included_tokens_per_period BIGINT NOT NULL DEFAULT 0,
  monthly_price_usd NUMERIC(10, 2) NOT NULL DEFAULT 0,
  stripe_price_id TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  included_credits_usd NUMERIC(10, 2) NOT NULL DEFAULT 0,
  credits_label TEXT NOT NULL DEFAULT 'credits',
  features_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  tagline_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  quota_hints JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- Idempotent column adds for existing databases that pre-date the new fields.
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS included_credits_usd NUMERIC(10, 2) NOT NULL DEFAULT 0;
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS credits_label TEXT NOT NULL DEFAULT 'credits';
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS features_json JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS tagline_json JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE billing_plans
  ADD COLUMN IF NOT EXISTS quota_hints JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS user_billing_profile (
  user_id UUID PRIMARY KEY REFERENCES profiles(user_id) ON DELETE CASCADE,
  stripe_customer_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_billing_profile_stripe_customer
  ON user_billing_profile (stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
  plan_slug TEXT NOT NULL REFERENCES billing_plans (slug),
  stripe_subscription_id TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'inactive',
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions (user_id);

CREATE TABLE IF NOT EXISTS model_pricing (
  model_id TEXT NOT NULL,
  usd_per_million_input NUMERIC(14, 6) NOT NULL,
  usd_per_million_output NUMERIC(14, 6) NOT NULL,
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, effective_from)
);

CREATE TABLE IF NOT EXISTS llm_usage_events (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects (id) ON DELETE SET NULL,
  request_id TEXT NOT NULL DEFAULT '',
  model_id TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(14, 6) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_events_user_created
  ON llm_usage_events (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_usage_events_request
  ON llm_usage_events (user_id, request_id);

CREATE TABLE IF NOT EXISTS user_billing_settings (
  user_id UUID PRIMARY KEY REFERENCES profiles(user_id) ON DELETE CASCADE,
  monthly_spend_cap_usd NUMERIC(12, 2) NOT NULL DEFAULT 100.00,
  arrears_allowance_usd NUMERIC(12, 2) NOT NULL DEFAULT 5.00,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  id TEXT PRIMARY KEY,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT,
  livemode BOOLEAN
);

INSERT INTO billing_plans (slug, display_name, included_tokens_per_period, monthly_price_usd, stripe_price_id, sort_order, included_credits_usd, credits_label)
VALUES
  ('free', 'Free', 500000, 0, NULL, 0, 5, 'credits'),
  ('pro', 'Pro', 1000000, 40, NULL, 1, 40, 'credits'),
  ('ultra', 'Ultra', 3000000, 100, NULL, 2, 100, 'credits'),
  ('enterprise', 'Enterprise', 0, 0, NULL, 3, 0, 'credits')
ON CONFLICT (slug) DO UPDATE SET
  included_credits_usd = EXCLUDED.included_credits_usd,
  credits_label = EXCLUDED.credits_label;

UPDATE billing_plans SET
  tagline_json = jsonb_build_object('en','For exploring SecManus on a small budget','zh','小额度试用 SecManus 的入门方案'),
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

UPDATE billing_plans SET
  tagline_json = jsonb_build_object('en','For security teams running daily investigations','zh','面向每天做安全调查的小团队'),
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

UPDATE billing_plans SET
  tagline_json = jsonb_build_object('en','For heavy-duty research and high-volume analysis','zh','面向高强度研究与大体量分析'),
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

UPDATE billing_plans SET
  tagline_json = jsonb_build_object('en','Custom usage, controls, and support','zh','定制用量、安全控制与服务支持'),
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

INSERT INTO model_pricing (model_id, usd_per_million_input, usd_per_million_output, effective_from)
VALUES
  ('google/gemini-3-flash-preview', 0.15, 0.60, timestamptz '2026-01-01 00:00:00+00'),
  ('google/gemini-3.1-pro-preview', 2.00, 8.00, timestamptz '2026-01-01 00:00:00+00'),
  ('google/gemini-3.1-flash-lite-preview', 0.08, 0.32, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/moonshotai/kimi-k2.6', 0.60, 2.40, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/anthropic/claude-sonnet-4.6', 3.00, 15.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/anthropic/claude-opus-4.7', 15.00, 75.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/google/gemini-3.1-pro-preview', 2.00, 8.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/google/gemini-3-flash-preview', 0.15, 0.60, timestamptz '2026-01-01 00:00:00+00')
ON CONFLICT (model_id, effective_from) DO NOTHING;

DROP TRIGGER IF EXISTS update_user_billing_profile_updated_at ON user_billing_profile;
CREATE TRIGGER update_user_billing_profile_updated_at
  BEFORE UPDATE ON user_billing_profile
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_subscriptions_updated_at ON user_subscriptions;
CREATE TRIGGER update_user_subscriptions_updated_at
  BEFORE UPDATE ON user_subscriptions
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_billing_settings_updated_at ON user_billing_settings;
CREATE TRIGGER update_user_billing_settings_updated_at
  BEFORE UPDATE ON user_billing_settings
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

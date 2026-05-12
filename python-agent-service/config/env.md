# Environment Variables Configuration

This document describes all environment variables used by the Python Agent Service.

## Agent Mode Configuration

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `AGENT_MODE` | Agent execution mode | `deepagent` | `deepagent`, `simple` |
| `DATABASE_MODE` | Database backend | `local` | `supabase`, `local` |

## Database Configuration

### Local PostgreSQL (when DATABASE_MODE=local)

| Variable | Description | Default |
|----------|-------------|---------|
| `LOCAL_DB_HOST` | PostgreSQL host | `localhost` |
| `LOCAL_DB_PORT` | PostgreSQL port | `5432` |
| `LOCAL_DB_NAME` | Database name | `secmanus` |
| `LOCAL_DB_USER` | Database user | `postgres` |
| `LOCAL_DB_PASSWORD` | Database password | `postgres` |

### Supabase (when DATABASE_MODE=supabase)

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes |

## API Keys

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key | Optional |
| `GOOGLE_API_KEY` | Google Gemini API key | Optional |
| `DOUBAO_API_KEY` | Doubao/Volcengine API key | Optional |
| `KIMI_API_KEY` | Kimi (Moonshot) API key | Optional |
| `GLM_API_KEY` | GLM (Zhipu) API key | Optional |
| `OPENROUTER_API_KEY` | OpenRouter unified model gateway API key | Optional |
| `OPENROUTER_APP_URL` | Optional OpenRouter attribution URL (`HTTP-Referer`) | Optional |
| `OPENROUTER_APP_TITLE` | Optional OpenRouter attribution title (`X-OpenRouter-Title`) | Optional |
| `LOVABLE_API_KEY` | Lovable AI Gateway key | Optional |
| `VIRUSTOTAL_API_KEY` | VirusTotal API key | Optional |

## External API URLs

### AI Providers

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_BASE_URL` | Google Gemini API base URL | `https://generativelanguage.googleapis.com/v1beta` |
| `DOUBAO_API_BASE_URL` | Doubao/Volcengine API base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| `KIMI_API_BASE_URL` | Kimi (Moonshot) OpenAI-compatible base URL | `https://api.moonshot.cn/v1` |
| `GLM_API_BASE_URL` | GLM (Zhipu) OpenAI-compatible base URL | `https://open.bigmodel.cn/api/paas/v4` |
| `LOVABLE_AI_GATEWAY_URL` | Lovable AI Gateway URL | `https://ai.gateway.lovable.dev/v1` |
| OpenRouter gateway base URL | Configured in `config/llm_gateway.yaml` provider `openrouter.base_url` | `https://openrouter.ai/api/v1` |

### Security Services

| Variable | Description | Default |
|----------|-------------|---------|
| `VIRUSTOTAL_API_BASE_URL` | VirusTotal API base URL | `https://www.virustotal.com/api/v3` |
| `VIRUSTOTAL_GUI_BASE_URL` | VirusTotal web GUI base URL | `https://www.virustotal.com/gui` |

### Web search APIs (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `TAVILY_API_KEY` | Tavily Search API; tried first when set | None |
| `SERPER_API_KEY` | [Serper.dev](https://serper.dev) Google SERP API; after Tavily, before Crawl4AI | None |
| `SERPER_API_BASE_URL` | Serper API host (POST `{base}/search`) | `https://google.serper.dev` |

### Crawl4AI (Web Search & URL Scraping)

| Variable | Description | Default |
|----------|-------------|---------|
| `CRAWL4AI_URL` | Crawl4AI API base URL | `http://localhost:11235` |
| `CRAWL4AI_API_TOKEN` | Crawl4AI API token (optional, for secured deployment) | None |
| `CRAWL4AI_PROXY_SERVER` | Optional HTTP(S) proxy for SERP crawls (e.g. residential) | None |
| `WEB_SEARCH_ENGINE` | `google` or `bing` (HTML scraping, not official APIs) | `google` |
| `FIRECRAWL_API_URL` | Firecrawl API URL (deprecated) | Auto-detected |
| `FIRECRAWL_API_KEY` | Firecrawl API key (deprecated) | Optional |

> **Note**: `web_search` tries Tavily, then Serper (if keys are set), then Crawl4AI (scrapes Google or Bing HTML per `WEB_SEARCH_ENGINE`), then HTTP+BeautifulSoup. `scrape_url` uses Crawl4AI first. For Railway: `CRAWL4AI_URL=https://your-app.up.railway.app`

## LangSmith (Observability)

| Variable | Description | Default |
|----------|-------------|---------|
| `LANGSMITH_API_KEY` | LangSmith API key | Optional |
| `LANGSMITH_PROJECT` | LangSmith project name | `security-deep-agent` |
| `LANGSMITH_TRACING` | Enable tracing | `false` |

## Billing / Stripe (`docs/Process/billing-token-stripe-usage/`)

| Variable | Description | Default |
|----------|-------------|---------|
| `BILLING_ENFORCE` | When `true`, enforce start-of-request billing gate (DB-backed) | `false` |
| `STRIPE_SECRET_KEY` | Stripe secret API key | Optional |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | Optional |
| `STRIPE_PRICE_PRO_MONTHLY` | Stripe Price ID for Pro ($40/mo) | Optional |
| `STRIPE_PRICE_ULTRA_MONTHLY` | Stripe Price ID for Ultra ($100/mo) | Optional |
| `BILLING_FREE_INCLUDED_TOKENS` | Default included tokens for Free tier (app override; DB seed may differ) | `500000` |
| `BILLING_DEFAULT_MONTHLY_SPEND_CAP_USD` | Default monthly spend ceiling (USD) for new users | `100` |
| `BILLING_DEFAULT_ARREARS_USD` | Small overage allowed before blocking next analyze | `5` |
| `BILLING_MAX_MONTHLY_SPEND_CAP_USD` | Server-side max for `PATCH /billing/settings` | `100` |
| `BILLING_CHECKOUT_SUCCESS_URL` | Stripe Checkout `success_url` | Optional |
| `BILLING_CHECKOUT_CANCEL_URL` | Stripe Checkout `cancel_url` | Optional |
| `BILLING_PORTAL_RETURN_URL` | Stripe Billing Portal `return_url` | Optional |

Apply migration `supabase/migrations/20260408120000_billing_token_stripe_usage.sql` for schema and plan seeds.

## Server Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Server bind host | `0.0.0.0` |
| `PORT` | Server bind port | `8000` |
| `WORKERS` | Number of worker processes | `4` |
| `RELOAD` | Enable auto-reload (dev mode) | `true` |
| `TRUST_X_FORWARDED_FOR` | When `true`, use the leftmost `X-Forwarded-For` IP as client IP (trusted reverse proxy only) | `false` |
| `LOGIN_IP_GEO_LOOKUP_ENABLED` | On successful login, resolve public client IP to country via ip-api.com | `true` |
| `LOGIN_IP_GEO_TIMEOUT_SECONDS` | HTTP timeout for IP geo lookup | `2.5` |

Apply `scripts/db/20260409120000_user_login_events_ip_country.sql` (and Supabase `20260409120000_user_login_events_ip_country.sql`) so `user_login_events.ip_country` exists.

### Uploads and analyze attachments

| Variable | Description | Default |
|----------|-------------|---------|
| `UPLOAD_DIR` | Root directory for stored uploads | `./uploads` |
| `MAX_UPLOAD_FILES_PER_BATCH` | Max files per `POST /uploads` | `10` |
| `MAX_UPLOAD_BYTES_PER_FILE` | Max bytes per uploaded file | `104857600` (100 MiB) |
| `MAIN_AGENT_MANIFEST_SNIFF_BYTES_PER_FILE` | Optional per-file preview bytes in analyze manifest | `4096` |
| `MAIN_AGENT_MANIFEST_SNIFF_BYTES_TOTAL` | Cap on sniff previews per analyze turn | `16384` |
| `ATTACHMENT_INLINE_MAX_TOTAL_BYTES` | Max total inline JSON attachment bytes (legacy clients) | `65536` |
| `ALLOW_LEGACY_FLAT_UPLOAD_PATHS` | Allow anonymous `/uploads/<session>/...` without `s_` prefix | `true` |

**Anonymous uploads:** v1 does not enforce TTL on disk; plan periodic cleanup of `UPLOAD_DIR/s_*` (or equivalent) in ops if needed.

## Agent Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `DEFAULT_MODEL` | Default AI model | `google/gemini-2.5-flash` |
| `MAX_ITERATIONS` | Maximum agent iterations | `20` |
| `TIMEOUT_SECONDS` | Request timeout | `300` |
| `READ_FILE_DEFAULT_LIMIT` | Default line count for `read_file` when caller omits `limit` | `1000` |

## Config files (non-env)

| File | Purpose |
|------|---------|
| `config/tool_presentation.yaml` | **Tiered registry** (recommended): `common_tools` declares **in order** which tools `create_common_tools()` mounts for main + default subagents (`enabled: true` + known implementation). `system_tools` / `subagent_tools` are SSE/UI (and related) only. Legacy flat `tools:` still supported if no tier keys are present. Hot-reloaded by mtime. |

## Context Management

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTEXT_MAX_TOKENS` | Trigger summarization threshold | `4000` |
| `CONTEXT_KEEP_RECENT` | Keep last N messages in full | `20` |
| `CONTEXT_OFFLOAD_THRESHOLD` | Chars for large output offload | `1000` |
| `MEMORY_TTL_HOURS` | TTL for short-term memories | `24` |
| `STORE_BACKEND` | Memory store backend | `memory` |
| `CONTEXT_MEMORY_ENABLED` | Enable derived-memory merge + inject blocks on `/analyze` | `false` |
| `DERIVED_LAYER_MODEL` | Gateway model id for optional turn summary (empty = rules-only) | (empty) |
| `CONTEXT_INJECT_MAX_CHARS` | Max chars for combined `[Project memory]` / `[User context]` | `6000` |
| `CONTEXT_HYDRATE_ENABLED` | Prepend last K DB messages as `[Hydrated from DB history]` | `false` |
| `CONTEXT_HYDRATE_MAX_TURNS` | Max user/assistant pairs for hydrate | `3` |
| `CONTEXT_MERGE_ASYNC` | Reserved (v1: merge is inline after persist) | `false` |
| `CONTEXT_SUMMARY_INPUT_MAX_CHARS` | Cap assistant excerpt sent to derived-layer LLM | `8000` |

## Example .env File

```bash
# Mode
AGENT_MODE=deepagent
DATABASE_MODE=local

# Local Database
LOCAL_DB_HOST=localhost
LOCAL_DB_PORT=5432
LOCAL_DB_NAME=secmanus
LOCAL_DB_USER=postgres
LOCAL_DB_PASSWORD=postgres

# API Keys (at least one required)
GOOGLE_API_KEY=your-google-api-key

# External URLs (optional, use defaults)
# GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com/v1beta
# VIRUSTOTAL_API_BASE_URL=https://www.virustotal.com/api/v3

# Server
HOST=0.0.0.0
PORT=8000
```

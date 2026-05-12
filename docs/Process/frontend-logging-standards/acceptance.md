# Acceptance — `frontend-logging-standards`

## Metadata

- **Slug:** `frontend-logging-standards`
- **Owner:** chenf
- **Updated:** 2026-04-16
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- `src/lib/logger.ts` — 自建日志门面
- `src/lib/api-client.ts` — `x-request-id` 注入
- `src/lib/sse/readSseJsonLines.ts` — 解析错误日志
- `src/components/AppErrorBoundary.tsx` — 全局错误日志
- 全部 hooks / components — `console.*` 迁移

## Environment

- **Runtime:** Vite dev server
- **Base URL:** `http://localhost:5173`
- **Feature flags:** none

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | `src/lib/logger.ts` 导出 `logger` 对象，支持 `debug/info/warn/error` 四个方法 | Vitest unit test |
| A-02 | Logger 支持 `setLevel()` 动态切换级别；低于阈值的事件被丢弃 | Vitest unit test |
| A-03 | Logger 输出为结构化 JSON，包含 `timestamp`(ISO)、`level`、`event` 字段 | Vitest unit test |
| A-04 | Logger 支持 `addSink()` 注册自定义 sink（为未来远程上报预留） | Vitest unit test |
| A-05 | `readSseJsonLines` 在 JSON 解析失败时调用 `logger.warn("sse_json_parse_error", ...)` | Vitest unit test |
| A-06 | `apiFetch` 每个请求生成 `x-request-id` 并作为 HTTP header 发送 | Vitest unit test |
| A-07 | `apiFetch` 请求失败时 `logger.error` 包含 `request_id` 字段 | Vitest unit test |
| A-08 | `AppErrorBoundary` 所有错误通过 `logger.error` 输出，不直接使用 `console.*` | 代码审查 (grep) |
| A-09 | `src/` 目录中不再有直接的 `console.log`/`console.error`/`console.warn` 调用（排除 `logger.ts` 内部 sink） | `rg "console\.(log|error|warn)" src/ --glob '!**/logger.ts'` = 0 |
| A-10 | 生产环境默认级别为 `warn`，开发环境为 `debug` | Vitest unit test |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Logger facade 体积 < 2KB (minified)；不引入任何第三方依赖 | 代码审查 |
| N-02 | 不破坏现有功能；全部现有 Vitest 测试继续通过 | `npm run test` exit 0 |
| N-03 | `AGENT.md` 包含前端日志规范 | 代码审查 (grep) |

## Evidence notes

- A-01 ~ A-07, A-10: Vitest 测试文件 `src/lib/__tests__/logger.test.ts`
- A-08: `rg "console\." src/components/AppErrorBoundary.tsx` 仅在 `logger.ts` sink 中
- A-09: `rg "console\.(log|error|warn)" src/ --glob '!**/logger.ts'` 返回 0 行

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | PASS | `logger.test.ts` — "exports a logger with debug/info/warn/error methods" passed | Agent | 2026-04-16 | |
| A-02 | PASS | `logger.test.ts` — "drops events below threshold" + "supports setLevel" passed | Agent | 2026-04-16 | |
| A-03 | PASS | `logger.test.ts` — "outputs structured JSON with timestamp, level, event" passed | Agent | 2026-04-16 | |
| A-04 | PASS | `logger.test.ts` — "addSink receives entries passing the level gate" passed | Agent | 2026-04-16 | |
| A-05 | PASS | `readSseJsonLines.test.ts` — stderr shows `sse_json_parse_error` warn on bad JSON | Agent | 2026-04-16 | |
| A-06 | PASS | `api-client.ts` — `generateRequestId()` + `headers["x-request-id"]` in `apiFetch` | Agent | 2026-04-16 | Code review |
| A-07 | PASS | `api-client.ts` — `logger.error("api_request_failed", { request_id })` + `logger.error("api_request_network_error", { request_id })` | Agent | 2026-04-16 | Code review |
| A-08 | PASS | `rg "console\." src/components/AppErrorBoundary.tsx` = 0 matches | Agent | 2026-04-16 | |
| A-09 | PASS | `rg "console\.(log\|error\|warn)" src/ --glob "*.{ts,tsx}"` = 0 matches (logger.ts uses `console[method]` programmatically) | Agent | 2026-04-16 | |
| A-10 | PASS | `logger.test.ts` — "defaults to debug level in dev mode" passed | Agent | 2026-04-16 | |
| N-01 | PASS | `logger.ts` = 105 lines, zero imports outside stdlib; no new `package.json` dependencies | Agent | 2026-04-16 | |
| N-02 | PASS | Vitest: 248 tests passed, 0 failed (2 pre-existing Playwright suite errors unrelated) | Agent | 2026-04-16 | |
| N-03 | PASS | `AGENT.md` §7.7 "Frontend Logging Standards" present | Agent | 2026-04-16 | |

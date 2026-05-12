# Proposal: frontend-logging-standards

## Problem

前端（React/TypeScript）日志全部依赖裸 `console.*`（41 处），无结构化、无级别控制、无关联 ID、无远程聚合能力。SSE 解析失败静默丢弃。生产环境下：
- 团队无法感知用户浏览器中的错误
- 无法将前端日志与后端 `request_id` 对齐做跨层排障
- `console.log` 噪声无法按环境关闭

## Goals

1. 自建轻量日志门面 `src/lib/logger.ts`，支持 level 控制 + 结构化输出
2. 全部 `console.*` 迁移到 logger 门面
3. SSE 解析失败改为 `logger.warn` + 计数
4. API client 统一注入 `request_id`，错误日志带关联 ID
5. `AppErrorBoundary` 全局错误 → logger + 可扩展 hook（为未来远程上报留口）
6. 在 `AGENT.md` 中新增前端日志规范

## Non-goals

- 不引入第三方日志库（pino / winston / loglevel）
- 不引入第三方错误上报（Sentry / DataDog）
- 不增加后端 `/api/client-errors` 端点（留给后续交付）
- 不增加子树 Error Boundary（独立交付）

## Users

- 开发团队（排障、生产监控）
- 未来 AI Agent（自动分析前端日志定位 BUG）

## Scope

前端 `src/` 目录。不涉及后端变更。

## Dependencies

- 后端 `observability-logging-standards` 交付已完成（`request_id` 协议已就绪）

## Success Metrics

- `src/` 中 `console.log` / `console.error` / `console.warn` 直接调用降至 0
- 所有日志走 `logger.*`，生产环境 `level >= warn`
- SSE 解析错误有 warn 日志 + 累计计数
- API 错误日志包含 `request_id`

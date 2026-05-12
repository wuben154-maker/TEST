# Proposal: log-persistence-configurable

## Problem

当前后端日志仅输出到 stdout/stderr，前端日志仅输出到浏览器 console。在没有日志采集基础设施的裸机/本地开发环境中，日志随进程终止丢失，无法事后分析。前端 warn/error 级别事件完全留在客户端，后端无感知。

## Goals

1. **后端日志持久化可配置**：通过环境变量选择 stdout-only、本地文件、或两者兼有。
2. **前端错误上报**：生产模式下 `logger.addSink` 自动注册远程 sink，将 warn/error POST 到后端 `/api/client-errors` endpoint。
3. **后端持久化前端错误**：新 endpoint 接收前端日志，写入与后端相同的日志管道（structlog → stdout / file）。

## Non-Goals

- 不引入第三方日志聚合服务（Sentry、Datadog、ELK）。
- 不做日志查询 UI。
- 不做日志告警/通知。

## Users

- 运维/开发者：查看持久化日志排查问题。
- AI Agent：读取日志文件自动诊断 bug。

## Scope

| Layer | Change |
|-------|--------|
| Backend config | `Settings` 新增 `LOG_SINK`, `LOG_FILE_PATH`, `LOG_FILE_MAX_BYTES`, `LOG_FILE_BACKUP_COUNT` |
| Backend logging | `main.py` 按配置可选添加 `RotatingFileHandler` |
| Backend API | 新 `POST /api/client-errors` endpoint |
| Frontend | 新 `src/lib/loggerRemoteSink.ts`，app 启动时注册 |
| Env | `.env.example` 更新 |

## Dependencies

- 依赖已完成的 `observability-logging-standards`（后端 structlog）和 `frontend-logging-standards`（前端 logger facade + addSink）。

## Success Metrics

- 配置 `LOG_SINK=file` 后，`logs/secmanus.log` 正常写入 JSON 行。
- 前端触发 `logger.error(...)` 后，后端日志管道出现对应 `client_error` 事件。
- 默认 `LOG_SINK=stdout` 行为无变化（向后兼容）。

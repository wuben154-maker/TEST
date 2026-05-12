# Acceptance — Workspace 知识库

## Metadata

- **Slug:** `workspace-knowledge-base`
- **Owner:** TBD（团队填写）
- **Updated:** 2026-04-28
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

本验收覆盖：

- 知识库存储路径与用户隔离（展示为 `Workspace/knowledge/`；磁盘硬编码 **`{upload_dir}/knowledge/<user_id>/`**）。
- 认证 API：存档专业任务报告 `.docx`、列表、下载。
- 幂等与错误码（体量、鉴权）。
- 「专业任务」与 `design.md` 中 taskKind=`security`|`research` 一致。

## Environment

- **Runtime:** 本地：`python-agent-service` + Vite 前端；或团队 staging。
- **Base URL：** 后端以 `.env`/部署为准（例 `http://127.0.0.1:8000`）。
- **Feature flags：** 无（本交付不引入 flag）。

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|----------------|
| A-01 | 已登录用户对 `POST` 存档接口传入合法 `.docx`（及元数据），文件落在 `{upload_dir}/knowledge/<caller_uid>/` 且无路径穿越（`..`）。 | 单测或集成：`os.listdir` / 路径断言；尝试 `path` 绕过应失败 |
| A-02 | 用户 A 的 `GET` 列表/`download` 无法访问用户 B 的知识库条目。 | 自动化：`401`/`403`/空列表任一符合实现 |
| A-03 | `GET` 列表返回每项含用户可见字段 `Workspace/knowledge/<filename>`（或等价字段名 `display_path`），与 API 契约一致。 | 响应 JSON 快照或单元测试 |
| A-04 | 同一 `message_id`（或约定幂等键）重复存档不产生重复业务记录或实现为幂等覆盖；至少不无限复制同一文件条目。 | 双次 `POST` 后条目数语义符合 `design.md` |
| A-05 | 未携带有效凭证的请求对存档与列表/`download` 返回 `401`（与现有 API 惯例一致）。 | `curl`/测试客户端 |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|----------------|
| N-01 | 单文件大小受上限约束（对齐或等于现有上传限额）；超限 `413`。 | 超限 mock 文件 POST |
| N-02 | 列表接口在「仅目录枚举」实现下，对单用户合理文件数（如 &lt;500）响应可接受（目标 p95 &lt; 500ms 本地，非硬性 SLA）。 | 粗略计时或略过（文档注明） |

## Evidence notes

- A-01–A-05：对应 **E2E** `E2E-01`/`E2E-02`（若仅后端可测，以 pytest 为主）。
- 与 UI 联动的证据见 [`acceptance-ui.md`](./acceptance-ui.md)。

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | | | | | |
| A-02 | | | | | |
| A-03 | | | | | |
| A-04 | | | | | |
| A-05 | | | | | |
| N-01 | | | | | |
| N-02 | | | | | |

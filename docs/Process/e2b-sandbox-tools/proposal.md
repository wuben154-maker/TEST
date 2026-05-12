# Proposal: E2B On-Demand Sandbox Tools

## Metadata

| Field | Value |
|-------|-------|
| Slug | `e2b-sandbox-tools` |
| Status | Draft (Phase 2) |
| Date | 2026-04-13 |
| Author | Agent |

---

## Problem

SecManus 安全分析场景中，某些任务需要在完全隔离的环境中执行：

- **二进制动态分析**：在沙箱中运行可疑 PE/ELF/脚本，观察行为、收集 IOC。
- **恶意邮件链接模拟访问**：在沙箱浏览器中打开钓鱼 URL，截图抓包，而不污染主机。
- **特殊命令执行**：运行用户提供的不可信命令片段，不影响 Agent 宿主环境。

**核心矛盾**：DeepAgents 官方的沙箱接入方式要求在 `create_deep_agent()` 时传入 backend，意味着每次创建 Agent 实例都会预先建立一个沙箱，但上述场景需要**按需、懒惰地**创建沙箱——其他普通分析场景完全不需要沙箱，仍使用本地文件系统。

---

## Goals

1. **G1 — 按需创建**：沙箱仅在工具被调用时创建，不影响无沙箱路径的正常分析。
2. **G2 — 可组合工具集**：提供通用原子 Tool（而非按场景封装为 `analyze_binary` / `simulate_url`），Agent/LLM 可按任意顺序组合调用，应对不断变化的安全场景。
3. **G3 — 模板参数化**：沙箱模板（E2B template ID、资源限制等）可在调用时动态传入，支持不同场景使用不同镜像。
4. **G4 — 双生命周期**：
   - *Per-call 模式*：每次工具调用创建新沙箱，完成后自动销毁（最安全）。
   - *Session 复用模式*：同一会话内显式创建沙箱、跨工具调用复用、最终显式销毁（性能更优）。
5. **G5 — 双接入路径**：
   - **Tool 路径**：`StructuredTool`，供 Agent 直接调用（主路径）。
   - **Backend 路径**：`E2BSandboxBackend` 继承 `BaseSandbox`，可作为子 Agent 的 `backend=` 参数（可选路径）。
6. **G6 — 集中配置**：所有沙箱相关配置（模板、超时、网络策略、默认资源）统一放在 `config/sandbox.yaml`。

---

## Non-Goals

- 不提供持久化沙箱（每次服务重启后沙箱记录清空）。
- 不实现 GUI/前端沙箱管理页面。
- 不支持非 E2B 沙箱提供商（后续可扩展接口）。
- 不替换现有的 `web-threat-yara-sandbox`（那是本地语法沙箱）。

---

## Users

- **Agent（LLM）**：主要使用方，通过调用工具与沙箱通信。
- **安全分析师**：通过前端发起分析请求，间接触发沙箱工具。
- **开发者**：配置 `config/sandbox.yaml`，扩展新模板或新工具。

---

## Scope

### In Scope

- `app/tools/sandbox_tools.py`：三个 `StructuredTool`（`sandbox_create`、`sandbox_destroy`、`sandbox_run`）。
- `app/backends/e2b_sandbox.py`：`E2BSandboxBackend` 类（继承 `BaseSandbox`，同步 E2B SDK）。
- `config/sandbox.yaml`：沙箱全局配置文件（模板定义、默认超时、网络策略）。
- `python-agent-service/requirements.txt`：新增 `e2b` 依赖。
- `.env.example`：新增 `E2B_API_KEY`、`E2B_DEFAULT_TEMPLATE` 等变量。
- `config/tool_presentation.yaml`：注册 sandbox 工具的 SSE 呈现配置。
- `app/tools/common/tools.py`（或对应注册点）：将 sandbox tools 挂载到 Agent。
- 单元测试：`tests/tools/test_sandbox_tools.py`。

### Out of Scope

- 前端 UI 改动。
- 数据库 schema 变更。

---

## Dependencies

| Dependency | Version | Notes |
|-----------|---------|-------|
| `e2b` | latest | E2B Python SDK（提供 `Sandbox`/`AsyncSandbox`） |
| `E2B_API_KEY` | — | 运行时环境变量 |

---

## Success Metrics

- Agent 可在无沙箱时正常工作（零沙箱创建开销）。
- `sandbox_run` per-call 模式：调用 → 执行 → 销毁三步完整，无泄漏。
- `sandbox_create` + `sandbox_run` + `sandbox_destroy` session 模式：同一沙箱 ID 跨调用复用。
- `config/sandbox.yaml` 修改模板后无需代码改动即可生效（热读或重启加载）。

---

## Open Questions (Resolved)

| # | Question | Decision |
|---|----------|---------|
| Q1 | 模板参数化方式 | `sandbox_run`/`sandbox_create` 接受 `template` 参数，默认读 `config/sandbox.yaml` |
| Q2 | 工具粒度 | 通用原子工具（3 个），而非场景函数 |
| Q3 | 是否需要 Backend 路径 | 是，`E2BSandboxBackend` 同步实现，两路径均提供 |
| Q4 | 生命周期 | Per-call + Session 两种均支持 |
| Q5 | 配置位置 | `config/sandbox.yaml` 为唯一沙箱配置入口 |

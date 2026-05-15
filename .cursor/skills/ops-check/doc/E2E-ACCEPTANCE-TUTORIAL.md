# ops-check 端到端验收教程 v2.1
>
> 验收对象：把本仓库的 `ops-check/` 接到一个真实的、可写的 GitHub 应用仓库上，跑通主链路：
>
> **拉日志 → 命中规则 → 路由判定 → 自动改代码 → 跑 required 测试 → 创建 PR → 人审合并 → 状态闭环**。
>
> 配套源文件（你会反复用到）：`ops-check/config.example.yaml`、`ops-check/test-map.example.yaml`、`ops-check/fix-agent.example.yaml`（Cursor 风格 CLI）、`ops-check/fix-agent.claude-code.example.yaml`、`ops-check/fix-agent.modelscope.example.yaml`（ModelScope Chat Fix Agent）、`ops-check/rules.yaml`、`.cursor/skills/ops-check/SKILL.md`、`.github/workflows/ops-check.yml`。

---

## 0. 30 秒读完

**整件事拆成 4 个阶段，按顺序做：**

| 阶段 | 谁做 | 干啥 | 大约耗时 |
|---|---|---|---|
| **A. 准备** | **只能你做** | 在 GitHub / AWS / 飞书 / ModelScope（或其它 OpenAI 兼容推理）等外部平台开账号、配 token、建 fork | 30~60 分钟 |
| **B. 填表** | **只能你做** | 填一份 `acceptance.config.yaml`（本文第 3 章），把验收所需信息一次性交给 AI | 10 分钟 |
| **C. 跑测试** | **AI 做** | 把第 4 章的"启动提示词" + 你的 `acceptance.config.yaml` 一起发给 AI，AI 自动复制代码、改配置、造日志、跑命令、判合格 | 30~120 分钟 |
| **D. 收尾** | **你做** | 在 GitHub UI 里 review + merge ops-check 自动开的 PR，并保存验收证据 | 10 分钟 |

> **重要前提**：ops-check 设计上**永远不会自己合并 PR**，这是合约硬约束。第 D 阶段的人审合并必须由你（或 reviewer）在 GitHub 网页/`gh pr merge` 上完成。

---

## 1. 名词速查（看不懂任何一段时回来看）

| 词 | 含义 |
|---|---|
| **host repo** | 当前 Watchtower 仓库（你现在看的这个），承载 ops-check 源码 |
| **consumer repo** | 你拿来当被测靶子的真实应用仓库（**必须是你能写的 fork**） |
| **logSource** | ops-check 拉日志的来源；3 种类型：`file` / `cloudwatch` / `http-json` |
| **fingerprint** | 错误指纹：用 service / errorType / msgTpl / stackTop / environment 做 sha256，去重和复发判定都靠它 |
| **fixRoute** | 路由结果：`template_patch`（模板补丁→PR）/ `fix_agent_request`（Fix Agent→PR：CLI 或 Chat API，见 `fix-agent.yaml` overlay）/ `issue_only`（高危→Issue） |
| **required tests** | 由 `test-map.yaml` 推导出来的命令列表，**全部 exit 0** 才允许开 PR |
| **forbiddenPaths** | 禁区路径（auth/billing/secrets/migrations/infra），命中即强转 issue_only |
| **state.json** | `.ops-check/state.json`，本地状态文件，记录指纹、PR 链接、复发计数等 |
| **dry-run** | 只算计划不动外部世界（不开 PR/Issue、不发飞书、不写 state） |
| **mature 验收** | 在真实 consumer repo 上、对真实日志、产生真实 PR、跑通真实 required tests 并归档 |

---

## 2. 必须由你（人）完成的清单

> 下面这 9 件事 **AI 永远做不了**，因为它们涉及第三方账号、付费、UI 点击或浏览器登录。请先全部完成，再进入第 3 章。

### 2.1 工作站工具
| 工具 | 最低版本 | 自检命令 |
|---|---|---|
| Node.js | 20+（用了内置 fetch） | `node -v` |
| Git | 2.40+ | `git --version` |
| GitHub CLI | 任意新版 | `gh --version` |
| PowerShell | 7+（Windows 用户） | `pwsh -v` |
| AWS CLI v2 | 仅当用 cloudwatch 源 | `aws --version` |
| Claude Code CLI | 仅当 optionalPaths.cursorAgent + Claude overlay | `claude --help`（或你环境里的等价命令） |

### 2.2 GitHub 端
1. **建一个 consumer repo**：fork 你要测的真实应用，或者把它 import 到你自己 GitHub 账号下，**必须有 push 权限**。
2. **创建 Fine-grained PAT**：仅授权这个 consumer repo，权限勾：`Contents R/W`、`Pull requests R/W`、`Issues R/W`。
3. **设仓库 Settings → Actions → General → Workflow permissions = Read and write permissions**（保证 Actions 自带的 `GITHUB_TOKEN` 也能写）。
4. **加 Branch protection（main）**：勾 `Require status checks to pass before merging`，至少把 `rules-selftest` 加进去；**别**勾"自动合并"。

### 2.3 三方账号（按需，每个都可选）
| 平台 | 何时需要 | 你要拿到什么 |
|---|---|---|
| **AWS** | 想测 `cloudwatch` 日志源 | 一个 IAM 用户，权限见 §6.2，记下 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION` |
| **任何云日志/Webhook** | 想测 `http-json` 源 | 一个 GET/POST 端点 URL + Bearer token（阿里云 SLS / 腾讯云 CLS / Sentry / 自建均可） |
| **飞书机器人** | 想测通知与升级链路 | 两个 Incoming Webhook URL：`FEISHU_WEBHOOK_URL` + `FEISHU_ESCALATION_WEBHOOK_URL` |
| **ModelScope 推理（推荐与本仓库默认一致）** | 想测 **分类 LLM**（`lib/llm-client.mjs`、`lib/route-advisor.mjs`）和/或 **Chat Fix Agent**（`lib/fix-chat-api.mjs`） | **只需一个密钥**：`OPENAI_API_KEY`（Bearer Token，两处共用）。可选 **`OPENAI_MODEL`**（不设则代码默认 `deepseek-ai/DeepSeek-V4-Pro`）。分类接口 Base URL 写在代码里：`https://api-inference.modelscope.cn/v1/chat/completions`；Fix Agent 的 Base URL 写在 **`fix-agent.yaml`** 的 `chatApi.baseUrl`（示例见 `fix-agent.modelscope.example.yaml`）。 |
| **Cursor IDE / Cursor CLI** | 想用 **CLI** 跑 Fix Agent（非 Chat API） | 安装 `cursor-agent` 或文档中的 `agent`，按需设置 **`CURSOR_API_KEY`**（Dashboard → Integrations）；可选 **`CURSOR_AGENT_API_URL`** + **`CURSOR_AGENT_API_TOKEN`**（overlay `api.endpointEnv` / `tokenEnv`）。 |
| **Claude Code CLI** | 想用 **`claude -p`** 跑 Fix Agent | 本机安装 Claude Code CLI；按需 **`ANTHROPIC_API_KEY`** 或 `claude auth login`。overlay：`fix-agent.claude-code.example.yaml`。 |

> **完全不配三方账号也能验收主链路**（local file 日志 + 模板补丁路径 + 不发飞书）。建议至少配 GitHub PAT。  
> **只要配 ModelScope：`OPENAI_API_KEY` 一根密钥即可覆盖「分类 LLM + ModelScope Chat Fix Agent」**（前提是 `fix-agent.yaml` 里 `chatApi.apiKeyEnv` 指向 `OPENAI_API_KEY`，示例已默认如此）。

### 2.4 把 secrets 写到 GitHub Actions
进 consumer repo → Settings → Secrets and variables → Actions：
- 上面 §2.3 拿到的所有 key 全部以 **Secrets** 形式存（**不是** Variables）。
- **与本仓库 workflow 对齐**：`.github/workflows/ops-check.yml` 会向 job 注入 **`OPENAI_API_KEY`**（分类 LLM + ModelScope Chat Fix Agent 共用）、以及按需的 **`CURSOR_API_KEY`**、**`ANTHROPIC_API_KEY`** 等（CLI Fix Agent 用）。请在仓库 Secrets 里创建同名项；未创建的 secret 在运行时为空字符串，不影响其它路径。
- **模型名（非密钥）**：如需在 Actions 里固定模型，可使用 Repository **Variables**（例如 `OPENAI_MODEL`，再在 workflow 里自行接线）；本地验收直接用 `$env:OPENAI_MODEL` 即可。
- 仅 `ENABLE_OPS_CHECK_SELF_HOSTED` 是 **Variables**（值 `"true"` / `"false"`），仅当你有 self-hosted runner 时设 true。

完成 §2.1~§2.4 后，进入第 3 章填表。

---

## 3. 给 AI 的"任务交付单" — `acceptance.config.yaml`

### 3.1 这是什么
- 一份**你只填一次**的 YAML 文件，里面装的是 AI 验收所需的全部信息（仓库地址、日志源选择、密钥环境变量名等）。
- AI 拿到它之后，会自动：
  1. 在你指定的本地路径上 clone consumer repo
  2. 把 `ops-check/` 拷进 consumer 仓库
  3. 按你的勾选生成正确的 `ops-check/config.yaml` / `test-map.yaml` / 故障日志
  4. 跑通第 5 章检查表（§5.0–§5.12，并按勾选执行可选 §5.13），并把每步证据归档

### 3.2 文件位置
建议放在你工作站任意位置（**不要 commit 进任何仓库**，因为里面有路径和环境变量名）：

```
d:\acceptance\acceptance.config.yaml
```

### 3.3 模板（直接复制，按注释填）

```yaml
# ──────────────────────────────────────────────────────────────
# ops-check 验收任务交付单
# 把这份文件 + 第 4 章的"启动提示词" 一起交给 AI，AI 接管后续。
# ──────────────────────────────────────────────────────────────

# 1) 你的 consumer 仓库（必须有 push 权限）
consumer:
  repoUrl: "https://github.com/<你的账号>/<你的fork>.git"
  localPath: "d:\\my-app-fork"           # AI 会 clone 到这里
  defaultBranch: "main"
  acceptanceBranch: "acceptance/ops-check"  # AI 会建这条分支跑全过程

# 2) host 仓库（当前 Watchtower 仓库的本地路径，AI 从这里拷 ops-check)
host:
  localPath: "d:\\Watchtower"

# 3) 应用本身的命令（AI 用它判断"应用本身能不能跑")
appCommands:
  install: "npm install"
  test: "npm test"
  lint: "npm run lint"
  e2e: "npm run e2e"          # 没有就留空字符串，AI 会用 npm init playwright 兜底
  buildOk: true                # 你确认 main 分支当前是绿的，AI 才敢继续

# 4) 选哪些日志源（至少选一个 file，验主链路；其他按你 §2.3 配的来勾)
logSources:
  file:
    enabled: true
    relativeDir: "./logs"      # AI 会在 consumer repo 仓内造日志文件
  cloudwatch:
    enabled: false                    # 设为 true 以测试 cloudwatch 日志源
    region: "ap-southeast-1"          # 改为你的 AWS 区域（consumer 里生成的 `ops-check/config.yaml` 也可写 `${from-cicd-env}` 从 `.cicd/env/<env>.yaml` 推导，见 SKILL.md）
    logGroupNames:
      - "/ecs/secmanus-prod"          # 改为 CI/CD awslogs 组名；或与 SKILL 一致用 `${from-cicd-env}` / `[]`，由 `.cicd/env` + 约定 `/ecs/<repository.name>-<env>` 推导
  httpJson:
    enabled: false
    urlEnvName: "OPS_CHECK_JSON_LOG_URL"     # 仅写环境变量名，URL 本身不写在这里
    authHeaderEnvName: "OPS_CHECK_LOG_AUTH_HEADER"

# 5) 通知 / LLM / Fix Agent 是否参与本次验收
optionalPaths:
  feishu: false                # true 时 AI 会跑 §5.10/§5.11 飞书与升级链路
  llmFallback: false           # true 时 AI 会跑 §5.13（分类 LLM / routing-advisor，需 OPENAI_API_KEY）
  cursorAgent: false           # true 时 AI 会跑 §5.13（fix_agent_request 真跑：CLI 或 chatApi，见 fix-agent.yaml）

# 6) 当前终端已经设置好的环境变量名清单（AI 用来反向检查你有没有漏配)
envVarsExpected:
  - GITHUB_TOKEN
  - GITHUB_REPOSITORY
  # 下面按你实际开了哪些路径勾选
  # - AWS_ACCESS_KEY_ID
  # - AWS_SECRET_ACCESS_KEY
  # - AWS_REGION
  # - OPS_CHECK_JSON_LOG_URL
  # - OPS_CHECK_LOG_AUTH_HEADER
  # - FEISHU_WEBHOOK_URL
  # - FEISHU_ESCALATION_WEBHOOK_URL
  # - OPENAI_API_KEY              # ModelScope：分类 LLM + chat Fix Agent 常共用同一密钥
  # - OPENAI_MODEL                # 可选；不设则默认 deepseek-ai/DeepSeek-V4-Pro
  # - CURSOR_API_KEY              # Cursor CLI Fix Agent（overlay 使用 fix-agent.example.yaml 时）
  # - ANTHROPIC_API_KEY           # Claude Code CLI Fix Agent（overlay 使用 fix-agent.claude-code.example.yaml 时）
  # - CURSOR_AGENT_API_URL        # 可选；少数 HTTP 风格 overlay 仍可用
  # - CURSOR_AGENT_API_TOKEN

# 7) 验收产物归档目录（AI 把每步 stdout / state.json / PR URL 写进这里）
evidence:
  outputDir: "d:\\acceptance\\evidence"

# 8) 安全开关（出了什么 AI 必须立刻停)
guardrails:
  abortIfSecretLeaked: true       # PR/Issue/日志里出现 token 或邮箱立刻 abort
  abortIfPushBeforeDryRunPassed: true
  maxAutoPRs: 2                   # 整个验收过程最多允许 AI 触发开 2 个 PR
```

### 3.4 字段含义速查
| 字段 | 为什么 AI 需要 | 不填会怎样 |
|---|---|---|
| `consumer.repoUrl` | clone 你 fork、push 验收分支、开 PR 都要它 | AI 直接报错停 |
| `consumer.localPath` | AI 工作目录 | 同上 |
| `host.localPath` | 从 Watchtower 拷 `ops-check/` 到 consumer | 同上 |
| `appCommands.test/lint` | 写进 `test-map.yaml` 的 required 命令 | required 列表为空，必然挡 PR |
| `appCommands.e2e` | 决定 `validate-test-map` 的 `e2eDiscovery.found` | 为空时 AI 触发 `npm init playwright@latest` 兜底 |
| `logSources.file` | 主链路必跑 | 没法验本地文件路径 |
| `optionalPaths.*` | 决定 AI 跑哪些可选步骤 | 默认全 false，最快验完主链路 |
| `envVarsExpected` | AI 启动前用 `Get-ChildItem env:` 反向检查 | AI 检测到缺失会停 |
| `guardrails` | 出事兜底 | 默认全开，请别关 |

---

## 4. 启动 AI（一次粘贴）

### 4.1 操作
1. 在 Cursor 里打开 **consumer 仓库**（`d:\my-app-fork` 或你填的路径）。
2. 把第 3 章填好的 `acceptance.config.yaml` 拖进 chat 窗口（或 `@` 引用）。
3. 把下面方框里的提示词整段粘贴进 chat。

### 4.2 启动提示词（直接复制）

```
你现在的角色是 ops-check 端到端验收执行者。
所有任务定义在 doc/E2E-ACCEPTANCE-TUTORIAL.md 第 5 章「检查表」（§5.0–§5.12 必跑；§5.13 按 acceptance.config.yaml 的 optionalPaths）。
所有用户输入都在我刚才发的 acceptance.config.yaml 里。

请按下列原则执行：

1. 严格读 acceptance.config.yaml + .cursor/skills/ops-check/SKILL.md
   + ops-check/config.example.yaml + ops-check/test-map.example.yaml
   + ops-check/fix-agent.example.yaml（Cursor CLI）
   + ops-check/fix-agent.claude-code.example.yaml（Claude CLI）
   + ops-check/fix-agent.modelscope.example.yaml（ModelScope chat Fix Agent）
   ，以这些为唯一权威。
2. 任何外部副作用前（push / 开 PR / 发飞书 / 写 state.json），先汇报计划等我确认。
3. 每完成一步，按 §5 的"合格信号"自检；不合格就回到该步排查，不要前进。
4. 把每步的 stdout 写到 acceptance.config.yaml.evidence.outputDir
   下，命名 step-<编号>-<名称>.json。
5. 若任意时刻发现 secret/token/email 泄露到 PR/Issue/日志/stdout，
   立刻 abort 并把命中位置打印出来。
6. 任何写入 consumer 仓库的文件改动都要走 git，不要散落。
7. 你不得自行 merge PR；最后输出"等待人审"提示等我接手。

开始：先做 §5.0 的"启动前自检"，确认 envVarsExpected 全部已设。
```

### 4.3 AI 中途要是卡住
- AI 会停下来报告"卡在第 X 步，原因 Y"。
- 你按本文档第 6 章【排查速查表】的对应行救场，然后告诉 AI"按速查表 X 行修，继续"。

---

## 5. 检查表（§5.0–§5.12 必跑；§5.13 按 optionalPaths / §2.3 选跑）

> 全部步骤默认在 `${consumer.localPath}` 下、`${consumer.acceptanceBranch}` 分支上跑。每一步给三件：**做什么 / 合格信号 / 失败救援**。

### §5.0 启动前自检（不连真实仓库）

```powershell
node -v                                  # 必须 20+
node ops-check/ops-check.mjs --help      # 列出 5 个子命令
node --test ops-check/*.test.mjs         # 仓内单元测试全绿
```
- **合格**：`--help` exit 0；`node --test` 0 failed。
- **失败**：Node < 20 → 升级；测试红 → 报告给我，停。

### §5.1 把 ops-check 注入 consumer 仓库

AI 自动做：
```powershell
$consumer = "${consumer.localPath}"
$host     = "${host.localPath}"
Copy-Item -Recurse -Force "$host\ops-check"          "$consumer\"
Copy-Item -Recurse -Force "$host\.cursor"            "$consumer\"
New-Item  -ItemType Directory -Force "$consumer\.github\workflows" | Out-Null
Copy-Item -Force "$host\.github\workflows\ops-check.yml"      "$consumer\.github\workflows\"
Copy-Item -Force "$host\.github\workflows\rules-selftest.yml" "$consumer\.github\workflows\"
git -C $consumer checkout -b "${consumer.acceptanceBranch}"
git -C $consumer add . ; git -C $consumer commit -m "chore: bootstrap ops-check"
```
- **合格**：`git status` clean，`acceptance/ops-check` 分支已建，**先不 push**。
- **失败**：路径含空格用引号；Windows 权限不够换管理员 PowerShell。

### §5.2 生成 `ops-check/config.yaml` + `ops-check/test-map.yaml`

AI 按第 3 章 `acceptance.config.yaml` 的勾选，生成两份文件。模板见本文 §A.1 / §A.2。
- **Fix Agent overlay**：按需执行 `Copy-Item`：`fix-agent.example.yaml`（Cursor CLI）→ `fix-agent.yaml`；若验收 Claude / ModelScope chat，则改用 `fix-agent.claude-code.example.yaml` 或 `fix-agent.modelscope.example.yaml`（并保持 `config.fixAgent.configPath` 指向该文件）。
- **关键约束**：
  - `runtime.dryRun: true`（先 dry-run）
  - `autofix.enabled: false`、`fixAgent.enabled: false`（5.6 才打开）
  - `logSources` 只放你 enable 的源
  - `runtime.allowedLogRoots` 必须覆盖 `logSources.file.paths`
- **合格**：跑 `node ops-check/ops-check.mjs validate-config --config ops-check/config.yaml` 输出 `{"ok": true}`。
- **失败**：`CONFIG ERRORS:` 后面打印的字段名 → 按字段名修。

### §5.3 校验 test-map（决定 required 命令清单）

```powershell
node ops-check/ops-check.mjs validate-test-map --config ops-check/config.yaml
```
- **合格**：JSON 含 `e2eDiscovery.found: true`。
- **失败**：`found: false` → AI 跑 `npm init playwright@latest -- --quiet --browser=chromium`，再写 `package.json` 的 `e2e` script，重跑。

### §5.4 规则 self-test（确保 rules.yaml 没坏）

```powershell
node --test ops-check/rules-selftest.test.mjs
```
- **合格**：每条规则的 examples 命中、negativeExamples 不命中。
- **失败**：报告失败规则名，停。

### §5.5 Planner Fixture Dry-Run（验链路本身）

```powershell
node ops-check/ops-check.mjs validate-config --config ops-check/config.planner-fixture.yaml
node ops-check/ops-check.mjs run --dry-run    --config ops-check/config.planner-fixture.yaml
```
- **合格**：`mode=run`、`sandboxPlanOnly=true`、`findings>=3`，至少同时出现 1 个 `template_patch`、1 个 `fix_agent_request`、1 个 `issue_only`。
- **失败**：`findings: 0` → fixtures 被删了，从 host repo 重新拷一次 `ops-check/fixtures/`。

### §5.6 真实日志 Dry-Run（local file 路径）

AI 在 `${logSources.file.relativeDir}` 下造 5 行同样的错误日志（fingerprint 才能上 high）：

```
2026-05-13T01:00:00Z service=<project> level=ERROR msg=TypeError: Cannot read properties of undefined (reading 'map') at AcceptanceWidget (src/components/AcceptanceWidget.tsx:7:12) user=alice@example.com ip=10.0.1.23
... 重复 4 行 ...
```

跑：
```powershell
node ops-check/ops-check.mjs diagnose --since 30m --config ops-check/config.yaml | Tee-Object evidence/step-6-diagnose.json
```
- **合格**：JSON 含 `findings >= 1`、`fixRoute=template_patch`，且 `sideEffectsSkipped` 含 5 项（github_issues/pull_requests/git_push/feishu_cards/state_file_writes）。
- **脱敏自检**：`Select-String -Pattern "alice@example.com|10\.0\.1\.23" evidence\step-6-diagnose.json` **必须无命中**，否则 abort。
- **失败**：`findings: 0` → 检查日志路径是否落在 `runtime.allowedLogRoots` 里。

### §5.7 切到 live run + 真实开 PR（核心验收点）

AI 改 `ops-check/config.yaml`：
```yaml
runtime: { dryRun: false }
autofix:  { enabled: true, maxPrsPerRun: 1 }
fixAgent: { enabled: false }
```
确认 `acceptance/ops-check` 已 push 到 origin（`git push -u origin acceptance/ops-check`）。

跑：
```powershell
node ops-check/ops-check.mjs run --config ops-check/config.yaml | Tee-Object evidence/step-7-run.json
```
- **合格（必须全部满足）**：
  1. 真实开了一个 PR，URL 形如 `https://github.com/<U>/<R>/pull/<N>`，分支名 `ops-check/fix-<fp8>`。
  2. PR title：`[ops-check] autofix react-undefined-property-read`。
  3. PR body 含：`Template autofix (**isolated worktree**)` / `### testPlan (required = all exit 0 before PR)`（required 非空）/ `### changed paths` / `### FIX_REQUEST_EMBED` JSON / `advisor: consulted=...`。
  4. diff 只改 1 个文件、行数 < 400。
  5. `.ops-check/state.json` 写入 `fingerprints[<fp>].prUrl`、`reviewStatus: "pending_or_timeout"`、`lastVerification.results[].status === 0`。
  6. stdout 含 `--- OPS_CHECK_REVIEW_REQUEST_BEGIN ---` / `--- END ---` 两个标记。
- **失败救援**：见第 6 章【排查速查表】对应行。

### §5.8 第二次 run，验证去重（不重复开 PR）

```powershell
node ops-check/ops-check.mjs run --config ops-check/config.yaml
```
- **合格**：日志含 `branch exists on remote`，**不开第二个 PR**。
- **失败**：去重失效 → 检查 `state.json` 是否被覆盖。

### §5.9【需 D 阶段人审】PR 合并后回放

人工动作（**ops-check 不会自己合并**）：
1. 用 `pr-commit-with-review` Skill 或在 GitHub UI 上 review approve + merge。
2. 合并方式选 squash 或 merge commit（**别 rebase**）。

AI 再跑：
```powershell
node ops-check/ops-check.mjs run --config ops-check/config.yaml
```
- **合格**：`state.fingerprints[<fp>].mergedFix === true` 且 `reviewStatus === "approved_and_merged"`，同 fingerprint 不再开新 PR。

### §5.10 高危 → issue_only（不开 PR，开 Issue）

AI 在 `logs/` 下 append 12 行 401：
```
2026-05-13T02:00:00Z HTTP/1.1" 401 -
... 共 12 行 ...
```
跑 `node ops-check/ops-check.mjs run --config ops-check/config.yaml`。
- **合格**：该指纹 `fixRoute === "issue_only"`，**不开 PR**，开了 GitHub Issue（label `ops-check, automated`），title 含 `[critical]`。配了 `FEISHU_ESCALATION_WEBHOOK_URL` 时发出升级卡片。
- **脱敏自检**：Issue body **不含**原始 IP / token / Bearer / JWT。

### §5.11 恢复闭环（错误消失 → Issue 自动关）

```powershell
Remove-Item ${logSources.file.relativeDir}\*-auth.log
node ops-check/ops-check.mjs run --config ops-check/config.yaml   # 跑 3 次
node ops-check/ops-check.mjs run --config ops-check/config.yaml
node ops-check/ops-check.mjs run --config ops-check/config.yaml
```
- **合格**：`state.fingerprints[<fp>].missStreak >= 3`，对应 Issue 自动 closed（GitHub UI 显示 `Closed by github-actions[bot]`），`wasClosed === true` 且 `issueNumber === null`。

### §5.12 GitHub Actions 端到端跑（最终落地）

AI 把 `acceptance/ops-check` push 到远端，提示你去 GitHub UI：
1. Actions → ops-check → Run workflow → 选 `acceptance/ops-check`。
2. 第一次：`dry_run = true`；第二次：`dry_run = false`。

- **合格**：cron `*/10 * * * *` 在 Actions 页面能看到下次调度；workflow logs 里 `Select-String` 找不到任何 token / webhook 真值；`hybrid` job 仅在 `vars.ENABLE_OPS_CHECK_SELF_HOSTED == 'true'` 时出现。

### §5.13（可选）分类 LLM + Fix Agent（ModelScope / Cursor CLI / Claude）

**前置**：在 `acceptance.config.yaml` 把 `optionalPaths.llmFallback` / `optionalPaths.cursorAgent` 设为 `true`，并按 §2.3 / §2.4 配置密钥与 Actions Secrets。

**环境变量（最小心智模型）**

| 目的 | 变量 | 说明 |
|---|---|---|
| 分类 LLM + routing advisor | `OPENAI_API_KEY` | Bearer Token；POST **代码内置** URL：`https://api-inference.modelscope.cn/v1/chat/completions`（见 `ops-check/lib/llm-client.mjs`、`route-advisor.mjs`）。 |
| 指定模型（可选） | `OPENAI_MODEL` | 不设则默认 `deepseek-ai/DeepSeek-V4-Pro`。 |
| Cursor CLI Fix Agent | `CURSOR_API_KEY` | 配合 `fix-agent.example.yaml`（或等价 overlay）。 |
| Claude Code CLI Fix Agent | `ANTHROPIC_API_KEY`（或 `claude auth login`） | 配合 `fix-agent.claude-code.example.yaml`。 |
| ModelScope Chat Fix Agent | `OPENAI_API_KEY`（与分类共用） | 复制 `fix-agent.modelscope.example.yaml` → `fix-agent.yaml`，确认 `chatApi.apiKeyEnv: OPENAI_API_KEY` 与 `chatApi.baseUrl` 指向 ModelScope `v1`。 |

**验收顺序（建议）**

1. **仅分类**：保持 §5.7 `fixAgent.enabled: false`，设置 `OPENAI_API_KEY`，跑一次带 `--dry-run` 或 live 的 `run`/`diagnose`，确认 advisor / `llmStats` 无致命报错。
2. **Fix Agent（chat）**：启用 `fixAgent.enabled: true`、`simulateRunner: false`，使用 ModelScope overlay，触发规则命中 `fix_agent_request`，确认 runner 日志出现 chat API 调用且无长时间卡在 `runner_deps_missing`。
3. **Fix Agent（CLI）**：改用 Cursor / Claude overlay，runner 已安装对应 CLI，按需配置 `CURSOR_API_KEY` / `ANTHROPIC_API_KEY`。

> **GitHub Actions**：consumer 仓库 Secrets 创建 **`OPENAI_API_KEY`**（及按需 **`CURSOR_API_KEY`** / **`ANTHROPIC_API_KEY`**）；`.github/workflows/ops-check.yml` 已向 job 注入同名环境变量。

---

## 6. 排查速查表（出问题时只看这一张表）

### 6.1 通用现象 → 根因 → 一句话修
| 现象 | 根因 | 修法 |
|---|---|---|
| `fetch is not defined` | Node < 20 | `nvm install 20` 或装最新 |
| `CONFIG ERRORS: logSources[*].allowedRoots` | file 源没配 allowedRoots | 在该 source 加 `allowedRoots: [./logs]` |
| `validate-test-map` 报 `e2eDiscovery.found: false` | consumer 没 Playwright/Cypress | `npm init playwright@latest -- --quiet --browser=chromium` |
| `findings: 0`（明明有错误日志） | 路径不在 `runtime.allowedLogRoots` 里，或 hosted runner 看不到本地路径 | 加 root 或换 self-hosted runner |
| `no patch` | stack 行号没匹配到 `(src/...:N:M)` | 重新造日志，确保 stack 顶含路径行号 |
| `forbidden path` | suspected 路径落在 forbiddenPaths | 把 bug 文件挪出 `src/auth/` 等禁区 |
| `branch exists on remote` | 上次跑已 push | `gh api -X DELETE repos/<U>/<R>/git/refs/heads/ops-check/fix-<fp8>` 删了再试 |
| `no required verification commands` | testPlan.required 空 | 在 `autofix.verificationCommands` 兜底 `npm run lint` |
| required 测试 exit≠0 | 补丁改坏或测试本来就红 | 先确保**没补丁时** `npm test/lint` 都 0 |
| `aws ... command not found` | runner 缺 aws cli | `apt-get install awscli` 或换 hosted ubuntu-latest |
| `http-json: response not JSON` | 端点返回 HTML 错误页 | curl 直接打一遍看返回 |
| Issue / PR body 含 IP / 邮箱 / Bearer | redact 失效 | abort，回退最近一次对 `redactText` 的改动 |
| Actions 跑出来 `findings: 0`（本地能看到） | 日志只在你机器上 | hosted runner 改用 cloudwatch / http-json，或 self-hosted |
| `runner_deps_missing` / Fix Agent 立刻失败 | CLI 未安装或 PATH 不在 runner | 安装 `cursor-agent`/`agent`/`claude`，或在 overlay 改用 `chatApi`（ModelScope 示例） |
| chat Fix Agent 401 / `invalid_api_key` | `OPENAI_API_KEY` 未注入或与 `chatApi.apiKeyEnv` 不一致 | 对齐密钥名；本地 `Get-ChildItem env:OPENAI_API_KEY`；Actions 检查 Secrets |
| `agent_parse_failed`（chat） | 模型返回非预期 JSON | 提高 timeout / 换模型 `OPENAI_MODEL` / 查看原始响应日志 |

### 6.2 三种日志源所需的最少配置
| 类型 | runner 必须 | 必备 secrets | config.yaml 关键字段 |
|---|---|---|---|
| `file` | self-hosted（要读公司机器路径）或 hosted（仅读仓内 `./logs/*.log`） | 无 | `paths`、`allowedRoots`、`runtime.allowedLogRoots` |
| `cloudwatch` | hosted 或 self-hosted | `AWS_ACCESS_KEY_ID`、`AWS_SECRET_ACCESS_KEY`、`AWS_REGION` | `region`、`logGroupNames` |
| `http-json` | hosted 即可 | `OPS_CHECK_JSON_LOG_URL`、`OPS_CHECK_LOG_AUTH_HEADER` | `urlEnv`、`headersEnv`（值是**环境变量名**，必须 `^[A-Z0-9_]+$`） |

当 cloudwatch 日志源与 CI/CD 的 awslogs 日志驱动配合使用时，logGroupNames 必须与 `docker run --log-opt awslogs-group=` 的值完全一致。

CloudWatch 的最小 IAM 策略：
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "logs:FilterLogEvents",
      "logs:GetLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams"
    ],
    "Resource": "arn:aws:logs:<region>:*:log-group:/aws/lambda/<your-prefix>*:*"
  }]
}
```

### 6.3 防泄密一键自检
```powershell
Select-String -Path "evidence\*.json","$env:USERPROFILE\.gitconfig",".ops-check\state.json" `
  -Pattern '(sk-[A-Za-z0-9]{16,}|Bearer [A-Za-z0-9._-]{16,}|eyJ[A-Za-z0-9._-]{16,}|ghp_[A-Za-z0-9]{20,})'
```
**任何匹配 = 验收不通过**。

---

## 7. 验收"通过"判定（8 条 must-pass）

**全部 PASS 才算 mature 验收通过**：

1. §5.0–§5.5 全 exit 0；
2. §5.6 真实本地日志能产生 findings 且脱敏自检无命中；
3. §5.6 / §5.7 至少跑通了 `file` 一种源；如勾选了 cloudwatch / http-json 也必须各自 dry-run 跑过 1 次；
4. §5.7 模板补丁路径**真实创建 PR**，PR body 含 isolated worktree / testPlan / FIX_REQUEST_EMBED / advisor 行，required tests 全 exit 0；
5. §5.8 同 fingerprint 第二次 run **不重复开 PR**；
6. §5.9 PR 合并后 state 切到 `approved_and_merged`；
7. §5.10 高危日志走 issue_only、不开 PR；
8. §5.11 错误消失后 3 轮 poll 自动 close Issue；
9. §5.12 GitHub Actions hosted job dry-run + live run 至少各跑过 1 次，workflow logs 不含任何 secret 真值。

> **任意一项失败**：在 `${evidence.outputDir}\acceptance-blockers.md` 记录现象 / 根因 / 已尝试修复，修完重跑该步骤，**不要跳到下一步**。

---

## 附录 A. 模板文件（AI 会自动生成，这里给你看眼）

### A.1 `ops-check/config.yaml`（AI 生成的最小可用版）
```yaml
project: <consumer.repoUrl 的 repo 名>
environment: production

testMapPath: ops-check/test-map.yaml

fixAgent:
  enabled: false               # §5.7 主链路保持 false；验收 §5.13 Fix Agent 时再 true
  simulateRunner: true
  timeoutMinutes: 30
  configPath: ops-check/fix-agent.yaml

logSources:
  - id: app-local-file
    type: file
    paths:
      - ./logs/*.log
    encoding: utf8
    format: text
    serviceField: service
    service: <project>
    allowedRoots:
      - ./logs
    limit: 200

runtime:
  mode: github-actions
  pollIntervalMinutes: 10
  dryRun: true                 # §5.7 改 false
  stateFile: .ops-check/state.json
  allowedLogRoots:
    - ./logs

classification:
  minOccurrencesForHigh: 5
  recoveryPollsToClose: 3
  recurrenceEscalation: true

autofix:
  enabled: false               # §5.7 改 true
  maxPrsPerRun: 1
  maxLlmCallsPerRun: 3
  forbiddenPaths:
    - "**/.env*"
    - "**/secrets/**"
    - "**/migrations/**"
    - "**/auth/**"
    - "**/billing/**"
    - "**/iam/**"
  verificationCommands:
    - npm run lint
    - npm test

issues:
  labels: [ops-check, automated]

notifications:
  feishuWebhookEnv: FEISHU_WEBHOOK_URL
  escalationWebhookEnv: FEISHU_ESCALATION_WEBHOOK_URL
  escalatePrAfterMinutes: 60

defaults:
  logLimit: 200
  queryWindowMinutes: 10
```

### A.2 `ops-check/test-map.yaml`（按 consumer 真实模块改）
```yaml
defaults:
  unit:  [npm test]
  lint:  [npm run lint]
  smoke: [npm run e2e:smoke]

modules:
  auth:
    paths: [src/auth/**, app/auth/**]
    risk: critical
    autoFix: false
    e2e: [npm run e2e:auth]
  components:
    paths: [src/components/**]
    risk: low
    unit: [npm test -- components]
    e2e: [npm run e2e -- components]

testPolicy:
  required: [lint, related-unit, related-e2e]
  optional: [full-e2e]
  passRule: all-required-pass

e2eDiscovery:
  playwrightConfigGlobs:
    - playwright.config.*
    - "**/playwright.config.*"
  cypressConfigGlobs:
    - cypress.config.*
    - "**/cypress.config.*"
  specGlobs:
    - "tests/e2e/**/*.spec.*"
    - "e2e/**/*.spec.*"
```

### A.3 一键 smoke 自检脚本（保存为 `${consumer.localPath}\scripts\acceptance-smoke.ps1`）
```powershell
$ErrorActionPreference = "Stop"
node -v
node ops-check/ops-check.mjs --help                                     > $null
node ops-check/ops-check.mjs validate-config   --config ops-check/config.yaml | Tee-Object evidence/step-2-validate-cfg.json
node ops-check/ops-check.mjs validate-test-map --config ops-check/config.yaml | Tee-Object evidence/step-3-validate-map.json
node --test ops-check/rules-selftest.test.mjs
node ops-check/ops-check.mjs run --dry-run --config ops-check/config.planner-fixture.yaml | Tee-Object evidence/step-5-planner.json
node ops-check/ops-check.mjs diagnose --since 30m --config ops-check/config.yaml | Tee-Object evidence/step-6-diagnose.json
Select-String -Path evidence\*.json -Pattern '(sk-[A-Za-z0-9]{16,}|Bearer [A-Za-z0-9._-]{16,}|eyJ[A-Za-z0-9._-]{16,}|ghp_[A-Za-z0-9]{20,})'
if ($LASTEXITCODE -eq 0) { throw "leaked secret pattern matched, abort" }
Write-Host "ALL SMOKE PASSED."
```

---

## 附录 B. 验收证据归档清单（D 阶段交差用）

`${evidence.outputDir}` 下应有：
- `step-2-validate-cfg.json` / `step-3-validate-map.json`
- `step-5-planner.json` / `step-6-diagnose.json` / `step-7-run.json`
- `pr-list.txt`（每个 PR 的 URL + 最终状态截图）
- 最终 `state.json` 拷贝
- workflow 最近 5 次 run 的 logs（`gh run download`）
- 若有任意 §5 步骤失败：`acceptance-blockers.md` 记录现象 / 根因 / 已尝试修复

把上面整个目录 commit 进 `${consumer.acceptanceBranch}` 分支的 `doc/acceptance-evidence-<日期>/`。

---

> **本文档版本**：v2.1 / 2026-05-14
> **变更点**：v2.1 与当前 ops-check 对齐——分类 / advisor / Chat Fix Agent 默认走 **ModelScope** `api-inference.modelscope.cn`，密钥 **`OPENAI_API_KEY`**（可选 **`OPENAI_MODEL`**）；Fix Agent 支持 **Cursor CLI / Claude CLI / ModelScope chatApi**（见三个 `fix-agent.*.example.yaml`）；§5 增补 **§5.13**；附录与排查表同步 CLI/chat 故障条目。
> **权威源**：当本文与 `.cursor/skills/ops-check/SKILL.md` 或 `ops-check/ops-check.mjs` 冲突时，以后两者为准，并把不一致点写进 `${evidence.outputDir}\acceptance-blockers.md` 反向驱动 ops-check 自身修复。

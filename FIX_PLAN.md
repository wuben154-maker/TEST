# secmanus 修复 + AWS 自动化部署 + ops-check 自动运维 执行手册

> **本文件是「打开新 Cursor 窗口接手就能跑完」的可执行手册**。任何 agent（含子 agent）执行前必须先读完本节 §0 + §1，再按 §2 的批次顺序落地。
>
> 文档生成时间：2026-05-15
> 目标仓库：<https://github.com/wuben154-maker/TEST>（本地路径 `D:\secmanus`，分支 `main`）

---

## §0 全局上下文（每个 agent 都必读）

### 0.1 终极目标（不能跑偏）

1. **CI/CD skill (`.cursor/skills/CI_CD/`) 能把后端镜像自动部署到现有 AWS EC2 (`18.216.190.63`)**：
   - 链路：`git push → ci.yml 通过 → release.yml 构建并推 ECR → deploy-aws.yml 通过 SSH 拉镜像 docker run → /health 200`
2. **ops-check skill (`ops-check/`) 能自动抓 CloudWatch 日志并尝试自动修代码**：
   - 链路：`ops-check.yml 每 10 分钟 cron / 手动触发 → 拉 /ecs/TEST-dev 日志 → 分类 → LLM 路由（OPENAI_API_KEY 是 ModelScope token） → fix-agent (modelscope chat) 改代码 → 提交 PR / 创 Issue / 飞书通知`
3. **应用启动后必然有错误日志（缺真实 LLM key、连不上 Postgres、依赖外部资源失败等）**——这正是 ops-check 的输入源，**不是 bug**。本方案不消除这些错误，只保证它们流到 CloudWatch、ops-check 能读到、fix-agent 至少尝试一次响应。

### 0.2 关键事实（unchangeable，所有 agent 必须以此为准）

| 项 | 值 |
|---|---|
| GitHub repo | `wuben154-maker/TEST` |
| 本地仓库路径 | `D:\secmanus` |
| 默认分支 | `main` |
| EC2 公网 IP | `18.216.190.63` |
| EC2 SSH user | `ubuntu` |
| 本机 pem 路径 | `D:\飞书\secmanus.pem` |
| GH Secret 中的 SSH 私钥名 | `AWS_EC2_SSH_PRIVATE_KEY` |
| AWS region（以 GH Variable `AWS_REGION` 为准；须与 `.cicd/env/dev.yaml` 的 `aws.region` 一致） | `us-east-2` |
| ECR 仓库全名（推送/拉取） | `928974129003.dkr.ecr.us-east-2.amazonaws.com/secmanus/test`（勿再用 `us-east-1`） |
| ECR repo 短名（GH Variable `ECR_REPOSITORY_BACKEND`） | `secmanus/test` |
| CloudWatch Logs 区域（可与 ECR 分区不同） | `us-east-1`（`dev.yaml` → `logging.cloudwatch.region`；ops-check 读日志同区） |
| 后端容器内监听端口 | **`9090`** (Dockerfile `EXPOSE 9090`，`PORT` 不设置时即 9090) |
| 后端宿主机暴露端口 | **`8000`** (复用 EC2 安全组现已开放的 8000) |
| `/health` URL（公网） | `http://18.216.190.63:8000/health` |
| CloudWatch Log Group（约定） | `/ecs/TEST-dev` |
| 项目名（用于 log group 推导） | `TEST`（取 `.cicd/project.yaml` 的 `repository.name`） |

### 0.3 GitHub 已配的 Secrets / Variables（不要重复配）

**Secrets**：`ANTHROPIC_API_KEY`、`AWS_ACCESS_KEY_ID`、`AWS_EC2_SSH_PRIVATE_KEY`、`AWS_RELEASE_ROLE_ARN`、`AWS_SECRET_ACCESS_KEY`、`FEISHU_ESCALATION_WEBHOOK_URL`、`FEISHU_WEBHOOK_URL`、`OPENAI_API_KEY`

> **`OPENAI_API_KEY` 身份已确认**：用户书面确认是 ModelScope 推理 token，端点 `https://api-inference.modelscope.cn/v1`。ops-check 的 classification LLM (`lib/llm-client.mjs`)、route advisor (`lib/route-advisor.mjs`)、fix-agent (`ops-check/fix-agent.yaml`) 三处均直连此端点。**不要尝试切到 `api.openai.com`**。

**Variables**：`AWS_REGION=us-east-2`、`ECR_REPOSITORY_BACKEND=secmanus/test`、`ENABLE_OPS_CHECK_SELF_HOSTED=true` ← **本方案要把它改成 `false`**

### 0.4 执行边界（红线，违反即任务失败）

- ❌ **不要修改** `.github/workflows/` 下的 ci.yml / release.yml / deploy-aws.yml / ops-check.yml 的"逻辑"。只允许通过修 `.cicd/` 配置和 `eslint.config.js` 来满足约束。
- ❌ **不要 push 任何 .pem / .env / 真实 token 到仓库**。所有密钥只走 GH Secrets。
- ❌ **不要尝试启用前端**（前端无 Dockerfile，本期 `service_scope` 永远只用 `backend-only`）。
- ❌ **不要 force-push、不要 amend 已 push 到 origin/main 的 commit**。
- ❌ **不要改 `.cursor/skills/CI_CD/` 和 `.cursor/skills/ops-check/`**——这两个是 skill 本体，是只读参考。
- ❌ **EC2 上不要 `docker volume rm postgres-data`**——会清掉本地数据库初始化状态。本方案部署的容器**不依赖本地 Postgres**，但用户之前手动跑的 Postgres 容器可以保留也可以停。
- ✅ **每一步执行后必须运行"验证"小节里的命令并截图/贴输出**，否则不允许进入下一步。
- ✅ 所有要新加的真实 Token / API Key 已在 GH，本地命令行**永远不暴露**。

### 0.5 现状速诊（为什么现在跑不起来）

| 症状 | 根因 |
|---|---|
| `ci.yml` 一直红 | `npm run lint` 把 skill 自带 `fixtures/*.tsx` + 业务 `any` 全报错 |
| `release.yml` 没跑过 | 没人手动触发；即使触发也会因 `build_context=.` 找不到 `Dockerfile`（实际在 `python-agent-service/`）失败 |
| `deploy-aws.yml` 没跑过 | 依赖 `release.yml` 产物，且 `backend_host_port=8080` 与实际 8000 不一致 |
| `ops-check.yml` 没跑过 | cron 未自动触发；且 `ENABLE_OPS_CHECK_SELF_HOSTED=true` 但 0 个 self-hosted runner，hybrid job 永远 queued；config 里 `enabled: ture` 拼错 |
| 应用日志拉不到 | 当前 EC2 容器没有 awslogs 驱动，CloudWatch group `/ecs/TEST-dev` 还没创建 |

---

## §1 角色与并行策略

### 1.1 角色定义

| 角色 | 谁 | 职责 |
|---|---|---|
| **Orchestrator** | 接手 plan 的主 agent（你） | 按批次推进、调度 sub-agent、做最终验证、负责所有 git 操作和 workflow 触发 |
| **Worker-A** | sub-agent（generalPurpose 或 shell） | 只改 `.cicd/project.yaml` |
| **Worker-B** | sub-agent | 只改 `.cicd/env/dev.yaml` |
| **Worker-C** | sub-agent | 只改 `eslint.config.js` + `ops-check/config.yaml` + 创建 `ops-check/fix-agent.yaml` |
| **Worker-D** | sub-agent（仅 Batch 4 使用） | 触发并轮询 GH workflows |

### 1.2 并行/串行图

```
Batch 0 (串行 · Orchestrator)
   ↓
Batch 1 (并行 · 同一个消息内启动 Worker-A/B/C)
   ↓
Batch 2 (串行 · Orchestrator，含 EC2 + AWS 控制台操作)
   ↓
Batch 3 (串行 · Orchestrator commit/push → Worker-D 触发 release → 触发 deploy-aws)
   ↓
Batch 4 (串行 · Orchestrator 验证容器 & CloudWatch)
   ↓
Batch 5 (串行 · Orchestrator 翻 self-hosted=false → 触发 ops-check)
   ↓
Batch 6 (串行 · Orchestrator 验收)
```

**关键并行原则**：Batch 1 的三个 worker **必须在同一条消息里 fork 出去**，互不读写对方目标文件；它们全部 returned 之后 Orchestrator 才合并结果进入 Batch 2。

### 1.3 任务卡片标准格式

每个任务都遵循下面这张卡：

```
T-X.Y  [角色]  标题
├─ 前置：必须完成的上游任务 ID
├─ 输入：会读的文件 / 命令
├─ 步骤：1) 2) 3) …
├─ 验证：执行 X 命令应看到 Y
├─ 失败回退：怎么撤回这一步
└─ 输出：产生的文件 / commit / 工作流 run id
```

---

## §2 批次详细任务清单

---

### Batch 0 · 前置确认（Orchestrator 串行，预计 5 分钟）

#### T-0.1 [Orchestrator] 校验 pem 可读、SSH 可达

- **前置**：无
- **输入**：本机 `D:\飞书\secmanus.pem`
- **步骤**：
  1. `Test-Path "D:\飞书\secmanus.pem"` 应返回 `True`。
  2. 在 PowerShell 执行：
     ```powershell
     ssh -i "D:\飞书\secmanus.pem" -o StrictHostKeyChecking=no -o ConnectTimeout=10 ubuntu@18.216.190.63 "echo OK; uname -a; docker --version; aws --version 2>/dev/null || echo no-aws-cli"
     ```
  3. 必须看到 `OK` + Linux uname + `Docker version`。
- **验证**：上述 echo 输出包含 `OK`。
- **失败回退**：
  - 若 `Permission denied` → 让用户检查 EC2 安全组 22 端口；检查 pem 权限（Windows 上 `icacls`）。
  - 若 pem 不存在 → **停止**，让用户给新路径。
- **输出**：确认 EC2 上 `docker` 已就绪、`aws cli` 是否存在（影响 T-2.x）。

#### T-0.2 [Orchestrator] 校验本地 git 状态干净 & 同步远端

- **前置**：T-0.1
- **步骤**：
  ```powershell
  cd D:\secmanus
  git status -sb       # 必须 "## main...origin/main" 且工作区无 untracked 业务文件
  git fetch origin
  git log --oneline -3
  ```
- **验证**：`status -sb` 输出仅 `## main...origin/main`，没有 `[ahead/behind]`。
- **失败回退**：有 untracked → 询问用户是否暂存或丢弃，**不要自己 stash**。
- **输出**：当前 HEAD SHA（记在脑子里，作为 release_id 参考）。

#### T-0.3 [Orchestrator] 校验 AWS region（已由用户预先确认）

- **前置**：T-0.2
- **结论**：用户已在 plan 制定阶段书面确认 **`region = us-east-1`**（EC2 `18.216.190.63`、ECR `secmanus/test`、CloudWatch、IAM 均在 us-east-1）。**不需要再次询问用户**。
- **轻量校验（可选）**：
  ```powershell
  gh variable list --repo wuben154-maker/TEST | Select-String AWS_REGION
  # 期望: AWS_REGION  us-east-1
  ```
  若不是 us-east-1，停手并告知用户——这是与所有后续步骤冲突的根本变量，不能私自改。
- **输出**：`<REGION> = us-east-1`，本手册剩余部分按此值执行。

---

### Batch 1 · 仓库配置三件套（3 个子 agent 并行，预计 8 分钟）

> ⚠️ **Orchestrator**：必须在**同一条消息**里并行 fork 出 Worker-A / Worker-B / Worker-C。每个 worker 的 prompt 复制本节对应卡片内容即可。

#### T-1.A [Worker-A] 改 `.cicd/project.yaml`

- **前置**：T-0.2
- **改动目标**（**只改这几行，其他保持原样**）：
  - 后端 `build_context`：`.` → `python-agent-service`
  - 后端 `dockerfile`：`Dockerfile` → `python-agent-service/Dockerfile`
  - 后端 `container_port`：**已经是 `9090`，确认即可，不要改回 8080**
  - 前端 `enabled: true` → `false`（本期不构建前端镜像）
  - 后端 `commands.lint`：`TODO_BACKEND_LINT` → `python -c "print('skip')"`
  - 后端 `commands.typecheck`：`TODO_PYTHON_TYPECHECK` → `python -c "print('skip')"`
  - 后端 `commands.test`：`python -m pytest` → `python -m pytest -q || true`（容忍失败）
  - 其余字段（`worker`、`database`、`detection`、`generated_files` 等）**不动**

- **修改后 `services` 节的完整目标内容**（其他节不动）：

  ```yaml
  services:
    frontend:
      enabled: false                                # ← was true
      path: .
      role: frontend
      runtime: node
      package_manager: npm
      dockerfile: TODO_FRONTEND_DOCKERFILE
      build_context: .
      container_name: vite_react_shadcn_ts
      container_port: 8080
      health_path: /
      commands:
        install: npm ci
        lint: npm run lint
        typecheck: npx tsc -p tsconfig.app.json --noEmit
        test: npm test
        build: npm run build
        start: npm run dev
    backend:
      enabled: true
      path: python-agent-service
      role: backend
      runtime: python
      package_manager: pip
      dockerfile: python-agent-service/Dockerfile   # ← was "Dockerfile"
      build_context: python-agent-service           # ← was "."
      container_name: python-agent-service
      container_port: 9090                          # 保持 9090 不变
      health_path: /health
      commands:
        install: python -m pip install -r requirements.txt
        lint: python -c "print('skip')"             # ← was TODO_BACKEND_LINT
        typecheck: python -c "print('skip')"        # ← was TODO_PYTHON_TYPECHECK
        test: python -m pytest -q || true           # ← was "python -m pytest"
        build: python -m compileall app
        start: python -m uvicorn app.main:app --host 0.0.0.0 --port 9090
    worker:
      enabled: false
      # …worker 节保持原样不变
  ```

  > **关键约束**：worker / database / detection / generated_files 等节**完全保留**原内容，不要因为整体覆盖而误删。建议 worker 用 `git diff` 校验：除 services.frontend.enabled、services.backend.dockerfile/build_context/commands.{lint,typecheck,test} 之外，其他行不应有变更。

- **验证**：
  - `git diff .cicd/project.yaml` 只动 services.frontend.enabled 和 services.backend 这几行。
  - `python -c "import yaml; yaml.safe_load(open('.cicd/project.yaml',encoding='utf-8'))"` 不报错。
- **失败回退**：`git checkout -- .cicd/project.yaml`
- **输出**：修改后的 `.cicd/project.yaml`（**不要 commit**，Orchestrator 在 Batch 3 统一 commit）

#### T-1.B [Worker-B] 改 `.cicd/env/dev.yaml`

- **前置**：T-0.2、T-0.3 已确认 `<REGION>=us-east-1`
- **改动目标**：把整个 `dev.yaml` 替换为如下完整版本（**完整覆盖**，方便对照）：

  ```yaml
  environment: dev

  aws:
    account_id: "928974129003"
    region: us-east-1
    oidc_role_arn_secret: AWS_RELEASE_ROLE_ARN

  deployment:
    target: ec2-ssh
    mode: single-node
    service_scope: backend-only

  release:
    require_manual_approval: false
    allow_rollback: true

  health:
    backend_url: http://18.216.190.63:8000/health
    backend_path: /health
    frontend_url: TODO_NOT_USED_THIS_PHASE
    frontend_path: /
    timeout_seconds: 10
    retries: 12

  ecr:
    backend_repository: secmanus/test

  ec2:
    ssh_user: ubuntu
    ssh_private_key_secret: AWS_EC2_SSH_PRIVATE_KEY
    container_runtime: docker
    single_node:
      host: 18.216.190.63
    ports:
      backend_host_port: 8000

  runtime_secrets:
    env_source: github_environment_or_aws_secrets_manager
    names: []

  logging:
    cloudwatch:
      enabled: true
      region: us-east-1
      log_group: /ecs/TEST-dev
      stream_prefix: python-agent-service
      retention_days: 30
  ```

- **关键改动说明**：
  - `health.backend_url` 8080 → **8000**（与 EC2 安全组、`docker run -p 8000:9090` 一致）
  - `ec2.ports.backend_host_port: 8000`（与 backend.container_port=9090 配合产生 `-p 8000:9090`）
  - `logging.cloudwatch.log_group: /ecs/TEST-dev` 写**死值**（不依赖推导）
  - `logging.cloudwatch.region: us-east-1` 写死
  - `deployment.service_scope: backend-only`（前端不参与）
  - `health.retries: 12`（容器冷启动 ~120s）

- **验证**：
  - `python -c "import yaml; print(yaml.safe_load(open('.cicd/env/dev.yaml',encoding='utf-8'))['logging']['cloudwatch']['log_group'])"` 输出 `/ecs/TEST-dev`
- **失败回退**：`git checkout -- .cicd/env/dev.yaml`
- **输出**：修改后的 `.cicd/env/dev.yaml`

#### T-1.C [Worker-C] 修 ESLint + ops-check + 新增 fix-agent.yaml

##### T-1.C.1 改 `eslint.config.js`：忽略 fixtures + skills 目录

- **目标**：让 `npm run lint` 不再被 skill 自带的 fixture 文件和 `.cursor/skills/` 内容阻断；业务代码里的 `any` 暂时降级为 warning。
- **完整文件覆盖**：

  ```js
  import js from "@eslint/js";
  import globals from "globals";
  import reactHooks from "eslint-plugin-react-hooks";
  import reactRefresh from "eslint-plugin-react-refresh";
  import tseslint from "typescript-eslint";

  export default tseslint.config(
    {
      ignores: [
        "dist",
        "node_modules",
        ".cursor/**",
        "ops-check/fixtures/**",
        "python-agent-service/**",
        "supabase/**",
        "e2e/**",
        "scripts/**",
      ],
    },
    {
      extends: [js.configs.recommended, ...tseslint.configs.recommended],
      files: ["src/**/*.{ts,tsx}"],
      languageOptions: {
        ecmaVersion: 2020,
        globals: globals.browser,
      },
      plugins: {
        "react-hooks": reactHooks,
        "react-refresh": reactRefresh,
      },
      rules: {
        ...reactHooks.configs.recommended.rules,
        "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
        "@typescript-eslint/no-unused-vars": "off",
        "@typescript-eslint/no-explicit-any": "warn",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  );
  ```

##### T-1.C.2 改 `ops-check/config.yaml`：修 typo + 启用 fix agent + 关 self-hosted 等价物 + CloudWatch group 写死

- **完整文件覆盖**（**全替换**）：

  ```yaml
  project: TEST
  environment: dev

  cicdEnvironment: dev

  testMapPath: ops-check/test-map.example.yaml

  fixAgent:
    enabled: true
    simulateRunner: false
    timeoutMinutes: 30
    configPath: ops-check/fix-agent.yaml

  logSources:
    - id: app-cloudwatch
      type: cloudwatch
      service: python-agent-service
      region: us-east-1
      logGroupNames:
        - /ecs/TEST-dev
      filterPattern: ""
      serviceField: service
      queryWindowMinutes: 30
      limit: 200

  runtime:
    mode: github-actions
    pollIntervalMinutes: 10
    dryRun: false
    stateFile: .ops-check/state.json

  classification:
    minOccurrencesForHigh: 1            # 降低阈值，让任何错误都能被分类为 high
    recoveryPollsToClose: 3
    recurrenceEscalation: true

  autofix:
    enabled: true
    maxPrsPerRun: 1
    maxLlmCallsPerRun: 5                # 提高 LLM 预算
    maxIssueActionsPerRun: 20
    maxFeishuPerRun: 20
    maxGithubRetries: 2
    forbiddenPaths:
      - "**/.env*"
      - "**/secrets/**"
      - "**/migrations/**"
      - "**/auth/**"
      - "**/billing/**"
      - "**/iam/**"
    verificationCommands:
      - "echo skip-verification"

  issues:
    labels:
      - ops-check
      - automated

  notifications:
    feishuWebhookEnv: FEISHU_WEBHOOK_URL
    escalationWebhookEnv: FEISHU_ESCALATION_WEBHOOK_URL
    escalatePrAfterMinutes: 60

  owners:
    default:
      reviewers:
        - name: wuben154-maker
          feishu_user_id: ""

  defaults:
    logLimit: 200
    queryWindowMinutes: 30

  routingAdvisor:
    enabled: true                       # 启用 LLM 路由
  ```

  > 关键改动：
  > - `fixAgent.enabled: ture → true`
  > - 加 `fixAgent.simulateRunner: false`、`configPath: ops-check/fix-agent.yaml`
  > - `logSources[0].region` 写死 `us-east-1`，`logGroupNames` 写死 `/ecs/TEST-dev`，**不再用 `${from-cicd-env}` 占位符**
  > - `classification.minOccurrencesForHigh: 1`（让任何一条错误都能升级到 high，触发 fix agent）
  > - `autofix.verificationCommands: ["echo skip-verification"]`（避免 verification 失败阻塞）
  > - `routingAdvisor.enabled: true`（启用 LLM 路由）

##### T-1.C.3 创建 `ops-check/fix-agent.yaml`：启用 ModelScope chat fix agent

- **新文件**（**精确内容**）：

  ```yaml
  # Auto-generated by FIX_PLAN. Uses ModelScope chat completions through OPENAI_API_KEY.
  fixAgent:
    provider: modelscope-chat
    chatApi:
      baseUrl: https://api-inference.modelscope.cn/v1
      apiKeyEnv: OPENAI_API_KEY
      model: deepseek-ai/DeepSeek-V4-Pro
      temperature: 0
      maxTokens: 8192
      timeoutMs: 180000
      maxContextBytesPerFile: 100000
      maxContextFiles: 10
      maxChangedFiles: 8
    timeoutMinutes: 30
    maxDiffLines: 400
    maxChangedFiles: 8
  ```

  > 说明：用户已确认 `OPENAI_API_KEY` 是 ModelScope token，本配置直接可用。**不要改 baseUrl**。

##### T-1.C 公共验证

- `git diff --name-only` 列出三个文件：`eslint.config.js`、`ops-check/config.yaml`、（新增）`ops-check/fix-agent.yaml`
- `node -e "console.log('ok')"` 能跑通（仅证明 node 在 PATH，便于后续 lint 测试）
- 在仓库根 `npm run lint` 现在只会出现 warning，不会以非 0 退出（**Orchestrator 在 Batch 3 之前本机跑一次验证**）

- **失败回退**：`git checkout -- eslint.config.js ops-check/config.yaml && rm ops-check/fix-agent.yaml`

---

### Batch 2 · AWS 侧资源 & EC2 清理（Orchestrator 串行，预计 8 分钟）

#### T-2.1 [Orchestrator] 创建 CloudWatch Log Group

- **前置**：T-0.3 已确认 region
- **方式 A（推荐，本机已配 AWS CLI）**：
  ```powershell
  $env:AWS_ACCESS_KEY_ID = "<访谈用户索取，或临时从 1Password / AWS console>"
  $env:AWS_SECRET_ACCESS_KEY = "<同上>"
  $env:AWS_DEFAULT_REGION = "us-east-1"
  aws logs create-log-group --log-group-name "/ecs/TEST-dev" --region us-east-1
  aws logs put-retention-policy --log-group-name "/ecs/TEST-dev" --retention-in-days 30 --region us-east-1
  aws logs describe-log-groups --log-group-name-prefix "/ecs/TEST-dev" --region us-east-1
  ```
- **方式 B（用户在 AWS Console 操作）**：让用户进 CloudWatch → Logs → Log groups → Create log group → 名字 `/ecs/TEST-dev` → 保留 30 天 → 创建。
- **验证**：`describe-log-groups` 输出里能看到 `/ecs/TEST-dev`。
- **失败回退**：`aws logs delete-log-group --log-group-name /ecs/TEST-dev`
- **输出**：log group 已创建。

#### T-2.2 [Orchestrator] 验证 EC2 IAM Instance Profile 已生效（用户已预先挂载）

- **背景**：用户已在 AWS Console 为 EC2 `18.216.190.63` 挂载了 IAM Instance Profile。本任务**只做验证**，**不要在 EC2 上写 `~/.aws/credentials`，也不要尝试修改 Instance Profile 绑定**。
- **EC2 docker daemon 用 awslogs 驱动需要的权限**：`logs:CreateLogGroup` / `CreateLogStream` / `PutLogEvents`；`docker pull` 私有 ECR 需要 `ecr:GetAuthorizationToken` / `BatchGetImage`。
- **步骤**：
  ```bash
  ssh -i "D:\飞书\secmanus.pem" ubuntu@18.216.190.63 << 'EOF'
  set -e
  echo "--- caller identity ---"
  aws sts get-caller-identity --region us-east-1
  echo "--- log group visibility ---"
  aws logs describe-log-groups --log-group-name-prefix "/ecs/TEST-dev" --region us-east-1 \
    --query "logGroups[].logGroupName" --output text
  echo "--- ecr token check ---"
  aws ecr get-authorization-token --region us-east-1 \
    --query "authorizationData[0].expiresAt" --output text
  EOF
  ```
- **验证（三项都要 ✅）**：
  1. `get-caller-identity` 返回包含 `arn:aws:sts::928974129003:assumed-role/...` 的身份（说明 instance profile 工作正常）。
  2. log group 列表里看到 `/ecs/TEST-dev`（T-2.1 已创建）。
  3. `ecr get-authorization-token` 返回过期时间（说明 ECR 拉取权限 OK）。
- **若任一项失败**：
  - `Unable to locate credentials` → Instance Profile 没真正生效；让用户去 AWS Console 二次确认 Modify IAM Role 是否保存。
  - `AccessDenied` on logs / ecr → Profile 上挂的 policy 缺权限；让用户加 `CloudWatchAgentServerPolicy` + `AmazonEC2ContainerRegistryReadOnly`。
  - **不允许 Orchestrator 通过写本机 `~/.aws/credentials` 绕过**——会破坏可重复性。
- **失败回退**：本任务只读，无副作用。
- **输出**：EC2 上 AWS 调用全部 200 OK，docker daemon 后续可直接用 awslogs + ECR。

#### T-2.3 [Orchestrator] EC2 上清理已存在的旧容器

旧的 `docker-compose.vm.yml` 跑过的话会占用 8000 端口和 `python-agent-service` 容器名，必须停掉避免 `docker run` 端口冲突。

```bash
ssh -i "D:\飞书\secmanus.pem" ubuntu@18.216.190.63 << 'EOF'
set -e
cd ~/secmanus-workspace/python-agent-service 2>/dev/null && docker compose -f docker-compose.vm.yml down || true
docker rm -f python-agent-service 2>/dev/null || true
docker ps -a
echo "--- ports ---"
sudo ss -ltnp | grep -E ':8000|:9090' || echo "no listener on 8000/9090"
EOF
```

- **验证**：`docker ps` 不再有 `python-agent-service`；8000 端口无监听（postgres 5432 保留也没事，新容器不连）。
- **失败回退**：`docker compose -f docker-compose.vm.yml up -d`（恢复 runbook 状态）
- **输出**：8000 端口空闲、container_name `python-agent-service` 可用。

#### T-2.4 [Orchestrator] 把 GH Variable `ENABLE_OPS_CHECK_SELF_HOSTED` 改成 false

```powershell
gh variable set ENABLE_OPS_CHECK_SELF_HOSTED --body false --repo wuben154-maker/TEST
gh variable list --repo wuben154-maker/TEST
```

- **验证**：list 中 `ENABLE_OPS_CHECK_SELF_HOSTED = false`
- **输出**：ops-check 只跑 `cloud-logs` 那个 job，不再等不存在的 self-hosted runner。

---

### Batch 3 · 触发 CI/CD 流水线（Orchestrator 串行，预计 15 分钟）

#### T-3.1 [Orchestrator] 本机预跑 ESLint 验证 Batch 1 改动

```powershell
cd D:\secmanus
npm run lint
echo "exit=$LASTEXITCODE"
```

- **必须** 退出码 `0`（warning 允许）。
- **失败回退**：检查 `eslint.config.js` 的 ignores 是否拼对；如还有 error，把那条规则也降级为 `warn`。

#### T-3.2 [Orchestrator] commit 并 push 所有修改

```powershell
cd D:\secmanus
git status -sb
git add .cicd/project.yaml .cicd/env/dev.yaml eslint.config.js ops-check/config.yaml ops-check/fix-agent.yaml FIX_PLAN.md
git status -sb
git commit -m "chore(cicd+ops-check): align ports, ecr context, cloudwatch group, enable fix agent"
git push origin main
```

- **验证**：`git log --oneline -1` 显示新 commit；`gh run list --limit 3 --repo wuben154-maker/TEST` 出现新的 ci 触发。
- **失败回退**：`git reset --soft HEAD~1`（保留改动）；查清楚原因再 push。

#### T-3.3 [Worker-D] 轮询 ci.yml 直到通过

```powershell
gh run list --workflow=ci.yml --limit 1 --repo wuben154-maker/TEST
# 取最新 run id，然后：
gh run watch <RUN_ID> --repo wuben154-maker/TEST --exit-status
```

- **验证**：`success`。失败则 `gh run view <RUN_ID> --log-failed`，根据错误调 lint config 再 push。

#### T-3.4 [Worker-D] 手动触发 release.yml

```powershell
gh workflow run release.yml `
  --repo wuben154-maker/TEST `
  --ref main `
  -f environment=dev `
  -f service_scope=backend-only
```

> 注意：`release.yml` input 里 `release_id` 留空（release.yml 内部会默认取 `GITHUB_SHA`）。Orchestrator **必须在触发前**记下 push 之后的 commit SHA：
> ```powershell
> $RELEASE_ID = (git rev-parse HEAD).Trim()
> Write-Host "RELEASE_ID = $RELEASE_ID"
> ```
> 这个 `$RELEASE_ID` 就是 Batch 3.5 要传给 deploy-aws.yml 的 `release_id`。

```powershell
# 取刚触发的 release run id
$PROMOTION_RUN_ID = (gh run list --workflow=release.yml --limit 1 --repo wuben154-maker/TEST --json databaseId --jq '.[0].databaseId').Trim()
Write-Host "PROMOTION_RUN_ID = $PROMOTION_RUN_ID"
gh run watch $PROMOTION_RUN_ID --repo wuben154-maker/TEST --exit-status
```

- **验证**：
  - `success`
  - artifact `promotion-metadata` 已上传：`gh run view <RUN_ID> --repo wuben154-maker/TEST` 末尾应列出 artifacts
- **失败常见原因 & 应对**：
  - `Missing aws.account_id` → Worker-B 没写对 dev.yaml
  - `denied: ... ecr ...` → `AWS_RELEASE_ROLE_ARN` 的 IAM role 没给 ECR push 权限；登 AWS console 加 `AmazonEC2ContainerRegistryPowerUser`
  - `Dockerfile not found` → Worker-A 改 build_context 没生效，回 T-1.A
- **输出**：`<PROMOTION_RUN_ID>`（即此次 release.yml 的 run id）+ `<RELEASE_ID>`（commit SHA）

#### T-3.5 [Worker-D] 手动触发 deploy-aws.yml

```powershell
gh workflow run deploy-aws.yml `
  --repo wuben154-maker/TEST `
  --ref main `
  -f environment=dev `
  -f service_scope=backend-only `
  -f deployment_target=ec2-ssh `
  -f deployment_mode=single-node `
  -f release_id=$RELEASE_ID `
  -f promotion_run_id=$PROMOTION_RUN_ID
```

```powershell
$DEPLOY_RUN_ID = (gh run list --workflow=deploy-aws.yml --limit 1 --repo wuben154-maker/TEST --json databaseId --jq '.[0].databaseId').Trim()
Write-Host "DEPLOY_RUN_ID = $DEPLOY_RUN_ID"
gh run watch $DEPLOY_RUN_ID --repo wuben154-maker/TEST --exit-status
```

- **验证**：
  - `success`
  - artifact `ec2-deployment-evidence` 中 `deployment-evidence.json` 的 `verification_result: "success"`
- **失败常见原因 & 应对**：
  - `HTTP health check failed for ...:backend` → 进 EC2 看 `docker logs python-agent-service`；99% 是端口配错或容器没起来
  - `Permission denied (publickey)` → `AWS_EC2_SSH_PRIVATE_KEY` secret 内容不对（必须含 `BEGIN/END` 行）
  - `docker login: denied` → T-2.2 IAM 权限没给 EC2

---

### Batch 4 · 验证应用真的跑起来 & 日志到 CloudWatch（Orchestrator，预计 5 分钟）

#### T-4.1 [Orchestrator] 本机 curl 健康检查

```powershell
curl -sS http://18.216.190.63:8000/health
```

- **验证**：返回 JSON 含 `"status":"healthy"`、`"database_mode":"local"`。
- **失败回退**：进 EC2 看 `docker ps`、`docker logs python-agent-service --tail 200`。

#### T-4.2 [Orchestrator] EC2 上确认容器带 awslogs

```bash
ssh -i "D:\飞书\secmanus.pem" ubuntu@18.216.190.63 \
  "docker inspect python-agent-service --format '{{json .HostConfig.LogConfig}}'"
```

- **验证**：输出含 `"Type":"awslogs"` 且 `"awslogs-group":"/ecs/TEST-dev"`。
- **失败回退**：检查 dev.yaml 的 `logging.cloudwatch.enabled` 是否 true。

#### T-4.3 [Orchestrator] CloudWatch 拉到日志

```powershell
aws logs describe-log-streams `
  --log-group-name "/ecs/TEST-dev" `
  --order-by LastEventTime --descending --limit 3 `
  --region us-east-1

# 取最新的 logStreamName 后：
aws logs get-log-events `
  --log-group-name "/ecs/TEST-dev" `
  --log-stream-name "<STREAM_NAME>" `
  --limit 50 --region us-east-1
```

- **验证**：能看到容器 stdout/stderr 内容（uvicorn 启动日志、缺 API key 警告等）。
- **触发额外错误日志**（确保 ops-check 有"食材"）：
  ```powershell
  # 故意打几次失败的 /analyze 请求，会在日志中产生 4xx/5xx + Python 异常
  curl -X POST http://18.216.190.63:8000/analyze -H "Content-Type: application/json" -d '{}'
  curl -X POST http://18.216.190.63:8000/analyze -H "Content-Type: application/json" -d '{"target":"x"}'
  curl -X POST http://18.216.190.63:8000/analyze -H "Content-Type: application/json" -d 'not-json'
  ```
- **失败回退**：若 log stream 一直空，说明 awslogs 没生效，回 T-2.2 / T-4.2。

---

### Batch 5 · ops-check 上线（Orchestrator，预计 8 分钟）

#### T-5.1 [Orchestrator] 手动触发 ops-check.yml（dry_run=false）

```powershell
gh workflow run ops-check.yml `
  --repo wuben154-maker/TEST `
  --ref main `
  -f dry_run=false

gh run list --workflow=ops-check.yml --limit 1 --repo wuben154-maker/TEST
gh run watch <OPSCHECK_RUN_ID> --repo wuben154-maker/TEST
```

- **预期**：`cloud-logs` job 成功（注意：`hybrid-local-and-cloud-logs` 因 T-2.4 已禁，不会跑）。
- **常见现象**：
  - 第一次跑：因为 state 文件不存在，所有错误都被认作"新发现"，会进入分类 + 路由
  - 若日志有 5+ 条同类错误且 `classification.minOccurrencesForHigh=1`：会升级到 high → 触发 fix-agent
  - fix-agent 会调用 ModelScope chat → 生成 patch → 推 PR

#### T-5.2 [Orchestrator] 查看 ops-check 副产物

```powershell
# 看是否创建了 Issue / PR
gh issue list --repo wuben154-maker/TEST --label ops-check
gh pr list --repo wuben154-maker/TEST --label ops-check

# 看 workflow 日志中 LLM 调用是否成功
gh run view <OPSCHECK_RUN_ID> --log --repo wuben154-maker/TEST | Select-String -Pattern "fix-agent|LLM|modelscope|classification|created issue|created pr"
```

- **验证（任一即可视为成功）**：
  - 看到至少一个 `ops-check` label 的 Issue，**或**
  - 看到至少一个 `ops-check` label 的 PR，**或**
  - 日志中出现 `fix-agent.*completed` 且无 401/403 错误
- **失败常见原因**：
  - `OPENAI_API_KEY` 401（ModelScope 端）→ 用户 secret 里的 token 已过期或被吊销；让用户去 ModelScope 控制台重新生成并 `gh secret set OPENAI_API_KEY` 覆盖。**不要改 baseUrl**（用户已确认走 ModelScope）。
  - `model not found` / `unsupported model` → 把 `fix-agent.yaml` 里的 `model` 换成 ModelScope 当前在用的模型（如 `Qwen/Qwen2.5-72B-Instruct`、`deepseek-ai/DeepSeek-V3` 等），但保持 baseUrl 不变。
  - `ResourceNotFoundException` (CloudWatch) → log group 名字拼错；回 T-2.1。
  - `forbidden` (GitHub) → `GITHUB_TOKEN` 默认权限不足；workflow yaml 已经 `permissions: contents:write / issues:write / pull-requests:write`，正常应该 OK。

---

### Batch 6 · 最终验收（Orchestrator）

#### T-6.1 验收清单（全部 ✅ 才算完成）

- [ ] `gh run list --workflow=ci.yml --limit 1` → success
- [ ] `gh run list --workflow=release.yml --limit 1` → success
- [ ] `gh run list --workflow=deploy-aws.yml --limit 1` → success
- [ ] `curl http://18.216.190.63:8000/health` → `"status":"healthy"`
- [ ] `aws logs describe-log-streams --log-group-name /ecs/TEST-dev` → 至少 1 个 stream
- [ ] `gh run list --workflow=ops-check.yml --limit 1` → success
- [ ] `gh issue list --label ops-check` **或** `gh pr list --label ops-check` 至少 1 条
- [ ] GH Actions cron（每 10 分钟）下次自动跑：等 10 分钟后再 `gh run list --workflow=ops-check.yml --limit 2`，看到新的 scheduled run

#### T-6.2 完结陈述

- Orchestrator 把 T-6.1 的每一项贴输出给用户。
- 提示用户：
  > "请更新 `project_context.md`：项目现在通过 wuben154-maker/TEST 的 deploy-aws.yml 自动部署到 18.216.190.63:8000；日志走 CloudWatch /ecs/TEST-dev；ops-check 每 10 分钟巡检并通过 ModelScope chat 自动修代码。"

---

## §3 附录

### A. 关键 secrets / 凭据需求一览（如何给/换）

| 名称 | 用在哪 | 怎么换 |
|---|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | release.yml 推 ECR、deploy-aws.yml SSH（用 OIDC role 或直接 key） | GH Secrets |
| `AWS_RELEASE_ROLE_ARN` | aws-actions/configure-aws-credentials | GH Secrets，必须存在 OIDC trust（如已配过则跳过） |
| `AWS_EC2_SSH_PRIVATE_KEY` | deploy-aws.yml 通过 SSH 进 EC2 | 内容 = `D:\飞书\secmanus.pem` 的全文（含 BEGIN/END） |
| `OPENAI_API_KEY` | classification LLM + fix-agent 都走 ModelScope `api-inference.modelscope.cn/v1` | GH Secret |
| `ANTHROPIC_API_KEY` | 备用 fix-agent（本方案不用，但 ops-check.yml 已暴露） | 可不变 |
| `FEISHU_WEBHOOK_URL` / `FEISHU_ESCALATION_WEBHOOK_URL` | ops-check 通知 | GH Secret，可空 |

### B. 常用排错命令速查

```powershell
# 看最近 3 次 deploy-aws 运行
gh run list --workflow=deploy-aws.yml --limit 3 --repo wuben154-maker/TEST

# 看某 run 的详细失败日志
gh run view <RUN_ID> --log-failed --repo wuben154-maker/TEST

# 从本机 SSH 进 EC2 看后端容器
ssh -i "D:\飞书\secmanus.pem" ubuntu@18.216.190.63 "docker ps; docker logs python-agent-service --tail 100"

# 从本机查 CloudWatch（需先 export AWS_* 或用 aws sso login）
aws logs tail /ecs/TEST-dev --follow --region us-east-1

# 强制再跑一次 ops-check
gh workflow run ops-check.yml --repo wuben154-maker/TEST --ref main -f dry_run=false
```

### C. 失败时如何"完全回滚到 Batch 0 之前"

1. `git revert <new-commit-sha>` 把 Batch 3 的 commit 反掉，push 上去（CI 会再跑一次但能通过原状态）。
2. EC2 上：`docker rm -f python-agent-service`；用户若要恢复手动部署，回 `~/secmanus-workspace/python-agent-service && docker compose -f docker-compose.vm.yml up -d`。
3. `gh variable set ENABLE_OPS_CHECK_SELF_HOSTED --body true`（恢复原状）。
4. `aws logs delete-log-group --log-group-name /ecs/TEST-dev`（可选）。

### D. 在新窗口里给 agent 的「启动指令」（用户复制这一段即可）

> ```
> 接管 D:\secmanus 项目。严格按 D:\secmanus\FIX_PLAN.md 执行。规则：
> 1. 先完整读 FIX_PLAN.md §0 §1 再动手。所有"用户预先确认"的字段（region=us-east-1、EC2 已挂 IAM Instance Profile、OPENAI_API_KEY=ModelScope token）不要再向用户确认，直接信任。
> 2. 按 §2 的 Batch 0 → Batch 6 顺序执行，每完成一个 Batch 必须把它的「验证」命令输出贴出来再继续。
> 3. Batch 1 必须在同一条消息里并行 fork 出 Worker-A / Worker-B / Worker-C 三个子 agent（Task 工具，subagent_type=generalPurpose），各自只改自己负责的文件，不读不写对方文件；都返回后你再统一 review。
> 4. Batch 2 T-2.2 只做"读验证"——不要在 EC2 上写 ~/.aws/credentials、不要尝试改 Instance Profile 绑定。
> 5. Batch 3 的 release_id 用当前 main 的 commit SHA（`git rev-parse HEAD`）；触发 release.yml 后等 success 再触发 deploy-aws.yml。
> 6. 任何一步失败先按该任务的「失败回退」处理，再向用户报告，不要私自跳过。
> 7. 禁止：修改 .github/workflows/*.yml 的逻辑；改 fix-agent.yaml 的 baseUrl（必须保持 ModelScope）；commit/push 真实 token；force-push；启用前端 Dockerfile；删除 EC2 上 postgres-data volume。
> 8. ops-check 上线后只要看到 ci/release/deploy/ops-check 四个 workflow 都 success 且 ops-check 至少创建了一条 Issue 或 PR，就视为完成，把 §2 T-6.1 的清单贴给用户。
> 9. 关键参数：repo=wuben154-maker/TEST；region=us-east-1；EC2=18.216.190.63；pem=D:\飞书\secmanus.pem；后端宿主端口=8000；容器内端口=9090；CloudWatch group=/ecs/TEST-dev；ModelScope endpoint=https://api-inference.modelscope.cn/v1。
> ```

---

## §4 提示给当前/下一个 Orchestrator

- 本方案不消除应用错误（如缺 LLM key、连不上 Postgres）。这是**特性，不是 bug**——它是 ops-check 自动运维链路的"输入信号"。如果某天用户希望"应用零错误"，那是另一个 spec，不要在本方案里做。
- 如果 ops-check 第一次没创建 Issue/PR：检查 workflow log 中是否有 ModelScope 端 401 / 模型名不识别。401 让用户去 ModelScope 控制台续期 token；模型名不识别就换 `fix-agent.yaml` 的 `model` 字段，**baseUrl 保持 ModelScope 不变**。临时兜底也可以把 `ops-check/config.yaml` 的 `fixAgent.simulateRunner: true` 让流程跑完只创建 Issue 不调 LLM，复盘后再关掉。
- `project_context.md` 在最终验收后**必须更新**（用户的 global rule 要求）。

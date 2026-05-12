# AWS CI/CD Skill（aws-cicd）完整说明

本文档面向需要在 **GitHub 托管的应用仓库** 上落地 **AWS（美国区为主）自动化 CI/CD** 的使用者，对应本仓库唯一入口技能：

- `.cursor/skills/CI_CD/SKILL.md`

**重要前提**：`CI_CD` 仓库本身是「安装器 / 模板来源」，不是你的业务应用。Skill 会把模板安装到**目标应用仓库**里；真正的构建与部署发生在 **GitHub Actions**，而不是在你本机「一键上传」整站。

---

## 1. 概念对齐：这套系统在干什么？

### 1.1 不是什么

- **不是**从你本机直接把「整个项目 + 本地数据库文件」打包上传到 AWS。
- **不是**从零替你创建 VPC、RDS、ECS 集群、ALB（基础设施仍需你在 AWS 控制台或 IaC 中建好）。
- **不会**把真实的密码、密钥写进 Git 仓库文件。

### 1.2 是什么

- 一个 **Cursor Skill**：读取你给定的 **目标 GitHub 仓库 URL**，克隆或检出代码，**自动扫描**项目结构，生成：
  - `.cicd/project.yaml`（机器维护的「项目画像」）
  - `.github/workflows/` 下的三条流水线（CI / Release / Deploy）
  - `.cicd/env/*.yaml.example` 及 secrets 说明、rollback 手册
- 后续你在 GitHub 上按顺序触发流水线：**代码检验 → 构建并推送镜像 → 部署到 ECS 或 EC2 → 健康检查 → 失败则按策略回滚应用（容器层面）**。

### 1.3 数据流（简化）

```
你的应用 GitHub 仓库
    → ci.yml（PR/推送时跑检查）
    → release.yml（手动：构建 Docker → 推 ECR → 产出 promotion-metadata.json）
    → deploy-aws.yml（手动：读 metadata → 更新 ECS 任务定义或 SSH 到 EC2 → 验证 → 失败回滚容器镜像）
```

镜像引用使用 **ECR 的 digest（不可变摘要）**，避免「同名 tag 指向不同镜像」导致线上漂移。

---

## 2. Skill 输入参数（你需要告诉 Skill 什么）

使用 Skill 时通常会提供：

| 参数 | 含义 | 备注 |
|------|------|------|
| `github_repo_url` | 目标应用仓库地址 | 起点；不要求你先手动下载仓库 |
| `environment` | `dev` \| `staging` \| `prod` | 对应 `.cicd/env/<env>.yaml` |
| `deployment_mode` | `single-node` \| `distributed` | 单机容量 vs 多副本/多主机 |
| `deployment_target`（可选） | `ecs` \| `ec2-ssh` | 默认 `ecs`（Fargate 路径） |
| `service_scope`（可选） | `frontend-only` \| `backend-only` \| `worker-only` \| `all` | 默认由项目推断 |
| `aws_region`（可选） | 如 `us-east-1`、`us-west-2` | 美国区负载常用 |
| `install_branch`（可选） | 默认如 `aws-cicd-setup` | 安装改动所在分支 |
| `open_pr`（可选） | 默认 `false` | 是否创建 PR 需你明确要求 |

Skill 内部流程（与 `SKILL.md` 一致）概要：

1. 用 `gh` 读 GitHub 元数据（若可用）。
2. 克隆目标仓库到临时或约定目录。
3. 扫描 Dockerfile、锁文件、脚本、已有 workflows、迁移工具等。
4. 生成或更新 `.cicd/project.yaml`（自动识别摘要）。
5. 若目标仓已有 CI/CD，**会先停下问你**是否覆盖。
6. 从 `.cursor/skills/CI_CD/templates/` 渲染并写入目标仓文件。
7. 列出仍需配置的 GitHub Secrets、Variables、AWS 密钥存放位置。
8. **在你同意前**不擅自 commit / push / 开 PR。
9. 配置齐全后可跑 `ci.yml` → `release.yml` → `deploy-aws.yml`。

---

## 3. 整体流程（逐步详解）

### 阶段 A：在目标仓库里「安装」CI/CD 文件

由 Skill 执行（或你按模板手工对齐），目标应用仓库最终应出现：

```text
.github/workflows/
  ci.yml              # 持续集成
  release.yml         # 构建镜像 + 推 ECR + 产物 metadata
  deploy-aws.yml      # 部署 + 验证 + 失败回滚（应用层）

.cicd/
  project.yaml        # 自动识别结果（通常不要手改）
  env/
    dev.yaml.example
    staging.yaml.example
    prod.yaml.example
  secrets/README.md   # 敏感信息边界说明
  runbooks/rollback.md
```

你需要把对应环境的示例复制成真实环境文件（示例）：

```bash
cp .cicd/env/prod.yaml.example .cicd/env/prod.yaml
```

然后编辑 `.cicd/env/prod.yaml`，填入 AWS 账号、区域、ECS 集群名、服务名、ECR 仓库名等（见第 5 节）。**不要把数据库密码写进该文件**。

### 阶段 B：CI — `ci.yml`

**触发**：Pull Request、推送到 `main`/`master`、`workflow_dispatch`。

**做什么**：

1. 读取 `.cicd/project.yaml`。
2. 找出 `services` 里 `enabled: true` 的服务，生成矩阵。
3. 对每个服务依次执行（若配置了且不是 `TODO`）：`install` → `lint` → `typecheck` → `test` → `build`。
4. 某一步未配置：该步 **skipped**，并在 GitHub Step Summary 写明原因。
5. **没有任何 enabled 服务**：整个 workflow **失败**（避免「空配置假装通过」）。

**你要做什么**：保证 `.cicd/project.yaml` 里各服务的 `path`、`commands`、Dockerfile 等与真实仓库一致；Skill 安装后会尽量自动填，你可能只需微调。

### 阶段 C：Release — `release.yml`

**触发**：仅 `workflow_dispatch`（手动），并选择：

- `environment`：`dev` / `staging` / `prod`
- `service_scope`：`all` 或 `*-only`
- `release_id`：可选，默认用当前 commit SHA

**做什么**：

1. 使用 GitHub OIDC 扮演 AWS 角色：`secrets.AWS_RELEASE_ROLE_ARN`。
2. 区域：`vars.AWS_REGION` 或默认 `us-east-1`。
3. 登录 ECR。
4. 读取 `.cicd/project.yaml` + `.cicd/env/<environment>.yaml`（若无则尝试 `.yaml.example`）。
5. 校验 `aws.account_id` 已填且非 `TODO`。
6. 按 `service_scope` 选择要构建的服务，对每个服务：
   - `docker build`（dockerfile、build_context 来自 `project.yaml`）
   - `docker push` 到对应 ECR 仓库（仓库名来自 env 文件或 GitHub Variables）
   - 用 AWS CLI 查出该 tag 对应的 **image digest**
7. 写入 **`promotion-metadata.json`**（包含 release_id、环境、各服务镜像 URI、digest、提交信息等）。
8. 把 `promotion-metadata.json` 作为 **artifact** 上传。

**你要做什么**：

- GitHub 仓库里配置好 Secret：`AWS_RELEASE_ROLE_ARN`。
- GitHub Environment（dev/staging/prod）与 IAM OIDC 信任关系正确。
- `.cicd/env/<env>.yaml` 里 `ecr.*_repository` 或 Variables `ECR_REPOSITORY_*` 已填。
- ECR 仓库在 AWS 侧已存在且 IAM 权限允许 push/describe-images。

### 阶段 D：Deploy — `deploy-aws.yml`

**触发**：`workflow_dispatch`，需要传入：

- `environment`
- `service_scope`
- `deployment_target`：`ecs` 或 `ec2-ssh`
- `deployment_mode`：`single-node` 或 `distributed`
- `release_id`：**必须与** `promotion-metadata.json` 里的一致
- `promotion_run_id`：**release 那次 workflow 的 run id**，用于下载同名 artifact

**Preflight**：

- 读取 `.cicd/env/<env>.yaml`（或 example）。
- 若 `distributed` + `ec2-ssh`，校验至少两个可用 host。

**ECS 路径**（`deployment_target == ecs`）：

1. `gh run download` 下载 `promotion-metadata.json`。
2. OIDC 登录 AWS。
3. 校验 metadata 的 `release_id` 与输入一致。
4. 读取 `ecs.cluster_name`、`desired_count`（按 single-node / distributed 取值）。
5. **distributed** 时若 `desired_count < 2` 会直接失败。
6. 对每个选中服务：
   - `describe-services` 取当前 task definition → 作为 **rollback 基线**
   - `describe-task-definition` 取完整定义，仅替换匹配 `container_name` 的 `image` 为 **digest URI**
   - `register-task-definition` → `update-service`（含 desired count）→ `wait services-stable`
   - 若配置了 `target_group_arn`，检查 ALB target 是否全部为 `healthy`
7. 对 frontend/backend 做 HTTP 健康检查（URL + path 来自 env 与 project）。
8. 任一步失败：**把 service 滚回 previous task definition**，写 `deployment-evidence.json` / `rollback-evidence.json`。

**EC2 SSH 路径**（`deployment_target == ec2-ssh`）：

1. 同样需要 promotion metadata。
2. `secrets.AWS_EC2_SSH_PRIVATE_KEY` 写入临时 key。
3. 按 `single-node` 或 `distributed` 解析主机列表；distributed 至少两台。
4. 每台机：ECR login → `docker pull` digest → 记录旧镜像 → `docker run` 新容器。
5. 健康检查：可用配置的 URL，否则按 `http://<host>:<port>/<path>` 探测。
6. 失败则尝试 **恢复上一镜像** 或移除新容器。

**你要做什么**：

- 确认 ECS 集群、服务、task 定义里的 container 名与 `.cicd/env/*.yaml` 一致。
- ALB / Target Group 已在 AWS 配好且与 ECS service 关联。
- 健康检查 URL 对 GitHub Runner 可达（公网或恰当网络）。

---

## 4. 数据库怎么处理（重点）

### 4.1 Skill / 模板对数据库的定位

- **数据库实例**（如 RDS、Aurora）通常在 AWS 控制台或 Terraform/CDK 中创建；本 Skill **不负责**替你开通 RDS。
- **Schema 与数据变更**属于应用责任：通过迁移工具（Prisma Migrate、Flyway、Liquibase、Alembic、Django migrations 等）在仓库里维护脚本。
- Skill 会在 `.cicd/project.yaml` 的 `database` 区块记录：

  - `migration_tool`
  - `migration_command`
  - `migration_required_before_deploy`（是否建议在部署前必须先迁移）

当前 **`release.yml` / `deploy-aws.yml` 模板里没有内置「自动执行 migrate」步骤**。也就是说：

- **默认行为**：部署的是**新镜像**；你是否在容器启动时执行迁移、或用单独 Job 执行，需要你在目标仓库里**明确设计**（例如在 ECS task 启动命令、`entrypoint.sh`、或扩展 workflow 增加 migrate job）。
- **初始数据 / SQL dump**：不属于标准模板范围；若需要，应单独设计一次性 Job（如运维脚本、AWS Batch、或受控的 GitHub Action），并做好备份与审计。

### 4.2 推荐流水线顺序（与 `docs/cicd/database-migrations.md` 一致）

对有数据库的后端，推荐顺序：

1. **预检**：连通性、凭证有效、迁移锁、备份是否新鲜。
2. **dry-run / plan**：如 `flyway validate`、`prisma migrate diff`、`alembic check`（按栈选择）。
3. **执行迁移**（在「兼容旧代码」的窗口内，或 Expand 阶段只加新列/新表）。
4. **校验**：schema 版本、关键读写 smoke。
5. **部署新版本应用**（可同时扩容再切换流量）。

若迁移失败：**停止部署**，不要假定「回滚容器」等于「回滚数据库」。

### 4.3 Expand → Migrate → Contract

1. **Expand**：先加向后兼容的变更（新列可空、新表、双写等）。
2. **Migrate**：上线能同时读写新旧结构的代码，必要时回填数据。
3. **Contract**：验证稳定后再删旧列/旧表。

### 4.4 为什么不能指望自动回滚数据库

应用回滚（ECS 回到旧 task definition、EC2 回到旧镜像）**只能恢复旧代码**，不能撤销已在库里执行的破坏性 SQL。因此：

- **破坏性迁移**必须人工审批与演练。
- 文档明确：**destructive migration** 属于人工介入场景，不在自动 rollback 保障范围内。

### 4.5 「上传数据库」你到底该怎么做？

按场景拆开：

| 场景 | 说明 |
|------|------|
| 仅 Schema | 用迁移工具提交到 Git；在运维窗口执行 migrate（自建 workflow 或启动脚本）。 |
| 种子数据 / 演示数据 | 用迁移 seed、或受控的初始化 Job；勿把生产 dump 提交到 Git。 |
| 从本地迁到 RDS | 通常：**导出**（`pg_dump` / `mysqldump`）→ 上传到 S3 管控 bucket → 在 VPC 内恢复或 DMS；不走「skill 自动上传」。 |
| 多环境 | dev/staging/prod 使用不同连接串（Secrets Manager），同一套迁移脚本，不同执行时机与权限。 |

连接串示例存放：**AWS Secrets Manager** 或 **SSM Parameter Store**（加密）；ECS task 通过 task execution role 读取；`.cicd/env/prod.yaml` 只写 **secret 名字或 ARN**，不写明文。

---

## 5. 敏感信息怎么填（边界非常清楚）

### 5.1 绝对规则

- **永远不要**把真实 secret 提交到 `.cicd/*.yaml`、README 或任何可被 clone 的文件。
- 仓库里只允许：**变量名、Secret 名、ARN、占位说明**。

### 5.2 GitHub Secrets（当前模板硬编码使用的）

| Secret | 用途 |
|--------|------|
| `AWS_RELEASE_ROLE_ARN` | OIDC 假设扮演的 IAM Role ARN，`release.yml` 与 `deploy-aws.yml` 都用 |
| `AWS_EC2_SSH_PRIVATE_KEY` | 仅 `ec2-ssh` 部署时需要；完整私钥内容放在 GitHub Secret |

在 GitHub：**Repo Settings → Secrets and variables → Actions**，并为 `dev`/`staging`/`prod` 配置 **Environments**（可选保护规则、审批人）。

### 5.3 GitHub Variables（可选补充）

模板中会读取：

- `AWS_REGION`
- `ECR_REPOSITORY_FRONTEND`
- `ECR_REPOSITORY_BACKEND`
- `ECR_REPOSITORY_WORKER`

若你在 `.cicd/env/<env>.yaml` 的 `ecr` 段已写满仓库名，可与 Variables 二选一或互补（以 `release.yml` 逻辑为准：优先 env 文件里的 `ecr.*_repository`，否则用环境变量 `ECR_REPOSITORY_*`）。

### 5.4 AWS 侧 Secret Store

适用于：

- 数据库用户名密码、连接 URL
- JWT、OAuth、第三方 API Key
- 任意运行时配置

存放位置：**Secrets Manager** 或 **SSM Parameter Store（SecureString）**。

在 `.cicd/env/prod.yaml` 的 `runtime_secrets.names` 里列出 **逻辑名称或 ARN**，便于运维对照；**真实值只在 AWS 控制台或 IaC 中创建**。

### 5.5 `.cicd/secrets/README.md` 的作用

安装到目标仓后，它是给团队的 **清单**：哪些 Secret 必须在 GitHub 建、哪些必须在 AWS 建；不包含真实值。

---

## 6. 单台（single-node）与分布式（distributed）

### 6.1 single-node

- **ECS**：`desired_count` 取 env 文件中 `ecs.desired_count.single_node`，模板默认为 **1**。
- **EC2**：只使用 `ec2.single_node.host` 一台机器。
- **适用**：开发、小型 staging、内部工具、不需要高可用的服务。
- **注意**：Skill 明确：**不能把 single-node 说成高可用**；宕机即中断。

### 6.2 distributed

- **ECS**：使用 `ecs.desired_count.distributed`，模板默认为 **2**；`deploy-aws.yml` 若检测到 `< 2` 会直接报错退出。
- **EC2**：`ec2.distributed.hosts` 至少 **2 台**可用主机（非 `TODO`）；preflight 会校验。
- **适用**：生产或对可用性有要求的 staging。
- **建议**：生产配置 **Auto Scaling**、多 AZ、容量策略；模板里 `autoscaling` 块多为占位，需在 AWS 控制台或 IaC 里落实。

### 6.3 与 `deployment_target` 的组合

| deployment_target | single-node | distributed |
|-------------------|-------------|-------------|
| ecs | 1 个 ECS task（Per service 更新逻辑仍以 service 为单位） | ≥2 tasks，跨 AZ 由集群/子网决定 |
| ec2-ssh | SSH 一台 host | SSH 多台 host，每台 pull + run |

---

## 7. 每个文件做什么（安装后的路径 = 目标应用仓库内）

### 7.1 `.github/workflows/ci.yml`

- 解析 `.cicd/project.yaml`，矩阵跑各服务命令。
- 安装 `pyyaml` 后执行内嵌 Python 脚本。
- 无 enabled services → **失败**。

### 7.2 `.github/workflows/release.yml`

- OIDC + ECR login。
- 构建、推送镜像；写入 **digest** 到 `promotion-metadata.json`。
- 上传 artifact **`promotion-metadata`**。

### 7.3 `.github/workflows/deploy-aws.yml`

- 下载指定 run id 的 artifact。
- ECS：改 task definition 镜像 → update service → ALB 健康检查 → HTTP 检查 → 失败回滚 task definition。
- EC2：SSH → docker pull/run → HTTP 检查 → 失败回滚镜像。
- 上传 `deployment-evidence.json` / `rollback-evidence.json`（若生成）。

### 7.4 `.cicd/project.yaml`

- Skill **自动生成/维护**的项目画像：仓库信息、布局、各服务路径、Dockerfile、命令、健康路径、`database` 迁移线索等。
- **日常尽量不要手改**；改代码结构后可以让 Skill 重新识别或局部更新。

### 7.5 `.cicd/env/dev.yaml.example` / `staging` / `prod`

- **人类主要编辑**的是复制后的 `.cicd/env/<env>.yaml`（无 `.example`）。
- 内容包含：`aws.account_id`、`region`、ECR、ECS 集群与服务、网络 ID、健康检查 URL、EC2 主机列表、`runtime_secrets` 名称列表等。
- **prod** 示例默认 `distributed` + 发布需审批（`release.require_manual_approval: true`）；**dev** 默认 `single-node` 且不要求审批。

### 7.6 `.cicd/secrets/README.md`

- 团队 onboarding：Secret 放哪里、命名约定、禁止提交明文。

### 7.7 `.cicd/runbooks/rollback.md`

- 人工操作指南：何时滚、ECS/EC2 命令示例、证据文件含义、何时必须停手升级事件。

### 7.8 本仓库 `SKILL.md` 与 `templates/`

- **SKILL.md**：Agent 行为契约（何时用、输入、禁止写真实 secret、执行顺序）。
- **templates/**：安装到目标仓的「源文件」，不应在生产应用里直接引用路径，仅作生成来源。

---

## 8. 实际怎么用（从零到第一次上线）

### 8.1 上线前你在 AWS 要提前有的东西

- IAM OIDC 信任 GitHub 的 Role，且权限包含：ECR push/pull、ECS Describe/Register/Update、ELB DescribeTargetHealth（按实际最小权限收紧）。
- ECR 仓库（frontend/backend/worker 按需）。
- ECS 集群 + Fargate service（或 EC2 + Docker）。
- 任务定义里容器名与 `.cicd/env/*.yaml` 中 `container_name` 一致。
- ALB + Target Group（若走 ECS 默认验证路径）。
- RDS 或自建数据库（若有）：安全组允许 ECS task 访问；Secret 存连接信息。

### 8.2 在 GitHub 配置

1. 创建 Environments：`dev`、`staging`、`prod`（按需加审批）。
2. 在 Repository secrets 或 Environment secrets 中设置：
   - `AWS_RELEASE_ROLE_ARN`
   - 若用 EC2：`AWS_EC2_SSH_PRIVATE_KEY`
3. 设置 Variables：`AWS_REGION`、`ECR_REPOSITORY_*`（若 env 文件未写全）。

### 8.3 在目标应用仓库

1. 用 Skill 安装文件（或合并 PR）到默认分支。
2. `cp .cicd/env/prod.yaml.example .cicd/env/prod.yaml`，填写所有非 TODO。
3. 在 AWS Secrets Manager 创建数据库等 secret；记下名称填入 `runtime_secrets.names`。
4. 确保 ECS task definition 已引用这些 secret（通过 `secrets` 字段或环境变量注入），这是 **AWS 控制台/Terraform** 的责任。

### 8.4 第一次发布与部署

1. 推送代码后观察 **CI** 是否绿。
2. Actions 里手动运行 **release**，选 `environment`（如 `staging`）、`service_scope`。
3. 记录本次 **release workflow 的 Run ID**（用于 deploy）。
4. 打开 **deploy-aws**，填入：
   - 同一 `environment`、`service_scope`
   - `deployment_target`: `ecs`（或 `ec2-ssh`）
   - `deployment_mode`: `single-node` 或 `distributed`
   - `release_id`: 与 `promotion-metadata.json` 内一致（默认常为本次 commit SHA）
   - `promotion_run_id`: 第 3 步的 Run ID
5. 完成后在 artifact 或日志中查看 `deployment-evidence.json`；失败时查看 `rollback-evidence.json`。

### 8.5 数据库迁移怎么接进流水线（你需要额外做的一步）

模板未内置 migrate job，常见三种接法（择一或与团队规范对齐）：

1. **容器启动时**：仅适合能快速失败、可幂等、且有锁的迁移；需谨慎避免并行 task 重复 migrate。
2. **单独 ECS RunTask / GitHub Action job**：在 `update-service` 前执行一次 migrate，失败则中断 deploy。
3. **人工窗口**：发布窗口先执行 migrate，再触发 deploy。

无论哪种，**破坏性变更**必须走变更审批与备份验证。

---

## 9. 常见问题（FAQ）

**Q：Skill 怎么识别我本地环境？**  
A：识别的是 **克隆下来的目标 GitHub 仓库内容**（文件结构、Dockerfile、配置），不是你本机全局 Python/Node 版本。CI 在 GitHub Runner 上跑；Runner 版本由 workflow 里的 `setup-*` 决定。

**Q：我能跳过 CI 直接部署吗？**  
A：技术上可以手动只跑 release/deploy，但不推荐；CI 是防止坏镜像进 ECR 的第一道门。

**Q：回滚会自动恢复数据库吗？**  
A：**不会**。自动回滚主要针对 **ECS task 定义 / EC2 容器镜像**。

**Q：为什么不默认自动 migrate？**  
A：迁移与数据风险强相关，不同栈命令、锁、并行策略差异大，错误 migrate 会造成跨环境灾难；因此模板选择「检测 + 文档 + 由你在目标仓显式接入」。

---

## 10. 延伸阅读（本仓库内）

- `.cursor/skills/CI_CD/SKILL.md` — Skill 机器可读契约  
- `docs/cicd/README.md` — 英文总览  
- `docs/cicd/database-migrations.md` — 迁移专题  
- `AWS-CICD-SKILL-OPTIMIZATION-OPERATIONS.md` — 维护与收口说明（给改造 Skill 的人看）

---

*文档生成说明：本文基于当前仓库内的 `SKILL.md`、`.cursor/skills/CI_CD/templates/` 与 `docs/cicd/` 内容整理；若你后续改了 workflow 模板，请以仓库内实际 YAML 为准。*

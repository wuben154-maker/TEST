# AWS CI/CD Skill Optimization Operations

## 目标

把当前 `CI_CD` 项目收敛成一个精简、可操作、可自动识别目标项目环境的 AWS CI/CD Skill 工具仓。

最终效果：

- 只保留一个 CI/CD 入口：`.cursor/skills/CI_CD/SKILL.md`。
- 不保留历史 CI/CD skill、旧 workflow、旧 `.cicd` 示例资料。
- 从 GitHub 仓库 URL 启动，不要求用户先手动下载项目。
- Skill 先自动识别目标项目环境，再生成 CI/CD 文件。
- 可自动推断的内容不要求用户填写。
- 只有敏感信息和无法从项目安全推断的云资源标识需要用户填写。
- 需要填写的内容集中在目标仓的一个配置目录中，便于操作。
- 支持 AWS 美国区部署，默认 ECS/Fargate，保留 EC2 SSH 作为可选路径。
- 支持 `single-node` 和 `distributed` 两种模式。
- 生成的 GitHub Actions 必须能执行真实 CI、release、AWS deploy、verify、rollback，不停留在 `echo` 占位。

## 当前关键判断

当前项目已经有正确方向：

```text
.cursor/skills/CI_CD/SKILL.md
```

但仍需要完成收口：

- 旧 CI/CD skill 已处于删除态或仍可能残留，不需要保留。
- 旧 `.github/workflows/*` 和旧 `.cicd/*` 不应继续作为本项目运行模型。
- `docs/cicd/` 文档存在重复，可以压缩。
- `aws-cicd` 模板结构还可以更利于填写。
- `deploy-aws.yml` 当前需要从说明型模板升级为真实部署模板。

## 最终项目结构

`CI_CD` 仓库建议保留以下 CI/CD 相关结构：

```text
.cursor/
  skills/
    CI_CD/
      SKILL.md
      templates/
        github-workflows/
          ci.yml
          release.yml
          deploy-aws.yml
        cicd-config/
          project.yaml
          env/
            dev.yaml.example
            staging.yaml.example
            prod.yaml.example
          secrets/
            README.md
          runbooks/
            rollback.md

docs/
  cicd/
    README.md
    database-migrations.md

AWS-CICD-SKILL-OPTIMIZATION-OPERATIONS.md
```

说明：

- `SKILL.md` 是唯一执行入口。
- `templates/github-workflows/` 存放安装到目标仓的 GitHub Actions。
- `templates/cicd-config/project.yaml` 是自动识别结果模板，尽量由 skill 填写。
- `templates/cicd-config/env/*.yaml.example` 是用户需要确认和填写的环境配置。
- `templates/cicd-config/secrets/README.md` 只说明敏感信息放在哪里，不存真实 secret。
- `docs/cicd/README.md` 是主说明文档。
- `docs/cicd/database-migrations.md` 可保留为数据库迁移专题。


## 目标仓安装结构

`aws-cicd` skill 运行后，应把以下结构安装进目标 GitHub 项目：

```text
.github/
  workflows/
    ci.yml
    release.yml
    deploy-aws.yml

.cicd/
  project.yaml
  env/
    dev.yaml
    staging.yaml
    prod.yaml
  secrets/
    README.md
  runbooks/
    rollback.md
```

如果用户还没有填写配置，先安装 example 文件：

```text
.cicd/
  env/
    dev.yaml.example
    staging.yaml.example
    prod.yaml.example
```

用户复制需要的环境文件：

```text
cp .cicd/env/prod.yaml.example .cicd/env/prod.yaml
```

真实 secret 不写入这些文件。

## 自动识别规则

Skill 必须先读取目标 GitHub 项目，再决定需要什么配置。

必须自动识别：

- GitHub owner、repo、default branch、remote URL。
- 项目类型：单应用、前后端分离、monorepo、worker。
- 服务角色：`frontend`、`backend`、`worker`、`shared`。
- 包管理器：npm、pnpm、yarn、bun、pip、poetry、gradle、maven、go 等。
- 运行命令：install、lint、typecheck、test、build、start。
- Dockerfile 和 build context。
- Docker Compose 文件。
- 端口：Docker `EXPOSE`、`.env.example`、框架默认端口。
- 健康检查：Docker healthcheck、`/health`、`/api/health`、`/`。
- 数据库迁移工具：Prisma、Drizzle、Flyway、Liquibase、Django migrations、Alembic 等。
- 已存在的 `.github/workflows`、`.cicd`、README 部署说明。

自动识别结果写入：

```text
.cicd/project.yaml
```

`project.yaml` 应是机器生成和维护的文件，用户通常不需要手动填写。

## 手动配置边界

只允许要求用户填写以下内容：

- AWS account ID。
- AWS region，默认 `us-east-1`。
- GitHub OIDC role ARN secret name。
- ECR repository name。
- ECS cluster name。
- ECS service name。
- ECS task family。
- ECS execution role ARN。
- ECS task role ARN。
- VPC、subnets、security groups。
- ALB 和 target groups。
- EC2 hosts、SSH user、SSH private key secret name。
- 域名、证书引用。
- 生产运行时 secret 名称。
- 数据库连接 secret 名称。

这些信息集中放到：

```text
.cicd/env/<environment>.yaml
.cicd/secrets/README.md
```

不要再拆出单独的 `.cicd/aws/ecs.yaml` 和 `.cicd/aws/ec2.yaml`，除非后续确实出现跨环境复用复杂度。

## 环境配置文件设计

每个环境文件包含完整的该环境部署信息。

示例结构：

```yaml
environment: prod
aws:
  account_id: TODO_REQUIRED
  region: us-east-1
  oidc_role_arn_secret: AWS_RELEASE_ROLE_ARN

deployment:
  target: ecs
  mode: distributed
  service_scope: all

release:
  require_manual_approval: true
  allow_rollback: true
  freeze_window_policy: TODO_OPTIONAL

health:
  frontend_url: TODO_REQUIRED_IF_FRONTEND
  backend_url: TODO_REQUIRED_IF_BACKEND
  frontend_path: TODO_AUTO_DETECTED
  backend_path: TODO_AUTO_DETECTED
  timeout_seconds: 10
  retries: 12

ecr:
  frontend_repository: TODO_REQUIRED_IF_FRONTEND
  backend_repository: TODO_REQUIRED_IF_BACKEND
  worker_repository: TODO_REQUIRED_IF_WORKER

ecs:
  cluster_name: TODO_REQUIRED_IF_ECS
  desired_count:
    single_node: 1
    distributed: 2
  autoscaling:
    enabled: TODO_CONFIRM_FOR_PROD
    min_capacity: 2
    max_capacity: TODO_REQUIRED_IF_AUTOSCALING
    cpu_target_percent: 60
    memory_target_percent: 70
  services:
    frontend:
      service_name: TODO_REQUIRED_IF_FRONTEND
      task_family: TODO_REQUIRED_IF_FRONTEND
      execution_role_arn: TODO_REQUIRED_IF_FRONTEND
      task_role_arn: TODO_REQUIRED_IF_FRONTEND
      container_name: TODO_AUTO_DETECTED
      target_group_arn: TODO_REQUIRED_IF_FRONTEND
    backend:
      service_name: TODO_REQUIRED_IF_BACKEND
      task_family: TODO_REQUIRED_IF_BACKEND
      execution_role_arn: TODO_REQUIRED_IF_BACKEND
      task_role_arn: TODO_REQUIRED_IF_BACKEND
      container_name: TODO_AUTO_DETECTED
      target_group_arn: TODO_REQUIRED_IF_BACKEND

network:
  vpc_id: TODO_REQUIRED_IF_ECS
  subnet_ids:
    - TODO_REQUIRED_IF_ECS
  security_group_ids:
    - TODO_REQUIRED_IF_ECS

ec2:
  ssh_user: ec2-user
  ssh_private_key_secret: AWS_EC2_SSH_PRIVATE_KEY
  single_node:
    host: TODO_REQUIRED_IF_EC2_SINGLE_NODE
  distributed:
    hosts:
      - host: TODO_REQUIRED_IF_EC2_DISTRIBUTED
        role: all
      - host: TODO_REQUIRED_IF_EC2_DISTRIBUTED
        role: all

runtime_secrets:
  env_source: github_environment_or_aws_secrets_manager
  names:
    - TODO_SECRET_NAME_ONLY
```

## 敏感信息目录

在模板中新增：

```text
.cursor/skills/CI_CD/templates/cicd-config/secrets/README.md
```

内容说明：

- 真实 secret 不提交到仓库。
- GitHub Actions 使用 GitHub Secrets 和 GitHub Variables。
- 应用运行时 secret 使用 AWS Secrets Manager 或 SSM Parameter Store。
- `.cicd/env/*.yaml` 只能保存 secret 名称、ARN 引用、变量名，不能保存真实值。

目标仓 `.cicd/secrets/README.md` 应列出用户需要创建的 secret：

```text
GitHub Secrets:
- AWS_RELEASE_ROLE_ARN
- AWS_EC2_SSH_PRIVATE_KEY, only for ec2-ssh

GitHub Variables:
- AWS_REGION
- ECR_REPOSITORY_FRONTEND
- ECR_REPOSITORY_BACKEND
- ECR_REPOSITORY_WORKER

AWS Secrets Manager or SSM:
- app runtime secrets
- database credentials
- third-party API keys
```

## SKILL.md 改写要求

`.cursor/skills/CI_CD/SKILL.md` 保持短，但必须更明确。

建议章节：

```text
# AWS CI/CD

## Purpose
## When To Use
## Inputs
## Non-Negotiable Rules
## Execution Flow
## Auto-Detection Contract
## Generated Target Files
## Manual Configuration Boundary
## Deployment Modes
## AWS Targets
## Verification And Rollback
## Stop Conditions
## Output Report
```

关键规则必须写入：

- `github_repo_url` 是起点。
- 先自动识别，再询问用户。
- 不保存真实 secret。
- 不保留旧 CI/CD skill。
- 默认 ECS/Fargate。
- `single-node` 不能伪装成高可用。
- `distributed` 必须有 ECS desired count `>=2` 或 EC2 至少两个 host。
- 构建一次，部署 immutable digest。
- deploy 成功不等于上线成功，verify 才是最终门。
- verify 失败必须 rollback 或阻塞曝光。

## GitHub 项目拉取策略

Skill 不应要求用户手动下载目标项目。

推荐优先级：

1. 使用 `gh` 读取目标 GitHub 仓库元数据。
2. 使用临时目录 clone 目标仓进行检测。
3. 在目标仓创建 setup branch。
4. 写入 `.github/workflows/*` 和 `.cicd/*`。
5. 仅在用户明确同意后 commit、push、open PR。

如果后续要做到更少本地依赖，可以升级为：

1. 使用 GitHub API 读取 tree 和 file contents。
2. 本地只生成 patch。
3. 通过 GitHub API 创建 branch 和 commit。

但第一阶段可以接受临时 clone，因为 CI/CD 执行发生在 GitHub Actions，不在本地跑部署。

## Workflow 实现要求

### `ci.yml`

必须做到：

- 读取 `.cicd/project.yaml`。
- 按服务启用状态运行对应 job。
- 自动选择包管理器和命令。
- 跑 lint、typecheck、test、build。
- 没有某类命令时跳过，但要输出 skipped reason。
- 不能因为命令缺失而伪装成功；必须在 summary 中写明。

注意：

- 如果 workflow 用 Python 解析 YAML，必须安装 `pyyaml`。
- 或改用 Node 脚本解析 YAML，并安装 `js-yaml`。

### `release.yml`

必须做到：

- 读取 `.cicd/project.yaml` 和 `.cicd/env/<env>.yaml`。
- 登录 AWS OIDC。
- 登录 ECR。
- 按 service scope 构建镜像。
- 推送 ECR。
- 获取 image digest。
- 生成 `promotion-metadata.json`。
- 上传 artifact。

镜像部署必须使用 digest，而不是只用 mutable tag。

### `deploy-aws.yml`

必须做到真实部署，不允许只 `echo`。

ECS 路径：

1. 下载 `promotion-metadata.json`。
2. 读取 `.cicd/env/<env>.yaml`。
3. 获取当前 ECS service 的 task definition，保存为 rollback baseline。
4. 基于当前 task definition 注册新 revision。
5. 把 container image 更新为 ECR digest。
6. 更新 ECS service。
7. 等待 service stable。
8. 检查 ALB target health。
9. 运行 HTTP health check。
10. 写入 `deployment-evidence.json`。
11. 失败时恢复旧 task definition。
12. 写入 `rollback-evidence.json`。

EC2 SSH 路径：

1. 下载 `promotion-metadata.json`。
2. 读取 `.cicd/env/<env>.yaml`。
3. 按 `single-node` 或 `distributed` 选 host。
4. SSH 到每台 host。
5. 登录 ECR。
6. 拉取 digest 镜像。
7. 保存当前运行 image digest 作为 rollback baseline。
8. 重启容器。
9. 逐 host health check。
10. 失败时恢复旧 digest。
11. 写入 deployment 和 rollback evidence。

### `rollback`

Rollback 不应只是 runbook，workflow 必须能自动回滚常见失败。

自动回滚范围：

- ECS service 更新后 verify 失败。
- EC2 container 重启后 verify 失败。
- ALB target health 不达标。
- HTTP health check 不通过。

人工介入范围：

- 数据库 destructive migration。
- AWS 权限缺失。
- secret 缺失。
- 网络基础设施配置错误。

## 文档压缩要求

`docs/cicd/README.md` 合并以下内容：

- 项目目标。
- 单 skill 入口。
- 目标仓安装结构。
- 自动识别字段。
- 手动配置字段。
- secret 边界。
- ECS/EC2 部署模型。
- `single-node` / `distributed` 差异。
- workflow 执行顺序。
- rollback 策略。
- 已知限制。

保留：

```text
docs/cicd/database-migrations.md
```

因为数据库迁移风险独立，适合单独说明。

## 验收标准

完成优化后，应满足：

- `.cursor/skills/` 下只有一个 CI/CD 相关 skill：`aws-cicd`。
- 根目录没有旧 CI/CD 说明文档。
- 本项目没有旧 `.github/workflows/*` CI/CD 示例。
- 本项目没有旧 `.cicd/` 示例目录。
- `docs/cicd/README.md` 是唯一主说明。
- `docs/cicd/database-migrations.md` 是唯一专题说明。
- `aws-cicd` skill 明确要求从 `github_repo_url` 启动。
- `aws-cicd` skill 明确要求先自动识别目标仓。
- 目标仓只需要填写 `.cicd/env/<env>.yaml` 和 secret store。
- 真实 secret 不进入 git。
- `deploy-aws.yml` 有真实 ECS 部署逻辑。
- `deploy-aws.yml` 有真实 EC2 SSH 部署逻辑，或明确 EC2 为第二阶段并在 skill 中标记 blocked。
- `single-node` 和 `distributed` 在配置、部署、验证中都有实际差异。
- workflow 不依赖未安装的 YAML 解析库。
- 失败路径能输出 deployment evidence 和 rollback evidence。
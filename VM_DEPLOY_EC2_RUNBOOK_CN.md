# SecManus（`dev-chenry-binary`）EC2 单机部署实录

面向仓库：[https://github.com/SecManus/secmanus-workspace/tree/dev-chenry-binary](https://github.com/SecManus/secmanus-workspace/tree/dev-chenry-binary)

本记录与 `.cursor/skills/CI_CD/SKILL.md` 的关系：

- **CI_CD skill 默认路径**是 GitHub Actions → ECR 镜像摘要 → ECS 或 **`ec2-ssh`（同样需要 GitHub Secret、metadata artifact）**。本次需求是「用 SSH 密钥把代码弄到指定 Ubuntu、本机 Compose 跑通」，属于 **单机自托管**，与流水线 **目标一致（不可变镜像/健康检查思路）**，但交付形态是 **手工/运维脚本**，不是自动跑 `deploy-aws.yml`。
- Skill 强调的边界仍然成立：**不要在仓库提交真实密钥**；LLM Key、Stripe 等与凭据相关内容通过环境变量或后续 GitHub/OS Secret 注入。

---

## 1. 环境与目标

| 项 | 值 |
|----|-----|
| 主机 | Ubuntu（EC2，`us-east-2`），用户 `ubuntu` |
| IP | `https://github.com/` 不适用；访问入口为：`http://18.216.190.63/`（前端）、`http://18.216.190.63:8000/`（API） |
| SSH | `ssh -i D:\code\cursor\env\secmanus.pem ubuntu@18.216.190.63` |

**若公网打不开页面**：在安全组中为该实例放行 **TCP 80**（前端）以及 **TCP 8000**（API，若浏览器需直连后端）。仅从你自己电脑 `curl`/浏览器访问时需配置；已通过 SSH 在实例本机验证 Nginx 与 `/health`。

---

## 2. 代码如何上机器（私有仓库）

在 EC2 上直接 `git clone https://github.com/SecManus/...` 会因 **匿名拉取被拒**失败。

**可行做法**：在已能访问 GitHub 的开发机上打包分支再 SCP：

```powershell
cd d:\path\to\secmanus-workspace
git fetch origin dev-chenry-binary
git archive --format=tar origin/dev-chenry-binary -o $env:TEMP\secmanus.tar
scp -i D:\code\cursor\env\secmanus.pem $env:TEMP\secmanus.tar ubuntu@18.216.190.63:/tmp/secmanus.tar
```

实例上解压：

```bash
rm -rf ~/secmanus-workspace && mkdir -p ~/secmanus-workspace
tar -xf /tmp/secmanus.tar -C ~/secmanus-workspace
```

---

## 3. 后端与容器编排

### 3.1 为何没有用仓库里的 `docker-compose.local.yml` 一整套

仓库中 `docker-compose.local.yml` 依赖 **`ghcr.io/devflowinc/firecrawl-simple:latest`**。在当前环境拉取时返回 **`denied`**（匿名拉取受限或需登录），导致 `docker compose up` 整体失败。

**对策**：使用仅包含 **PostgreSQL + deep-agent** 的编排文件 `python-agent-service/docker-compose.vm.yml`（已通过 SCP 传到服务器同路径；也可随本仓库运维文件维护）。其中：

- 去掉本地 Firecrawl 容器；
- **`FIRECRAWL_API_URL` / `FIRECRAWL_API_KEY` 置空**：应用内会按 `app/config/settings.py` 的 **firecrawl_url** 回落逻辑处理（爬虫类能力可能指向云端或其它地址；上线 Firecrawl 需自行解决镜像拉取或登录 GHCR）。
- Postgres 映射为 **`127.0.0.1:5432:5432`**，避免数据库端口对整个公网暴露。

### 3.2 Dockerfile 与端口（必须已知）

镜像内 `Dockerfile` 默认 **`PORT` 未设置时监听 9090**，而 Compose 写的是 **`8000:8000`**。因此在 VM 编排里显式加入：

```yaml
- PORT=8000
```

否则会端口不一致、健康检查失败。

启动命令（在 `~/secmanus-workspace/python-agent-service`）：

```bash
docker compose -f docker-compose.vm.yml up -d --build
curl -sf http://127.0.0.1:8000/health
```

预期 JSON 中包含 `"status":"healthy"`、`"database_mode":"local"`。

### 3.3 环境变量与 AI 密钥

至少需要为 **某一种** LLM 配置真实 Key（如 `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`），`/analyze` 才会正常工作；`/health` 可在无 Key 时已返回 healthy。

不要将 Key 写入 Git；实例上可使用：

```bash
export GOOGLE_API_KEY=...   # 或其它提供商
docker compose -f docker-compose.vm.yml up -d
```

或在本目录创建 `.env`，由 Compose 读取（同样勿提交）。

---

## 4. 数据库与迁移说明（本次部署核心）

本项目存在 **两套数据定义来源**，语义不同：

| 来源 | 路径 | 用途 |
|------|------|------|
| **云端 Supabase 迁移** | 仓库根目录 `supabase/migrations/*.sql` | 托管 Supabase 上的 PostgreSQL：**RLS、Auth、与 Lovable Cloud 对齐的 schema**。用于 `DATABASE_MODE=supabase` 或前端 `VITE_API_MODE=cloud`。 |
| **本地 PostgreSQL 初始化** | `python-agent-service/scripts/db/init_local_db.sql` | 单机 Docker：**首次创建数据卷时**由官方 Postgres 镜像的 `docker-entrypoint-initdb.d` **自动执行一次**，建表与本地认证所需结构（见该脚本内注释与表定义）。 |

**本次 EC2（`DATABASE_MODE=local`）发生了什么：**

1. `docker-compose.vm.yml` 为 Postgres 挂载命名卷 **`postgres-data`**。
2. **第一次**在该卷上空库启动容器时，`init_local_db.sql` 作为 **`/docker-entrypoint-initdb.d/init.sql`** 执行，完成本地库 **schema 初始化**。
3. 这不是 ORM 的「版本化迁移命令」（如 Alembic/Prisma migrate），而是 **一次性 SQL 引导文件**；与 CI_CD 技能文档中说明一致：**破坏性迁移无法用回滚容器镜像撤销**，扩缩表应走变更评审与备份。

**若你已跑过一次并希望强制重新初始化 Postgres：**

```bash
docker compose -f docker-compose.vm.yml down
docker volume rm python-agent-service_postgres-data   # 名称以 docker volume ls 为准
docker compose -f docker-compose.vm.yml up -d
```

**若要在本机对齐 Supabase 云上的某次迁移：** 一般由 Supabase Dashboard / CI 对已连接项目执行 **`supabase db push` 或托管迁移**；**不要**假设把 `supabase/migrations/*.sql` 整批丢进本地 `init_local_db.sql` 即可——其中含 RLS/Auth 与本地模式可能不兼容，需单独评估。

---

## 5. 前端构建与 Nginx（SPA）

### 5.1 构建

在 `~/secmanus-workspace`：

```bash
export VITE_API_MODE=local
export VITE_LOCAL_API_URL=http://18.216.190.63:8000
npm ci
npm run build
```

`VITE_LOCAL_API_URL` 必须指向 **浏览器可访问的后端地址**（公网 IP + 端口或域名）。

### 5.2 Nginx 配置要点

- `root` 指向 `dist`；
- `location /` 使用 SPA 回退：`try_files $uri $uri/ /index.html;`
- 配置文件须为 **LF 行尾**（Windows 编辑后若带 CR，Nginx 会解析异常）。

### 5.3 权限

默认 `www-data` 无法进入 `/home/ubuntu`（家目录常为 `750`）。可选其一：

- `chmod o+x /home/ubuntu`（最小改动，使 Nginx 能沿路径 `stat` 到 `dist`）；或  
- 将 `dist` 同步到 `/var/www/secmanus` 并把 `root` 指过去（更规范）。

---

## 6. 最终访问链接（验证清单）

请在 **放行安全组端口** 后，用浏览器自检：

| 页面 / 接口 | URL |
|-------------|-----|
| 前端（营销页 + SPA） | [http://18.216.190.63/](http://18.216.190.63/) |
| 后端健康检查 | [http://18.216.190.63:8000/health](http://18.216.190.63:8000/health) |

注册/登录与项目数据走 **本地 API + 本地 Postgres**（当前 `VITE_API_MODE=local`）；若改回 Supabase 云，需改为 `cloud` 模式并在构建参数中填入 `VITE_SUPABASE_*`。

---

## 7. 若后续要完全对齐 CI_CD skill（GitHub → ECR → ec2-ssh）

1. 在 GitHub 安装模板工作流（见 `.cursor/skills/CI_CD/templates/`）。
2. 配置 `AWS_RELEASE_ROLE_ARN`、`AWS_EC2_SSH_PRIVATE_KEY`（仅存 Secret 名或控制台配置，不写仓库）。
3. 在 `.cicd/env/<env>.yaml` 写入 `ec2.single_node.host: 18.216.190.63`（及容器名等与线上一致）。
4. 流水线仍 **不会默认执行数据库迁移**：Expand–Migrate–Contract 与是否在 deploy 前加 Job，需团队在应用仓自行落地（与 `AWS-CI-CD-SKILL.md` 第 4 节一致）。

---

*文档生成日期：2026-05-09；分支快照：`origin/dev-chenry-binary`。*

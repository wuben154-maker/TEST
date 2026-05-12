# DeepAgent 服务部署指南

本指南帮助你将 Python DeepAgent 服务部署到云平台。

## 🚀 快速部署选项

### 方式一：Railway（推荐，最简单）

1. **创建 Railway 账号**
   - 访问 [railway.app](https://railway.app) 并注册

2. **部署服务**
   ```bash
   # 安装 Railway CLI
   npm install -g @railway/cli
   
   # 登录
   railway login
   
   # 在 python-agent-service 目录下
   cd python-agent-service
   
   # 初始化并部署
   railway init
   railway up
   ```

3. **配置环境变量**
   在 Railway Dashboard 中设置以下变量：
   ```
   GOOGLE_API_KEY=your-google-api-key
   SUPABASE_URL=https://oesjguzpffndunspkosj.supabase.co
   SUPABASE_ANON_KEY=your-supabase-anon-key
   ```

4. **获取服务 URL**
   部署成功后，Railway 会分配一个 URL，如：
   `https://deepagent-xxx.up.railway.app`

---

### 方式二：Fly.io

1. **安装 Fly CLI**
   ```bash
   # macOS
   brew install flyctl
   
   # Windows
   powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
   
   # Linux
   curl -L https://fly.io/install.sh | sh
   ```

2. **登录并部署**
   ```bash
   # 登录
   fly auth login
   
   # 在 python-agent-service 目录下
   cd python-agent-service
   
   # 启动部署（首次会创建应用）
   fly launch --config fly.toml
   
   # 后续更新部署
   fly deploy
   ```

3. **配置 Secrets**
   ```bash
   fly secrets set GOOGLE_API_KEY=your-google-api-key
   fly secrets set SUPABASE_URL=https://oesjguzpffndunspkosj.supabase.co
   fly secrets set SUPABASE_ANON_KEY=your-supabase-anon-key
   ```

4. **获取服务 URL**
   ```bash
   fly status
   # URL: https://deepagent-security.fly.dev
   ```

---

### 方式三：Docker 自托管

1. **构建镜像**
   ```bash
   cd python-agent-service
   docker build -t deepagent-security .
   ```

2. **运行容器**
   ```bash
   docker run -d \
     -p 8000:8000 \
     -e GOOGLE_API_KEY=your-key \
     -e SUPABASE_URL=https://oesjguzpffndunspkosj.supabase.co \
     -e SUPABASE_ANON_KEY=your-anon-key \
     --name deepagent \
     deepagent-security
   ```

---

## ⚙️ 必需的环境变量

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `GOOGLE_API_KEY` | ✅ | Google AI API Key（用于 Gemini） |
| `SUPABASE_URL` | ✅ | Supabase 项目 URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase 匿名 Key |
| `ANTHROPIC_API_KEY` | ❌ | Anthropic API Key（可选） |
| `OPENAI_API_KEY` | ❌ | OpenAI API Key（可选） |
| `VIRUSTOTAL_API_KEY` | ❌ | VirusTotal API Key（威胁情报） |
| `LANGSMITH_API_KEY` | ❌ | LangSmith Key（可观测性） |

---

## 🔗 连接到前端

部署成功后，需要在 Lovable Cloud 中配置 `DEEP_AGENT_SERVICE_URL`：

1. 在 Lovable 项目中添加 Secret：
   - 名称：`DEEP_AGENT_SERVICE_URL`
   - 值：你的部署 URL（如 `https://deepagent-xxx.up.railway.app`）

2. Edge Function 会自动检测并使用 Python 服务

---

## 🧪 验证部署

```bash
# 健康检查
curl https://your-service-url/health

# 预期响应
# {"status":"healthy","version":"2.0.0","framework":"DeepAgents"}

# 测试分析
curl -X POST https://your-service-url/analyze \
  -H "Content-Type: application/json" \
  -d '{"message": "Suspicious IP: 192.168.1.1", "stream": false}'
```

---

## 📊 监控与日志

### Railway
- 在 Dashboard 的 Logs 标签页查看实时日志

### Fly.io
```bash
# 查看日志
fly logs

# 查看状态
fly status

# SSH 到容器
fly ssh console
```

---

## 🔧 故障排除

### 服务无响应
1. 检查健康检查端点：`/health`
2. 查看日志确认启动成功
3. 确认环境变量配置正确

### AI 调用失败
1. 验证 API Key 是否有效
2. 检查 API 配额是否充足
3. 确认网络访问正常

### 内存不足
- Railway：升级到更高配置
- Fly.io：修改 `fly.toml` 中的 `memory` 配置

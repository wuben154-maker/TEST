# Python 虚拟环境构建指南

本文档说明如何为 `python-agent-service` 项目创建和配置 Python 虚拟环境。

---

## 📋 前置要求

- **Python 3.10+** 已安装
- 确认 Python 版本：
  ```bash
  python --version
  # 或
  python3 --version
  ```

---

## 🚀 快速开始

### Windows

```powershell
# 1. 进入 Python 服务目录
cd python-agent-service

# 2. 创建虚拟环境
python -m venv venv

# 3. 激活虚拟环境
.\venv\Scripts\activate

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装依赖
pip install -r requirements.txt

# 6. 配置环境变量
copy env.template .env
# 然后编辑 .env 文件，填入必要的配置
```

### Linux/Mac

```bash
# 1. 进入 Python 服务目录
cd python-agent-service

# 2. 创建虚拟环境
python3 -m venv venv

# 3. 激活虚拟环境
source venv/bin/activate

# 4. 升级 pip
python -m pip install --upgrade pip

# 5. 安装依赖
pip install -r requirements.txt

# 6. 配置环境变量
cp env.template .env
# 然后编辑 .env 文件，填入必要的配置
```

---

## 📝 详细步骤

### 步骤 1: 创建虚拟环境

虚拟环境将创建在 `python-agent-service/venv` 目录下。

#### Windows PowerShell

```powershell
cd python-agent-service
python -m venv venv
```

#### Linux/Mac

```bash
cd python-agent-service
python3 -m venv venv
```

**验证创建**：
- Windows: 检查 `venv\Scripts\python.exe` 是否存在
- Linux/Mac: 检查 `venv/bin/python` 是否存在

### 步骤 2: 激活虚拟环境

激活后，终端提示符前会显示 `(venv)` 前缀。

#### Windows PowerShell

```powershell
.\venv\Scripts\activate
```

如果遇到执行策略错误：

**方法 1：设置执行策略（如果允许）**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**方法 2：如果执行策略被组策略限制，使用 CMD 激活（推荐）**
```powershell
# 在 PowerShell 中使用 CMD 执行激活脚本
cmd /c "venv\Scripts\activate.bat && python --version"
```

**方法 3：使用项目提供的激活脚本**
```powershell
# 使用项目根目录下的 activate.ps1（绕过执行策略限制）
.\activate.ps1
```

**方法 4：直接使用完整路径（无需激活）**
```powershell
# 直接使用虚拟环境中的 Python，无需激活
.\venv\Scripts\python.exe --version
.\venv\Scripts\pip.exe install -r requirements.txt
```

#### Windows CMD

```cmd
venv\Scripts\activate.bat
```

#### Linux/Mac

```bash
source venv/bin/activate
```

**验证激活**：
- 终端提示符前应该显示 `(venv)`
- 运行 `which python` (Linux/Mac) 或 `where python` (Windows)，应该指向 venv 目录

### 步骤 3: 升级 pip

```bash
python -m pip install --upgrade pip
```

### 步骤 4: 安装项目依赖

```bash
pip install -r requirements.txt
```

**如果安装速度慢，可以使用国内镜像源**：

```bash
# 使用清华大学镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用阿里云镜像源
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

**主要依赖包**：
- `langchain` 和 `langgraph` - AI Agent 框架
- `fastapi` 和 `uvicorn` - Web 框架和 ASGI 服务器
- `langchain-openai`, `langchain-anthropic`, `langchain-google-genai` - LLM 提供商
- `structlog` - 结构化日志
- `pydantic` - 数据验证
- 其他工具和库（详见 `requirements.txt`）

### 步骤 5: 配置环境变量

1. **复制环境变量模板**：
   ```bash
   # Windows
   copy env.template .env
   
   # Linux/Mac
   cp env.template .env
   ```

2. **编辑 `.env` 文件**，填入必要的配置：
   - **API Keys**（至少配置一个）：
     - `OPENAI_API_KEY` - OpenAI API 密钥
     - `ANTHROPIC_API_KEY` - Anthropic API 密钥
     - `GOOGLE_API_KEY` - Google Gemini API 密钥
   
   - **数据库配置**（如果使用本地数据库）：
     - `DATABASE_MODE=local`
     - `LOCAL_DB_HOST=localhost`
     - `LOCAL_DB_PORT=5432`
     - `LOCAL_DB_NAME=secmanus`
     - `LOCAL_DB_USER=postgres`
     - `LOCAL_DB_PASSWORD=postgres`
   
   - **Supabase 配置**（如果使用云数据库）：
     - `DATABASE_MODE=supabase`
     - `SUPABASE_URL=your_supabase_url`
     - `SUPABASE_ANON_KEY=your_anon_key`
     - `SUPABASE_SERVICE_ROLE_KEY=your_service_role_key`

### 步骤 6: 验证虚拟环境

```bash
# 检查 Python 解释器路径
which python   # Linux/Mac
where python   # Windows

# 应该指向：
# Windows: ...\python-agent-service\venv\Scripts\python.exe
# Linux/Mac: .../python-agent-service/venv/bin/python

# 检查已安装的包
pip list

# 测试导入关键模块
python -c "import fastapi; print('FastAPI:', fastapi.__version__)"
python -c "import uvicorn; print('Uvicorn installed')"
python -c "import langchain; print('LangChain installed')"
```

### 步骤 7: 在 VS Code/Cursor 中选择解释器

1. **打开命令面板**：
   - Windows/Linux: `Ctrl+Shift+P`
   - Mac: `Cmd+Shift+P`

2. **选择 Python 解释器**：
   - 输入 "Python: Select Interpreter"
   - 选择 `python-agent-service/venv` 中的解释器
     - Windows: `.\python-agent-service\venv\Scripts\python.exe`
     - Linux/Mac: `./python-agent-service/venv/bin/python`

3. **验证选择**：
   - 打开任意 Python 文件
   - 查看右下角状态栏，应该显示虚拟环境的 Python 路径
   - 打开终端，应该自动激活虚拟环境（看到 `(venv)` 前缀）

### 步骤 8: 测试启动服务

```bash
# 确保在虚拟环境中
cd python-agent-service

# 测试启动（不调试模式）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 或使用启动脚本
python run_server.py
```

**成功启动的标志**：
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

访问 `http://localhost:8000/health` 应该返回健康检查响应。

---

## 🔧 常见问题

### Q1: 虚拟环境创建失败？

**可能原因**：
- Python 版本过低（需要 3.10+）
- 磁盘空间不足
- 权限问题

**解决方案**：
```bash
# 检查 Python 版本
python --version

# 尝试使用 python3
python3 -m venv venv

# Windows: 以管理员身份运行 PowerShell
# Linux/Mac: 检查目录权限
```

### Q2: `pip install` 失败或速度很慢？

**解决方案**：
```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 如果特定包安装失败，单独安装
pip install package_name -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q3: 虚拟环境激活后命令不可用？

**Windows PowerShell - 执行策略错误**：

如果遇到 "禁止运行脚本" 错误，有以下解决方案：

**方案 A：设置执行策略（如果系统允许）**
```powershell
# 检查当前执行策略
Get-ExecutionPolicy

# 设置执行策略
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 重新激活
.\venv\Scripts\activate
```

**方案 B：执行策略被组策略限制时（推荐）**
```powershell
# 方法1: 使用 CMD 激活（最简单）
cmd /c "venv\Scripts\activate.bat && python --version"

# 方法2: 使用项目提供的激活脚本
.\activate.ps1

# 方法3: 直接使用完整路径，无需激活
.\venv\Scripts\python.exe --version
.\venv\Scripts\pip.exe list
```

**Windows CMD**：
```cmd
# 使用 .bat 文件激活（不受执行策略影响）
venv\Scripts\activate.bat
```

### Q4: VS Code/Cursor 找不到虚拟环境？

**解决方案**：
1. 确保虚拟环境已创建在 `python-agent-service/venv` 目录
2. 手动选择解释器（见步骤 7）
3. 重启 VS Code/Cursor
4. 检查 `.vscode/settings.json` 中的路径配置

### Q7: 调试时出现 "Debug Stopped" 错误？

**可能原因**：
- Python 解释器路径不正确
- debugpy 未安装或版本不兼容
- VS Code/Cursor 未正确选择 Python 解释器
- 模块导入失败

**解决方案**：

1. **手动选择 Python 解释器**：
   ```powershell
   # 按 Ctrl+Shift+P 打开命令面板
   # 输入 "Python: Select Interpreter"
   # 选择: python-agent-service/venv/Scripts/python.exe
   ```

2. **运行诊断脚本**：
   ```powershell
   cd python-agent-service
   .\diagnose_debug.ps1
   ```

3. **检查 debugpy 安装**：
   ```powershell
   .\venv\Scripts\python.exe -c "import debugpy; print(debugpy.__version__)"
   ```

4. **尝试不同的调试配置**：
   - 如果 "Python: FastAPI (Uvicorn)" 失败，尝试 "Python: FastAPI (No Reload)"
   - 不带 `--reload` 参数可能更稳定

5. **检查调试日志**：
   - 查看 VS Code/Cursor 的调试控制台（Debug Console）
   - 查看 `.vscode/debugpy.log` 文件（如果配置了日志）

6. **重启 VS Code/Cursor**：
   - 完全关闭并重新打开编辑器
   - 确保 Python 扩展已加载

7. **验证模块导入**：
   ```powershell
   cd python-agent-service
   .\venv\Scripts\python.exe -c "import app.main; print('OK')"
   ```

### Q5: 如何删除并重建虚拟环境？

```bash
# 1. 退出虚拟环境
deactivate

# 2. 删除旧环境
# Windows
rmdir /s venv

# Linux/Mac
rm -rf venv

# 3. 重新创建（见步骤 1）
python -m venv venv  # 或 python3 -m venv venv
```

### Q6: 导入模块时出错？

**检查**：
```bash
# 确认在虚拟环境中
which python  # 应该指向 venv

# 检查包是否安装
pip list | grep package_name

# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

---

## 📂 虚拟环境目录结构

创建成功后，`python-agent-service/venv` 目录结构应该类似：

```
venv/
├── Scripts/              # Windows: 可执行文件
│   ├── python.exe
│   ├── pip.exe
│   ├── activate
│   └── activate.ps1
├── bin/                  # Linux/Mac: 可执行文件
│   ├── python
│   ├── pip
│   └── activate
├── Lib/                  # Windows: Python 库
│   └── site-packages/
│       ├── fastapi/
│       ├── uvicorn/
│       ├── langchain/
│       └── ...
├── lib/                  # Linux/Mac: Python 库
│   └── python3.x/
│       └── site-packages/
│           ├── fastapi/
│           ├── uvicorn/
│           ├── langchain/
│           └── ...
└── pyvenv.cfg           # 虚拟环境配置文件
```

---

## ⚠️ 重要注意事项

### 1. 不要提交虚拟环境到 Git

- `venv/` 目录已在 `.gitignore` 中
- 每个开发者需要自己创建虚拟环境
- 只提交 `requirements.txt` 文件

### 2. 虚拟环境是项目特定的

- 不要在不同项目间共享虚拟环境
- 每个项目应该有独立的虚拟环境
- 虚拟环境路径：`python-agent-service/venv`

### 3. 定期更新依赖

```bash
# 更新所有包到最新版本
pip install --upgrade -r requirements.txt

# 或更新特定包
pip install --upgrade package_name
```

### 4. 导出依赖列表（可选）

如果需要锁定依赖版本：

```bash
# 导出当前环境的所有包及版本
pip freeze > requirements-lock.txt

# 使用锁定的版本安装
pip install -r requirements-lock.txt
```

### 5. 虚拟环境激活状态

- 每次打开新终端都需要重新激活虚拟环境
- VS Code/Cursor 可以配置自动激活（见 `.vscode/settings.json`）
- 激活后，`pip install` 的包会安装到虚拟环境中，而不是系统 Python

---

## 🧪 验证清单

完成虚拟环境设置后，请验证以下项目：

- [ ] Python 版本 >= 3.10
- [ ] 虚拟环境已创建在 `python-agent-service/venv`
- [ ] 虚拟环境可以成功激活（看到 `(venv)` 前缀）
- [ ] 所有依赖已安装（`pip list` 显示所有需要的包）
- [ ] `.env` 文件已创建并配置
- [ ] VS Code/Cursor 已选择正确的 Python 解释器
- [ ] 可以成功导入关键模块（fastapi, uvicorn, langchain）
- [ ] 可以成功启动服务（`python -m uvicorn app.main:app`）

---

## 📚 相关文档

- [Python venv 官方文档](https://docs.python.org/3/library/venv.html)
- [pip 用户指南](https://pip.pypa.io/en/stable/user_guide/)
- [VS Code Python 环境配置](https://code.visualstudio.com/docs/python/environments)
- 项目 `requirements.txt` 文件
- `.vscode/README.md` - VS Code 配置说明

---

## 💡 提示

- 如果遇到问题，先检查 Python 版本和虚拟环境路径
- 使用 `pip list` 查看已安装的包
- 使用 `python -c "import module"` 测试模块导入
- 查看终端错误信息，通常会有明确的提示
- 确保网络连接正常（安装依赖需要下载包）



调试注意事项：

## 🔍 问题总结

**核心问题**：在 Cursor/VS Code 中调试 Python 时，如果出现以下错误：
- "You need to select a Python interpreter before you start debugging"
- "The Python path in your debug configuration is invalid"
- "Debug Stopped" 对话框（无任何输出）

**根本原因**：Cursor/VS Code 的 Python 扩展需要**明确知道使用哪个 Python 解释器**，即使 `settings.json` 中配置了默认路径，有时也需要手动在状态栏选择一次。

方法1：
# 按 Ctrl+Shift+P 打开命令面板
Python: Select Interpreter

# 或者更具体的命令
Python: Set Interpreter

方法2：
vscode看窗口底部状态栏，右侧会有一个 Python 版本/“Select Interpreter” 的位置。



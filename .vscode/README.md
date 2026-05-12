# .vscode 配置文件生成指南

本目录包含 VS Code/Cursor 的工作区配置文件。如果这些文件丢失，可以通过以下方式重新生成。

---

## 📁 文件说明

### 1. `settings.json` - 工作区设置
- Python 解释器路径
- Python 分析配置
- 文件排除规则
- 代码格式化设置

### 2. `launch.json` - 调试配置
- 前端 React 应用调试
- 后端 Python FastAPI 调试
- 全栈调试配置

### 3. `tasks.json` - 任务配置
- npm 开发服务器任务
- Python 服务启动任务

---

## 🚀 快速生成方法

### 方法 1: 通过 Cursor AI 助手生成（推荐）

**提示词**：
```
请为这个项目生成 .vscode 配置文件：

项目结构：
- 前端：React + TypeScript + Vite，端口 8080
- 后端：Python FastAPI + Uvicorn，端口 8000
- Python 虚拟环境：python-agent-service/venv
- 工作区根目录：${workspaceFolder}

需要生成：
1. settings.json - Python 解释器路径、代码格式化、文件排除
2. launch.json - 前端 Chrome 调试、后端 Python 调试、全栈调试
3. tasks.json - npm dev 任务、Python uvicorn 启动任务

要求：
- Python 解释器：${workspaceFolder}/python-agent-service/venv/Scripts/python.exe
- Python 工作目录：${workspaceFolder}/python-agent-service
- 前端开发服务器：npm run dev，端口 8080
- 后端服务器：uvicorn app.main:app --reload，端口 8000
```

---

### 方法 2: 手动创建文件

#### 步骤 1: 创建 `.vscode` 目录
```bash
mkdir .vscode
```

#### 步骤 2: 创建 `settings.json`
在 Cursor 中：
1. 按 `Ctrl+Shift+P` (Windows) 或 `Cmd+Shift+P` (Mac)
2. 输入 "Preferences: Open Workspace Settings (JSON)"
3. 这会自动创建 `.vscode/settings.json`

#### 步骤 3: 创建 `launch.json`
在 Cursor 中：
1. 切换到 "Run and Debug" 视图 (`Ctrl+Shift+D`)
2. 点击 "create a launch.json file"
3. 选择 "Python" 或 "Chrome" 作为调试器
4. 这会自动创建 `.vscode/launch.json`

#### 步骤 4: 创建 `tasks.json`
在 Cursor 中：
1. 按 `Ctrl+Shift+P`
2. 输入 "Tasks: Configure Task"
3. 选择 "Create tasks.json file from template"
4. 选择 "Others"

---

### 方法 3: 使用模板文件

直接复制以下模板内容：

#### `settings.json` 模板
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/python-agent-service/venv/Scripts/python.exe",
  "python.terminal.activateEnvironment": true,
  "python.analysis.extraPaths": [
    "${workspaceFolder}/python-agent-service"
  ],
  "python.analysis.autoImportCompletions": true,
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  },
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "ms-python.black-formatter",
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  }
}
```

#### `launch.json` 模板
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug React App",
      "type": "chrome",
      "request": "launch",
      "url": "http://localhost:8080",
      "webRoot": "${workspaceFolder}/src",
      "sourceMaps": true,
      "preLaunchTask": "npm: dev"
    },
    {
      "name": "Python: FastAPI (Uvicorn)",
      "type": "debugpy",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
      ],
      "jinja": true,
      "justMyCode": false,
      "cwd": "${workspaceFolder}/python-agent-service",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/python-agent-service"
      },
      "python": "${workspaceFolder}/python-agent-service/venv/Scripts/python.exe",
      "console": "integratedTerminal",
      "autoReload": {
        "enable": true
      }
    },
    {
      "name": "Python: Current File",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "cwd": "${workspaceFolder}/python-agent-service",
      "python": "${workspaceFolder}/python-agent-service/venv/Scripts/python.exe",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/python-agent-service"
      },
      "justMyCode": false
    }
  ],
  "compounds": [
    {
      "name": "Debug Full Stack",
      "configurations": ["Debug React App", "Python: FastAPI (Uvicorn)"]
    }
  ]
}
```

#### `tasks.json` 模板
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "npm: dev",
      "type": "shell",
      "command": "npm",
      "args": ["run", "dev"],
      "isBackground": true,
      "problemMatcher": {
        "pattern": {
          "regexp": "^$",
          "file": 1,
          "location": 2,
          "message": 3
        },
        "background": {
          "activeOnStart": true,
          "beginsPattern": ".*VITE.*ready.*",
          "endsPattern": ".*Local:.*http://localhost:8080.*"
        }
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "Python: Start Uvicorn (Background)",
      "type": "shell",
      "command": "${workspaceFolder}/python-agent-service/venv/Scripts/python.exe",
      "args": [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
      ],
      "options": {
        "cwd": "${workspaceFolder}/python-agent-service",
        "env": {
          "PYTHONPATH": "${workspaceFolder}/python-agent-service"
        }
      },
      "isBackground": true,
      "problemMatcher": {
        "pattern": {
          "regexp": "^$"
        },
        "background": {
          "activeOnStart": true,
          "beginsPattern": ".*",
          "endsPattern": ".*Uvicorn running on.*"
        }
      },
      "presentation": {
        "reveal": "always",
        "panel": "dedicated",
        "focus": false
      }
    }
  ]
}
```

---

## 🔧 通过 Cursor AI 生成的具体步骤

### 步骤 1: 打开 Cursor AI 聊天
- 按 `Ctrl+L` (Windows) 或 `Cmd+L` (Mac) 打开 AI 聊天面板

### 步骤 2: 使用生成提示词
复制并发送以下提示词：

```
我需要为这个项目生成 .vscode 配置文件。请创建以下三个文件：

1. .vscode/settings.json
   - Python 解释器路径：${workspaceFolder}/python-agent-service/venv/Scripts/python.exe
   - Python 工作目录：${workspaceFolder}/python-agent-service
   - 启用 Python linting (flake8)
   - 排除 __pycache__ 和 .pyc 文件
   - Python 代码保存时自动格式化 (black)

2. .vscode/launch.json
   - React 应用调试配置（Chrome，端口 8080）
   - Python FastAPI 调试配置（uvicorn，端口 8000）
   - Python 当前文件调试配置
   - 全栈调试组合配置

3. .vscode/tasks.json
   - npm dev 任务（前端开发服务器）
   - Python uvicorn 启动任务（后端服务器）

项目信息：
- 前端：React + TypeScript + Vite，运行在 http://localhost:8080
- 后端：Python FastAPI，运行在 http://localhost:8000
- Python 模块路径：${workspaceFolder}/python-agent-service
```

### 步骤 3: 应用生成的代码
- Cursor AI 会生成代码
- 点击 "Accept" 或使用快捷键应用更改
- 确保文件保存在 `.vscode/` 目录下

---

## 📝 验证配置

生成配置文件后，验证：

1. **settings.json**:
   - 打开 Python 文件，检查右下角是否显示正确的解释器路径
   - 保存 Python 文件，检查是否自动格式化

2. **launch.json**:
   - 按 `F5` 或切换到 "Run and Debug" 视图
   - 应该能看到所有调试配置
   - 选择 "Debug Full Stack" 应该能同时启动前后端

3. **tasks.json**:
   - 按 `Ctrl+Shift+P`，输入 "Tasks: Run Task"
   - 应该能看到 "npm: dev" 和 "Python: Start Uvicorn" 任务

---

## 🛠️ 常见问题

### Q: 配置文件丢失后如何快速恢复？
A: 使用上面的方法 1（Cursor AI）或方法 3（模板文件）最快。

### Q: Python 解释器路径不对怎么办？
A: 检查 `python-agent-service/venv/Scripts/python.exe` 是否存在，如果虚拟环境在其他位置，修改 `settings.json` 中的路径。

### Q: 调试配置不工作？
A: 
- 确保安装了必要的扩展：Python、Debugger for Chrome
- 检查端口是否被占用（8080 和 8000）
- 确保虚拟环境已激活

### Q: 如何添加新的调试配置？
A: 在 `launch.json` 的 `configurations` 数组中添加新配置，参考现有配置的格式。

---

## 📚 相关资源

- [VS Code 调试文档](https://code.visualstudio.com/docs/editor/debugging)
- [VS Code 任务文档](https://code.visualstudio.com/docs/editor/tasks)
- [Python 调试配置](https://code.visualstudio.com/docs/python/debugging)

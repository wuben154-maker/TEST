# Python 虚拟环境使用指南

## 问题
如果遇到 `ModuleNotFoundError: No module named 'structlog'` 等模块缺失错误，通常是因为没有激活虚拟环境。

## 解决方案

### Windows PowerShell

1. **激活虚拟环境**：
```powershell
cd python-agent-service
.\activate.ps1
```

2. **或者手动激活**：
```powershell
cd python-agent-service
.\venv\Scripts\Activate.ps1
```

3. **验证环境**：
```powershell
python --version
# 应该显示虚拟环境中的 Python 版本
which python
# 应该指向 venv\Scripts\python.exe
```

### Windows CMD

```cmd
cd python-agent-service
venv\Scripts\activate.bat
```

### 安装依赖

如果虚拟环境中缺少依赖：

```powershell
# 激活虚拟环境后
pip install -r requirements.txt
```

### VS Code / Cursor 配置

确保 VS Code/Cursor 使用虚拟环境中的 Python：

1. 按 `Ctrl+Shift+P`
2. 输入 "Python: Select Interpreter"
3. 选择：`.\venv\Scripts\python.exe`

或者在 `.vscode/settings.json` 中配置：
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/python-agent-service/venv/Scripts/python.exe"
}
```

## 验证安装

```powershell
python -c "import structlog; print('structlog version:', structlog.__version__)"
```

应该输出：`structlog version: 25.5.0`

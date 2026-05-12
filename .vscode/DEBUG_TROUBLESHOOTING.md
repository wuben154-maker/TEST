# 调试问题排查指南

## "Debug Stopped" 错误解决方案

### 问题现象
点击调试按钮后，立即弹出 "Debug Stopped" 对话框，没有任何输出。

### 根本原因
VS Code/Cursor 的 Python 扩展需要**明确知道使用哪个 Python 解释器**，即使 `settings.json` 中配置了默认路径，有时也需要手动在状态栏选择一次。

### 解决方案（按顺序尝试）

#### 方案 1：手动选择 Python 解释器（最常用）

1. **打开命令面板**：
   - 按 `Ctrl+Shift+P` (Windows/Linux) 或 `Cmd+Shift+P` (Mac)

2. **选择 Python 解释器**：
   - 输入 `Python: Select Interpreter`
   - 或输入 `Python: Set Interpreter`
   - 选择 `python-agent-service/venv/Scripts/python.exe` (Windows)
   - 或 `python-agent-service/venv/bin/python` (Linux/Mac)

3. **验证选择**：
   - 查看窗口底部状态栏右侧
   - 应该显示 Python 版本或路径
   - 点击可以快速切换解释器

4. **重新启动调试**：
   - 按 `F5` 或点击调试按钮
   - 选择 "Python: FastAPI (Uvicorn)"

#### 方案 2：使用状态栏选择解释器

1. 查看 VS Code/Cursor 窗口底部状态栏
2. 找到右侧显示 Python 版本的位置（可能显示 "Python 3.x.x" 或 "Select Interpreter"）
3. 点击该位置
4. 从列表中选择 `python-agent-service/venv/Scripts/python.exe`

#### 方案 3：尝试不同的调试配置

如果 "Python: FastAPI (Uvicorn)" 仍然失败：

1. 打开调试面板（`Ctrl+Shift+D`）
2. 在配置下拉菜单中选择：
   - **Python: FastAPI (No Reload)** - 不带自动重载，更稳定
   - **Python: Current File** - 用于调试单个文件

#### 方案 4：检查并修复配置

1. **验证 Python 路径**：
   ```powershell
   # 在终端中运行
   cd python-agent-service
   .\venv\Scripts\python.exe --version
   ```

2. **检查 launch.json**：
   - 确保 `python` 字段指向正确的路径
   - Windows: `${workspaceFolder}/python-agent-service/venv/Scripts/python.exe`
   - Linux/Mac: `${workspaceFolder}/python-agent-service/venv/bin/python`

3. **检查 settings.json**：
   - 确保 `python.defaultInterpreterPath` 正确设置

#### 方案 5：重启并清理

1. **完全关闭 VS Code/Cursor**
2. **删除 Python 扩展缓存**（可选）：
   - Windows: `%APPDATA%\Code\User\workspaceStorage\`
   - 或直接重启编辑器
3. **重新打开项目**
4. **重新选择 Python 解释器**（方案 1）

#### 方案 6：运行诊断脚本

```powershell
cd python-agent-service
.\diagnose_debug.ps1
```

根据诊断结果修复问题。

### 验证调试环境

运行以下命令验证环境：

```powershell
cd python-agent-service

# 1. 检查 Python 版本
.\venv\Scripts\python.exe --version

# 2. 检查 debugpy
.\venv\Scripts\python.exe -c "import debugpy; print('debugpy OK')"

# 3. 检查模块导入
.\venv\Scripts\python.exe -c "import app.main; print('app.main OK')"

# 4. 测试 uvicorn（不启动，只检查）
.\venv\Scripts\python.exe -m uvicorn --help
```

### 常见错误信息

#### "You need to select a Python interpreter before you start debugging"
- **解决**：使用方案 1 手动选择解释器

#### "The Python path in your debug configuration is invalid"
- **解决**：检查 `launch.json` 中的 `python` 路径是否正确
- 确保路径使用正斜杠 `/` 或正确的转义

#### "ModuleNotFoundError: No module named 'app'"
- **解决**：确保 `cwd` 设置为 `${workspaceFolder}/python-agent-service`
- 确保 `PYTHONPATH` 环境变量正确设置

### 调试技巧

1. **查看调试控制台**：
   - 调试时打开 "Debug Console" 标签
   - 查看详细的错误信息

2. **查看日志文件**：
   - 如果配置了 `logToFile`，查看 `.vscode/debugpy.log`

3. **使用断点**：
   - 在代码中设置断点
   - 如果断点不生效，说明调试器未正确附加

4. **逐步调试**：
   - 使用 "Python: Current File" 配置调试单个文件
   - 验证调试器是否正常工作

### 预防措施

1. **每次打开项目后**：
   - 检查状态栏的 Python 解释器选择
   - 确保指向虚拟环境

2. **提交代码前**：
   - 确保 `.vscode/settings.json` 中的路径正确
   - 不要提交个人特定的绝对路径

3. **团队协作**：
   - 使用 `${workspaceFolder}` 变量而不是绝对路径
   - 确保所有成员都创建了虚拟环境

---

如果以上方案都无法解决问题，请：
1. 运行 `diagnose_debug.ps1` 脚本
2. 查看 VS Code/Cursor 的输出面板（View → Output → Python）
3. 检查是否有 Python 扩展的错误信息

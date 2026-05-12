# 修复解释器选择问题

## 问题现象

在解释器选择对话框中：
- 红框中的选项（使用 "python.defaultInterpreterPath" 设置）无法选择
- 显示为相对路径 `.\python-agent-service\venv\Scripts\python.exe`
- 右下角弹出"选择解释器"提示

## 原因

VS Code/Cursor 的解释器选择器有时无法正确解析 `${workspaceFolder}` 变量，导致显示为相对路径且无法选择。

## 解决方案

### 方案 1：选择列表中已检测到的解释器（推荐）

在解释器选择对话框中：

1. **不要选择红框中的选项**（那个相对路径的选项）
2. **选择 "Python 3.14.0 64-bit"**，右侧显示 "推荐的项目"
   - 这个就是虚拟环境中的 Python 3.14.0
   - VS Code/Cursor 已经自动检测到了
3. 点击选择后，调试应该可以正常工作

### 方案 2：手动输入解释器路径

如果方案 1 不行：

1. 在解释器选择对话框中，点击 **"输入解释器路径..."**
2. 输入以下路径（根据你的实际路径调整）：
   ```
   C:\chenf\SecManus\secmanus-workspace\python-agent-service\venv\Scripts\python.exe
   ```
3. 或者使用相对路径（从工作区根目录）：
   ```
   python-agent-service\venv\Scripts\python.exe
   ```

### 方案 3：更新 settings.json 使用绝对路径（临时方案）

如果上述方案都不行，可以临时使用绝对路径：

1. 打开 `.vscode/settings.json`
2. 将 `python.defaultInterpreterPath` 改为绝对路径：
   ```json
   {
     "python.defaultInterpreterPath": "C:\\chenf\\SecManus\\secmanus-workspace\\python-agent-service\\venv\\Scripts\\python.exe"
   }
   ```
3. **注意**：绝对路径不利于团队协作，建议只在个人开发时使用

### 方案 4：验证解释器选择

选择解释器后，验证是否正确：

1. 查看状态栏右下角，应该显示 Python 版本或路径
2. 打开任意 Python 文件
3. 查看状态栏，确认显示的是虚拟环境的 Python
4. 在终端中运行：
   ```powershell
   python --version
   where python
   ```
   应该指向虚拟环境中的 Python

## 推荐操作步骤

1. **直接选择 "Python 3.14.0 64-bit"（推荐的项目）**
   - 这是最简单可靠的方法
   - VS Code/Cursor 已经正确检测到了虚拟环境

2. **验证选择**：
   - 状态栏显示 Python 3.14.0
   - 可以正常调试

3. **如果还有问题**：
   - 重启 VS Code/Cursor
   - 重新选择解释器
   - 检查 `.vscode/settings.json` 配置

## 为什么红框中的选项无法选择？

- VS Code/Cursor 的解释器选择器在解析 `${workspaceFolder}` 变量时可能有问题
- 显示为相对路径 `.\python-agent-service\...` 时，路径解析可能失败
- 这是 VS Code Python 扩展的已知问题，不影响使用

## 最佳实践

1. **使用自动检测的解释器**：
   - VS Code/Cursor 会自动扫描项目中的虚拟环境
   - 选择标记为 "推荐的项目" 的解释器通常最可靠

2. **避免使用相对路径**：
   - 在 `settings.json` 中使用 `${workspaceFolder}` 变量
   - 但在解释器选择时，优先选择自动检测的选项

3. **团队协作**：
   - 不要提交包含绝对路径的 `settings.json`
   - 每个开发者自己选择解释器即可

# Proposal: Agent 多格式安全读取（Webshell / 二进制 / 邮件）

## Metadata

- **Slug**: `agent-multiformat-file-read`
- **Status**: planned
- **Last updated**: 2026-04-28

## Problem

安全分析场景下，Agent 通过 `read_file` 读取用户上传或沙箱内的文件时，常见问题包括：

1. **文本误判**：`.php`、`.txt`、无扩展名等被当作 UTF-8 文本打开，遇到 GBK/其它编码即 `UnicodeDecodeError`（与当前 `FilesystemBackend.read` 行为一致）。
2. **Webshell**：多数为短文本或混杂压缩/编码 payload；需要可读文本、可选十六进制预览与编码元数据，而非直接失败。
3. **二进制**：PE/DLL、图片、压缩包等应避免误用文本解码；需要统一 **base64 + MIME + 大小上限**，并可选 **头部 hex 摘要**。
4. **邮件**：`.eml` / `.mbox` 需解析出 **头/正文/附件元数据**，避免把大附件当行文本读入上下文。

当前 DeepAgents 链路已区分 `_get_file_type` 的 text vs 非 text，但 **text 路径硬编码 UTF-8**，无法满足上述混合现实。

## Goals

- 提供 **单一入口的读取函数**（及配套 Agent 工具契约），对调用方返回 **结构化结果**（类型、编码、截断、风险提示），而非裸字符串或泛泛 Error。
- 覆盖：**Webshell 常见文本形态**、**明确定义的二进制族**、**RFC 822 风格邮件**，并对 **设备文件 / 超大文件 / 单行巨文件 / 空洞路径** 等做显式处理。
- **借鉴 Claude Code FileReadTool**：多形态输出、扩展名/类型门禁、行分页与字节预算、BOM/换行规范化、去读重（dedup）与安全提示（在产品 policy 中落地）。

## Non-goals

- 不在本期实现完整恶意软件动态分析、沙箱执行或反病毒引擎集成。
- 不承诺对任意私有邮件格式（如部分加密 PST）开箱完整解析；仅定义 **EML/MIME 树** 与退化行为。
- 不在本期重做整个 `edit_file` / `write_file` 的编码策略（可后续对齐）。

## Users

- **安全分析 Agent**（web-security subagent 等）：读取检材、引用片段、减少工具失败率。
- **平台工程师**：统一上限、观测指标与审计日志字段。

## Scope（本期设计约束）

- 以 **Python（python-agent-service）** 为落地语言；与现有 `ReadResult` / `FileData` 协议对齐或可映射。
- 读取对象默认为 **已落盘路径**（或后端 `BackendProtocol.read` 入参）；不讨论浏览器直传流式协议细节。

## Dependencies

- 可选：`charset-normalizer`（或等价）用于文本编码探测。
- 可选：`stdlib email.parser` 处理 `.eml`；`mbox` 仅建议「按需读首封」策略。
- Claude Code 参考实现（第三方归档）：[FileReadTool](https://github.com/chauncygu/collection-claude-code-source-code/blob/main/original-source-code/src/tools/FileReadTool/FileReadTool.ts)、[readFileInRange](https://github.com/chauncygu/collection-claude-code-source-code/blob/main/original-source-code/src/utils/readFileInRange.ts)。

## Success metrics

- **工具失败率**：非损坏文件在抽样集（UTF-8 / GBK PHP / 小 PE / 单封 eml）上 **read 工具返回可解析结构化结果** 的比例 ≥ 约定阈值（在 `acceptance.md` 中量化）。
- **上下文可控**：单次读取默认 **字节 + 行 + token/字符** 三重上限可配置；超大文件不得静默 OOM。
- **可观测**：每次读取日志含 `content_kind`、`declared_encoding`、`truncated`、`duration_ms`（无敏感正文）。

## References

- 现有实现：`python-agent-service/app/_vendor/deepagents/backends/filesystem.py` 中 `read()` UTF-8 文本路径与 `UnicodeDecodeError` 处理。
- `design.md` 为实施与设计细节的唯一来源（SoT）。

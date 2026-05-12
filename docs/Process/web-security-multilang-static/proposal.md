# Proposal: Multi-language hosted-code static analysis

## Problem

`detect_web_attack` 的代码分支目前以 **PHP**（`<?php`）为主；分类器也主要依赖 PHP 标记。用户需要在 **同一工具** 内对 **PHP、JSP、Python、ASP.NET（ASPX/C# 服务端片段）** 做可比对的高危 sink 检测（`py` 与 **Python** 为同一语言，不重复实现）。

## Goals

- 在 `webshell_or_code` / `mixed` 路径下，按 **推断的主语言** 运行对应静态 sink 扫描（与现有 PHP 逻辑同级）。
- **语言优先级（实现与歧义消解顺序）**：PHP → JSP → Python → ASPX。
- 保持 **schema v2** 兼容：`parse_status.code.language` 反映主语言；`findings[].evidence.location` 使用可解析前缀（如 `python:sink:eval`）。
- 可测：分类、各语言样例 fixture、pytest 绿。

## Non-goals

- 本迭代不引入 YARA 规则包与沙箱（可后续独立交付）。
- 不要求各语言完整 AST（JSP/ASPX 以高信号模式 + 片段证据为主，与当前 PHP 模块一致）。

## Success metrics

- 四种语言各至少 **1** 个可自动验收的正例（高危 sink 被检出且 `ast_sink` 信号存在）。
- 现有 `web-security-semantic-pipeline` 相关测试不回归。

## Dependencies

- `app/tools/web_security/*` 既有管线与 `cap_high_critical` 规则。

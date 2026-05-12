# Proposal: YARA + dynamic sandbox layers for `detect_web_attack`

## Problem

`detect_web_attack` 已有 **L2 多语言静态 sink** 与弱正则，但缺少与既定架构一致的 **L1 YARA 规则层**（可随 skill 发布）与 **L3 动态沙箱（解释器级）** 证据，难以形成完整证据链。

## Goals

- **L1 — YARA**：从 **磁盘绝对路径** 加载 `subagents/official/web-security/skills/web-security/yara/*.yar`，对输入 UTF-8 字节扫描；命中产出带 `rule_ref` 的 finding。
- **L1b — 熵（可选弱信号）**：对大段连续高熵片段给出 **info/low** 级 pattern 类发现，不单独抬到 critical。
- **L2 — 静态**：保持现有 per-language sink 扫描（不变更语义，仅标记 `layer=L2`）。
- **L3 — 动态沙箱**：对 **PHP / Python** 在受控子进程中运行 **语法级** 检查（`php -l`、`python -m py_compile`），**不执行**用户代码语义；记录 stdout/stderr 摘要到 `parse_status` 与（仅失败时）finding。
- **合约**：`Finding` 带 `layer` + `signals` 含 `yara_rule` / `sandbox_trace`；`cap_high_critical` 将 YARA/沙箱与 `ast_sink` 同等视为「结构化证据」门槛。

## Non-goals

- 不在本交付内实现 **JSP/Java bytecode** 或 **C#** 的完整 detonation。
- 不在 API 服务进程内 **eval 用户样本**。

## Success metrics

- 规则目录存在且可被编译；YARA 不可用时降级明确（`parse_status`/`layers`）。
- pytest 覆盖 YARA 命中、沙箱成功/失败路径；无 YARA 库时跳过或降级测试。

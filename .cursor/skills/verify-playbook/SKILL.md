---
name: verify-playbook
description: 验证 Playbook 执行的完整性、正确性和一致性。当用户说"验证 playbook"、"verify playbook"、"检查 playbook 执行"、"playbook 验收"、"check playbook"时触发，用于校验 IMPL-PLAYBOOK 是否已被正确执行。
---

# 验证 Playbook

读取 IMPL-PROGRESS.md + IMPL-PLAYBOOK.md + SPEC.md + 源代码 + git log，生成三维验证报告。

**输入**：可选指定 spec 目录路径。若未指定，搜索 `specs/*/IMPL-PLAYBOOK.md` 或 `IMPL-PLAYBOOK.md` 模式自动定位。

## 步骤

### 1. 定位并加载产物

找到 spec 目录。所需文件：

| 文件 | 必需 | 用途 |
|------|------|------|
| IMPL-PROGRESS.md | 是 | 批次完成状态 |
| IMPL-PLAYBOOK.md | 是 | 批次卡、⛔ 范围、AC 表、FR 索引 |
| SPEC.md | 是 | 原始 FR/AC/NFR，用于正确性校验 |
| DESIGN.md | 否 | ADR 交叉引用 |
| IMPL-GUIDE.md | 否 | NFR 验证方法、测试策略 |

若 IMPL-PROGRESS.md 或 IMPL-PLAYBOOK.md 缺失，终止并给出明确错误。

### 2. 解析结构

从 **IMPL-PROGRESS.md** 提取：
- 每行批次：批次 ID、状态（✅/🔧/⏸️/❌/空）、AC 通过率、已通过 AC、备注

从 **IMPL-PLAYBOOK.md** 提取：
- FR → 批次索引表（FR、批次、验证类型、主源文件）
- 路径约定表（cwd、别名 → 完整路径映射）
- 每张批次卡：批次 ID、FR/AC 范围、⛔ 范围（允许修改的文件）、④.5 前向声明

从 **SPEC.md** 提取：
- 所有 FR ID 及其 AC
- NFR 列表及验证方法
- 假设列表

### 3. 验证完整性（Completeness）

**3a. 批次完成度**

逐批次检查 PROGRESS 中的状态：
- 状态为 ✅？若否，按类型记录严重级别：
  - C 批次未 ✅ → CRITICAL："批次 Cx 未完成（状态：<status>）"
  - P/F/S 批次未 ✅ → 按状态分级：
    - ❌ 阻塞 → CRITICAL
    - ⏸️ 暂停 / 🔧 进行中 / 空 → WARNING
    - R 批次为空 → SUGGESTION（R 为可选）

**3b. AC 通过率**

对每个状态为 ✅ 的 C 批次：
- AC 通过率应为 N/N（100%）。若不是：
  - CRITICAL："批次 Cx 标记为 ✅ 但 AC 通过率为 M/N"
- 检查"已通过 AC"列：是否为 `all` 或列出了全部 AC？与批次卡中的 AC 数量交叉核对。

**3c. FR 覆盖率**

- 列出 SPEC.md 中所有 FR ID
- 逐个确认是否出现在 FR → 批次索引表中
- 缺失的 FR → CRITICAL："FR-xx 未分配批次"
- FR 已分配批次但批次未 ✅ → 已被 3a 覆盖

**3d. 阻塞/暂停清单**

- 列出所有 ❌ 和 ⏸️ 批次及其备注
- 各自 → CRITICAL（❌）或 WARNING（⏸️），附记录的原因

### 4. 验证正确性（Correctness）

**4a. AC 抽查（抽样校验）**

对每个已完成的 C 批次（尽量全部覆盖，最少 2 个批次）：
- 读取批次卡，选取 2 条 AC（优先选择"单测"验证类型的 AC）
- 读取 ⛔ 范围内的源文件
- 读取 SPEC.md 中对应的 AC 原文
- 评估：源代码是否实际满足该 AC 的意图？
- 有偏差 → WARNING："批次 Cx, FR-xx AC-y：实现可能不满足'<AC 摘要>'。见 `<file>:<line-range>`"
- 无法判断 → WARNING（非 CRITICAL），标注不确定性

启发式规则：
- "单测" AC：检查是否存在断言该 AC 行为的测试
- "代码审查" AC：检查 AC 描述的代码模式是否存在
- "Prompt 行为" AC：跳过代码检查，交由 4c 处理
- "配置审查" AC：检查配置值是否存在

**4b. NFR/假设验证（F1 完成标志）**

- 若 F1 批次在 PROGRESS 中为 ✅ → 检查 NFR 验证是否有证据：
  - 在源文件/测试文件中搜索 NFR 相关模式（如超时值、递归限制）
  - 若 IMPL-GUIDE.md 有 NFR 验证方法，检查是否逐条落实
- 若 F1 未 ✅ → WARNING："F1 未完成 — NFR/假设验证待处理"
- 缺少 NFR 验证证据 → 每条 NFR 一个 WARNING

**4c. Prompt 验证交叉引用**

- 若 P1 批次存在且为 ✅：
  - 检查 F-manual 是否有"Prompt 行为专项验证"表
  - P1 中每条 ⚠️（仅靠 Prompt）的条目应在 F-manual 验证表中有对应行
  - 缺少对应 → WARNING："P1 条目 'FR-xx AC-y' 在 F-manual 中无对应验证记录"
- 若 P1 不适用（无 Prompt FR）→ 跳过

### 5. 验证一致性（Coherence）

**5a. Git Commit 对齐**

在项目目录运行 `git log --oneline`。对每个已完成的 C 批次：
- 搜索提及批次 ID 的 commit（如 "C1"、"Batch: C1"、"FR-xx"）
- 无匹配 commit → WARNING："批次 Cx 无对应 git commit"
- commit 消息格式各异；灵活搜索批次 ID、FR ID 或批次标题关键词

**5b. Commit 范围对齐**

对每个已识别 commit（或 commit 范围）的批次：
- 运行 `git show --name-only <commit>` 或 `git diff --name-only <commit>~1 <commit>`
- 将修改的文件与该批次的 ⛔ 范围比对
- 修改了 ⛔ 范围外的文件 → WARNING："批次 Cx commit 修改了 ⛔ 范围外的 `<file>`"
- 使用路径约定表将别名解析为完整路径

**5c. 跨批次接口验证**

对有 ④.5 前向声明的批次：
- 提取声明的接口（函数/类名）
- 在下游批次的源文件中搜索这些接口的实际使用
- 声明了但下游未使用 → WARNING："批次 Cx 前向声明了 `<interface>` 但下游未实际调用"
- 使用了但未声明 → SUGGESTION："批次 Cy 使用了 Cx 的 `<interface>` 但 Cx ④.5 未声明它"

### 6. 生成报告

**总结计分卡：**

```text
## Playbook 验证报告: <spec-dir-name>

### 总结
| 维度 | 状态 | 详情 |
|------|------|------|
| 完整性 | X/Y 批次 ✅ | Z 个 FR 已覆盖，W 个 AC 问题 |
| 正确性 | M/N 抽查通过 | NFR：状态，Prompt：状态 |
| 一致性 | A/B commit 对齐 | C 个范围问题，D 个接口问题 |

总评：<通过 / 有警告通过 / 未通过>
```

**按优先级列出问题：**

1. **CRITICAL**（必须修复）：
   - 未完成的 C 批次
   - AC 通过率不匹配
   - FR 覆盖缺失
   - ❌ 阻塞的批次
   - 每条附具体、可操作的修复建议

2. **WARNING**（应当修复）：
   - AC 抽查发现的偏差
   - 缺少 NFR 验证证据
   - commit 范围越界
   - 未被下游使用的前向声明
   - P1/F-manual 交叉引用缺失
   - ⏸️ 暂停的批次
   - 每条附 file:line 引用（如适用）

3. **SUGGESTION**（建议修复）：
   - 缺少 git commit（可能已被 squash）
   - 未声明的跨批次接口依赖
   - 可选的 R 批次未完成
   - 每条附具体建议

**最终评定：**

- CRITICAL > 0："发现 X 个关键问题。Playbook 执行不完整 — 修复后再继续。"
- 仅有 WARNING："无关键问题。Y 个警告待处理。执行基本完成。"
- 全部通过："所有检查通过。Playbook 执行验证通过。"

## 验证启发式

- **完整性**：客观判定 — 解析 PROGRESS 表，每批次二元通过/未通过
- **正确性**：抽样校验 — 抽查 ≥2 个 C 批次，每批次 ≥2 条 AC；不要求完全确定
- **一致性**：尽力而为 — git log 解析是模糊的；不确定时优先 WARNING 而非 CRITICAL
- **误报控制**：不确定时，SUGGESTION > WARNING > CRITICAL
- **可操作性**：每个问题必须附具体建议，含文件路径或批次 ID
- **语言**：报告语言与 PLAYBOOK/SPEC 语言一致（遵循已有惯例）

## 降级策略

| 场景 | 行为 |
|------|------|
| PROGRESS 存在但为空（无状态填写） | 报告所有批次为未完成；跳过正确性/一致性检查 |
| 无 git 仓库或无 commit | 跳过一致性 §5a/5b，标注"git 历史不可用" |
| 无 SPEC.md | 跳过正确性 §4a 的 AC 原文对比，改用批次卡中的 AC 摘要 |
| 无 P1/Prompt 批次 | 跳过 §4c |
| 无 F-manual | 跳过 §4c 中的 F-manual 交叉引用 |
| 仅部分批次完成 | 验证已完成批次，将其余列为未完成 |

## 输出格式

使用清晰的 markdown：
- 表格呈现总结计分卡
- 分组列表呈现问题（CRITICAL / WARNING / SUGGESTION）
- 代码引用格式：`file.py:123` 或 `file.py`（函数名）
- 批次引用格式："批次 Cx"，链接到 PLAYBOOK 对应章节
- 具体、可操作的建议 — 不接受"请检查"式模糊表述

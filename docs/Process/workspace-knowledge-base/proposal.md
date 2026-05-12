# Proposal — Workspace 知识库（专业任务报告归档）

## 问题

专业安全 / 研究类任务会产生可长期复用的报告，但目前缺少统一归档入口；用户无法在固定位置回顾历史报告，也不便与后续「自有知识文件」能力衔接。

## 目标

1. 在应用侧栏提供固定的「知识库」入口，进入独立页面浏览内容。
2. 将**每次专业任务**（与产品内「专业子 Agent」任务一致：后端 `stats.taskKind` 为 `security` 或 `research` 的分析回合）完成时所产生报告，**自动生成 Word（.docx）** 并写入当前用户隔离的存储区。
3. 物理存储：磁盘 **硬编码** 为 **`{upload_dir}/knowledge/<用户 id>/`**（目录名 `knowledge`）；对用户展示为 `Workspace/knowledge/` 下逻辑路径。
4. **本版本不支持**用户上传自有知识文件（仅预留后续接入点，见非目标）。

## 非目标（本版本明确不做）

- 用户上传、删除、重命名知识文件的完整文件管理（可作为下一版）。
- 在知识库内全文检索、向量语义搜索（若需可另开交付）。
- 修改专业任务本身模型或子 Agent 编排（仅消费「任务已完成 + 报告可用」的现有时机）。

## 用户与场景

- **已登录用户**：完成一次专业类分析后，可在知识库中看到新增 .docx；侧栏随时进入知识库列表。
- **未登录 / 仅 session**：本版本以「已登录」为主；匿名知识落盘策略在 `design.md` 中明确（建议：不写入知识库或仅本地提示，以免无法关联用户 id）。

## 范围与依赖

- **前端：** `ProjectSidebar` 导航、`App.tsx` 路由、知识库列表页、与现有 `docx-export` / 报告归一化链路对接。
- **后端：** 认证用户 id；落盘 **`{upload_dir}/knowledge/<user_id>/`**（与其它上传树根并列）；提供列表与接收归档文件的 API。
- **依赖：** 现有 `normalizeReportDocument`、`export`/`docx-export` 能力与 `TaskStatsMeta.taskKind` 判定。

## 成功指标

- 专业任务完成后，对应用户知识库中出现一条可下载或可定位的 .docx（相同内容可与当前报告导出观感一致）。
- 侧栏在所有支持侧栏的 Workspace 布局下可见「知识库」项，且路由可 deep link。

## 术语对齐

- **专业任务**：本仓库内与「专业子 Agent」报告栏一致，以 `taskKind ∈ { security, research }` 为判据（见 `streamingConclusionForChat.ts`、`reportDocument.ts`、`TaskStatsBar` 等）。

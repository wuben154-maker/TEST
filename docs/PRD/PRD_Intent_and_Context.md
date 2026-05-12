# 智能意图识别与上下文关联 (Intent Understanding & Context)

## 📋 文档信息

- **文档版本**: 2.1.0
- **创建日期**: 2026.02.03
- **最后更新**: 2026.03.02
- **文档状态**: 已对齐当前实现（持续演进）
- **所属模块**: SecManus Workspace 核心能力层
- **文档负责人**: Intent & Context 模块团队

---

## 📖 目录

- [1. 需求概述](#1-需求概述)
- [2. 功能范围](#2-功能范围)
- [3. 核心能力详解](#3-核心能力详解)
- [4. 技术架构](#4-技术架构)
- [5. 数据模型](#5-数据模型)
- [6. 交互流程](#6-交互流程)
- [7. 接口定义](#7-接口定义)
- [8. 异常处理](#8-异常处理)
- [9. 性能要求](#9-性能要求)
- [10. 验收标准](#10-验收标准)
- [11. 附录](#11-附录)
- [12. 优化计划与待实现功能](#12-优化计划与待实现功能)
- [13. 当前实现对齐（2026-03）](#13-当前实现对齐2026-03)

---

## 1. 需求概述

### 1.1 背景与目标

**背景**:
SecManus Workspace 作为安全分析平台，需要理解用户多样化的输入需求。用户可能以自然语言、文件上传或混合形式提交分析请求，且需求可能跨越多个会话持续演化。

**目标**:
构建一个智能化的意图识别与上下文关联系统，能够：
- 精准理解用户输入的任何需求（文本、文件、混合输入）
- 智能关联历史会话上下文（短期记忆+长期记忆）
- 在需要时主动与用户交互获取必要信息
- 返回简洁、准确的意图理解结果，引导后续分析流程

### 1.2 用户价值

| 用户场景 | 痛点 | 解决方案 |
|---------|------|---------|
| SOC分析师处理告警 | 需要多次输入相似信息 | 自动关联历史上下文，记住分析偏好 |
| 安全研究员深度分析 | 分析过程跨越多个会话 | 长期记忆保存研究进展和关键发现 |
| 事件响应快速处置 | 需要频繁输入API密钥等参数 | 参数加密存储，一次输入多次使用 |
| 非安全领域用户 | 不确定系统能做什么 | 清晰的能力边界提示和引导 |

### 1.3 设计原则

1. **简洁性原则**: 返回给用户的意图理解结果必须简洁明了（<100字）
2. **渐进式理解**: 采用两阶段理解流程，必要时增强上下文
3. **隐私优先**: 敏感参数加密存储，用户完全可控
4. **透明性**: 意图识别过程可视化，用户可查看推理链路
5. **容错性**: 模糊意图通过提问澄清，而非直接拒绝

---

## 2. 功能范围

### 2.1 功能边界

**包含范围**:
- ✅ 多模态输入解析（文本 + 多文件）
- ✅ 意图识别与分类（安全/研究/未知）
- ✅ 上下文关联（短期记忆 + 长期记忆）
- ✅ 人机协作参数收集
- ✅ 文件类型检测与预处理
- ✅ 两阶段意图理解（初步分类 + 上下文增强）

**不包含范围**（由其他模块处理）:
- ❌ 具体的安全分析执行（由子智能体处理）
- ❌ 深度研究的信息收集（由研究智能体处理）
- ❌ 分析报告生成（由报告模块处理）

### 2.2 功能矩阵

| 功能 | P0(必需) | P1(重要) | P2(增强) | 状态 |
|-----|---------|---------|---------|------|
| 文本输入理解 | ✅ | - | - | 已实现 |
| 单文件上传解析 | ✅ | - | - | 已实现 |
| 多文件批量解析 | ✅ | - | - | 已实现 |
| 混合输入解析 | ✅ | - | - | 已实现 |
| 安全类文件识别 | ✅ | - | - | 已实现 |
| 非安全类文件识别 | ✅ | - | - | 已实现 |
| 短期记忆（当前会话） | ✅ | - | - | 已实现 |
| 长期记忆（跨会话） | - | ✅ | - | 已实现 |
| 参数请求与加密存储 | - | ✅ | - | 已实现 |
| 两阶段意图理解 | - | - | ✅ | 已实现 |
| 意图置信度评估 | - | - | ✅ | 已实现 |
| 多语言支持（中英日韩） | - | - | ✅ | 已实现 |
| 意图歧义澄清 | - | - | ✅ | 待完善 |
| 个性化偏好学习 | - | - | - | ✅ 规划中 |
| 意图预测（主动建议） | - | - | - | ✅ 规划中 |
| 高级文件类型解析（pcap/elf/压缩文件等） | - | ✅ | - | ⚠️ 待实现 |
| 大文件智能采样策略 | - | ✅ | - | ⚠️ 待实现 |
| 长期记忆向量检索（pgvector） | - | ✅ | - | ⚠️ 待实现 |
| 参数加密存储验证（AES-256） | ✅ | - | - | ⚠️ 待验证 |
| 性能监控与指标追踪 | - | - | ✅ | ⚠️ 待实现 |
| 配置文件管理（YAML） | - | - | ✅ | ⚠️ 待实现 |
| 上下文摘要增强 | - | - | ✅ | ⚠️ 待实现 |
| 文件类型检测增强（python-magic） | - | - | ✅ | ⚠️ 待实现 |
| 置信度阈值配置化 | - | - | ✅ | ⚠️ 待实现 |

---

## 3. 核心能力详解

### 3.1 多模态输入解析 (Input Parsing)

#### 3.1.1 支持的输入类型

**文本输入**:
- 自然语言描述（任意长度）
- 结构化数据（JSON、CSV、XML）
- 代码片段
- 日志文本
- 邮件原文

**文件输入**:

| 文件类型 | MIME类型/扩展名 | 处理策略 | 安全相关性 |
|---------|----------------|---------|-----------|
| 邮件文件 | .eml, .msg | 解析头部+正文+附件 | 高 |
| 网络数据包 | .pcap, .pcapng | 提取元数据+关键帧 | 高 |
| Windows可执行文件 | .exe, .dll, .sys | 计算哈希+元数据 | 高 |
| Linux可执行文件 | ELF格式 | 计算哈希+元数据 | 高 |
| Web文件 | .php, .jsp, .asp, .aspx | 代码分析+Webshell检测 | 高 |
| 日志文件 | .log, .txt | 格式检测+关键行提取 | 中 |
| JSON文件 | .json | 结构化解析 | 中 |
| CSV文件 | .csv | 表格解析 | 中 |
| 压缩文件 | .zip, .rar, .7z | 解压+递归分析 | 中 |
| 图片文件 | .png, .jpg, .gif | OCR提取（如含文字） | 低 |
| 文档文件 | .pdf, .docx | 文本提取 | 低 |

#### 3.1.2 文件解析策略

```python
# 解析流程
1. 文件接收 -> 计算MD5/SHA256哈希
2. MIME类型检测 -> 基于magic number + 扩展名
3. 内容预处理 -> 文本/二进制分流
4. 格式识别 -> 邮件/日志/代码/数据
5. 元数据提取 -> 大小、编码、关键字段
6. 内容摘要生成 -> 前N行/关键段落
```

#### 3.1.3 大文件处理

| 文件大小 | 处理策略 |
|---------|---------|
| < 1MB | 完整解析 |
| 1-10MB | 智能采样（头部+关键段落+尾部） |
| 10-100MB | 结构分析+分块读取 |
| > 100MB | 元数据提取+用户确认 |

### 3.2 意图识别 (Intent Recognition)

#### 3.2.1 任务分类体系

```
任务类别 (TaskCategory)
├── SECURITY (安全分析)
│   ├── EMAIL_ANALYSIS (邮件安全分析)
│   ├── MALWARE_ANALYSIS (恶意软件分析)
│   ├── WEB_ATTACK (Web攻击分析)
│   ├── SOC_ALERT (SOC告警分析)
│   ├── VULN_SCAN (漏洞扫描分析)
│   ├── IOC_LOOKUP (IOC查询)
│   └── GENERIC_SECURITY (通用安全分析)
├── RESEARCH (深度研究)
│   ├── TOPIC_RESEARCH (主题研究)
│   ├── THREAT_RESEARCH (威胁研究)
│   └── TECH_RESEARCH (技术研究)
├── PARAMETER_NEEDED (需要参数)
└── UNKNOWN (未知/不支持)
```

#### 3.2.2 意图识别触发词

| 任务类型 | 触发词示例 |
|---------|-----------|
| 邮件分析 | "分析这封邮件", "这是钓鱼邮件吗", "eml文件", "邮件附件" |
| 恶意软件分析 | "分析这个exe", "是不是病毒", "二进制文件", "恶意软件" |
| Webshell检测 | "这是webshell吗", "php文件分析", "后门检测" |
| 告警分析 | "分析这条告警", "SIEM告警", "安全事件" |
| IOC查询 | "查一下这个IP", "域名信誉", "文件哈希查询" |
| 漏洞研究 | "CVE-2024", "漏洞详情", "漏洞利用" |
| 威胁研究 | "APT组织", "威胁情报", "攻击团伙" |
| 通用研究 | "研究一下", "深度分析", "调研" |

#### 3.2.3 两阶段理解流程

```
阶段1: 初步理解 (Phase 1)
├── 输入: 
│   ├── 用户原始输入（文本 + 文件）
│   ├── 文件元数据（文件名、类型、大小、哈希等）
│   └── 短期记忆上下文（当前会话最近20条交互的摘要）
│       ⚠️ 注意：阶段1仅加载短期记忆，不加载长期记忆
├── 处理: 快速分类 + 置信度评估
├── 输出: 初步类别 + 是否需要更多上下文
└── 决策: 高置信度(>=0.7) -> 直接返回；低置信度(<0.7) -> 进入阶段2

阶段2: 上下文增强 (Phase 2) [可选]
├── 触发条件: 阶段1置信度<0.7 或 明确需要更多信息
├── 增强操作（外部工具，非记忆检索）:
│   ├── Web搜索 (威胁情报/CVE信息)
│   ├── URL抓取 (分析可疑链接)
│   ├── 文件深度读取 (解析大文件关键内容)
│   └── 文件结构分析 (提取文件特征)
├── 处理: 基于增强上下文重新理解（仍使用短期记忆 + 新增外部信息）
└── 输出: 最终意图结果
```

**记忆加载策略说明**:
- **阶段1**: 仅加载**短期记忆**（当前会话的最近20条交互），用于快速理解当前对话上下文
- **阶段2**: 继续使用短期记忆，同时通过外部工具（web_search、scrape_url等）获取额外信息
- **长期记忆**: 主要用于跨会话的场景，在意图理解阶段暂不使用，但在后续分析阶段可能会被调用

### 3.3 上下文关联 (Context Association)

#### 3.3.1 记忆层级

```
记忆层级
├── 短期记忆 (Short-term Memory)
│   ├── 存储位置: 内存 (per-session)
│   ├── 保留数量: 最近20条交互
│   ├── 内容类型: 用户输入、意图结果、关键实体
│   └── 生命周期: 会话期间
│
└── 长期记忆 (Long-term Memory)
    ├── 存储位置: PostgreSQL (Supabase)
    ├── 命名空间:
    │   ├── memories/{session_id} - 会话相关记忆
    │   └── parameters/{session_id} - 加密参数
    ├── 保留策略: 永久（直到用户删除）
    ├── 内容类型: 分析结论、用户偏好、加密参数
    └── 检索方式: 向量相似度 + 关键词匹配
```

#### 3.3.2 上下文使用场景

| 场景 | 上下文应用 | 示例 |
|-----|-----------|------|
| 指代消解 | "分析这个" -> 关联上一个文件 | 用户先上传文件，后续说"分析一下这个" |
| 任务延续 | 继续之前的分析方向 | "刚才分析的邮件，再深入看下附件" |
| 参数复用 | 自动填充历史参数 | 使用上次输入的VirusTotal API Key |
| 偏好记忆 | 记住用户习惯 | 用户偏好英文输出，后续自动使用英文 |
| 结论关联 | 引用之前分析结果 | "结合上次的分析结论，这次..." |

#### 3.3.3 上下文摘要生成

```python
# 用于LLM的上下文摘要格式
会话历史:
- 用户输入: [简要描述最近5次用户输入]
- 意图: [类别] - [简要结果]
- 关键实体: [提取的IOC、文件名等]
- 已分析文件: [文件列表]
- 用户偏好: [语言、输出格式等]
```

### 3.4 人机协作 (Human-in-the-Loop)

#### 3.4.1 参数请求场景

| 场景 | 参数示例 | 存储方式 |
|-----|---------|---------|
| 第三方API调用 | VirusTotal API Key | 加密存储 |
| 外部系统集成 | SIEM接口地址+认证信息 | 加密存储 |
| 分析配置 | 扫描深度、超时时间 | 明文存储 |
| 用户偏好 | 输出语言、报告格式 | 明文存储 |

#### 3.4.2 参数请求流程

```
1. 意图识别发现需要外部参数
   ↓
2. 生成参数请求描述
   ├── 参数名称
   ├── 参数类型 (text/password/url/json)
   ├── 参数说明
   ├── 是否必填
   └── 是否加密存储
   ↓
3. 返回 PARAMETER_NEEDED 类别
   ↓
4. 前端渲染参数输入表单
   ↓
5. 用户输入参数
   ↓
6. 后端验证 + 存储（加密参数使用AES-256）
   ↓
7. 重新触发意图识别（携带新参数）
   ↓
8. 进入正常分析流程
```

#### 3.4.3 参数管理

```python
# 参数存储结构
{
    "id": "uuid",
    "name": "vt_api_key",
    "value": "<encrypted_value>",  # 加密存储
    "param_type": "password",
    "description": "VirusTotal API Key",
    "session_id": "session_uuid",
    "created_at": "2026-02-03T10:00:00Z",
    "last_used": "2026-02-03T12:00:00Z",
    "usage_count": 5
}
```

---

## 4. 技术架构

### 4.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     Intent Understanding Layer                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Input Parser │  │ Intent         │  │ Context      │         │
│  │              │  │ Classifier     │  │ Retriever    │         │
│  │ - Text       │  │                │  │              │         │
│  │ - File       │  │ - Phase 1      │  │ - Short-term │         │
│  │ - Multi-file │  │ - Phase 2      │  │ - Long-term  │         │
│  └──────┬───────┘  └───────┬──────┘  └───────┬──────┘         │
│         │                  │                  │                │
│         └──────────────────┼──────────────────┘                │
│                            ▼                                   │
│  ┌─────────────────────────────────────────────────────┐      │
│  │               Enrichment Tools                        │      │
│  │  - Web Search  - URL Scraper  - File Reader         │      │
│  └─────────────────────────────────────────────────────┘      │
│                            │                                   │
│                            ▼                                   │
│  ┌─────────────────────────────────────────────────────┐      │
│  │               Result Formatter                        │      │
│  │  - Summary Generator  - Confidence Scorer           │      │
│  │  - User Message Builder  - Event Converter            │      │
│  └─────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Storage Layer                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │  Memory Store    │  │  Parameter Store   │                    │
│  │  (PostgreSQL)    │  │  (PostgreSQL+AES)  │                    │
│  └──────────────────┘  └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件

#### 4.2.1 文件解析器 (FileParser)

**职责**: 识别文件类型，提取内容和元数据

**实现要点**:
- 使用 `python-magic` 或文件签名检测MIME类型（⚠️ 待实现：当前仅基于扩展名）
- 支持多种编码格式（UTF-8, UTF-16, Latin-1等）
- 大文件智能采样策略（⚠️ 待实现：当前仅使用max_lines限制）
- 安全文件与非安全文件差异化处理

**待实现功能**:
- ⚠️ 网络数据包解析（.pcap, .pcapng）：提取元数据+关键帧
- ⚠️ 可执行文件深度分析（.exe, .dll, .sys, ELF）：计算哈希+提取PE/ELF元数据
- ⚠️ Web文件分析（.php, .jsp, .asp, .aspx）：代码分析+Webshell检测
- ⚠️ 压缩文件处理（.zip, .rar, .7z）：解压+递归分析
- ⚠️ 图片OCR（.png, .jpg, .gif）：提取图片中的文字内容
- ⚠️ 文档文本提取（.pdf, .docx）：提取文档中的文本内容

#### 4.2.2 意图分类器 (IntentClassifier)

**职责**: 基于LLM进行两阶段意图理解

**实现要点**:
- 提示词模板化管理（从MASTER_AGENT.md加载）
- 支持工具调用模式（Function Calling）
- 多语言响应支持（通过language参数控制）
- 置信度阈值控制（默认0.7触发阶段2，⚠️ 待实现：应支持配置化）

**待实现功能**:
- ⚠️ 意图歧义澄清机制：当置信度<0.5且无法通过阶段2提升时，生成澄清问题
- ⚠️ 置信度阈值配置化：支持从配置文件加载，允许运行时动态调整

#### 4.2.3 上下文检索器 (ContextRetriever)

**职责**: 管理短期和长期记忆

**实现要点**:
- 短期记忆：内存字典，按session_id隔离
- 长期记忆：向量数据库（pgvector），支持语义检索（⚠️ 待实现：当前仅使用简单search）
- 自动摘要生成，控制LLM上下文窗口（⚠️ 待增强：当前摘要较简单）
- 记忆清理策略（短期记忆会话结束清理）

**记忆加载策略**:
- **意图理解阶段1**: 仅加载**短期记忆**（当前会话最近20条），用于快速理解当前对话上下文
- **意图理解阶段2**: 继续使用短期记忆，通过外部工具获取额外信息（不加载长期记忆）
- **长期记忆用途**: 主要用于跨会话场景，在意图理解阶段暂不使用，但在后续分析阶段可能会被调用

**待实现功能**:
- ⚠️ 向量相似度检索：使用pgvector的`vector_cosine_ops`进行语义搜索
- ⚠️ 向量嵌入生成：为长期记忆生成向量嵌入并存储
- ⚠️ 上下文摘要增强：提取关键实体、文件列表、用户偏好等信息
- ⚠️ 长期记忆在意图理解中的应用：考虑在阶段2中引入长期记忆的语义检索（可选增强）

#### 4.2.4 上下文增强工具 (ContextEnrichmentTool)

**职责**: 为阶段2提供额外的上下文信息

**工具列表**:
- `web_search`: DuckDuckGo搜索威胁情报
- `scrape_url`: 抓取可疑URL内容
- `read_file`: 深度读取上传的文件
- `analyze_file_structure`: 分析文件结构而不读取全部内容

---

## 5. 数据模型

### 5.1 核心数据结构

#### 5.1.1 文件信息 (FileInfo)

```python
@dataclass
class FileInfo:
    filename: str              # 原始文件名
    content_type: str          # MIME类型
    size: int                  # 文件大小(bytes)
    content: bytes | str       # 文件内容（二进制或文本）
    hash_md5: str              # MD5哈希
    hash_sha256: str           # SHA256哈希
    parsed_content: str        # 解析后的文本内容
```

#### 5.1.2 用户输入 (UserInput)

```python
@dataclass
class UserInput:
    text: str                  # 文本输入
    files: list[FileInfo]      # 文件列表
    timestamp: datetime        # 输入时间(UTC)
    session_id: str            # 会话ID
```

#### 5.1.3 意图结果 (IntentResult)

```python
@dataclass
class IntentResult:
    # 基本信息
    task_category: TaskCategory        # 任务类别
    input_type: InputType              # 输入类型
    confidence: float                  # 置信度(0-1)
    summary: str                       # 简洁摘要(<50字)
    
    # 详细信息
    key_entities: list[str]            # 关键实体(IP、域名、文件等)
    analysis_goals: list[str]          # 分析目标
    suggested_approach: str            # 建议的分析方法
    
    # 安全任务特定
    security_subtype: SecuritySubType   # 安全子类型
    threat_indicators: list[str]       # 威胁指标
    
    # 研究任务特定
    research_topic: str                # 研究主题
    research_scope: str                # 研究范围
    
    # 参数请求
    parameter_requests: list[ParameterRequest]
    
    # 两阶段理解
    enrichment_applied: bool           # 是否应用了增强
    enrichment_summary: str             # 增强摘要
    enrichment_sources: list[str]       # 增强内容来源
    understanding_phases: int           # 理解阶段数(1或2)
```

### 5.2 数据库表结构

#### 5.2.1 长期记忆表 (memories)

**用途**: 存储跨会话的长期记忆，支持语义检索和持久化存储

**设计特点**:
- **向量检索**: 包含 `vector VECTOR(1536)` 字段，支持基于语义相似度的检索
- **命名空间隔离**: 通过 `namespace` 字段区分 `memories/{session_id}` 和 `parameters/{session_id}`
- **访问统计**: 记录 `accessed_at` 和 `access_count`，用于优化检索策略
- **键值存储**: 采用 key-value 结构，支持灵活的存储格式

**存储内容**:
- 分析结论和关键发现（跨会话复用）
- 用户偏好设置（语言、输出格式等）
- 加密参数（API密钥等敏感信息）
- 研究进展和重要发现

**检索方式**:
- 向量相似度检索（通过 pgvector）
- 关键词匹配（通过 key 字段）
- 按 session_id 和 namespace 过滤

```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    namespace VARCHAR(255),           -- 命名空间(memories/parameters)
    key VARCHAR(255),                 -- 记忆键
    value TEXT,                       -- 记忆值(加密或明文)
    vector VECTOR(1536),              -- 向量嵌入(用于语义检索)
    metadata JSONB,                   -- 元数据
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    accessed_at TIMESTAMP,            -- 最后访问时间
    access_count INTEGER DEFAULT 0    -- 访问计数
);

CREATE INDEX idx_memories_session ON memories(session_id);
CREATE INDEX idx_memories_namespace ON memories(namespace);
CREATE INDEX idx_memories_vector ON memories USING ivfflat (vector vector_cosine_ops);
```

**使用场景示例**:
```python
# 保存分析结论到长期记忆
await context_retriever.save_to_long_term(
    session_id="session_123",
    key="analysis_conclusion_cve_2024_3094",
    value="CVE-2024-3094是xz工具包的后门漏洞，影响范围...",
    encrypted=False
)

# 语义检索相关记忆
related_memories = await context_retriever.get_long_term_context(
    session_id="session_123",
    query="xz backdoor vulnerability"
)
```

#### 5.2.2 会话上下文表 (session_context)

**用途**: 存储会话内的上下文序列，按时间顺序记录交互历史

**设计特点**:
- **序列化存储**: 通过 `sequence` 字段保证时间顺序
- **类型区分**: 通过 `context_type` 区分 `input`（用户输入）、`intent`（意图结果）、`result`（分析结果）
- **JSONB存储**: 使用 `content JSONB` 存储结构化数据，支持灵活查询
- **会话隔离**: 按 `session_id` 组织，每个会话独立

**存储内容**:
- 用户输入记录（文本、文件上传等）
- 意图理解结果（任务类别、置信度、摘要等）
- 分析结果摘要（关键发现、IOC等）

**检索方式**:
- 按 `session_id` 和 `sequence` 排序获取完整会话历史
- 按 `context_type` 过滤特定类型的上下文
- 按时间范围查询

```sql
CREATE TABLE session_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id),
    context_type VARCHAR(50),         -- 上下文类型(input/intent/result)
    content JSONB,                    -- 内容
    sequence INTEGER,                 -- 序列号(用于排序)
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_session_context_session ON session_context(session_id, sequence);
```

**使用场景示例**:
```python
# 保存用户输入到会话上下文
INSERT INTO session_context (session_id, context_type, content, sequence)
VALUES (
    'session_123',
    'input',
    '{"text": "分析这个文件", "files": ["suspicious.exe"]}',
    1
);

# 获取会话完整历史（按时间顺序）
SELECT * FROM session_context 
WHERE session_id = 'session_123' 
ORDER BY sequence ASC;
```

#### 5.2.3 两表对比

| 维度 | memories（长期记忆表） | session_context（会话上下文表） |
|-----|---------------------|------------------------------|
| **主要用途** | 跨会话的长期记忆存储 | 会话内的交互历史记录 |
| **存储方式** | Key-Value 结构 | 序列化时间线结构 |
| **检索方式** | 向量相似度 + 关键词 | 按序列号排序 |
| **数据特点** | 去重、聚合、摘要 | 完整、有序、详细 |
| **生命周期** | 永久（直到用户删除） | 可配置TTL或永久 |
| **典型内容** | 分析结论、用户偏好、参数 | 用户输入、意图结果、分析结果 |
| **使用场景** | 跨会话知识复用、语义检索 | 会话历史重建、上下文追溯 |
| **性能优化** | 向量索引、访问统计 | 序列索引、时间索引 |

**设计理念**:
- **memories表**: 面向"知识"的存储，强调语义关联和跨会话复用
- **session_context表**: 面向"历史"的存储，强调时间顺序和完整记录

**当前实现状态**:
- ⚠️ **memories表**: 已实现基础功能，向量检索功能待完善
- ⚠️ **session_context表**: 表结构已定义，但当前实现使用内存短期记忆，数据库持久化待实现

---

## 6. 交互流程

### 6.1 标准意图理解流程

```
用户输入
    │
    ▼
┌──────────────────────────────────────────┐
│ 1. 输入预处理                             │
│    - 文本清理                            │
│    - 文件上传处理                        │
│    - 计算文件哈希                        │
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│ 2. 短期记忆检索                           │
│    - 获取当前会话历史（最近20条）        │
│    - 生成上下文摘要                      │
│    ⚠️ 注意：仅加载短期记忆，不加载长期记忆│
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│ 3. 阶段1: 初步理解                        │
│    - 构建提示词(模板+短期记忆上下文+输入) │
│    - LLM分类(工具调用模式)               │
│    - 解析结果                            │
└──────────────────────────────────────────┘
    │
    ├── 高置信度(>=0.7) ──► 直接返回结果
    │
    └── 低置信度(<0.7)  ──► 进入阶段2
                              │
                              ▼
                    ┌──────────────────────────┐
                    │ 4. 上下文增强              │
                    │    - 执行查询列表          │
                    │    - 收集额外信息          │
                    └──────────────────────────┘
                              │
                              ▼
                    ┌──────────────────────────┐
                    │ 5. 阶段2: 重新理解        │
                    │    - 基于增强上下文        │
                    │    - LLM重新分类           │
                    └──────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────┐
│ 6. 结果格式化                             │
│    - 构建用户消息                        │
│    - 生成SSE事件                         │
│    - 保存到短期记忆                        │
└──────────────────────────────────────────┘
    │
    ▼
返回给用户
```

### 6.2 参数请求流程

```
意图识别发现需要参数
    │
    ▼
生成 ParameterRequest 列表
    │
    ▼
返回 TaskCategory.PARAMETER_NEEDED
    │
    ▼
前端渲染参数输入表单
    │
    ▼
用户输入参数值
    │
    ▼
后端验证参数格式
    │
    ▼
加密存储敏感参数
    │
    ▼
重新触发意图识别
    │
    ▼
携带参数继续分析
```

### 6.3 多轮对话流程

```
第1轮:
用户: "分析这个文件" + upload: suspicious.exe
系统: 🔒 检测到可执行文件，将进行恶意软件分析

第2轮:
用户: "使用VirusTotal查一下"
系统: 📝 需要提供VirusTotal API Key [显示输入框]

用户输入: <api_key>
系统: 🔒 已保存API Key，正在查询VirusTotal...

第3轮:
用户: "刚才那个文件的SHA256是多少"
系统: 🔒 您之前上传的suspicious.exe的SHA256是: a1b2c3d4...
(系统自动关联第1轮的文件)
```

---

## 7. 接口定义

### 7.1 内部API

#### 7.1.1 意图理解接口

```python
# 意图理解中间件入口
async def understand_intent(
    user_input: UserInput,
    session_id: str,
    context_retriever: ContextRetriever,
    on_phase_update: Optional[Callable] = None,
    language: str = "zh",
) -> IntentResult:
    """
    理解用户意图的主入口函数
    
    Args:
        user_input: 用户输入（文本+文件）
        session_id: 会话ID
        context_retriever: 上下文检索器实例
        on_phase_update: 阶段更新回调函数
        language: 响应语言 (zh/en/ja/ko)
    
    Returns:
        IntentResult: 意图理解结果
    """
```

#### 7.1.2 上下文检索接口

```python
class ContextRetriever:
    async def get_context_summary(self, session_id: str) -> str:
        """获取用于LLM的上下文摘要"""
    
    async def save_to_long_term(
        self, 
        session_id: str, 
        key: str, 
        value: Any,
        metadata: dict = None,
        encrypted: bool = False
    ):
        """保存到长期记忆"""
    
    async def get_long_term_context(
        self, 
        session_id: str, 
        query: str,
        limit: int = 10
    ) -> list[dict]:
        """语义检索长期记忆"""
```

### 7.2 SSE事件格式

**SSE (Server-Sent Events) 事件格式说明**:

SSE事件格式用于后端向前端实时推送意图理解过程中的状态更新和结果。通过HTTP长连接，后端可以持续发送事件流，前端通过EventSource API接收并实时更新UI。

**主要用途**:
1. **实时状态反馈**: 向用户展示意图理解的进度（阶段1开始、阶段2开始等）
2. **结果推送**: 将意图理解结果实时推送给前端，无需轮询
3. **参数请求**: 当需要用户输入参数时，通过事件通知前端显示参数输入表单
4. **过程可视化**: 让用户了解系统正在做什么（"正在分析文件..."、"正在检索上下文..."等）

**事件传输格式**:
```
data: {"type": "understanding", "id": "intent-understanding", ...}

```
前端通过 `EventSource` 监听 `/api/analyze/stream` 端点接收这些事件。

#### 7.2.1 意图理解事件

**字段定义**（接口规范）:

```json
{
  "event": "intent_understanding",
  "data": {
    "type": "intent_understanding",           // 固定值，标识事件类型
    "inputType": "<text|email|log|code|binary|image|document|mixed>",  // 输入类型枚举
    "summary": "<string>",                    // 简洁摘要（<50字），用户语言
    "keyEntities": ["<string>", ...],         // 关键实体列表（IP、域名、文件名等）
    "analysisGoals": ["<string>", ...],       // 分析目标列表
    "suggestedApproach": "<string>",          // 建议的分析方法
    "confidence": <0.0-1.0>,                  // 置信度（浮点数）
    "taskCategory": "<security|research|parameter_needed|unknown>",  // 任务类别
    "securitySubtype": "<string|null>",        // 安全子类型（仅security类别时有效）
    "researchTopic": "<string|null>",         // 研究主题（仅research类别时有效）
    "parameterRequests": [<ParameterRequest>, ...],  // 参数请求列表（空数组表示不需要参数）
    "enrichmentApplied": <boolean>,           // 是否应用了上下文增强
    "enrichmentSummary": "<string>",          // 上下文增强摘要
    "understandingPhases": <1|2>               // 理解阶段数（1=仅阶段1，2=包含阶段2）
  }
}
```

**实际示例**（便于理解）:

```json
{
  "event": "intent_understanding",
  "data": {
    "type": "intent_understanding",
    "inputType": "mixed",
    "summary": "检测到可执行文件，将进行恶意软件分析",
    "keyEntities": ["suspicious.exe", "SHA256: abc123..."],
    "analysisGoals": ["检测恶意软件特征", "提取IOC指标"],
    "suggestedApproach": "使用静态分析+威胁情报查询",
    "confidence": 0.92,
    "taskCategory": "security",
    "securitySubtype": "malware_analysis",
    "researchTopic": null,
    "parameterRequests": [],
    "enrichmentApplied": false,
    "enrichmentSummary": "",
    "understandingPhases": 1
  }
}
```

**说明**:
- 上述示例展示了一个**真实场景**下的数据格式，便于开发者理解各字段的实际含义
- 实际运行时，`summary`、`keyEntities` 等字段的值由 LLM 根据用户输入动态生成
- 所有字符串字段的内容都是**动态生成**的，示例中的中文描述仅用于说明格式

#### 7.2.2 参数请求事件

**字段定义**（接口规范）:

```json
{
  "event": "intent_understanding",
  "data": {
    "type": "intent_understanding",
    "inputType": "<text|email|log|code|binary|image|document|mixed>",
    "summary": "<string>",                    // 参数请求的简要说明
    "taskCategory": "parameter_needed",       // 固定值，标识需要参数
    "parameterRequests": [
      {
        "id": "<uuid>",                       // 参数请求的唯一标识
        "name": "<string>",                   // 参数名称（用于后端存储）
        "description": "<string>",            // 参数说明（用户语言）
        "paramType": "<text|password|url|json>",  // 参数类型
        "required": <boolean>,                // 是否必填
        "placeholder": "<string>",            // 输入框占位符文本
        "encrypted": <boolean>                // 是否加密存储
      }
    ]
  }
}
```

**实际示例**（便于理解）:

```json
{
  "event": "intent_understanding",
  "data": {
    "type": "intent_understanding",
    "inputType": "text",
    "summary": "需要提供外部API参数",
    "taskCategory": "parameter_needed",
    "parameterRequests": [
      {
        "id": "uuid-1",
        "name": "vt_api_key",
        "description": "VirusTotal API Key，用于查询文件信誉",
        "paramType": "password",
        "required": true,
        "placeholder": "输入您的VirusTotal API Key",
        "encrypted": true
      }
    ]
  }
}
```

**说明**:
- 当 `taskCategory` 为 `parameter_needed` 时，前端应渲染参数输入表单
- `parameterRequests` 数组中的每个对象对应一个输入字段
- 用户提交参数后，前端需要调用参数提交API，然后重新触发意图理解

#### 7.2.3 阶段更新事件

```json
{
  "event": "thinking",
  "data": {
    "type": "thinking",
    "phase": "phase1_start",
    "message": "开始初步意图理解...",
    "files": ["suspicious.exe"]
  }
}
```

**阶段更新事件类型**:
- `phase1_start`: 阶段1开始
- `phase1_complete`: 阶段1完成
- `phase2_start`: 阶段2开始（上下文增强）
- `phase2_context_retrieved`: 上下文增强完成
- `phase2_complete`: 阶段2完成
- `understanding_complete`: 意图理解完成

#### 7.2.4 SSE事件格式总结

**事件类型映射**:

| 事件类型 | event字段 | 用途 | 触发时机 |
|---------|----------|------|---------|
| 意图理解结果 | `intent_understanding` | 推送意图理解结果 | 阶段1或阶段2完成后 |
| 参数请求 | `intent_understanding` | 通知前端显示参数输入表单 | 检测到需要参数时 |
| 阶段更新 | `thinking` | 展示意图理解进度 | 各阶段开始/完成时 |

**前端处理流程**:

```typescript
// 前端通过 EventSource 接收事件
const eventSource = new EventSource('/api/analyze/stream');

eventSource.addEventListener('intent_understanding', (e) => {
  const data = JSON.parse(e.data);
  // 更新UI显示意图理解结果
  updateIntentDisplay(data);
});

eventSource.addEventListener('thinking', (e) => {
  const data = JSON.parse(e.data);
  // 更新进度指示器
  updateProgressIndicator(data.phase);
});
```

**SSE事件格式的优势**:
1. **实时性**: 无需轮询，后端主动推送
2. **低延迟**: 事件立即传输，用户体验好
3. **单向通信**: 适合服务器向客户端推送状态更新
4. **自动重连**: EventSource API 支持自动重连机制
5. **流式传输**: 支持长连接，持续接收事件流

---

## 8. 异常处理

### 8.1 异常场景与处理策略

| 异常场景 | 处理策略 | 用户反馈 |
|---------|---------|---------|
| 文件解析失败 | 记录错误，跳过该文件，继续分析其他 | "文件X解析失败，将继续分析其他内容" |
| LLM调用超时 | 重试1次，仍失败则使用阶段1结果 | "分析超时，使用初步理解结果" |
| LLM返回格式错误 | 尝试解析，失败则返回UNKNOWN | "无法完全理解您的需求，请提供更多细节" |
| 上下文检索失败 | 降级为仅使用短期记忆 | 无感知降级 |
| 参数验证失败 | 提示重新输入 | "参数格式不正确，请重新输入" |
| 存储失败 | 重试1次，仍失败则仅内存存储 | 无感知降级 |

### 8.2 降级策略

```python
# 多级降级策略
def classify_with_fallback(user_input, context):
    try:
        # 正常两阶段理解
        return await two_phase_classify(user_input, context)
    except TimeoutError:
        # 降级1: 仅阶段1
        return await phase1_classify(user_input, context)
    except LLMError:
        # 降级2: 基于规则分类
        return await rule_based_classify(user_input)
    except Exception:
        # 最终降级: UNKNOWN
        return IntentResult(
            task_category=TaskCategory.UNKNOWN,
            summary="系统暂时无法处理您的请求"
        )
```

**待完善项**:
- ⚠️ 超时重试机制：LLM调用超时应自动重试1次
- ⚠️ 错误消息多语言支持：异常反馈应支持用户语言
- ⚠️ 降级策略监控：记录降级触发原因，便于优化

---

## 9. 性能要求

### 9.1 响应时间目标

| 操作 | P90目标 | P99目标 |
|-----|--------|--------|
| 阶段1理解 | < 3s | < 5s |
| 阶段2理解(含增强) | < 10s | < 15s |
| 上下文检索 | < 200ms | < 500ms |
| 文件解析(<1MB) | < 500ms | < 1s |
| 完整意图理解 | < 5s | < 10s |

### 9.2 资源限制

| 资源 | 限制 |
|-----|------|
| 短期记忆条目数 | 每会话最多20条 |
| 长期记忆检索 | 单次最多返回10条 |
| 上下文增强查询 | 单次最多5个查询 |
| 提示词长度 | 不超过8000 tokens |
| 文件解析大小 | 单次请求总大小不超过50MB |

---

## 10. 验收标准

### 10.1 功能验收

| 验收项 | 验收标准 | 测试方法 |
|-------|---------|---------|
| 意图识别准确率 | 安全/研究分类准确率 > 90% | 测试集验证 |
| 文件类型检测 | 支持的所有文件类型正确识别率 > 95% | 单元测试 |
| 上下文关联 | 指代消解准确率 > 80% | 人工评估 |
| 参数请求 | 正确识别需要参数的场景并生成请求 | 集成测试 |
| 多语言支持 | 中英日韩四种语言正确响应 | 多语言测试集 |

### 10.2 性能验收

| 验收项 | 验收标准 |
|-------|---------|
| 阶段1延迟 | 95%请求 < 3s |
| 整体延迟 | 95%请求 < 5s（无阶段2）或 < 10s（有阶段2） |
| 并发处理 | 支持10并发请求，响应时间增加 < 50% |
| 内存使用 | 单会话短期记忆 < 10MB |

### 10.3 安全验收

| 验收项 | 验收标准 |
|-------|---------|
| 参数加密 | 敏感参数必须使用AES-256加密 |
| 数据隔离 | 不同会话的记忆数据完全隔离 |
| 输入验证 | 所有用户输入必须经过验证和清理 |

---

## 11. 附录

### 11.1 提示词模板

#### 11.1.1 阶段1提示词

```markdown
## 角色
你是一个任务分类助手，分析用户的安全分析或研究意图。

## 上下文
{context}

## 用户输入
文本: {text}
文件: {files}

## 任务
1. 判断用户意图类别: security / research / parameter_needed / unknown
2. 检测输入类型: text / email / log / code / binary / image / document / mixed
3. 提取关键实体和分析目标
4. 评估置信度(0-1)
5. 判断是否**需要更多上下文**才能准确理解:
   - 如果看到CVE编号但没有详细信息 -> 需要web_search
   - 如果看到URL需要分析 -> 需要scrape_url  
   - 如果文件太大只解析了部分 -> 需要read_file
   - 如果不确定文件类型 -> 需要analyze_file_structure

## 输出格式
必须调用 classify_intent_phase1 函数，参数:
- task_category: 任务类别
- input_type: 输入类型
- confidence: 置信度
- summary: 简洁摘要（用户语言，<50字）
- needs_more_context: 是否需要更多上下文(true/false)
- context_queries: 如果需要，列出查询列表
- context_reasoning: 为什么需要更多上下文的解释

## 重要
- 必须使用{language}进行回复
- summary必须简洁，适合直接展示给用户
```

#### 11.1.2 阶段2提示词

```markdown
## 角色
你是一个任务分类助手，已有额外上下文信息。

## 原始请求
文本: {text}
文件: {files}

## 增强的上下文
{additional_context}

## 会话上下文
{context}

## 任务
基于增强的上下文，重新判断用户意图。

## 输出格式
必须调用 classify_intent 函数，参数:
- task_category: 任务类别
- input_type: 输入类型
- confidence: 置信度(应该比阶段1更高)
- summary: 简洁摘要
- key_entities: 关键实体列表
- analysis_goals: 分析目标列表
- suggested_approach: 建议方法
- enrichment_summary: 如何利用增强上下文改进了理解

## 重要
- 必须使用{language}进行回复
- 置信度应该比阶段1更高
```

### 11.2 配置文件示例

```yaml
# intent_config.yaml
intent_understanding:
  # 两阶段理解配置
  two_phase:
    enabled: true
    confidence_threshold: 0.7  # 触发阶段2的阈值
    max_enrichment_queries: 5
    enrichment_timeout: 10s
  
  # 分类配置
  classification:
    supported_languages: ["zh", "en", "ja", "ko"]
    default_language: "zh"
    max_retries: 1
  
  # 上下文配置
  context:
    short_term_limit: 20  # 短期记忆条目数
    long_term_retrieval_limit: 10
    context_window_size: 5  # 用于LLM的历史轮数
  
  # 文件处理配置
  file_processing:
    max_file_size: 50MB
    max_total_size: 100MB
    max_files_per_request: 10
    sampling_threshold: 1MB  # 超过此大小启用采样
  
  # 加密配置
  encryption:
    algorithm: "AES-256-GCM"
    key_rotation_days: 90
```

### 11.3 相关文档索引

| 文档 | 路径 | 说明 |
|-----|------|------|
| 整体PRD | docs/PRD/PRD.md | 产品整体需求 |
| 架构文档 | docs/ARCHITECTURE.md | 系统架构设计 |
| Master Agent提示词 | python-agent-service/app/prompts/MASTER_AGENT.md | LLM提示词定义 |
| 意图理解实现 | python-agent-service/app/middleware/intent_understanding.py | 代码实现 |
| 技能模块 | python-agent-service/skills/*/SKILL.md | 各技能描述 |

---

## 12. 优化计划与待实现功能

### 12.1 优化需求概述

基于当前实现代码与PRD需求的对比分析，识别出以下待优化和待实现的功能项。这些优化将进一步提升系统的能力、性能和用户体验。

### 12.2 优先级分类

#### P0 - 必须实现（安全相关）

| 优化项 | 当前状态 | 目标 | 影响 |
|-------|---------|------|------|
| **参数加密存储验证（AES-256）** | ⚠️ 待验证 | 确认敏感参数使用AES-256-GCM加密 | 安全合规性 |

**实施建议**:
- 检查 `StoreBackend` 在 `encrypted=True` 时是否真正使用 AES-256-GCM 加密
- 验证加密密钥管理机制（密钥轮换、安全存储）
- 添加加密验证的单元测试和集成测试

#### P1 - 重要功能（核心能力增强）

| 优化项 | 当前状态 | 目标 | 影响 |
|-------|---------|------|------|
| **高级文件类型解析** | ⚠️ 待实现 | 支持 pcap/elf/压缩文件/图片/文档等 | 功能完整性 |
| **大文件智能采样策略** | ⚠️ 待实现 | 按文件大小采用不同处理策略 | 性能优化 |
| **长期记忆向量检索** | ⚠️ 待实现 | 使用 pgvector 进行语义搜索 | 上下文关联准确性 |
| **数据库表结构实现** | ⚠️ 待验证 | 确认 memories 和 session_context 表完整实现 | 数据持久化 |

**实施建议**:

1. **高级文件类型解析**:
   - 扩展 `FileParser.parse_file()` 方法
   - 集成专用库：`pypcap`（网络包）、`pefile`（PE文件）、`pyelftools`（ELF文件）
   - 添加压缩文件解压逻辑（zipfile, rarfile, py7zr）
   - 集成 OCR 库（如 `pytesseract`）用于图片文字提取
   - 集成文档解析库（如 `PyPDF2`, `python-docx`）用于文档文本提取

2. **大文件智能采样策略**:
   ```python
   # 在 FileParser 中实现
   def _smart_sample(self, file_info: FileInfo) -> str:
       size_mb = file_info.size / (1024 * 1024)
       if size_mb < 1:
           return self._parse_full(file_info)
       elif size_mb < 10:
           return self._parse_sampled(file_info, head=1000, tail=1000, middle=500)
       elif size_mb < 100:
           return self._parse_structured(file_info)
       else:
           return self._parse_metadata_only(file_info)
   ```

3. **长期记忆向量检索**:
   - 在 `ContextRetriever.get_long_term_context()` 中实现向量相似度检索
   - 使用 OpenAI embeddings 或本地模型生成向量嵌入
   - 利用 pgvector 的 `vector_cosine_ops` 进行语义搜索
   - 添加向量索引优化查询性能

4. **数据库表结构验证**:
   - 检查 Supabase 迁移是否包含完整的表结构
   - 确认 `VECTOR(1536)` 字段和 `ivfflat` 索引已创建
   - 验证 `session_context` 表的序列号排序功能

#### P2 - 增强功能（体验优化）

| 优化项 | 当前状态 | 目标 | 影响 |
|-------|---------|------|------|
| **意图歧义澄清机制** | ⚠️ 待实现 | 低置信度时主动提问澄清 | 用户体验 |
| **性能监控与指标追踪** | ⚠️ 待实现 | 记录各阶段耗时，便于优化 | 可观测性 |
| **配置文件管理（YAML）** | ⚠️ 待实现 | 支持从配置文件加载参数 | 可维护性 |
| **上下文摘要增强** | ⚠️ 待实现 | 提取关键实体、文件列表、用户偏好 | 上下文质量 |
| **文件类型检测增强** | ⚠️ 待实现 | 使用 python-magic 基于 magic number 检测 | 准确性 |
| **置信度阈值配置化** | ⚠️ 待实现 | 支持从配置文件加载，允许动态调整 | 灵活性 |

**实施建议**:

1. **意图歧义澄清机制**:
   ```python
   # 在 IntentClassifier 中增加
   if confidence < 0.5 and not enrichment_applied:
       clarification_questions = self._generate_clarification_questions(
           user_input, phase1_result
       )
       return IntentResult(
           task_category=TaskCategory.PARAMETER_NEEDED,
           parameter_requests=[...],  # 包含澄清问题
       )
   ```

2. **性能监控与指标追踪**:
   - 在 `IntentUnderstandingMiddleware.understand()` 中添加性能计时
   - 记录：阶段1延迟、阶段2延迟、上下文检索时间、文件解析时间
   - 输出性能指标到日志或监控系统（如 Prometheus）

3. **配置文件管理**:
   - 创建 `intent_config.yaml` 配置文件
   - 在 `IntentUnderstandingMiddleware.__init__()` 中加载配置
   - 支持环境变量覆盖配置值

4. **上下文摘要增强**:
   ```python
   # 增强 ContextRetriever.get_context_summary()
   def get_context_summary(self, session_id: str) -> str:
       history = self.get_short_term_context(session_id)
       # 提取关键实体（IOC、文件名等）
       entities = self._extract_entities(history)
       # 提取已分析文件列表
       files = self._extract_files(history)
       # 提取用户偏好
       preferences = self._extract_preferences(history)
       # 生成增强摘要
       return self._format_enhanced_summary(history, entities, files, preferences)
   ```

5. **文件类型检测增强**:
   - 集成 `python-magic` 库进行 MIME 类型检测
   - 结合 magic number 和扩展名提高准确性
   - 处理文件类型伪装场景

6. **置信度阈值配置化**:
   - 将 `confidence_threshold` 设为可配置参数（默认 0.7）
   - 支持在配置文件中调整
   - 允许运行时动态调整（通过 API）

### 12.3 实施路线图

#### 第一阶段（1-2周）：P0 + 部分P1
- ✅ 参数加密存储验证
- ✅ 大文件智能采样策略
- ✅ 文件类型检测增强（python-magic）

#### 第二阶段（2-3周）：核心P1功能
- ✅ 高级文件类型解析（优先实现 pcap 和可执行文件）
- ✅ 长期记忆向量检索
- ✅ 数据库表结构验证与完善

#### 第三阶段（1-2周）：P2增强功能
- ✅ 意图歧义澄清机制
- ✅ 性能监控与指标追踪
- ✅ 配置文件管理
- ✅ 上下文摘要增强
- ✅ 置信度阈值配置化

### 12.4 验收标准

每个优化项完成后，需要满足以下验收标准：

| 优化项 | 验收标准 |
|-------|---------|
| 参数加密存储验证 | 通过安全审计，确认所有敏感参数使用 AES-256-GCM 加密 |
| 高级文件类型解析 | 支持的文件类型解析成功率 > 95% |
| 大文件智能采样 | 10MB 文件处理时间 < 2s，采样内容覆盖关键信息 |
| 长期记忆向量检索 | 语义检索准确率 > 80%，检索延迟 < 500ms |
| 意图歧义澄清 | 低置信度场景下澄清问题生成准确率 > 70% |
| 性能监控 | 所有关键路径都有性能指标记录，P90延迟可追踪 |
| 配置文件管理 | 所有可配置参数都支持从 YAML 加载 |
| 上下文摘要增强 | 摘要包含关键实体、文件列表、用户偏好，长度 < 500 tokens |

### 12.5 相关文档

- 实现代码：`python-agent-service/app/middleware/intent_understanding.py`
- 配置文件示例：见 [11.2 配置文件示例](#112-配置文件示例)
- 数据库迁移：`supabase/migrations/`

---

## 13. 当前实现对齐（2026-03）

本章节用于把 PRD 与当前代码实现对齐；若与上文历史描述存在冲突，以本章节和实现代码为准。

### 13.1 新增/强化能力

1. **显式分析范围（Analysis Scope）**
   - 新增 `analysis_scope` 输入参数：`all_input | attachment_only | text_only`
   - 支持从用户文本与显式参数联合推断范围
   - 当用户要求 `attachment_only` 但未上传文件时，自动安全回退到 `all_input`

2. **结构化附件输入契约**
   - `/analyze` 支持结构化 `attachments[]`（含 `filename/content_type/content/size`）
   - 主智能体不再依赖“把附件内容拼进文本”来理解需求
   - 子智能体接收按任务过滤后的文件清单与意图结果

3. **最小硬规则 + 能力协商 + 策略守卫**
   - 新增策略模块用于 `scope normalize`、`policy evaluate`
   - 新增能力请求与协商（`required/optional/extensions`）
   - 未知能力扩展进入协商结果，不直接放行

4. **多类型附件任务拆分**
   - 任务规划采用 merge-first：无论 `intent_result.tasks` 是否为空，先按 `skill/family` 聚合任务
   - `security` 任务按 skill 合并，同 skill 多条任务聚合为单个执行任务
   - 当输入包含多类 artifact（email / binary / web 等）时，按 family 形成对应任务组（如 email/web/binary）
   - 每个任务只携带该类型相关文件，避免跨类型污染
   - 原始依赖 `depends_on_task_ids` 会映射到聚合后的任务 ID，避免聚合后依赖失真

5. **历史分析结合（通用，不限邮件）**
   - 从历史会话提取结构化事实 `historyContext[]`（摘要、实体、置信度、来源）
   - 历史信息标记为 `trust=untrusted_text`，仅作证据，不作指令
   - 子智能体输出要求区分：
     - `newEvidence`
     - `historicalCorrelation`
     - `conflicts`

6. **前端附件管理增强**
   - 已上传附件列表可视化展示
   - 支持逐个删除附件
   - 去重逻辑按 `SHA-256` 执行：仅 hash 相同去重，同名但 hash 不同允许上传

### 13.2 当前主链路（简版）

1) `main.py` 接收 `message + attachments + analysis_scope`  
2) `IntentUnderstandingMiddleware` 完成文件解析、scope 推断、意图识别、历史事实提取  
3) `TaskPlanner` 按类型路由并注入结构化 payload  
4) `TaskInstructionBuilder` 组装主智能体控制指令与子任务描述  
5) 子智能体在 guardrail 下执行，输出结构化结果并流式返回

### 13.3 数据字段对齐（关键）

`IntentResult` 当前关键补充字段：

- `analysis_scope`
- `file_manifest`
- `history_context`
- `hard_constraints`
- `capability_request`
- `capability_negotiation`
- `policy_guard`

### 13.4 与实现锚点

- `python-agent-service/app/middleware/intent_understanding.py`
- `python-agent-service/app/middleware/policy_guard.py`
- `python-agent-service/app/middleware/task_planner.py`
- `python-agent-service/app/middleware/task_instruction_builder.py`
- `python-agent-service/app/middleware/context_retriever.py`
- `python-agent-service/app/main.py`
- `src/components/CommandCenter.tsx`
- `src/hooks/useStreamingAnalysis.ts`

### 13.5 参考设计文档

请同时参考：`docs/INTENT_UNDERSTANDING_COMPLETE_DESIGN.md`

---

**文档状态**: 已对齐当前实现（持续演进）  
**最后更新**: 2026.03.02  
**下次评审**: 2026.03.16  
**文档所有者**: Intent & Context Team

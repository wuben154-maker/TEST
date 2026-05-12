# SecManus DeepAgent 架构图与时序图

> **请以 [`ARCHITECTURE.md`](./ARCHITECTURE.md) 为结构与流程的权威说明。**  
> 本文保留 Mermaid 图；曾误用的入口名 `analyze_with_intent_stream` 已删除（现为 `stream_analyze_request` / `stream_resume_request`）。  
> 更新日期：2026-04-04

---

## 一、整体系统架构图

```mermaid
flowchart TB
    subgraph Client [前端 Client]
        UI[React UI]
    end

    subgraph API [FastAPI 层]
        Main[main.py stream_deep_analysis]
        SSE[StreamingResponse]
    end

    subgraph DeepAgent [DeepAgent 核心]
        SAS[stream_analyze_request]
        DS[DeepAgentWithIntent]
        AS[analyze_stream]
    end

    subgraph Official [官方 create_deep_agent]
        Agent[LangGraph Agent]
        TodoFS[TodoList + Filesystem + Summarization]
        SubMW[SubAgentMiddleware]
        SkillsMW[SkillsMiddleware]
    end

    subgraph SubAgents [安全 SubAgents]
        SA1[email-security]
        SA2[binary-analysis]
        SA3[web-security]
        SA4[soc-alert]
        SA5[vuln-scan]
        SA6[general-security]
        SA7[deep-research]
    end

    subgraph Backends [存储 Backend]
        Factory[create_layered_backend]
        Composite[CompositeBackend]
        DB[DatabaseBackend]
        FS[FilesystemBackend]
    end

    subgraph Storage [持久化]
        PG[(PostgreSQL/Supabase)]
    end

    UI -->|HTTP/SSE| Main
    Main --> SAS
    SAS --> DS
    DS --> AS
    AS --> Agent
    Agent --> TodoFS
    Agent --> SubMW
    SubMW --> SA1 & SA2 & SA3 & SA4 & SA5 & SA6 & SA7
    SA1 & SA2 & SA3 & SA4 & SA5 & SA6 & SA7 --> SkillsMW
    DS --> Factory
    Factory --> Composite
    Composite --> DB
    Composite --> FS
    DB --> PG
    DS --> Main
    Main --> SSE
    SSE --> UI
```

---

## 二、端到端安全分析时序图

```mermaid
sequenceDiagram
    participant User
    participant Main as main.py
    participant SAS as stream_analyze_request
    participant DA as DeepAgentWithIntent
    participant AG as create_deep_agent
    participant Sub as SubAgent

    User->>Main: POST /analyze
    Main->>SAS: stream_analyze_request(...)
    Note over SAS: 同 session 串行锁、上传路径作用域、request LLM id
    SAS->>DA: analyze_stream(text, files, ...)
    Note over DA: 解析附件 / manifest、构建消息、adapt_astream_to_sse
    DA->>AG: agent.astream(...)
    AG->>Sub: task(subagent_type, ...) 可选
    Sub-->>AG: 子代理结果
    AG-->>DA: 模型与工具事件
    DA-->>User: SSE（reasoning / tool_call / conclusion / done 等）
```

---

## 三、Backend 路由架构图

```mermaid
flowchart TB
    subgraph Config [配置]
        DBMode[DATABASE_MODE]
        DBMode -->|local or supabase| UseDB[DatabaseBackend]
        DBMode -->|memory| UseMem[StoreBackend + InMemoryStore]
    end

    subgraph Factory [create_layered_backend]
        BuildRoutes[_build_routes]
        FactoryFn[factory(rt) -> CompositeBackend]
    end

    subgraph Composite [CompositeBackend]
        Default[default: StateBackend]
        Routes[routes]
    end

    subgraph RouteMap [路由表 routes]
        R1["/memories/"]
        R2["/parameters/"]
        R3["/skills/"]
    end

    subgraph Backends [具体 Backend]
        State[StateBackend - 会话临时状态]
        DB1[DatabaseBackend namespace=memories]
        DB2[DatabaseBackend namespace=parameters]
        FS[FilesystemBackend - SKILLS_DIR]
    end

    subgraph Storage [持久化]
        AgentStore[(agent_store 表)]
    end

    BuildRoutes --> R1 & R2 & R3
    R1 --> DB1
    R2 --> DB2
    R3 --> FS
    Default --> State
    Routes --> RouteMap
    DB1 & DB2 --> AgentStore
```

---

## 四、Backend 路径路由决策流程图

```mermaid
flowchart LR
    Request[文件操作请求 path]
    Request --> Match{匹配前缀?}

    Match -->|/temp/ 或未匹配| Default[StateBackend -  ephemeral]
    Match -->|/memories/| Mem[memories backend]
    Match -->|/parameters/| Params[parameters backend]
    Match -->|/skills/| Skills[FilesystemBackend]

    Mem --> DB1[(agent_store namespace=memories)]
    Params --> DB2[(agent_store namespace=parameters)]
    Skills --> FS["SKILLS_DIR 磁盘"]
```

---

## 五、路由与任务形态（当前实现）

独立「意图理解服务 → TaskPlanner → TaskExecutor」流水线**不存在**。分类、是否先 `web_search`、是否 `task(deep-research)` 等由 **主模型** 在 LangGraph 内按 `MASTER_AGENT.md` 与工具调用完成。

---

## 六、主模型委派（概念）

```mermaid
flowchart TB
    MA[主 Agent LLM]
    MA --> Tools[通用工具 web_search / read_file / …]
    MA --> Todos[write_todos 可选]
    Todos --> Task[task(subagent_type, description)]
    Task --> Sub[SubAgentMiddleware → 对应子代理]
    Sub --> Out[结果回主线程 / SSE]
```

---

## 七、SubAgent 与 Skill 依赖矩阵

```mermaid
flowchart LR
    subgraph SubAgents [SubAgents]
        Email[email-security]
        Binary[binary-analysis]
        Web[web-security]
        SOC[soc-alert]
        Vuln[vuln-scan]
        General[general-security]
        Deep[deep-research]
    end

    subgraph Skills [SKILL.md 路径]
        S1["/skills/email-security/"]
        S2["/skills/binary-analysis/"]
        S3["/skills/web-security/"]
        S4["/skills/soc-alert/"]
        S5["/skills/vuln-scan/"]
        S6["/skills/general-security/"]
        S7["/skills/deep-research/"]
    end

    Email --> S1
    Binary --> S2
    Web --> S3
    SOC --> S4
    Vuln --> S5
    General --> S6
    Deep --> S7
```

---

## 八、SSE 事件流图（简化）

```mermaid
flowchart TB
    subgraph Source [事件来源]
        SAS[stream_analyze_request]
        Adapt[analyze_stream / adapt_astream_to_sse]
        Agent[agent.astream]
    end

    subgraph Events [常见 SSE 类型]
        E1[step]
        E2[reasoning]
        E3[tool_call]
        E4[tool_result]
        E5[conclusion]
        E6[done]
    end

    subgraph Frontend [前端消费]
        useStream[useStreamingAnalysis]
        UI[React UI]
    end

    SAS --> Adapt
    Adapt --> E1 & E5 & E6
    Agent --> E2 & E3 & E4 & E5 & E6
    E1 & E2 & E3 & E4 & E5 & E6 --> useStream
    useStream --> UI
```

---

## 九、create_deep_agent 内部 Middleware 链

```mermaid
flowchart LR
    subgraph Official [官方 create_deep_agent 内置]
        A[Agent 节点]
        M1[TodoListMiddleware]
        M2[FilesystemMiddleware]
        M3[SummarizationMiddleware]
        M4[SubAgentMiddleware]
        M5[SkillsMiddleware]
    end

    A --> M1 --> M2 --> M3 --> M4 --> M5
    M2 -->|backend| CompositeBackend
    M5 -->|read skills| CompositeBackend
```

---

## 十、存储层数据流图

```mermaid
flowchart TB
    subgraph App [应用层]
        Runtime[Agent 运行时 / create_deep_agent]
        Composite[CompositeBackend]
    end

    subgraph ContextStore [ContextStoreAdapter]
        CSA[get/set/search/list_keys]
    end

    subgraph BackendChoice [Backend 选择]
        DBMode{DATABASE_MODE}
        DBMode -->|local/supabase| DB[DatabaseBackend]
        DBMode -->|memory| Mem[StoreBackend + InMemoryStore]
    end

    subgraph DBBackend [DatabaseBackend 内部]
        NS1[namespace=memories]
        NS2[namespace=parameters]
        PG[PostgresStore]
        Supa[SupabaseStore]
    end

    subgraph Persistence [持久化]
        Table[(agent_store)]
    end

    Runtime --> CSA
    CSA --> DB
    CSA --> Mem
    DB --> NS1 & NS2
    NS1 & NS2 --> PG
    NS1 & NS2 --> Supa
    PG --> Table
    Supa --> Table
    Composite --> DB
```

---

## 十一、组件层次结构图

```mermaid
flowchart TB
    subgraph Entry [入口]
        main[main.py]
        sas[stream_analyze_request]
    end

    subgraph Core [核心编排]
        DeepAgent[DeepAgentWithIntent]
        analyze[analyze_stream]
    end

    subgraph AgentLayer [Agent 层]
        Agent[create_deep_agent 图]
    end

    subgraph Vendor [Vendor 官方]
        Graph[LangGraph compiled graph]
        SubMW[SubAgentMiddleware]
        SkillsMW[SkillsMiddleware]
        Backends[backends]
    end

    main --> sas
    sas --> DeepAgent
    DeepAgent --> analyze
    analyze --> Agent
    Agent --> Graph
    Graph --> SubMW
    Graph --> SkillsMW
    Graph --> Backends
```

---

## 图例说明

| 符号     | 含义      |
| -------- | --------- |
| 实线箭头 | 调用/数据流 |
| 虚线框   | 逻辑分组  |
| 菱形     | 条件分支  |
| 圆角矩形 | 处理节点  |

---

## 相关文档

- [`ARCHITECTURE.md`](./ARCHITECTURE.md)

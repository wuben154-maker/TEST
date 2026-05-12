# SecManus 二进制深度分析系统 - 架构设计文档

## 🎯 系统概述

SecManus 二进制深度分析系统是基于现有 SecManus 安全分析平台构建的专业二进制文件分析模块，提供自动化恶意代码检测和程序调用关系分析功能。

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     Web 用户界面 (React)                        │
├─────────────────────────────────────────────────────────────────┤
│  文件上传  │  分析控制台  │  可视化展示  │  报告导出  │  历史查看  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    API 网关层 (FastAPI)                        │
├─────────────────────────────────────────────────────────────────┤
│     认证授权    │    路由转发    │    请求验证    │    限流控制    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                  LangGraph Agent 编排层                        │
├─────────────────────────────────────────────────────────────────┤
│  主控 Agent  │  分析 Agent  │  检测 Agent  │  可视化 Agent      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    核心分析引擎                                  │
├─────────────────┬───────────────┬───────────────┬───────────────┤
│  静态分析模块    │  动态分析模块  │  恶意检测模块  │  可视化模块    │
├─────────────────┼───────────────┼───────────────┼───────────────┤
│ • 反汇编引擎    │ • 沙箱执行    │ • YARA 规则   │ • 调用图生成   │
│ • 控制流分析    │ • API 监控    │ • ML 检测     │ • 控制流图     │
│ • 调用图构建    │ • 行为捕获    │ • 签名匹配    │ • 交互式导航   │
│ • 字符串提取    │ • 内存分析    │ • 威胁评级    │ • 3D 可视化    │
└─────────────────┴───────────────┴───────────────┴───────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   数据存储层 (Supabase)                         │
├─────────────────────────────────────────────────────────────────┤
│  分析结果表  │  恶意样本库  │  规则库  │  用户会话  │  审计日志   │
└─────────────────────────────────────────────────────────────────┘
```

## 🔧 核心模块设计

### 1. 二进制分析引擎

#### 1.1 文件格式解析器
```python
class BinaryAnalyzer:
    """二进制文件分析器基类"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.binary = lief.parse(file_path)
        self.disassembler = capstone.Cs()
        
    def analyze(self) -> AnalysisResult:
        """执行完整分析"""
        return AnalysisResult(
            basic_info=self.extract_basic_info(),
            strings=self.extract_strings(),
            imports=self.extract_imports(),
            exports=self.extract_exports(),
            sections=self.analyze_sections(),
            entropy=self.calculate_entropy(),
            call_graph=self.build_call_graph(),
            control_flow=self.analyze_control_flow()
        )
```

#### 1.2 静态分析核心
- **反汇编引擎**: 基于 Capstone，支持多架构
- **控制流分析**: CFG 构建和基本块识别
- **数据流分析**: 变量追踪和依赖分析
- **字符串提取**: 智能字符串识别和分类

### 2. 恶意代码检测模块

#### 2.1 多层检测策略
```python
class MalwareDetector:
    def __init__(self):
        self.yara_engine = YaraEngine()
        self.ml_classifier = MLClassifier()
        self.behavior_analyzer = BehaviorAnalyzer()
        
    def detect(self, binary: BinaryFile) -> ThreatAssessment:
        """多层恶意代码检测"""
        results = []
        
        # 1. YARA 规则匹配
        yara_matches = self.yara_engine.scan(binary)
        results.append(yara_matches)
        
        # 2. 机器学习分类
        ml_prediction = self.ml_classifier.predict(binary.features)
        results.append(ml_prediction)
        
        # 3. 行为模式分析
        behavior_score = self.behavior_analyzer.analyze(binary.api_calls)
        results.append(behavior_score)
        
        return self.aggregate_threat_score(results)
```

#### 2.2 检测技术栈
- **签名检测**: YARA 规则库 + 自定义规则
- **机器学习**: XGBoost + 深度学习模型
- **行为分析**: API 调用序列分析
- **启发式检测**: 熵分析 + 加壳检测

### 3. 调用关系分析模块

#### 3.1 静态调用图构建
```python
class CallGraphBuilder:
    def __init__(self, binary: BinaryFile):
        self.binary = binary
        self.functions = self.identify_functions()
        self.call_graph = nx.DiGraph()
        
    def build_call_graph(self) -> nx.DiGraph:
        """构建函数调用图"""
        for func_addr in self.functions:
            callers, callees = self.analyze_function_calls(func_addr)
            
            # 添加节点和边
            self.call_graph.add_node(func_addr, **func_info)
            for callee in callees:
                self.call_graph.add_edge(func_addr, callee)
                
        return self.call_graph
        
    def analyze_control_flow(self, func_addr: int) -> ControlFlowGraph:
        """分析单个函数的控制流"""
        cfg = ControlFlowGraph()
        basic_blocks = self.identify_basic_blocks(func_addr)
        
        for bb in basic_blocks:
            cfg.add_block(bb)
            # 分析跳转关系
            successors = self.find_successors(bb)
            for succ in successors:
                cfg.add_edge(bb, succ)
                
        return cfg
```

#### 3.2 类 OllyDbg 功能
- **交互式反汇编**: 点击跳转和交叉引用
- **断点设置**: 虚拟断点标记重要位置
- **寄存器状态**: 模拟执行状态展示
- **内存映射**: 虚拟地址空间可视化

### 4. 可视化系统

#### 4.1 多维度可视化
```typescript
// 调用图可视化组件
const CallGraphViewer: React.FC<CallGraphProps> = ({ callGraph }) => {
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [layout, setLayout] = useState<'hierarchical' | 'force' | 'circular'>('hierarchical');
  
  return (
    <div className="call-graph-container">
      <div className="controls">
        <LayoutSelector value={layout} onChange={setLayout} />
        <SearchBar onSearch={handleNodeSearch} />
        <FilterPanel onFilter={handleFilter} />
      </div>
      
      <div className="graph-area">
        <NetworkGraph 
          data={callGraph}
          layout={layout}
          onNodeSelect={setSelectedNode}
          highlightPath={highlightedPath}
        />
      </div>
      
      <div className="details-panel">
        {selectedNode && (
          <FunctionDetails 
            function={getFunctionInfo(selectedNode)}
            disassembly={getDisassembly(selectedNode)}
          />
        )}
      </div>
    </div>
  );
};
```

#### 4.2 可视化特性
- **多布局算法**: 层次布局、力导向布局、环形布局
- **交互式导航**: 缩放、平移、节点搜索
- **路径高亮**: 函数调用链路径追踪
- **详情面板**: 选中节点的详细信息

## 📊 数据库设计

### 核心表结构

```sql
-- 二进制文件分析记录
CREATE TABLE binary_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size BIGINT,
    file_type TEXT, -- PE, ELF, Mach-O等
    upload_time TIMESTAMP DEFAULT NOW(),
    analysis_status TEXT DEFAULT 'pending', -- pending, running, completed, failed
    threat_level INTEGER DEFAULT 0, -- 0-100 威胁等级
    analysis_duration INTEGER, -- 分析耗时(秒)
    metadata JSONB -- 其他元数据
);

-- 分析结果存储
CREATE TABLE analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES binary_analyses(id),
    result_type TEXT NOT NULL, -- basic_info, strings, imports, call_graph等
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 威胁检测结果
CREATE TABLE threat_detections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES binary_analyses(id),
    detection_type TEXT NOT NULL, -- yara, ml, behavior
    threat_name TEXT,
    confidence FLOAT, -- 置信度 0-1
    description TEXT,
    severity TEXT, -- low, medium, high, critical
    iocs TEXT[], -- IOCs数组
    created_at TIMESTAMP DEFAULT NOW()
);

-- 调用图数据
CREATE TABLE call_graphs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID REFERENCES binary_analyses(id),
    graph_data JSONB NOT NULL, -- 序列化的图数据
    function_count INTEGER,
    edge_count INTEGER,
    complexity_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🚀 技术实现细节

### 1. 性能优化策略

#### 1.1 异步处理
```python
class AnalysisOrchestrator:
    def __init__(self):
        self.task_queue = asyncio.Queue()
        self.worker_pool = []
        
    async def submit_analysis(self, file_path: str) -> str:
        """提交分析任务"""
        task_id = str(uuid.uuid4())
        task = AnalysisTask(
            task_id=task_id,
            file_path=file_path,
            timestamp=datetime.now()
        )
        
        await self.task_queue.put(task)
        return task_id
        
    async def process_tasks(self):
        """异步处理分析任务"""
        while True:
            task = await self.task_queue.get()
            asyncio.create_task(self.analyze_file(task))
```

#### 1.2 缓存机制
- **结果缓存**: Redis 缓存常用分析结果
- **文件哈希**: 避免重复分析相同文件
- **增量分析**: 只分析文件变化部分

### 2. 安全考虑

#### 2.1 沙箱隔离
```python
class SecureAnalyzer:
    def __init__(self):
        self.sandbox = Docker('analysis-sandbox:latest')
        
    async def safe_analyze(self, file_path: str) -> AnalysisResult:
        """在安全沙箱中分析文件"""
        container_id = await self.sandbox.create_container(
            image='analysis-sandbox',
            command=f'python /app/analyze.py {file_path}',
            network_mode='none',  # 禁用网络
            memory_limit='1g',
            cpu_limit='50%',
            read_only=True,
            security_opt=['no-new-privileges:true']
        )
        
        try:
            result = await self.sandbox.run_container(container_id)
            return self.parse_result(result)
        finally:
            await self.sandbox.remove_container(container_id)
```

#### 2.2 权限控制
- **文件访问**: 严格的文件系统权限
- **网络隔离**: 分析过程中断网
- **资源限制**: CPU/内存使用限制
- **审计日志**: 完整的操作记录

## 🔄 工作流程

### 分析流程图
```
文件上传 → 预处理 → 队列调度 → 多模块分析 → 结果聚合 → 报告生成
    ↓         ↓         ↓         ↓         ↓         ↓
  验证格式   计算哈希   任务分发   并行执行   威胁评级   可视化
```

### 详细步骤
1. **文件上传**: 支持拖拽上传，格式验证
2. **预处理**: 文件哈希计算，重复检测
3. **任务调度**: 智能任务分配和负载均衡
4. **并行分析**: 多模块同时执行分析
5. **结果整合**: 聚合各模块分析结果
6. **威胁评级**: 综合评分和风险评估
7. **报告生成**: 自动生成详细分析报告
8. **可视化展示**: 交互式图形展示

## 📈 扩展性设计

### 1. 模块化架构
- **插件系统**: 支持自定义分析模块
- **规则引擎**: 灵活的检测规则配置
- **API 扩展**: RESTful API 支持集成

### 2. 横向扩展
- **微服务架构**: 核心模块可独立部署
- **负载均衡**: 支持多实例水平扩展
- **分布式存储**: 大文件和结果数据分布式存储

## 🏁 实施计划

### 阶段 1: 核心引擎 (2-3 周)
- [ ] 基础二进制分析引擎
- [ ] YARA 规则集成
- [ ] 基本 Web 界面

### 阶段 2: 检测能力 (2-3 周)  
- [ ] 机器学习检测模型
- [ ] 行为分析模块
- [ ] 威胁评级系统

### 阶段 3: 可视化系统 (2-3 周)
- [ ] 调用图可视化
- [ ] 控制流图展示
- [ ] 交互式分析界面

### 阶段 4: 性能优化 (1-2 周)
- [ ] 异步处理优化
- [ ] 缓存机制
- [ ] 安全强化

## 🎯 预期效果

### 功能特性
- ✅ 支持主流二进制格式分析
- ✅ 高精度恶意代码检测
- ✅ 直观的调用关系可视化
- ✅ 类 OllyDbg 交互式分析
- ✅ 自动化威胁评级
- ✅ 专业分析报告生成

### 性能指标
- **分析速度**: 10MB 文件 < 30秒
- **检测准确率**: > 95%
- **并发处理**: 支持 50+ 并发分析
- **可视化性能**: 1000+ 节点流畅展示

通过这个系统，用户将获得专业级别的二进制文件分析能力，大幅提升恶意代码检测和逆向分析的效率。
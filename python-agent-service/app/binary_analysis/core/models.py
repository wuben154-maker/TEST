"""
二进制分析数据模型定义
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime


class AnalysisStatus(Enum):
    """分析状态枚举"""
    PENDING = "pending"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ThreatLevel(Enum):
    """威胁等级枚举"""
    CLEAN = 0
    SUSPICIOUS = 25
    LIKELY_MALICIOUS = 50
    MALICIOUS = 75
    CRITICAL = 100


class FileType(Enum):
    """支持的文件类型"""
    PE = "pe"           # Windows PE
    ELF = "elf"         # Linux ELF
    MACH_O = "mach_o"   # macOS Mach-O
    JAVA_CLASS = "java_class"  # Java字节码
    PYTHON_PYC = "python_pyc"  # Python字节码
    ANDROID_DEX = "android_dex" # Android DEX
    UNKNOWN = "unknown"


@dataclass
class BasicFileInfo:
    """基本文件信息"""
    file_name: str
    file_path: str
    file_size: int
    file_type: FileType
    architecture: str  # x86, x64, arm, etc.
    md5: str
    sha1: str
    sha256: str
    created_time: Optional[datetime] = None
    modified_time: Optional[datetime] = None


@dataclass
class SectionInfo:
    """节区信息"""
    name: str
    virtual_address: int
    virtual_size: int
    raw_size: int
    entropy: float
    permissions: List[str]  # ['read', 'write', 'execute']
    characteristics: List[str]
    is_executable: bool
    contains_code: bool


@dataclass
class ImportedFunction:
    """导入函数信息"""
    function_name: str
    library_name: str
    ordinal: Optional[int] = None
    is_suspicious: bool = False
    risk_level: str = "low"  # low, medium, high
    description: str = ""


@dataclass
class ExportedFunction:
    """导出函数信息"""
    function_name: str
    address: int
    ordinal: Optional[int] = None
    is_forwarded: bool = False
    forward_name: Optional[str] = None


@dataclass
class StringInfo:
    """字符串信息"""
    content: str
    address: int
    encoding: str  # ascii, utf-8, utf-16, etc.
    length: int
    is_url: bool = False
    is_ip: bool = False
    is_email: bool = False
    is_registry_key: bool = False
    is_file_path: bool = False
    is_suspicious: bool = False


@dataclass
class Instruction:
    """反汇编指令"""
    address: int
    mnemonic: str
    operands: str
    bytes: bytes
    size: int
    is_call: bool = False
    is_jump: bool = False
    is_conditional: bool = False
    target_address: Optional[int] = None


@dataclass
class BasicBlock:
    """基本块"""
    start_address: int
    end_address: int
    instructions: List[Instruction] = field(default_factory=list)
    successors: List[int] = field(default_factory=list)
    predecessors: List[int] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.instructions:
            self.instructions = []
        if not self.successors:
            self.successors = []
        if not self.predecessors:
            self.predecessors = []


@dataclass
class FunctionInfo:
    """函数信息"""
    address: int
    name: str
    size: int
    basic_blocks: List[BasicBlock] = field(default_factory=list)
    called_functions: List[int] = field(default_factory=list)
    calling_functions: List[int] = field(default_factory=list)
    api_calls: List[str] = field(default_factory=list)
    complexity_score: float = 0.0
    is_suspicious: bool = False
    
    def __post_init__(self):
        if not self.basic_blocks:
            self.basic_blocks = []
        if not self.called_functions:
            self.called_functions = []
        if not self.calling_functions:
            self.calling_functions = []
        if not self.api_calls:
            self.api_calls = []


@dataclass
class CallGraphNode:
    """调用图节点"""
    address: int
    function_name: str
    call_count: int = 0
    called_by_count: int = 0
    is_entry_point: bool = False
    is_suspicious: bool = False


@dataclass
class CallGraphEdge:
    """调用图边"""
    source: int
    target: int
    call_count: int = 1
    edge_type: str = "direct"  # direct, indirect


@dataclass
class CallGraph:
    """函数调用图"""
    nodes: List[CallGraphNode] = field(default_factory=list)
    edges: List[CallGraphEdge] = field(default_factory=list)
    entry_points: List[int] = field(default_factory=list)
    complexity_score: float = 0.0
    
    def __post_init__(self):
        if not self.nodes:
            self.nodes = []
        if not self.edges:
            self.edges = []
        if not self.entry_points:
            self.entry_points = []


@dataclass
class ThreatDetection:
    """威胁检测结果"""
    detection_id: str
    detector_name: str
    threat_name: str
    threat_type: str  # malware, packer, obfuscator, etc.
    confidence: float  # 0.0 - 1.0
    severity: ThreatLevel
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    iocs: List[str] = field(default_factory=list)
    mitigation: str = ""
    
    def __post_init__(self):
        if not self.evidence:
            self.evidence = {}
        if not self.iocs:
            self.iocs = []


@dataclass
class AnalysisResult:
    """完整分析结果"""
    analysis_id: str
    file_info: BasicFileInfo
    status: AnalysisStatus
    threat_level: ThreatLevel
    
    # 基础分析结果
    sections: List[SectionInfo] = field(default_factory=list)
    imports: List[ImportedFunction] = field(default_factory=list)
    exports: List[ExportedFunction] = field(default_factory=list)
    strings: List[StringInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    call_graph: Optional[CallGraph] = None
    
    # 威胁检测结果
    threats: List[ThreatDetection] = field(default_factory=list)
    
    # 分析元数据
    analysis_start_time: Optional[datetime] = None
    analysis_end_time: Optional[datetime] = None
    analysis_duration: float = 0.0
    error_message: str = ""
    warnings: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.sections:
            self.sections = []
        if not self.imports:
            self.imports = []
        if not self.exports:
            self.exports = []
        if not self.strings:
            self.strings = []
        if not self.functions:
            self.functions = []
        if not self.threats:
            self.threats = []
        if not self.warnings:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'analysis_id': self.analysis_id,
            'file_info': {
                'file_name': self.file_info.file_name,
                'file_size': self.file_info.file_size,
                'file_type': self.file_info.file_type.value,
                'architecture': self.file_info.architecture,
                'md5': self.file_info.md5,
                'sha1': self.file_info.sha1,
                'sha256': self.file_info.sha256
            },
            'status': self.status.value,
            'threat_level': self.threat_level.value,
            'sections_count': len(self.sections),
            'imports_count': len(self.imports),
            'exports_count': len(self.exports),
            'strings_count': len(self.strings),
            'functions_count': len(self.functions),
            'threats_count': len(self.threats),
            'analysis_duration': self.analysis_duration,
            'has_call_graph': self.call_graph is not None
        }
    
    def to_json(self) -> str:
        """转换为JSON格式"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class AnalysisConfig:
    """分析配置"""
    # 分析模式
    enable_deep_analysis: bool = True
    enable_disassembly: bool = True
    enable_call_graph: bool = True
    enable_string_analysis: bool = True
    enable_entropy_analysis: bool = True
    
    # 检测配置
    enable_yara_scan: bool = True
    enable_ml_detection: bool = True
    enable_behavior_analysis: bool = True
    
    # 性能配置
    max_analysis_time: int = 300  # 秒
    max_memory_usage: int = 1024  # MB
    max_disasm_instructions: int = 100000
    
    # 输出配置
    include_disassembly: bool = False
    include_call_graph_data: bool = True
    verbose_output: bool = False


class AnalysisError(Exception):
    """分析错误基类"""
    pass


class FileParsingError(AnalysisError):
    """文件解析错误"""
    pass


class DisassemblyError(AnalysisError):
    """反汇编错误"""
    pass


class DetectionError(AnalysisError):
    """检测错误"""
    pass
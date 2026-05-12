"""
SecManus 二进制分析模块

提供专业的二进制文件分析能力：
- 静态分析和反汇编
- 恶意代码检测
- 调用关系分析
- 可视化展示
"""

from .core.analyzer import BinaryAnalyzer
from .core.disassembler import DisassemblerEngine
from .core.call_graph import CallGraphBuilder
from .detectors.malware_detector import MalwareDetector
from .detectors.yara_engine import YaraEngine
from .utils.file_parser import FileParser

__version__ = "1.0.0"
__author__ = "SecManus Team"

__all__ = [
    "BinaryAnalyzer",
    "DisassemblerEngine", 
    "CallGraphBuilder",
    "MalwareDetector",
    "YaraEngine",
    "FileParser"
]
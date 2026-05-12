"""
主二进制分析器

整合所有分析模块，提供统一的分析接口
"""

import os
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from ..core.models import (
    AnalysisResult, AnalysisStatus, ThreatLevel, AnalysisConfig,
    BasicFileInfo, StringInfo, AnalysisError
)
from ..utils.file_parser import FileParser
from ..core.disassembler import DisassemblerEngine
from ..core.call_graph import CallGraphBuilder
from ..detectors.malware_detector import MalwareDetector


class BinaryAnalyzer:
    """主二进制分析器"""
    
    def __init__(self, config: Optional[AnalysisConfig] = None):
        """
        初始化分析器
        
        Args:
            config: 分析配置
        """
        self.config = config or AnalysisConfig()
        self.logger = logging.getLogger(__name__)
        
        # 初始化各个组件
        self.file_parser = FileParser()
        self.disassembler = None
        self.call_graph_builder = None
        self.malware_detector = None
        
        self._init_detectors()
    
    def _init_detectors(self):
        """初始化检测器"""
        try:
            # 恶意代码检测器
            detector_config = {
                'enable_yara': self.config.enable_yara_scan,
                'enable_ml': self.config.enable_ml_detection,
                'enable_behavior': self.config.enable_behavior_analysis
            }
            self.malware_detector = MalwareDetector(detector_config)
            self.logger.info("Malware detector initialized")
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize some detectors: {e}")
    
    def analyze(self, file_path: str) -> AnalysisResult:
        """
        执行完整的二进制文件分析
        
        Args:
            file_path: 文件路径
            
        Returns:
            AnalysisResult: 分析结果
        """
        analysis_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        self.logger.info(f"Starting analysis of {file_path}")
        
        # 初始化结果对象
        result = AnalysisResult(
            analysis_id=analysis_id,
            file_info=BasicFileInfo(
                file_name=os.path.basename(file_path),
                file_path=file_path,
                file_size=0,
                file_type=None,
                architecture="unknown",
                md5="", sha1="", sha256=""
            ),
            status=AnalysisStatus.RUNNING,
            threat_level=ThreatLevel.CLEAN,
            analysis_start_time=start_time
        )
        
        try:
            # 1. 基础文件信息解析
            self.logger.info("Parsing basic file information")
            result.file_info = self.file_parser.parse_file(file_path)
            
            # 2. 解析节区信息
            if self.config.enable_deep_analysis:
                self.logger.info("Parsing sections")
                result.sections = self.file_parser.parse_sections(file_path)
            
            # 3. 解析导入/导出表
            self.logger.info("Parsing imports and exports")
            result.imports = self.file_parser.parse_imports(file_path)
            result.exports = self.file_parser.parse_exports(file_path)
            
            # 4. 字符串提取
            if self.config.enable_string_analysis:
                self.logger.info("Extracting strings")
                result.strings = self._extract_strings(file_path)
            
            # 5. 反汇编和函数分析
            if self.config.enable_disassembly:
                self.logger.info("Performing disassembly analysis")
                self._perform_disassembly_analysis(result)
            
            # 6. 调用图构建
            if self.config.enable_call_graph and result.functions:
                self.logger.info("Building call graph")
                result.call_graph = self._build_call_graph(file_path)
            
            # 7. 威胁检测
            self.logger.info("Performing threat detection")
            if self.malware_detector:
                result.threats = self.malware_detector.detect_threats(result)
            
            # 8. 计算最终威胁等级
            result.threat_level = self._calculate_overall_threat_level(result)
            
            # 9. 完成分析
            result.status = AnalysisStatus.COMPLETED
            result.analysis_end_time = datetime.now()
            result.analysis_duration = (result.analysis_end_time - result.analysis_start_time).total_seconds()
            
            self.logger.info(f"Analysis completed in {result.analysis_duration:.2f} seconds")
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            result.status = AnalysisStatus.FAILED
            result.error_message = str(e)
            result.analysis_end_time = datetime.now()
            result.analysis_duration = (result.analysis_end_time - result.analysis_start_time).total_seconds()
        
        return result
    
    def analyze_quick(self, file_path: str) -> AnalysisResult:
        """
        快速分析（仅基础信息和威胁检测）
        
        Args:
            file_path: 文件路径
            
        Returns:
            AnalysisResult: 分析结果
        """
        # 创建快速分析配置
        quick_config = AnalysisConfig(
            enable_deep_analysis=False,
            enable_disassembly=False,
            enable_call_graph=False,
            enable_string_analysis=True,
            max_analysis_time=60
        )
        
        # 临时切换配置
        old_config = self.config
        self.config = quick_config
        
        try:
            result = self.analyze(file_path)
        finally:
            # 恢复原配置
            self.config = old_config
        
        return result
    
    def _perform_disassembly_analysis(self, result: AnalysisResult):
        """执行反汇编分析"""
        try:
            # 初始化反汇编引擎
            self.disassembler = DisassemblerEngine(
                result.file_info.file_type,
                result.file_info.architecture
            )
            
            # 查找函数
            function_addresses = self.disassembler.find_functions(result.file_info.file_path)
            self.logger.info(f"Found {len(function_addresses)} functions")
            
            # 限制分析的函数数量
            max_functions = 100
            if len(function_addresses) > max_functions:
                self.logger.warning(f"Too many functions ({len(function_addresses)}), limiting to {max_functions}")
                function_addresses = function_addresses[:max_functions]
            
            # 分析每个函数
            functions = []
            for addr in function_addresses:
                try:
                    func_info = self.disassembler.disassemble_function(
                        result.file_info.file_path, addr, self.config
                    )
                    functions.append(func_info)
                except Exception as e:
                    self.logger.warning(f"Failed to analyze function at 0x{addr:x}: {e}")
                    continue
            
            result.functions = functions
            
        except Exception as e:
            self.logger.error(f"Disassembly analysis failed: {e}")
            result.warnings.append(f"Disassembly failed: {e}")
    
    def _build_call_graph(self, file_path: str):
        """构建调用图"""
        try:
            if not self.disassembler:
                return None
                
            self.call_graph_builder = CallGraphBuilder(self.disassembler)
            return self.call_graph_builder.build_call_graph(file_path, self.config)
            
        except Exception as e:
            self.logger.error(f"Call graph building failed: {e}")
            return None
    
    def _extract_strings(self, file_path: str, min_length: int = 4) -> list:
        """提取字符串"""
        strings = []
        
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # 提取ASCII字符串
            ascii_strings = self._extract_ascii_strings(data, min_length)
            strings.extend(ascii_strings)
            
            # 提取Unicode字符串
            unicode_strings = self._extract_unicode_strings(data, min_length)
            strings.extend(unicode_strings)
            
            # 限制字符串数量
            if len(strings) > 10000:
                self.logger.warning(f"Too many strings ({len(strings)}), limiting to 10000")
                strings = strings[:10000]
            
        except Exception as e:
            self.logger.error(f"String extraction failed: {e}")
        
        return strings
    
    def _extract_ascii_strings(self, data: bytes, min_length: int) -> list:
        """提取ASCII字符串"""
        strings = []
        current_string = b""
        offset = 0
        
        for i, byte in enumerate(data):
            if 32 <= byte <= 126:  # 可打印ASCII字符
                current_string += bytes([byte])
            else:
                if len(current_string) >= min_length:
                    string_info = self._create_string_info(
                        current_string.decode('ascii', errors='ignore'),
                        offset, 'ascii'
                    )
                    strings.append(string_info)
                
                current_string = b""
                offset = i + 1
        
        # 处理文件末尾的字符串
        if len(current_string) >= min_length:
            string_info = self._create_string_info(
                current_string.decode('ascii', errors='ignore'),
                offset, 'ascii'
            )
            strings.append(string_info)
        
        return strings
    
    def _extract_unicode_strings(self, data: bytes, min_length: int) -> list:
        """提取Unicode字符串"""
        strings = []
        
        try:
            # 尝试UTF-16LE编码
            for i in range(0, len(data) - 1, 2):
                try:
                    chunk = data[i:i+200]  # 检查200字节
                    if len(chunk) % 2 != 0:
                        chunk = chunk[:-1]
                    
                    decoded = chunk.decode('utf-16le', errors='strict')
                    if len(decoded) >= min_length and self._is_printable_unicode(decoded):
                        string_info = self._create_string_info(decoded, i, 'utf-16le')
                        strings.append(string_info)
                        
                except UnicodeDecodeError:
                    continue
                    
        except Exception as e:
            self.logger.debug(f"Unicode string extraction failed: {e}")
        
        return strings
    
    def _create_string_info(self, content: str, address: int, encoding: str) -> StringInfo:
        """创建字符串信息对象"""
        # 分析字符串类型
        is_url = any(content.lower().startswith(proto) for proto in ['http://', 'https://', 'ftp://'])
        is_ip = self._is_ip_address(content)
        is_email = '@' in content and '.' in content
        is_registry_key = content.startswith('HKEY_') or '\\Software\\' in content
        is_file_path = ('\\' in content or '/' in content) and ('.' in content or len(content.split('\\')) > 2)
        
        # 检查是否可疑
        is_suspicious = self._is_suspicious_string(content)
        
        return StringInfo(
            content=content,
            address=address,
            encoding=encoding,
            length=len(content),
            is_url=is_url,
            is_ip=is_ip,
            is_email=is_email,
            is_registry_key=is_registry_key,
            is_file_path=is_file_path,
            is_suspicious=is_suspicious
        )
    
    def _is_printable_unicode(self, text: str) -> bool:
        """检查Unicode文本是否可打印"""
        printable_count = sum(1 for c in text if c.isprintable() and ord(c) > 31)
        return printable_count / len(text) > 0.8 if text else False
    
    def _is_ip_address(self, text: str) -> bool:
        """检查是否为IP地址"""
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return bool(re.match(ip_pattern, text))
    
    def _is_suspicious_string(self, content: str) -> bool:
        """检查字符串是否可疑"""
        suspicious_keywords = [
            'password', 'keylog', 'backdoor', 'trojan', 'virus',
            'malware', 'exploit', 'shellcode', 'payload', 'rootkit',
            'steal', 'hack', 'crack', 'inject', 'hide'
        ]
        
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in suspicious_keywords)
    
    def _calculate_overall_threat_level(self, result: AnalysisResult) -> ThreatLevel:
        """计算整体威胁等级"""
        if not result.threats:
            return ThreatLevel.CLEAN
        
        # 获取最高威胁等级
        max_threat_level = max(threat.severity for threat in result.threats)
        
        # 考虑威胁数量
        threat_count = len(result.threats)
        high_confidence_threats = sum(1 for t in result.threats if t.confidence > 0.8)
        
        # 调整威胁等级
        if max_threat_level == ThreatLevel.CRITICAL:
            return ThreatLevel.CRITICAL
        elif max_threat_level == ThreatLevel.MALICIOUS:
            return ThreatLevel.MALICIOUS
        elif max_threat_level == ThreatLevel.LIKELY_MALICIOUS:
            if high_confidence_threats > 1 or threat_count > 3:
                return ThreatLevel.MALICIOUS
            return ThreatLevel.LIKELY_MALICIOUS
        elif max_threat_level == ThreatLevel.SUSPICIOUS:
            if high_confidence_threats > 2 or threat_count > 5:
                return ThreatLevel.LIKELY_MALICIOUS
            return ThreatLevel.SUSPICIOUS
        else:
            return ThreatLevel.CLEAN
    
    def get_analysis_summary(self, result: AnalysisResult) -> Dict[str, Any]:
        """获取分析摘要"""
        return {
            'analysis_id': result.analysis_id,
            'file_name': result.file_info.file_name,
            'file_size': result.file_info.file_size,
            'file_type': result.file_info.file_type.value if result.file_info.file_type else 'unknown',
            'architecture': result.file_info.architecture,
            'status': result.status.value,
            'threat_level': result.threat_level.value,
            'threat_count': len(result.threats),
            'analysis_duration': result.analysis_duration,
            'sections_count': len(result.sections),
            'imports_count': len(result.imports),
            'exports_count': len(result.exports),
            'strings_count': len(result.strings),
            'functions_count': len(result.functions),
            'has_call_graph': result.call_graph is not None,
            'warnings': result.warnings,
            'error_message': result.error_message
        }
"""
YARA 规则引擎模块

提供基于 YARA 规则的恶意代码检测功能
"""

import os
import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

try:
    import yara
    YARA_AVAILABLE = True
except ImportError:
    YARA_AVAILABLE = False
    logging.warning("YARA library not available. YARA detection will be disabled.")

from ..core.models import ThreatDetection, ThreatLevel, DetectionError


class YaraEngine:
    """YARA 规则引擎"""
    
    def __init__(self, rules_directory: Optional[str] = None):
        """
        初始化 YARA 引擎
        
        Args:
            rules_directory: YARA 规则文件目录
        """
        self.logger = logging.getLogger(__name__)
        self.compiled_rules = {}
        
        if not YARA_AVAILABLE:
            raise DetectionError("YARA library not available")
        
        # 默认规则目录
        if rules_directory is None:
            rules_directory = os.path.join(
                os.path.dirname(__file__), '..', 'rules', 'yara'
            )
        
        self.rules_directory = Path(rules_directory)
        self._load_rules()
    
    def _load_rules(self):
        """加载 YARA 规则文件"""
        try:
            if not self.rules_directory.exists():
                self.logger.warning(f"Rules directory not found: {self.rules_directory}")
                self._create_default_rules()
            
            # 编译所有 .yar 和 .yara 文件
            rule_files = {}
            for rule_path in self.rules_directory.glob("*.yar*"):
                rule_name = rule_path.stem
                try:
                    with open(rule_path, 'r', encoding='utf-8') as f:
                        rule_content = f.read()
                    rule_files[rule_name] = rule_content
                except Exception as e:
                    self.logger.error(f"Failed to read rule file {rule_path}: {e}")
            
            if rule_files:
                self.compiled_rules = yara.compile(sources=rule_files)
                self.logger.info(f"Loaded {len(rule_files)} YARA rule files")
            else:
                self.logger.warning("No YARA rules loaded")
                
        except Exception as e:
            self.logger.error(f"Failed to load YARA rules: {e}")
            self.compiled_rules = None
    
    def scan_file(self, file_path: str, timeout: int = 60) -> List[ThreatDetection]:
        """
        扫描文件
        
        Args:
            file_path: 文件路径
            timeout: 扫描超时时间（秒）
            
        Returns:
            List[ThreatDetection]: 检测结果列表
        """
        detections = []
        
        if not self.compiled_rules:
            self.logger.warning("No YARA rules available for scanning")
            return detections
        
        try:
            matches = self.compiled_rules.match(file_path, timeout=timeout)
            
            for match in matches:
                detection = self._create_detection_from_match(match, file_path)
                detections.append(detection)
                
        except yara.TimeoutError:
            self.logger.warning(f"YARA scan timeout for {file_path}")
            raise DetectionError(f"YARA scan timeout: {file_path}")
        except Exception as e:
            self.logger.error(f"YARA scan failed for {file_path}: {e}")
            raise DetectionError(f"YARA scan failed: {e}")
        
        return detections
    
    def scan_data(self, data: bytes, timeout: int = 60) -> List[ThreatDetection]:
        """
        扫描二进制数据
        
        Args:
            data: 二进制数据
            timeout: 扫描超时时间（秒）
            
        Returns:
            List[ThreatDetection]: 检测结果列表
        """
        detections = []
        
        if not self.compiled_rules:
            self.logger.warning("No YARA rules available for scanning")
            return detections
        
        try:
            matches = self.compiled_rules.match(data=data, timeout=timeout)
            
            for match in matches:
                detection = self._create_detection_from_match(match, "<memory>")
                detections.append(detection)
                
        except yara.TimeoutError:
            self.logger.warning("YARA scan timeout for data")
            raise DetectionError("YARA scan timeout")
        except Exception as e:
            self.logger.error(f"YARA scan failed for data: {e}")
            raise DetectionError(f"YARA scan failed: {e}")
        
        return detections
    
    def _create_detection_from_match(self, match, source: str) -> ThreatDetection:
        """从 YARA 匹配创建威胁检测结果"""
        # 解析元数据
        metadata = {}
        if hasattr(match, 'meta'):
            metadata = {item.identifier: item.string for item in match.meta}
        
        # 提取基本信息
        threat_name = metadata.get('description', match.rule)
        threat_type = metadata.get('type', 'malware')
        author = metadata.get('author', 'Unknown')
        reference = metadata.get('reference', '')
        
        # 确定威胁等级
        threat_level = self._determine_threat_level(metadata, match.rule)
        
        # 收集匹配的字符串
        matched_strings = []
        if hasattr(match, 'strings'):
            for string_match in match.strings:
                matched_strings.append({
                    'identifier': string_match.identifier,
                    'instances': len(string_match.instances),
                    'first_offset': string_match.instances[0].offset if string_match.instances else None
                })
        
        # 构建证据
        evidence = {
            'rule_name': match.rule,
            'matched_strings': matched_strings,
            'metadata': metadata,
            'source': source,
            'yara_version': yara.__version__ if hasattr(yara, '__version__') else 'unknown'
        }
        
        # 生成 IOCs
        iocs = self._extract_iocs_from_match(match, metadata)\n        \n        # 生成缓解建议\n        mitigation = self._generate_mitigation_advice(threat_type, metadata)\n        \n        return ThreatDetection(\n            detection_id=f\"yara_{match.rule}_{hash(source) % 10000:04d}\",\n            detector_name=\"YARA\",\n            threat_name=threat_name,\n            threat_type=threat_type,\n            confidence=0.9,  # YARA 规则通常有高置信度\n            severity=threat_level,\n            description=f\"YARA rule '{match.rule}' matched. {metadata.get('description', '')}\",\n            evidence=evidence,\n            iocs=iocs,\n            mitigation=mitigation\n        )\n    \n    def _determine_threat_level(self, metadata: Dict[str, str], rule_name: str) -> ThreatLevel:\n        \"\"\"确定威胁等级\"\"\"\n        # 从元数据获取等级\n        severity = metadata.get('severity', '').lower()\n        \n        if severity in ['critical', 'high']:\n            return ThreatLevel.CRITICAL\n        elif severity == 'medium':\n            return ThreatLevel.LIKELY_MALICIOUS\n        elif severity == 'low':\n            return ThreatLevel.SUSPICIOUS\n        \n        # 基于规则名称推断\n        rule_lower = rule_name.lower()\n        \n        if any(keyword in rule_lower for keyword in ['apt', 'trojan', 'backdoor', 'rootkit']):\n            return ThreatLevel.CRITICAL\n        elif any(keyword in rule_lower for keyword in ['malware', 'virus', 'worm']):\n            return ThreatLevel.MALICIOUS\n        elif any(keyword in rule_lower for keyword in ['suspicious', 'packer', 'obfuscator']):\n            return ThreatLevel.LIKELY_MALICIOUS\n        else:\n            return ThreatLevel.SUSPICIOUS\n    \n    def _extract_iocs_from_match(self, match, metadata: Dict[str, str]) -> List[str]:\n        \"\"\"从匹配结果提取 IOCs\"\"\"\n        iocs = []\n        \n        # 从规则名称提取\n        iocs.append(f\"yara_rule:{match.rule}\")\n        \n        # 从元数据提取\n        if 'hash' in metadata:\n            iocs.append(f\"file_hash:{metadata['hash']}\")\n        if 'family' in metadata:\n            iocs.append(f\"malware_family:{metadata['family']}\")\n        \n        return iocs\n    \n    def _generate_mitigation_advice(self, threat_type: str, metadata: Dict[str, str]) -> str:\n        \"\"\"生成缓解建议\"\"\"\n        base_advice = \"立即隔离可疑文件，进行深度分析。\"\n        \n        threat_specific = {\n            'trojan': \"检查系统是否有持久化机制，扫描网络连接。\",\n            'backdoor': \"监控网络流量，检查系统账户和权限变化。\",\n            'ransomware': \"立即断网，检查备份系统，不要支付赎金。\",\n            'keylogger': \"更改所有密码，检查敏感信息泄露。\",\n            'spyware': \"检查数据泄露，审查隐私设置。\",\n            'packer': \"使用专业工具脱壳，进一步分析内部代码。\",\n            'rootkit': \"使用专业反rootkit工具，考虑重装系统。\"\n        }\n        \n        specific_advice = threat_specific.get(threat_type.lower(), \"\")\n        \n        return f\"{base_advice} {specific_advice}\".strip()\n    \n    def _create_default_rules(self):\n        \"\"\"创建默认的 YARA 规则\"\"\"\n        try:\n            self.rules_directory.mkdir(parents=True, exist_ok=True)\n            \n            # 基础恶意软件检测规则\n            basic_malware_rule = '''\nrule Basic_PE_Malware\n{\n    meta:\n        description = \"Basic PE malware detection\"\n        author = \"SecManus\"\n        type = \"malware\"\n        severity = \"medium\"\n        \n    strings:\n        $pe = { 4D 5A }  // MZ header\n        $suspicious_api1 = \"CreateRemoteThread\" ascii\n        $suspicious_api2 = \"WriteProcessMemory\" ascii\n        $suspicious_api3 = \"VirtualAllocEx\" ascii\n        \n    condition:\n        $pe at 0 and 2 of ($suspicious_api*)\n}\n\nrule High_Entropy_Section\n{\n    meta:\n        description = \"Detects sections with high entropy (possible packed/encrypted)\"\n        author = \"SecManus\"\n        type = \"packer\"\n        severity = \"low\"\n        \n    condition:\n        for any section in pe.sections : (\n            section.name == \".text\" and\n            math.entropy(section.raw_data_offset, section.raw_data_size) > 7.5\n        )\n}\n\nrule Suspicious_Import_Table\n{\n    meta:\n        description = \"Detects suspicious import combinations\"\n        author = \"SecManus\"\n        type = \"suspicious\"\n        severity = \"medium\"\n        \n    condition:\n        pe.imports(\"kernel32.dll\", \"CreateProcessA\") and\n        pe.imports(\"advapi32.dll\", \"RegCreateKeyA\") and\n        pe.imports(\"ws2_32.dll\", \"send\")\n}\n'''\n            \n            # 写入基础规则文件\n            basic_rule_path = self.rules_directory / \"basic_malware.yar\"\n            with open(basic_rule_path, 'w', encoding='utf-8') as f:\n                f.write(basic_malware_rule)\n            \n            # 网络相关恶意行为规则\n            network_malware_rule = '''\nrule Network_Backdoor\n{\n    meta:\n        description = \"Detects potential network backdoor\"\n        author = \"SecManus\"\n        type = \"backdoor\"\n        severity = \"high\"\n        \n    strings:\n        $net1 = \"WSAStartup\" ascii\n        $net2 = \"socket\" ascii\n        $net3 = \"connect\" ascii\n        $shell = \"cmd.exe\" ascii\n        $shell2 = \"/bin/sh\" ascii\n        \n    condition:\n        2 of ($net*) and 1 of ($shell*)\n}\n\nrule Keylogger_Behavior\n{\n    meta:\n        description = \"Detects potential keylogger behavior\"\n        author = \"SecManus\"\n        type = \"keylogger\"\n        severity = \"high\"\n        \n    strings:\n        $api1 = \"SetWindowsHookEx\" ascii\n        $api2 = \"GetAsyncKeyState\" ascii\n        $api3 = \"GetKeyState\" ascii\n        $log = \"keylog\" ascii nocase\n        \n    condition:\n        1 of ($api*) and ($log or filesize < 100KB)\n}\n'''\n            \n            network_rule_path = self.rules_directory / \"network_threats.yar\"\n            with open(network_rule_path, 'w', encoding='utf-8') as f:\n                f.write(network_malware_rule)\n            \n            self.logger.info(f\"Created default YARA rules in {self.rules_directory}\")\n            \n        except Exception as e:\n            self.logger.error(f\"Failed to create default rules: {e}\")\n    \n    def add_custom_rule(self, rule_name: str, rule_content: str) -> bool:\n        \"\"\"添加自定义规则\"\"\"\n        try:\n            # 验证规则语法\n            yara.compile(source=rule_content)\n            \n            # 保存规则文件\n            rule_path = self.rules_directory / f\"{rule_name}.yar\"\n            with open(rule_path, 'w', encoding='utf-8') as f:\n                f.write(rule_content)\n            \n            # 重新加载规则\n            self._load_rules()\n            \n            self.logger.info(f\"Added custom rule: {rule_name}\")\n            return True\n            \n        except Exception as e:\n            self.logger.error(f\"Failed to add custom rule {rule_name}: {e}\")\n            return False\n    \n    def get_rule_info(self) -> Dict[str, Any]:\n        \"\"\"获取规则信息\"\"\"\n        info = {\n            'rules_directory': str(self.rules_directory),\n            'rules_loaded': bool(self.compiled_rules),\n            'rule_files': []\n        }\n        \n        if self.rules_directory.exists():\n            for rule_path in self.rules_directory.glob(\"*.yar*\"):\n                try:\n                    stat = rule_path.stat()\n                    info['rule_files'].append({\n                        'name': rule_path.name,\n                        'size': stat.st_size,\n                        'modified': stat.st_mtime\n                    })\n                except Exception:\n                    continue\n        \n        return info
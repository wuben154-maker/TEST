"""
文件解析工具模块

支持多种二进制文件格式的解析：
- PE (Portable Executable) - Windows
- ELF (Executable and Linkable Format) - Linux
- Mach-O - macOS
- 其他格式
"""

import os
import hashlib
import magic
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

try:
    import lief
    LIEF_AVAILABLE = True
except ImportError:
    LIEF_AVAILABLE = False
    logging.warning("LIEF library not available. Some parsing features will be disabled.")

try:
    import pefile
    PE_AVAILABLE = True
except ImportError:
    PE_AVAILABLE = False
    logging.warning("pefile library not available. PE parsing will use LIEF only.")

from ..core.models import (
    BasicFileInfo, FileType, SectionInfo, ImportedFunction, 
    ExportedFunction, FileParsingError
)


class FileParser:
    """文件解析器类"""
    
    def __init__(self):
        """初始化文件解析器"""
        self.logger = logging.getLogger(__name__)
        self._magic = magic.Magic(mime=True) if hasattr(magic, 'Magic') else None
        
    def parse_file(self, file_path: str) -> BasicFileInfo:
        """
        解析文件基本信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            BasicFileInfo: 基本文件信息
            
        Raises:
            FileParsingError: 文件解析失败
        """
        try:
            if not os.path.exists(file_path):
                raise FileParsingError(f"File not found: {file_path}")
            
            # 获取文件统计信息
            file_stat = os.stat(file_path)
            file_size = file_stat.st_size
            created_time = datetime.fromtimestamp(file_stat.st_ctime)
            modified_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            # 计算文件哈希
            hashes = self._calculate_hashes(file_path)
            
            # 检测文件类型
            file_type = self._detect_file_type(file_path)
            
            # 检测架构
            architecture = self._detect_architecture(file_path, file_type)
            
            return BasicFileInfo(
                file_name=os.path.basename(file_path),
                file_path=file_path,
                file_size=file_size,
                file_type=file_type,
                architecture=architecture,
                md5=hashes['md5'],
                sha1=hashes['sha1'],
                sha256=hashes['sha256'],
                created_time=created_time,
                modified_time=modified_time
            )
            
        except Exception as e:
            self.logger.error(f"Failed to parse file {file_path}: {e}")
            raise FileParsingError(f"Failed to parse file: {e}")
    
    def parse_sections(self, file_path: str) -> List[SectionInfo]:
        """
        解析文件节区信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[SectionInfo]: 节区信息列表
        """
        sections = []
        
        if not LIEF_AVAILABLE:
            self.logger.warning("LIEF not available, cannot parse sections")
            return sections
            
        try:
            binary = lief.parse(file_path)
            if not binary:
                self.logger.warning(f"Failed to parse binary: {file_path}")
                return sections
            
            for section in binary.sections:
                # 计算节区熵值
                entropy = self._calculate_entropy(section.content)
                
                # 获取权限信息
                permissions = self._get_section_permissions(section)
                
                # 获取特征信息
                characteristics = self._get_section_characteristics(section)
                
                section_info = SectionInfo(
                    name=section.name,
                    virtual_address=section.virtual_address,
                    virtual_size=section.virtual_size,
                    raw_size=section.size,
                    entropy=entropy,
                    permissions=permissions,
                    characteristics=characteristics,
                    is_executable='execute' in permissions,
                    contains_code=self._section_contains_code(section, entropy)
                )
                
                sections.append(section_info)
                
        except Exception as e:
            self.logger.error(f"Failed to parse sections: {e}")
            
        return sections
    
    def parse_imports(self, file_path: str) -> List[ImportedFunction]:
        """
        解析导入函数信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[ImportedFunction]: 导入函数列表
        """
        imports = []
        
        if not LIEF_AVAILABLE:
            return imports
            
        try:
            binary = lief.parse(file_path)
            if not binary:
                return imports
            
            if hasattr(binary, 'imports'):
                for import_lib in binary.imports:
                    lib_name = import_lib.name if hasattr(import_lib, 'name') else "unknown"
                    
                    # 获取库中的函数
                    if hasattr(import_lib, 'entries'):
                        for entry in import_lib.entries:
                            func_name = entry.name if hasattr(entry, 'name') else f"ord_{entry.ordinal}"
                            ordinal = getattr(entry, 'ordinal', None)
                            
                            # 分析函数风险等级
                            is_suspicious, risk_level, description = self._analyze_import_risk(func_name, lib_name)
                            
                            import_func = ImportedFunction(
                                function_name=func_name,
                                library_name=lib_name,
                                ordinal=ordinal,
                                is_suspicious=is_suspicious,
                                risk_level=risk_level,
                                description=description
                            )
                            
                            imports.append(import_func)
                            
        except Exception as e:
            self.logger.error(f"Failed to parse imports: {e}")
            
        return imports
    
    def parse_exports(self, file_path: str) -> List[ExportedFunction]:
        """
        解析导出函数信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            List[ExportedFunction]: 导出函数列表
        """
        exports = []
        
        if not LIEF_AVAILABLE:
            return exports
            
        try:
            binary = lief.parse(file_path)
            if not binary:
                return exports
            
            if hasattr(binary, 'exported_functions'):
                for export in binary.exported_functions:
                    export_func = ExportedFunction(
                        function_name=export.name,
                        address=export.address,
                        ordinal=getattr(export, 'ordinal', None),
                        is_forwarded=getattr(export, 'is_forwarded', False),
                        forward_name=getattr(export, 'forward_name', None)
                    )
                    exports.append(export_func)
                    
        except Exception as e:
            self.logger.error(f"Failed to parse exports: {e}")
            
        return exports
    
    def _calculate_hashes(self, file_path: str) -> Dict[str, str]:
        """计算文件哈希值"""
        hashes = {'md5': '', 'sha1': '', 'sha256': ''}
        
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                
            hashes['md5'] = hashlib.md5(content).hexdigest()
            hashes['sha1'] = hashlib.sha1(content).hexdigest()
            hashes['sha256'] = hashlib.sha256(content).hexdigest()
            
        except Exception as e:
            self.logger.error(f"Failed to calculate hashes: {e}")
            
        return hashes
    
    def _detect_file_type(self, file_path: str) -> FileType:
        """检测文件类型"""
        try:
            # 尝试使用 magic
            if self._magic:
                mime_type = self._magic.from_file(file_path)
                if 'application/x-executable' in mime_type or 'application/x-pie-executable' in mime_type:
                    return FileType.ELF
                elif 'application/x-dosexec' in mime_type:
                    return FileType.PE
                elif 'application/x-mach-binary' in mime_type:
                    return FileType.MACH_O
            
            # 通过文件头判断
            with open(file_path, 'rb') as f:
                header = f.read(8)
                
            if header[:2] == b'MZ':
                return FileType.PE
            elif header[:4] == b'\x7fELF':
                return FileType.ELF
            elif header[:4] in [b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', 
                               b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe']:
                return FileType.MACH_O
            elif header[:4] == b'\xca\xfe\xba\xbe':
                return FileType.JAVA_CLASS
            elif header[:4] == b'\x03\xf3\x0d\x0a':
                return FileType.PYTHON_PYC
            elif header[:8] == b'dex\n035\x00':
                return FileType.ANDROID_DEX
                
        except Exception as e:
            self.logger.error(f"Failed to detect file type: {e}")
            
        return FileType.UNKNOWN
    
    def _detect_architecture(self, file_path: str, file_type: FileType) -> str:
        """检测文件架构"""
        if not LIEF_AVAILABLE:
            return "unknown"
            
        try:
            binary = lief.parse(file_path)
            if not binary:
                return "unknown"
            
            if file_type == FileType.PE:
                machine = getattr(binary.header, 'machine', None)
                if machine == lief.PE.MACHINE_TYPES.AMD64:
                    return "x64"
                elif machine == lief.PE.MACHINE_TYPES.I386:
                    return "x86"
                elif machine == lief.PE.MACHINE_TYPES.ARM64:
                    return "arm64"
                elif machine == lief.PE.MACHINE_TYPES.ARM:
                    return "arm"
                    
            elif file_type == FileType.ELF:
                machine = getattr(binary.header, 'machine_type', None)
                if machine == lief.ELF.ARCH.x86_64:
                    return "x64"
                elif machine == lief.ELF.ARCH.i386:
                    return "x86"
                elif machine == lief.ELF.ARCH.ARM:
                    return "arm"
                elif machine == lief.ELF.ARCH.AARCH64:
                    return "arm64"
                    
            elif file_type == FileType.MACH_O:
                cpu_type = getattr(binary.header, 'cpu_type', None)
                if cpu_type == lief.MachO.CPU_TYPES.x86_64:
                    return "x64"
                elif cpu_type == lief.MachO.CPU_TYPES.x86:
                    return "x86"
                elif cpu_type == lief.MachO.CPU_TYPES.ARM64:
                    return "arm64"
                elif cpu_type == lief.MachO.CPU_TYPES.ARM:
                    return "arm"
                    
        except Exception as e:
            self.logger.error(f"Failed to detect architecture: {e}")
            
        return "unknown"
    
    def _calculate_entropy(self, data: bytes) -> float:
        """计算数据熵值"""
        if not data:
            return 0.0
            
        # 统计字节频率
        byte_counts = [0] * 256
        for byte in data:
            byte_counts[byte] += 1
            
        # 计算熵值
        entropy = 0.0
        data_len = len(data)
        
        for count in byte_counts:
            if count > 0:
                freq = count / data_len
                entropy -= freq * (freq.bit_length() - 1)
                
        return entropy / 8.0  # 标准化到0-1
    
    def _get_section_permissions(self, section) -> List[str]:
        """获取节区权限"""
        permissions = []
        
        if hasattr(section, 'characteristics'):
            chars = section.characteristics
            # PE 文件节区特征
            if hasattr(chars, 'IMAGE_SCN_MEM_READ') and chars & 0x40000000:
                permissions.append('read')
            if hasattr(chars, 'IMAGE_SCN_MEM_WRITE') and chars & 0x80000000:
                permissions.append('write')
            if hasattr(chars, 'IMAGE_SCN_MEM_EXECUTE') and chars & 0x20000000:
                permissions.append('execute')
        elif hasattr(section, 'flags'):
            # ELF 文件节区标志
            flags = section.flags
            if flags & 0x4:  # SHF_EXECINSTR
                permissions.append('execute')
            if flags & 0x1:  # SHF_WRITE
                permissions.append('write')
            # ELF 节区默认可读
            permissions.append('read')
            
        return permissions if permissions else ['read']
    
    def _get_section_characteristics(self, section) -> List[str]:
        """获取节区特征"""
        characteristics = []
        
        if hasattr(section, 'name'):
            name = section.name.lower()
            if '.text' in name or '.code' in name:
                characteristics.append('code')
            elif '.data' in name:
                characteristics.append('data')
            elif '.bss' in name:
                characteristics.append('uninitialized_data')
            elif '.rdata' in name or '.rodata' in name:
                characteristics.append('readonly_data')
            elif '.rsrc' in name or '.resource' in name:
                characteristics.append('resources')
            elif '.reloc' in name:
                characteristics.append('relocations')
            elif '.import' in name or '.idata' in name:
                characteristics.append('imports')
            elif '.export' in name or '.edata' in name:
                characteristics.append('exports')
                
        return characteristics
    
    def _section_contains_code(self, section, entropy: float) -> bool:
        """判断节区是否包含代码"""
        # 基于名称判断
        if hasattr(section, 'name'):
            name = section.name.lower()
            if any(keyword in name for keyword in ['.text', '.code', '_text']):
                return True
                
        # 基于权限判断
        permissions = self._get_section_permissions(section)
        if 'execute' in permissions:
            return True
            
        # 基于熵值判断（代码段通常熵值适中）
        if 0.3 < entropy < 0.8:
            return True
            
        return False
    
    def _analyze_import_risk(self, func_name: str, lib_name: str) -> tuple:
        """分析导入函数风险等级"""
        # 高风险函数列表
        high_risk_functions = {
            'CreateRemoteThread', 'WriteProcessMemory', 'VirtualAllocEx', 
            'SetWindowsHookEx', 'CreateProcess', 'WinExec', 'ShellExecute',
            'RegCreateKey', 'RegSetValue', 'CryptAcquireContext', 'CryptEncrypt',
            'InternetOpen', 'InternetConnect', 'HttpOpenRequest', 'recv', 'send'
        }
        
        # 中风险函数列表
        medium_risk_functions = {
            'VirtualAlloc', 'VirtualProtect', 'LoadLibrary', 'GetProcAddress',
            'CreateFile', 'WriteFile', 'ReadFile', 'CreateThread', 'Sleep',
            'GetTickCount', 'GetSystemTime', 'GetComputerName'
        }
        
        func_lower = func_name.lower()
        
        # 检查高风险
        for risk_func in high_risk_functions:
            if risk_func.lower() in func_lower:
                return True, "high", f"High-risk API: {func_name}"
                
        # 检查中风险
        for risk_func in medium_risk_functions:
            if risk_func.lower() in func_lower:
                return True, "medium", f"Medium-risk API: {func_name}"
                
        # 检查库风险
        if lib_name.lower() in ['ntdll.dll', 'kernel32.dll', 'advapi32.dll']:
            if any(keyword in func_lower for keyword in ['nt', 'zw', 'rtl']):
                return True, "medium", f"Low-level system API: {func_name}"
                
        return False, "low", f"Standard API: {func_name}"
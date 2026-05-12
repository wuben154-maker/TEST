"""
反汇编引擎模块

基于 Capstone 引擎提供多架构反汇编支持
"""

import logging
from typing import List, Dict, Optional, Set, Tuple
from collections import defaultdict

try:
    import capstone as cs
    CAPSTONE_AVAILABLE = True
except ImportError:
    CAPSTONE_AVAILABLE = False
    logging.warning("Capstone library not available. Disassembly features will be disabled.")

try:
    import lief
    LIEF_AVAILABLE = True
except ImportError:
    LIEF_AVAILABLE = False

from ..core.models import (
    Instruction, BasicBlock, FunctionInfo, FileType, 
    DisassemblyError, AnalysisConfig
)


class DisassemblerEngine:
    """反汇编引擎类"""
    
    def __init__(self, file_type: FileType, architecture: str):
        """
        初始化反汇编引擎
        
        Args:
            file_type: 文件类型
            architecture: 目标架构
        """
        self.file_type = file_type
        self.architecture = architecture
        self.logger = logging.getLogger(__name__)
        
        if not CAPSTONE_AVAILABLE:
            raise DisassemblyError("Capstone library not available")
            
        # 初始化 Capstone 引擎
        self.disasm = self._init_capstone_engine()
        self.disasm.detail = True  # 启用详细分析
        
        # 缓存
        self._instruction_cache = {}
        self._function_cache = {}
        
    def _init_capstone_engine(self):
        """初始化 Capstone 反汇编引擎"""
        arch_map = {
            ('x86', FileType.PE): (cs.CS_ARCH_X86, cs.CS_MODE_32),
            ('x64', FileType.PE): (cs.CS_ARCH_X86, cs.CS_MODE_64),
            ('x86', FileType.ELF): (cs.CS_ARCH_X86, cs.CS_MODE_32),
            ('x64', FileType.ELF): (cs.CS_ARCH_X86, cs.CS_MODE_64),
            ('arm', FileType.ELF): (cs.CS_ARCH_ARM, cs.CS_MODE_ARM),
            ('arm64', FileType.ELF): (cs.CS_ARCH_ARM64, cs.CS_MODE_ARM),
            ('x64', FileType.MACH_O): (cs.CS_ARCH_X86, cs.CS_MODE_64),
            ('arm64', FileType.MACH_O): (cs.CS_ARCH_ARM64, cs.CS_MODE_ARM),
        }
        
        key = (self.architecture, self.file_type)
        if key not in arch_map:
            self.logger.warning(f"Unsupported architecture/file type: {key}")
            # 默认使用 x64
            arch, mode = cs.CS_ARCH_X86, cs.CS_MODE_64
        else:
            arch, mode = arch_map[key]
            
        return cs.Cs(arch, mode)
    
    def disassemble_data(self, data: bytes, base_address: int = 0, 
                        max_instructions: int = 10000) -> List[Instruction]:
        """
        反汇编二进制数据
        
        Args:
            data: 二进制数据
            base_address: 基地址
            max_instructions: 最大指令数限制
            
        Returns:
            List[Instruction]: 指令列表
        """
        instructions = []
        
        try:
            count = 0
            for insn in self.disasm.disasm(data, base_address):
                if count >= max_instructions:
                    self.logger.warning(f"Reached maximum instruction limit: {max_instructions}")
                    break
                    
                instruction = self._create_instruction(insn)
                instructions.append(instruction)
                count += 1
                
        except Exception as e:
            self.logger.error(f"Disassembly failed: {e}")
            raise DisassemblyError(f"Failed to disassemble data: {e}")
            
        return instructions
    
    def disassemble_function(self, binary_path: str, func_address: int, 
                           config: Optional[AnalysisConfig] = None) -> FunctionInfo:
        """
        反汇编单个函数
        
        Args:
            binary_path: 二进制文件路径
            func_address: 函数地址
            config: 分析配置
            
        Returns:
            FunctionInfo: 函数信息
        """
        if config is None:
            config = AnalysisConfig()
            
        # 检查缓存
        cache_key = f"{binary_path}:{func_address}"
        if cache_key in self._function_cache:
            return self._function_cache[cache_key]
            
        try:
            # 读取函数数据
            func_data = self._extract_function_data(binary_path, func_address)
            if not func_data:
                raise DisassemblyError(f"Cannot extract function data at 0x{func_address:x}")
            
            # 反汇编指令
            instructions = self.disassemble_data(
                func_data, 
                func_address, 
                config.max_disasm_instructions
            )
            
            # 构建基本块
            basic_blocks = self._build_basic_blocks(instructions)
            
            # 分析函数调用
            called_functions, api_calls = self._analyze_function_calls(instructions)
            
            # 计算复杂度
            complexity_score = self._calculate_complexity(basic_blocks, instructions)
            
            # 检查可疑行为
            is_suspicious = self._detect_suspicious_patterns(instructions, api_calls)
            
            func_info = FunctionInfo(
                address=func_address,
                name=f"sub_{func_address:x}",
                size=len(func_data),
                basic_blocks=basic_blocks,
                called_functions=called_functions,
                calling_functions=[],  # 需要全局分析才能填充
                api_calls=api_calls,
                complexity_score=complexity_score,
                is_suspicious=is_suspicious
            )
            
            # 缓存结果
            self._function_cache[cache_key] = func_info
            return func_info
            
        except Exception as e:
            self.logger.error(f"Failed to disassemble function at 0x{func_address:x}: {e}")
            raise DisassemblyError(f"Function disassembly failed: {e}")
    
    def find_functions(self, binary_path: str) -> List[int]:
        """
        查找所有函数入口点
        
        Args:
            binary_path: 二进制文件路径
            
        Returns:
            List[int]: 函数地址列表
        """
        function_addresses = set()
        
        try:
            if not LIEF_AVAILABLE:
                self.logger.warning("LIEF not available, using heuristic function detection")
                return self._find_functions_heuristic(binary_path)
            
            # 使用 LIEF 获取符号信息
            binary = lief.parse(binary_path)
            if binary:
                # 从符号表获取
                if hasattr(binary, 'symbols'):
                    for symbol in binary.symbols:
                        if (hasattr(symbol, 'type') and 
                            str(symbol.type).endswith('FUNCTION') and
                            hasattr(symbol, 'value')):
                            function_addresses.add(symbol.value)
                
                # 从导出表获取
                if hasattr(binary, 'exported_functions'):
                    for export in binary.exported_functions:
                        if hasattr(export, 'address'):
                            function_addresses.add(export.address)
                
                # 获取入口点
                if hasattr(binary, 'entrypoint'):
                    function_addresses.add(binary.entrypoint)
            
            # 启发式查找补充
            heuristic_functions = self._find_functions_heuristic(binary_path)
            function_addresses.update(heuristic_functions)
            
        except Exception as e:
            self.logger.error(f"Failed to find functions: {e}")
            
        return sorted(list(function_addresses))
    
    def _create_instruction(self, capstone_insn) -> Instruction:
        """从 Capstone 指令创建 Instruction 对象"""
        # 分析指令类型
        is_call = capstone_insn.group(cs.CS_GRP_CALL) if hasattr(capstone_insn, 'group') else False
        is_jump = capstone_insn.group(cs.CS_GRP_JUMP) if hasattr(capstone_insn, 'group') else False
        is_conditional = capstone_insn.group(cs.CS_GRP_BRANCH_RELATIVE) if hasattr(capstone_insn, 'group') else False
        
        # 获取目标地址
        target_address = None
        if is_call or is_jump:
            for operand in capstone_insn.operands:
                if operand.type == cs.CS_OP_IMM:
                    target_address = operand.value.imm
                    break
        
        return Instruction(
            address=capstone_insn.address,
            mnemonic=capstone_insn.mnemonic,
            operands=capstone_insn.op_str,
            bytes=capstone_insn.bytes,
            size=capstone_insn.size,
            is_call=is_call,
            is_jump=is_jump,
            is_conditional=is_conditional,
            target_address=target_address
        )
    
    def _build_basic_blocks(self, instructions: List[Instruction]) -> List[BasicBlock]:
        """构建基本块"""
        if not instructions:
            return []
            
        basic_blocks = []
        
        # 识别基本块边界
        block_starts = set()
        block_starts.add(instructions[0].address)
        
        for insn in instructions:
            # 跳转目标是新基本块的开始
            if insn.target_address:
                block_starts.add(insn.target_address)
            
            # 跳转指令后的指令是新基本块的开始
            if insn.is_jump or insn.is_call:
                next_addr = insn.address + insn.size
                if any(i.address == next_addr for i in instructions):
                    block_starts.add(next_addr)
        
        # 按地址排序
        sorted_starts = sorted(block_starts)
        
        # 构建基本块
        for i, start_addr in enumerate(sorted_starts):
            end_addr = sorted_starts[i + 1] if i + 1 < len(sorted_starts) else instructions[-1].address + instructions[-1].size
            
            # 收集该基本块的指令
            block_instructions = [
                insn for insn in instructions 
                if start_addr <= insn.address < end_addr
            ]
            
            if block_instructions:
                basic_block = BasicBlock(
                    start_address=start_addr,
                    end_address=block_instructions[-1].address + block_instructions[-1].size,
                    instructions=block_instructions
                )
                basic_blocks.append(basic_block)
        
        # 计算基本块之间的关系
        self._calculate_block_relationships(basic_blocks)
        
        return basic_blocks
    
    def _calculate_block_relationships(self, basic_blocks: List[BasicBlock]):
        """计算基本块之间的前驱后继关系"""
        # 创建地址到基本块的映射
        addr_to_block = {bb.start_address: bb for bb in basic_blocks}
        
        for bb in basic_blocks:
            if not bb.instructions:
                continue
                
            last_insn = bb.instructions[-1]
            
            # 直接跳转关系
            if last_insn.target_address and last_insn.target_address in addr_to_block:
                target_bb = addr_to_block[last_insn.target_address]
                bb.successors.append(target_bb.start_address)
                target_bb.predecessors.append(bb.start_address)
            
            # 顺序执行关系（非无条件跳转）
            if not last_insn.is_jump or last_insn.is_conditional:
                next_addr = last_insn.address + last_insn.size
                if next_addr in addr_to_block:
                    target_bb = addr_to_block[next_addr]
                    bb.successors.append(target_bb.start_address)
                    target_bb.predecessors.append(bb.start_address)
    
    def _analyze_function_calls(self, instructions: List[Instruction]) -> Tuple[List[int], List[str]]:
        """分析函数调用"""
        called_functions = []
        api_calls = []
        
        for insn in instructions:
            if insn.is_call and insn.target_address:
                called_functions.append(insn.target_address)
                
                # 尝试识别 API 调用
                api_name = self._resolve_api_name(insn.target_address, insn.operands)
                if api_name:
                    api_calls.append(api_name)
        
        return called_functions, api_calls
    
    def _resolve_api_name(self, address: int, operands: str) -> Optional[str]:
        """解析 API 名称（简化实现）"""
        # 这里可以集成符号信息或导入表来解析真实的API名称
        # 简化实现：直接返回地址
        if 'dword ptr' in operands.lower():
            return f"api_call_0x{address:x}"
        return None
    
    def _calculate_complexity(self, basic_blocks: List[BasicBlock], 
                            instructions: List[Instruction]) -> float:
        """计算函数复杂度（基于圈复杂度）"""
        if not basic_blocks:
            return 0.0
        
        # 圈复杂度 = E - N + 2P
        # E = 边数, N = 节点数, P = 连通分量数
        
        nodes = len(basic_blocks)
        edges = sum(len(bb.successors) for bb in basic_blocks)
        components = 1  # 假设函数是连通的
        
        cyclomatic_complexity = edges - nodes + 2 * components
        
        # 标准化到0-1范围（经验公式）
        normalized = min(cyclomatic_complexity / 50.0, 1.0)
        
        return normalized
    
    def _detect_suspicious_patterns(self, instructions: List[Instruction], 
                                   api_calls: List[str]) -> bool:
        """检测可疑模式"""
        suspicious_indicators = []
        
        # 检查可疑API调用模式
        suspicious_apis = {
            'CreateRemoteThread', 'WriteProcessMemory', 'VirtualAllocEx',
            'SetWindowsHookEx', 'CreateProcess', 'RegCreateKey'
        }
        
        for api in api_calls:
            if any(sus_api.lower() in api.lower() for sus_api in suspicious_apis):
                suspicious_indicators.append(f"Suspicious API: {api}")
        
        # 检查代码模式
        if len(instructions) > 1000:
            suspicious_indicators.append("Large function size")
        
        # 检查混淆模式
        nop_count = sum(1 for insn in instructions if insn.mnemonic.lower() == 'nop')
        if nop_count > len(instructions) * 0.1:
            suspicious_indicators.append("High NOP density")
        
        return len(suspicious_indicators) > 0
    
    def _extract_function_data(self, binary_path: str, func_address: int, 
                             max_size: int = 4096) -> Optional[bytes]:
        """提取函数数据"""
        try:
            with open(binary_path, 'rb') as f:
                # 这是简化实现，实际需要考虑虚拟地址到文件偏移的映射
                f.seek(func_address)
                data = f.read(max_size)
                return data
        except Exception as e:
            self.logger.error(f"Failed to extract function data: {e}")
            return None
    
    def _find_functions_heuristic(self, binary_path: str) -> List[int]:
        """启发式函数查找"""
        functions = []
        
        try:
            with open(binary_path, 'rb') as f:
                data = f.read()
            
            # 查找函数序言模式 (x86/x64)
            if self.architecture in ['x86', 'x64']:
                # 常见函数序言
                prologues = [
                    b'\x55\x8b\xec',           # push ebp; mov ebp, esp
                    b'\x48\x89\x5c\x24',       # mov [rsp+x], rbx
                    b'\x40\x53',               # push rbx (x64)
                    b'\x48\x83\xec',           # sub rsp, x
                ]
                
                for prologue in prologues:
                    offset = 0
                    while True:
                        offset = data.find(prologue, offset)
                        if offset == -1:
                            break
                        functions.append(offset)
                        offset += len(prologue)
            
        except Exception as e:
            self.logger.error(f"Heuristic function finding failed: {e}")
        
        return sorted(list(set(functions)))  # 去重并排序
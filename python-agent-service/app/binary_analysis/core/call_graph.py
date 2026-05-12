"""
调用图构建模块

分析程序的函数调用关系并构建调用图
"""

import logging
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict, deque
import networkx as nx

from ..core.models import (
    CallGraph, CallGraphNode, CallGraphEdge, FunctionInfo, 
    Instruction, AnalysisConfig
)
from ..core.disassembler import DisassemblerEngine


class CallGraphBuilder:
    """调用图构建器"""
    
    def __init__(self, disassembler: DisassemblerEngine):
        """
        初始化调用图构建器
        
        Args:
            disassembler: 反汇编引擎实例
        """
        self.disassembler = disassembler
        self.logger = logging.getLogger(__name__)
        
        # 内部状态
        self._function_cache = {}
        self._call_relationships = defaultdict(set)
        self._reverse_call_relationships = defaultdict(set)
    
    def build_call_graph(self, binary_path: str, 
                        config: Optional[AnalysisConfig] = None) -> CallGraph:
        """
        构建完整的调用图
        
        Args:
            binary_path: 二进制文件路径
            config: 分析配置
            
        Returns:
            CallGraph: 完整的调用图
        """
        if config is None:
            config = AnalysisConfig()
            
        self.logger.info(f"Building call graph for {binary_path}")
        
        try:
            # 1. 查找所有函数
            function_addresses = self.disassembler.find_functions(binary_path)
            self.logger.info(f"Found {len(function_addresses)} functions")
            
            if not function_addresses:
                return CallGraph()
            
            # 2. 分析每个函数
            functions_info = {}
            for addr in function_addresses:
                try:
                    func_info = self.disassembler.disassemble_function(
                        binary_path, addr, config
                    )
                    functions_info[addr] = func_info
                    
                    # 记录调用关系
                    for called_addr in func_info.called_functions:
                        self._call_relationships[addr].add(called_addr)
                        self._reverse_call_relationships[called_addr].add(addr)
                        
                except Exception as e:
                    self.logger.warning(f"Failed to analyze function at 0x{addr:x}: {e}")
                    continue
            
            # 3. 更新函数的调用关系信息
            for addr, func_info in functions_info.items():
                func_info.calling_functions = list(self._reverse_call_relationships[addr])
            
            # 4. 构建调用图
            call_graph = self._create_call_graph(functions_info)
            
            # 5. 计算复杂度指标
            call_graph.complexity_score = self._calculate_graph_complexity(call_graph)
            
            self.logger.info(f"Call graph built successfully: {len(call_graph.nodes)} nodes, {len(call_graph.edges)} edges")
            return call_graph
            
        except Exception as e:
            self.logger.error(f"Failed to build call graph: {e}")
            return CallGraph()
    
    def build_partial_call_graph(self, binary_path: str, root_functions: List[int],
                                max_depth: int = 5) -> CallGraph:
        """
        构建部分调用图（从指定根函数开始）
        
        Args:
            binary_path: 二进制文件路径
            root_functions: 根函数地址列表
            max_depth: 最大深度
            
        Returns:
            CallGraph: 部分调用图
        """
        self.logger.info(f"Building partial call graph from {len(root_functions)} root functions")
        
        visited_functions = set()
        functions_info = {}
        
        # BFS 遍历
        queue = deque([(addr, 0) for addr in root_functions])
        
        while queue:
            func_addr, depth = queue.popleft()
            
            if func_addr in visited_functions or depth > max_depth:
                continue
                
            visited_functions.add(func_addr)
            
            try:
                # 分析函数
                func_info = self.disassembler.disassemble_function(binary_path, func_addr)
                functions_info[func_addr] = func_info
                
                # 添加被调用的函数到队列
                for called_addr in func_info.called_functions:
                    if called_addr not in visited_functions:
                        queue.append((called_addr, depth + 1))
                        
                # 记录调用关系
                for called_addr in func_info.called_functions:
                    self._call_relationships[func_addr].add(called_addr)
                    self._reverse_call_relationships[called_addr].add(func_addr)
                    
            except Exception as e:
                self.logger.warning(f"Failed to analyze function at 0x{func_addr:x}: {e}")
                continue
        
        # 更新反向调用关系
        for addr, func_info in functions_info.items():
            func_info.calling_functions = list(self._reverse_call_relationships[addr])
        
        # 构建调用图
        call_graph = self._create_call_graph(functions_info)
        call_graph.entry_points = root_functions
        
        return call_graph
    
    def find_call_chains(self, call_graph: CallGraph, start_func: int, 
                        end_func: int, max_length: int = 10) -> List[List[int]]:
        """
        查找两个函数之间的调用链
        
        Args:
            call_graph: 调用图
            start_func: 起始函数地址
            end_func: 结束函数地址
            max_length: 最大路径长度
            
        Returns:
            List[List[int]]: 调用链列表
        """
        # 构建 NetworkX 图
        G = nx.DiGraph()
        
        for edge in call_graph.edges:
            G.add_edge(edge.source, edge.target)
        
        try:
            # 查找所有简单路径
            paths = list(nx.all_simple_paths(
                G, start_func, end_func, cutoff=max_length
            ))
            return paths
            
        except nx.NetworkXNoPath:
            return []
        except Exception as e:
            self.logger.error(f"Failed to find call chains: {e}")
            return []
    
    def find_recursive_functions(self, call_graph: CallGraph) -> List[int]:
        """
        查找递归函数
        
        Args:
            call_graph: 调用图
            
        Returns:
            List[int]: 递归函数地址列表
        """
        recursive_functions = []
        
        # 构建 NetworkX 图
        G = nx.DiGraph()
        for edge in call_graph.edges:
            G.add_edge(edge.source, edge.target)
        
        # 查找强连通分量
        try:
            sccs = list(nx.strongly_connected_components(G))
            for scc in sccs:
                if len(scc) > 1:
                    # 多个函数组成的循环
                    recursive_functions.extend(scc)
                elif len(scc) == 1:
                    # 自递归
                    func_addr = list(scc)[0]
                    if G.has_edge(func_addr, func_addr):
                        recursive_functions.append(func_addr)
                        
        except Exception as e:
            self.logger.error(f"Failed to find recursive functions: {e}")
        
        return recursive_functions
    
    def analyze_call_patterns(self, call_graph: CallGraph) -> Dict[str, any]:
        """
        分析调用模式
        
        Args:
            call_graph: 调用图
            
        Returns:
            Dict: 分析结果
        """
        analysis = {
            'total_functions': len(call_graph.nodes),
            'total_calls': len(call_graph.edges),
            'entry_points': len(call_graph.entry_points),
            'leaf_functions': 0,
            'hub_functions': [],
            'isolated_functions': [],
            'max_call_depth': 0,
            'average_fan_out': 0.0,
            'average_fan_in': 0.0
        }
        
        try:
            # 构建度统计
            in_degrees = defaultdict(int)
            out_degrees = defaultdict(int)
            
            for edge in call_graph.edges:
                out_degrees[edge.source] += 1
                in_degrees[edge.target] += 1
            
            # 分析各种函数类型
            leaf_functions = []
            hub_functions = []
            isolated_functions = []
            
            for node in call_graph.nodes:
                addr = node.address
                in_deg = in_degrees[addr]
                out_deg = out_degrees[addr]
                
                # 叶子函数（不调用其他函数）
                if out_deg == 0:
                    leaf_functions.append(addr)
                
                # 中心函数（高度连接的节点）
                if in_deg > 5 or out_deg > 10:
                    hub_functions.append({
                        'address': addr,
                        'in_degree': in_deg,
                        'out_degree': out_deg
                    })
                
                # 孤立函数（既不调用也不被调用）
                if in_deg == 0 and out_deg == 0:
                    isolated_functions.append(addr)
            
            # 计算统计信息
            analysis['leaf_functions'] = len(leaf_functions)
            analysis['hub_functions'] = hub_functions
            analysis['isolated_functions'] = isolated_functions
            
            if call_graph.nodes:
                total_in = sum(in_degrees.values())
                total_out = sum(out_degrees.values())
                analysis['average_fan_in'] = total_in / len(call_graph.nodes)
                analysis['average_fan_out'] = total_out / len(call_graph.nodes)
            
            # 计算最大调用深度
            if call_graph.entry_points:
                G = nx.DiGraph()
                for edge in call_graph.edges:
                    G.add_edge(edge.source, edge.target)
                
                max_depth = 0
                for entry in call_graph.entry_points:
                    try:
                        depths = nx.single_source_shortest_path_length(G, entry)
                        if depths:
                            max_depth = max(max_depth, max(depths.values()))
                    except:
                        continue
                
                analysis['max_call_depth'] = max_depth
            
        except Exception as e:
            self.logger.error(f"Failed to analyze call patterns: {e}")
        
        return analysis
    
    def _create_call_graph(self, functions_info: Dict[int, FunctionInfo]) -> CallGraph:
        """从函数信息创建调用图"""
        nodes = []
        edges = []
        entry_points = []
        
        # 创建节点
        for addr, func_info in functions_info.items():
            node = CallGraphNode(
                address=addr,
                function_name=func_info.name,
                call_count=len(func_info.called_functions),
                called_by_count=len(func_info.calling_functions),
                is_entry_point=len(func_info.calling_functions) == 0,
                is_suspicious=func_info.is_suspicious
            )
            nodes.append(node)
            
            if node.is_entry_point:
                entry_points.append(addr)
        
        # 创建边
        call_counts = defaultdict(int)
        for source_addr, func_info in functions_info.items():
            for target_addr in func_info.called_functions:
                call_counts[(source_addr, target_addr)] += 1
        
        for (source, target), count in call_counts.items():
            edge = CallGraphEdge(
                source=source,
                target=target,
                call_count=count,
                edge_type="direct"
            )
            edges.append(edge)
        
        return CallGraph(
            nodes=nodes,
            edges=edges,
            entry_points=entry_points
        )
    
    def _calculate_graph_complexity(self, call_graph: CallGraph) -> float:
        """计算调用图复杂度"""
        if not call_graph.nodes:
            return 0.0
        
        try:
            nodes = len(call_graph.nodes)
            edges = len(call_graph.edges)
            
            # 基于图的密度和圈复杂度计算
            density = edges / (nodes * (nodes - 1)) if nodes > 1 else 0
            
            # 构建 NetworkX 图计算圈复杂度
            G = nx.DiGraph()
            for edge in call_graph.edges:
                G.add_edge(edge.source, edge.target)
            
            # 圈复杂度 = E - N + 2P (P为连通分量数)
            connected_components = nx.number_weakly_connected_components(G)
            cyclomatic = edges - nodes + 2 * connected_components
            
            # 标准化复杂度（经验公式）
            normalized_complexity = min(
                (density * 0.5 + cyclomatic / (nodes + 1) * 0.5), 1.0
            )
            
            return normalized_complexity
            
        except Exception as e:
            self.logger.error(f"Failed to calculate graph complexity: {e}")
            return 0.0
    
    def export_to_networkx(self, call_graph: CallGraph) -> nx.DiGraph:
        """导出为 NetworkX 图"""
        G = nx.DiGraph()
        
        # 添加节点
        for node in call_graph.nodes:
            G.add_node(node.address, 
                      function_name=node.function_name,
                      is_suspicious=node.is_suspicious,
                      is_entry_point=node.is_entry_point,
                      call_count=node.call_count,
                      called_by_count=node.called_by_count)
        
        # 添加边
        for edge in call_graph.edges:
            G.add_edge(edge.source, edge.target,
                      call_count=edge.call_count,
                      edge_type=edge.edge_type)
        
        return G
    
    def export_to_dot(self, call_graph: CallGraph, output_path: str):
        """导出为 DOT 格式（Graphviz）"""
        try:
            with open(output_path, 'w') as f:
                f.write("digraph CallGraph {\n")
                f.write("  rankdir=TB;\n")
                f.write("  node [shape=box];\n")
                
                # 写入节点
                for node in call_graph.nodes:
                    style = ""
                    if node.is_entry_point:
                        style = ", style=filled, fillcolor=lightgreen"
                    elif node.is_suspicious:
                        style = ", style=filled, fillcolor=lightcoral"
                    
                    f.write(f'  "0x{node.address:x}" [label="{node.function_name}\\n0x{node.address:x}"{style}];\n')
                
                # 写入边
                for edge in call_graph.edges:
                    f.write(f'  "0x{edge.source:x}" -> "0x{edge.target:x}"')
                    if edge.call_count > 1:
                        f.write(f' [label="{edge.call_count}"]')
                    f.write(";\n")
                
                f.write("}\n")
                
            self.logger.info(f"Call graph exported to {output_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to export call graph: {e}")
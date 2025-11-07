# -*- coding: utf-8 -*-
"""
调用链分析工具 - 静态分析启动代码的调用链

用于识别可能的重复执行点和验证单一事实原则。
"""

import ast
import inspect
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional
import importlib.util


class CallChainAnalyzer:
    """调用链分析器"""

    def __init__(self, project_root: Optional[str] = None):
        """初始化分析器

        Args:
            project_root: 项目根目录，默认为当前工作目录
        """
        if project_root is None:
            project_root_path = Path.cwd()
        else:
            project_root_path = Path(project_root)
        self.project_root = project_root_path
        
        # 启动相关的关键文件
        self.startup_files = {
            "orchestrator": self.project_root / "backend" / "startup" / "orchestrator.py",
            "qt_framework": self.project_root / "backend" / "startup" / "stages" / "qt_framework.py",
            "backend_init": self.project_root / "backend" / "startup" / "stages" / "backend_init.py",
            "backend_initializer_worker": self.project_root / "backend" / "startup" / "workers" / "backend_initializer.py",
            "service_initializer": self.project_root / "backend" / "core" / "base.py",
        }
        
        # 关键方法列表（需要验证单一执行点）
        self.critical_methods = {
            "EventEngine.__init__": {"module": "vnpy.event", "class": "EventEngine", "method": "__init__"},
            "MainEngine.__init__": {"module": "vnpy.trader.engine", "class": "MainEngine", "method": "__init__"},
            "_initialize_vnpy_core": {"pattern": "_initialize_vnpy_core"},
            "initialize_core_services": {"pattern": "initialize_core_services"},
            "initialize_services": {"pattern": "initialize_services"},
        }
        
        # 调用链图谱
        self.call_graph: Dict[str, List[str]] = defaultdict(list)
        
        # 方法调用位置映射
        self.method_locations: Dict[str, List[Tuple[str, int]]] = defaultdict(list)

    def analyze_all(self) -> Dict[str, Any]:
        """分析所有启动相关文件

        Returns:
            Dict: 分析结果
        """
        results = {
            "files_analyzed": [],
            "call_chains": {},
            "critical_methods": {},
            "potential_duplicates": [],
            "validation_issues": [],
        }
        
        # 分析每个启动文件
        for name, file_path in self.startup_files.items():
            if not file_path.exists():
                results["validation_issues"].append(f"文件不存在: {file_path}")
                continue
            
            try:
                file_results = self._analyze_file(file_path, name)
                results["files_analyzed"].append(name)
                
                # 合并调用链
                for method, calls in file_results.get("call_chains", {}).items():
                    results["call_chains"][method] = results["call_chains"].get(method, []) + calls
                
                # 记录关键方法位置
                for method, locations in file_results.get("method_locations", {}).items():
                    results["critical_methods"][method] = results["critical_methods"].get(method, []) + locations
                    
            except Exception as e:
                results["validation_issues"].append(f"分析文件 {name} 失败: {e}")
        
        # 检查潜在的重复执行点
        results["potential_duplicates"] = self._find_potential_duplicates(results)
        
        return results

    def _analyze_file(self, file_path: Path, module_name: str) -> Dict[str, Any]:
        """分析单个文件

        Args:
            file_path: 文件路径
            module_name: 模块名称

        Returns:
            Dict: 文件分析结果
        """
        results = {
            "call_chains": {},
            "method_locations": {},
        }
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
            
            tree = ast.parse(source_code, filename=str(file_path))
            
            # 分析AST
            analyzer = ASTCallAnalyzer(module_name, file_path)
            analyzer.visit(tree)
            
            results["call_chains"] = analyzer.call_chains
            results["method_locations"] = analyzer.method_locations
            
        except Exception as e:
            raise RuntimeError(f"解析文件失败: {e}")
        
        return results

    def _find_potential_duplicates(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """查找潜在的重复执行点

        Args:
            results: 分析结果

        Returns:
            List: 潜在的重复执行点列表
        """
        duplicates = []
        
        # 检查关键方法的调用位置
        critical_calls = {}
        for method, locations in results.get("critical_methods", {}).items():
            if len(locations) > 1:
                critical_calls[method] = locations
        
        # 检查EventEngine/MainEngine的创建
        for method in ["EventEngine.__init__", "MainEngine.__init__"]:
            locations = results.get("critical_methods", {}).get(method, [])
            if len(locations) > 1:
                duplicates.append({
                    "method": method,
                    "type": "multiple_creation",
                    "locations": locations,
                    "severity": "high",
                    "message": f"{method} 在多个位置被调用，违反单一事实原则",
                })
        
        # 检查_initialize_vnpy_core的调用
        vnpy_core_locations = results.get("critical_methods", {}).get("_initialize_vnpy_core", [])
        if len(vnpy_core_locations) > 1:
            duplicates.append({
                "method": "_initialize_vnpy_core",
                "type": "multiple_execution",
                "locations": vnpy_core_locations,
                "severity": "high",
                "message": "_initialize_vnpy_core 在多个位置被执行，可能重复初始化",
            })
        
        return duplicates

    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成分析报告

        Args:
            results: 分析结果

        Returns:
            str: 分析报告
        """
        lines = []
        lines.append("=" * 80)
        lines.append("启动代码调用链分析报告")
        lines.append("=" * 80)
        lines.append("")
        
        # 文件分析情况
        lines.append("## 文件分析情况")
        lines.append(f"- 已分析文件数: {len(results.get('files_analyzed', []))}")
        for name in results.get("files_analyzed", []):
            lines.append(f"  ✓ {name}")
        lines.append("")
        
        # 关键方法调用位置
        lines.append("## 关键方法调用位置")
        for method, locations in results.get("critical_methods", {}).items():
            lines.append(f"\n### {method}")
            for module, line_num in locations:
                lines.append(f"  - {module}:{line_num}")
        lines.append("")
        
        # 潜在重复执行点
        duplicates = results.get("potential_duplicates", [])
        if duplicates:
            lines.append("## ⚠️ 潜在的重复执行点")
            for dup in duplicates:
                lines.append(f"\n### {dup['method']} ({dup['severity']})")
                lines.append(f"  问题: {dup['message']}")
                lines.append("  调用位置:")
                for module, line_num in dup["locations"]:
                    lines.append(f"    - {module}:{line_num}")
        else:
            lines.append("## ✅ 未发现重复执行点")
        lines.append("")
        
        # 验证问题
        issues = results.get("validation_issues", [])
        if issues:
            lines.append("## ❌ 验证问题")
            for issue in issues:
                lines.append(f"  - {issue}")
        lines.append("")
        
        lines.append("=" * 80)
        return "\n".join(lines)


class ASTCallAnalyzer(ast.NodeVisitor):
    """AST调用分析器"""

    def __init__(self, module_name: str, file_path: Path):
        """初始化分析器

        Args:
            module_name: 模块名称
            file_path: 文件路径
        """
        self.module_name = module_name
        self.file_path = file_path
        self.call_chains: Dict[str, List[str]] = defaultdict(list)
        self.method_locations: Dict[str, List[Tuple[str, int]]] = defaultdict(list)
        self.current_method = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """访问函数定义"""
        old_method = self.current_method
        self.current_method = node.name
        
        # 检查是否是关键方法
        if "_initialize_vnpy_core" in node.name:
            self.method_locations["_initialize_vnpy_core"].append((self.module_name, node.lineno))
        if "initialize_core_services" in node.name:
            self.method_locations["initialize_core_services"].append((self.module_name, node.lineno))
        if "initialize_services" in node.name:
            self.method_locations["initialize_services"].append((self.module_name, node.lineno))
        
        self.generic_visit(node)
        self.current_method = old_method

    def visit_Call(self, node: ast.Call):
        """访问函数调用"""
        # 检查是否是EventEngine/MainEngine的创建
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in ["EventEngine", "MainEngine"]:
                self.method_locations[f"{func_name}.__init__"].append((self.module_name, node.lineno))
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                attr_name = node.func.attr
                if obj_name in ["EventEngine", "MainEngine"] and attr_name == "__init__":
                    self.method_locations[f"{obj_name}.__init__"].append((self.module_name, node.lineno))
                elif attr_name == "_initialize_vnpy_core":
                    self.method_locations["_initialize_vnpy_core"].append((self.module_name, node.lineno))
                elif attr_name == "initialize_core_services":
                    self.method_locations["initialize_core_services"].append((self.module_name, node.lineno))
                elif attr_name == "initialize_services":
                    self.method_locations["initialize_services"].append((self.module_name, node.lineno))
        
        # 记录调用链
        if self.current_method:
            try:
                call_str = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
                self.call_chains[self.current_method].append(call_str)
            except Exception:
                pass
        
        self.generic_visit(node)


def main():
    """主函数 - 运行分析"""
    analyzer = CallChainAnalyzer()
    results = analyzer.analyze_all()
    report = analyzer.generate_report(results)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(report, extra={"log_type": "SYSTEM"})
    
    # 保存报告到文件
    report_path = analyzer.project_root / "logs" / "startup_call_chain_analysis.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    logger.info(f"\n报告已保存到: {report_path}", extra={"log_type": "SYSTEM"})
    
    return results


if __name__ == "__main__":
    main()


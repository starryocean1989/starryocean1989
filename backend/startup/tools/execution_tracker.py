# -*- coding: utf-8 -*-
"""
执行追踪器 - 运行时验证启动执行顺序

用于追踪关键方法的执行，检测重复执行和验证单一事实原则。
"""

import functools
import time
from collections import defaultdict
from typing import Dict, List, Any, Callable, Optional
from pathlib import Path
import threading
import logging


logger = logging.getLogger(__name__)

class ExecutionTracker:
    """执行追踪器"""

    def __init__(self, enabled: bool = True):
        """初始化追踪器

        Args:
            enabled: 是否启用追踪
        """
        self.enabled = enabled
        self.execution_log: List[Dict[str, Any]] = []
        self.method_call_count: Dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()
        self.startup_stage: Optional[str] = None

    def set_stage(self, stage_name: str):
        """设置当前启动阶段

        Args:
            stage_name: 阶段名称
        """
        self.startup_stage = stage_name

    def track_method(self, method_name: str, stage: Optional[str] = None):
        """追踪方法执行的装饰器

        Args:
            method_name: 方法名称（用于标识）
            stage: 阶段名称（如果None，使用当前阶段）

        Returns:
            Callable: 装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                if not self.enabled:
                    return func(*args, **kwargs)
                
                current_stage = stage or self.startup_stage or "unknown"
                
                # 记录方法调用
                call_info = {
                    "method": method_name,
                    "function": func.__name__,
                    "stage": current_stage,
                    "timestamp": time.time(),
                    "file": func.__code__.co_filename,
                    "line": func.__code__.co_firstlineno,
                }
                
                with self.lock:
                    self.execution_log.append(call_info)
                    self.method_call_count[method_name] += 1
                
                # 执行方法
                try:
                    result = func(*args, **kwargs)
                    call_info["success"] = True
                    call_info["duration_ms"] = (time.time() - call_info["timestamp"]) * 1000
                except Exception as e:
                    call_info["success"] = False
                    call_info["error"] = str(e)
                    call_info["duration_ms"] = (time.time() - call_info["timestamp"]) * 1000
                    raise
                finally:
                    # 更新日志条目
                    with self.lock:
                        if self.execution_log:
                            self.execution_log[-1].update(call_info)
                
                return result
            
            return wrapper
        return decorator

    def track_call(self, method_name: str, stage: Optional[str] = None, **kwargs):
        """手动追踪方法调用

        Args:
            method_name: 方法名称
            stage: 阶段名称
            **kwargs: 额外的追踪信息
        """
        if not self.enabled:
            return
        
        current_stage = stage or self.startup_stage or "unknown"
        
        call_info = {
            "method": method_name,
            "stage": current_stage,
            "timestamp": time.time(),
            **kwargs,
        }
        
        with self.lock:
            self.execution_log.append(call_info)
            self.method_call_count[method_name] += 1

    def get_duplicate_executions(self) -> List[Dict[str, Any]]:
        """获取重复执行的方法

        Returns:
            List: 重复执行的方法列表
        """
        duplicates = []
        
        # 检查每个方法的调用次数
        for method_name, count in self.method_call_count.items():
            if count > 1:
                method_calls = [
                    log for log in self.execution_log
                    if log.get("method") == method_name
                ]
                
                # 检查是否在不同阶段执行
                stages = set(log.get("stage") for log in method_calls if log.get("stage") is not None)
                if len(stages) > 1:
                    stage_str = ", ".join(str(s) for s in stages)
                    duplicates.append({
                        "method": method_name,
                        "count": count,
                        "stages": list(stages),
                        "calls": method_calls,
                        "severity": "high",
                        "message": f"{method_name} 在多个阶段被执行（{stage_str}），违反单一事实原则",
                    })
                else:
                    duplicates.append({
                        "method": method_name,
                        "count": count,
                        "stages": list(stages),
                        "calls": method_calls,
                        "severity": "medium",
                        "message": f"{method_name} 在同一阶段被执行 {count} 次，可能重复执行",
                    })
        
        return duplicates

    def generate_report(self, output_path: Optional[Path] = None) -> str:
        """生成执行追踪报告

        Args:
            output_path: 输出路径（如果提供，保存到文件）

        Returns:
            str: 报告内容
        """
        lines = []
        lines.append("=" * 80)
        lines.append("启动执行追踪报告")
        lines.append("=" * 80)
        lines.append("")
        
        # 执行统计
        lines.append("## 执行统计")
        lines.append(f"- 总方法调用数: {len(self.execution_log)}")
        lines.append(f"- 唯一方法数: {len(self.method_call_count)}")
        lines.append("")
        
        # 方法调用次数
        lines.append("## 方法调用次数")
        for method_name, count in sorted(self.method_call_count.items()):
            lines.append(f"  - {method_name}: {count} 次")
        lines.append("")
        
        # 重复执行检测
        duplicates = self.get_duplicate_executions()
        if duplicates:
            lines.append("## ⚠️ 重复执行检测")
            for dup in duplicates:
                lines.append(f"\n### {dup['method']} ({dup['severity']})")
                lines.append(f"  问题: {dup['message']}")
                lines.append(f"  调用次数: {dup['count']}")
                lines.append(f"  涉及阶段: {', '.join(dup['stages'])}")
                lines.append("  调用详情:")
                for i, call in enumerate(dup['calls'], 1):
                    stage = call.get('stage', 'unknown')
                    timestamp = call.get('timestamp', 0)
                    success = call.get('success', True)
                    duration = call.get('duration_ms', 0)
                    file = call.get('file', 'unknown')
                    line = call.get('line', 0)
                    status = "✅" if success else "❌"
                    lines.append(f"    {i}. [{status}] {stage} - {file}:{line} ({duration:.2f}ms)")
        else:
            lines.append("## ✅ 未发现重复执行")
        lines.append("")
        
        # 执行顺序
        lines.append("## 执行顺序")
        for i, log in enumerate(self.execution_log[:50], 1):  # 只显示前50条
            method = log.get('method', 'unknown')
            stage = log.get('stage', 'unknown')
            success = "✅" if log.get('success', True) else "❌"
            duration = log.get('duration_ms', 0)
            lines.append(f"  {i}. [{success}] {method} ({stage}) - {duration:.2f}ms")
        
        if len(self.execution_log) > 50:
            lines.append(f"  ... 还有 {len(self.execution_log) - 50} 条记录")
        lines.append("")
        
        lines.append("=" * 80)
        
        report_content = "\n".join(lines)
        
        # 保存到文件
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
        
        return report_content

    def reset(self):
        """重置追踪器"""
        with self.lock:
            self.execution_log.clear()
            self.method_call_count.clear()
            self.startup_stage = None


# 全局追踪器实例
_global_tracker: Optional[ExecutionTracker] = None


def get_tracker() -> ExecutionTracker:
    """获取全局追踪器实例

    Returns:
        ExecutionTracker: 全局追踪器实例
    """
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ExecutionTracker(enabled=True)
    return _global_tracker


def track_method(method_name: str, stage: Optional[str] = None):
    """追踪方法执行的装饰器（便捷函数）

    Args:
        method_name: 方法名称
        stage: 阶段名称

    Returns:
        Callable: 装饰器函数
    """
    return get_tracker().track_method(method_name, stage)


def track_call(method_name: str, stage: Optional[str] = None, **kwargs):
    """手动追踪方法调用（便捷函数）

    Args:
        method_name: 方法名称
        stage: 阶段名称
        **kwargs: 额外的追踪信息
    """
    get_tracker().track_call(method_name, stage, **kwargs)


def generate_tracking_report(output_path: Optional[Path] = None) -> str:
    """生成追踪报告（便捷函数）

    Args:
        output_path: 输出路径

    Returns:
        str: 报告内容
    """
    return get_tracker().generate_report(output_path)


if __name__ == "__main__":
    # 示例使用
    tracker = ExecutionTracker()
    tracker.set_stage("stage2")
    
    @tracker.track_method("test_method", "stage2")
    def test_func():
        time.sleep(0.1)
        return "ok"
    
    test_func()
    tracker.set_stage("stage3")
    test_func()
    
    report = tracker.generate_report()
    logger.info(report, extra={"log_type": "SYSTEM"})


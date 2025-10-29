# -*- coding: utf-8 -*-
"""Qt线程安全与日志格式统一修复验证脚本

用途：验证所有修复是否正确生效

使用方法：
    python scripts/verify_qt_thread_safety.py

验证内容：
    1. 检查所有事件处理器是否使用QTimer.singleShot
    2. 检查子进程函数是否初始化logger
    3. 检查Terminal过滤规则是否正确
"""

import re
from pathlib import Path


def verify_event_handlers():
    """验证事件处理器的线程安全修复"""
    print("=" * 80)
    print("验证1: 检查事件处理器线程安全")
    print("=" * 80)
    
    file_path = Path("ui/modules/data_center_view.py")
    content = file_path.read_text(encoding="utf-8")
    
    # 需要验证的事件处理器
    event_handlers = [
        "_on_download_event",
        "_on_server_status_update",
        "_on_local_data_index_ready",
        "_on_file_watcher_started",
        "_on_data_metrics_updated",
        "_on_invalid_symbols_updated",
        "_on_data_scan_finished",
        "_on_quality_scan_phase",
        "_on_data_quality_update",
        "_on_data_scan_complete",
        "_on_tick_event",
    ]
    
    results = []
    for handler in event_handlers:
        # 查找处理器定义
        pattern = rf"def {handler}\(self.*?\):(.*?)(?=\n    def |\nclass |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            handler_code = match.group(1)
            
            # 检查是否有警告注释
            has_warning = "⚠️" in handler_code and "vnpy事件引擎可能在非Qt主线程中调用此方法" in handler_code
            
            # 检查是否使用QTimer.singleShot
            has_qtimer = "QTimer.singleShot" in handler_code
            
            status = "✅" if (has_warning and has_qtimer) else "❌"
            results.append({
                "handler": handler,
                "status": status,
                "has_warning": has_warning,
                "has_qtimer": has_qtimer
            })
            
            print(f"{status} {handler}")
            if not has_warning:
                print(f"    ⚠️  缺少线程安全警告注释")
            if not has_qtimer:
                print(f"    ⚠️  未使用QTimer.singleShot转发UI操作")
        else:
            print(f"❓ {handler} - 未找到方法定义")
            results.append({
                "handler": handler,
                "status": "❓",
                "has_warning": False,
                "has_qtimer": False
            })
    
    # 统计
    success_count = sum(1 for r in results if r["status"] == "✅")
    total_count = len(event_handlers)
    
    print()
    print(f"结果: {success_count}/{total_count} 个事件处理器已修复")
    
    return success_count == total_count


def verify_subprocess_logging():
    """验证子进程日志初始化"""
    print("\n" + "=" * 80)
    print("验证2: 检查子进程日志初始化")
    print("=" * 80)
    
    file_path = Path("backend/infrastructure/data_module_vnpy/load_balancer/load_balancer.py")
    content = file_path.read_text(encoding="utf-8")
    
    # 需要验证的子进程函数
    functions = [
        "_process_task_unit",
        "_process_async_batch",
    ]
    
    results = []
    for func in functions:
        # 查找函数定义
        pattern = rf"def {func}\(.*?\):(.*?)(?=\ndef |\nclass |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            func_code = match.group(1)
            
            # 检查是否有日志初始化注释
            has_comment = "初始化子进程日志" in func_code
            
            # 检查是否使用logging.getLogger
            has_logger = "logging.getLogger" in func_code and "subprocess" in func_code
            
            status = "✅" if (has_comment and has_logger) else "❌"
            results.append({
                "function": func,
                "status": status,
                "has_comment": has_comment,
                "has_logger": has_logger
            })
            
            print(f"{status} {func}")
            if not has_comment:
                print(f"    ⚠️  缺少日志初始化注释")
            if not has_logger:
                print(f"    ⚠️  未初始化logger")
        else:
            print(f"❓ {func} - 未找到函数定义")
            results.append({
                "function": func,
                "status": "❓",
                "has_comment": False,
                "has_logger": False
            })
    
    # 统计
    success_count = sum(1 for r in results if r["status"] == "✅")
    total_count = len(functions)
    
    print()
    print(f"结果: {success_count}/{total_count} 个子进程函数已修复")
    
    return success_count == total_count


def verify_console_filter():
    """验证Terminal过滤规则"""
    print("\n" + "=" * 80)
    print("验证3: 检查Terminal输出过滤规则")
    print("=" * 80)
    
    file_path = Path("backend/infrastructure/system_vnpy/unified_log_system.py")
    content = file_path.read_text(encoding="utf-8")
    
    # 查找_to_console方法
    pattern = r"def _to_console\(self.*?\):(.*?)(?=\n    def |\nclass |\Z)"
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print("❌ 未找到_to_console方法")
        return False
    
    method_code = match.group(1)
    
    # 检查是否有正确的注释
    has_comment = "WARNING及以上级别" in method_code
    
    # 检查是否有WARNING过滤逻辑
    has_warning_filter = "logging.WARNING" in method_code or "record.level >= logging.WARNING" in method_code
    
    # 检查是否有类型过滤
    has_type_filter = "console_enabled_types" in method_code
    
    print(f"{'✅' if has_comment else '❌'} 文档注释包含WARNING级别说明")
    print(f"{'✅' if has_warning_filter else '❌'} 代码包含WARNING级别过滤")
    print(f"{'✅' if has_type_filter else '❌'} 代码包含类型过滤")
    
    success = has_comment and has_warning_filter and has_type_filter
    
    print()
    print(f"结果: {'✅ Terminal过滤规则配置正确' if success else '❌ Terminal过滤规则配置不完整'}")
    
    return success


def verify_ui_update_methods():
    """验证UI更新方法是否存在"""
    print("\n" + "=" * 80)
    print("验证4: 检查UI更新方法是否存在")
    print("=" * 80)
    
    file_path = Path("ui/modules/data_center_view.py")
    content = file_path.read_text(encoding="utf-8")
    
    # 需要验证的UI更新方法
    ui_methods = [
        "_update_progress_ui",
        "_handle_download_complete",
        "_handle_download_error",
        "_handle_download_stopped",
        "_update_server_status_ui",
        "_update_local_data_index_ui",
        "_handle_file_watcher_started_ui",
        "_update_data_metrics_ui",
        "_update_invalid_symbols_ui",
        "_handle_data_scan_finished_ui",
        "_update_quality_scan_phase_ui",
        "_handle_scan_complete_ui",
        "_handle_tick_ui",
    ]
    
    results = []
    for method in ui_methods:
        pattern = rf"def {method}\(self.*?\):"
        match = re.search(pattern, content)
        
        status = "✅" if match else "❌"
        results.append({
            "method": method,
            "exists": bool(match)
        })
        
        print(f"{status} {method}")
    
    # 统计
    success_count = sum(1 for r in results if r["exists"])
    total_count = len(ui_methods)
    
    print()
    print(f"结果: {success_count}/{total_count} 个UI更新方法已创建")
    
    return success_count == total_count


def main():
    """主验证流程"""
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "Qt线程安全与日志格式统一修复验证" + " " * 23 + "║")
    print("╚" + "═" * 78 + "╝")
    print()
    
    results = []
    
    # 验证1: 事件处理器
    results.append(("事件处理器线程安全", verify_event_handlers()))
    
    # 验证2: 子进程日志
    results.append(("子进程日志初始化", verify_subprocess_logging()))
    
    # 验证3: Terminal过滤规则
    results.append(("Terminal过滤规则", verify_console_filter()))
    
    # 验证4: UI更新方法
    results.append(("UI更新方法创建", verify_ui_update_methods()))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("验证汇总")
    print("=" * 80)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {name}")
    
    # 总结
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print()
    if success_count == total_count:
        print("🎉 所有验证项通过！修复已正确实施。")
        print()
        print("下一步：")
        print("  1. 运行应用并检查Terminal无Qt线程警告")
        print("  2. 触发数据下载功能验证UI更新正常")
        print("  3. 检查logs/ai/目录验证日志输出完整")
        return 0
    else:
        print(f"⚠️  {total_count - success_count} 个验证项失败，请检查修复代码。")
        return 1


if __name__ == "__main__":
    exit(main())


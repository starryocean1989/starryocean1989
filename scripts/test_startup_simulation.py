#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模拟启动流程测试 - 验证AI日志完整性

此脚本模拟系统启动时的各类日志输出，验证：
1. Terminal输出简洁（只显示关键节点）
2. AI日志文件详细（包含所有DEBUG/INFO/WARNING/ERROR/CRITICAL）
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.system_vnpy.unified_log_system import (
    get_logging_hub,
    get_ai_log_handler,
    start_ai_process,
    end_ai_process,
)


def setup_logging_hub():
    """初始化LoggingHub"""
    # 获取LoggingHub
    hub = get_logging_hub()
    hub.set_stage("startup")
    
    # 配置控制台Handler（简洁输出）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(formatter)
    hub.set_console_handler(console_handler)
    
    # 配置文件Handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "terminal.log", mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    hub.set_file_handler(file_handler)
    
    # 配置AI日志Handler
    ai_handler = get_ai_log_handler()
    hub.set_ai_log_handler(ai_handler)
    
    # 添加到root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(hub)
    root_logger.setLevel(logging.DEBUG)
    
    return hub


def simulate_startup_logs():
    """模拟启动流程的各类日志"""
    
    # 创建各种logger
    stage_logger = logging.getLogger("startup.stage")
    config_logger = logging.getLogger("backend.core.config")
    data_logger = logging.getLogger("backend.services.data_center_service")
    ui_logger = logging.getLogger("ui.main_window")
    monitor_logger = logging.getLogger("backend.infrastructure.system_vnpy.monitor")
    
    print("\n" + "=" * 80)
    print("模拟启动流程 - 观察Terminal输出（应该简洁）")
    print("=" * 80 + "\n")
    
    # 1. 阶段节点（应该输出到Terminal）
    stage_logger.info("📍 系统启动开始")
    
    # 2. DEBUG日志（不应输出到Terminal，但应进入AI日志）
    config_logger.debug("读取配置文件: terminal_config.json")
    config_logger.debug("配置项加载: database.sqlite_path = data/terminal.db")
    config_logger.debug("配置项加载: logging.level = INFO")
    
    # 3. INFO日志（不应输出到Terminal，但应进入AI日志）
    config_logger.info("开始初始化全局配置: 文件=terminal_config.json")
    config_logger.info("配置文件加载完成: 配置节=11, 配置项=80")
    
    # 4. 更多DEBUG（不应输出到Terminal）
    data_logger.debug("初始化数据中心服务")
    data_logger.debug("连接数据库: data/terminal.db")
    data_logger.debug("创建数据表: symbols, kline_data, tick_data")
    
    # 5. INFO（不应输出到Terminal）
    data_logger.info("数据中心服务已初始化")
    ui_logger.info("主窗口框架初始化完成")
    
    # 6. 阶段节点（应该输出到Terminal）
    stage_logger.info("📍 Qt框架初始化完成")
    
    # 7. WARNING（应该输出到Terminal）
    monitor_logger.warning("未检测到硬件传感器，部分监控功能将不可用")
    
    # 8. DEBUG（不应输出到Terminal）
    monitor_logger.debug("尝试连接硬件传感器...")
    monitor_logger.debug("CPU传感器检测失败")
    monitor_logger.debug("GPU传感器检测失败")
    
    # 9. INFO（不应输出到Terminal）
    monitor_logger.info("系统监控已启用（基础模式）")
    
    # 10. 阶段节点（应该输出到Terminal）
    stage_logger.info("📍 主窗口已显示")
    
    # 11. ERROR（应该输出到Terminal）
    try:
        raise ValueError("测试异常：模拟配置文件加载错误")
    except Exception as e:
        config_logger.error("配置文件部分项解析失败", exc_info=True)
    
    # 12. 更多DEBUG（不应输出到Terminal）
    data_logger.debug("开始加载品种列表缓存")
    data_logger.debug("缓存文件: data/symbols_cache.pkl")
    data_logger.debug("缓存命中率: 95.6%")
    
    # 13. INFO（不应输出到Terminal）
    data_logger.info("品种列表加载完成: 共5000个品种")
    
    # 14. CRITICAL（应该输出到Terminal）
    stage_logger.critical("测试严重错误日志（实际不会发生）")
    
    # 15. 阶段节点（应该输出到Terminal）
    stage_logger.info("📍 系统启动完成")


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("AI日志完整性测试 - 启动流程模拟")
    print("=" * 80)
    
    # 1. 初始化LoggingHub
    hub = setup_logging_hub()
    print("\n✅ LoggingHub已初始化")
    
    # 2. 启动AI日志流程
    ai_log_file = start_ai_process(
        "startup_simulation",
        metadata={
            "test_type": "startup_simulation",
            "purpose": "验证AI日志完整性"
        }
    )
    print(f"✅ AI日志文件: {ai_log_file}\n")
    
    # 3. 模拟启动日志
    simulate_startup_logs()
    
    # 4. 结束AI日志流程
    end_ai_process(success=True, summary="启动流程模拟完成")
    
    # 5. 获取统计信息
    stats = hub.get_statistics()
    ai_stats = get_ai_log_handler().get_statistics()
    
    print("\n" + "=" * 80)
    print("统计信息")
    print("=" * 80)
    print(f"\nLoggingHub统计:")
    print(f"  总日志数: {stats['total_logs']}")
    print(f"  控制台输出: {stats['console_writes']}")
    print(f"  文件输出: {stats['file_writes']}")
    print(f"  AI日志输出: {stats['ai_log_writes']}")
    print(f"  数据库写入: {stats['db_writes']}")
    
    print(f"\nAI日志统计:")
    print(f"  流程数: {ai_stats['process_count']}")
    print(f"  总日志条数: {ai_stats['total_logs']}")
    print(f"  DEBUG: {ai_stats['level_counts']['DEBUG']} 条")
    print(f"  INFO: {ai_stats['level_counts']['INFO']} 条")
    print(f"  WARNING: {ai_stats['level_counts']['WARNING']} 条")
    print(f"  ERROR: {ai_stats['level_counts']['ERROR']} 条")
    print(f"  CRITICAL: {ai_stats['level_counts']['CRITICAL']} 条")
    
    print("\n" + "=" * 80)
    print("验证结果")
    print("=" * 80)
    
    # 验证
    success = True
    
    # 1. Terminal输出应该少（只有关键节点）
    if stats['console_writes'] <= 10:
        print(f"✅ Terminal输出简洁: {stats['console_writes']} 条（预期 ≤10）")
    else:
        print(f"❌ Terminal输出过多: {stats['console_writes']} 条（预期 ≤10）")
        success = False
    
    # 2. AI日志应该包含所有日志
    expected_min_logs = 25  # 至少应该有25条（包括DEBUG、INFO等）
    if ai_stats['total_logs'] >= expected_min_logs:
        print(f"✅ AI日志详细完整: {ai_stats['total_logs']} 条（预期 ≥{expected_min_logs}）")
    else:
        print(f"❌ AI日志过少: {ai_stats['total_logs']} 条（预期 ≥{expected_min_logs}）")
        success = False
    
    # 3. AI日志应该包含DEBUG
    if ai_stats['level_counts']['DEBUG'] > 0:
        print(f"✅ AI日志包含DEBUG: {ai_stats['level_counts']['DEBUG']} 条")
    else:
        print(f"❌ AI日志缺少DEBUG")
        success = False
    
    # 4. AI日志应该包含所有级别
    all_levels_present = all(
        ai_stats['level_counts'][level] > 0
        for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    )
    if all_levels_present:
        print("✅ AI日志包含所有级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）")
    else:
        print("❌ AI日志缺少某些级别")
        success = False
    
    print("\n" + "=" * 80)
    if success:
        print("🎉 验证通过！AI日志系统工作正常")
        print("   - Terminal输出简洁")
        print("   - AI日志详细完整")
        print("   - 所有级别日志都已记录")
    else:
        print("❌ 验证失败！请检查日志系统配置")
    print("=" * 80)
    
    print(f"\n请查看AI日志文件: {ai_log_file}")
    print("应包含所有DEBUG/INFO/WARNING/ERROR/CRITICAL日志\n")


if __name__ == "__main__":
    main()

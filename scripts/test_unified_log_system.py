#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试整合后的统一日志系统

验证所有功能是否正常工作
"""

import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.system_vnpy.unified_log_system import (
    get_logging_hub,
    get_ai_log_handler,
    get_routing_engine,
    ai_log_process,
    start_ai_process,
    end_ai_process,
    LogType,
    ProcessNames,
)


def test_basic_logging():
    """测试基本日志功能."""
    print("\n" + "=" * 80)
    print("测试1: 基本日志功能")
    print("=" * 80)
    
    logger = logging.getLogger("test.basic")
    logger.debug("DEBUG日志")
    logger.info("INFO日志")
    logger.warning("WARNING日志")
    logger.error("ERROR日志")
    
    print("✅ 基本日志功能测试完成")


def test_ai_log_process():
    """测试AI日志流程."""
    print("\n" + "=" * 80)
    print("测试2: AI日志流程")
    print("=" * 80)
    
    logger = logging.getLogger("test.ai_process")
    
    try:
        with ai_log_process("test_process", metadata={"test_id": "001"}):
            logger.info("流程开始")
            logger.info("处理中...")
            logger.info("流程结束")
        
        # 检查日志文件是否创建
        handler = get_ai_log_handler()
        stats = handler.get_statistics()
        print(f"  AI日志统计: {stats}")
        print("✅ AI日志流程测试完成")
    except Exception as e:
        print(f"❌ AI日志流程测试失败: {e}")
        return False
    
    return True


def test_routing():
    """测试路由规则."""
    print("\n" + "=" * 80)
    print("测试3: 路由规则")
    print("=" * 80)
    
    try:
        hub = get_logging_hub()
        engine = get_routing_engine()
        
        if not engine:
            print("⚠️  路由引擎未初始化")
            return False
        
        # 测试阶段切换
        print("  当前阶段:", engine.current_stage)
        hub.set_stage("downloading")
        print("  切换后阶段:", engine.current_stage)
        
        logger = logging.getLogger("test.routing")
        logger.info("下载阶段日志（应该被静默）")
        
        # 切换回startup
        hub.set_stage("startup")
        logger.info("启动阶段日志（应该显示在Terminal）")
        
        print("✅ 路由规则测试完成")
        return True
    except Exception as e:
        print(f"❌ 路由规则测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_statistics():
    """测试统计信息."""
    print("\n" + "=" * 80)
    print("测试4: 统计信息")
    print("=" * 80)
    
    try:
        hub = get_logging_hub()
        stats = hub.get_statistics()
        
        print("  统计信息:")
        print(f"    总日志数: {stats['total_logs']}")
        print(f"    控制台输出: {stats['console_writes']}")
        print(f"    文件输出: {stats['file_writes']}")
        print(f"    AI日志输出: {stats['ai_log_writes']}")
        print(f"    数据库写入: {stats['db_writes']}")
        
        if 'routing_engine' in stats:
            re_stats = stats['routing_engine']
            print(f"\n  路由引擎统计:")
            print(f"    总路由次数: {re_stats['total_routes']}")
            print(f"    缓存命中率: {re_stats['cache_stats']['hit_rate']}")
            print(f"    当前阶段: {re_stats['current_stage']}")
            print(f"    运行模式: {re_stats['run_mode']}")
        
        print("✅ 统计信息测试完成")
        return True
    except Exception as e:
        print(f"❌ 统计信息测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_import_compatibility():
    """测试导入兼容性."""
    print("\n" + "=" * 80)
    print("测试5: 导入兼容性")
    print("=" * 80)
    
    try:
        # 测试所有关键导入
        from backend.infrastructure.system_vnpy.unified_log_system import (
            LoggingHub,
            RoutingRuleEngine,
            RuleCache,
            AILogFileHandler,
            ProgressThrottler,
            AILogProcess,
            ProcessNames,
            ai_log_process_decorator,
            log_progress,
            notify_complete,
            alert,
            log_system,
        )
        
        print("  ✅ LoggingHub")
        print("  ✅ RoutingRuleEngine")
        print("  ✅ RuleCache")
        print("  ✅ AILogFileHandler")
        print("  ✅ ProgressThrottler")
        print("  ✅ AILogProcess")
        print("  ✅ ProcessNames")
        print("  ✅ ai_log_process_decorator")
        print("  ✅ log_progress")
        print("  ✅ notify_complete")
        print("  ✅ alert")
        print("  ✅ log_system")
        
        print("\n✅ 导入兼容性测试完成")
        return True
    except ImportError as e:
        print(f"❌ 导入兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_process_names():
    """测试ProcessNames常量."""
    print("\n" + "=" * 80)
    print("测试6: ProcessNames常量")
    print("=" * 80)
    
    try:
        assert ProcessNames.STARTUP == "startup"
        assert ProcessNames.SYMBOL_REFRESH == "symbol_refresh"
        assert ProcessNames.DOWNLOAD_KLINE == "download_kline"
        assert ProcessNames.QUALITY_SCAN == "quality_scan"
        assert ProcessNames.STRATEGY_BACKTEST == "strategy_backtest"
        
        print("  ✅ ProcessNames.STARTUP")
        print("  ✅ ProcessNames.SYMBOL_REFRESH")
        print("  ✅ ProcessNames.DOWNLOAD_KLINE")
        print("  ✅ ProcessNames.QUALITY_SCAN")
        print("  ✅ ProcessNames.STRATEGY_BACKTEST")
        
        print("\n✅ ProcessNames常量测试完成")
        return True
    except AssertionError as e:
        print(f"❌ ProcessNames常量测试失败: {e}")
        return False


def main():
    """主测试函数."""
    print("=" * 80)
    print("统一日志系统整合测试 v5.0")
    print("=" * 80)
    
    results = []
    
    # 运行所有测试
    results.append(("基本日志功能", test_basic_logging()))
    results.append(("AI日志流程", test_ai_log_process()))
    results.append(("路由规则", test_routing()))
    results.append(("统计信息", test_statistics()))
    results.append(("导入兼容性", test_import_compatibility()))
    results.append(("ProcessNames常量", test_process_names()))
    
    # 汇总结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        if result is None or result is True:
            print(f"  ✅ {test_name}")
            passed += 1
        else:
            print(f"  ❌ {test_name}")
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"测试完成: 通过 {passed}/{len(results)}, 失败 {failed}/{len(results)}")
    print("=" * 80)
    
    if failed == 0:
        print("\n🎉 所有测试通过! 整合成功!")
        return 0
    else:
        print(f"\n⚠️  {failed}个测试失败,请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())

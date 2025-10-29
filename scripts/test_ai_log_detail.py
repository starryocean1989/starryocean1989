# -*- coding: utf-8 -*-
"""
测试AI日志文件输出详细程度

验证AI日志文件包含所有级别的日志信息（DEBUG、INFO、WARNING、ERROR、CRITICAL）
"""

import logging
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.system_vnpy.unified_log_system import (
    ai_log_process,
    get_ai_log_handler,
    get_logging_hub,
)


def test_ai_log_levels():
    """测试AI日志文件输出所有级别的日志."""
    print("\n" + "=" * 80)
    print("测试AI日志文件详细程度")
    print("=" * 80)

    # 配置根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # ✅ 初始化LoggingHub和AILogFileHandler
    logging_hub = get_logging_hub()
    ai_handler = get_ai_log_handler()
    
    # ✅ 将AILogFileHandler注入LoggingHub
    logging_hub.set_ai_log_handler(ai_handler)
    
    # ✅ 将LoggingHub添加到根logger
    root_logger.addHandler(logging_hub)

    # 创建测试流程
    with ai_log_process("test_log_levels", metadata={"test_type": "log_level_coverage"}):
        # ✅ 使用backend开头的logger，确保DEBUG不被过滤
        logger = logging.getLogger("backend.test.ai.log")

        print("\n📝 生成各级别日志...")

        # DEBUG级别（调试信息）
        logger.debug("这是DEBUG级别日志 - 用于调试时查看详细执行流程")
        logger.debug("变量值检查: count=100, status='running'")

        # INFO级别（普通信息）
        logger.info("这是INFO级别日志 - 记录正常执行流程")
        logger.info("任务启动: 共1000个品种待处理")

        # WARNING级别（警告）
        logger.warning("这是WARNING级别日志 - 可能存在的问题")
        logger.warning("连接重试: 第3次尝试，剩余7次")

        # ERROR级别（错误）
        logger.error("这是ERROR级别日志 - 发生了错误但可恢复")
        logger.error("数据下载失败: 代码=600000, 原因=连接超时")

        # CRITICAL级别（严重错误）
        logger.critical("这是CRITICAL级别日志 - 严重错误，系统可能无法继续")
        logger.critical("数据库连接断开，系统即将关闭")

        # 测试异常日志
        try:
            raise ValueError("这是一个测试异常，用于验证异常堆栈跟踪")
        except Exception as e:
            logger.exception("捕获异常并记录完整堆栈")

        print("✅ 各级别日志生成完成")

    # 获取AI日志文件路径
    ai_handler = get_ai_log_handler()
    stats = ai_handler.get_statistics()

    print("\n" + "=" * 80)
    print("AI日志统计信息")
    print("=" * 80)
    print(f"流程总数: {stats['process_count']}")
    print(f"总日志条数: {stats['total_logs']}")
    print(f"\n各级别日志分布:")
    level_counts = stats.get('level_counts', {})
    for level, count in level_counts.items():
        print(f"  {level:8s}: {count:3d} 条")

    print(f"\n最后生成的日志文件: {stats['current_file']}")

    # 验证各级别日志是否都有
    print("\n" + "=" * 80)
    print("验证结果")
    print("=" * 80)

    expected_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    all_present = True

    for level in expected_levels:
        count = level_counts.get(level, 0)
        if count > 0:
            print(f"✅ {level:8s}: {count} 条日志已记录")
        else:
            print(f"❌ {level:8s}: 未找到日志")
            all_present = False

    if all_present:
        print("\n🎉 验证通过！AI日志文件包含所有级别的日志")
        print("📋 Terminal输出简化，AI日志详细完整")
    else:
        print("\n❌ 验证失败！部分级别日志缺失")

    return all_present


if __name__ == "__main__":
    success = test_ai_log_levels()
    sys.exit(0 if success else 1)

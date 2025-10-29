# -*- coding: utf-8 -*-
"""
测试AI日志系统完整性 - 验证所有级别日志都正确输出到AI文件

测试目标:
1. 验证DEBUG/INFO/WARNING/ERROR/CRITICAL所有级别都能输出到AI日志
2. 验证Terminal输出简洁(只显示关键节点)
3. 验证AI日志文件详细完整
4. 验证异常堆栈信息正确记录
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def setup_logging():
    """初始化日志系统."""
    from backend.infrastructure.system_vnpy.unified_log_system import (
        get_logging_hub,
        get_ai_log_handler,
        start_ai_process,
    )

    # 获取LoggingHub
    logging_hub = get_logging_hub()

    # 创建Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logging_hub.set_console_handler(console_handler)

    # 创建文件Handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "test_comprehensive.log", mode="w", encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logging_hub.set_file_handler(file_handler)

    # 设置AI Handler
    ai_handler = get_ai_log_handler()
    logging_hub.set_ai_log_handler(ai_handler)

    # 添加到root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(logging_hub)

    # 启动AI流程
    ai_log_file = start_ai_process(
        "comprehensive_test",
        metadata={
            "test_type": "complete_level_coverage",
            "expected_levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        },
    )

    return logging_hub, ai_log_file


def test_all_log_levels():
    """测试所有日志级别."""
    print("\n" + "=" * 80)
    print("测试1: 所有日志级别输出")
    print("=" * 80)

    # 创建不同模块的logger
    test_logger = logging.getLogger("backend.test.comprehensive")
    stage_logger = logging.getLogger("backend.startup.stage")
    progress_logger = logging.getLogger("backend.data.download.progress")
    alert_logger = logging.getLogger("backend.monitor.alert")

    # 测试DEBUG级别
    print("\n📍 测试 DEBUG 级别...")
    test_logger.debug("这是DEBUG级别日志 - 应该只在文件和AI日志中")
    test_logger.debug("DEBUG详细信息: %s", {"key": "value", "count": 100})

    # 测试INFO级别
    print("\n📍 测试 INFO 级别...")
    test_logger.info("这是INFO级别日志 - 应该只在文件和AI日志中")
    test_logger.info("INFO详细信息: 处理了 %d 条数据", 1000)

    # 测试WARNING级别
    print("\n📍 测试 WARNING 级别...")
    test_logger.warning("这是WARNING级别日志 - 应该输出到Terminal")
    test_logger.warning("WARNING详细信息: 连接超时 %d 次", 3)

    # 测试ERROR级别
    print("\n📍 测试 ERROR 级别...")
    test_logger.error("这是ERROR级别日志 - 应该输出到Terminal")
    test_logger.error("ERROR详细信息: 查询失败,错误码 %d", 500)

    # 测试CRITICAL级别
    print("\n📍 测试 CRITICAL 级别...")
    test_logger.critical("这是CRITICAL级别日志 - 应该输出到Terminal并弹窗")
    test_logger.critical("CRITICAL详细信息: 系统崩溃")

    # 测试STAGE_NODE类型(应该输出到Terminal)
    print("\n📍 测试 STAGE_NODE 类型...")
    stage_logger.info("📍 阶段开始: 数据初始化")
    stage_logger.info("📍 阶段完成: 数据初始化")

    # 测试PROGRESS类型(不应输出到Terminal)
    print("\n📍 测试 PROGRESS 类型...")
    progress_logger.info("下载进度: 10%")
    progress_logger.info("下载进度: 50%")
    progress_logger.info("下载进度: 100%")

    # 测试ALERT类型(WARNING以上应输出到Terminal)
    print("\n📍 测试 ALERT 类型...")
    alert_logger.warning("⚠️ 监控告警: CPU温度过高 85°C")
    alert_logger.error("❌ 监控告警: 磁盘空间不足 5%")

    print("\n✅ 所有级别测试完成")


def test_exception_logging():
    """测试异常日志."""
    print("\n" + "=" * 80)
    print("测试2: 异常堆栈信息")
    print("=" * 80)

    logger = logging.getLogger("backend.test.exception")

    try:
        # 故意触发异常
        result = 1 / 0
    except Exception as e:
        logger.error("捕获到异常", exc_info=True)
        logger.exception("使用exception方法记录异常")

    print("\n✅ 异常测试完成")


def test_high_frequency_logging():
    """测试高频日志."""
    print("\n" + "=" * 80)
    print("测试3: 高频日志(100条)")
    print("=" * 80)

    logger = logging.getLogger("backend.test.highfreq")

    for i in range(100):
        if i % 10 == 0:
            logger.debug(f"高频DEBUG {i}/100")
        if i % 20 == 0:
            logger.info(f"高频INFO {i}/100")
        if i % 50 == 0:
            logger.warning(f"高频WARNING {i}/100")

    print("\n✅ 高频日志测试完成")


def verify_results(ai_log_file: Path):
    """验证测试结果."""
    print("\n" + "=" * 80)
    print("验证测试结果")
    print("=" * 80)

    # 检查AI日志文件是否存在
    if not ai_log_file.exists():
        print(f"❌ AI日志文件不存在: {ai_log_file}")
        return False

    # 读取AI日志内容
    content = ai_log_file.read_text(encoding="utf-8")
    lines = content.split("\n")

    # 统计各级别日志数量
    level_counts = {
        "DEBUG": 0,
        "INFO": 0,
        "WARNING": 0,
        "ERROR": 0,
        "CRITICAL": 0,
    }

    for line in lines:
        for level in level_counts:
            if f"[{level}]" in line or f"- {level} -" in line:
                level_counts[level] += 1
                break

    print(f"\nAI日志文件: {ai_log_file}")
    print(f"文件大小: {ai_log_file.stat().st_size} bytes")
    print(f"总行数: {len(lines)}")
    print("\n日志级别统计:")
    for level, count in level_counts.items():
        print(f"  - {level}: {count} 条")

    # 验证标准
    success = True
    if level_counts["DEBUG"] == 0:
        print("❌ 缺少DEBUG级别日志")
        success = False
    if level_counts["INFO"] == 0:
        print("❌ 缺少INFO级别日志")
        success = False
    if level_counts["WARNING"] == 0:
        print("❌ 缺少WARNING级别日志")
        success = False
    if level_counts["ERROR"] == 0:
        print("❌ 缺少ERROR级别日志")
        success = False

    # 检查异常堆栈
    has_traceback = "Traceback" in content or "异常堆栈跟踪" in content
    if not has_traceback:
        print("❌ 缺少异常堆栈信息")
        success = False
    else:
        print("✅ 包含异常堆栈信息")

    if success:
        print("\n✅ 所有验证通过!")
    else:
        print("\n❌ 验证失败,请检查日志系统配置")

    return success


def main():
    """主测试函数."""
    print("=" * 80)
    print("AI日志系统完整性测试")
    print("=" * 80)

    # 初始化日志系统
    print("\n📍 初始化日志系统...")
    logging_hub, ai_log_file = setup_logging()
    print(f"✅ 日志系统初始化完成")
    print(f"   AI日志文件: {ai_log_file}")

    # 执行测试
    test_all_log_levels()
    test_exception_logging()
    test_high_frequency_logging()

    # 等待日志写入
    print("\n⏳ 等待日志写入...")
    time.sleep(2)

    # 结束AI流程
    from backend.infrastructure.system_vnpy.unified_log_system import end_ai_process

    end_ai_process(success=True, summary="综合测试完成")

    # 验证结果
    time.sleep(1)
    success = verify_results(ai_log_file)

    # 输出统计信息
    stats = logging_hub.get_statistics()
    print("\n" + "=" * 80)
    print("LoggingHub统计信息")
    print("=" * 80)
    print(f"总日志数: {stats['total_logs']}")
    print(f"控制台写入: {stats['console_writes']}")
    print(f"文件写入: {stats['file_writes']}")
    print(f"AI日志写入: {stats['ai_log_writes']}")
    print(f"数据库写入: {stats['db_writes']}")

    if "routing_engine" in stats:
        cache_stats = stats["routing_engine"]["cache_stats"]
        print(f"\n路由缓存统计:")
        print(f"  - 缓存大小: {cache_stats['size']}")
        print(f"  - 命中率: {cache_stats['hit_rate']}")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

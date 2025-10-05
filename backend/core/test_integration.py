# -*- coding: utf-8 -*-
"""
核心模块集成测试
验证VNPY架构集成、统一导入、数据模型等核心功能
"""

import sys
import logging
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 核心模块导入
from backend.core.vnpy_integration import (
    VNPY_AVAILABLE, get_terminal_engine
)
from backend.core.imports import (
    check_module_availability, setup_logging,
    ModuleAvailability
)
from backend.core.models import (
    UnifiedMarketData, get_data_model_manager
)
from backend.core.factories import (
    UnifiedFactory
)
from backend.core.shared_services import (
    ConfigService, LoggingService, MonitoringService
)


def test_vnpy_integration():
    """测试VNPY架构集成"""
    print("=== 测试VNPY架构集成 ===")

    try:
        print(f"VNPY可用性: {VNPY_AVAILABLE}")

        # 创建终端引擎实例
        engine = get_terminal_engine()
        print(f"终端引擎创建成功: {type(engine)}")

        # 获取系统状态
        status = engine.get_status()
        print(f"系统状态: {status}")

        # 测试事件系统
        engine.emit_event("eSystemStatus", {"test": "success"})
        print("事件发送测试完成")

        print("✅ VNPY架构集成测试通过")
        return True

    except (ImportError, AttributeError, RuntimeError, ConnectionError) as e:
        print(f"❌ VNPY架构集成测试失败: {e}")
        return False


def test_unified_imports():
    """测试统一导入管理"""
    print("\n=== 测试统一导入管理 ===")

    try:
        # 检查模块可用性
        availability = check_module_availability()
        print(f"模块可用性检查完成: {len(availability)} 个模块")

        # 测试日志配置
        logger = setup_logging("test_logger", "DEBUG")
        logger.info("统一导入管理测试日志")
        print("日志配置测试完成")

        # 测试关键模块
        print(f"Pandas可用: {ModuleAvailability.PANDAS}")
        print(f"Psutil可用: {ModuleAvailability.PSUTIL}")
        print(f"VNPY可用: {ModuleAvailability.VNPY}")

        print("✅ 统一导入管理测试通过")
        return True

    except (ImportError, AttributeError, RuntimeError) as e:
        print(f"❌ 统一导入管理测试失败: {e}")
        return False


def test_data_models():
    """测试统一数据模型"""
    print("\n=== 测试统一数据模型 ===")

    try:
        # 测试数据模型创建
        market_data = UnifiedMarketData(
            symbol="000001",
            exchange="SZSE",
            data_type="tick",
            datetime=None,
            timestamp=0,
            open_price=10.0,
            high_price=10.5,
            low_price=9.8,
            close_price=10.2,
            volume=1000,
            turnover=10200.0
        )
        print(f"行情数据模型创建成功: {market_data.symbol}")

        # 测试数据管理器
        manager = get_data_model_manager()
        manager.add_market_data(market_data)

        retrieved_data = manager.get_market_data("000001", "SZSE")
        print(f"数据检索成功: {len(retrieved_data)} 条记录")

        # 测试统计信息
        stats = manager.get_statistics()
        print(f"数据统计: {stats}")

        print("✅ 统一数据模型测试通过")
        return True

    except (ImportError, AttributeError, RuntimeError, ValueError) as e:
        print(f"❌ 统一数据模型测试失败: {e}")
        return False


def test_factories():
    """测试工厂模式"""
    print("\n=== 测试工厂模式 ===")

    try:
        # 获取终端引擎
        engine = get_terminal_engine()

        # 创建统一工厂
        factory = UnifiedFactory(engine)
        print("统一工厂创建成功")

        # 获取工厂状态
        status = factory.get_status()
        print(f"工厂状态: {status}")

        print("✅ 工厂模式测试通过")
        return True

    except (ImportError, AttributeError, RuntimeError) as e:
        print(f"❌ 工厂模式测试失败: {e}")
        return False


def test_shared_services():
    """测试共享服务层"""
    print("\n=== 测试共享服务层 ===")

    try:
        # 测试配置服务
        config_service = ConfigService("test_config.json")
        app_name = config_service.get("app.name")
        print(f"配置服务测试: {app_name}")

        # 测试日志服务
        logging_service = LoggingService(config_service)
        test_logger = logging_service.get_logger("test")
        test_logger.info("共享服务层测试日志")
        print("日志服务测试完成")

        # 测试监控服务（短暂运行）
        engine = get_terminal_engine()
        monitoring_service = MonitoringService(config_service, engine)

        # 等待一小段时间收集监控数据
        time.sleep(2)

        metrics = monitoring_service.get_current_metrics()
        print(f"监控指标收集成功: {len(metrics)} 类指标")

        health_score = monitoring_service.get_system_health_score()
        print(f"系统健康评分: {health_score}")

        # 清理
        monitoring_service.stop_monitoring()

        print("✅ 共享服务层测试通过")
        return True

    except (ImportError, AttributeError, RuntimeError, OSError, IOError) as e:
        print(f"❌ 共享服务层测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🚀 开始核心模块集成测试")
    print("=" * 50)

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 运行所有测试
    tests = [
        test_vnpy_integration,
        test_unified_imports,
        test_data_models,
        test_factories,
        test_shared_services
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except (ImportError, AttributeError, RuntimeError, ValueError) as e:
            print(f"❌ 测试异常: {e}")
            results.append(False)

    # 输出结果摘要
    print("\n" + "=" * 50)
    print("📊 测试结果摘要:")

    passed = sum(results)
    total = len(results)

    for i, (test_func, result) in enumerate(zip(tests, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{i+1}. {test_func.__name__}: {status}")

    print(f"\n总体结果: {passed}/{total} 个测试通过")

    if passed == total:
        print("🎉 所有核心模块测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，需要检查相关模块")
        return 1


if __name__ == "__main__":
    sys.exit(main())

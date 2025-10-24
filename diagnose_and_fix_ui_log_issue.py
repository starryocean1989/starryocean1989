# -*- coding: utf-8 -*-
"""诊断并修复UI日志问题的脚本"""

import sys
import os
import logging

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print("\n" + "=" * 60)
print("UI日志问题诊断和修复脚本")
print("=" * 60 + "\n")

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def diagnose_and_fix():
    """诊断并修复UI日志问题"""

    print("【诊断步骤1】检查VNPY是否可以正常初始化...")
    try:
        from vnpy.event import EventEngine
        from vnpy.trader.engine import MainEngine

        logger.info("正在创建EventEngine...")
        event_engine = EventEngine(interval=1)
        logger.info("✅ EventEngine创建成功")

        logger.info("正在创建MainEngine...")
        main_engine = MainEngine(event_engine)
        logger.info("✅ MainEngine创建成功")

        print("✅ VNPY可以正常初始化\n")

        # 设置到全局
        logger.info("正在设置全局EventEngine和MainEngine...")
        from backend.core.base import set_event_engine, set_main_engine

        set_event_engine(event_engine)
        set_main_engine(main_engine)
        logger.info("✅ 全局引擎已设置\n")

        # 验证设置
        from backend.core.base import get_event_engine, get_main_engine

        if get_event_engine() and get_main_engine():
            print("✅ 全局EventEngine和MainEngine已正确设置\n")
        else:
            print("❌ 全局引擎设置失败\n")
            return False

    except Exception as e:
        logger.error("❌ VNPY初始化失败: %s", e, exc_info=True)
        print(f"❌ VNPY初始化失败: {e}\n")
        print("可能的原因：")
        print("1. vnpy包未正确安装")
        print("2. vnpy依赖包缺失")
        print("3. 系统环境问题")
        return False

    print("【诊断步骤2】测试SystemManagerService初始化...")
    try:
        from backend.services.system_manager_service import SystemManagerService

        logger.info("正在创建SystemManagerService...")
        system_service = SystemManagerService()
        logger.info("✅ SystemManagerService已创建")

        logger.info("正在初始化SystemManagerService...")
        init_success = system_service.initialize()

        if init_success:
            print("✅ SystemManagerService初始化成功\n")
        else:
            print("❌ SystemManagerService初始化失败\n")
            return False

    except Exception as e:
        logger.error("❌ SystemManagerService创建/初始化失败: %s", e, exc_info=True)
        print(f"❌ SystemManagerService失败: {e}\n")
        return False

    print("【诊断步骤3】注册SystemManagerService到ServiceManager...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()
        logger.info("ServiceManager已获取")

        logger.info("正在注册SystemManagerService...")
        register_success = service_manager.register_service(
            "system_manager_service", system_service
        )

        if register_success:
            print("✅ SystemManagerService已注册\n")
        else:
            print("⚠️ SystemManagerService注册失败（可能已存在）\n")

        # 验证注册
        service = service_manager.get_service("system_manager_service", silent=True)
        if service:
            print("✅ 可以从ServiceManager获取SystemManagerService\n")
        else:
            print("❌ 无法从ServiceManager获取SystemManagerService\n")
            return False

    except Exception as e:
        logger.error("❌ 服务注册失败: %s", e, exc_info=True)
        print(f"❌ 服务注册失败: {e}\n")
        return False

    print("【诊断步骤4】测试日志查询...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()
        service = service_manager.get_service("system_manager_service", silent=True)

        logger.info("正在查询日志...")
        result = service.query_logs(limit=5)

        if result.get("success"):
            logs = result.get("logs", [])
            print(f"✅ 日志查询成功，获取到 {len(logs)} 条日志")
            if logs:
                print(f"   第一条: {logs[0].get('timestamp')} - {logs[0].get('message')[:50]}")
            print()
        else:
            print("❌ 日志查询失败\n")
            return False

    except Exception as e:
        logger.error("❌ 日志查询失败: %s", e, exc_info=True)
        print(f"❌ 日志查询失败: {e}\n")
        return False

    print("=" * 60)
    print("✅ 诊断完成：所有测试通过")
    print("=" * 60)
    print()
    print("修复方案：")
    print("1. 问题根因：ServiceInitializer在初始化时，如果VNPY初始化失败，")
    print("   会将EventEngine设置为None，但返回True让系统继续")
    print("2. 这导致SystemManagerService无法初始化，进而导致UI日志为空")
    print("3. 解决方案：确保VNPY正常初始化，或者在VNPY初始化失败时，")
    print("   仍然创建一个EventEngine供SystemManagerService使用")
    print()
    print("建议：")
    print("- 检查启动日志，确认VNPY是否初始化失败")
    print("- 如果VNPY确实失败，需要修复VNPY初始化问题")
    print("- 或者修改代码，在VNPY失败时仍创建EventEngine")
    print()
    return True


if __name__ == "__main__":
    success = diagnose_and_fix()
    sys.exit(0 if success else 1)

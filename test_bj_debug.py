# -*- coding: utf-8 -*-
"""
诊断脚本：模拟UI操作测试北证数据读取
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_with_real_workflow():
    """模拟真实的UI工作流"""
    print("\n" + "=" * 70)
    print("诊断: 模拟UI操作 - 北证市场批量读取")
    print("=" * 70)

    try:
        # 1. 初始化服务（模拟UI启动）
        print("\n步骤1: 初始化服务...")
        from backend.core.base import get_service_manager
        from backend.services.data_center_service import DataCenterService
        from backend.services.system_manager_service import SystemManagerService

        # 注册数据中心服务
        service_manager = get_service_manager()

        data_center_service = DataCenterService()
        data_center_service.initialize()
        service_manager.register_service("data_center_service", data_center_service)
        print("✅ DataCenterService 已注册")

        system_service = SystemManagerService()
        system_service.initialize()
        service_manager.register_service("system_manager_service", system_service)
        print("✅ SystemManagerService 已注册")

        # 2. 加载品种缓存（模拟"刷新品种"按钮）
        print("\n步骤2: 加载品种缓存...")
        result = data_center_service.refresh_symbol_list()
        if result["success"]:
            symbol_count = result.get("symbol_count", 0)
            print(f"✅ 品种缓存加载成功: {symbol_count} 个品种")
        else:
            print(f"❌ 加载失败: {result.get('message')}")
            return False

        # 3. 配置读取参数（模拟UI配置）
        print("\n步骤3: 配置读取参数...")
        config = {
            "data_types": ["day", "5min", "1min"],  # 全部数据类型
            "markets": ["bj"],  # 北证
            "tdx_root": "C:\\new_tdx",
            "use_symbol_cache": True,
            "max_workers": 8,
        }

        print(f"  数据类型: {config['data_types']}")
        print(f"  市场: {config['markets']}")
        print(f"  线程数: {config['max_workers']}")

        # 4. 定义进度回调（模拟UI更新）
        progress_data = {"current": 0, "total": 0, "last_print": 0}

        def progress_callback(current, total, info, success):
            """进度回调"""
            progress_data["current"] = current
            progress_data["total"] = total

            # 每10个或最后一个打印一次
            if current % 10 == 0 or current == total or current == 1:
                progress_pct = int(current / total * 100) if total > 0 else 0
                status_icon = "✅" if success else "❌"
                print(f"  [{progress_pct:3d}%] {status_icon} {current}/{total} - {info}")

        # 5. 执行批量读取
        print("\n步骤4: 执行批量读取...")
        print("-" * 70)

        result = system_service.read_tdx_data(config, progress_callback)

        print("-" * 70)

        # 6. 显示结果
        print("\n步骤5: 结果统计...")
        if result["success"]:
            print(f"✅ 读取成功:")
            print(f"   总任务数: {result.get('total_tasks', 0)}")
            print(f"   成功: {result.get('success_count', 0)}")
            print(f"   失败: {result.get('fail_count', 0)}")
            return True
        else:
            print(f"❌ 读取失败: {result.get('message')}")
            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_with_real_workflow()
    sys.exit(0 if success else 1)

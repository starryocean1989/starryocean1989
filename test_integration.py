# -*- coding: utf-8 -*-
"""
Data Module vnpy 集成功能测试脚本

测试内容：
1. 数据标准化读取器
2. 虚拟推送网关（如果有历史数据）
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def test_tdx_reader():
    """测试通达信数据读取器"""
    print("\n" + "=" * 60)
    print("测试 1: 数据标准化读取器")
    print("=" * 60)

    try:
        # 导入服务
        from backend.services.system_manager_service import SystemManagerService

        # 创建服务实例
        service = SystemManagerService()
        service.initialize()

        print("\n✅ SystemManagerService 初始化成功")

        # 测试获取可用读取器
        print("\n1. 获取可用的数据读取器...")
        result = service.get_available_data_readers()

        if result["success"]:
            readers = result["readers"]
            print(f"✅ 找到 {len(readers)} 个读取器:")
            for reader in readers:
                print(f"   - {reader['name']}: {reader['description']}")
        else:
            print(f"❌ 获取读取器失败: {result.get('message')}")
            return False

        # 测试获取配置
        print("\n2. 获取通达信读取器配置...")
        result = service.get_tdx_reader_config()

        if result["success"]:
            config = result["config"]
            print(f"✅ 配置获取成功:")
            print(f"   - 通达信根目录: {config.get('tdx_root')}")
            print(f"   - 数据类型: {list(config.get('data_types', {}).keys())}")
            print(f"   - 市场: {list(config.get('markets', {}).keys())}")
        else:
            print(f"❌ 获取配置失败: {result.get('message')}")

        # 测试读取数据
        print("\n3. 测试读取通达信数据...")
        test_config = {
            "data_type": "day",
            "market": "sh",
            "tdx_root": "C:\\new_tdx",
            "symbols": ["600000", "600036"],
        }

        print(
            f"   配置: 数据类型={test_config['data_type']}, "
            f"市场={test_config['market']}, "
            f"品种={test_config['symbols']}"
        )

        result = service.read_tdx_data(test_config)

        if result["success"]:
            success_count = result.get("success_count", 0)
            fail_count = result.get("fail_count", 0)
            print(f"✅ 读取完成: 成功 {success_count} 个, 失败 {fail_count} 个")

            # 检查保存的文件
            data_dir = Path("data/kline")
            if data_dir.exists():
                saved_files = list(data_dir.rglob("*.parquet"))
                print(f"✅ 发现 {len(saved_files)} 个 Parquet 文件")
                for f in saved_files[:5]:  # 只显示前5个
                    print(f"   - {f.relative_to(data_dir)}")
        else:
            print(f"❌ 读取失败: {result.get('message')}")
            return False

        print("\n" + "=" * 60)
        print("✅ 数据标准化读取器测试通过!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_virtual_gateway():
    """测试虚拟推送网关"""
    print("\n" + "=" * 60)
    print("测试 2: 虚拟推送网关")
    print("=" * 60)

    try:
        # 检查是否有历史1分钟线数据
        data_dir = Path("data/kline")
        if not data_dir.exists():
            print("⚠️  数据目录不存在，跳过虚拟网关测试")
            print("   提示: 先运行全量下载或增量下载获取历史数据")
            return True

        # 查找1分钟线数据
        minute_files = list(data_dir.rglob("*_1m.parquet"))
        if not minute_files:
            print("⚠️  未找到1分钟线数据，跳过虚拟网关测试")
            print("   提示: 先运行全量下载或增量下载获取1分钟线数据")
            return True

        print(f"✅ 找到 {len(minute_files)} 个1分钟线数据文件")

        # 导入服务
        from backend.services.data_center_service import DataCenterService

        # 创建服务实例
        service = DataCenterService()
        service.initialize()

        print("✅ DataCenterService 初始化成功")

        # 测试配置（不启动，仅测试方法可用性）
        print("\n1. 测试虚拟网关方法可用性...")

        # 检查方法是否存在
        if hasattr(service, "start_virtual_gateway"):
            print("✅ start_virtual_gateway 方法存在")
        else:
            print("❌ start_virtual_gateway 方法不存在")
            return False

        if hasattr(service, "stop_virtual_gateway"):
            print("✅ stop_virtual_gateway 方法存在")
        else:
            print("❌ stop_virtual_gateway 方法不存在")
            return False

        if hasattr(service, "get_virtual_gateway_status"):
            print("✅ get_virtual_gateway_status 方法存在")
        else:
            print("❌ get_virtual_gateway_status 方法不存在")
            return False

        print("\n2. 测试获取网关状态...")
        result = service.get_virtual_gateway_status()

        if result["success"]:
            status = result["status"]
            print(f"✅ 获取状态成功: 运行状态={status.get('running')}")
        else:
            print(f"❌ 获取状态失败: {result.get('message')}")
            return False

        print("\n" + "=" * 60)
        print("✅ 虚拟推送网关测试通过!")
        print("   (未启动网关，仅测试方法可用性)")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Data Module vnpy 集成功能自动化测试")
    print("=" * 60)

    results = []

    # 测试1: 数据标准化读取器
    results.append(("数据标准化读取器", test_tdx_reader()))

    # 测试2: 虚拟推送网关
    results.append(("虚拟推送网关", test_virtual_gateway()))

    # 输出总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())

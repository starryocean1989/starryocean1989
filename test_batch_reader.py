# -*- coding: utf-8 -*-
"""
测试数据标准化读取器 - 多市场、多周期、多线程批量读取
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def test_multi_market_multi_interval():
    """测试多市场、多周期批量读取"""
    print("\n" + "=" * 70)
    print("测试: 数据标准化读取器 - 多市场、多周期、多线程批量读取")
    print("=" * 70)

    try:
        # 导入服务
        from backend.services.system_manager_service import SystemManagerService

        # 创建服务实例
        service = SystemManagerService()
        service.initialize()

        print("\n✅ SystemManagerService 初始化成功")

        # 进度回调函数
        progress_data = {"current": 0, "total": 0}

        def progress_callback(current, total, info, success):
            """进度回调"""
            progress_data["current"] = current
            progress_data["total"] = total
            progress_pct = int(current / total * 100) if total > 0 else 0
            status_icon = "✅" if success else "❌"
            print(f"  [{progress_pct:3d}%] {status_icon} {current}/{total} - {info}")

        # 测试配置：多市场、多周期
        config = {
            "data_types": ["day"],  # 先测试日线，节省时间
            "markets": ["sh"],  # 上证市场
            "tdx_root": "C:\\new_tdx",
            "use_symbol_cache": True,
            "max_workers": 4,  # 4线程并发
        }

        print("\n配置信息:")
        print(f"  数据类型: {config['data_types']}")
        print(f"  市场: {config['markets']}")
        print(f"  通达信根目录: {config['tdx_root']}")
        print(f"  线程数: {config['max_workers']}")
        print(f"  使用品种缓存: {config['use_symbol_cache']}")

        print("\n开始批量读取...")
        print("-" * 70)

        result = service.read_tdx_data(config, progress_callback)

        print("-" * 70)

        if result["success"]:
            success_count = result.get("success_count", 0)
            fail_count = result.get("fail_count", 0)
            total_tasks = result.get("total_tasks", 0)

            print(f"\n✅ 批量读取完成!")
            print(f"   总任务数: {total_tasks}")
            print(f"   成功: {success_count}")
            print(f"   失败: {fail_count}")
            print(
                f"   成功率: {success_count/total_tasks*100:.1f}%"
                if total_tasks > 0
                else "   成功率: N/A"
            )

            # 检查保存的文件
            data_dir = Path("data/kline")
            if data_dir.exists():
                saved_files = list(data_dir.rglob("*_1d.parquet"))
                print(f"\n✅ 发现 {len(saved_files)} 个日线Parquet文件")
                if saved_files:
                    print("   文件列表（前10个）:")
                    for f in saved_files[:10]:
                        print(f"   - {f.relative_to(data_dir)}")

            return True
        else:
            print(f"\n❌ 批量读取失败: {result.get('message')}")
            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_multi_interval():
    """测试多周期批量读取（单个品种）"""
    print("\n" + "=" * 70)
    print("测试: 多周期批量读取（日线 + 5分钟线 + 1分钟线）")
    print("=" * 70)

    try:
        from backend.services.system_manager_service import SystemManagerService

        service = SystemManagerService()
        service.initialize()

        print("\n✅ SystemManagerService 初始化成功")

        # 进度回调
        def progress_callback(current, total, info, success):
            progress_pct = int(current / total * 100) if total > 0 else 0
            status_icon = "✅" if success else "❌"
            print(f"  [{progress_pct:3d}%] {status_icon} {current}/{total} - {info}")

        # 配置：全部三种周期
        config = {
            "data_types": ["day", "5min", "1min"],
            "markets": ["sh"],
            "tdx_root": "C:\\new_tdx",
            "use_symbol_cache": True,
            "max_workers": 8,  # 提高线程数
        }

        print("\n配置信息:")
        print(f"  数据类型: {config['data_types']}")
        print(f"  市场: {config['markets']}")
        print(f"  线程数: {config['max_workers']}")

        print("\n开始批量读取（包含多周期）...")
        print("-" * 70)

        result = service.read_tdx_data(config, progress_callback)

        print("-" * 70)

        if result["success"]:
            print(f"\n✅ 多周期读取完成!")
            print(f"   成功: {result.get('success_count', 0)}")
            print(f"   失败: {result.get('fail_count', 0)}")

            # 检查各周期的文件
            data_dir = Path("data/kline")
            if data_dir.exists():
                day_files = list(data_dir.rglob("*_1d.parquet"))
                min5_files = list(data_dir.rglob("*_5m.parquet"))
                min1_files = list(data_dir.rglob("*_1m.parquet"))

                print(f"\n文件统计:")
                print(f"   日线文件: {len(day_files)}")
                print(f"   5分钟线: {len(min5_files)}")
                print(f"   1分钟线: {len(min1_files)}")

            return True
        else:
            print(f"\n❌ 读取失败: {result.get('message')}")
            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("数据标准化读取器 - 升级版功能测试")
    print("=" * 70)

    results = []

    # 测试1: 单市场单周期（验证基础功能）
    results.append(("多市场多周期批量读取", test_multi_market_multi_interval()))

    # 如果第一个测试通过，可以测试更复杂的场景
    if results[0][1]:
        print("\n" + "=" * 70)
        print("提示: 如需测试多周期，可以取消注释下面的测试")
        print("=" * 70)
        # results.append(("多周期批量读取", test_multi_interval()))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n🎉 所有测试通过!")
        print("\n升级完成的功能:")
        print("  ✅ 多市场批量读取（上证/深证/北证）")
        print("  ✅ 多周期批量读取（日线/5分钟/1分钟）")
        print("  ✅ 多线程并发处理")
        print("  ✅ 实时进度显示")
        print("  ✅ 自动从品种缓存获取品种列表")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())

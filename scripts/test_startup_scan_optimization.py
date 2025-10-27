# -*- coding: utf-8 -*-
"""
启动扫描优化测试脚本

测试启动时只执行阶段0-2，手动触发时执行完整阶段0-3
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_startup_scan():
    """测试启动快速扫描（阶段0-2）"""
    print("\n" + "=" * 70)
    print("测试1: 启动快速扫描（max_phase=2）")
    print("=" * 70)

    from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
    from vnpy.event import EventEngine

    # 创建事件引擎
    event_engine = EventEngine()
    event_engine.start()

    # 创建数据感知器
    sensor = DataSensor(event_engine)

    # 模拟品种列表（少量品种用于测试）
    test_symbols = ["000001", "000002", "600000", "600519", "688001"]

    print(f"\n测试品种: {test_symbols}")
    print("\n开始启动快速扫描...")

    try:
        # 执行快速扫描（max_phase=2）
        overview = sensor.scan_all_data_adaptive(
            reference_symbols=test_symbols,
            intervals=["1d"],
            force_refresh=True,
            max_phase=2,  # 关键：只执行到阶段2
        )

        print("\n✓ 扫描完成!")
        print(f"  - 总品种: {overview.total_symbols}")
        print(f"  - 缺失品种: {overview.missing_symbols}")
        print(f"  - 过时品种: {overview.outdated_symbols}")
        print(f"  - 错误品种: {overview.error_symbols}")
        print(f"  - 警告品种: {overview.warning_symbols}")
        print(f"  - 评分: {overview.quality_score}")

        # 验证是否跳过了阶段3
        if overview.error_symbols == 0 and overview.warning_symbols == 0:
            print("\n✅ 测试通过: 阶段3已跳过（错误和警告品种为0）")
        else:
            print("\n⚠️ 警告: 可能执行了阶段3（存在错误或警告）")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        event_engine.stop()


def test_manual_scan():
    """测试手动完整扫描（阶段0-3）"""
    print("\n" + "=" * 70)
    print("测试2: 手动完整扫描（max_phase=None）")
    print("=" * 70)

    from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
    from vnpy.event import EventEngine

    # 创建事件引擎
    event_engine = EventEngine()
    event_engine.start()

    # 创建数据感知器
    sensor = DataSensor(event_engine)

    # 模拟品种列表（少量品种用于测试）
    test_symbols = ["000001", "000002", "600000", "600519", "688001"]

    print(f"\n测试品种: {test_symbols}")
    print("\n开始完整扫描...")

    try:
        # 执行完整扫描（max_phase=None，默认执行全部）
        overview = sensor.scan_all_data_adaptive(
            reference_symbols=test_symbols,
            intervals=["1d"],
            force_refresh=True,
            max_phase=None,  # 关键：执行全部阶段
        )

        print("\n✓ 扫描完成!")
        print(f"  - 总品种: {overview.total_symbols}")
        print(f"  - 缺失品种: {overview.missing_symbols}")
        print(f"  - 过时品种: {overview.outdated_symbols}")
        print(f"  - 错误品种: {overview.error_symbols}")
        print(f"  - 警告品种: {overview.warning_symbols}")
        print(f"  - 评分: {overview.quality_score}")

        # 验证是否执行了阶段3
        if overview.error_symbols > 0 or overview.warning_symbols > 0 or len(overview.details) > 0:
            print("\n✅ 测试通过: 阶段3已执行（存在详细的问题信息）")
        else:
            print("\n⚠️ 可能的问题: 阶段3可能未执行或没有发现问题")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        event_engine.stop()


def test_max_phase_parameter():
    """测试max_phase参数在不同值时的行为"""
    print("\n" + "=" * 70)
    print("测试3: max_phase参数行为测试")
    print("=" * 70)

    from backend.infrastructure.data_module_vnpy.local_data.data_quality import DataSensor
    from vnpy.event import EventEngine

    test_symbols = ["000001", "000002"]

    for max_phase in [0, 1, 2, 3, None]:
        print(f"\n--- 测试 max_phase={max_phase} ---")

        event_engine = EventEngine()
        event_engine.start()
        sensor = DataSensor(event_engine)

        try:
            overview = sensor.scan_all_data_adaptive(
                reference_symbols=test_symbols,
                intervals=["1d"],
                force_refresh=True,
                max_phase=max_phase,
            )
            print(f"✓ 执行成功 (错误:{overview.error_symbols}, 警告:{overview.warning_symbols})")
        except Exception as e:
            print(f"❌ 执行失败: {e}")
        finally:
            event_engine.stop()


if __name__ == "__main__":
    print("\n启动扫描优化测试")
    print("=" * 70)

    # 测试1: 启动快速扫描
    test_startup_scan()

    # 测试2: 手动完整扫描
    test_manual_scan()

    # 测试3: 参数行为测试
    test_max_phase_parameter()

    print("\n" + "=" * 70)
    print("所有测试完成")
    print("=" * 70)

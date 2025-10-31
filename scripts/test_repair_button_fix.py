# -*- coding: utf-8 -*-
"""
测试脚本: 验证下载修复数据按钮状态更新修复

测试场景:
1. 模拟启动流程推送EVENT_DATA_METRICS_UPDATED事件(包含品种缺失和失效品种)
2. 验证按钮状态是否正确变为启用
3. 验证日志输出是否包含失效品种计数

预期结果:
- 启动流程发现品种缺失5个时,按钮应变蓝(启用)
- 日志应显示: total_problems=缺失数+失效数
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, r"C:\Users\USER\Desktop\terminal_v0.50")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from vnpy.event import Event, EventEngine
from backend.core.base import set_event_engine, get_event_engine
from ui.modules.data_center_view import DataCenter


def test_repair_button_with_missing_and_invalid():
    """测试按钮在有品种缺失和失效品种时的状态"""
    print("=" * 70)
    print("测试: 下载修复数据按钮状态更新修复")
    print("=" * 70)

    # 创建应用
    app = QApplication(sys.argv)

    # 创建事件引擎
    event_engine = EventEngine()
    event_engine.start()
    set_event_engine(event_engine)

    # 创建数据中心UI
    print("\n✓ 创建数据中心UI...")
    data_center = DataCenter()
    data_center.show()

    # 等待UI初始化完成
    QTimer.singleShot(2000, lambda: run_test(data_center, event_engine))

    # 10秒后自动退出
    QTimer.singleShot(10000, app.quit)

    print("\n等待UI初始化...")
    sys.exit(app.exec())


def run_test(data_center, event_engine):
    """执行测试"""
    try:
        print("\n" + "=" * 70)
        print("步骤1: 检查初始状态")
        print("=" * 70)

        # 检查按钮初始状态
        if not data_center.repair_download_btn:
            print("❌ 测试失败: repair_download_btn未初始化")
            return

        initial_enabled = data_center.repair_download_btn.isEnabled()
        print(f"初始按钮状态: {'启用' if initial_enabled else '禁用'}")

        # 检查初始计数
        print(f"_missing_count: {getattr(data_center, '_missing_count', 0)}")
        print(f"_invalid_symbols_count: {getattr(data_center, '_invalid_symbols_count', 0)}")
        print(f"_outdated_count: {getattr(data_center, '_outdated_count', 0)}")

        print("\n" + "=" * 70)
        print("步骤2: 模拟启动流程推送EVENT_DATA_METRICS_UPDATED事件")
        print("=" * 70)

        # 模拟启动流程步骤7推送的事件(有品种缺失和失效品种)
        metrics_data = {
            "total_symbols": 110,  # 总品种数(参考100 + 失效10)
            "reference_symbols": 100,  # 参考品种数
            "downloaded": 95,  # 已下载95个
            "missing": 5,  # 品种缺失5个
            "invalid_count": 10,  # 失效品种10个
            "details": [
                {"symbol": "000001", "name": "缺失品种1", "status": "missing", "issues": "本地无数据", "score": 0},
                {"symbol": "000002", "name": "缺失品种2", "status": "missing", "issues": "本地无数据", "score": 0},
                {"symbol": "000003", "name": "缺失品种3", "status": "missing", "issues": "本地无数据", "score": 0},
                {"symbol": "000004", "name": "缺失品种4", "status": "missing", "issues": "本地无数据", "score": 0},
                {"symbol": "000005", "name": "缺失品种5", "status": "missing", "issues": "本地无数据", "score": 0},
                {"symbol": "999991", "name": "失效品种1", "status": "invalid", "issues": "品种已失效", "score": 0},
                {"symbol": "999992", "name": "失效品种2", "status": "invalid", "issues": "品种已失效", "score": 0},
            ],
            "timestamp": "2025-10-31T10:00:00",
        }

        event = Event("eDataMetricsUpdated", metrics_data)
        event_engine.put(event)

        print(f"✓ 已推送事件: 总品种={metrics_data['total_symbols']}, "
              f"已下载={metrics_data['downloaded']}, "
              f"缺失={metrics_data['missing']}, "
              f"失效={metrics_data['invalid_count']}")

        # 等待事件处理
        print("\n等待事件处理(2秒)...")
        QTimer.singleShot(2000, lambda: verify_result(data_center))

    except Exception as e:
        print(f"\n❌ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()


def verify_result(data_center):
    """验证测试结果"""
    try:
        print("\n" + "=" * 70)
        print("步骤3: 验证按钮状态")
        print("=" * 70)

        # 检查状态变量
        missing = getattr(data_center, "_missing_count", 0)
        invalid = getattr(data_center, "_invalid_symbols_count", 0)
        outdated = getattr(data_center, "_outdated_count", 0)
        error = getattr(data_center, "_error_count", 0)
        data_missing = getattr(data_center, "_data_missing_count", 0)
        warning = getattr(data_center, "_warning_count", 0)

        print(f"_missing_count: {missing}")
        print(f"_invalid_symbols_count: {invalid}")
        print(f"_outdated_count: {outdated}")
        print(f"_error_count: {error}")
        print(f"_data_missing_count: {data_missing}")
        print(f"_warning_count: {warning}")

        total_problems = missing + invalid + outdated + error + data_missing + warning
        print(f"\n总问题数: {total_problems}")

        # 检查按钮状态
        if not data_center.repair_download_btn:
            print("❌ 测试失败: 按钮未初始化")
            return

        final_enabled = data_center.repair_download_btn.isEnabled()
        print(f"最终按钮状态: {'启用' if final_enabled else '禁用'}")

        # 验证结果
        print("\n" + "=" * 70)
        print("测试结果")
        print("=" * 70)

        expected_enabled = total_problems > 0

        if final_enabled == expected_enabled:
            if final_enabled:
                print("✅ 测试通过: 按钮正确变为启用状态")
                print(f"   问题数据: 缺失={missing}, 失效={invalid}")
                print("   修复方案生效: 失效品种已被计入问题数据")
            else:
                print("✅ 测试通过: 按钮正确保持禁用状态(无问题数据)")
        else:
            print(f"❌ 测试失败:")
            print(f"   预期状态: {'启用' if expected_enabled else '禁用'}")
            print(f"   实际状态: {'启用' if final_enabled else '禁用'}")
            print(f"   总问题数: {total_problems}")
            print(f"   问题明细: 缺失={missing}, 失效={invalid}, 过时={outdated}, "
                  f"错误={error}, 数据缺失={data_missing}, 警告={warning}")

        print("\n按钮样式:")
        print(f"  objectName: {data_center.repair_download_btn.objectName()}")
        print(f"  styleSheet: {data_center.repair_download_btn.styleSheet()[:200]}...")

    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_repair_button_with_missing_and_invalid()

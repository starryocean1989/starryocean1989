# -*- coding: utf-8 -*-
"""
完整诊断脚本：检查事件注册和处理流程
用于诊断"下载修复数据"按钮不可点击的问题
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def main():
    """主诊断函数"""
    print("=" * 70)
    print("完整诊断：检查事件注册和处理流程")
    print("=" * 70)

    # 步骤1：检查后端事件常量
    print("\n[诊断] 步骤1: 检查后端事件常量")
    try:
        from backend.infrastructure.data_module_vnpy.data_module import EVENT_DATA_METRICS_UPDATED
        print(f"✅ EVENT_DATA_METRICS_UPDATED = '{EVENT_DATA_METRICS_UPDATED}'")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False

    # 步骤2：检查前端事件处理器是否存在
    print("\n[诊断] 步骤2: 检查前端事件处理器")
    try:
        from ui.modules.data_center_view import DataCenter
        print(f"✅ DataCenter类已导入")
        print(f"✅ 是否有_on_data_metrics_updated方法: {hasattr(DataCenter, '_on_data_metrics_updated')}")

        if hasattr(DataCenter, '_on_data_metrics_updated'):
            handler = getattr(DataCenter, '_on_data_metrics_updated')
            print(f"✅ _on_data_metrics_updated方法: {handler}")
            print(f"✅ 方法名称: {handler.__name__}")
        else:
            print(f"❌ _on_data_metrics_updated方法不存在！")
            return False
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        print(f"异常堆栈:\n{traceback.format_exc()}")
        return False

    # 步骤3：测试事件引擎注册
    print("\n[诊断] 步骤3: 测试事件引擎注册")
    try:
        from vnpy.event import EventEngine, Event

        event_engine = EventEngine()
        event_engine.start()

        received = []
        def handler(event):
            received.append(event)

        event_name = EVENT_DATA_METRICS_UPDATED
        print(f"✅ 准备注册事件: '{event_name}'")

        event_engine.register(event_name, handler)
        print(f"✅ 事件已注册")

        # 验证注册
        if hasattr(event_engine, '_handlers'):
            handlers = event_engine._handlers.get(event_name, [])
            print(f"✅ 验证: 注册了 {len(handlers)} 个处理器")
            if len(handlers) == 0:
                print(f"❌ 警告: 注册后处理器数量为0！")
                return False
        else:
            print(f"❌ event_engine 没有 _handlers 属性")
            return False

        # 测试事件推送
        test_data = {
            "total_symbols": 6128,
            "downloaded": 6123,
            "missing": 5,
            "invalid_count": 0,
            "details": [],
        }
        event = Event(event_name, test_data)
        event_engine.put(event)
        print(f"✅ 事件已推送")

        # 等待处理
        import time
        time.sleep(0.5)

        if len(received) == 0:
            print(f"❌ 警告: 事件未被处理！接收到的事件数: {len(received)}")
            return False
        else:
            print(f"✅ 事件已被处理！接收到的事件数: {len(received)}")

        event_engine.stop()
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        print(f"异常堆栈:\n{traceback.format_exc()}")
        return False

    print("\n" + "=" * 70)
    print("✅ 所有诊断步骤通过")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

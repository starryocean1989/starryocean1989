# -*- coding: utf-8 -*-
"""
测试事件注册和处理流程
用于诊断"下载修复数据"按钮不可点击的问题
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from vnpy.event import EventEngine, Event

def test_event_registration():
    """测试事件注册和处理"""
    print("=" * 70)
    print("测试事件注册和处理流程")
    print("=" * 70)

    # 创建事件引擎
    event_engine = EventEngine()
    event_engine.start()

    # 模拟事件处理器
    received_events = []

    def event_handler(event):
        """事件处理器"""
        print(f"[事件处理] 🔔 事件处理器被调用: event.type={event.type}")
        received_events.append(event)

    # 注册事件
    event_name = "eDataMetricsUpdated"
    print(f"[事件注册] 步骤1: 准备注册事件: {event_name}")
    print(f"[事件注册] 步骤2: 处理器函数={event_handler}")

    try:
        event_engine.register(event_name, event_handler)
        print(f"[事件注册] 步骤3: ✅ 已注册 {event_name}")

        # 验证注册
        if hasattr(event_engine, '_handlers'):
            handlers = event_engine._handlers.get(event_name, [])
            print(f"[事件注册] 验证: {event_name} 注册了 {len(handlers)} 个处理器")
            if len(handlers) == 0:
                print(f"[事件注册] ❌ 警告: {event_name} 注册后处理器数量为0！")
                return False
            else:
                print(f"[事件注册] ✅ 验证通过: {event_name} 已注册 {len(handlers)} 个处理器")
        else:
            print(f"[事件注册] ⚠️ event_engine 没有 _handlers 属性")
            return False

        # 推送测试事件
        print(f"\n[事件推送] 准备推送测试事件: {event_name}")
        test_data = {
            "total_symbols": 6128,
            "downloaded": 6123,
            "missing": 5,
            "invalid_count": 0,
            "details": [],
            "timestamp": "2025-10-31T10:58:04"
        }
        event = Event(event_name, test_data)
        event_engine.put(event)
        print(f"[事件推送] ✅ 已推送事件: {event_name}")

        # 等待事件处理（EventEngine是异步的）
        import time
        time.sleep(0.5)

        # 检查事件是否被处理
        if len(received_events) == 0:
            print(f"[事件处理] ❌ 警告: 事件未被处理！接收到的事件数: {len(received_events)}")
            return False
        else:
            print(f"[事件处理] ✅ 事件已被处理！接收到的事件数: {len(received_events)}")
            return True

    except Exception as e:
        print(f"[事件注册] ❌ 注册失败: {e}")
        import traceback
        print(f"[事件注册] 异常堆栈:\n{traceback.format_exc()}")
        return False
    finally:
        event_engine.stop()

if __name__ == "__main__":
    success = test_event_registration()
    sys.exit(0 if success else 1)

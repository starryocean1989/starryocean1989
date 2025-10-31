# -*- coding: utf-8 -*-
"""
诊断事件注册问题
用于验证事件注册是否成功，以及事件处理器是否被调用
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def diagnose_event_registration():
    """诊断事件注册问题"""
    print("=" * 70)
    print("诊断事件注册问题")
    print("=" * 70)

    try:
        from backend.core.base import get_event_engine
        from vnpy.event import Event

        # 获取全局事件引擎
        event_engine = get_event_engine()
        if not event_engine:
            print("[诊断] ❌ EventEngine不可用")
            return False

        print(f"[诊断] ✅ EventEngine可用: {event_engine}")

        # 检查事件注册
        event_name = "eDataMetricsUpdated"
        if hasattr(event_engine, '_handlers'):
            handlers = event_engine._handlers.get(event_name, [])
            print(f"[诊断] 事件 '{event_name}' 注册了 {len(handlers)} 个处理器")

            if len(handlers) == 0:
                print(f"[诊断] ❌ 事件未注册任何处理器！")
                return False
            else:
                print(f"[诊断] ✅ 事件已注册处理器:")
                for i, handler in enumerate(handlers):
                    print(f"  [{i+1}] {handler}")
        else:
            print(f"[诊断] ⚠️ EventEngine没有_handlers属性")
            return False

        # 测试推送事件
        print(f"[诊断] 测试推送事件...")
        test_data = {
            "total_symbols": 6128,
            "downloaded": 6123,
            "missing": 5,
            "invalid_count": 0,
            "details": [],
        }
        event = Event(event_name, test_data)
        event_engine.put(event)
        print(f"[诊断] ✅ 事件已推送")

        # 等待处理
        import time
        time.sleep(0.5)

        print(f"[诊断] ✅ 诊断完成")
        return True

    except Exception as e:
        print(f"[诊断] ❌ 诊断失败: {e}")
        import traceback
        print(f"[诊断] 异常堆栈:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = diagnose_event_registration()
    sys.exit(0 if success else 1)


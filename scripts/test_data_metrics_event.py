# -*- coding: utf-8 -*-
"""
测试数据指标更新事件的完整流程
用于诊断"下载修复数据"按钮不可点击的问题
"""
import sys
import os

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def test_event_registration_and_handling():
    """测试事件注册和处理流程"""
    print("=" * 70)
    print("测试数据指标更新事件的完整流程")
    print("=" * 70)
    
    try:
        from vnpy.event import EventEngine, Event
        
        # 创建事件引擎
        event_engine = EventEngine()
        event_engine.start()
        
        # 模拟事件处理器
        received_events = []
        
        def event_handler(event):
            """事件处理器"""
            print(f"[测试] 🔔 事件处理器被调用: event.type={event.type}")
            data = event.data
            missing = data.get("missing", 0)
            print(f"[测试] 📊 收到事件: missing={missing}")
            received_events.append(event)
            return missing  # 返回缺失数量，用于验证
        
        # 注册事件
        event_name = "eDataMetricsUpdated"
        print(f"[测试] 步骤1: 准备注册事件: {event_name}")
        
        try:
            event_engine.register(event_name, event_handler)
            print(f"[测试] 步骤2: ✅ 已注册事件")
            
            # 验证注册
            if hasattr(event_engine, '_handlers'):
                handlers = event_engine._handlers.get(event_name, [])
                print(f"[测试] 步骤3: 验证注册，处理器数量={len(handlers)}")
                if len(handlers) == 0:
                    print(f"[测试] ❌ 注册失败：处理器数量为0")
                    return False
            else:
                print(f"[测试] ❌ event_engine没有_handlers属性")
                return False
            
            # 推送测试事件
            print(f"[测试] 步骤4: 准备推送测试事件")
            test_data = {
                "total_symbols": 6128,
                "downloaded": 6123,
                "missing": 5,  # 关键：5个缺失品种
                "invalid_count": 0,
                "details": [],
                "timestamp": "2025-10-31T11:21:18"
            }
            event = Event(event_name, test_data)
            event_engine.put(event)
            print(f"[测试] 步骤5: ✅ 已推送事件")
            
            # 等待事件处理（EventEngine是异步的）
            import time
            time.sleep(0.5)
            
            # 检查事件是否被处理
            if len(received_events) == 0:
                print(f"[测试] ❌ 事件未被处理！接收到的事件数: {len(received_events)}")
                return False
            else:
                print(f"[测试] ✅ 事件已被处理！接收到的事件数: {len(received_events)}")
                # 验证数据
                processed_event = received_events[0]
                processed_missing = processed_event.data.get("missing", 0)
                if processed_missing == 5:
                    print(f"[测试] ✅ 数据验证通过：missing={processed_missing}")
                    return True
                else:
                    print(f"[测试] ❌ 数据验证失败：expected missing=5, actual={processed_missing}")
                    return False
                
        except Exception as e:
            print(f"[测试] ❌ 测试失败: {e}")
            import traceback
            print(f"[测试] 异常堆栈:\n{traceback.format_exc()}")
            return False
        finally:
            event_engine.stop()
            
    except Exception as e:
        print(f"[测试] ❌ 初始化失败: {e}")
        import traceback
        print(f"[测试] 异常堆栈:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    success = test_event_registration_and_handling()
    sys.exit(0 if success else 1)

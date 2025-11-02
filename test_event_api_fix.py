#!/usr/bin/env python3
"""
测试EventEngine API修复
验证Event对象的正确创建和使用
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_event_api():
    """测试Event API的正确使用"""
    try:
        from vnpy.event import Event, EventEngine
        
        # 创建事件引擎
        event_engine = EventEngine()
        
        # 测试正确的Event创建和put调用
        event_data = {
            "test": "data",
            "timestamp": "2025-11-02T14:34:00",
            "severity": "INFO"
        }
        
        # 正确的方式：创建Event对象然后put
        event = Event("TEST_EVENT", event_data)
        print(f"✅ Event对象创建成功: {event}")
        print(f"   事件类型: {event.type}")
        print(f"   事件数据: {event.data}")
        
        # 测试put方法（只接受1个参数：Event对象）
        try:
            event_engine.put(event)
            print("✅ event_engine.put(event) 调用成功")
        except Exception as e:
            print(f"❌ event_engine.put(event) 调用失败: {e}")
        
        # 测试错误的调用方式（应该失败）
        try:
            event_engine.put("TEST_EVENT", event_data)
            print("❌ 错误的API调用竟然成功了！")
        except TypeError as e:
            print(f"✅ 错误的API调用正确地失败了: {e}")
        
        event_engine.stop()
        print("✅ 测试完成")
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("EventEngine API 修复验证")
    print("=" * 50)
    
    success = test_event_api()
    
    if success:
        print("\n🎉 所有测试通过！EventEngine API使用正确。")
    else:
        print("\n❌ 测试失败！需要进一步检查。")
#!/usr/bin/env python3
"""
简单测试ServiceHealthChecker，不涉及UI
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

def test_service_health_checker():
    """测试ServiceHealthChecker"""
    print("开始测试ServiceHealthChecker...")
    
    try:
        # 直接导入ServiceHealthChecker
        from backend.infrastructure.system_vnpy.monitor_toolkit import ServiceHealthChecker
        
        print("✅ ServiceHealthChecker导入成功")
        
        # 创建实例
        checker = ServiceHealthChecker()
        print("✅ ServiceHealthChecker实例创建成功")
        
        # 检查方法
        methods = [m for m in dir(checker) if not m.startswith('_')]
        print(f"可用方法: {methods}")
        
        # 测试check_all_services方法
        if hasattr(checker, 'check_all_services'):
            print("✅ check_all_services方法存在")
            try:
                # 创建一个模拟的service_manager
                class MockServiceManager:
                    def __init__(self):
                        pass
                
                mock_manager = MockServiceManager()
                result = checker.check_all_services(mock_manager)
                print(f"✅ check_all_services调用成功: {type(result)}")
                print(f"结果内容: {result}")
            except Exception as e:
                print(f"❌ check_all_services调用失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ check_all_services方法不存在")
        
        print("测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_service_health_checker()
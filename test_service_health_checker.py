#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ServiceHealthChecker导入和方法
"""

def test_service_health_checker():
    try:
        # 测试导入
        from backend.infrastructure.system_vnpy import ServiceHealthChecker
        print("✓ ServiceHealthChecker导入成功")
        
        # 创建实例
        checker = ServiceHealthChecker()
        print("✓ ServiceHealthChecker实例创建成功")
        
        # 检查方法是否存在
        methods_to_check = [
            'record_call',
            'get_health_status', 
            'quick_check',
            'check_external_dependencies',
            'check_all_services'
        ]
        
        for method_name in methods_to_check:
            if hasattr(checker, method_name):
                print(f"✓ 方法 {method_name} 存在")
            else:
                print(f"✗ 方法 {method_name} 不存在")
        
        # 测试check_all_services方法
        print("\n测试check_all_services方法...")
        try:
            # 创建一个模拟的service_manager
            class MockServiceManager:
                def list_services(self):
                    return []
            
            mock_manager = MockServiceManager()
            result = checker.check_all_services(mock_manager)
            print("✓ check_all_services方法调用成功")
            print(f"返回结果: {result}")
            
        except Exception as e:
            print(f"✗ check_all_services方法调用失败: {e}")
            
    except Exception as e:
        print(f"✗ 导入或测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_service_health_checker()
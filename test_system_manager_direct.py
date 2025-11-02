#!/usr/bin/env python3
"""
直接测试SystemManagerService的ServiceHealthChecker
"""
import sys
import os
import time
from PySide6.QtCore import QTimer, QCoreApplication

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

def test_system_manager_service():
    """测试SystemManagerService的ServiceHealthChecker"""
    print("开始测试SystemManagerService...")
    
    try:
        # 创建Qt应用
        app = QCoreApplication(sys.argv)
        
        # 导入SystemManagerService
        from backend.services.system_manager_service import SystemManagerService
        
        print("✅ SystemManagerService导入成功")
        
        # 创建实例
        service = SystemManagerService()
        print("✅ SystemManagerService实例创建成功")
        
        # 检查ServiceHealthChecker
        print(f"ServiceHealthChecker类型: {type(service.service_health_checker)}")
        print(f"ServiceHealthChecker方法: {[m for m in dir(service.service_health_checker) if not m.startswith('_')]}")
        
        # 测试check_all_services方法
        if hasattr(service.service_health_checker, 'check_all_services'):
            print("✅ check_all_services方法存在")
            try:
                result = service.service_health_checker.check_all_services(service)
                print(f"✅ check_all_services调用成功: {result}")
            except Exception as e:
                print(f"❌ check_all_services调用失败: {e}")
        else:
            print("❌ check_all_services方法不存在")
        
        # 测试_push_service_status方法
        print("测试_push_service_status方法...")
        try:
            service._push_service_status()
            print("✅ _push_service_status调用成功")
        except Exception as e:
            print(f"❌ _push_service_status调用失败: {e}")
            import traceback
            traceback.print_exc()
        
        print("测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_system_manager_service()
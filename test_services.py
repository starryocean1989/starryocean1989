#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证重构后的服务管理器
"""

import traceback

def test_service_manager():
    """测试服务管理器"""
    try:
        print("正在测试服务管理器...")
        
        # 测试导入
        from backend.core.shared_services import get_service_manager, initialize_services
        print("✅ 服务管理器模块导入成功")
        
        # 测试实例化
        service_manager = get_service_manager()
        print("✅ 服务管理器实例化成功")
        
        # 测试初始化服务
        result = initialize_services()
        print(f"✅ 服务初始化结果: {result.get('success', False)}")
        
        # 获取错误报告
        error_report = service_manager.get_user_friendly_error_report()
        print("\n📋 错误报告:")
        print(error_report)
        
        # 测试VnPy服务适配器
        vnpy_service = service_manager.get_service("vnpy_service")
        if vnpy_service:
            print("✅ VnPy服务适配器可用")
            
            # 测试ChinaStock引擎
            chinastock_engine = vnpy_service.get_chinastock_engine()
            if chinastock_engine:
                print("✅ ChinaStock引擎可用")
                
                # 测试获取品种列表
                try:
                    symbols = vnpy_service.get_symbols()
                    print(f"✅ 获取品种列表成功: {len(symbols)}个品种")
                except Exception as e:
                    print(f"⚠️ 获取品种列表失败: {str(e)}")
            else:
                print("⚠️ ChinaStock引擎不可用")
        else:
            print("❌ VnPy服务适配器不可用")
        
        # 测试品种服务
        symbol_service = service_manager.get_service("symbol_service")
        if symbol_service:
            print("✅ 品种服务可用")
        else:
            print("⚠️ 品种服务不可用")
        
        # 测试本地数据服务
        local_data_service = service_manager.get_service("local_data_service")
        if local_data_service:
            print("✅ 本地数据服务可用")
        else:
            print("⚠️ 本地数据服务不可用")
        
        print("\n🎉 服务管理器测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_service_manager()
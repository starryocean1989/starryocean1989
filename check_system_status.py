#!/usr/bin/env python3
"""
检查系统当前状态和监控数据获取情况
"""
import sys
import os
import time
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🔍 检查系统状态...")
    
    try:
        # 1. 检查SystemManagerService状态
        print("\n📊 步骤1: 检查SystemManagerService状态")
        from backend.services.system_manager_service import SystemManagerService
        
        # 创建服务实例
        service = SystemManagerService()
        print("✅ SystemManagerService实例创建成功")
        
        # 检查权限
        has_admin = service._check_admin_privileges()
        print(f"权限状态: {'✅ 有管理员权限' if has_admin else '❌ 无管理员权限'}")
        
        # 检查IPC可用性
        print(f"IPC可用性: {service._ipc_available}")
        print(f"IPC模式: {getattr(service, '_ipc_mode', 'unknown')}")
        
        # 2. 测试数据获取功能
        print("\n📊 步骤2: 测试数据获取功能")
        
        # 测试基础系统数据
        try:
            basic_data = service._get_basic_system_data()
            print("✅ 基础系统数据获取成功:")
            print(f"   - CPU使用率: {basic_data.get('system', {}).get('cpu_percent', 'N/A')}%")
            print(f"   - 内存使用率: {basic_data.get('system', {}).get('memory_percent', 'N/A')}%")
            print(f"   - 数据源: {basic_data.get('source', 'N/A')}")
        except Exception as e:
            print(f"❌ 基础系统数据获取失败: {e}")
        
        # 测试最小系统数据
        try:
            minimal_data = service._get_minimal_system_data()
            print("✅ 最小系统数据获取成功:")
            print(f"   - 平台: {minimal_data.get('system', {}).get('platform', 'N/A')}")
            print(f"   - Python版本: {minimal_data.get('system', {}).get('python_version', 'N/A')}")
            print(f"   - 数据源: {minimal_data.get('source', 'N/A')}")
        except Exception as e:
            print(f"❌ 最小系统数据获取失败: {e}")
        
        # 3. 测试IPC连接（如果可用）
        if service._ipc_available:
            print("\n📊 步骤3: 测试IPC连接")
            try:
                # 这里需要先初始化服务
                print("⚠️ IPC连接测试需要完整的服务初始化，跳过")
            except Exception as e:
                print(f"❌ IPC连接测试失败: {e}")
        else:
            print("\n📊 步骤3: IPC不可用，跳过连接测试")
        
        # 4. 检查监控进程状态
        print("\n📊 步骤4: 检查监控进程状态")
        try:
            signal_file = "logs/monitor_ready.signal"
            if os.path.exists(signal_file):
                import json
                with open(signal_file, 'r') as f:
                    signal_data = json.load(f)
                print("✅ 监控进程信号文件存在:")
                print(f"   - PID: {signal_data.get('pid', 'N/A')}")
                print(f"   - 状态: {signal_data.get('status', 'N/A')}")
                print(f"   - 管道: {signal_data.get('pipes', {})}")
            else:
                print("❌ 监控进程信号文件不存在")
        except Exception as e:
            print(f"❌ 检查监控进程状态失败: {e}")
        
        print("\n✅ 系统状态检查完成")
        
    except Exception as e:
        print(f"❌ 系统状态检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
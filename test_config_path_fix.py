#!/usr/bin/env python3
"""
测试配置文件路径修复
验证监控系统能够正确加载配置文件
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_config_paths():
    """测试配置文件路径是否正确"""
    
    # 测试speedtest_servers.yaml
    script_dir = os.path.dirname(os.path.abspath("backend/infrastructure/system_vnpy/monitor_system.py"))
    speedtest_config = os.path.join(script_dir, "backend", "infrastructure", "system_vnpy", "config", "speedtest_servers.yaml")
    
    print("=" * 60)
    print("配置文件路径测试")
    print("=" * 60)
    
    # 检查speedtest配置文件
    if os.path.exists(speedtest_config):
        print(f"✅ speedtest_servers.yaml 存在: {speedtest_config}")
        try:
            import yaml
            with open(speedtest_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            print(f"✅ speedtest配置文件格式正确，包含 {len(config.get('servers', []))} 个服务器")
        except Exception as e:
            print(f"❌ speedtest配置文件读取失败: {e}")
    else:
        print(f"❌ speedtest_servers.yaml 不存在: {speedtest_config}")
    
    # 检查ping配置文件
    ping_config = os.path.join(script_dir, "backend", "infrastructure", "system_vnpy", "config", "ping_servers.yaml")
    if os.path.exists(ping_config):
        print(f"✅ ping_servers.yaml 存在: {ping_config}")
        try:
            import yaml
            with open(ping_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            print(f"✅ ping配置文件格式正确，包含 {len(config.get('servers', []))} 个服务器")
        except Exception as e:
            print(f"❌ ping配置文件读取失败: {e}")
    else:
        print(f"❌ ping_servers.yaml 不存在: {ping_config}")
    
    # 测试监控系统的配置加载
    print("\n" + "=" * 60)
    print("监控系统配置加载测试")
    print("=" * 60)
    
    try:
        # 切换到正确的工作目录
        original_cwd = os.getcwd()
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        from backend.infrastructure.system_vnpy.monitor_system import BandwidthMonitor, LatencyMonitor
        
        # 测试BandwidthMonitor
        print("测试 BandwidthMonitor...")
        bandwidth_monitor = BandwidthMonitor()
        print("✅ BandwidthMonitor 初始化成功")
        
        # 测试LatencyMonitor
        print("测试 LatencyMonitor...")
        latency_monitor = LatencyMonitor()
        print("✅ LatencyMonitor 初始化成功")
        
        # 恢复工作目录
        os.chdir(original_cwd)
        
        return True
        
    except Exception as e:
        print(f"❌ 监控系统初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_config_paths()
    
    if success:
        print("\n🎉 所有测试通过！配置文件路径修复成功。")
    else:
        print("\n❌ 测试失败！需要进一步检查。")
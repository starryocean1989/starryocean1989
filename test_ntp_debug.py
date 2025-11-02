#!/usr/bin/env python3
"""
NTP时间同步诊断脚本
用于诊断时间同步失败的原因
"""

import ntplib
import socket
import time
from datetime import datetime

# NTP服务器列表
NTP_SERVERS = [
    "ntp.aliyun.com",
    "ntp.tencent.com", 
    "cn.ntp.org.cn",
    "ntp1.aliyun.com",
    "ntp2.aliyun.com",
    "time.windows.com",
    "pool.ntp.org",
    "time.nist.gov",
    "time.google.com"
]

def test_ntp_server(server, timeout=5.0):
    """测试单个NTP服务器"""
    print(f"\n测试服务器: {server}")
    print("-" * 50)
    
    try:
        # 创建NTP客户端
        client = ntplib.NTPClient()
        
        # 记录开始时间
        start_time = time.time()
        
        # 发送NTP请求
        response = client.request(server, version=3, timeout=timeout)
        
        # 记录结束时间
        end_time = time.time()
        request_time = (end_time - start_time) * 1000  # 毫秒
        
        # 解析响应
        offset = response.offset
        delay = response.delay
        
        # 计算网络时间
        network_time = datetime.fromtimestamp(response.tx_time)
        system_time = datetime.now()
        
        print(f"✅ 连接成功")
        print(f"   请求耗时: {request_time:.1f}ms")
        print(f"   网络延迟: {delay*1000:.1f}ms")
        print(f"   时间偏移: {offset:.3f}秒")
        print(f"   系统时间: {system_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"   网络时间: {network_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        
        if abs(offset) > 1.0:
            direction = "慢" if offset > 0 else "快"
            print(f"   ⚠️ 系统时间{direction}了 {abs(offset):.3f}秒")
        else:
            print(f"   ✓ 时间偏差在正常范围内 ({abs(offset)*1000:.1f}毫秒)")
            
        return True, offset, delay, request_time
        
    except socket.timeout:
        print(f"❌ 连接超时 (>{timeout}秒)")
        return False, None, None, None
        
    except socket.gaierror as e:
        print(f"❌ DNS解析失败: {e}")
        return False, None, None, None
        
    except ConnectionRefusedError:
        print(f"❌ 连接被拒绝")
        return False, None, None, None
        
    except OSError as e:
        print(f"❌ 网络错误: {e}")
        return False, None, None, None
        
    except Exception as e:
        print(f"❌ 未知错误: {type(e).__name__}: {e}")
        return False, None, None, None

def test_network_connectivity():
    """测试网络连通性"""
    print("测试网络连通性")
    print("=" * 50)
    
    test_hosts = [
        ("百度", "www.baidu.com", 80),
        ("阿里云", "www.aliyun.com", 80),
        ("腾讯", "www.qq.com", 80),
        ("Google DNS", "8.8.8.8", 53)
    ]
    
    for name, host, port in test_hosts:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print(f"✅ {name} ({host}:{port}) - 连接成功")
            else:
                print(f"❌ {name} ({host}:{port}) - 连接失败")
                
        except Exception as e:
            print(f"❌ {name} ({host}:{port}) - 错误: {e}")

def main():
    """主函数"""
    print("NTP时间同步诊断工具")
    print("=" * 50)
    print(f"当前系统时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"ntplib版本: {getattr(ntplib, '__version__', '未知')}")
    print()
    
    # 测试网络连通性
    test_network_connectivity()
    print()
    
    # 测试NTP服务器
    print("测试NTP服务器")
    print("=" * 50)
    
    successful_servers = []
    failed_servers = []
    
    for server in NTP_SERVERS:
        success, offset, delay, request_time = test_ntp_server(server)
        
        if success:
            successful_servers.append({
                'server': server,
                'offset': offset,
                'delay': delay,
                'request_time': request_time
            })
        else:
            failed_servers.append(server)
    
    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)
    
    print(f"成功的服务器: {len(successful_servers)}/{len(NTP_SERVERS)}")
    print(f"失败的服务器: {len(failed_servers)}/{len(NTP_SERVERS)}")
    
    if successful_servers:
        print("\n✅ 可用的NTP服务器:")
        for server_info in successful_servers:
            print(f"   {server_info['server']}: "
                  f"偏移{server_info['offset']:.3f}秒, "
                  f"延迟{server_info['delay']*1000:.1f}ms, "
                  f"响应{server_info['request_time']:.1f}ms")
        
        # 推荐最佳服务器
        best_server = min(successful_servers, key=lambda x: x['request_time'])
        print(f"\n🏆 推荐服务器: {best_server['server']} (响应最快: {best_server['request_time']:.1f}ms)")
    
    if failed_servers:
        print(f"\n❌ 失败的服务器: {', '.join(failed_servers)}")
    
    if not successful_servers:
        print("\n⚠️ 所有NTP服务器都无法连接!")
        print("可能的原因:")
        print("1. 网络连接问题")
        print("2. 防火墙阻止NTP请求 (UDP 123端口)")
        print("3. 代理服务器配置问题")
        print("4. DNS解析问题")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简单的NTP测试脚本"""

import socket
import ntplib
import time

def test_dns(server):
    """测试DNS解析"""
    try:
        ip = socket.gethostbyname(server)
        print(f"✅ DNS解析成功: {server} -> {ip}")
        return True, ip
    except Exception as e:
        print(f"❌ DNS解析失败: {server} - {e}")
        return False, None

def test_ntp(server, timeout=3):
    """测试NTP同步"""
    print(f"\n测试NTP服务器: {server}")
    print("-" * 50)
    
    try:
        client = ntplib.NTPClient()
        start = time.time()
        
        response = client.request(server, version=3, timeout=timeout)
        elapsed = (time.time() - start) * 1000
        
        print(f"✅ NTP同步成功!")
        print(f"   响应时间: {elapsed:.0f}ms")
        print(f"   时间偏移: {response.offset:.3f}秒")
        print(f"   网络延迟: {response.delay*1000:.1f}ms")
        return True
        
    except socket.timeout:
        print(f"❌ 连接超时 (>{timeout}秒)")
        return False
    except socket.gaierror as e:
        print(f"❌ DNS解析失败: {e}")
        return False
    except Exception as e:
        print(f"❌ NTP请求失败: {type(e).__name__}: {e}")
        return False

# 测试列表
servers = [
    "ntp.aliyun.com",
    "ntp.tencent.com",
    "cn.ntp.org.cn",
    "time.windows.com"
]

print("=" * 50)
print("NTP时间同步诊断工具")
print("=" * 50)

print("\n步骤1: DNS解析测试")
print("-" * 50)
for server in servers:
    test_dns(server)

print("\n步骤2: NTP同步测试")
print("=" * 50)
success_count = 0
for server in servers:
    if test_ntp(server, timeout=10):
        success_count += 1

print("\n" + "=" * 50)
print("测试总结")
print("=" * 50)
print(f"成功: {success_count}/{len(servers)}")

if success_count == 0:
    print("\n❌ 所有NTP服务器都无法连接!")
    print("可能原因:")
    print("1. 防火墙阻止了UDP 123端口")
    print("2. 网络配置问题")
    print("3. 需要代理服务器")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络问题诊断脚本 - 区分防火墙 vs 代理问题

诊断策略:
1. 检查系统代理设置
2. 测试直连 vs 代理连接
3. 测试UDP/TCP协议差异
4. 检查环境变量
5. 测试HTTPS连接(代理通常支持)
"""

import os
import socket
import urllib.request
import urllib.error
import winreg
from typing import Dict, Optional, Tuple

def get_windows_proxy_settings() -> Dict[str, Optional[str]]:
    """获取Windows系统代理设置"""
    proxy_settings = {
        'http_proxy': None,
        'https_proxy': None,
        'proxy_enable': False,
        'proxy_server': None,
        'proxy_override': None
    }
    
    try:
        # 读取注册表
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        ) as key:
            try:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                proxy_settings['proxy_enable'] = bool(proxy_enable)
            except FileNotFoundError:
                pass
            
            try:
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                proxy_settings['proxy_server'] = proxy_server
            except FileNotFoundError:
                pass
            
            try:
                proxy_override, _ = winreg.QueryValueEx(key, "ProxyOverride")
                proxy_settings['proxy_override'] = proxy_override
            except FileNotFoundError:
                pass
    
    except Exception as e:
        print(f"⚠️ 读取注册表失败: {e}")
    
    return proxy_settings


def get_environment_proxy() -> Dict[str, Optional[str]]:
    """获取环境变量中的代理设置"""
    return {
        'HTTP_PROXY': os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy'),
        'HTTPS_PROXY': os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'),
        'NO_PROXY': os.environ.get('NO_PROXY') or os.environ.get('no_proxy'),
        'ALL_PROXY': os.environ.get('ALL_PROXY') or os.environ.get('all_proxy')
    }


def test_http_connection(url: str, use_proxy: bool = True, timeout: float = 5.0) -> Tuple[bool, Optional[str]]:
    """测试HTTP连接"""
    try:
        if use_proxy:
            # 使用系统代理
            request = urllib.request.Request(url)
            response = urllib.request.urlopen(request, timeout=timeout)
        else:
            # 禁用代理
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            response = opener.open(url, timeout=timeout)
        
        status = response.getcode()
        response.close()
        return True, f"HTTP {status}"
    
    except urllib.error.URLError as e:
        return False, f"URLError: {e.reason}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


def test_raw_socket_connection(host: str, port: int, protocol: str = "tcp", timeout: float = 3.0) -> Tuple[bool, Optional[str]]:
    """测试原始socket连接"""
    try:
        if protocol.lower() == "tcp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        sock.settimeout(timeout)
        
        if protocol.lower() == "tcp":
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True, "连接成功"
            else:
                return False, f"连接失败(错误码: {result})"
        else:
            # UDP - 发送测试数据包
            sock.sendto(b'\x1b' + 47 * b'\0', (host, port))
            try:
                data, _ = sock.recvfrom(1024)
                sock.close()
                return True, "收到响应"
            except socket.timeout:
                sock.close()
                return False, "超时无响应"
    
    except socket.gaierror:
        return False, "DNS解析失败"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)}"


def print_separator(title: str = "", char: str = "=", length: int = 100):
    """打印分隔线"""
    if title:
        print(f"\n{char * length}")
        print(f"{title}")
        print(f"{char * length}\n")
    else:
        print(f"{char * length}")


def main():
    """主函数"""
    print_separator("网络问题诊断工具 - 防火墙 vs 代理")
    
    # 第1步: 检查代理配置
    print_separator("【步骤1】检查系统代理配置", "-")
    
    print("1.1 Windows系统代理设置:")
    win_proxy = get_windows_proxy_settings()
    for key, value in win_proxy.items():
        print(f"    {key}: {value}")
    
    print("\n1.2 环境变量代理设置:")
    env_proxy = get_environment_proxy()
    has_proxy = False
    for key, value in env_proxy.items():
        if value:
            has_proxy = True
            print(f"    {key}: {value}")
    
    if not has_proxy and not win_proxy['proxy_enable']:
        print("    ✅ 未检测到代理配置")
    else:
        print("    ⚠️ 检测到代理配置")
    
    # 第2步: 测试HTTP连接(有/无代理)
    print_separator("【步骤2】测试HTTP连接", "-")
    
    test_url = "http://www.baidu.com"
    
    print(f"2.1 使用系统代理访问 {test_url}:")
    success_with_proxy, msg_with_proxy = test_http_connection(test_url, use_proxy=True)
    print(f"    {'✅' if success_with_proxy else '❌'} {msg_with_proxy}")
    
    print(f"\n2.2 禁用代理访问 {test_url}:")
    success_without_proxy, msg_without_proxy = test_http_connection(test_url, use_proxy=False)
    print(f"    {'✅' if success_without_proxy else '❌'} {msg_without_proxy}")
    
    # 第3步: 测试UDP vs TCP
    print_separator("【步骤3】测试UDP vs TCP原始连接", "-")
    
    test_host = "ntp.aliyun.com"
    test_port = 123
    
    print(f"3.1 TCP连接到 {test_host}:{test_port}:")
    tcp_success, tcp_msg = test_raw_socket_connection(test_host, test_port, "tcp")
    print(f"    {'✅' if tcp_success else '❌'} {tcp_msg}")
    
    print(f"\n3.2 UDP连接到 {test_host}:{test_port}:")
    udp_success, udp_msg = test_raw_socket_connection(test_host, test_port, "udp")
    print(f"    {'✅' if udp_success else '❌'} {udp_msg}")
    
    # 第4步: 测试HTTPS连接
    print_separator("【步骤4】测试HTTPS连接(代理通常支持)", "-")
    
    https_url = "https://www.baidu.com"
    
    print(f"4.1 HTTPS连接到 {https_url}:")
    https_success, https_msg = test_http_connection(https_url, use_proxy=True)
    print(f"    {'✅' if https_success else '❌'} {https_msg}")
    
    # 第5步: 测试HTTP时间API
    print_separator("【步骤5】测试HTTP时间API(备用方案)", "-")
    
    time_apis = [
        "http://worldtimeapi.org/api/timezone/Asia/Shanghai",
        "http://worldclockapi.com/api/json/utc/now"
    ]
    
    for api_url in time_apis:
        api_success, api_msg = test_http_connection(api_url, use_proxy=True, timeout=5.0)
        print(f"    {api_url}")
        print(f"    {'✅' if api_success else '❌'} {api_msg}\n")
    
    # 诊断结论
    print_separator("【诊断结论】", "=")
    
    has_system_proxy = win_proxy['proxy_enable'] or any(env_proxy.values())
    
    print("分析结果:\n")
    
    # 场景1: 有代理配置
    if has_system_proxy:
        print("🔍 检测到代理配置")
        if success_with_proxy and not success_without_proxy:
            print("📌 结论: 网络访问依赖代理")
            print("   - HTTP/HTTPS通过代理正常工作")
            print("   - 原因: 企业网络或受限环境,必须通过代理上网")
        elif success_without_proxy:
            print("📌 结论: 代理配置存在但直连也可用")
            print("   - 代理可能是可选的或未生效")
    else:
        print("🔍 未检测到代理配置")
    
    # 场景2: UDP问题
    if not udp_success and tcp_success:
        print("\n📌 关键发现: UDP被阻止但TCP可通")
        print("   - 原因分析:")
        print("     1. 防火墙策略禁用UDP协议")
        print("     2. 安全策略限制UDP流量")
        print("     3. 网络设备(路由器/交换机)过滤UDP")
        if has_system_proxy:
            print("     4. 代理服务器不支持UDP转发(常见)")
        print("\n   - 解决方案:")
        print("     ✅ 使用HTTP时间API作为备用(推荐)")
        print("     ⚠️ 联系网络管理员开放UDP 123端口(如需NTP)")
    
    elif not udp_success and not tcp_success:
        print("\n📌 关键发现: UDP和TCP都被阻止")
        print("   - 原因分析:")
        print("     1. 123端口被完全封锁")
        print("     2. 目标服务器被防火墙黑名单")
        if has_system_proxy:
            print("     3. 代理限制了对NTP服务器的访问")
        print("\n   - 解决方案:")
        print("     ✅ 必须使用HTTP时间API")
    
    elif udp_success:
        print("\n✅ UDP连接正常")
        print("   - NTP时间同步应该可以正常工作")
        print("   - 如果仍失败,可能是ntplib库或代码问题")
    
    # HTTP API可用性
    print("\n" + "-" * 100)
    if any(test_http_connection(url, use_proxy=True, timeout=3.0)[0] for url in time_apis):
        print("✅ HTTP时间API可用 - 可以作为NTP的可靠备用方案")
    else:
        print("❌ HTTP时间API也不可用 - 网络限制严重,只能使用系统时间")
    
    print_separator()


if __name__ == "__main__":
    main()

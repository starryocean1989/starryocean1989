#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NTP授时TCP vs UDP连接测试脚本

功能：
1. 测试UDP连接NTP服务器（标准NTP协议）
2. 测试TCP连接NTP服务器的123端口
3. 对比两种协议的可达性和响应时间
"""

import socket
import struct
import time
from datetime import datetime
from typing import Tuple, Optional

# NTP服务器列表
NTP_SERVERS = [
    "ntp.aliyun.com",
    "ntp.tencent.com",
    "cn.ntp.org.cn",
    "ntp1.aliyun.com",
    "time.windows.com",
    "pool.ntp.org"
]

# NTP常量
NTP_PORT = 123
NTP_PACKET_FORMAT = "!12I"
NTP_DELTA = 2208988800  # 1970-01-01 到 1900-01-01 的秒数


def create_ntp_packet():
    """创建NTP请求数据包"""
    # NTP版本3，客户端模式
    packet = b'\x1b' + 47 * b'\0'
    return packet


def parse_ntp_response(data: bytes) -> Optional[float]:
    """解析NTP响应获取时间戳"""
    try:
        if len(data) < 48:
            return None
        
        # 提取transmit timestamp (bytes 40-47)
        unpacked = struct.unpack(NTP_PACKET_FORMAT, data)
        timestamp = unpacked[10] + float(unpacked[11]) / 2**32
        
        # 转换为Unix时间戳
        unix_timestamp = timestamp - NTP_DELTA
        return unix_timestamp
    except Exception:
        return None


def test_ntp_udp(server: str, timeout: float = 3.0) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    使用UDP测试NTP服务器（标准NTP协议）
    
    Returns:
        (是否成功, 响应时间ms, 错误信息)
    """
    try:
        # 解析服务器地址
        addr = socket.getaddrinfo(server, NTP_PORT, socket.AF_INET, socket.SOCK_DGRAM)[0][4]
        
        # 创建UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        # 发送NTP请求
        packet = create_ntp_packet()
        start_time = time.time()
        sock.sendto(packet, addr)
        
        # 接收响应
        data, _ = sock.recvfrom(1024)
        elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
        
        sock.close()
        
        # 解析时间戳
        timestamp = parse_ntp_response(data)
        if timestamp:
            return True, elapsed, None
        else:
            return False, None, "无法解析NTP响应"
            
    except socket.timeout:
        return False, None, "连接超时"
    except socket.gaierror as e:
        return False, None, f"DNS解析失败: {e}"
    except OSError as e:
        return False, None, f"网络错误: {e}"
    except Exception as e:
        return False, None, f"未知错误: {type(e).__name__}: {e}"


def test_tcp_connection(server: str, port: int = 123, timeout: float = 3.0) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    使用TCP测试端口连接（仅测试端口可达性，不是标准NTP）
    
    Returns:
        (是否成功, 响应时间ms, 错误信息)
    """
    try:
        # 解析服务器地址
        addr_info = socket.getaddrinfo(server, port, socket.AF_INET, socket.SOCK_STREAM)
        if not addr_info:
            return False, None, "无法解析服务器地址"
        
        addr = addr_info[0][4]
        
        # 创建TCP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        # 尝试连接
        start_time = time.time()
        result = sock.connect_ex(addr)
        elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
        
        sock.close()
        
        if result == 0:
            return True, elapsed, None
        else:
            return False, None, f"连接被拒绝 (错误代码: {result})"
            
    except socket.timeout:
        return False, None, "连接超时"
    except socket.gaierror as e:
        return False, None, f"DNS解析失败: {e}"
    except OSError as e:
        return False, None, f"网络错误: {e}"
    except Exception as e:
        return False, None, f"未知错误: {type(e).__name__}: {e}"


def print_header():
    """打印表头"""
    print("=" * 100)
    print("NTP服务器TCP vs UDP连接测试")
    print("=" * 100)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试服务器数量: {len(NTP_SERVERS)}")
    print("=" * 100)
    print()


def print_server_result(server: str, udp_result: Tuple, tcp_result: Tuple):
    """打印单个服务器的测试结果"""
    print(f"\n{'=' * 100}")
    print(f"服务器: {server}")
    print(f"{'-' * 100}")
    
    # UDP结果
    udp_success, udp_time, udp_error = udp_result
    print(f"UDP (标准NTP协议):")
    if udp_success:
        print(f"  ✅ 成功 - 响应时间: {udp_time:.1f}ms")
    else:
        print(f"  ❌ 失败 - {udp_error}")
    
    # TCP结果
    tcp_success, tcp_time, tcp_error = tcp_result
    print(f"TCP (端口123连接):")
    if tcp_success:
        print(f"  ✅ 成功 - 响应时间: {tcp_time:.1f}ms")
    else:
        print(f"  ❌ 失败 - {tcp_error}")
    
    # 对比分析
    print(f"\n对比分析:")
    if udp_success and tcp_success:
        print(f"  ℹ️  两种协议都可达")
        faster = "UDP" if udp_time < tcp_time else "TCP"
        print(f"  ℹ️  {faster}更快 (UDP: {udp_time:.1f}ms, TCP: {tcp_time:.1f}ms)")
    elif udp_success:
        print(f"  ⚠️  仅UDP可达 (NTP服务器通常只支持UDP)")
    elif tcp_success:
        print(f"  ⚠️  仅TCP可达 (不常见，可能是代理或防火墙转发)")
    else:
        print(f"  ❌ 两种协议都不可达 (可能被防火墙阻止)")


def print_summary(results: dict):
    """打印汇总统计"""
    print("\n" + "=" * 100)
    print("测试汇总")
    print("=" * 100)
    
    udp_success_count = sum(1 for r in results.values() if r["udp"][0])
    tcp_success_count = sum(1 for r in results.values() if r["tcp"][0])
    total_count = len(results)
    
    print(f"\nUDP连接统计:")
    print(f"  成功: {udp_success_count}/{total_count} ({udp_success_count/total_count*100:.1f}%)")
    print(f"  失败: {total_count - udp_success_count}/{total_count}")
    
    print(f"\nTCP连接统计:")
    print(f"  成功: {tcp_success_count}/{total_count} ({tcp_success_count/total_count*100:.1f}%)")
    print(f"  失败: {total_count - tcp_success_count}/{total_count}")
    
    print(f"\n结论:")
    if udp_success_count > 0:
        print(f"  ✅ UDP协议可用，NTP时间同步应该正常工作")
    else:
        print(f"  ❌ UDP协议不可用，可能被防火墙阻止")
        print(f"  💡 建议使用HTTP时间API作为备用方案")
    
    if tcp_success_count > 0 and udp_success_count == 0:
        print(f"  ⚠️  TCP可达但UDP不可达，说明123端口本身没有被阻止")
        print(f"  💡 可能是UDP协议被防火墙策略禁用")
    
    # 推荐的服务器
    if udp_success_count > 0:
        fastest_udp = None
        fastest_time = float('inf')
        for server, result in results.items():
            if result["udp"][0] and result["udp"][1] < fastest_time:
                fastest_time = result["udp"][1]
                fastest_udp = server
        
        if fastest_udp:
            print(f"\n推荐使用: {fastest_udp} (响应最快: {fastest_time:.1f}ms)")


def main():
    """主函数"""
    print_header()
    
    results = {}
    
    for server in NTP_SERVERS:
        print(f"\n正在测试 {server}...")
        
        # 测试UDP
        print(f"  - 测试UDP...")
        udp_result = test_ntp_udp(server, timeout=3.0)
        
        # 测试TCP
        print(f"  - 测试TCP...")
        tcp_result = test_tcp_connection(server, port=123, timeout=3.0)
        
        results[server] = {
            "udp": udp_result,
            "tcp": tcp_result
        }
        
        # 打印结果
        print_server_result(server, udp_result, tcp_result)
    
    # 打印汇总
    print_summary(results)
    
    print("\n" + "=" * 100)
    print("测试完成")
    print("=" * 100)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows防火墙状态检查脚本

功能:
1. 检查Windows防火墙是否启用
2. 检查NTP相关的防火墙规则
3. 提供配置建议
"""

import subprocess
import sys
import os

def run_command(cmd: str) -> tuple:
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def check_admin_rights() -> bool:
    """检查是否有管理员权限"""
    try:
        # 尝试读取需要管理员权限的注册表
        result = subprocess.run(
            'net session',
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except:
        return False


def check_firewall_status():
    """检查防火墙状态"""
    print("=" * 80)
    print("Windows防火墙状态检查")
    print("=" * 80)
    print()
    
    # 检查管理员权限
    is_admin = check_admin_rights()
    if is_admin:
        print("✅ 已具有管理员权限")
    else:
        print("⚠️ 未以管理员身份运行(部分功能受限)")
    print()
    
    # 检查防火墙状态
    print("-" * 80)
    print("【1】防火墙启用状态")
    print("-" * 80)
    
    success, stdout, stderr = run_command('netsh advfirewall show allprofiles state')
    if success and stdout:
        lines = stdout.split('\n')
        for line in lines:
            if 'State' in line or '状态' in line:
                print(f"  {line.strip()}")
    else:
        print("  ❌ 无法获取防火墙状态")
    print()
    
    # 检查NTP相关规则
    print("-" * 80)
    print("【2】NTP相关防火墙规则")
    print("-" * 80)
    
    rules_to_check = [
        "Python NTP UDP Outbound",
        "NTP Client UDP Outbound"
    ]
    
    found_rules = []
    
    for rule_name in rules_to_check:
        success, stdout, stderr = run_command(
            f'netsh advfirewall firewall show rule name="{rule_name}"'
        )
        if success and 'No rules match' not in stdout and '找不到' not in stdout:
            found_rules.append(rule_name)
            print(f"  ✅ 已找到规则: {rule_name}")
            # 解析规则详情
            for line in stdout.split('\n'):
                if 'Enabled' in line or '启用' in line:
                    print(f"      {line.strip()}")
                elif 'Direction' in line or '方向' in line:
                    print(f"      {line.strip()}")
                elif 'Action' in line or '操作' in line:
                    print(f"      {line.strip()}")
        else:
            print(f"  ❌ 未找到规则: {rule_name}")
    print()
    
    # 检查UDP 123端口相关的所有规则
    print("-" * 80)
    print("【3】所有UDP 123端口规则")
    print("-" * 80)
    
    success, stdout, stderr = run_command(
        'netsh advfirewall firewall show rule name=all | findstr /i "123"'
    )
    
    if success and stdout:
        print("  找到以下包含'123'的规则:")
        for line in stdout.split('\n'):
            if line.strip():
                print(f"      {line.strip()}")
    else:
        print("  未找到UDP 123端口相关规则")
    print()
    
    # 诊断建议
    print("=" * 80)
    print("诊断结果与建议")
    print("=" * 80)
    print()
    
    if not found_rules:
        print("⚠️ 未找到NTP防火墙规则")
        print()
        print("建议操作:")
        print("  1. 运行配置脚本(需管理员权限):")
        print("     右键 scripts\\configure_firewall_for_ntp.bat")
        print("     选择 '以管理员身份运行'")
        print()
        print("  2. 或手动配置防火墙:")
        print("     - 打开 Windows Defender 防火墙")
        print("     - 高级设置 -> 出站规则 -> 新建规则")
        print("     - 选择 '端口' -> UDP -> 远程端口 123")
        print("     - 允许连接 -> 完成")
        print()
    else:
        print("✅ 已找到NTP防火墙规则")
        print()
        print("如果NTP仍然无法工作，可能原因:")
        print("  1. 规则未启用 - 检查上方规则状态")
        print("  2. 其他安全软件阻止 - 检查杀毒软件/第三方防火墙")
        print("  3. 路由器/网关限制 - 联系网络管理员")
        print()
        print("测试建议:")
        print("  运行: python scripts\\test_ntp_tcp_vs_udp.py")
        print()
    
    # HTTP时间API提醒
    print("-" * 80)
    print()
    print("💡 备用方案:")
    print("   即使UDP被阻止,系统已实现HTTP时间API备用方案")
    print("   时间同步会自动降级,不影响系统正常运行")
    print()
    print("=" * 80)


if __name__ == "__main__":
    check_firewall_status()

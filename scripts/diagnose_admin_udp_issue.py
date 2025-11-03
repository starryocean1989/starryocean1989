#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理员账户UDP问题诊断

专门诊断"管理员账户UDP失败,普通账户正常"的问题
"""

import os
import subprocess
import ctypes
import socket

def is_admin():
    """检查是否以管理员身份运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def get_current_user_info():
    """获取当前用户信息"""
    print("=" * 80)
    print("当前用户信息")
    print("=" * 80)
    
    # 用户名
    username = os.environ.get('USERNAME', 'Unknown')
    print(f"用户名: {username}")
    
    # 是否管理员
    admin_status = is_admin()
    print(f"管理员权限: {'✅ 是' if admin_status else '❌ 否'}")
    
    # 用户配置文件路径
    userprofile = os.environ.get('USERPROFILE', 'Unknown')
    print(f"用户配置: {userprofile}")
    
    print()

def check_windows_firewall_profiles():
    """检查不同配置文件的防火墙状态"""
    print("=" * 80)
    print("Windows防火墙配置文件状态")
    print("=" * 80)
    
    profiles = ['domainprofile', 'privateprofile', 'publicprofile']
    
    for profile in profiles:
        print(f"\n【{profile.upper()}】")
        cmd = f'netsh advfirewall show {profile}'
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'State' in line or '状态' in line:
                        print(f"  {line.strip()}")
                    elif 'Inbound' in line or '入站' in line:
                        print(f"  {line.strip()}")
                    elif 'Outbound' in line or '出站' in line:
                        print(f"  {line.strip()}")
        except Exception as e:
            print(f"  ❌ 检查失败: {e}")
    
    print()

def test_udp_as_current_user():
    """以当前用户身份测试UDP"""
    print("=" * 80)
    print("UDP连接测试(当前用户)")
    print("=" * 80)
    print()
    
    test_server = "ntp.aliyun.com"
    test_port = 123
    
    print(f"测试服务器: {test_server}:{test_port}")
    print(f"当前用户: {os.environ.get('USERNAME')}")
    print(f"管理员权限: {'是' if is_admin() else '否'}")
    print()
    
    try:
        # 创建UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        
        # 发送NTP请求
        packet = b'\x1b' + 47 * b'\0'
        sock.sendto(packet, (test_server, test_port))
        
        # 尝试接收
        try:
            data, addr = sock.recvfrom(1024)
            print(f"✅ UDP连接成功!")
            print(f"   收到 {len(data)} 字节数据")
            sock.close()
            return True
        except socket.timeout:
            print(f"❌ UDP超时(3秒)")
            sock.close()
            return False
            
    except Exception as e:
        print(f"❌ UDP连接失败: {type(e).__name__}: {e}")
        return False

def check_local_security_policy():
    """检查本地安全策略"""
    print("=" * 80)
    print("本地安全策略检查")
    print("=" * 80)
    print()
    
    if not is_admin():
        print("⚠️ 需要管理员权限才能检查安全策略")
        print()
        return
    
    # 检查组策略中的网络相关设置
    print("检查组策略设置...")
    
    try:
        # 尝试读取相关注册表项
        cmd = r'reg query "HKLM\SOFTWARE\Policies\Microsoft\Windows Defender Firewall" /s'
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )
        
        if result.returncode == 0 and result.stdout.strip():
            print("✅ 找到Windows Defender防火墙策略:")
            print(result.stdout)
        else:
            print("ℹ️  未找到特殊的防火墙策略配置")
    except Exception as e:
        print(f"⚠️ 检查失败: {e}")
    
    print()

def check_network_isolation_settings():
    """检查网络隔离设置"""
    print("=" * 80)
    print("网络隔离与权限检查")
    print("=" * 80)
    print()
    
    # 检查IntegrityLevel (完整性级别)
    try:
        cmd = 'whoami /groups'
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore'
        )
        
        if 'Mandatory Label' in result.stdout or '强制标签' in result.stdout:
            print("进程完整性级别:")
            for line in result.stdout.split('\n'):
                if 'Mandatory' in line or '强制' in line or 'High' in line or 'Medium' in line:
                    print(f"  {line.strip()}")
        
        # 检查是否有管理员组
        if 'Administrators' in result.stdout or '管理员' in result.stdout:
            print("\n✅ 当前用户属于管理员组")
        else:
            print("\n❌ 当前用户不属于管理员组")
            
    except Exception as e:
        print(f"⚠️ 检查失败: {e}")
    
    print()

def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "管理员账户UDP问题诊断" + " " * 20 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    # 1. 用户信息
    get_current_user_info()
    
    # 2. 防火墙配置文件
    check_windows_firewall_profiles()
    
    # 3. UDP测试
    udp_success = test_udp_as_current_user()
    
    # 4. 安全策略
    check_local_security_policy()
    
    # 5. 网络隔离设置
    check_network_isolation_settings()
    
    # 诊断结论
    print("=" * 80)
    print("诊断结论")
    print("=" * 80)
    print()
    
    if is_admin() and not udp_success:
        print("🔍 问题确认: 管理员账户下UDP被阻止")
        print()
        print("可能的原因:")
        print()
        print("1️⃣  Windows Defender应用控制 (AppLocker)")
        print("   - 管理员账户可能启用了更严格的应用控制策略")
        print("   - 检查: gpedit.msc -> 计算机配置 -> Windows设置 -> 安全设置 -> 应用程序控制策略")
        print()
        print("2️⃣  增强的保护模式 (Enhanced Protected Mode)")
        print("   - 某些安全软件对管理员进程有特殊限制")
        print("   - 尝试以普通用户权限运行应用")
        print()
        print("3️⃣  防火墙对管理员进程的特殊规则")
        print("   - 某些防火墙会对管理员权限的进程应用不同规则")
        print("   - 检查防火墙的'高级安全'设置")
        print()
        print("4️⃣  用户账户控制(UAC)虚拟化")
        print("   - UAC可能导致管理员进程的网络访问受限")
        print("   - 文件和注册表虚拟化可能影响网络设置")
        print()
        print("=" * 80)
        print("建议解决方案:")
        print("=" * 80)
        print()
        print("✅ 方案1: 使用普通用户权限运行 (推荐)")
        print("   不要以'管理员身份运行'启动应用")
        print("   直接双击启动批处理文件即可")
        print()
        print("✅ 方案2: 添加防火墙例外")
        print("   右键运行(管理员): scripts\\configure_firewall_for_ntp.bat")
        print("   为Python添加明确的UDP出站规则")
        print()
        print("✅ 方案3: 使用HTTP时间API (已实现)")
        print("   系统已自动降级到HTTP时间服务")
        print("   不影响正常使用")
        print()
    elif not is_admin() and udp_success:
        print("✅ 普通用户权限下UDP正常工作")
        print()
        print("建议:")
        print("  不要以管理员身份运行应用,使用普通权限即可")
        print()
    elif is_admin() and udp_success:
        print("✅ 管理员权限下UDP正常工作")
        print()
        print("问题可能已解决或不是权限相关问题")
        print()
    else:
        print("⚠️ 两种权限下UDP都无法工作")
        print()
        print("建议使用HTTP时间API备用方案(已实现)")
        print()
    
    print("=" * 80)

if __name__ == "__main__":
    main()

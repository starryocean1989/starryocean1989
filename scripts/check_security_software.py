#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查第三方安全软件"""

import subprocess
import re

def check_running_security_software():
    """检查正在运行的安全软件"""
    print("=" * 80)
    print("检查第三方安全软件")
    print("=" * 80)
    print()
    
    # 常见安全软件进程名
    security_processes = {
        '360': ['360tray.exe', '360sd.exe', 'ZhuDongFangYu.exe'],
        '腾讯电脑管家': ['QQPCTray.exe', 'QQPCRTP.exe'],
        '金山毒霸': ['kxetray.exe', 'KSafeTray.exe'],
        '瑞星': ['RavMonD.exe', 'RsTray.exe'],
        'McAfee': ['mcshield.exe', 'mfemms.exe'],
        'Norton': ['ccSvcHst.exe', 'NortonSecurity.exe'],
        'Kaspersky': ['avp.exe', 'kavtray.exe'],
        'Avast': ['AvastUI.exe', 'AvastSvc.exe'],
        'AVG': ['avgui.exe', 'avgsvc.exe']
    }
    
    # 获取所有进程
    try:
        result = subprocess.run(
            'tasklist',
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk'
        )
        
        running_processes = result.stdout.lower()
        
        found_software = []
        
        for software_name, processes in security_processes.items():
            for process in processes:
                if process.lower() in running_processes:
                    found_software.append(software_name)
                    break
        
        if found_software:
            print("⚠️ 检测到以下安全软件正在运行:")
            for software in set(found_software):
                print(f"   - {software}")
            print()
            print("建议操作:")
            print("  1. 打开安全软件的防火墙设置")
            print("  2. 查找'流量监控'或'网络防护'功能")
            print("  3. 将Python.exe添加到白名单或允许UDP连接")
            print("  4. 或临时关闭防火墙功能进行测试")
        else:
            print("✅ 未检测到常见的第三方安全软件")
            print()
            print("可能的其他原因:")
            print("  1. 路由器/网关设备的防火墙")
            print("  2. 企业网络的安全策略")
            print("  3. ISP级别的UDP过滤")
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    check_running_security_software()

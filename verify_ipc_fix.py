# -*- coding: utf-8 -*-
"""
验证IPC修复效果

检查修复后的代码是否正确处理大缓冲区
"""

import re
import sys
from pathlib import Path

def check_file_fixes():
    """检查文件修复情况"""
    project_root = Path(__file__).parent
    
    fixes_applied = []
    issues_found = []
    
    # 检查system_manager_service.py
    service_file = project_root / "backend/services/system_manager_service.py"
    if service_file.exists():
        content = service_file.read_text(encoding='utf-8')
        
        # 检查是否使用了大缓冲区
        large_buffer_pattern = r'\.read\(size=65536\)'
        matches = re.findall(large_buffer_pattern, content)
        
        if len(matches) >= 3:  # 应该有3处修改
            fixes_applied.append(f"✅ system_manager_service.py: 已应用大缓冲区修复 ({len(matches)}处)")
        else:
            issues_found.append(f"❌ system_manager_service.py: 大缓冲区修复不完整 ({len(matches)}/3)")
        
        # 检查JSON错误处理
        json_error_pattern = r'json\.JSONDecodeError'
        if re.search(json_error_pattern, content):
            fixes_applied.append("✅ system_manager_service.py: 已添加JSON错误处理")
        else:
            issues_found.append("❌ system_manager_service.py: 缺少JSON错误处理")
    
    # 检查monitor_system.py
    monitor_file = project_root / "backend/infrastructure/system_vnpy/monitor_system.py"
    if monitor_file.exists():
        content = monitor_file.read_text(encoding='utf-8')
        
        # 检查是否使用了大缓冲区
        large_buffer_pattern = r'\.read\(size=65536\)'
        matches = re.findall(large_buffer_pattern, content)
        
        if len(matches) >= 2:  # 应该有2处修改
            fixes_applied.append(f"✅ monitor_system.py: 已应用大缓冲区修复 ({len(matches)}处)")
        else:
            issues_found.append(f"❌ monitor_system.py: 大缓冲区修复不完整 ({len(matches)}/2)")
        
        # 检查数据大小检查
        size_check_pattern = r'len\(response_bytes\) > 32768'
        if re.search(size_check_pattern, content):
            fixes_applied.append("✅ monitor_system.py: 已添加数据大小检查")
        else:
            issues_found.append("❌ monitor_system.py: 缺少数据大小检查")
        
        # 检查JSON压缩
        json_compress_pattern = r'separators=\(\'\,\', \':\'\)'
        if re.search(json_compress_pattern, content):
            fixes_applied.append("✅ monitor_system.py: 已启用JSON压缩")
        else:
            issues_found.append("❌ monitor_system.py: 缺少JSON压缩")
    
    return fixes_applied, issues_found

def check_buffer_size_issue():
    """检查缓冲区大小问题的理论分析"""
    print("\n=== IPC缓冲区问题分析 ===")
    print("问题根因：")
    print("1. native_ipc默认缓冲区大小为4096字节")
    print("2. 监控数据JSON序列化后超过4KB")
    print("3. 数据在4096字节处被截断，导致JSON解析失败")
    print()
    print("修复方案：")
    print("1. 增加读取缓冲区大小到65536字节（64KB）")
    print("2. 添加数据大小检查和警告")
    print("3. 启用JSON压缩减少数据量")
    print("4. 改进错误处理和日志记录")
    print()

def main():
    """主函数"""
    print("=== IPC修复验证工具 ===")
    
    # 检查修复情况
    fixes_applied, issues_found = check_file_fixes()
    
    print("\n=== 修复应用情况 ===")
    for fix in fixes_applied:
        print(fix)
    
    if issues_found:
        print("\n=== 发现的问题 ===")
        for issue in issues_found:
            print(issue)
    
    # 理论分析
    check_buffer_size_issue()
    
    # 总结
    print("=== 修复总结 ===")
    if len(fixes_applied) >= 5 and not issues_found:
        print("🎉 所有修复已正确应用！")
        print("建议：重新启动终端以测试修复效果")
    elif fixes_applied:
        print("⚠️ 部分修复已应用，但可能还有遗漏")
        print("建议：检查上述问题并完善修复")
    else:
        print("❌ 修复未正确应用")
        print("建议：重新应用修复代码")
    
    print("\n=== 测试建议 ===")
    print("1. 重新启动终端应用")
    print("2. 观察日志中是否还有JSON解析错误")
    print("3. 检查IPC连接测试是否成功")
    print("4. 监控数据查询是否正常工作")

if __name__ == "__main__":
    main()
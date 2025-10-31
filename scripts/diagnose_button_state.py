# -*- coding: utf-8 -*-
"""
诊断脚本：检查下载修复数据按钮的状态

使用方法：
1. 打开终端应用
2. 在Python控制台中运行此脚本
3. 查看输出的状态变量值
"""

import sys
sys.path.insert(0, r"C:\Users\USER\Desktop\terminal_v0.50")

def diagnose_button_state():
    """诊断按钮状态"""
    print("=" * 70)
    print("诊断：下载修复数据按钮状态")
    print("=" * 70)
    
    # 说明
    print("\n请在终端应用运行后，在数据中心界面执行以下代码：")
    print("\n" + "=" * 70)
    print("# 在Python控制台中执行（假设data_center是数据中心界面实例）:")
    print("=" * 70)
    
    diagnostic_code = """
# 获取状态变量
missing = getattr(data_center, '_missing_count', 0)
invalid = getattr(data_center, '_invalid_symbols_count', 0)
outdated = getattr(data_center, '_outdated_count', 0)
error = getattr(data_center, '_error_count', 0)
data_missing = getattr(data_center, '_data_missing_count', 0)
warning = getattr(data_center, '_warning_count', 0)

total_problems = missing + invalid + outdated + error + data_missing + warning

print(f"状态变量值:")
print(f"  _missing_count (品种缺失): {missing}")
print(f"  _invalid_symbols_count (失效品种): {invalid}")
print(f"  _outdated_count (过时): {outdated}")
print(f"  _error_count (错误): {error}")
print(f"  _data_missing_count (数据缺失): {data_missing}")
print(f"  _warning_count (警告): {warning}")
print(f"\\n总问题数: {total_problems}")
print(f"按钮应启用: {total_problems > 0}")

# 检查按钮实际状态
if data_center.repair_download_btn:
    actual_enabled = data_center.repair_download_btn.isEnabled()
    print(f"\\n按钮实际状态: {'启用' if actual_enabled else '禁用'}")
    
    if (total_problems > 0) != actual_enabled:
        print("\\n❌ 警告：按钮状态与预期不符！")
        print(f"   预期: {'启用' if total_problems > 0 else '禁用'}")
        print(f"   实际: {'启用' if actual_enabled else '禁用'}")
        
        # 手动触发状态更新
        print("\\n尝试手动触发状态更新...")
        data_center._update_repair_button_state()
        
        new_enabled = data_center.repair_download_btn.isEnabled()
        print(f"手动更新后状态: {'启用' if new_enabled else '禁用'}")
    else:
        print("\\n✅ 按钮状态正确")
else:
    print("\\n❌ 错误：repair_download_btn未初始化")
"""
    
    print(diagnostic_code)
    print("=" * 70)
    
    print("\n如果没有Python控制台，请按以下步骤操作：")
    print("1. 关闭当前终端应用（如果正在运行）")
    print("2. 重新启动终端应用（修改的代码会生效）")
    print("3. 等待启动流程完成")
    print("4. 查看数据中心 -> 本地数据 -> 数据质量概览")
    print("5. 观察「下载修复数据」按钮的颜色")
    print("\n预期结果：")
    print("  - 如果有品种缺失或失效品种 → 按钮应该是蓝绿色（可点击）")
    print("  - 如果没有任何问题 → 按钮应该是灰色（禁用）")
    
    print("\n" + "=" * 70)
    print("提示：检查AI日志文件获取更详细的诊断信息")
    print("日志路径: C:\\Users\\USER\\Desktop\\terminal_v0.50\\logs\\ai\\")
    print("=" * 70)


if __name__ == "__main__":
    diagnose_button_state()

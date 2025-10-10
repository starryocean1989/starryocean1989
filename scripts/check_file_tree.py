# -*- coding: utf-8 -*-
"""
检查文件树状态的诊断脚本
"""
import os
import sys

# 添加项目根目录到路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

print("=" * 60)
print("策略中心文件树诊断工具")
print("=" * 60)

# 检查策略目录
strategy_dir = os.path.join(project_root, "strategies", "user_strategies")
print(f"\n1. 策略目录: {strategy_dir}")
print(f"   存在: {os.path.exists(strategy_dir)}")

if os.path.exists(strategy_dir):
    files = [f for f in os.listdir(strategy_dir) if f.endswith(".py") and not f.startswith("__")]
    print(f"   文件数量: {len(files)}")
    for f in files:
        file_path = os.path.join(strategy_dir, f)
        file_size = os.path.getsize(file_path)
        print(f"   - {f} ({file_size} bytes)")
else:
    print("   ❌ 目录不存在！")

# 检查模板目录
template_dir = os.path.join(project_root, "strategies", "templates")
print(f"\n2. 模板目录: {template_dir}")
print(f"   存在: {os.path.exists(template_dir)}")

if os.path.exists(template_dir):
    files = [f for f in os.listdir(template_dir) if f.endswith(".py") and not f.startswith("__")]
    print(f"   文件数量: {len(files)}")
    for f in files:
        file_path = os.path.join(template_dir, f)
        file_size = os.path.getsize(file_path)
        print(f"   - {f} ({file_size} bytes)")
else:
    print("   ❌ 目录不存在！")

# 检查当前工作目录
print(f"\n3. 当前工作目录: {os.getcwd()}")
print(f"   项目根目录: {project_root}")

# 检查最新的日志
log_file = os.path.join(project_root, "logs", "terminal_v0.50.log.old")
print(f"\n4. 检查日志文件: {log_file}")
if os.path.exists(log_file):
    print("   ✅ 日志文件存在")
    print("\n   查找文件树相关日志...")
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            relevant_lines = [
                line
                for line in lines[-500:]  # 只看最后500行
                if "文件树" in line or "策略目录" in line or "找到策略文件" in line
            ]
            if relevant_lines:
                print(f"   找到 {len(relevant_lines)} 条相关日志:")
                for line in relevant_lines[-10:]:  # 显示最后10条
                    print(f"   {line.strip()}")
            else:
                print("   ⚠️ 未找到文件树相关日志（可能还没有启动过新版本）")
    except Exception as e:
        print(f"   ❌ 读取日志失败: {e}")
else:
    print("   ⚠️ 日志文件不存在")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)

# -*- coding: utf-8 -*-
"""
测试后端初始化流程
"""

import os
import sys
from pathlib import Path

# 设置项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

print("=" * 70)
print("测试后端初始化流程")
print("=" * 70)

# 测试1: 导入初始化函数
print("\n[测试1] 导入initialize_services...")
try:
    from backend.core.base import initialize_services

    print("✅ 导入成功")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 测试2: 创建进度回调
print("\n[测试2] 创建进度回调...")
progress_log = []


def progress_callback(message: str, progress: int):
    """记录进度"""
    log_entry = f"[{progress}%] {message}"
    print(log_entry)
    progress_log.append(log_entry)


print("✅ 进度回调已创建")

# 测试3: 执行初始化
print("\n[测试3] 执行initialize_services(带进度回调)...")
print("-" * 70)
try:
    result = initialize_services(progress_callback=progress_callback)
    print("-" * 70)
    print("✅ 初始化执行完成")
    print(f"结果: success={result.get('success')}")
except Exception as e:
    print("-" * 70)
    print(f"❌ 初始化失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 测试4: 验证进度记录
print("\n[测试4] 验证进度记录...")
print(f"记录的进度更新次数: {len(progress_log)}")
if progress_log:
    print("进度更新列表:")
    for log in progress_log:
        print(f"  {log}")
    print("✅ 进度回调正常工作")
else:
    print("⚠️ 警告: 没有记录到进度更新")

print("\n" + "=" * 70)
print("✅ 所有测试完成")
print("=" * 70)

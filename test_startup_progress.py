# -*- coding: utf-8 -*-
"""
测试启动进度 - 验证UI能否从20%顺利推进到100%
"""

import os
import sys
import time
from pathlib import Path

# 设置项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

print("=" * 70)
print("测试启动进度")
print("=" * 70)

# 初始化配置
print("\n[1/3] 初始化配置...")
from backend.config import init_settings

init_settings()
print("✅ 配置初始化完成")

# 测试后端初始化带进度回调
print("\n[2/3] 测试后端初始化（带进度回调）...")
print("-" * 70)

progress_log = []


def progress_callback(message: str, progress: int):
    """记录进度"""
    log_entry = f"[{progress:3d}%] {message}"
    print(log_entry)
    progress_log.append((progress, message))

    # 检查是否卡住
    if len(progress_log) > 1:
        prev_progress = progress_log[-2][0]
        if progress == prev_progress:
            print(f"  ⚠️ 警告: 进度未增长")


try:
    from backend.core.base import initialize_services

    start_time = time.time()
    result = initialize_services(progress_callback=progress_callback)
    elapsed = time.time() - start_time

    print("-" * 70)
    print(f"✅ 初始化完成，总耗时: {elapsed:.2f}秒")
    print(f"   结果: success={result.get('success')}")

except Exception as e:
    print("-" * 70)
    print(f"❌ 初始化失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 验证进度记录
print("\n[3/3] 验证进度记录...")
print(f"总进度更新次数: {len(progress_log)}")

if not progress_log:
    print("❌ 错误: 没有记录到任何进度更新")
    sys.exit(1)

# 检查进度范围
min_progress = min(p[0] for p in progress_log)
max_progress = max(p[0] for p in progress_log)
print(f"进度范围: {min_progress}% → {max_progress}%")

# 检查关键进度点
expected_milestones = [20, 40, 60, 75, 90, 95, 100]
found_milestones = []
for milestone in expected_milestones:
    # 允许±5%的误差
    if any(abs(p[0] - milestone) <= 5 for p in progress_log):
        found_milestones.append(milestone)

print(f"找到的里程碑: {found_milestones}")
print(f"预期的里程碑: {expected_milestones}")

if max_progress >= 95:
    print("✅ 进度成功推进到95%以上")
else:
    print(f"❌ 警告: 进度只到{max_progress}%，未达到95%")

# 检查是否有卡顿
print("\n进度流畅性检查:")
stuck_points = []
for i in range(1, len(progress_log)):
    prev_progress, prev_msg = progress_log[i - 1]
    curr_progress, curr_msg = progress_log[i]
    if curr_progress == prev_progress:
        stuck_points.append((prev_progress, prev_msg, curr_msg))

if stuck_points:
    print(f"⚠️ 发现 {len(stuck_points)} 个卡顿点:")
    for progress, msg1, msg2 in stuck_points[:5]:  # 只显示前5个
        print(f"  - {progress}%: {msg1} → {msg2}")
else:
    print("✅ 没有发现明显卡顿")

print("\n" + "=" * 70)
if max_progress >= 95 and result.get("success"):
    print("✅ 启动进度测试通过！")
else:
    print("⚠️ 启动进度测试有问题，请检查日志")
print("=" * 70)

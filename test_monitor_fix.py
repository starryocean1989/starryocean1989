# -*- coding: utf-8 -*-
"""测试监控进程修复"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 60)
print("测试监控进程修复")
print("=" * 60)

# 测试1: 导入logging_system
print("\n测试1: 导入logging_system...")
try:
    from backend.infrastructure.system_vnpy.logging_system import setup_subprocess_logging
    print("✅ logging_system导入成功")
except Exception as e:
    print(f"❌ logging_system导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试2: 导入monitor_system
print("\n测试2: 导入monitor_system...")
try:
    from backend.infrastructure.system_vnpy import monitor_system
    print("✅ monitor_system导入成功")
except Exception as e:
    print(f"❌ monitor_system导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试3: 检查修复是否应用
print("\n测试3: 检查修复代码...")
import inspect

# 检查monitor_system.main()是否有早期信号文件代码
main_source = inspect.getsource(monitor_system.main)
if "Level 0信号文件已创建" in main_source:
    print("✅ monitor_system.main() 早期信号文件代码已应用")
else:
    print("❌ monitor_system.main() 缺少早期信号文件代码")

# 检查setup_subprocess_logging是否修复了process_name
setup_source = inspect.getsource(setup_subprocess_logging)
if '"process_name": process_name' in setup_source:
    print("❌ logging_system.setup_subprocess_logging() 仍有process_name冲突")
else:
    print("✅ logging_system.setup_subprocess_logging() process_name冲突已修复")

print("\n" + "=" * 60)
print("所有测试完成！")
print("=" * 60)

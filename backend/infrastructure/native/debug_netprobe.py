# -*- coding: utf-8 -*-
"""直接测试netprobe模块的debug脚本"""
import sys
import time
from pathlib import Path

# 添加native目录到路径
native_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(native_dir))

print("=" * 60)
print("开始debug netprobe模块")
print("=" * 60)

print("\n步骤1: 导入模块...")
try:
    import native_netprobe
    print(f"✓ native_netprobe模块导入成功")
    print(f"  NETPROBE_AVAILABLE: {native_netprobe.NETPROBE_AVAILABLE}")
except Exception as e:
    print(f"✗ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n步骤2: 测试单个连接（极短超时）...")
print("  目标: 127.0.0.1:65534, 超时: 0.01秒")
start = time.time()
try:
    result = native_netprobe.test_connection("127.0.0.1", 65534, timeout=0.01)
    elapsed = time.time() - start
    print(f"✓ 测试完成，耗时: {elapsed:.3f}秒")
    print(f"  结果: {result}")
except Exception as e:
    elapsed = time.time() - start
    print(f"✗ 测试失败，耗时: {elapsed:.3f}秒")
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()

print("\n步骤3: 测试批量连接（极短超时）...")
print("  目标: 2个不可达地址, 超时: 0.01秒")
start = time.time()
try:
    servers = [("127.0.0.1", 65534), ("127.0.0.1", 65533)]
    result = native_netprobe.batch_test_connections(servers, timeout=0.01, max_concurrent=2)
    elapsed = time.time() - start
    print(f"✓ 测试完成，耗时: {elapsed:.3f}秒")
    print(f"  结果: total={result['total']}, success={result['success']}, timeout={result['timeout']}, error={result['error']}")
except Exception as e:
    elapsed = time.time() - start
    print(f"✗ 测试失败，耗时: {elapsed:.3f}秒")
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Debug测试结束")
print("=" * 60)

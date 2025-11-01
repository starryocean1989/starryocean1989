"""快速测试 LoadBalancer 和 TdxDataReader"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("快速测试开始...")
print("=" * 80)

# 测试1: 导入 LoadBalancer
print("\n[测试1] 导入 LoadBalancer...")
try:
    from backend.infrastructure.data_module_vnpy.load_balancer import (
        LoadBalancer,
        TaskCategory,
        TaskConfig,
    )
    print("✅ LoadBalancer 导入成功")
except Exception as e:
    print(f"❌ LoadBalancer 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试2: TaskCategory 枚举
print("\n[测试2] TaskCategory 枚举...")
try:
    assert TaskCategory.NETWORK_DOWNLOAD == "network_download"
    assert TaskCategory.LOCAL_SCAN == "local_scan"
    assert TaskCategory.LOCAL_READ == "local_read"
    print("✅ TaskCategory 枚举定义正确")
    print(f"  - NETWORK_DOWNLOAD: {TaskCategory.NETWORK_DOWNLOAD}")
    print(f"  - LOCAL_SCAN: {TaskCategory.LOCAL_SCAN}")
    print(f"  - LOCAL_READ: {TaskCategory.LOCAL_READ}")
except Exception as e:
    print(f"❌ TaskCategory 枚举测试失败: {e}")
    sys.exit(1)

# 测试3: 创建 TaskConfig
print("\n[测试3] 创建 TaskConfig...")
try:
    task = TaskConfig(
        name="test_task",
        category=TaskCategory.LOCAL_READ,
        total_count=1000,
        is_io_intensive=True,
    )
    print("✅ TaskConfig 创建成功")
    print(f"  - name: {task.name}")
    print(f"  - category: {task.category}")
    print(f"  - total_count: {task.total_count}")
except Exception as e:
    print(f"❌ TaskConfig 创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试4: LoadBalancer.get_optimal_config()
print("\n[测试4] LoadBalancer.get_optimal_config()...")
try:
    lb = LoadBalancer()
    config = lb.get_optimal_config(task=task)
    print("✅ get_optimal_config() 执行成功")
    print(f"  - processes: {config.get('processes')}")
    print(f"  - coroutines_per_process: {config.get('coroutines_per_process')}")
    print(f"  - max_concurrent_connections: {config.get('max_concurrent_connections')}")
except Exception as e:
    print(f"❌ get_optimal_config() 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试5: 导入 TdxDataReader
print("\n[测试5] 导入 TdxDataReader...")
try:
    from backend.infrastructure.data_module_vnpy.data_acquisition import TdxDataReader
    print("✅ TdxDataReader 导入成功")
except Exception as e:
    print(f"❌ TdxDataReader 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试6: 创建 TdxDataReader 实例
print("\n[测试6] 创建 TdxDataReader 实例...")
try:
    reader = TdxDataReader(tdx_root_path=Path("C:/new_tdx"))
    print("✅ TdxDataReader 实例创建成功")
    print(f"  - TDX根目录: {reader.tdx_root}")
except Exception as e:
    print(f"❌ TdxDataReader 实例创建失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试7: 市场自动判断
print("\n[测试7] 市场自动判断...")
try:
    market_sh = TdxDataReader._get_market_from_symbol("600000")
    market_sz = TdxDataReader._get_market_from_symbol("000001")
    market_bj = TdxDataReader._get_market_from_symbol("430047")
    
    assert market_sh == "sh", f"预期 'sh', 得到 '{market_sh}'"
    assert market_sz == "sz", f"预期 'sz', 得到 '{market_sz}'"
    assert market_bj == "bj", f"预期 'bj', 得到 '{market_bj}'"
    
    print("✅ 市场自动判断成功")
    print(f"  - 600000 -> {market_sh}")
    print(f"  - 000001 -> {market_sz}")
    print(f"  - 430047 -> {market_bj}")
except Exception as e:
    print(f"❌ 市场自动判断失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ 所有快速测试通过！")
print("=" * 80)

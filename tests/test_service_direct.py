# -*- coding: utf-8 -*-
"""直接测试data_center_service在应用环境中的状态."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print("=" * 80)
print("测试：直接调用data_center_service")
print("=" * 80)

# 1. 初始化服务（模拟应用启动）
print("\n【步骤1】初始化服务...")
from backend.core.base import initialize_services, get_service_manager

init_result = initialize_services()
print(f"  初始化结果: {init_result.get('success')}")

# 2. 获取服务
service_manager = get_service_manager()
data_center_service = service_manager.get_service("data_center_service")

print(f"\n【步骤2】服务状态检查...")
print(f"  data_center_service: {data_center_service}")
print(f"  类型: {type(data_center_service)}")

if not data_center_service:
    print("❌ 服务不可用")
    sys.exit(1)

# 3. 检查服务健康状态
print(f"\n【步骤3】检查服务健康状态...")
try:
    health = data_center_service.health_check()
    print(f"  健康检查: {health}")
except Exception as e:
    print(f"  健康检查失败: {e}")

# 4. 检查china_stock_engine
print(f"\n【步骤4】检查china_stock_engine...")
try:
    china_stock_engine = data_center_service.china_stock_engine
    print(f"  china_stock_engine: {china_stock_engine}")
    print(f"  类型: {type(china_stock_engine)}")

    if china_stock_engine:
        # 检查stock_fetcher
        print(f"  stock_fetcher: {china_stock_engine.stock_fetcher}")
        print(f"  block_parser: {china_stock_engine.block_parser}")
except Exception as e:
    print(f"  检查失败: {e}")
    import traceback

    traceback.print_exc()

# 5. 尝试简单调用
print(f"\n【步骤5】尝试调用 get_symbol_list()...")
try:
    import time

    start = time.time()

    print("  调用 get_symbol_list()...")
    result = data_center_service.get_symbol_list()

    elapsed = time.time() - start
    print(f"  ✅ 成功！耗时: {elapsed:.2f}秒")
    print(f"  返回类型: {type(result)}")
    print(f"  数据量: {len(result.get('data', []))} 个品种")

except Exception as e:
    print(f"  ❌ 失败: {e}")
    import traceback

    traceback.print_exc()

# 6. 尝试reload（关键测试）
print(f"\n【步骤6】尝试调用 reload_symbol_list()...")
print("  ⚠️  这个调用可能会卡住！如果超过30秒没响应，请按Ctrl+C终止")

try:
    import time

    start = time.time()

    print("  → 调用 reload_symbol_list(force=True)...")
    result = data_center_service.reload_symbol_list(force=True)

    elapsed = time.time() - start
    print(f"  ✅ 成功！耗时: {elapsed:.2f}秒")
    print(f"  success: {result.get('success')}")
    print(f"  count: {result.get('symbol_count')}")

except KeyboardInterrupt:
    print(f"\n  ⚠️  用户中断（已等待 {time.time() - start:.2f}秒）")
    print("  说明：reload_symbol_list 确实卡住了")

except Exception as e:
    elapsed = time.time() - start
    print(f"  ❌ 失败（耗时{elapsed:.2f}秒）: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)

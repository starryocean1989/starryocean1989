# -*- coding: utf-8 -*-
"""快速启动功能测试脚本."""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print("=" * 70)
print("快速启动功能测试")
print("=" * 70)

# 测试1: 验证ServiceInitializer拆分
print("\n[测试1] 验证ServiceInitializer拆分...")
try:
    from backend.core.base import ServiceInitializer, get_service_manager

    # 检查方法存在
    assert hasattr(
        ServiceInitializer, "initialize_core_services"
    ), "缺少 initialize_core_services 方法"
    assert hasattr(
        ServiceInitializer, "initialize_optional_services"
    ), "缺少 initialize_optional_services 方法"
    assert hasattr(
        ServiceInitializer, "initialize_all_services"
    ), "缺少 initialize_all_services 方法（回退）"

    print("  ✅ ServiceInitializer 方法定义正确")

except Exception as e:
    print(f"  ❌ ServiceInitializer 测试失败: {e}")
    sys.exit(1)

# 测试2: 验证initialize_services接口
print("\n[测试2] 验证initialize_services接口...")
try:
    from backend.core.base import initialize_services

    # 检查函数签名
    import inspect

    sig = inspect.signature(initialize_services)
    params = list(sig.parameters.keys())

    assert "progress_callback" in params, "缺少 progress_callback 参数"
    assert "fast_startup" in params, "缺少 fast_startup 参数"

    # 检查默认值
    fast_startup_default = sig.parameters["fast_startup"].default
    assert (
        fast_startup_default == True
    ), f"fast_startup 默认值应为True，实际为 {fast_startup_default}"

    print("  ✅ initialize_services 接口正确")
    print(f"     - 参数: {params}")
    print(f"     - fast_startup 默认值: {fast_startup_default}")

except Exception as e:
    print(f"  ❌ initialize_services 测试失败: {e}")
    sys.exit(1)

# 测试3: 验证OptionalServicesLoader定义
print("\n[测试3] 验证OptionalServicesLoader...")
try:
    # 导入start_async_fixed并检查_start_optional_services_loader是否存在
    with open("start_async_fixed.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "_start_optional_services_loader" in content, "缺少 _start_optional_services_loader 函数"
    assert "OptionalServicesLoader" in content, "缺少 OptionalServicesLoader 类"
    assert "service_ready = Signal(str, bool)" in content, "缺少 service_ready 信号"

    print("  ✅ OptionalServicesLoader 定义正确")

except Exception as e:
    print(f"  ❌ OptionalServicesLoader 测试失败: {e}")
    sys.exit(1)

# 测试4: 验证UI动态启用接口
print("\n[测试4] 验证UI动态启用接口...")
try:
    with open("ui/main_window.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "def on_service_ready(" in content, "缺少 on_service_ready 方法"
    assert "service_name: str" in content, "on_service_ready 缺少 service_name 参数"
    assert "success: bool" in content, "on_service_ready 缺少 success 参数"

    print("  ✅ UI动态启用接口定义正确")

except Exception as e:
    print(f"  ❌ UI动态启用测试失败: {e}")
    sys.exit(1)

# 测试5: 模拟快速启动流程
print("\n[测试5] 模拟快速启动流程...")
try:
    # 设置环境
    import os

    os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

    # 导入必要模块
    from backend.core.base import initialize_services, get_service_manager

    print("  [5.1] 初始化配置...")
    from backend.core.config import init_settings

    init_settings()
    print("     ✅ 配置初始化完成")

    print("  [5.2] 测试核心服务初始化...")
    start_time = time.time()

    # 创建进度回调
    def progress_callback(msg, progress):
        print(f"     [{progress:3d}%] {msg}")

    # 执行快速启动
    result = initialize_services(progress_callback=progress_callback, fast_startup=True)

    elapsed = time.time() - start_time

    # 验证结果
    assert result.get("success") == True, "核心服务初始化失败"
    assert result.get("fast_startup") == True, "未使用快速启动模式"
    assert "initializer" in result, "缺少 initializer 实例"

    print(f"     ✅ 核心服务初始化成功（耗时: {elapsed:.2f}秒）")

    # 测试可选服务加载接口
    print("  [5.3] 测试可选服务加载接口...")
    initializer = result["initializer"]

    loaded_services = []

    def service_callback(name, success):
        status = "✅" if success else "❌"
        loaded_services.append((name, success))
        print(f"     {status} {name}")

    # 执行可选服务加载（这会加载实际的服务，可能需要一些时间）
    print("     开始加载可选服务...")
    optional_results = initializer.initialize_optional_services(service_callback)

    print(f"     ✅ 可选服务加载完成: {len(loaded_services)} 个服务")

except Exception as e:
    print(f"  ❌ 快速启动流程测试失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 测试总结
print("\n" + "=" * 70)
print("✅ 所有测试通过！快速启动功能已正确实现。")
print("=" * 70)
print("\n下一步：")
print("1. 运行完整应用测试启动速度")
print("2. 观察日志验证UI在3秒内显示")
print("3. 确认可选服务后台加载")
print("4. 验证服务就绪后UI功能启用")

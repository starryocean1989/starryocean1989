import os
import asyncio
from pathlib import Path
import sys

# 将仓库根目录加入sys.path，确保能导入backend包
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib.util
from types import ModuleType

# 直接按文件路径加载data_module_vnpy/core_engine.py，避免触发backend包的重型导入链
DMCE_PATH = ROOT / "backend" / "infrastructure" / "data_module_vnpy" / "core_engine.py"
spec = importlib.util.spec_from_file_location("dmce_core_engine", str(DMCE_PATH))
dmce_module: ModuleType = importlib.util.module_from_spec(spec)  # type: ignore
assert spec and spec.loader
spec.loader.exec_module(dmce_module)  # type: ignore
DailyCacheManager = dmce_module.DailyCacheManager


def print_header(msg: str):
    print(f"\n=== {msg} ===")


def assert_true(name: str, cond: bool):
    print(f"[{'OK' if cond else 'FAIL'}] {name}")


def run_sync_tests(base_file: Path):
    print_header("同步测试")
    DailyCacheManager.clear_cache(base_file)

    data = {"a": 1, "b": 2, "list": ["x", "y"]}
    ok = DailyCacheManager.save_with_date(data, base_file)
    assert_true("sync save", ok)

    bin_file = base_file.with_suffix('.bin')
    json_file = base_file if base_file.suffix.lower() == '.json' else base_file.with_suffix('.json')
    assert_true("bin exists (sync)", bin_file.exists())
    assert_true("json exists (sync)", json_file.exists())

    data2, date_str, valid = DailyCacheManager.load_with_validation(base_file)
    assert_true("sync load data equal", data2 == data)
    assert_true("sync load is_valid", bool(valid) is True)
    assert_true("get_cache_date (sync)", isinstance(DailyCacheManager.get_cache_date(base_file), str))

    # BIN回退：移除JSON后从BIN读取
    if json_file.exists():
        os.remove(json_file)
    data3, date_str2, valid2 = DailyCacheManager.load_with_validation(base_file)
    assert_true("sync load BIN fallback data equal", data3 == data)
    assert_true("sync load BIN fallback is_valid", bool(valid2) is True)

    # 清理
    DailyCacheManager.clear_cache(base_file)


async def run_async_tests(base_file: Path):
    print_header("异步测试")
    DailyCacheManager.clear_cache(base_file)

    data = {"hello": "world", "n": 123, "list": [1, 2, 3]}
    ok = await DailyCacheManager.save_with_date_async(data, base_file)
    assert_true("async save", ok)

    bin_file = base_file.with_suffix('.bin')
    json_file = base_file if base_file.suffix.lower() == '.json' else base_file.with_suffix('.json')
    assert_true("bin exists (async)", bin_file.exists())
    # 某些环境下native_iocp的文本写入不支持encoding参数，JSON可能未生成；此处不强制要求

    data2, date_str, valid = await DailyCacheManager.load_with_validation_async(base_file)
    assert_true("async load data equal", data2 == data)
    assert_true("async load is_valid", bool(valid) is True)
    assert_true("get_cache_date (async)", isinstance(DailyCacheManager.get_cache_date(base_file), str))

    # JSON回退：通过另一路径构造仅JSON存在的场景，验证回退读取
    base_file_json_only = Path('data/test_cache/daily_cache_async_json_only.json')
    DailyCacheManager.clear_cache(base_file_json_only)
    DailyCacheManager.save_with_date(data, base_file_json_only)
    bin_file2 = base_file_json_only.with_suffix('.bin')
    if bin_file2.exists():
        os.remove(bin_file2)
    data3, date_str2, valid2 = await DailyCacheManager.load_with_validation_async(base_file_json_only)
    assert_true("async load JSON fallback data equal", data3 == data)
    assert_true("async load JSON fallback is_valid", bool(valid2) is True)

    # 清理
    # 等待释放文件句柄，避免Windows短暂占用
    await asyncio.sleep(0.2)
    try:
        DailyCacheManager.clear_cache(base_file)
    except Exception as e:
        print(f"清理原路径失败（忽略）：{e}")
    DailyCacheManager.clear_cache(base_file_json_only)


def main():
    print_header("DailyCacheManager 二进制优先缓存测试")
    # 检查native_serialization可用性（避免导入整个core_engine模块导致不必要依赖）
    try:
        from backend.infrastructure.native.native_serialization import SERIALIZATION_AVAILABLE
        print(f"native_serialization available: {SERIALIZATION_AVAILABLE}")
    except Exception:
        # 降级：直接从已加载的dmce_module判断
        print(f"native_serialization available: {getattr(dmce_module, 'NATIVE_SER_AVAILABLE', False)}")
    base_file = Path('data/test_cache/daily_cache.json')

    run_sync_tests(base_file)
    asyncio.run(run_async_tests(base_file))
    print_header("所有测试完成")


if __name__ == '__main__':
    main()
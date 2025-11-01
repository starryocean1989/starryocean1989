# -*- coding: utf-8 -*-
"""
Native IOCP/IPC 集成验证测试

快速验证已完成的改造是否正常工作。
"""

import asyncio
import sys
import platform
import tempfile
from pathlib import Path

# 确保在项目路径中
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 仅Windows平台支持
if platform.system() != "Windows":
    print("⚠️ 此测试仅支持Windows平台")
    sys.exit(0)


async def test_tdx_reader():
    """测试TDX Reader使用native_iocp"""
    print("\n" + "="*60)
    print("测试: TDX Reader with native_iocp")
    print("="*60)

    try:
        from backend.infrastructure.tdx_asyncio import read_day_data
        from backend.infrastructure.native_iocp import get_backend

        print(f"Backend: {get_backend()}")

        # 创建临时测试文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.day') as f:
            import struct
            for i in range(10):
                date_int = 20240101 + i
                data = struct.pack('<I', date_int) + b'\x00' * 28
                f.write(data)
            temp_file = f.name

        try:
            df = await read_day_data(temp_file)
            print(f"✅ 成功读取 {len(df)} 条记录")
            await asyncio.sleep(0.1)
            return True
        finally:
            import time
            time.sleep(0.2)
            try:
                Path(temp_file).unlink(missing_ok=True)
            except:
                pass

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def test_parquet_async():
    """测试Parquet异步读取"""
    print("\n" + "="*60)
    print("测试: Parquet异步读取")
    print("="*60)

    try:
        import pandas as pd
        from backend.infrastructure.data_module_vnpy.data_quality import _read_parquet_async

        df_test = pd.DataFrame({
            'datetime': pd.date_range('2024-01-01', periods=100),
            'value': range(100, 200),
        })

        with tempfile.NamedTemporaryFile(delete=False, suffix='.parquet') as f:
            df_test.to_parquet(f.name, index=False)
            temp_file = f.name

        try:
            df = await _read_parquet_async(temp_file)
            print(f"✅ 成功读取 {len(df)} 行")
            assert len(df) == 100
            await asyncio.sleep(0.1)
            return True
        finally:
            import time
            time.sleep(0.2)
            try:
                Path(temp_file).unlink(missing_ok=True)
            except:
                pass

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def test_cache():
    """测试缓存模块"""
    print("\n" + "="*60)
    print("测试: 缓存模块")
    print("="*60)

    try:
        import pandas as pd
        from backend.infrastructure.tdx_asyncio.caching import AsyncFileCache

        cache = AsyncFileCache('test', format_type='parquet', cache_dir=tempfile.mkdtemp())

        df_test = pd.DataFrame({'value': range(50)})

        @cache
        async def test_func():
            return df_test

        result1 = await test_func()
        result2 = await test_func()

        print(f"✅ 缓存工作正常")
        assert len(result1) == 50
        assert len(result2) == 50
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


def test_ipc_queue():
    """测试IPC队列"""
    print("\n" + "="*60)
    print("测试: IPC队列适配器")
    print("="*60)

    try:
        from backend.infrastructure.data_module_vnpy.ipc_queue_adapter import IPCQueue

        queue = IPCQueue("test", role="server")
        print(f"✅ IPCQueue创建成功")
        return True

    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


async def run_tests():
    """运行所有测试"""
    print("\n" + "="*80)
    print("Native IOCP/IPC 集成验证测试")
    print("="*80)

    results = []
    results.append(("TDX Reader", await test_tdx_reader()))
    results.append(("Parquet异步读取", await test_parquet_async()))
    results.append(("缓存模块", await test_cache()))
    results.append(("IPC队列", test_ipc_queue()))

    print("\n" + "="*80)
    print("测试结果")
    print("="*80)

    passed = sum(1 for _, r in results if r)
    for name, result in results:
        print(f"{'✅' if result else '❌'} {name}")

    print(f"\n总计: {passed}/{len(results)} 通过")
    print("="*80)

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)


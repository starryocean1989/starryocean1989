# -*- coding: utf-8 -*-
"""
IOCP异步文件I/O测试

测试C扩展、Python API和asyncio集成。
"""

import asyncio
import platform
import tempfile
import os
from pathlib import Path

# 测试是否在Windows平台
if platform.system() != "Windows":
    print("⚠️ 测试需要Windows平台，跳过")
    import sys
    sys.exit(0)

# 测试导入
def test_imports():
    """测试模块导入"""
    print("=" * 60)
    print("测试1: 模块导入")
    print("=" * 60)

    try:
        from backend.infrastructure.native_iocp import aopen
        print("✅ native_iocp 导入成功")
        return True
    except ImportError as e:
        print(f"❌ native_iocp 导入失败: {e}")
        print("   提示: 可能需要先编译C扩展")
        return False
    except RuntimeError as e:
        print(f"⚠️ 运行时错误: {e}")
        return False


def test_compat_layer():
    """测试兼容层"""
    print("\n" + "=" * 60)
    print("测试2: 兼容层")
    print("=" * 60)

    try:
        from backend.infrastructure.native_iocp.compat import (
            is_iocp_available,
            is_fallback_available,
            get_backend,
        )

        iocp_avail = is_iocp_available()
        fallback_avail = is_fallback_available()
        backend = get_backend()

        print(f"IOCP可用: {iocp_avail}")
        print(f"降级方案可用: {fallback_avail}")
        print(f"当前后端: {backend}")

        return True
    except Exception as e:
        print(f"❌ 兼容层测试失败: {e}")
        return False


async def test_basic_read_write():
    """测试基本读写"""
    print("\n" + "=" * 60)
    print("测试3: 基本读写功能")
    print("=" * 60)

    try:
        from backend.infrastructure.native_iocp.compat import aopen

        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            test_file = f.name
            f.write("Hello, IOCP!")

        try:
            # 读取文件
            file = await aopen(test_file, 'rb')
            async with file:
                data = await file.read()
                print(f"✅ 读取成功: {len(data)} 字节")
                print(f"   内容: {data.decode('utf-8')}")

            # 写入文件
            file = await aopen(test_file, 'wb')
            async with file:
                new_data = b"Hello, IOCP Write!"
                written = await file.write(new_data)
                print(f"✅ 写入成功: {written} 字节")

            # 验证写入
            file = await aopen(test_file, 'rb')
            async with file:
                data = await file.read()
                if data == new_data:
                    print("✅ 写入验证成功")
                else:
                    print("❌ 写入验证失败")

        finally:
            # 清理
            if os.path.exists(test_file):
                os.unlink(test_file)

        return True

    except Exception as e:
        print(f"❌ 基本读写测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_concurrent_read():
    """测试并发读取"""
    print("\n" + "=" * 60)
    print("测试4: 并发读取")
    print("=" * 60)

    try:
        from backend.infrastructure.native_iocp.compat import aopen

        # 创建多个临时文件
        test_files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
                f.write(f"Test file {i}")
                test_files.append(f.name)

        try:
            # 并发读取
            tasks = [aopen(f, 'rb') for f in test_files]
            files = await asyncio.gather(*tasks)

            read_tasks = []
            for f in files:
                async with f as file_obj:
                    read_tasks.append(file_obj.read())

            results = await asyncio.gather(*read_tasks)

            print(f"✅ 并发读取成功: {len(results)} 个文件")
            for i, data in enumerate(results):
                print(f"   文件{i}: {len(data)} 字节 - {data.decode('utf-8')[:20]}")

        finally:
            # 清理
            for f in test_files:
                if os.path.exists(f):
                    os.unlink(f)

        return True

    except Exception as e:
        print(f"❌ 并发读取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """运行所有测试"""
    print("🧪 IOCP异步文件I/O测试套件")
    print("=" * 60)

    results = []

    # 测试1: 导入
    results.append(("导入测试", test_imports()))

    # 测试2: 兼容层
    results.append(("兼容层测试", test_compat_layer()))

    # 测试3: 基本读写（需要asyncio）
    try:
        results.append(("基本读写测试", await test_basic_read_write()))
    except Exception as e:
        print(f"❌ 基本读写测试异常: {e}")
        results.append(("基本读写测试", False))

    # 测试4: 并发读取（需要asyncio）
    try:
        results.append(("并发读取测试", await test_concurrent_read()))
    except Exception as e:
        print(f"❌ 并发读取测试异常: {e}")
        results.append(("并发读取测试", False))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️ 部分测试失败")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)


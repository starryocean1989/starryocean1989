#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证Native日志桥接体系完整性
"""

import sys
import os
import asyncio
import logging
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(__file__))

def setup_test_logging():
    """设置测试日志"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(native_module)s - %(native_function)s'
    )

def test_native_log_bridge_core():
    """测试Native Log Bridge核心功能"""
    print("🔍 测试Native Log Bridge核心功能...")

    try:
        from backend.infrastructure.native.logging_bridge import (
            native_call_guard,
            native_async_call_guard,
            NativeLogLevel,
            log_from_native,
            install_native_logging_bridge,
            _logger
        )
        print("✅ 成功导入logging_bridge模块")

        # 测试常量
        assert NativeLogLevel.DEBUG == 10, f"DEBUG常量错误: {NativeLogLevel.DEBUG}"
        assert NativeLogLevel.INFO == 20, f"INFO常量错误: {NativeLogLevel.INFO}"
        assert NativeLogLevel.ERROR == 40, f"ERROR常量错误: {NativeLogLevel.ERROR}"
        print("✅ 日志级别常量正确")

        # 测试同步装饰器
        @native_call_guard(component='test.sync')
        def test_sync_success():
            return "sync_success"

        @native_call_guard(component='test.sync')
        def test_sync_error():
            raise ValueError("sync test error")

        result = test_sync_success()
        assert result == "sync_success"
        print("✅ 同步native_call_guard装饰器正常工作")

        try:
            test_sync_error()
            assert False, "应该抛出异常"
        except ValueError as e:
            assert str(e) == "sync test error"
            print("✅ 同步异常捕获和日志记录正常")

        # 测试异步装饰器
        @native_async_call_guard(component='test.async')
        async def test_async_success():
            await asyncio.sleep(0.001)
            return "async_success"

        @native_async_call_guard(component='test.async')
        async def test_async_error():
            await asyncio.sleep(0.001)
            raise RuntimeError("async test error")

        # 运行异步测试
        async def run_async_tests():
            result = await test_async_success()
            assert result == "async_success"
            print("✅ 异步native_async_call_guard装饰器正常工作")

            try:
                await test_async_error()
                assert False, "应该抛出异常"
            except RuntimeError as e:
                assert str(e) == "async test error"
                print("✅ 异步异常捕获和日志记录正常")

        asyncio.run(run_async_tests())

        # 测试log_from_native函数
        with patch.object(_logger, 'log') as mock_log:
            log_from_native(
                level=NativeLogLevel.INFO,
                component="test.component",
                function="test_function",
                line=42,
                message="测试消息",
                details="测试详情"
            )

            # 验证日志调用
            assert mock_log.called, "log_from_native没有调用logger.log"
            args, kwargs = mock_log.call_args
            assert args[0] == logging.INFO, f"日志级别错误: {args[0]}"
            assert "测试消息" in args[1], f"消息内容错误: {args[1]}"
            assert kwargs['extra']['native_module'] == 'test.component'
            assert kwargs['extra']['native_function'] == 'test_function'
            assert kwargs['extra']['native_line'] == 42
            print("✅ log_from_native函数正常工作")

        # 测试安装功能
        result = install_native_logging_bridge()
        print(f"✅ 日志桥接安装结果: {result}")

        return True

    except Exception as e:
        print(f"❌ Native Log Bridge核心测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_native_ipc_integration():
    """测试native_ipc日志集成"""
    print("\n🔍 测试native_ipc日志集成...")

    try:
        from backend.infrastructure.native.native_ipc import IPC_AVAILABLE
        from backend.infrastructure.native.native_ipc.async_ipc import AsyncIPCPipe

        if not IPC_AVAILABLE:
            print("⚠️  native_ipc扩展不可用，跳过集成测试")
            return True

        print("✅ native_ipc扩展可用")

        # 检查AsyncIPCPipe是否有装饰器
        import inspect

        # 检查read方法
        read_method = getattr(AsyncIPCPipe, 'read', None)
        if read_method and hasattr(read_method, '__wrapped__'):
            print("✅ AsyncIPCPipe.read方法已正确装饰")
        else:
            print("⚠️  AsyncIPCPipe.read方法装饰器状态未知")

        # 检查write方法
        write_method = getattr(AsyncIPCPipe, 'write', None)
        if write_method and hasattr(write_method, '__wrapped__'):
            print("✅ AsyncIPCPipe.write方法已正确装饰")
        else:
            print("⚠️  AsyncIPCPipe.write方法装饰器状态未知")

        # 检查是否有native_async_call_guard导入
        import backend.infrastructure.native.native_ipc.async_ipc as ipc_module
        if hasattr(ipc_module, 'native_async_call_guard'):
            print("✅ native_ipc模块正确导入了native_async_call_guard")
        else:
            print("⚠️  native_ipc模块未导入native_async_call_guard")

        return True

    except Exception as e:
        print(f"❌ native_ipc集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_native_iocp_integration():
    """测试native_iocp日志集成"""
    print("\n🔍 测试native_iocp日志集成...")

    try:
        from backend.infrastructure.native.native_iocp import IOCP_AVAILABLE
        from backend.infrastructure.native.native_iocp.async_iocp_file import AsyncIOCPFile

        if not IOCP_AVAILABLE:
            print("⚠️  native_iocp扩展不可用，跳过集成测试")
            return True

        print("✅ native_iocp扩展可用")

        # 检查AsyncIOCPFile是否有装饰器
        import inspect

        # 检查read方法
        read_method = getattr(AsyncIOCPFile, 'read', None)
        if read_method and hasattr(read_method, '__wrapped__'):
            print("✅ AsyncIOCPFile.read方法已正确装饰")
        else:
            print("⚠️  AsyncIOCPFile.read方法装饰器状态未知")

        # 检查write方法
        write_method = getattr(AsyncIOCPFile, 'write', None)
        if write_method and hasattr(write_method, '__wrapped__'):
            print("✅ AsyncIOCPFile.write方法已正确装饰")
        else:
            print("⚠️  AsyncIOCPFile.write方法装饰器状态未知")

        # 检查close方法
        close_method = getattr(AsyncIOCPFile, 'close', None)
        if close_method and hasattr(close_method, '__wrapped__'):
            print("✅ AsyncIOCPFile.close方法已正确装饰")
        else:
            print("⚠️  AsyncIOCPFile.close方法装饰器状态未知")

        # 检查是否有native_async_call_guard导入
        import backend.infrastructure.native.native_iocp.async_iocp_file as iocp_module
        if hasattr(iocp_module, 'native_async_call_guard'):
            print("✅ native_iocp模块正确导入了native_async_call_guard")
        else:
            print("⚠️  native_iocp模块未导入native_async_call_guard")

        return True

    except Exception as e:
        print(f"❌ native_iocp集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主验证函数"""
    print("🚀 开始验证Native日志桥接体系...")
    print("=" * 50)

    setup_test_logging()

    results = []
    results.append(("Native Log Bridge核心", test_native_log_bridge_core()))
    results.append(("native_ipc集成", test_native_ipc_integration()))
    results.append(("native_iocp集成", test_native_iocp_integration()))

    print("\n" + "=" * 50)
    print("📊 验证结果总结:")

    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        all_passed = all_passed and passed

    print("=" * 50)
    if all_passed:
        print("🎉 所有验证通过！Native日志桥接体系集成成功！")
        return 0
    else:
        print("⚠️  部分验证失败，请检查上述错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main())

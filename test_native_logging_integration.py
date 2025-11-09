#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试native日志桥接集成
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_native_log_bridge():
    """测试native日志桥接功能"""
    print("Testing Native Log Bridge Integration...")

    try:
        from backend.infrastructure.native.logging_bridge import (
            native_call_guard,
            NativeLogLevel,
            log_from_native,
            install_native_logging_bridge
        )
        print("✓ Successfully imported logging_bridge module")

        # 安装日志桥接
        install_native_logging_bridge()
        print("✓ Successfully installed native logging bridge")

        # 测试常量
        assert NativeLogLevel.DEBUG == 10
        assert NativeLogLevel.INFO == 20
        assert NativeLogLevel.ERROR == 40
        print("✓ Log level constants are correct")

        # 测试装饰器 - 成功情况
        @native_call_guard(component='test.native')
        def test_success():
            return "success"

        result = test_success()
        assert result == "success"
        print("✓ native_call_guard decorator works for success case")

        # 测试装饰器 - 异常情况
        @native_call_guard(component='test.native')
        def test_failure():
            raise ValueError("test error")

        try:
            test_failure()
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert str(e) == "test error"
            print("✓ native_call_guard decorator works for error case")

        # 测试log_from_native函数
        log_from_native(
            level=NativeLogLevel.INFO,
            component="test.native",
            function="test_function",
            line=42,
            message="Test log message",
            details="Test details"
        )
        print("✓ log_from_native function works")

        # 测试native_ipc导入
        try:
            from backend.infrastructure.native.native_ipc import IPC_AVAILABLE
            if IPC_AVAILABLE:
                print("✓ native_ipc extension is available")
                # 测试导入async_ipc
                from backend.infrastructure.native.native_ipc.async_ipc import AsyncIPCPipe
                print("✓ AsyncIPCPipe import successful")
            else:
                print("⚠ native_ipc extension not compiled")
        except ImportError as e:
            print(f"⚠ native_ipc import failed: {e}")

        # 测试native_iocp导入
        try:
            from backend.infrastructure.native.native_iocp import IOCP_AVAILABLE
            if IOCP_AVAILABLE:
                print("✓ native_iocp extension is available")
                # 测试导入AsyncIOCPFile
                from backend.infrastructure.native.native_iocp.async_iocp_file import AsyncIOCPFile
                print("✓ AsyncIOCPFile import successful")
            else:
                print("⚠ native_iocp extension not compiled")
        except ImportError as e:
            print(f"⚠ native_iocp import failed: {e}")

        print("\n🎉 All native logging bridge tests passed!")
        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_native_log_bridge()
    sys.exit(0 if success else 1)

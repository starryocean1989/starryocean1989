# -*- coding: utf-8 -*-
"""
测试native_ipc的日志桥接功能
"""

import pytest
import logging
from unittest.mock import patch, MagicMock

from backend.infrastructure.native.native_ipc import IPC_AVAILABLE
from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    install_native_logging_bridge,
    native_call_guard,
)


@pytest.mark.skipif(not IPC_AVAILABLE, reason="IPC extension not available")
class TestNativeIPCLogging:
    """测试native_ipc的日志桥接功能"""

    def setup_method(self):
        """测试前准备"""
        # 安装日志桥接
        install_native_logging_bridge()

    def test_native_call_guard_decorator(self):
        """测试native_call_guard装饰器"""

        @native_call_guard(component="test.ipc")
        def test_function_success():
            return "success"

        @native_call_guard(component="test.ipc")
        def test_function_error():
            raise ValueError("test error")

        # 测试成功情况
        with patch('backend.infrastructure.native.logging_bridge._logger') as mock_logger:
            result = test_function_success()
            assert result == "success"
            # 不应该记录错误日志
            mock_logger.log.assert_not_called()

        # 测试异常情况
        with patch('backend.infrastructure.native.logging_bridge._logger') as mock_logger:
            with pytest.raises(ValueError, match="test error"):
                test_function_error()
            # 应该记录错误日志
            mock_logger.log.assert_called_once()
            args = mock_logger.log.call_args
            assert args[0][0] == logging.ERROR  # 级别
            assert "test_function_error raised" in args[0][1]  # 消息
            assert args[1]['extra']['native_module'] == 'test.ipc'

    def test_async_native_call_guard_decorator(self):
        """测试异步native_call_guard装饰器"""
        import asyncio

        @native_call_guard(component="test.ipc")
        async def async_test_function_success():
            await asyncio.sleep(0.001)
            return "async success"

        @native_call_guard(component="test.ipc")
        async def async_test_function_error():
            await asyncio.sleep(0.001)
            raise RuntimeError("async test error")

        # 测试异步成功情况
        async def test_async_success():
            with patch('backend.infrastructure.native.logging_bridge._logger') as mock_logger:
                result = await async_test_function_success()
                assert result == "async success"
                mock_logger.log.assert_not_called()

        # 测试异步异常情况
        async def test_async_error():
            with patch('backend.infrastructure.native.logging_bridge._logger') as mock_logger:
                with pytest.raises(RuntimeError, match="async test error"):
                    await async_test_function_error()
                mock_logger.log.assert_called_once()
                args = mock_logger.log.call_args
                assert args[0][0] == logging.ERROR
                assert "async_test_function_error raised" in args[0][1]

        # 运行异步测试
        asyncio.run(test_async_success())
        asyncio.run(test_async_error())

    def test_native_log_bridge_constants(self):
        """测试日志桥接常量"""
        assert NativeLogLevel.DEBUG == 10
        assert NativeLogLevel.INFO == 20
        assert NativeLogLevel.WARNING == 30
        assert NativeLogLevel.ERROR == 40
        assert NativeLogLevel.CRITICAL == 50

    @patch('backend.infrastructure.native.logging_bridge._logger')
    def test_log_from_native_function(self, mock_logger):
        """测试log_from_native函数"""
        from backend.infrastructure.native.logging_bridge import log_from_native

        # 测试不同级别的日志
        log_from_native(
            level=NativeLogLevel.INFO,
            component="test.component",
            function="test_function",
            line=42,
            message="Test message",
            details="Test details"
        )

        mock_logger.log.assert_called_once()
        args = mock_logger.log.call_args
        assert args[0][0] == logging.INFO
        assert args[0][1] == "Test message"
        assert args[1]['extra']['native_module'] == 'test.component'
        assert args[1]['extra']['native_function'] == 'test_function'
        assert args[1]['extra']['native_line'] == 42
        assert args[1]['extra']['native_details'] == 'Test details'

    def test_install_native_logging_bridge(self):
        """测试日志桥接安装"""
        from backend.infrastructure.native.logging_bridge import install_native_logging_bridge

        # 创建模拟logger
        mock_logger = MagicMock()
        mock_alert_logger = MagicMock()

        # 安装自定义日志桥接
        install_native_logging_bridge(
            logger=mock_logger,
            alert_logger=mock_alert_logger,
            level_map={10: logging.DEBUG, 40: logging.CRITICAL}
        )

        # 验证安装成功
        # 这里主要验证没有抛出异常
        assert True


if __name__ == "__main__":
    pytest.main([__file__])

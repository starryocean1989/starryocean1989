# -*- coding: utf-8 -*-
"""
测试阶段5：native_rpc_bridge & native_serialization 日志埋点全面改造

验证日志桥接和异常捕获链路是否正常工作。
"""

import pytest
import logging
from unittest.mock import patch, MagicMock

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    install_native_logging_bridge,
    log_from_native,
)


class TestStage5LoggingIntegration:
    """测试阶段5日志集成"""

    def setup_method(self):
        """测试前设置"""
        self.logger = logging.getLogger("test.native.stage5")
        self.logger.setLevel(logging.DEBUG)

        # 创建内存处理器来捕获日志
        self.log_handler = logging.Handler()
        self.log_handler.setLevel(logging.DEBUG)
        self.captured_logs = []

        def capture_log(record):
            self.captured_logs.append({
                'level': record.levelno,
                'message': record.getMessage(),
                'component': getattr(record, 'native_module', None),
                'scenario': getattr(record, 'scenario', None),
            })

        self.log_handler.emit = capture_log
        self.logger.addHandler(self.log_handler)

        # 安装日志桥接
        install_native_logging_bridge(logger=self.logger)

    def teardown_method(self):
        """测试后清理"""
        self.logger.removeHandler(self.log_handler)

    def test_native_log_bridge_basic(self):
        """测试基础日志桥接功能"""
        # 清空日志
        self.captured_logs.clear()

        # 调用native日志
        log_from_native(
            NativeLogLevel.INFO,
            "test.component",
            "test_function",
            42,
            "Test message",
            "extra details"
        )

        # 验证日志被捕获
        assert len(self.captured_logs) == 1
        log_entry = self.captured_logs[0]
        assert log_entry['level'] == logging.INFO
        assert log_entry['message'] == "Test message"
        assert log_entry['component'] == "test.component"
        assert log_entry['scenario'] == "test.component"

    @pytest.mark.parametrize("level,expected_std_level", [
        (NativeLogLevel.DEBUG, logging.DEBUG),
        (NativeLogLevel.INFO, logging.INFO),
        (NativeLogLevel.WARNING, logging.WARNING),
        (NativeLogLevel.ERROR, logging.ERROR),
        (NativeLogLevel.CRITICAL, logging.CRITICAL),
    ])
    def test_native_log_level_mapping(self, level, expected_std_level):
        """测试日志等级映射"""
        self.captured_logs.clear()

        log_from_native(level, "test", "func", 1, "level test")

        assert len(self.captured_logs) == 1
        assert self.captured_logs[0]['level'] == expected_std_level


class TestNativeRpcBridgeLogging:
    """测试native_rpc_bridge日志功能"""

    def setup_method(self):
        self.logger = logging.getLogger("test.rpc.bridge")
        self.logger.setLevel(logging.DEBUG)

        self.log_handler = logging.Handler()
        self.captured_logs = []

        def capture_log(record):
            self.captured_logs.append({
                'level': record.levelno,
                'message': record.getMessage(),
                'component': getattr(record, 'native_module', None),
                'function': getattr(record, 'native_function', None),
                'line': getattr(record, 'native_line', 0),
            })

        self.log_handler.emit = capture_log
        self.logger.addHandler(self.log_handler)

    @patch('backend.infrastructure.native.native_rpc_bridge.native_rpc_bridge.create_request_header')
    def test_rpc_bridge_header_creation_logging(self, mock_native_func):
        """测试RPC桥接头创建的日志"""
        from backend.infrastructure.native.native_rpc_bridge import create_request_header

        # 模拟native函数返回
        mock_native_func.return_value = {
            "method_id": 1,
            "payload_size": 1024,
            "request_id": 123,
            "flags": 1,
        }

        # 调用包装函数
        result = create_request_header(1, 1024)

        # 验证结果
        assert result["method_id"] == 1
        assert result["payload_size"] == 1024

        # 验证native函数被调用
        mock_native_func.assert_called_once_with(1, 1024)

    def test_rpc_bridge_fallback_logging(self):
        """测试RPC桥接降级模式的日志"""
        # 模拟模块导入失败的情况
        with patch.dict('sys.modules', {
            'backend.infrastructure.native.native_rpc_bridge.native_rpc_bridge': None
        }):
            # 重新导入以触发降级路径
            import importlib
            import backend.infrastructure.native.native_rpc_bridge
            importlib.reload(backend.infrastructure.native.native_rpc_bridge)

            from backend.infrastructure.native.native_rpc_bridge import create_request_header

            # 调用降级函数
            result = create_request_header(5, 2048)

            # 验证降级实现
            assert result["method_id"] == 5
            assert result["payload_size"] == 2048
            assert result["request_id"] == 0
            assert result["flags"] == 0


class TestNativeSerializationLogging:
    """测试native_serialization日志功能"""

    def setup_method(self):
        self.logger = logging.getLogger("test.serialization")
        self.logger.setLevel(logging.DEBUG)

        self.log_handler = logging.Handler()
        self.captured_logs = []

        def capture_log(record):
            self.captured_logs.append({
                'level': record.levelno,
                'message': record.getMessage(),
                'component': getattr(record, 'native_module', None),
            })

        self.log_handler.emit = capture_log
        self.logger.addHandler(self.log_handler)

    @patch('backend.infrastructure.native.native_serialization.native_serialization.batch_serialize')
    def test_serialization_batch_logging(self, mock_native_func):
        """测试序列化批量操作的日志"""
        from backend.infrastructure.native.native_serialization import batch_serialize

        # 模拟native函数返回
        mock_native_func.return_value = [b'data1', b'data2']

        # 调用包装函数
        result = batch_serialize([1, 2, {"key": "value"}])

        # 验证结果
        assert len(result) == 2

        # 验证native函数被调用
        mock_native_func.assert_called_once()

    def test_serialization_fallback_logging(self):
        """测试序列化降级模式的日志"""
        # 模拟模块导入失败的情况
        with patch.dict('sys.modules', {
            'backend.infrastructure.native.native_serialization.native_serialization': None
        }):
            # 重新导入以触发降级路径
            import importlib
            import backend.infrastructure.native.native_serialization
            importlib.reload(backend.infrastructure.native.native_serialization)

            from backend.infrastructure.native.native_serialization import batch_serialize

            # 调用降级函数应抛出异常
            with pytest.raises(ImportError, match="Serialization C extension not compiled"):
                batch_serialize([1, 2, 3])


class TestExceptionLogging:
    """测试异常日志记录"""

    def setup_method(self):
        self.logger = logging.getLogger("test.exceptions")
        self.logger.setLevel(logging.DEBUG)

        self.log_handler = logging.Handler()
        self.captured_logs = []

        def capture_log(record):
            self.captured_logs.append({
                'level': record.levelno,
                'message': record.getMessage(),
                'component': getattr(record, 'native_module', None),
                'has_exception': hasattr(record, 'exc_text') and record.exc_text is not None,
            })

        self.log_handler.emit = capture_log
        self.logger.addHandler(self.log_handler)

        install_native_logging_bridge(logger=self.logger)

    def test_call_guard_captures_exceptions(self):
        """测试调用守卫器捕获异常"""
        from backend.infrastructure.native.logging_bridge import native_call_guard

        @native_call_guard(component="test.guard")
        def failing_function():
            raise ValueError("Test exception")

        # 调用会失败但不抛出异常（被守卫器捕获）
        failing_function()

        # 验证异常被记录
        assert len(self.captured_logs) > 0
        error_logs = [log for log in self.captured_logs if log['level'] >= logging.ERROR]
        assert len(error_logs) > 0

        # 验证错误日志包含异常信息
        error_log = error_logs[0]
        assert "ValueError" in error_log['message']
        assert "Test exception" in error_log['message']


if __name__ == "__main__":
    pytest.main([__file__])

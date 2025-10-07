# -*- coding: utf-8 -*-
"""
信号记录器.

记录和验证Qt信号发射。
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SignalRecorder:
    """记录UI信号发射，用于验证事件触发."""

    def __init__(self):
        """初始化信号记录器."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._recorded_signals: Dict[str, List[Dict[str, Any]]] = {}
        self._connected_signals: Dict[str, Any] = {}

    def connect_signal(self, signal: Any, signal_name: str):
        """
        连接信号进行记录.

        Args:
            signal: Qt信号
            signal_name: 信号名称
        """

        def slot(*args, **kwargs):
            self._record_signal_emission(signal_name, args, kwargs)

        signal.connect(slot)
        self._connected_signals[signal_name] = signal
        self.logger.info("已连接信号: %s", signal_name)

    def _record_signal_emission(self, signal_name: str, args: tuple, kwargs: dict):
        """
        记录信号发射.

        Args:
            signal_name: 信号名称
            args: 位置参数
            kwargs: 关键字参数
        """
        if signal_name not in self._recorded_signals:
            self._recorded_signals[signal_name] = []

        self._recorded_signals[signal_name].append(
            {
                "args": args,
                "kwargs": kwargs,
                "count": len(self._recorded_signals[signal_name]) + 1,
            }
        )

        self.logger.info("信号发射: %s, 参数: %s, %s", signal_name, args, kwargs)

    def record_signal(self, signal_name: str, *args, **kwargs):
        """
        手动记录信号.

        Args:
            signal_name: 信号名称
            *args: 位置参数
            **kwargs: 关键字参数
        """
        self._record_signal_emission(signal_name, args, kwargs)

    def verify_signal_emitted(
        self, signal_name: str, times: Optional[int] = None
    ) -> bool:
        """
        验证信号是否发射.

        Args:
            signal_name: 信号名称
            times: 期望发射次数（None表示至少一次）

        Returns:
            bool: 是否符合预期
        """
        if signal_name not in self._recorded_signals:
            self.logger.warning("信号未发射: %s", signal_name)
            return False

        emitted_times = len(self._recorded_signals[signal_name])

        if times is None:
            # 至少发射一次
            result = emitted_times > 0
        else:
            # 精确匹配次数
            result = emitted_times == times

        if result:
            self.logger.info(
                "信号验证成功: %s, 发射次数: %s", signal_name, emitted_times
            )
        else:
            self.logger.warning(
                "信号验证失败: %s, 期望: %s, 实际: %s",
                signal_name,
                times,
                emitted_times,
            )

        return result

    def get_signal_args(self, signal_name: str, index: int = 0) -> Optional[Dict]:
        """
        获取信号参数.

        Args:
            signal_name: 信号名称
            index: 发射索引（默认第一次）

        Returns:
            dict: 信号参数字典，包含 args 和 kwargs
        """
        if signal_name not in self._recorded_signals:
            self.logger.warning("信号未记录: %s", signal_name)
            return None

        emissions = self._recorded_signals[signal_name]
        if index >= len(emissions):
            self.logger.warning("信号索引超出范围: %s[%s]", signal_name, index)
            return None

        return emissions[index]

    def get_signal_count(self, signal_name: str) -> int:
        """
        获取信号发射次数.

        Args:
            signal_name: 信号名称

        Returns:
            int: 发射次数
        """
        if signal_name not in self._recorded_signals:
            return 0
        return len(self._recorded_signals[signal_name])

    def clear_signals(self):
        """清除所有记录的信号."""
        self._recorded_signals.clear()
        self.logger.info("已清除所有信号记录")

    def clear_signal(self, signal_name: str):
        """
        清除特定信号的记录.

        Args:
            signal_name: 信号名称
        """
        if signal_name in self._recorded_signals:
            del self._recorded_signals[signal_name]
            self.logger.info("已清除信号记录: %s", signal_name)

    @contextmanager
    def capture(self):
        """
        上下文管理器：捕获信号.

        使用示例:
            with signal_recorder.capture():
                # 执行操作
                button.click()
            # 验证信号
            assert signal_recorder.verify_signal_emitted("clicked")
        """
        self.clear_signals()
        yield self

    def get_all_signals(self) -> Dict[str, int]:
        """
        获取所有信号及其发射次数.

        Returns:
            dict: 信号名称到发射次数的映射
        """
        return {
            name: len(emissions) for name, emissions in self._recorded_signals.items()
        }

    def print_summary(self):
        """打印信号记录摘要."""
        self.logger.info("=" * 60)
        self.logger.info("信号记录摘要")
        self.logger.info("=" * 60)

        if not self._recorded_signals:
            self.logger.info("  无信号记录")
        else:
            for signal_name, emissions in self._recorded_signals.items():
                self.logger.info("  %s: %s次", signal_name, len(emissions))
                for i, emission in enumerate(emissions):
                    args_str = emission["args"]
                    kwargs_str = emission["kwargs"]
                    self.logger.info(
                        "    [%s] args=%s, kwargs=%s",
                        i,
                        args_str,
                        kwargs_str,
                    )

        self.logger.info("=" * 60)

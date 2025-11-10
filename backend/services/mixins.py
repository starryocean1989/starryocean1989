# -*- coding: utf-8 -*-
"""
服务层混入类

提供通用的功能混入类，用于服务组件。
"""

import logging


class LoggerMixin:
    """日志混入类.

    提供统一的日志器访问接口。
    """

    @property
    def logger(self):
        """获取日志器实例（延迟初始化）.

        Returns:
            logging.Logger: 日志器实例
        """
        if not hasattr(self, '_logger'):
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger

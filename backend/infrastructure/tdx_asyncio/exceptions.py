# -*- coding: utf-8 -*-
# cython: language_level=3
from typing import Optional


class TdxConnectionError(Exception):
    """
    当连接服务器出错的时候，会抛出的异常
    """

    pass


class TdxFunctionCallError(Exception):
    """
    当函数调用出错的时候
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.original_exception: Optional[Exception] = None


class ValidationException(Exception):
    ...


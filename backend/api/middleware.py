# -*- coding: utf-8 -*-
"""
中间件模块.

提供统一的请求处理中间件，包括日志、认证、CORS、异常处理等。
"""

import logging
import time
import traceback
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件."""

    def __init__(self, app: "ASGIApp"):
        """初始化日志中间件."""
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: "RequestResponseEndpoint"
    ) -> Response:
        """处理请求并记录日志."""
        # 记录请求开始时间
        start_time = time.time()

        # 记录请求信息
        client_host = request.client.host if request.client else "unknown"
        logger.info(
            "请求开始: %s %s from %s", request.method, request.url.path, client_host
        )

        # 处理请求
        try:
            response = await call_next(request)

            # 计算处理时间
            process_time = time.time() - start_time

            # 记录响应信息
            logger.info(
                "请求完成: %s %s 状态码: %s 耗时: %.4fs",
                request.method,
                request.url.path,
                response.status_code,
                process_time,
            )

            # 添加处理时间到响应头
            response.headers["X-Process-Time"] = str(process_time)

            return response

        except Exception as e:  # pylint: disable=W0718
            # 记录异常信息 - 捕获所有异常以确保请求日志完整性
            process_time = time.time() - start_time
            logger.error(
                "请求异常: %s %s 异常: %s 耗时: %.4fs",
                request.method,
                request.url.path,
                str(e),
                process_time,
            )
            logger.error("异常堆栈: %s", traceback.format_exc())

            # 返回错误响应
            return JSONResponse(
                status_code=500,
                content={"code": -1, "message": "服务器内部错误", "data": None},
            )


class ExceptionHandlingMiddleware(BaseHTTPMiddleware):
    """异常处理中间件."""

    def __init__(self, app: "ASGIApp"):
        """初始化异常处理中间件."""
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: "RequestResponseEndpoint"
    ) -> Response:
        """处理请求并捕获异常."""
        try:
            response = await call_next(request)
            return response

        except HTTPException as e:
            # 处理HTTP异常
            logger.warning("HTTP异常: %s - %s", e.status_code, e.detail)
            return JSONResponse(
                status_code=e.status_code,
                content={"code": e.status_code, "message": e.detail, "data": None},
            )

        except ValueError as e:
            # 处理值错误
            logger.error("值错误: %s", str(e))
            return JSONResponse(
                status_code=400,
                content={
                    "code": 400,
                    "message": f"请求参数错误: {str(e)}",
                    "data": None,
                },
            )

        except PermissionError as e:
            # 处理权限错误
            logger.error("权限错误: %s", str(e))
            return JSONResponse(
                status_code=403,
                content={"code": 403, "message": "权限不足", "data": None},
            )

        except Exception as e:  # pylint: disable=W0718
            # 处理其他未捕获的异常 - 作为最后的兜底，确保应用不会崩溃
            logger.error("未捕获异常: %s", str(e))
            logger.error("异常堆栈: %s", traceback.format_exc())
            return JSONResponse(
                status_code=500,
                content={"code": 500, "message": "服务器内部错误", "data": None},
            )


def setup_cors_middleware(app: "ASGIApp") -> None:
    """设置CORS中间件."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # React开发服务器
            "http://localhost:5173",  # Vite开发服务器
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def setup_middleware(app: "ASGIApp") -> None:
    """设置所有中间件."""
    # 添加异常处理中间件（最先添加，最后执行）
    app.add_middleware(ExceptionHandlingMiddleware)

    # 添加日志中间件
    app.add_middleware(LoggingMiddleware)

    # 添加CORS中间件
    setup_cors_middleware(app)

    logger.info("所有中间件已设置完成")


# 导出公共接口
__all__ = [
    "LoggingMiddleware",
    "ExceptionHandlingMiddleware",
    "setup_cors_middleware",
    "setup_middleware",
]

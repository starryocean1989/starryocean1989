# -*- coding: utf-8 -*-
"""
统一响应格式工具.

提供API响应的统一格式化和处理功能。
"""

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiResponse:
    """API响应格式化类."""

    @staticmethod
    def success(
        data: Any = None, message: str = "操作成功", code: int = 0, **kwargs
    ) -> Dict[str, Any]:
        """成功响应格式."""
        response = {
            "code": code,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "success": True,
        }

        # 添加额外的字段
        response.update(kwargs)

        return response

    @staticmethod
    def error(
        message: str = "操作失败",
        code: int = -1,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """错误响应格式."""
        response = {
            "code": code,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat(),
            "success": False,
        }

        if error_code:
            response["error_code"] = error_code

        if details:
            response["details"] = details

        # 添加额外的字段
        response.update(kwargs)

        return response

    @staticmethod
    def paginated(
        data: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
        message: str = "查询成功",
    ) -> Dict[str, Any]:
        """分页响应格式."""
        total_pages = (total + page_size - 1) // page_size

        return {
            "code": 0,
            "message": message,
            "data": {
                "items": data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            },
            "timestamp": datetime.now().isoformat(),
            "success": True,
        }

    @staticmethod
    def validation_error(
        errors: List[Dict[str, Any]], message: str = "数据验证失败"
    ) -> Dict[str, Any]:
        """验证错误响应格式."""
        return {
            "code": 400,
            "message": message,
            "data": None,
            "validation_errors": errors,
            "timestamp": datetime.now().isoformat(),
            "success": False,
        }

    @staticmethod
    def not_found(
        resource: str = "资源", message: Optional[str] = None
    ) -> Dict[str, Any]:
        """资源未找到响应格式."""
        if message is None:
            message = f"{resource}不存在"

        return {
            "code": 404,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat(),
            "success": False,
        }

    @staticmethod
    def forbidden(message: str = "权限不足") -> Dict[str, Any]:
        """权限不足响应格式."""
        return {
            "code": 403,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat(),
            "success": False,
        }

    @staticmethod
    def server_error(
        message: str = "服务器内部错误", error_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """服务器错误响应格式."""
        response = {
            "code": 500,
            "message": message,
            "data": None,
            "timestamp": datetime.now().isoformat(),
            "success": False,
        }

        if error_id:
            response["error_id"] = error_id

        return response


class ResponseHelper:
    """响应辅助工具."""

    @staticmethod
    def create_json_response(
        response_data: Dict[str, Any],
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
    ) -> JSONResponse:
        """创建JSON响应."""
        if headers is None:
            headers = {}

        return JSONResponse(
            content=response_data, status_code=status_code, headers=headers
        )

    @staticmethod
    def success_response(
        data: Any = None, message: str = "操作成功", status_code: int = 200, **kwargs
    ) -> JSONResponse:
        """创建成功响应."""
        response_data = ApiResponse.success(data, message, **kwargs)
        return ResponseHelper.create_json_response(response_data, status_code)

    @staticmethod
    def error_response(
        message: str = "操作失败", code: int = -1, status_code: int = 400, **kwargs
    ) -> JSONResponse:
        """创建错误响应."""
        response_data = ApiResponse.error(message, code, **kwargs)
        return ResponseHelper.create_json_response(response_data, status_code)

    @staticmethod
    def paginated_response(
        data: List[Any],
        total: int,
        page: int = 1,
        page_size: int = 20,
        status_code: int = 200,
        **kwargs,
    ) -> JSONResponse:
        """创建分页响应."""
        response_data = ApiResponse.paginated(data, total, page, page_size, **kwargs)
        return ResponseHelper.create_json_response(response_data, status_code)

    @staticmethod
    def validation_error_response(
        errors: List[Dict[str, Any]], message: str = "数据验证失败"
    ) -> JSONResponse:
        """创建验证错误响应."""
        response_data = ApiResponse.validation_error(errors, message)
        return ResponseHelper.create_json_response(response_data, 400)

    @staticmethod
    def not_found_response(
        resource: str = "资源", message: Optional[str] = None
    ) -> JSONResponse:
        """创建资源未找到响应."""
        response_data = ApiResponse.not_found(resource, message)
        return ResponseHelper.create_json_response(response_data, 404)

    @staticmethod
    def forbidden_response(message: str = "权限不足") -> JSONResponse:
        """创建权限不足响应."""
        response_data = ApiResponse.forbidden(message)
        return ResponseHelper.create_json_response(response_data, 403)

    @staticmethod
    def server_error_response(
        message: str = "服务器内部错误", error_id: Optional[str] = None
    ) -> JSONResponse:
        """创建服务器错误响应."""
        response_data = ApiResponse.server_error(message, error_id)
        return ResponseHelper.create_json_response(response_data, 500)


class HTTPExceptionHelper:
    """HTTP异常辅助工具."""

    @staticmethod
    def bad_request(
        message: str = "请求参数错误", details: Optional[Dict[str, Any]] = None
    ) -> HTTPException:
        """创建400错误异常."""
        return HTTPException(
            status_code=400,
            detail={
                "message": message,
                "details": details,
                "timestamp": datetime.now().isoformat(),
            },
        )

    @staticmethod
    def unauthorized(message: str = "未授权访问") -> HTTPException:
        """创建401错误异常."""
        return HTTPException(
            status_code=401,
            detail={"message": message, "timestamp": datetime.now().isoformat()},
        )

    @staticmethod
    def forbidden(message: str = "权限不足") -> HTTPException:
        """创建403错误异常."""
        return HTTPException(
            status_code=403,
            detail={"message": message, "timestamp": datetime.now().isoformat()},
        )

    @staticmethod
    def not_found(
        resource: str = "资源", message: Optional[str] = None
    ) -> HTTPException:
        """创建404错误异常."""
        if message is None:
            message = f"{resource}不存在"

        return HTTPException(
            status_code=404,
            detail={"message": message, "timestamp": datetime.now().isoformat()},
        )

    @staticmethod
    def conflict(message: str = "资源冲突") -> HTTPException:
        """创建409错误异常."""
        return HTTPException(
            status_code=409,
            detail={"message": message, "timestamp": datetime.now().isoformat()},
        )

    @staticmethod
    def unprocessable_entity(
        message: str = "数据格式错误", errors: Optional[List[Dict[str, Any]]] = None
    ) -> HTTPException:
        """创建422错误异常."""
        detail = {"message": message, "timestamp": datetime.now().isoformat()}

        if errors:
            detail["errors"] = str(errors)

        return HTTPException(status_code=422, detail=detail)

    @staticmethod
    def too_many_requests(
        message: str = "请求过于频繁", retry_after: Optional[int] = None
    ) -> HTTPException:
        """创建429错误异常."""
        detail = {"message": message, "timestamp": datetime.now().isoformat()}

        if retry_after:
            detail["retry_after"] = str(retry_after)

        return HTTPException(status_code=429, detail=detail)

    @staticmethod
    def internal_server_error(
        message: str = "服务器内部错误", error_id: Optional[str] = None
    ) -> HTTPException:
        """创建500错误异常."""
        detail = {"message": message, "timestamp": datetime.now().isoformat()}

        if error_id:
            detail["error_id"] = error_id

        return HTTPException(status_code=500, detail=detail)

    @staticmethod
    def service_unavailable(
        message: str = "服务不可用", retry_after: Optional[int] = None
    ) -> HTTPException:
        """创建503错误异常."""
        detail = {"message": message, "timestamp": datetime.now().isoformat()}

        if retry_after:
            detail["retry_after"] = str(retry_after)

        return HTTPException(status_code=503, detail=detail)


# 导出公共接口
__all__ = ["ApiResponse", "ResponseHelper", "HTTPExceptionHelper"]

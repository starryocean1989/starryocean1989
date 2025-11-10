# -*- coding: utf-8 -*-
"""数据中心服务代理.

该代理运行在主进程，通过 DataProcessClient 与数据进程中的真实
`DataCenterService` 通信，适配三进程架构。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict

from backend.framework import ServiceBase
from backend.core.contracts import DataServiceContract
from backend.infrastructure.data_module_vnpy.data_process_client import (
    get_data_process_client,
)

ROOT_PATH = Path(__file__).resolve().parent.parent.parent


class DataCenterServiceProxy(ServiceBase, DataServiceContract):
    """数据中心服务代理."""

    class _RemoteDownloadTasks:
        """远程下载任务集合，支持 `len()` 和 `size()`."""

        def __init__(self, proxy: "DataCenterServiceProxy") -> None:
            self._proxy = proxy

        def __len__(self) -> int:  # pragma: no cover - 简单访问器
            try:
                result = self._proxy._rpc_call("get_download_task_count")
                if isinstance(result, dict):
                    return int(result.get("count", 0))
                if isinstance(result, (int, float)):
                    return int(result)
            except Exception:
                pass
            return 0

        def size(self) -> int:  # pragma: no cover - 简单访问器
            return len(self)

    def __init__(self) -> None:
        ServiceBase.__init__(self)
        self.logger = logging.getLogger(self.__class__.__name__)
        self._client = get_data_process_client()
        self._download_tasks_proxy = DataCenterServiceProxy._RemoteDownloadTasks(self)

    def _do_initialize(self) -> bool:
        signal_path = ROOT_PATH / "logs" / "data_process_ready.signal"
        deadline = time.time() + 30
        while time.time() < deadline:
            if signal_path.exists():
                self.logger.debug("检测到数据进程就绪信号文件: %s", signal_path)
                break
            time.sleep(0.5)

        # 初始化阶段不强制连接，采用懒加载模式
        self.logger.info("ℹ️ 数据中心服务代理进入懒加载模式，首次调用时建立RPC连接")
        return True

    def _do_shutdown(self) -> bool:
        try:
            self._client.disconnect()
            self.logger.info("✅ 数据进程RPC客户端已断开")
        except Exception as exc:  # pragma: no cover - 关闭异常
            self.logger.warning(
                "⚠️ 断开数据进程RPC客户端时发生异常: %s",
                exc,
                extra={"log_type": "SYSTEM"},
            )
        return True

    def _do_health_check(self) -> Dict[str, Any]:
        return {"connected": self._client.is_connected()}

    def _rpc_call(self, method: str, *args, **kwargs) -> Any:
        if not self._ensure_connection():
            return {"success": False, "message": "无法连接数据进程"}
        return self._client.call(method, *args, **kwargs)

    def _ensure_connection(self) -> bool:
        if self._client.is_connected():
            return True

        last_error: Exception | None = None
        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                if self._client.connect():
                    self.logger.info("✅ 数据进程RPC客户端连接成功（第%d次尝试）", attempt)
                    return True
                self.logger.debug(
                    "数据进程RPC客户端连接失败（第%d次尝试），1秒后重试",
                    attempt,
                    extra={"log_type": "SYSTEM"},
                )
            except Exception as exc:
                last_error = exc
                self.logger.debug(
                    "数据进程RPC客户端连接异常（第%d次尝试）: %s",
                    attempt,
                    exc,
                    extra={"log_type": "SYSTEM"},
                )
            time.sleep(1)

        if last_error:
            self.logger.error(
                "❌ 数据进程RPC客户端连接异常: %s", last_error, exc_info=True, extra={"log_type": "SYSTEM"}
            )
        else:
            self.logger.error("❌ 数据进程RPC客户端连接失败，已达到最大重试次数")
        return False

    def __getattr__(self, item: str):  # pragma: no cover - 动态代理
        if item.startswith("_"):
            raise AttributeError(item)

        def wrapper(*args, **kwargs):
            try:
                return self._rpc_call(item, *args, **kwargs)
            except Exception as exc:
                self.logger.error(
                    "❌ 调用远程方法失败: %s(%s, %s) -> %s",
                    item,
                    args,
                    kwargs,
                    exc,
                    exc_info=True,
                    extra={"log_type": "SYSTEM"},
                )
                return {"success": False, "message": f"远程方法调用失败: {exc}"}

        return wrapper

    def refresh_symbol_list(self) -> Dict[str, Any]:
        """刷新品种列表."""
        return self._rpc_call("refresh_symbol_list")

    @property
    def _download_tasks(self) -> "DataCenterServiceProxy._RemoteDownloadTasks":  # pragma: no cover
        return self._download_tasks_proxy

# -*- coding: utf-8 -*-
"""
数据进程主入口 - 独立数据服务进程

职责：
- 初始化数据进程的日志系统（setup_subprocess_logging）
- 初始化数据服务（ChinaStockEngine、UnifiedDataManager等）
- 等待主进程的IPC连接
- 处理主进程的RPC请求（数据查询、计算任务等）

这是三进程架构中的数据进程，负责所有数据相关的操作。
"""

import asyncio
import json
import logging
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, cast

# 导入 talib 和 numpy
try:
    import talib
    import numpy as np
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    talib = None
    np = None

# 高性能JSON库（优先使用orjson）
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

# 在导入项目内模块前确保加入项目根目录，避免多进程环境下的导入失败
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.system_vnpy.logging_system import (
    alert_log,
    bind_logger_defaults,
    load_queue_from_env,
    setup_subprocess_logging,
    stage_log,
)
from backend.infrastructure.system_vnpy.process_watchdog import ensure_parent_watchdog
from backend.infrastructure.native.native_serialization import build_dataframe_payload
from backend.infrastructure.data_module_vnpy.rpc_protocol import (
    FLAG_BINARY_PAYLOAD,
    FLAG_ERROR,
    FLAG_NATIVE,
    RPCRequest,
    decode_request,
    encode_native_response,
    prepare_json_payload,
)
# 原生RPC桥接（用于方法ID映射）
try:
    from backend.infrastructure.native.native_rpc_bridge import (
        RPC_BRIDGE_AVAILABLE,
        batch_decode_requests,
        get_method_name,
    )
except ImportError:  # pragma: no cover - 构建失败时降级
    RPC_BRIDGE_AVAILABLE = False  # type: ignore

    def get_method_name(method_id: int) -> Optional[str]:  # type: ignore
        return None

    def batch_decode_requests(  # type: ignore
        buffer_sequence, method_resolver=None
    ):
        raise NotImplementedError

# 原生指标计算
try:
    from backend.infrastructure.native.native_indicator import (
        INDICATOR_AVAILABLE as NATIVE_INDICATOR_AVAILABLE,
        calculate_indicator as native_calculate_indicator,
    )
except ImportError:
    NATIVE_INDICATOR_AVAILABLE = False
    native_calculate_indicator = None  # type: ignore

# 原生风险指标
try:
    from backend.infrastructure.native.native_finance_ops import (
        FINANCE_OPS_AVAILABLE,
        compute_return_metrics as native_compute_return_metrics,
        compute_period_statistics as native_compute_period_statistics,
        compute_risk_profile as native_compute_risk_profile,
    )
    # 使用cast解决pyright无法识别C扩展函数签名的问题
    # 注意：这些函数实际上接受关键字参数，但我们用**kwargs来兼容
    native_compute_return_metrics = cast(
        Optional[Callable[..., Dict[str, Any]]],
        native_compute_return_metrics
    )
    native_compute_period_statistics = cast(
        Optional[Callable[..., Dict[str, Any]]],
        native_compute_period_statistics
    )
    native_compute_risk_profile = cast(
        Optional[Callable[..., Dict[str, Any]]],
        native_compute_risk_profile
    )
except ImportError:
    FINANCE_OPS_AVAILABLE = False
    native_compute_return_metrics = None  # type: ignore
    native_compute_period_statistics = None  # type: ignore
    native_compute_risk_profile = None  # type: ignore

# 添加项目根目录到Python路径（用于独立运行）
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


def get_root() -> Path:
    """获取项目根目录路径（统一方法，与工作目录解绑）

    通过当前文件的路径向上查找项目根目录。
    data_process_main.py 位于 backend/infrastructure/data_module_vnpy/
    需要向上4级到达项目根目录。

    Returns:
        Path: 项目根目录的Path对象
    """
    current_file = Path(__file__).resolve()
    root_path = current_file.parent.parent.parent.parent
    return root_path


# 创建专用logger（模块级别，数据进程独立）
logger = bind_logger_defaults(
    logging.getLogger("data_process"), log_type="SYSTEM", scenario="data_process"
)
logger_rpc = bind_logger_defaults(
    logging.getLogger("data_process.rpc"), log_type="SYSTEM", scenario="data_process.rpc"
)

DATA_PROCESS_SCENARIO = "data_process_init"

if not NATIVE_INDICATOR_AVAILABLE:
    alert_log(
        "⚠️ native_indicator扩展不可用，指标计算将回退到talib实现",
        scenario=DATA_PROCESS_SCENARIO,
        stacklevel=3,
    )

if not FINANCE_OPS_AVAILABLE:
    alert_log(
        "⚠️ native_finance_ops扩展不可用，风险指标计算将使用Python实现",
        scenario=DATA_PROCESS_SCENARIO,
        stacklevel=3,
    )

# 记录使用的JSON库
if HAS_ORJSON:
    logger.info("✅ 数据进程使用orjson高性能JSON库")
else:
    logger.warning("⚠️ 数据进程orjson不可用，使用标准json库（降级模式）")


# 尝试导入native_ipc
try:
    from backend.infrastructure.native.native_ipc import AsyncIPCPipe, IPC_AVAILABLE
    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe as _AsyncIPCPipe
    NATIVE_IPC_AVAILABLE = IPC_AVAILABLE
except ImportError:
    NATIVE_IPC_AVAILABLE = False
    _AsyncIPCPipe = None  # type: ignore
    AsyncIPCPipe = None  # type: ignore


class DataProcess:
    """数据进程主类

    负责：
    - 初始化数据服务
    - 处理主进程的RPC请求
    - 管理IPC连接
    """

    def __init__(self, log_queue: Optional[multiprocessing.Queue] = None):
        """初始化数据进程

        Args:
            log_queue: 日志队列（用于跨进程日志收集）
        """
        self.log_queue = log_queue
        self.china_stock_engine: Optional[Any] = None
        self.unified_data_manager: Optional[Any] = None
        self.load_balancer: Optional[Any] = None
        self.server_pool_manager: Optional[Any] = None
        self._is_ready = False
        self._rpc_server: Optional[Any] = None
        self._ipc_pipes: Dict[str, Any] = {}

        # 指标计算库
        self.talib = talib
        self.np = np

        # 管道连接状态跟踪（避免频繁尝试读取未连接的管道）
        self._pipe_connected: Dict[str, bool] = {}  # {pipe_name: is_connected}
        self._pipe_last_attempt: Dict[str, float] = {}  # {pipe_name: last_attempt_time}

        # 批量处理配置
        self._batch_size = 10  # 每批最多处理的请求数
        self._batch_timeout = 0.01  # 批次等待超时（秒）- 降低以提升响应速度

    def _parse_call_arguments(self, raw_params: Any) -> Tuple[List[Any], Dict[str, Any]]:
        """解析RPC请求中的位置参数和关键字参数."""
        if isinstance(raw_params, dict):
            args = raw_params.get("_args")
            kwargs = raw_params.get("_kwargs")

            if kwargs is None:
                kwargs_dict = dict(raw_params)
                kwargs_dict.pop("_args", None)
                kwargs_dict.pop("_kwargs", None)
            else:
                kwargs_dict = dict(kwargs) if isinstance(kwargs, dict) else {}

            if args is None:
                args_list: List[Any] = []
            elif isinstance(args, list):
                args_list = list(args)
            else:
                args_list = [args]

            return args_list, kwargs_dict

        return [], {}

    async def initialize(self):
        """初始化数据服务"""
        try:
            logger.debug(
                f"[DEBUG] 数据进程initialize开始 (PID={os.getpid()})",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            stage_log("📍 数据进程初始化开始", scenario="data_process_init", stacklevel=3)

            # 1. 初始化数据服务
            logger.debug(
                "[DEBUG] 数据进程开始初始化数据服务...",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            await self._initialize_data_services()
            logger.debug(
                "[DEBUG] 数据进程数据服务初始化完成",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            # 2. 初始化IPC服务器
            logger.debug(
                "[DEBUG] 数据进程开始初始化IPC服务器...",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            await self._initialize_ipc_server()
            logger.debug(
                "[DEBUG] 数据进程IPC服务器初始化完成",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            # 3. 标记就绪
            logger.debug(
                "[DEBUG] 数据进程开始写入就绪信号文件...",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            self._is_ready = True
            self._write_ready_signal()
            logger.debug(
                "[DEBUG] 数据进程就绪信号文件已写入",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            stage_log("✅ 数据进程初始化完成", scenario="data_process_init", stacklevel=3)

        except Exception as e:
            logger.debug(
                f"[DEBUG] 数据进程初始化失败: {e}",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            import traceback
            logger.debug(
                "[DEBUG] 数据进程初始化失败堆栈:",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            logger.error(f"❌ 数据进程初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            raise

    async def _initialize_data_services(self):
        """初始化数据服务"""
        try:
            if self.talib:
                stage_log("│ ✅ talib可用，指标计算功能完整", scenario="data_process_init", stacklevel=4)
            else:
                logger.warning(
                    "│ ⚠️ talib不可用，部分指标计算将受限",
                    extra={"log_type": "SYSTEM", "scenario": "data_process_init"},
                )

            stage_log("│ ⏳ 初始化ChinaStockEngine...", scenario="data_process_init", stacklevel=4)

            # 创建EventEngine（数据进程内部使用）
            from vnpy.event import EventEngine

            event_engine = EventEngine(interval=1)
            event_engine.start()

            # 初始化ChinaStockEngine（数据进程中没有main_engine，使用None）
            from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine

            # 在数据进程中，main_engine为None（因为MainEngine在主进程）
            # ChinaStockEngine需要兼容这种情况
            self.china_stock_engine = ChinaStockEngine(main_engine=None, event_engine=event_engine)
            success = self.china_stock_engine.initialize()
            if not success:
                raise RuntimeError("ChinaStockEngine初始化失败")

            stage_log("│ ✅ ChinaStockEngine初始化完成", scenario="data_process_init", stacklevel=4)

            stage_log("│ ⏳ 初始化UnifiedDataManager...", scenario="data_process_init", stacklevel=4)
            from backend.infrastructure.data_module_vnpy.data_runtime import UnifiedDataManager

            self.unified_data_manager = UnifiedDataManager(event_engine=event_engine)
            stage_log("│ ✅ UnifiedDataManager初始化完成", scenario="data_process_init", stacklevel=4)

            stage_log("│ ⏳ 初始化DataCenterService（RPC服务器）...", scenario="data_process_init", stacklevel=4)
            from backend.services.data_center_service import DataCenterService

            self.data_center_service = DataCenterService()
            stage_log("│ ✅ DataCenterService（RPC服务器）初始化完成", scenario="data_process_init", stacklevel=4)

            stage_log("│ ⏳ 初始化LoadBalancer...", scenario="data_process_init", stacklevel=4)
            from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer

            config_manager = self.china_stock_engine.config_manager
            self.load_balancer = LoadBalancer(config_manager=config_manager)
            stage_log("│ ✅ LoadBalancer初始化完成", scenario="data_process_init", stacklevel=4)

            stage_log("│ ⏳ 初始化ServerPoolManager...", scenario="data_process_init", stacklevel=4)
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                get_server_pool_manager,
            )

            self.server_pool_manager = get_server_pool_manager()
            stage_log("│ ✅ ServerPoolManager初始化完成", scenario=DATA_PROCESS_SCENARIO, stacklevel=4)

        except Exception as e:
            logger.error(f"❌ 数据服务初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            raise

    async def _initialize_ipc_server(self):
        """初始化IPC服务器"""
        if not NATIVE_IPC_AVAILABLE:
            alert_log("⚠️ native_ipc不可用，将使用降级方案", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)
            return

        try:
            stage_log("│ ⏳ 初始化IPC服务器...", scenario=DATA_PROCESS_SCENARIO, stacklevel=4)

            # 创建IPC管道
            # data_query: 数据查询管道
            # data_calculation: 计算任务管道
            pipe_names = ["data_query", "data_calculation"]

            for pipe_name in pipe_names:
                try:
                    # 检查AsyncIPCPipe是否可用
                    if not NATIVE_IPC_AVAILABLE or AsyncIPCPipe is None:
                        raise RuntimeError("native_ipc扩展不可用")
                    # AsyncIPCPipe使用server类方法创建服务端管道
                    pipe = await AsyncIPCPipe.server(pipe_name, wait_for_client=False)
                    self._ipc_pipes[pipe_name] = pipe
                    # 初始化连接状态跟踪
                    self._pipe_connected[pipe_name] = False
                    self._pipe_last_attempt[pipe_name] = 0
                    stage_log(
                        f"│ ✅ IPC管道已创建: {pipe_name}",
                        scenario=DATA_PROCESS_SCENARIO,
                        stacklevel=4,
                    )
                except Exception as e:
                    logger.error(
                        f"❌ 创建IPC管道失败: {pipe_name}, 错误: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT"},
                    )

            # 启动RPC服务器任务
            asyncio.create_task(self._rpc_server_task())

            stage_log("│ ✅ IPC服务器初始化完成", scenario=DATA_PROCESS_SCENARIO, stacklevel=4)

        except Exception as e:
            logger.error(f"❌ IPC服务器初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            raise

    async def _rpc_server_task(self):
        """RPC服务器任务（处理主进程的RPC请求）"""
        try:
            while True:
                # 处理数据查询请求
                if "data_query" in self._ipc_pipes:
                    await self._handle_data_query_requests()

                # 处理计算任务请求
                if "data_calculation" in self._ipc_pipes:
                    await self._handle_calculation_requests()

                await asyncio.sleep(0.1)  # 避免CPU占用过高

        except Exception as e:
            logger.error(f"❌ RPC服务器任务异常: {e}", exc_info=True, extra={"log_type": "ALERT"})

    async def _handle_data_query_requests(self):
        """处理数据查询请求（批量优化版）"""
        try:
            pipe = self._ipc_pipes.get("data_query")
            if not pipe:
                return

            pipe_name = "data_query"
            current_time = time.time()

            # 检查连接状态：如果未连接，且距离上次尝试不足1秒，则跳过
            if not self._pipe_connected.get(pipe_name, False):
                last_attempt = self._pipe_last_attempt.get(pipe_name, 0)
                if current_time - last_attempt < 1.0:  # 未连接时，每1秒尝试一次
                    return
                self._pipe_last_attempt[pipe_name] = current_time
                warning_key = f"{pipe_name}_warning_ts"
                last_warning_ts = self._pipe_last_attempt.get(warning_key)
                if last_warning_ts is None:
                    self._pipe_last_attempt[warning_key] = current_time
                elif current_time - last_warning_ts > 10.0:
                    logger.warning(f"IPC管道 '{pipe_name}' 超过10秒未连接", extra={"log_type": "SYSTEM"})
                    self._pipe_last_attempt[warning_key] = current_time

            # 批量读取请求
            batch_requests = []

            # 读取第一个请求（阻塞等待）
            try:
                first_request_data = await asyncio.wait_for(pipe.read(), timeout=0.1)
                # 成功读取，标记为已连接
                self._pipe_connected[pipe_name] = True

                if first_request_data:
                    batch_requests.append(first_request_data)

            except asyncio.TimeoutError:
                return
            except ValueError as e:
                # 管道未打开（客户端未连接），标记为未连接
                if "Pipe not opened" in str(e):
                    self._pipe_connected[pipe_name] = False
                    return
                # 其他ValueError，记录日志
                logger.debug(f"读取管道时发生错误: {e}", extra={"log_type": "SYSTEM"})
                return
            except Exception as e:
                # 其他异常，记录日志但不中断
                logger.debug(f"读取管道时发生异常: {e}", extra={"log_type": "SYSTEM"})
                return

            # 尝试读取更多请求（非阻塞，短超时）
            for _ in range(self._batch_size - 1):
                try:
                    extra_request_data = await asyncio.wait_for(
                        pipe.read(),
                        timeout=self._batch_timeout
                    )
                    if extra_request_data:
                        batch_requests.append(extra_request_data)
                except asyncio.TimeoutError:
                    # 没有更多请求，退出循环
                    break
                except Exception:
                    # 其他异常，退出循环
                    break

            # 如果没有读取到任何请求，直接返回
            if not batch_requests:
                return

            logger.info(f"开始处理 {len(batch_requests)} 个批量请求", extra={"log_type": "SYSTEM"})
            # 批量处理请求
            batch_responses = await self._process_batch_requests(batch_requests)

            # 批量发送响应
            for response_data in batch_responses:
                try:
                    await pipe.write(response_data)
                except Exception as e:
                    logger.error(
                        f"❌ 发送批量响应失败: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT"},
                    )

        except Exception as e:
            logger.error(
                f"❌ 处理数据查询请求异常: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

    async def _process_batch_requests(self, batch_requests: list) -> list:
        """批量处理RPC请求并返回序列化响应数据."""

        responses: List[bytes] = []

        if RPC_BRIDGE_AVAILABLE:
            try:
                native_decoded = batch_decode_requests(
                    batch_requests,
                    method_resolver=get_method_name,
                )
            except Exception as exc:
                logger.warning(
                    "⚠️ 原生批量解码失败，回退逐条解析: %s",
                    exc,
                    extra={"log_type": "SYSTEM"},
                )
                native_decoded = None
        else:
            native_decoded = None

        decoded_iterable: Iterable[Any]
        if native_decoded:
            decoded_iterable = native_decoded
        else:
            decoded_iterable = batch_requests

        for request_entry in decoded_iterable:
            try:
                if native_decoded:
                    (
                        method_id,
                        request_id,
                        flags,
                        method_name,
                        metadata,
                        payload_view,
                    ) = request_entry
                    request_id = int(request_id)
                    flags = int(flags)
                    metadata_dict = metadata if isinstance(metadata, dict) else {}
                    params = metadata_dict.get("params", {})
                    method = (method_name or metadata_dict.get("method") or "").strip()
                    if not method:
                        method = get_method_name(method_id) or ""
                    is_native = True
                    binary_payload = payload_view if payload_view not in (None, Py_None) else None  # type: ignore[name-defined]
                    request_id = request_id
                else:
                    rpc_request: RPCRequest = decode_request(
                        request_entry,
                        method_resolver=get_method_name if RPC_BRIDGE_AVAILABLE else (lambda _: ""),
                    )
                    method = rpc_request.method
                    params = rpc_request.params or {}
                    is_native = rpc_request.is_native
                    method_id = rpc_request.method_id or 0
                    request_id = rpc_request.request_id
                    flags = rpc_request.flags
                    binary_payload = rpc_request.payload

                logger.debug(
                    "收到RPC请求: %s",
                    method,
                    extra={"log_type": "SYSTEM", "request_id": request_id},
                )

                response_payload: Any = None
                error_message: Optional[str] = None

                try:
                    args, kwargs = self._parse_call_arguments(params)
                    params_dict = kwargs if kwargs else (params if isinstance(params, dict) else {})
                    if method == "get_kline_data":
                        response_payload, binary_payload = await self._handle_get_kline_data(params_dict)
                    elif method == "get_symbol_list":
                        response_payload = await self._handle_get_symbol_list(params_dict)
                    else:
                        try:
                            response_payload = await self._invoke_data_center_method(
                                method, args, kwargs
                            )
                        except AttributeError:
                            error_message = f"未知方法: {method}"
                        except Exception as exc:
                            error_message = str(exc)
                except Exception as exc:
                    logger.error(
                        "❌ 批量处理RPC请求失败: %s, 错误: %s",
                        method,
                        exc,
                        extra={"log_type": "ALERT"},
                        exc_info=True,
                    )
                    error_message = str(exc)

                if is_native:
                    target_request_id = request_id
                    target_method_id = method_id

                    if error_message:
                        response_bytes = encode_native_response(
                            request_id=target_request_id,
                            method_id=target_method_id,
                            result=None,
                            error=error_message,
                            flags=flags,
                        )
                    else:
                        native_metadata: Dict[str, Any] | None = None
                        binary_path: Optional[Sequence[str]] = None
                        if isinstance(response_payload, dict):
                            native_metadata = {"result": response_payload}
                            if binary_payload is not None:
                                binary_path = ("result", "data")
                        response_bytes = encode_native_response(
                            request_id=target_request_id,
                            method_id=target_method_id,
                            result=response_payload,
                            flags=flags,
                            binary_payload=binary_payload,
                            metadata=native_metadata,
                            binary_field_path=binary_path,
                        )
                    responses.append(response_bytes)
                    logger.debug(
                        "发送本地响应: %s",
                        method,
                        extra={"log_type": "SYSTEM", "request_id": target_request_id},
                    )
                    continue

                if native_decoded:
                    response_request_id = request_id
                else:
                    response_request_id = rpc_request.request_id

                if error_message:
                    response_dict = {"id": response_request_id, "error": error_message}
                else:
                    result_payload = response_payload
                    if binary_payload is not None and isinstance(response_payload, dict):
                        result_payload = prepare_json_payload(response_payload, binary_payload)
                    elif binary_payload is not None:
                        result_payload = {
                            "transport": "buffer",
                            "data": binary_payload,
                            "metadata": {"encoding": "raw-buffer"},
                        }
                    response_dict = {"id": response_request_id, "result": result_payload}

                if HAS_ORJSON:
                    responses.append(orjson.dumps(response_dict))
                else:
                    responses.append(json.dumps(response_dict, ensure_ascii=False).encode("utf-8"))
                logger.debug(
                    "发送JSON响应: %s",
                    method,
                    extra={"log_type": "SYSTEM", "request_id": response_request_id},
                )

            except Exception as exc:
                logger.error(
                    "❌ 批量处理请求异常: %s",
                    exc,
                    exc_info=True,
                    extra={"log_type": "ALERT"},
                )

        return responses

    async def _invoke_data_center_method(
        self,
        method: str,
        args: Sequence[Any],
        kwargs: Dict[str, Any],
    ) -> Any:
        """调用数据中心服务方法."""
        service = getattr(self, "data_center_service", None)
        if service is None:
            raise RuntimeError("DataCenterService 未初始化")

        target = getattr(service, method, None)
        if target is None:
            raise AttributeError(f"DataCenterService 未实现方法: {method}")

        if asyncio.iscoroutinefunction(target):
            return await target(*args, **kwargs)

        return await asyncio.to_thread(target, *args, **kwargs)

    async def _handle_calculation_requests(self):
        """处理计算任务请求"""
        try:
            pipe = self._ipc_pipes.get("data_calculation")
            if not pipe:
                return

            pipe_name = "data_calculation"
            current_time = time.time()

            # 检查连接状态：如果未连接，且距离上次尝试不足1秒，则跳过
            if not self._pipe_connected.get(pipe_name, False):
                last_attempt = self._pipe_last_attempt.get(pipe_name, 0)
                if current_time - last_attempt < 1.0:  # 未连接时，每1秒尝试一次
                    return
                self._pipe_last_attempt[pipe_name] = current_time
                warning_key = f"{pipe_name}_warning_ts"
                last_warning_ts = self._pipe_last_attempt.get(warning_key)
                if last_warning_ts is None:
                    self._pipe_last_attempt[warning_key] = current_time
                elif current_time - last_warning_ts > 10.0:
                    logger.warning(f"IPC管道 '{pipe_name}' 超过10秒未连接", extra={"log_type": "SYSTEM"})
                    self._pipe_last_attempt[warning_key] = current_time

            # 读取请求（非阻塞）
            try:
                request_data = await asyncio.wait_for(pipe.read(), timeout=0.1)
                # 成功读取，标记为已连接
                self._pipe_connected[pipe_name] = True
            except asyncio.TimeoutError:
                return
            except ValueError as e:
                # 管道未打开（客户端未连接），标记为未连接
                if "Pipe not opened" in str(e):
                    self._pipe_connected[pipe_name] = False
                    return
                # 其他ValueError，记录日志
                logger.debug(f"读取管道时发生错误: {e}", extra={"log_type": "SYSTEM"})
                return
            except Exception as e:
                # 其他异常，记录日志但不中断
                logger.debug(f"读取管道时发生异常: {e}", extra={"log_type": "SYSTEM"})
                return

            if not request_data:
                return

            # 解析请求
            try:
                if HAS_ORJSON:
                    # orjson.loads可以直接处理bytes
                    request = orjson.loads(request_data)
                else:
                    # 降级到标准json
                    request = json.loads(request_data)
            except json.JSONDecodeError:
                logger.warning("⚠️ 无效的计算任务请求格式", extra={"log_type": "SYSTEM"})
                return

            # 处理请求
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")
            logger.debug(f"收到计算任务请求: {method}", extra={"log_type": "SYSTEM", "request_id": request_id})

            try:
                args, kwargs = self._parse_call_arguments(params)
                params_dict = kwargs if kwargs else (params if isinstance(params, dict) else {})
                if method == "calculate_indicator":
                    result = await self._handle_calculate_indicator(params_dict)
                elif method == "calculate_risk_metrics":
                    result = await self._handle_calculate_risk_metrics(params_dict)
                elif method == "compute_period_statistics":
                    result = await self._handle_compute_period_statistics(params_dict)
                elif method == "compute_risk_profile":
                    result = await self._handle_compute_risk_profile(params_dict)
                else:
                    try:
                        result = await self._invoke_data_center_method(method, args, kwargs)
                    except AttributeError:
                        result = {"success": False, "message": f"未知方法: {method}"}
                    except Exception as exc:
                        result = {"success": False, "message": str(exc)}

                # 发送响应
                response = {"id": request_id, "result": result}
                if HAS_ORJSON:
                    # orjson.dumps返回bytes，直接使用
                    response_data = orjson.dumps(response)
                else:
                    # 降级到标准json
                    response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)
                logger.debug(f"发送计算任务响应: {method}", extra={"log_type": "SYSTEM", "request_id": request_id})

            except Exception as e:
                logger.error(
                    f"❌ 处理计算任务请求失败: {method}, 错误: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT"},
                )
                # 发送错误响应
                response = {"id": request_id, "error": str(e)}
                if HAS_ORJSON:
                    # orjson.dumps返回bytes，直接使用
                    response_data = orjson.dumps(response)
                else:
                    # 降级到标准json
                    response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)
                logger.debug(f"发送计算任务错误响应: {method}", extra={"log_type": "SYSTEM", "request_id": request_id})

        except Exception as e:
            logger.error(
                f"❌ 处理计算任务请求异常: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

    async def _handle_get_kline_data(self, params: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[memoryview]]:
        """处理获取K线数据请求"""
        try:
            if not self.unified_data_manager:
                return {"success": False, "message": "UnifiedDataManager未初始化"}, None

            symbol = params.get("symbol")
            interval = params.get("interval", "1d")
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            check_gaps = params.get("check_gaps", False)
            prefer_format = params.get("prefer_format", "arrow")

            df = self.unified_data_manager.get_kline_data(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
                use_preload=True,
            )

            if df is not None and not df.empty:
                payload = build_dataframe_payload(
                    df,
                    prefer_format="arrow" if prefer_format == "arrow" else "records",
                )

                if payload.transport == "buffer" and isinstance(payload.data, (memoryview, bytes, bytearray)):
                    binary_view = payload.data if isinstance(payload.data, memoryview) else memoryview(payload.data)
                    result_payload: Dict[str, Any] = {
                        "success": True,
                        "message": f"获取 {payload.rows} 条数据",
                        "format": payload.format,
                        "transport": payload.transport,
                        "rows": payload.rows,
                        "columns": payload.columns,
                        "metadata": payload.metadata,
                        "data": [],
                    }
                    return result_payload, binary_view

                return (
                    {
                        "success": True,
                        "message": f"获取 {payload.rows} 条数据",
                        "format": payload.format,
                        "transport": payload.transport,
                        "rows": payload.rows,
                        "columns": payload.columns,
                        "metadata": payload.metadata,
                        "data": payload.data,
                    },
                    None,
                )
            else:
                return (
                    {
                        "success": False,
                        "message": "数据为空",
                        "format": "records",
                        "transport": "json",
                        "data": [],
                        "rows": 0,
                        "columns": [],
                    },
                    None,
                )

        except Exception as e:
            logger.error(f"❌ 获取K线数据失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}, None

    async def _handle_get_symbol_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取品种列表请求"""
        try:
            if not self.unified_data_manager:
                return {"success": False, "message": "UnifiedDataManager未初始化"}

            # 使用UnifiedDataManager的get_all_contracts方法
            contracts = self.unified_data_manager.get_all_contracts()

            # 提取品种代码列表
            symbol_list = [
                contract.get("symbol") for contract in contracts if contract.get("symbol")
            ]

            return {
                "success": True,
                "data": symbol_list,
                "message": f"获取 {len(symbol_list)} 个品种",
            }

        except Exception as e:
            logger.error(f"❌ 获取品种列表失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

    async def _handle_calculate_indicator(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理计算技术指标请求"""
        try:
            # 使用线程池执行计算任务（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as executor:
                result = await loop.run_in_executor(executor, self._do_calculate_indicator, params)

            return result

        except Exception as e:
            logger.error(f"❌ 计算技术指标失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

    def _do_calculate_indicator(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行技术指标计算（优先native，回退talib）"""
        data = params.get("data", [])
        indicator_name_raw = params.get("indicator_name")
        indicator_params = params.get("params", {})

        indicator_name = str(indicator_name_raw or "").strip()
        if not indicator_name:
            return {"success": False, "message": "缺少指标名称"}

        if not data:
            return {"success": False, "message": "输入数据为空"}

        closes: List[float] = []
        for item in data:
            if isinstance(item, dict):
                closes.append(float(item.get("close", 0.0)))
            else:
                closes.append(float(item))

        # 1. 尝试使用 native_indicator
        if NATIVE_INDICATOR_AVAILABLE and native_calculate_indicator is not None:
            try:
                result_native = native_calculate_indicator(indicator_name, closes, **indicator_params)
                if isinstance(result_native, dict) and result_native.get("success"):
                    native_data = result_native.get("data")
                    return {
                        "success": True,
                        "data": native_data,
                        "engine": "native_indicator",
                        "message": f"计算 {indicator_name} 完成",
                    }
                logger.debug("native_indicator 计算失败，回退到talib")
            except Exception:
                logger.debug("native_indicator 计算异常，回退到talib", exc_info=True)

        # 2. 回退到 talib
        try:
            import talib
            import numpy as np

            closes_array = np.array(closes, dtype=float)
            indicator_name_upper = indicator_name.upper()

            result_data = None
            if indicator_name_upper == "SMA":
                result_data = talib.SMA(closes_array, timeperiod=indicator_params.get("period", 5))
            elif indicator_name_upper == "EMA":
                result_data = talib.EMA(closes_array, timeperiod=indicator_params.get("period", 5))
            elif indicator_name_upper == "MACD":
                macd, signal, hist = talib.MACD(
                    closes_array,
                    fastperiod=indicator_params.get("fast", 12),
                    slowperiod=indicator_params.get("slow", 26),
                    signalperiod=indicator_params.get("signal", 9),
                )
                result_data = {"macd": macd.tolist(), "signal": signal.tolist(), "hist": hist.tolist()}
            elif indicator_name_upper == "RSI":
                result_data = talib.RSI(closes_array, timeperiod=indicator_params.get("period", 14))
            else:
                return {"success": False, "message": f"指标 {indicator_name} 在talib中不支持"}

            if isinstance(result_data, np.ndarray):
                result_data = result_data.tolist()

            return {
                "success": True,
                "data": result_data,
                "engine": "talib",
                "message": f"计算 {indicator_name} 完成",
            }
        except ImportError:
            return {"success": False, "message": "指标计算引擎talib不可用"}
        except Exception as e:
            logger.error(f"talib 计算失败: {e}", exc_info=True)
            return {"success": False, "message": f"talib 计算失败: {e}"}

    async def _handle_calculate_risk_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理计算风险指标请求"""
        try:
            # 使用线程池执行计算任务（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as executor:
                result = await loop.run_in_executor(
                    executor, self._do_calculate_risk_metrics, params
                )

            return result

        except Exception as e:
            logger.error(f"❌ 计算风险指标失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

    def _do_calculate_risk_metrics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行风险指标计算（在线程池中执行）"""
        try:
            import numpy as np

            portfolio_name = params.get("portfolio_name", "")
            price_history = params.get("price_history", [])
            confidence_level = params.get("confidence_level", 0.95)

            if not price_history or len(price_history) < 2:
                return {"success": False, "message": "价格数据不足，无法计算风险指标"}

            # 转换为numpy数组
            prices = np.array(price_history)

            # 计算收益率
            returns = np.diff(prices) / prices[:-1]

            volatility = float(np.std(returns) * np.sqrt(252))

            var_percentile = (1 - confidence_level) * 100
            var_value = float(np.percentile(returns, var_percentile))
            var_amount = abs(var_value * prices[-1])

            cvar_returns = returns[returns <= var_value]
            cvar_value = float(np.mean(cvar_returns)) if len(cvar_returns) > 0 else var_value
            cvar_amount = abs(cvar_value * prices[-1])

            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

            risk_free_rate = 0.03
            excess_returns = float(np.mean(returns) * 252 - risk_free_rate)
            sharpe_ratio = excess_returns / volatility if volatility > 0 else 0.0

            additional_metrics: Dict[str, Any] = {}

            if FINANCE_OPS_AVAILABLE and native_compute_return_metrics is not None:
                try:
                    pnl_series = returns.tolist()
                    equity_series = cumulative.tolist()
                    native_metrics = native_compute_return_metrics(  # pyright: ignore[reportCallIssue]
                        pnl_series=pnl_series,
                        equity_series=equity_series,
                        trading_days_per_year=252,
                    )
                    if isinstance(native_metrics, dict) and native_metrics:
                        volatility = float(native_metrics.get("volatility", volatility))
                        sharpe_ratio = float(native_metrics.get("sharpe_ratio", sharpe_ratio))
                        max_drawdown = float(native_metrics.get("max_drawdown", max_drawdown))
                        additional_metrics.update(
                            {
                                "total_return": float(native_metrics.get("total_return", 0.0)),
                                "annualized_return": float(native_metrics.get("annualized_return", 0.0)),
                                "calmar_ratio": float(native_metrics.get("calmar_ratio", 0.0)),
                            }
                        )
                except Exception:
                    logger.debug("native_finance_ops 计算失败，回退到numpy实现", exc_info=True)

            if not additional_metrics:
                additional_metrics = {
                    "total_return": float(np.sum(returns)),
                    "annualized_return": float(np.mean(returns) * 252),
                    "calmar_ratio": float(sharpe_ratio / abs(max_drawdown)) if max_drawdown else 0.0,
                }

            return {
                "success": True,
                "metrics": {
                    "volatility": float(volatility),
                    "var_95": float(var_amount),
                    "cvar_95": float(cvar_amount),
                    "max_drawdown": float(max_drawdown),
                    "sharpe_ratio": float(sharpe_ratio),
                    "mean_return": float(np.mean(returns)),
                    "std_return": float(np.std(returns)),
                    **additional_metrics,
                },
            }

        except ImportError:
            return {"success": False, "message": "numpy未安装"}
        except Exception as e:
            logger.error(
                f"❌ 执行风险指标计算失败: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )
            return {"success": False, "message": str(e)}

    async def _handle_compute_period_statistics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理周期统计请求"""
        try:
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as executor:
                result = await loop.run_in_executor(executor, self._do_compute_period_statistics, params)
            return result
        except Exception as e:
            logger.error("❌ 计算周期统计失败: %s", e, exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

    def _do_compute_period_statistics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        dates = params.get("dates") or []
        pnl = params.get("pnl") or []
        initial_equity = float(params.get("initial_equity", 1_000_000.0))
        risk_free_rate = float(params.get("risk_free_rate", 0.03))
        trading_days = int(params.get("trading_days_per_year", 252))

        if not dates or not pnl or len(dates) != len(pnl):
            return {"success": False, "message": "缺少有效的日期或盈亏数据"}

        if FINANCE_OPS_AVAILABLE and native_compute_period_statistics:
            try:
                result = native_compute_period_statistics(  # pyright: ignore[reportCallIssue]
                    dates=dates,
                    pnl=pnl,
                    initial_equity=initial_equity,
                    risk_free_rate=risk_free_rate,
                    trading_days_per_year=trading_days,
                )
                if isinstance(result, dict):
                    result.setdefault("success", True)
                    return result
            except Exception:
                logger.debug(
                    "native_finance_ops.compute_period_statistics失败, 回退Python实现",
                    exc_info=True,
                )

        return self._python_compute_period_statistics(
            dates, pnl, initial_equity, risk_free_rate, trading_days
        )

    def _python_compute_period_statistics(
        self,
        dates: Sequence[Any],
        pnl: Sequence[float],
        initial_equity: float,
        risk_free_rate: float,
        trading_days: int,
    ) -> Dict[str, Any]:
        from collections import OrderedDict
        from datetime import datetime
        import math

        def parse_date(value: Any) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, (int, float)):
                text = f"{int(value):08d}"
                return datetime.strptime(text, "%Y%m%d")
            if isinstance(value, str):
                text = value.strip()
                if len(text) >= 10 and text[4] == "-" and text[7] == "-":
                    return datetime.strptime(text[:10], "%Y-%m-%d")
                if len(text) == 8 and text.isdigit():
                    return datetime.strptime(text, "%Y%m%d")
            raise ValueError(f"无法解析日期: {value}")

        try:
            combined = []
            for d, amount in zip(dates, pnl):
                dt = parse_date(d)
                combined.append((dt, float(amount)))

            combined.sort(key=lambda x: x[0])
            if not combined:
                return {
                    "success": True,
                    "daily": [],
                    "weekly": [],
                    "monthly": [],
                    "equity_curve": [],
                    "summary": {
                        "initial_equity": initial_equity,
                        "final_equity": initial_equity,
                        "total_pnl": 0.0,
                        "total_return": 0.0,
                        "annual_return": 0.0,
                        "volatility": 0.0,
                        "sharpe_ratio": 0.0,
                        "max_drawdown": 0.0,
                        "max_drawdown_duration": 0.0,
                        "win_rate": 0.0,
                        "trading_days": 0,
                    },
                }

            daily_map: OrderedDict[str, float] = OrderedDict()
            for dt, amount in combined:
                key = dt.strftime("%Y-%m-%d")
                daily_map[key] = daily_map.get(key, 0.0) + amount

            equity = initial_equity
            daily_entries: List[Dict[str, Any]] = []
            equity_curve: List[Dict[str, Any]] = []
            sum_returns = 0.0
            sum_square_returns = 0.0
            win_days = 0
            raw_daily = []

            for key, amount in daily_map.items():
                start_equity = equity
                equity += amount
                daily_return = amount / start_equity if start_equity > 0 else 0.0
                cumulative_return = (equity - initial_equity) / initial_equity if initial_equity > 0 else 0.0

                daily_entries.append(
                    {
                        "period": key,
                        "pnl": float(amount),
                        "return": float(daily_return),
                        "start_equity": float(start_equity),
                        "end_equity": float(equity),
                        "cumulative_return": float(cumulative_return),
                    }
                )
                equity_curve.append({"date": key, "equity": float(equity)})
                raw_daily.append((datetime.strptime(key, "%Y-%m-%d"), start_equity, equity, amount))

                sum_returns += daily_return
                sum_square_returns += daily_return * daily_return
                if amount > 0:
                    win_days += 1

            def aggregate_period(mode: str) -> List[Dict[str, Any]]:
                aggregated: OrderedDict[str, Dict[str, Any]] = OrderedDict()
                for dt, start_eq, end_eq, amount in raw_daily:
                    if mode == "weekly":
                        key = dt.strftime("%G-W%V")
                    elif mode == "monthly":
                        key = dt.strftime("%Y-%m")
                    else:
                        key = dt.strftime("%Y")

                    entry = aggregated.get(key)
                    if not entry:
                        entry = {
                            "period": key,
                            "pnl": 0.0,
                            "start_equity": float(start_eq),
                            "end_equity": float(end_eq),
                        }
                        aggregated[key] = entry

                    entry["pnl"] += float(amount)
                    entry["end_equity"] = float(end_eq)

                result_items: List[Dict[str, Any]] = []
                for entry in aggregated.values():
                    start_eq = entry["start_equity"]
                    end_eq = entry["end_equity"]
                    entry["return"] = (end_eq - start_eq) / start_eq if start_eq > 0 else 0.0
                    entry["cumulative_return"] = (end_eq - initial_equity) / initial_equity if initial_equity > 0 else 0.0
                    result_items.append(entry)
                return result_items

            weekly_entries = aggregate_period("weekly")
            monthly_entries = aggregate_period("monthly")

            trading_days_count = len(daily_entries)
            mean_return = sum_returns / trading_days_count if trading_days_count else 0.0
            variance = (sum_square_returns / trading_days_count - mean_return * mean_return) if trading_days_count else 0.0
            variance = max(variance, 0.0)
            std_daily = math.sqrt(variance)
            annual_return = mean_return * trading_days
            annual_volatility = std_daily * math.sqrt(trading_days)
            sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0.0
            win_rate = win_days / trading_days_count if trading_days_count else 0.0
            total_pnl = equity - initial_equity
            total_return = (equity - initial_equity) / initial_equity if initial_equity > 0 else 0.0

            peak = initial_equity
            max_drawdown = 0.0
            peak_index = 0
            trough_index = 0
            current_peak_index = 0
            equity_values = [point["equity"] for point in equity_curve]
            for idx, eq in enumerate(equity_values):
                if eq > peak:
                    peak = eq
                    current_peak_index = idx
                dd = (eq - peak) / peak if peak > 0 else 0.0
                if dd < max_drawdown:
                    max_drawdown = dd
                    peak_index = current_peak_index
                    trough_index = idx

            max_drawdown_duration = float(trough_index - peak_index) if trough_index > peak_index else 0.0

            summary = {
                "initial_equity": float(initial_equity),
                "final_equity": float(equity),
                "total_pnl": float(total_pnl),
                "total_return": float(total_return),
                "annual_return": float(annual_return),
                "volatility": float(annual_volatility),
                "sharpe_ratio": float(sharpe_ratio),
                "max_drawdown": float(max_drawdown),
                "max_drawdown_duration": float(max_drawdown_duration),
                "win_rate": float(win_rate),
                "trading_days": trading_days_count,
            }

            return {
                "success": True,
                "daily": daily_entries,
                "weekly": weekly_entries,
                "monthly": monthly_entries,
                "equity_curve": equity_curve,
                "summary": summary,
            }
        except Exception as exc:
            logger.error("Python周期统计失败: %s", exc, exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(exc)}

    async def _handle_compute_risk_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理风险画像请求"""
        try:
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=4) as executor:
                result = await loop.run_in_executor(executor, self._do_compute_risk_profile, params)
            return result
        except Exception as e:
            logger.error("❌ 计算风险画像失败: %s", e, exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

    def _do_compute_risk_profile(self, params: Dict[str, Any]) -> Dict[str, Any]:
        returns = params.get("returns") or []
        scale = float(params.get("scale", 1.0))
        risk_free_rate = float(params.get("risk_free_rate", 0.03))
        trading_days = int(params.get("trading_days_per_year", 252))
        confidence_levels = params.get("confidence_levels") or [0.95, 0.99]

        if not returns or len(returns) < 2:
            return {"success": False, "message": "缺少足够的收益率数据"}

        if FINANCE_OPS_AVAILABLE and native_compute_risk_profile:
            try:
                result = native_compute_risk_profile(  # pyright: ignore[reportCallIssue]
                    returns=returns,
                    scale=scale,
                    risk_free_rate=risk_free_rate,
                    trading_days_per_year=trading_days,
                    confidence_levels=confidence_levels,
                )
                if isinstance(result, dict):
                    result["success"] = True
                    return result
            except Exception:
                logger.debug(
                    "native_finance_ops.compute_risk_profile失败, 回退Python实现",
                    exc_info=True,
                )

        return self._python_compute_risk_profile(
            returns, scale, risk_free_rate, trading_days, confidence_levels
        )

    def _python_compute_risk_profile(
        self,
        returns: Sequence[float],
        scale: float,
        risk_free_rate: float,
        trading_days: int,
        confidence_levels: Sequence[float],
    ) -> Dict[str, Any]:
        try:
            import numpy as np

            returns_arr = np.asarray(returns, dtype=float)
            if returns_arr.size < 2:
                return {"success": False, "message": "收益率数据不足"}

            mean_return = float(np.mean(returns_arr))
            std_return = float(np.std(returns_arr))
            annual_return = mean_return * trading_days
            annual_volatility = std_return * np.sqrt(trading_days)
            sharpe_ratio = (
                (annual_return - risk_free_rate) / annual_volatility if annual_volatility > 0 else 0.0
            )

            downside = returns_arr[returns_arr < 0]
            downside_deviation = float(np.std(downside) * np.sqrt(trading_days)) if downside.size > 0 else 0.0
            sortino_ratio = (
                (annual_return - risk_free_rate) / downside_deviation if downside_deviation > 0 else 0.0
            )

            win_rate = float(np.mean(returns_arr > 0))
            loss_rate = float(np.mean(returns_arr < 0))
            avg_gain = float(np.mean(returns_arr[returns_arr > 0])) if np.any(returns_arr > 0) else 0.0
            avg_loss = float(np.mean(returns_arr[returns_arr < 0])) if np.any(returns_arr < 0) else 0.0

            skewness = (
                float(((returns_arr - mean_return) ** 3).mean() / (std_return**3)) if std_return > 0 else 0.0
            )
            kurtosis = (
                float(((returns_arr - mean_return) ** 4).mean() / (std_return**4)) if std_return > 0 else 0.0
            )

            levels = confidence_levels if confidence_levels else [0.95, 0.99]
            var_result: Dict[str, Dict[str, float]] = {}
            for level in levels:
                level_float = float(level)
                level_float = min(max(level_float, 0.0), 0.999)
                var_value = float(np.quantile(returns_arr, 1.0 - level_float))
                tail = returns_arr[returns_arr <= var_value]
                cvar_value = float(tail.mean()) if tail.size > 0 else var_value
                key = f"{level_float:.2f}"
                var_result[key] = {
                    "var_value": var_value,
                    "var_amount": abs(var_value * scale),
                    "cvar_value": cvar_value,
                    "cvar_amount": abs(cvar_value * scale),
                }

            equity_curve = np.cumprod(np.concatenate(([1.0], 1 + returns_arr)))
            peak = np.maximum.accumulate(equity_curve)
            drawdowns = (equity_curve - peak) / peak
            max_drawdown = float(np.min(drawdowns))
            trough_index = int(np.argmin(drawdowns))
            peak_index = int(np.argmax(equity_curve[: trough_index + 1])) if trough_index >= 0 else 0
            max_drawdown_duration = float(trough_index - peak_index) if trough_index > peak_index else 0.0
            calmar_ratio = (annual_return / abs(max_drawdown)) if max_drawdown < 0 else 0.0
            cumulative_return = float(equity_curve[-1] - 1.0)

            return {
                "success": True,
                "count": int(returns_arr.size),
                "mean_return": mean_return,
                "std_return": std_return,
                "annual_return": annual_return,
                "annual_volatility": annual_volatility,
                "sharpe_ratio": sharpe_ratio,
                "sortino_ratio": sortino_ratio,
                "skewness": skewness,
                "kurtosis": kurtosis,
                "win_rate": win_rate,
                "loss_rate": loss_rate,
                "avg_gain": avg_gain,
                "avg_loss": avg_loss,
                "downside_deviation": downside_deviation,
                "max_drawdown": max_drawdown,
                "max_drawdown_duration": max_drawdown_duration,
                "calmar_ratio": calmar_ratio,
                "cumulative_return": cumulative_return,
                "var": var_result,
                "equity_curve": equity_curve.tolist(),
            }
        except Exception as exc:
            logger.error("Python风险画像计算失败: %s", exc, exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(exc)}

    def _write_ready_signal(self):
        """写入就绪信号文件"""
        try:
            root = get_root()
            signal_file = root / "logs" / "data_process_ready.signal"
            logger.debug(
                f"[DEBUG] 数据进程准备写入就绪信号文件: {signal_file} (PID={os.getpid()})",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            # 确保logs目录存在
            signal_file.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "[DEBUG] 数据进程logs目录已确保存在",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            # 写入信号文件
            signal_data = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "level": 2,  # Level 2: 功能完整
                "pipes": list(self._ipc_pipes.keys()),
            }
            logger.debug(
                f"[DEBUG] 数据进程信号数据: {signal_data}",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            with open(signal_file, "w", encoding="utf-8") as f:
                # 使用标准json以确保格式正确（orjson的OPT_INDENT_2会省略逗号）
                json.dump(signal_data, f, indent=2)
            logger.debug(
                f"[DEBUG] 数据进程就绪信号文件已写入: {signal_file}",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )

            stage_log(f"✅ 就绪信号文件已写入: {signal_file}", scenario="data_process_init", stacklevel=4)

        except Exception as e:
            logger.debug(
                f"[DEBUG] 数据进程写入就绪信号文件失败: {e}",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            import traceback
            logger.debug(
                "[DEBUG] 写入就绪信号文件失败堆栈:",
                extra={"log_type": "DEBUG", "scenario": "data_process_init"},
            )
            logger.error(
                f"❌ 写入就绪信号文件失败: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

    async def run(self):
        """运行数据进程"""
        try:
            # 🔧 调试：记录数据进程启动
            logger.debug(
                f"[DEBUG] 数据进程开始运行 (PID={os.getpid()})",
                extra={"log_type": "DEBUG", "scenario": "data_process_run"},
            )

            # 初始化
            logger.debug(
                "[DEBUG] 数据进程开始初始化...",
                extra={"log_type": "DEBUG", "scenario": "data_process_run"},
            )
            await self.initialize()
            logger.debug(
                "[DEBUG] 数据进程初始化完成",
                extra={"log_type": "DEBUG", "scenario": "data_process_run"},
            )

            # 保持运行
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            stage_log("📍 数据进程收到中断信号，正在退出...", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)
        except Exception as e:
            import sys
            print(f"[DEBUG] 数据进程运行异常: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            logger.error(f"❌ 数据进程运行异常: {e}", exc_info=True, extra={"log_type": "ALERT"})
        finally:
            # 清理资源
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        try:
            stage_log("📍 数据进程清理资源...", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)

            # 关闭IPC管道
            for pipe_name, pipe in self._ipc_pipes.items():
                try:
                    await pipe.close()
                    stage_log(f"✅ IPC管道已关闭: {pipe_name}", scenario=DATA_PROCESS_SCENARIO, stacklevel=4)
                except Exception as e:
                    logger.warning(
                        f"⚠️ 关闭IPC管道失败: {pipe_name}, 错误: {e}", extra={"log_type": "SYSTEM"}
                    )

            # 清理就绪信号文件
            try:
                root = get_root()
                signal_file = root / "logs" / "data_process_ready.signal"
                if signal_file.exists():
                    signal_file.unlink()
                    stage_log("✅ 就绪信号文件已清理", scenario=DATA_PROCESS_SCENARIO, stacklevel=4)
            except Exception as e:
                logger.warning(f"⚠️ 清理就绪信号文件失败: {e}", extra={"log_type": "SYSTEM"})

            stage_log("✅ 数据进程清理完成", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)

        except Exception as e:
            logger.error(f"❌ 数据进程清理失败: {e}", exc_info=True, extra={"log_type": "ALERT"})


async def main():
    """主函数"""
    # 获取日志队列（从环境变量或命令行参数）
    log_queue = None
    env_queue = load_queue_from_env()
    if env_queue is not None:
        log_queue = env_queue
        stage_log("✅ 通过环境变量获取日志队列", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)
    if len(sys.argv) > 1:
        # 从命令行参数获取队列（序列化后的队列对象）
        # 注意：multiprocessing.Queue不能直接序列化，需要通过其他方式传递
        pass

    # 如果提供了日志队列，配置子进程日志
    if log_queue:
        try:
            setup_subprocess_logging(log_queue)
            stage_log("✅ 子进程日志配置完成", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)
        except Exception as e:
            logger.warning(f"⚠️ 子进程日志配置失败: {e}", extra={"log_type": "SYSTEM"})

    ensure_parent_watchdog(
        label="data_process",
        logger=logger,
        check_interval=5.0,
    )

    # 创建并运行数据进程
    data_process = DataProcess(log_queue=log_queue)
    await data_process.run()


if __name__ == "__main__":
    # 轻量降级日志（在统一日志系统初始化前），避免basicConfig破坏托管
    try:
        stream_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(stream_handler)
    except Exception:
        pass

    # 运行主函数
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stage_log("📍 数据进程已退出", scenario=DATA_PROCESS_SCENARIO, stacklevel=3)
    except Exception as e:
        logger.error(f"❌ 数据进程启动失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
        sys.exit(1)


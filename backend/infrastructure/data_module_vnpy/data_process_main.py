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
from typing import Any, Dict, Optional

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
logger = logging.getLogger("data_process")
logger_rpc = logging.getLogger("data_process.rpc")


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

        # 管道连接状态跟踪（避免频繁尝试读取未连接的管道）
        self._pipe_connected: Dict[str, bool] = {}  # {pipe_name: is_connected}
        self._pipe_last_attempt: Dict[str, float] = {}  # {pipe_name: last_attempt_time}

    async def initialize(self):
        """初始化数据服务"""
        try:
            logger.info("📍 数据进程初始化开始", extra={"log_type": "STAGE_NODE"})

            # 1. 初始化数据服务
            await self._initialize_data_services()

            # 2. 初始化IPC服务器
            await self._initialize_ipc_server()

            # 3. 标记就绪
            self._is_ready = True
            self._write_ready_signal()

            logger.info("✅ 数据进程初始化完成", extra={"log_type": "STAGE_NODE"})

        except Exception as e:
            logger.error(f"❌ 数据进程初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            raise

    async def _initialize_data_services(self):
        """初始化数据服务"""
        try:
            logger.info("│ ⏳ 初始化ChinaStockEngine...", extra={"log_type": "STAGE_NODE"})

            # 创建EventEngine（数据进程内部使用）
            from vnpy.event import EventEngine

            event_engine = EventEngine(interval=1)
            event_engine.start()

            # 初始化ChinaStockEngine（数据进程中没有main_engine，使用None）
            from backend.infrastructure.data_module_vnpy.core_engine import ChinaStockEngine

            # 在数据进程中，main_engine为None（因为MainEngine在主进程）
            # ChinaStockEngine需要兼容这种情况
            self.china_stock_engine = ChinaStockEngine(main_engine=None, event_engine=event_engine)
            # initialize()返回bool，不是协程
            success = self.china_stock_engine.initialize()
            if not success:
                raise RuntimeError("ChinaStockEngine初始化失败")

            logger.info("│ ✅ ChinaStockEngine初始化完成", extra={"log_type": "STAGE_NODE"})

            # 初始化UnifiedDataManager
            logger.info("│ ⏳ 初始化UnifiedDataManager...", extra={"log_type": "STAGE_NODE"})
            from backend.infrastructure.data_module_vnpy.data_runtime import UnifiedDataManager

            self.unified_data_manager = UnifiedDataManager(event_engine=event_engine)
            logger.info("│ ✅ UnifiedDataManager初始化完成", extra={"log_type": "STAGE_NODE"})

            # 初始化LoadBalancer
            logger.info("│ ⏳ 初始化LoadBalancer...", extra={"log_type": "STAGE_NODE"})
            from backend.infrastructure.data_module_vnpy.load_balancer import LoadBalancer

            # LoadBalancer需要config_manager，从ChinaStockEngine获取
            config_manager = self.china_stock_engine.config_manager
            self.load_balancer = LoadBalancer(config_manager=config_manager)
            logger.info("│ ✅ LoadBalancer初始化完成", extra={"log_type": "STAGE_NODE"})

            # 初始化ServerPoolManager
            logger.info("│ ⏳ 初始化ServerPoolManager...", extra={"log_type": "STAGE_NODE"})
            from backend.infrastructure.data_module_vnpy.load_balancer import (
                get_server_pool_manager,
            )

            self.server_pool_manager = get_server_pool_manager()
            logger.info("│ ✅ ServerPoolManager初始化完成", extra={"log_type": "STAGE_NODE"})

        except Exception as e:
            logger.error(f"❌ 数据服务初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            raise

    async def _initialize_ipc_server(self):
        """初始化IPC服务器"""
        if not NATIVE_IPC_AVAILABLE:
            logger.warning("⚠️ native_ipc不可用，将使用降级方案", extra={"log_type": "SYSTEM"})
            return

        try:
            logger.info("│ ⏳ 初始化IPC服务器...", extra={"log_type": "STAGE_NODE"})

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
                    pipe = await AsyncIPCPipe.server(pipe_name)
                    self._ipc_pipes[pipe_name] = pipe
                    # 初始化连接状态跟踪
                    self._pipe_connected[pipe_name] = False
                    self._pipe_last_attempt[pipe_name] = 0
                    logger.info(
                        f"│ ✅ IPC管道已创建: {pipe_name}", extra={"log_type": "STAGE_NODE"}
                    )
                except Exception as e:
                    logger.error(
                        f"❌ 创建IPC管道失败: {pipe_name}, 错误: {e}",
                        exc_info=True,
                        extra={"log_type": "ALERT"},
                    )

            # 启动RPC服务器任务
            asyncio.create_task(self._rpc_server_task())

            logger.info("│ ✅ IPC服务器初始化完成", extra={"log_type": "STAGE_NODE"})

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
        """处理数据查询请求"""
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

            # 解析请求（request_data是bytes类型，需要先解码）
            try:
                if isinstance(request_data, bytes):
                    request = json.loads(request_data.decode("utf-8"))
                else:
                    request = json.loads(request_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning(f"⚠️ 无效的RPC请求格式: {e}", extra={"log_type": "SYSTEM"})
                return

            # 处理请求
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            try:
                if method == "get_kline_data":
                    result = await self._handle_get_kline_data(params)
                elif method == "get_symbol_list":
                    result = await self._handle_get_symbol_list(params)
                else:
                    result = {"success": False, "message": f"未知方法: {method}"}

                # 发送响应
                response = {"id": request_id, "result": result}
                response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)

            except Exception as e:
                logger.error(
                    f"❌ 处理RPC请求失败: {method}, 错误: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT"},
                )
                # 发送错误响应
                response = {"id": request_id, "error": str(e)}
                response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)

        except Exception as e:
            logger.error(
                f"❌ 处理数据查询请求异常: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

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
                request = json.loads(request_data)
            except json.JSONDecodeError:
                logger.warning("⚠️ 无效的计算任务请求格式", extra={"log_type": "SYSTEM"})
                return

            # 处理请求
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            try:
                if method == "calculate_indicator":
                    result = await self._handle_calculate_indicator(params)
                elif method == "calculate_risk_metrics":
                    result = await self._handle_calculate_risk_metrics(params)
                else:
                    result = {"success": False, "message": f"未知方法: {method}"}

                # 发送响应
                response = {"id": request_id, "result": result}
                response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)

            except Exception as e:
                logger.error(
                    f"❌ 处理计算任务请求失败: {method}, 错误: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT"},
                )
                # 发送错误响应
                response = {"id": request_id, "error": str(e)}
                response_data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                await pipe.write(response_data)

        except Exception as e:
            logger.error(
                f"❌ 处理计算任务请求异常: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

    async def _handle_get_kline_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """处理获取K线数据请求"""
        try:
            if not self.unified_data_manager:
                return {"success": False, "message": "UnifiedDataManager未初始化"}

            symbol = params.get("symbol")
            interval = params.get("interval", "1d")
            start_date = params.get("start_date")
            end_date = params.get("end_date")
            check_gaps = params.get("check_gaps", False)

            df = self.unified_data_manager.get_kline_data(
                symbol=symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
                use_preload=True,
            )

            if df is not None and not df.empty:
                # 转换为字典格式
                data = []
                for idx, row in df.iterrows():
                    data.append(
                        {
                            "datetime": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                            "open": float(row.get("open", 0)),
                            "high": float(row.get("high", 0)),
                            "low": float(row.get("low", 0)),
                            "close": float(row.get("close", 0)),
                            "volume": float(row.get("volume", 0)),
                        }
                    )

                return {"success": True, "data": data, "message": f"获取 {len(data)} 条数据"}
            else:
                return {"success": False, "message": "数据为空"}

        except Exception as e:
            logger.error(f"❌ 获取K线数据失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            return {"success": False, "message": str(e)}

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
        """执行技术指标计算（在线程池中执行）"""
        try:
            import talib
            import numpy as np

            data = params.get("data", [])
            indicator_name = params.get("indicator_name")
            indicator_params = params.get("params", {})

            if not data:
                return {"success": False, "message": "数据为空"}

            # 转换为numpy数组
            closes = np.array([float(d.get("close", 0)) for d in data])

            # 计算技术指标
            if indicator_name == "SMA":
                period = indicator_params.get("period", 5)
                result = talib.SMA(closes, timeperiod=period)
            elif indicator_name == "EMA":
                period = indicator_params.get("period", 5)
                result = talib.EMA(closes, timeperiod=period)
            elif indicator_name == "MACD":
                fast = indicator_params.get("fast", 12)
                slow = indicator_params.get("slow", 26)
                signal = indicator_params.get("signal", 9)
                macd, signal_line, hist = talib.MACD(
                    closes, fastperiod=fast, slowperiod=slow, signalperiod=signal
                )
                result = {
                    "macd": macd.tolist(),
                    "signal": signal_line.tolist(),
                    "hist": hist.tolist(),
                }
            elif indicator_name == "RSI":
                period = indicator_params.get("period", 14)
                result = talib.RSI(closes, timeperiod=period)
            else:
                return {"success": False, "message": f"未知指标: {indicator_name}"}

            # 转换为列表
            if isinstance(result, dict):
                result_list = {
                    k: v.tolist() if hasattr(v, "tolist") else v for k, v in result.items()
                }
            else:
                result_list = result.tolist() if hasattr(result, "tolist") else result

            return {"success": True, "data": result_list, "message": f"计算 {indicator_name} 完成"}

        except ImportError:
            return {"success": False, "message": "talib未安装"}
        except Exception as e:
            logger.error(
                f"❌ 执行技术指标计算失败: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )
            return {"success": False, "message": str(e)}

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

            # 计算波动率（年化）
            volatility = np.std(returns) * np.sqrt(252)  # 假设252个交易日

            # 计算VaR（Value at Risk）
            var_percentile = (1 - confidence_level) * 100
            var_value = np.percentile(returns, var_percentile)
            var_amount = abs(var_value * prices[-1])  # 转换为金额

            # 计算CVaR（Conditional VaR，期望损失）
            cvar_returns = returns[returns <= var_value]
            cvar_value = np.mean(cvar_returns) if len(cvar_returns) > 0 else var_value
            cvar_amount = abs(cvar_value * prices[-1])

            # 计算最大回撤
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0.0

            # 计算夏普比率（假设无风险利率为3%）
            risk_free_rate = 0.03
            excess_returns = np.mean(returns) * 252 - risk_free_rate
            sharpe_ratio = excess_returns / volatility if volatility > 0 else 0.0

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
                },
            }

        except ImportError:
            return {"success": False, "message": "numpy未安装"}
        except Exception as e:
            logger.error(
                f"❌ 执行风险指标计算失败: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )
            return {"success": False, "message": str(e)}

    def _write_ready_signal(self):
        """写入就绪信号文件"""
        try:
            root = get_root()
            signal_file = root / "logs" / "data_process_ready.signal"

            # 确保logs目录存在
            signal_file.parent.mkdir(parents=True, exist_ok=True)

            # 写入信号文件
            signal_data = {
                "pid": os.getpid(),
                "timestamp": time.time(),
                "level": 2,  # Level 2: 功能完整
                "pipes": list(self._ipc_pipes.keys()),
            }

            with open(signal_file, "w", encoding="utf-8") as f:
                json.dump(signal_data, f, indent=2)

            logger.info(f"✅ 就绪信号文件已写入: {signal_file}", extra={"log_type": "STAGE_NODE"})

        except Exception as e:
            logger.error(
                f"❌ 写入就绪信号文件失败: {e}", exc_info=True, extra={"log_type": "ALERT"}
            )

    async def run(self):
        """运行数据进程"""
        try:
            # 初始化
            await self.initialize()

            # 保持运行
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("📍 数据进程收到中断信号，正在退出...", extra={"log_type": "STAGE_NODE"})
        except Exception as e:
            logger.error(f"❌ 数据进程运行异常: {e}", exc_info=True, extra={"log_type": "ALERT"})
        finally:
            # 清理资源
            await self.cleanup()

    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("📍 数据进程清理资源...", extra={"log_type": "STAGE_NODE"})

            # 关闭IPC管道
            for pipe_name, pipe in self._ipc_pipes.items():
                try:
                    await pipe.close()
                    logger.info(f"✅ IPC管道已关闭: {pipe_name}", extra={"log_type": "STAGE_NODE"})
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
                    logger.info("✅ 就绪信号文件已清理", extra={"log_type": "STAGE_NODE"})
            except Exception as e:
                logger.warning(f"⚠️ 清理就绪信号文件失败: {e}", extra={"log_type": "SYSTEM"})

            logger.info("✅ 数据进程清理完成", extra={"log_type": "STAGE_NODE"})

        except Exception as e:
            logger.error(f"❌ 数据进程清理失败: {e}", exc_info=True, extra={"log_type": "ALERT"})


async def main():
    """主函数"""
    # 获取日志队列（从环境变量或命令行参数）
    log_queue = None
    if len(sys.argv) > 1:
        # 从命令行参数获取队列（序列化后的队列对象）
        # 注意：multiprocessing.Queue不能直接序列化，需要通过其他方式传递
        pass

    # 如果提供了日志队列，配置子进程日志
    if log_queue:
        try:
            from backend.infrastructure.system_vnpy.logging_system import setup_subprocess_logging

            setup_subprocess_logging(log_queue)
            logger.info("✅ 子进程日志配置完成", extra={"log_type": "STAGE_NODE"})
        except Exception as e:
            logger.warning(f"⚠️ 子进程日志配置失败: {e}", extra={"log_type": "SYSTEM"})

    # 创建并运行数据进程
    data_process = DataProcess(log_queue=log_queue)
    await data_process.run()


if __name__ == "__main__":
    # 设置基本日志（在日志系统初始化前）
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 运行主函数
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("📍 数据进程已退出", extra={"log_type": "STAGE_NODE"})
    except Exception as e:
        logger.error(f"❌ 数据进程启动失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
        sys.exit(1)

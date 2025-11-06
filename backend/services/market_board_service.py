# -*- coding: utf-8 -*-
"""
行情看板服务（重构版）.

职责简化：
- 技术指标计算（talib集成）
- 历史数据查询代理（直接调用data_module_vnpy）

职责移除：
- 断点检测 → data_module_vnpy统一数据管理器负责
- 数据融合 → data_module_vnpy统一数据管理器负责
- 数据录制 → 数据中心模块负责
"""

from typing import Any, Dict, List, Optional
import logging

from backend.core.service_base import BaseService

# 专用logger - 日志埋点v4.0
logger_alert = logging.getLogger("backend.market.alert")


class MarketBoardService(BaseService):
    """行情看板服务（重构版）.

    核心职责：
    1. 技术指标计算（talib库支持）
    2. 历史数据查询代理（直接调用data_module_vnpy）

    移除职责（交由其他模块负责）：
    - 断点检测 → data_module_vnpy
    - 数据融合 → data_module_vnpy
    - 数据录制 → 数据中心模块
    """

    def __init__(self):
        """初始化行情看板服务."""
        super().__init__()

        # 技术指标库
        self.talib = None

        # data_module_vnpy统一数据管理器
        self.unified_data_manager = None

        self.logger.info("行情看板服务已创建（重构版）")

    def _do_initialize(self) -> bool:
        """初始化行情看板服务."""
        try:
            self.logger.info("正在初始化行情看板服务（重构版）...")

            # 初始化技术指标库
            self._init_talib()

            # 获取data_module_vnpy统一数据管理器
            self._init_unified_data_manager()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _init_unified_data_manager(self):
        """初始化data_module_vnpy统一数据管理器."""
        try:
            # 在三进程架构中，通过RPC客户端访问数据进程
            from backend.infrastructure.data_module_vnpy.data_process_client import (
                get_data_process_client,
            )

            self.data_client = get_data_process_client()

            # 连接数据进程（延迟到首次使用时连接）
            # self.data_client.connect()  # 延迟连接，避免启动时阻塞

            self.logger.info("✅ 已初始化数据进程RPC客户端")

        except Exception as e:
            self.logger.error(
                "初始化数据进程客户端失败：%s", e, exc_info=True, extra={"log_type": "SYSTEM"}
            )
            self.data_client = None

    def _do_shutdown(self) -> bool:
        """关闭行情看板服务."""
        try:
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "talib_available": self.talib is not None,
            "data_client_available": self.data_client is not None
            and self.data_client.is_connected(),
        }

    def _init_talib(self):
        """初始化talib技术指标库."""
        try:
            import talib

            self.talib = talib
            self.logger.info("✅ talib技术指标库可用")
        except ImportError:
            self.talib = None
            self.logger.warning("⚠️ talib技术指标库不可用", extra={"log_type": "SYSTEM"})

    # ==================== 行情数据查询 ====================

    def query_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
        check_gaps: bool = False,
    ) -> Dict[str, Any]:
        """查询历史行情数据（重构版：直接调用data_module_vnpy）.

        Args:
            symbol: 品种代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 周期
            check_gaps: 是否检测数据断点（由data_module_vnpy负责）

        Returns:
            Dict: 历史数据，包含：
                - success: bool
                - data: List[Dict]
                - message: str
        """
        try:
            # 优先使用数据进程RPC客户端
            if self.data_client:
                try:
                    # 通过RPC调用数据进程的get_kline_data方法
                    result = self.data_client.call(
                        "get_kline_data",
                        symbol=symbol,
                        interval=interval,
                        start_date=start_date,
                        end_date=end_date,
                        check_gaps=check_gaps,
                        use_preload=True,
                    )

                    if result and isinstance(result, dict):
                        if result.get("success", False):
                            return result
                        else:
                            self.logger.warning(
                                f"数据进程返回失败: {result.get('message', '未知错误')}"
                            )
                    else:
                        # 如果返回的是DataFrame格式（兼容旧格式）
                        import pandas as pd

                        if isinstance(result, pd.DataFrame) and not result.empty:
                            # 将DataFrame转换为Dict格式
                            data = []
                            for idx, row in result.iterrows():
                                data.append(
                                    {
                                        "datetime": (
                                            idx.isoformat()
                                            if isinstance(idx, pd.Timestamp)
                                            else str(idx)
                                        ),
                                        "open": float(row.get("open", 0)),
                                        "high": float(row.get("high", 0)),
                                        "low": float(row.get("low", 0)),
                                        "close": float(row.get("close", 0)),
                                        "volume": float(row.get("volume", 0)),
                                    }
                                )

                            return {
                                "success": True,
                                "data": data,
                                "message": f"从数据进程获取 {len(data)} 条数据",
                            }

                except Exception as e:
                    self.logger.warning(
                        "从数据进程查询失败：%s，尝试使用DataCenterService",
                        e,
                        extra={"log_type": "SYSTEM"},
                    )

            # 备用方案：使用DataCenterService
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            data_center_service = service_manager.get_service("data_center_service")

            if not data_center_service:
                return {
                    "success": False,
                    "message": "DataCenterService不可用",
                    "data": [],
                }

            # 调用DataCenterService的查询方法
            result = data_center_service.query_local_data(
                symbol=symbol, start_date=start_date, end_date=end_date, interval=interval
            )

            return result

        except Exception as e:
            self._log_error("查询历史数据", e)
            return {"success": False, "message": str(e), "data": []}

    # ==================== 技术指标计算 ====================

    def calculate_indicator(
        self, data: List[float], indicator_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """计算技术指标.

        Args:
            data: 价格数据
            indicator_name: 指标名称（如：SMA, EMA, MACD等）
            params: 指标参数

        Returns:
            Dict: 指标计算结果
        """
        try:
            if self.talib is None:
                return {
                    "success": False,
                    "message": "talib不可用",
                    "data": [],
                }

            # 转换数据为numpy数组
            import numpy as np

            price_array = np.array(data, dtype=float)

            if len(price_array) == 0:
                return {
                    "success": False,
                    "message": "数据为空",
                    "data": [],
                }

            # 根据指标名称调用对应的talib函数
            params = params or {}

            if indicator_name.upper() == "SMA":
                timeperiod = params.get("timeperiod", 20)
                result = self.talib.SMA(price_array, timeperiod=timeperiod)

            elif indicator_name.upper() == "EMA":
                timeperiod = params.get("timeperiod", 20)
                result = self.talib.EMA(price_array, timeperiod=timeperiod)

            elif indicator_name.upper() == "MA":
                timeperiod = params.get("timeperiod", 20)
                result = self.talib.MA(price_array, timeperiod=timeperiod)

            elif indicator_name.upper() == "BBANDS":
                timeperiod = params.get("timeperiod", 20)
                nbdevup = params.get("nbdevup", 2)
                nbdevdn = params.get("nbdevdn", 2)
                upper, middle, lower = self.talib.BBANDS(
                    price_array, timeperiod=timeperiod, nbdevup=nbdevup, nbdevdn=nbdevdn
                )
                result = {
                    "upper": upper.tolist(),
                    "middle": middle.tolist(),
                    "lower": lower.tolist(),
                }

            elif indicator_name.upper() == "MACD":
                fastperiod = params.get("fastperiod", 12)
                slowperiod = params.get("slowperiod", 26)
                signalperiod = params.get("signalperiod", 9)
                macd, signal, hist = self.talib.MACD(
                    price_array,
                    fastperiod=fastperiod,
                    slowperiod=slowperiod,
                    signalperiod=signalperiod,
                )
                result = {"macd": macd.tolist(), "signal": signal.tolist(), "hist": hist.tolist()}

            elif indicator_name.upper() == "RSI":
                timeperiod = params.get("timeperiod", 14)
                result = self.talib.RSI(price_array, timeperiod=timeperiod)

            elif indicator_name.upper() == "KDJ":
                # KDJ需要高低收三个价格
                # 这里简化处理，仅计算STOCH
                fastk_period = params.get("fastk_period", 9)
                slowk_period = params.get("slowk_period", 3)
                slowd_period = params.get("slowd_period", 3)
                slowk, slowd = self.talib.STOCH(
                    price_array,
                    price_array,
                    price_array,
                    fastk_period=fastk_period,
                    slowk_period=slowk_period,
                    slowd_period=slowd_period,
                )
                result = {"k": slowk.tolist(), "d": slowd.tolist()}

            else:
                return {
                    "success": False,
                    "message": f"不支持的指标: {indicator_name}",
                    "data": [],
                }

            # 转换为列表格式
            if isinstance(result, np.ndarray):
                result = result.tolist()

            return {
                "success": True,
                "indicator": indicator_name,
                "data": result,
                "params": params,
            }

        except Exception as e:
            self._log_error("计算技术指标", e)
            return {"success": False, "message": str(e), "data": []}

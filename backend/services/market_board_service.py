# -*- coding: utf-8 -*-
"""
行情看板服务.

提供行情数据和技术分析功能，包括：
- 行情数据供应（历史数据、实时数据、数据录制、断点检测）
- 技术指标计算（talib集成）
- 图表数据准备（多周期K线、品种叠加）
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_service import BaseService


class MarketBoardService(BaseService):
    """行情看板服务.

    提供专业的行情分析功能，支持：
    1. 多周期K线（日线、5min、1min及合成周期）
    2. 实时行情（Tick、分时）
    3. 技术指标（talib库支持）
    4. 品种叠加、指标叠加
    5. 数据录制和断点检测
    """

    def __init__(self):
        """初始化行情看板服务."""
        super().__init__()

        # 当前订阅的品种
        self.subscribed_symbols: List[str] = []

        # 实时数据缓存
        self.realtime_data_cache: Dict[str, Any] = {}

        # 数据录制状态
        self.recording_enabled = False

        self.logger.info("行情看板服务已创建")

    def _do_initialize(self) -> bool:
        """初始化行情看板服务."""
        try:
            self.logger.info("初始化行情看板服务...")

            # 初始化技术指标库
            self._init_talib()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭行情看板服务."""
        try:
            # 停止数据录制
            self.stop_recording()

            # 取消所有订阅
            self.unsubscribe_all()

            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "subscribed_symbol_count": len(self.subscribed_symbols),
            "recording_enabled": self.recording_enabled,
            "cache_size": len(self.realtime_data_cache),
        }

    def _init_talib(self):
        """初始化talib技术指标库."""
        try:
            import talib

            self.talib = talib
            self.logger.info("✅ talib技术指标库可用")
        except ImportError:
            self.talib = None
            self.logger.warning("⚠️ talib技术指标库不可用")

    # ==================== 行情数据查询 ====================

    def query_historical_data(
        self, symbol: str, start_date: str, end_date: str, interval: str = "1d"
    ) -> Dict[str, Any]:
        """查询历史行情数据.

        Args:
            symbol: 品种代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 周期

        Returns:
            Dict: 历史数据
        """
        try:
            # 从DataCenterService查询历史数据
            from backend.core.shared_services import get_service_manager

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

    def subscribe_realtime_data(self, symbol: str) -> Dict[str, Any]:
        """订阅实时行情.

        Args:
            symbol: 品种代码

        Returns:
            Dict: 操作结果
        """
        try:
            if symbol in self.subscribed_symbols:
                return {"success": True, "message": "已订阅"}

            # 调用main_engine订阅实时行情
            if not self.main_engine:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 订阅行情
            try:
                # VNPY的订阅通过网关完成
                # 这里记录订阅，实际订阅在网关连接后自动进行
                self.subscribed_symbols.append(symbol)

                self.logger.info(f"已订阅实时行情: {symbol}")

                # TODO: 如果有活跃的网关，向网关订阅
                # 这需要知道symbol对应的exchange和gateway

            except Exception as e:
                self.logger.error(f"订阅失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"订阅失败: {str(e)}",
                }

            return {
                "success": True,
                "message": f"已订阅 {symbol}",
            }

        except Exception as e:
            self._log_error("订阅实时数据", e)
            return {"success": False, "message": str(e)}

    def unsubscribe_realtime_data(self, symbol: str) -> Dict[str, Any]:
        """取消订阅实时行情.

        Args:
            symbol: 品种代码

        Returns:
            Dict: 操作结果
        """
        try:
            if symbol in self.subscribed_symbols:
                self.subscribed_symbols.remove(symbol)

            return {
                "success": True,
                "message": f"已取消订阅 {symbol}",
            }

        except Exception as e:
            self._log_error("取消订阅", e)
            return {"success": False, "message": str(e)}

    def unsubscribe_all(self):
        """取消所有订阅."""
        self.subscribed_symbols.clear()

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

            # 计算指标
            params = params or {}
            result_data = None

            try:
                if indicator_name.upper() == "SMA":
                    period = params.get("period", 20)
                    result_data = self.talib.SMA(price_array, timeperiod=period)

                elif indicator_name.upper() == "EMA":
                    period = params.get("period", 20)
                    result_data = self.talib.EMA(price_array, timeperiod=period)

                elif indicator_name.upper() == "MACD":
                    macd, signal, hist = self.talib.MACD(price_array)
                    result_data = {
                        "macd": macd.tolist(),
                        "signal": signal.tolist(),
                        "hist": hist.tolist(),
                    }

                elif indicator_name.upper() == "RSI":
                    period = params.get("period", 14)
                    result_data = self.talib.RSI(price_array, timeperiod=period)

                elif indicator_name.upper() == "BBANDS":
                    period = params.get("period", 20)
                    upper, middle, lower = self.talib.BBANDS(price_array, timeperiod=period)
                    result_data = {
                        "upper": upper.tolist(),
                        "middle": middle.tolist(),
                        "lower": lower.tolist(),
                    }

                else:
                    return {
                        "success": False,
                        "message": f"不支持的指标: {indicator_name}",
                        "data": [],
                    }

                # 转换结果为列表
                if isinstance(result_data, np.ndarray):
                    result_data = result_data.tolist()

                return {
                    "success": True,
                    "indicator": indicator_name,
                    "data": result_data,
                }

            except Exception as e:
                self.logger.error(f"指标计算失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"计算失败: {str(e)}",
                    "data": [],
                }

        except Exception as e:
            self._log_error("计算技术指标", e)
            return {"success": False, "message": str(e), "data": []}

    # ==================== 数据录制 ====================

    def start_recording(self) -> Dict[str, Any]:
        """启动数据录制.

        Returns:
            Dict: 操作结果
        """
        try:
            # TODO: 调用vnpy_datarecorder

            self.recording_enabled = True

            return {
                "success": True,
                "message": "数据录制已启动",
            }

        except Exception as e:
            self._log_error("启动录制", e)
            return {"success": False, "message": str(e)}

    def stop_recording(self) -> Dict[str, Any]:
        """停止数据录制.

        Returns:
            Dict: 操作结果
        """
        try:
            self.recording_enabled = False

            return {
                "success": True,
                "message": "数据录制已停止",
            }

        except Exception as e:
            self._log_error("停止录制", e)
            return {"success": False, "message": str(e)}

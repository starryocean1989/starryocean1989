# -*- coding: utf-8 -*-
"""
服务层基础模块 - 合并版本.

整合了以下模块：
- base_service: 基础服务类
- data_conversion: 数据转换工具

提供统一的服务基础设施和数据转换功能。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Union
from datetime import datetime
from enum import Enum

from backend.core.models import (
    UnifiedMarketData,
    UnifiedOrder,
    UnifiedTrade,
    UnifiedPosition,
    UnifiedAccount,
    DataMetadata,
    DataCategory,
    DataSource,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Part 1: 服务基类 (来自 base_service.py)
# =============================================================================


class ServiceStatus(Enum):
    """服务状态枚举."""

    STOPPED = "stopped"  # 未启动
    STARTING = "starting"  # 启动中
    RUNNING = "running"  # 运行中
    STOPPING = "stopping"  # 停止中
    ERROR = "error"  # 错误状态


class BaseService(ABC):
    """服务基类.

    所有业务服务的抽象基类，提供：
    - 标准的初始化和关闭接口
    - 健康检查机制
    - 状态管理
    - 日志记录
    - 错误处理
    """

    def __init__(self) -> None:
        """初始化基础服务."""
        self.service_name = self.__class__.__name__
        # 使用子类的模块名而不是BaseService的模块名
        child_module = self.__class__.__module__
        self._logger = logging.getLogger(child_module)
        self.status = ServiceStatus.STOPPED
        self.is_initialized = False
        self.start_time: Optional[datetime] = None
        self._errors: List[str] = []

        # VNPY引擎引用（在_do_initialize中设置）
        self.main_engine = None
        self.event_engine = None

        self.logger.info("服务 %s 创建完成", self.service_name)

    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器.

        Returns:
            logging.Logger: 日志记录器实例
        """
        return self._logger

    def initialize(self) -> bool:
        """初始化服务.

        Returns:
            bool: 是否成功初始化
        """
        try:
            self.status = ServiceStatus.STARTING

            # 阶段感知：启动阶段详细日志
            try:
                from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

                ctx = get_logging_hub()
                if ctx and ctx._routing_engine and ctx._routing_engine.current_stage == "startup":
                    self.logger.info("正在初始化服务: %s", self.service_name)
                else:
                    self.logger.debug("重新初始化服务: %s", self.service_name)
            except ImportError:
                # 如果logging_context未初始化，使用默认INFO级别
                self.logger.info("正在初始化服务: %s", self.service_name)

            # 获取全局VNPY引擎
            from backend.core.base import get_main_engine, get_event_engine

            self.main_engine = get_main_engine()
            self.event_engine = get_event_engine()

            # 调用子类的具体初始化逻辑
            result = self._do_initialize()

            if result:
                self.is_initialized = True
                self.start_time = datetime.now()
                self.status = ServiceStatus.RUNNING
                self.logger.info("服务 %s 初始化成功", self.service_name)
            else:
                self.status = ServiceStatus.ERROR
                self.logger.error("服务 %s 初始化失败", self.service_name)

            return result

        except Exception as e:
            self.status = ServiceStatus.ERROR
            self._errors.append("初始化异常: %s" % str(e))
            self.logger.exception("服务 %s 初始化异常", self.service_name)
            return False

    def shutdown(self) -> bool:
        """关闭服务.

        Returns:
            bool: 是否成功关闭
        """
        try:
            self.status = ServiceStatus.STOPPING
            self.logger.info("正在关闭服务: %s", self.service_name)

            # 调用子类的具体关闭逻辑
            result = self._do_shutdown()

            self.is_initialized = False
            self.status = ServiceStatus.STOPPED
            self.logger.info("服务 %s 关闭完成", self.service_name)

            return result

        except Exception as e:
            self.status = ServiceStatus.ERROR
            self._errors.append("关闭异常: %s" % str(e))
            self.logger.exception("服务 %s 关闭异常", self.service_name)
            return False

    def health_check(self) -> Dict[str, Any]:
        """健康检查.

        Returns:
            Dict: 健康检查结果
        """
        try:
            # 基础健康检查
            is_healthy = (
                self.status == ServiceStatus.RUNNING
                and self.is_initialized
                and len(self._errors) == 0
            )

            # 调用子类的具体健康检查逻辑
            custom_health = self._do_health_check()

            uptime = self._get_uptime()
            error_count = len(self._errors)

            # 记录健康检查日志（P2优化）
            if not is_healthy:
                self.logger.warning(
                    "服务 %s 健康检查异常: 状态=%s, 已初始化=%s, 错误数=%d",
                    self.service_name,
                    self.status.value,
                    self.is_initialized,
                    error_count,
                )
            else:
                self.logger.debug(
                    "服务 %s 健康检查通过: 运行时长=%.2fs, 错误数=%d",
                    self.service_name,
                    uptime if uptime else 0,
                    error_count,
                )

            return {
                "service_name": self.service_name,
                "status": self.status.value,
                "is_healthy": is_healthy,
                "is_initialized": self.is_initialized,
                "uptime": uptime,
                "errors": self._errors[-5:],  # 最近5个错误
                "custom": custom_health,
            }

        except Exception as e:
            self.logger.exception("服务 %s 健康检查失败", self.service_name)
            return {
                "service_name": self.service_name,
                "status": "error",
                "is_healthy": False,
                "error": str(e),
            }

    @abstractmethod
    def _do_initialize(self) -> bool:
        """具体的初始化逻辑（由子类实现）.

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    def _do_shutdown(self) -> bool:
        """具体的关闭逻辑（由子类实现）.

        Returns:
            bool: 是否成功
        """
        pass

    def _do_health_check(self) -> Dict[str, Any]:
        """具体的健康检查逻辑（由子类可选实现）.

        Returns:
            Dict: 自定义健康检查信息
        """
        return {}

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息."""
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "is_initialized": self.is_initialized,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": self._get_uptime(),
            "error_count": len(self._errors),
            "has_main_engine": self.main_engine is not None,
            "has_event_engine": self.event_engine is not None,
        }

    def _get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）."""
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志."""
        details = ", ".join("%s=%s" % (k, v) for k, v in kwargs.items())
        if details:
            self.logger.info("[%s] %s %s", self.service_name, operation, details)
        else:
            self.logger.info("[%s] %s", self.service_name, operation)

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志."""
        error_msg = "%s: %s" % (operation, str(error))
        self._errors.append(error_msg)

        # 限制错误列表大小
        if len(self._errors) > 100:
            self._errors = self._errors[-50:]

        details = ", ".join("%s=%s" % (k, v) for k, v in kwargs.items())
        if details:
            self.logger.exception("[%s] %s 失败 - %s", self.service_name, operation, details)
        else:
            self.logger.exception("[%s] %s 失败", self.service_name, operation)

    def clear_errors(self):
        """清空错误记录."""
        self._errors.clear()

    def get_errors(self, limit: int = 10) -> List[str]:
        """获取最近的错误记录.

        Args:
            limit: 返回的错误数量限制

        Returns:
            List[str]: 错误列表
        """
        return self._errors[-limit:] if self._errors else []


# =============================================================================
# Part 2: 数据转换工具 (来自 data_conversion.py)
# =============================================================================


class DataConverter:
    """数据转换器."""

    @staticmethod
    def vnpy_tick_to_unified(tick: Any) -> Optional[UnifiedMarketData]:
        """将VnPy TickData转换为统一行情数据."""
        try:
            if not tick or not hasattr(tick, "symbol"):
                return None

            return UnifiedMarketData(
                symbol=tick.symbol,
                exchange=getattr(tick, "exchange", ""),
                data_type="tick",
                datetime=getattr(tick, "datetime", datetime.now()),
                timestamp=int(getattr(tick, "datetime", datetime.now()).timestamp()),
                open_price=getattr(tick, "open_price", 0.0),
                high_price=getattr(tick, "high_price", 0.0),
                low_price=getattr(tick, "low_price", 0.0),
                close_price=getattr(tick, "last_price", 0.0),
                pre_close=getattr(tick, "pre_close", 0.0),
                volume=getattr(tick, "volume", 0),
                turnover=getattr(tick, "turnover", 0.0),
                open_interest=getattr(tick, "open_interest", 0),
                bid_price=getattr(tick, "bid_price_1", 0.0),
                bid_volume=getattr(tick, "bid_volume_1", 0),
                ask_price=getattr(tick, "ask_price_1", 0.0),
                ask_volume=getattr(tick, "ask_volume_1", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=tick.symbol,
                    exchange=getattr(tick, "exchange", ""),
                    count=1,
                    last_updated=getattr(tick, "datetime", datetime.now()),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy TickData失败: %s", e)
            return None

    @staticmethod
    def vnpy_bar_to_unified(bar: Any) -> Optional[UnifiedMarketData]:
        """将VnPy BarData转换为统一行情数据."""
        try:
            if not bar or not hasattr(bar, "symbol"):
                return None

            return UnifiedMarketData(
                symbol=bar.symbol,
                exchange=getattr(bar, "exchange", ""),
                data_type="bar",
                datetime=getattr(bar, "datetime", datetime.now()),
                timestamp=int(getattr(bar, "datetime", datetime.now()).timestamp()),
                open_price=getattr(bar, "open_price", 0.0),
                high_price=getattr(bar, "high_price", 0.0),
                low_price=getattr(bar, "low_price", 0.0),
                close_price=getattr(bar, "close_price", 0.0),
                pre_close=0.0,  # BarData中没有pre_close
                volume=getattr(bar, "volume", 0),
                turnover=getattr(bar, "turnover", 0.0),
                open_interest=getattr(bar, "open_interest", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=bar.symbol,
                    exchange=getattr(bar, "exchange", ""),
                    frequency=f"{getattr(bar, 'interval', 1)}m",
                    count=1,
                    last_updated=getattr(bar, "datetime", datetime.now()),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy BarData失败: %s", e)
            return None

    @staticmethod
    def vnpy_order_to_unified(order: Any) -> Optional[UnifiedOrder]:
        """将VnPy OrderData转换为统一订单数据."""
        try:
            if not order or not hasattr(order, "symbol"):
                return None

            return UnifiedOrder(
                order_id=getattr(order, "orderid", ""),
                symbol=order.symbol,
                exchange=getattr(order, "exchange", ""),
                order_type=getattr(order, "type", ""),
                direction=getattr(order, "direction", ""),
                price=getattr(order, "price", 0.0),
                volume=getattr(order, "volume", 0),
                status=getattr(order, "status", ""),
                order_time=DataConverter._parse_time(getattr(order, "time", "")),
                traded_volume=getattr(order, "traded", 0),
                metadata=DataMetadata(
                    DataCategory.TRANSACTION_DATA,
                    DataSource.VNPY,
                    symbol=order.symbol,
                    exchange=getattr(order, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy OrderData失败: %s", e)
            return None

    @staticmethod
    def vnpy_trade_to_unified(trade: Any) -> Optional[UnifiedTrade]:
        """将VnPy TradeData转换为统一成交数据."""
        try:
            if not trade or not hasattr(trade, "symbol"):
                return None

            return UnifiedTrade(
                trade_id=getattr(trade, "tradeid", ""),
                order_id=getattr(trade, "orderid", ""),
                symbol=trade.symbol,
                exchange=getattr(trade, "exchange", ""),
                direction=getattr(trade, "direction", ""),
                price=getattr(trade, "price", 0.0),
                volume=getattr(trade, "volume", 0),
                trade_time=DataConverter._parse_time(getattr(trade, "time", "")),
                metadata=DataMetadata(
                    DataCategory.TRANSACTION_DATA,
                    DataSource.VNPY,
                    symbol=trade.symbol,
                    exchange=getattr(trade, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy TradeData失败: %s", e)
            return None

    @staticmethod
    def vnpy_position_to_unified(position: Any) -> Optional[UnifiedPosition]:
        """将VnPy PositionData转换为统一持仓数据."""
        try:
            if not position or not hasattr(position, "symbol"):
                return None

            volume = getattr(position, "volume", 0)
            frozen = getattr(position, "frozen", 0)
            available = max(0, volume - frozen)

            return UnifiedPosition(
                symbol=position.symbol,
                exchange=getattr(position, "exchange", ""),
                direction=getattr(position, "direction", ""),
                volume=volume,
                frozen_volume=frozen,
                available_volume=available,
                cost_price=getattr(position, "price", 0.0),
                market_price=0.0,  # 需要外部提供
                unrealized_pnl=getattr(position, "pnl", 0.0),
                realized_pnl=0.0,  # 需要外部计算
                metadata=DataMetadata(
                    DataCategory.PORTFOLIO_DATA,
                    DataSource.VNPY,
                    symbol=position.symbol,
                    exchange=getattr(position, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy PositionData失败: %s", e)
            return None

    @staticmethod
    def vnpy_account_to_unified(account: Any) -> Optional[UnifiedAccount]:
        """将VnPy AccountData转换为统一账户数据."""
        try:
            if not account or not hasattr(account, "accountid"):
                return None

            balance = getattr(account, "balance", 0.0)
            available = getattr(account, "available", 0.0)
            frozen = balance - available
            close_profit = getattr(account, "close_profit", 0.0)
            position_profit = getattr(account, "position_profit", 0.0)
            total_profit = close_profit + position_profit

            return UnifiedAccount(
                account_id=account.accountid,
                account_type="future",  # 默认期货账户
                balance=balance,
                available=available,
                frozen=frozen,
                commission=getattr(account, "commission", 0.0),
                margin=getattr(account, "margin", 0.0),
                close_profit=close_profit,
                position_profit=position_profit,
                total_profit=total_profit,
                metadata=DataMetadata(
                    DataCategory.PORTFOLIO_DATA,
                    DataSource.VNPY,
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy AccountData失败: %s", e)
            return None

    @staticmethod
    def unified_to_dict(
        data: Union[
            UnifiedMarketData,
            UnifiedOrder,
            UnifiedTrade,
            UnifiedPosition,
            UnifiedAccount,
        ],
    ) -> Dict[str, Any]:
        """将统一数据模型转换为字典."""
        try:
            if isinstance(data, UnifiedMarketData):
                return data.to_pandas_row()
            elif isinstance(data, (UnifiedOrder, UnifiedTrade, UnifiedPosition, UnifiedAccount)):
                return {
                    key: value for key, value in data.__dict__.items() if not key.startswith("_")
                }
            else:
                return {}

        except Exception as e:
            logger.error("转换统一数据模型为字典失败: %s", e)
            return {}

    @staticmethod
    def batch_convert_vnpy_data(data_list: List[Any], data_type: str) -> List[Dict[str, Any]]:
        """批量转换VnPy数据."""
        try:
            converted_data = []

            for data in data_list:
                unified_data: Any = None

                if data_type == "tick":
                    unified_data = DataConverter.vnpy_tick_to_unified(data)
                elif data_type == "bar":
                    unified_data = DataConverter.vnpy_bar_to_unified(data)
                elif data_type == "order":
                    unified_data = DataConverter.vnpy_order_to_unified(data)
                elif data_type == "trade":
                    unified_data = DataConverter.vnpy_trade_to_unified(data)
                elif data_type == "position":
                    unified_data = DataConverter.vnpy_position_to_unified(data)
                elif data_type == "account":
                    unified_data = DataConverter.vnpy_account_to_unified(data)

                if unified_data:
                    converted_data.append(DataConverter.unified_to_dict(unified_data))

            return converted_data

        except Exception as e:
            logger.error("批量转换VnPy数据失败: %s", e)
            return []

    @staticmethod
    def _parse_time(time_str: str) -> datetime:
        """解析时间字符串."""
        try:
            if not time_str:
                return datetime.now()

            # 尝试不同的时间格式
            time_formats = [
                "%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
            ]

            for fmt in time_formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue

            # 如果都失败，返回当前时间
            return datetime.now()

        except Exception as e:
            logger.error("解析时间字符串失败: %s - %s", time_str, e)
            return datetime.now()

    @staticmethod
    def validate_data_quality(data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """验证数据质量."""
        try:
            quality_score = 1.0
            issues = []

            if data_type == "market_data":
                # 验证行情数据质量
                required_fields = ["symbol", "datetime", "close_price"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

                # 验证价格合理性
                if "close_price" in data and data["close_price"] <= 0:
                    issues.append("价格数据异常")
                    quality_score -= 0.3

            elif data_type == "order":
                # 验证订单数据质量
                required_fields = ["order_id", "symbol", "price", "volume"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

            elif data_type == "trade":
                # 验证成交数据质量
                required_fields = ["trade_id", "symbol", "price", "volume"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

            # 确保质量分数在0-1之间
            quality_score = max(0.0, min(1.0, quality_score))

            return {
                "quality_score": quality_score,
                "issues": issues,
                "is_valid": quality_score >= 0.7,
            }

        except Exception as e:
            logger.error("验证数据质量失败: %s", e)
            return {
                "quality_score": 0.0,
                "issues": [f"验证过程出错: {e}"],
                "is_valid": False,
            }


# =============================================================================
# Part 3: LoggerMixin (从logging_alert.py迁移)
# =============================================================================


class LoggerMixin:
    """日志记录器混入类.

    为类提供标准化的日志记录功能，包括：
    - 自动创建命名日志记录器
    - 标准化的日志输出方法
    - 上下文信息传递
    - 性能日志记录

    使用方法:
        class MyService(LoggerMixin):
            def __init__(self):
                super().__init__()
                self.logger.info("服务已创建")
    """

    def __init__(self):
        """初始化日志记录器混入."""
        # 创建以类名命名的日志记录器
        self._logger = logging.getLogger(self.__class__.__name__)

    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器.

        Returns:
            日志记录器实例
        """
        return self._logger

    def log_with_context(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> None:
        """记录带上下文信息的日志.

        Args:
            level: 日志级别（logging.DEBUG, INFO, WARNING, ERROR, CRITICAL）
            message: 日志消息
            extra: 额外的上下文信息
            exc_info: 是否包含异常信息
        """
        log_extra = extra or {}
        self._logger.log(level, message, extra=log_extra, exc_info=exc_info)

    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录性能日志.

        Args:
            operation: 操作名称
            duration_ms: 操作耗时（毫秒）
            success: 操作是否成功
            extra: 额外的上下文信息
        """
        log_extra = extra or {}
        log_extra.update(
            {
                "operation": operation,
                "duration_ms": duration_ms,
                "success": success,
            }
        )

        if success:
            self._logger.debug(
                "[性能] %s 完成，耗时: %.2fms", operation, duration_ms, extra=log_extra
            )
        else:
            self._logger.warning(
                "[性能] %s 失败，耗时: %.2fms", operation, duration_ms, extra=log_extra
            )

    def log_operation_start(self, operation: str, **kwargs) -> None:
        """记录操作开始日志.

        Args:
            operation: 操作名称
            **kwargs: 操作参数
        """
        params_str = ", ".join(["%s=%s" % (k, v) for k, v in kwargs.items()])
        if params_str:
            self._logger.info("[开始] %s (%s)", operation, params_str)
        else:
            self._logger.info("[开始] %s", operation)

    def log_operation_success(self, operation: str, **kwargs) -> None:
        """记录操作成功日志.

        Args:
            operation: 操作名称
            **kwargs: 结果信息
        """
        result_str = ", ".join(["%s=%s" % (k, v) for k, v in kwargs.items()])
        if result_str:
            self._logger.info("[成功] %s (%s)", operation, result_str)
        else:
            self._logger.info("[成功] %s", operation)

    def log_operation_failure(self, operation: str, error: Exception, **kwargs) -> None:
        """记录操作失败日志.

        Args:
            operation: 操作名称
            error: 错误异常
            **kwargs: 错误上下文
        """
        context_str = ", ".join(["%s=%s" % (k, v) for k, v in kwargs.items()])
        if context_str:
            self._logger.exception("[失败] %s: %s (%s)", operation, str(error), context_str)
        else:
            self._logger.exception("[失败] %s: %s", operation, str(error))


# =============================================================================
# 导出的公共接口
# =============================================================================

__all__ = [
    # 服务基类
    "BaseService",
    "ServiceStatus",
    # 数据转换
    "DataConverter",
    # 日志混入
    "LoggerMixin",
]

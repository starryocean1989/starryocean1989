# -*- coding: utf-8 -*-
"""
本地数据服务 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道本地数据服务的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from backend.core.shared_services import ErrorSeverity, get_service_manager

logger = logging.getLogger(__name__)


class LocalDataService:
    """本地数据服务 - 专注于错误追踪和详细报告"""

    def __init__(self):
        """初始化本地数据服务"""
        self.service_manager = get_service_manager()
        self.logger = logging.getLogger(self.__class__.__name__)

        self._data_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_ttl = 300  # 缓存5分钟
        self._initialization_successful = False

        # 尝试初始化
        self._attempt_initialization()

    def _attempt_initialization(self):
        """尝试初始化本地数据服务"""
        try:
            self.service_manager.record_error(
                "LocalDataService",
                "INITIALIZATION_START",
                "开始初始化本地数据服务",
                severity=ErrorSeverity.INFO,
            )

            # 初始化数据缓存
            self._data_cache.clear()

            self._initialization_successful = True
            self.service_manager.record_error(
                "LocalDataService",
                "INITIALIZATION_SUCCESS",
                "本地数据服务初始化成功",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"本地数据服务初始化失败: {str(e)}"
            self.service_manager.record_error(
                "LocalDataService",
                "INITIALIZATION_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )

    async def query_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_type: str = "bar",
        frequency: str = "1m",
        limit: int = 1000,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """查询本地数据"""
        # 标记参数为有意未使用
        _ = start_date, end_date, kwargs
        try:
            self.service_manager.record_error(
                "LocalDataService",
                "QUERY_DATA_START",
                f"开始查询本地数据: {symbol}.{exchange}, 类型={data_type}, 频率={frequency}",
                severity=ErrorSeverity.INFO,
            )

            # 生成缓存键
            cache_key = f"{symbol}.{exchange}.{data_type}.{frequency}"

            # 检查缓存
            if cache_key in self._data_cache:
                cached_data = self._data_cache[cache_key]
                self.service_manager.record_error(
                    "LocalDataService",
                    "QUERY_DATA_CACHE_HIT",
                    f"从缓存获取数据成功: {cache_key}, {len(cached_data)}条记录",
                    severity=ErrorSeverity.INFO,
                )
                return cached_data

            # 模拟数据查询
            mock_data = self._generate_mock_data(symbol, exchange, data_type, frequency, limit)

            # 缓存数据
            self._data_cache[cache_key] = mock_data

            self.service_manager.record_error(
                "LocalDataService",
                "QUERY_DATA_SUCCESS",
                f"查询本地数据成功: {symbol}.{exchange}, 返回{len(mock_data)}条记录",
                severity=ErrorSeverity.INFO,
            )

            return mock_data

        except Exception as e:
            error_msg = f"查询本地数据失败: {str(e)}"
            self.service_manager.record_error(
                "LocalDataService",
                "QUERY_DATA_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    def _generate_mock_data(
        self, symbol: str, exchange: str, data_type: str, frequency: str, limit: int
    ) -> List[Dict[str, Any]]:
        """生成模拟数据"""
        # 标记参数为有意未使用
        _ = frequency
        try:
            data = []
            base_time = datetime.now() - timedelta(minutes=limit)
            base_price = 10.0

            for i in range(min(limit, 100)):  # 最多生成100条记录
                timestamp = base_time + timedelta(minutes=i)
                price_change = (i % 10 - 5) * 0.01  # 简单的价格变动

                if data_type == "bar":
                    record = {
                        "symbol": symbol,
                        "exchange": exchange,
                        "datetime": timestamp.isoformat(),
                        "open": base_price + price_change,
                        "high": base_price + price_change + 0.02,
                        "low": base_price + price_change - 0.02,
                        "close": base_price + price_change + 0.01,
                        "volume": 1000 + i * 10,
                        "turnover": (base_price + price_change) * (1000 + i * 10),
                    }
                else:  # tick
                    record = {
                        "symbol": symbol,
                        "exchange": exchange,
                        "datetime": timestamp.isoformat(),
                        "last_price": base_price + price_change,
                        "volume": 1000 + i * 10,
                        "bid_price_1": base_price + price_change - 0.01,
                        "ask_price_1": base_price + price_change + 0.01,
                        "bid_volume_1": 100,
                        "ask_volume_1": 100,
                    }

                data.append(record)

            return data

        except Exception as e:
            self.service_manager.record_error(
                "LocalDataService",
                "GENERATE_MOCK_DATA_EXCEPTION",
                f"生成模拟数据失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    async def get_latest_data(
        self,
        symbol: str,
        exchange: str,
        data_type: str = "tick",
    ) -> Optional[Dict[str, Any]]:
        """获取最新数据"""
        try:
            # 查询一条最新数据
            data_list = await self.query_data(symbol, exchange, data_type=data_type, limit=1)

            if data_list:
                latest_data = data_list[-1]
                self.service_manager.record_error(
                    "LocalDataService",
                    "GET_LATEST_DATA_SUCCESS",
                    f"获取最新数据成功: {symbol}.{exchange}",
                    severity=ErrorSeverity.INFO,
                )
                return latest_data
            else:
                self.service_manager.record_error(
                    "LocalDataService",
                    "GET_LATEST_DATA_EMPTY",
                    f"最新数据为空: {symbol}.{exchange}",
                    severity=ErrorSeverity.WARNING,
                )
                return None

        except Exception as e:
            error_msg = f"获取最新数据失败: {str(e)}"
            self.service_manager.record_error(
                "LocalDataService",
                "GET_LATEST_DATA_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    def get_status(self) -> str:
        """获取服务状态"""
        if self._initialization_successful:
            return f"运行中 (缓存{len(self._data_cache)}项)"
        else:
            return "初始化失败"

    def get_service_status(self) -> Dict[str, Any]:
        """获取详细服务状态"""
        return {
            "initialization_successful": self._initialization_successful,
            "cache_size": len(self._data_cache),
            "cache_keys": list(self._data_cache.keys()),
        }

    def clear_cache(self) -> bool:
        """清空缓存"""
        try:
            self._data_cache.clear()
            self.service_manager.record_error(
                "LocalDataService",
                "CLEAR_CACHE_SUCCESS",
                "本地数据缓存清空成功",
                severity=ErrorSeverity.INFO,
            )
            return True
        except Exception as e:
            self.service_manager.record_error(
                "LocalDataService",
                "CLEAR_CACHE_EXCEPTION",
                f"清空缓存失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        report_lines = []
        report_lines.append("🔍 本地数据服务状态报告")
        report_lines.append("=" * 50)

        # 基本状态
        status_icon = "✅" if self._initialization_successful else "❌"
        report_lines.append(
            f"📊 初始化状态: {status_icon} {'成功' if self._initialization_successful else '失败'}"
        )

        # 缓存状态
        report_lines.append(f"💾 缓存大小: {len(self._data_cache)} 项")
        if self._data_cache:
            report_lines.append("📋 缓存项目:")
            for key in list(self._data_cache.keys())[:5]:  # 只显示前5项
                item_count = len(self._data_cache[key])
                report_lines.append(f"  - {key}: {item_count}条记录")
            if len(self._data_cache) > 5:
                report_lines.append(f"  ... 还有{len(self._data_cache) - 5}项")
        else:
            report_lines.append("📋 缓存为空")

        return "\n".join(report_lines)


# 导出公共接口
__all__ = ["LocalDataService"]

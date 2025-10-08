# -*- coding: utf-8 -*-
"""
品种服务 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道品种服务的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from backend.core.shared_services import ErrorSeverity, get_service_manager
from backend.core.models import SymbolInfo

if TYPE_CHECKING:
    from backend.core.vnpy_service_adapter import VnPyServiceAdapter

logger = logging.getLogger(__name__)


class SymbolService:
    """品种服务 - 专注于错误追踪和详细报告"""

    def __init__(self, vnpy_adapter: "VnPyServiceAdapter"):
        """初始化品种服务"""
        self.vnpy_adapter = vnpy_adapter
        self.service_manager = get_service_manager()
        self.logger = logging.getLogger(self.__class__.__name__)

        self._symbols_cache: Dict[str, SymbolInfo] = {}
        self._cache_updated = False
        self._initialization_successful = False

        # 尝试初始化
        self._attempt_initialization()

    def _attempt_initialization(self):
        """尝试初始化品种服务"""
        try:
            self.service_manager.record_error(
                "SymbolService",
                "INITIALIZATION_START",
                "开始初始化品种服务",
                severity=ErrorSeverity.INFO,
            )

            # 检查VnPy适配器状态
            if self.vnpy_adapter is None:
                error_msg = "VnPy适配器不可用，无法初始化品种服务"
                self.service_manager.record_error(
                    "SymbolService",
                    "VNPY_ADAPTER_UNAVAILABLE",
                    error_msg,
                    severity=ErrorSeverity.CRITICAL,
                )
                return

            # 加载品种信息到缓存
            self._load_symbols_cache()

            self._initialization_successful = True
            self.service_manager.record_error(
                "SymbolService",
                "INITIALIZATION_SUCCESS",
                f"品种服务初始化成功，缓存{len(self._symbols_cache)}个品种",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"品种服务初始化失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "INITIALIZATION_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )

    def _load_symbols_cache(self):
        """从VnPy适配器加载品种信息到缓存"""
        try:
            self.service_manager.record_error(
                "SymbolService",
                "CACHE_LOAD_START",
                "开始从VnPy适配器加载品种信息到缓存",
                severity=ErrorSeverity.INFO,
            )

            # 从VnPy适配器获取品种信息
            vnpy_symbols = self.vnpy_adapter.get_symbols()

            if not vnpy_symbols:
                self.service_manager.record_error(
                    "SymbolService",
                    "EMPTY_SYMBOLS_LIST",
                    "从VnPy适配器获得的品种列表为空，尝试刷新",
                    severity=ErrorSeverity.WARNING,
                )

                # 尝试刷新品种列表
                refresh_result = self.vnpy_adapter.refresh_stock_list()
                if refresh_result:
                    vnpy_symbols = self.vnpy_adapter.get_symbols()
                    if vnpy_symbols:
                        self.service_manager.record_error(
                            "SymbolService",
                            "SYMBOLS_REFRESH_SUCCESS",
                            f"品种列表刷新成功，获得{len(vnpy_symbols)}个品种",
                            severity=ErrorSeverity.INFO,
                        )
                    else:
                        self.service_manager.record_error(
                            "SymbolService",
                            "SYMBOLS_STILL_EMPTY_AFTER_REFRESH",
                            "刷新后品种列表仍为空",
                            severity=ErrorSeverity.ERROR,
                        )
                else:
                    self.service_manager.record_error(
                        "SymbolService",
                        "SYMBOLS_REFRESH_FAILED",
                        "品种列表刷新失败",
                        severity=ErrorSeverity.ERROR,
                    )

            # 清空现有缓存
            self._symbols_cache.clear()

            # 转换并缓存品种信息
            for vnpy_symbol in vnpy_symbols:
                try:
                    symbol_info = SymbolInfo(
                        id=None,
                        symbol=vnpy_symbol["symbol"],
                        exchange=vnpy_symbol["exchange"],
                        name=vnpy_symbol.get("name", vnpy_symbol["symbol"]),
                        product=vnpy_symbol.get("category", vnpy_symbol.get("product", "")),
                        size=100,  # 默认手数
                        pricetick=0.01,  # 默认最小价格变动
                        min_volume=1,
                        max_volume=1000000,
                        is_active=True,
                        listed_date=None,
                        expired_date=None,
                    )

                    # 使用symbol+exchange作为缓存键
                    cache_key = f"{symbol_info.symbol}.{symbol_info.exchange}"
                    self._symbols_cache[cache_key] = symbol_info

                except Exception as e:
                    self.service_manager.record_error(
                        "SymbolService",
                        "SYMBOL_CONVERSION_ERROR",
                        f"转换品种信息失败: {vnpy_symbol}, 错误: {str(e)}",
                        exception=e,
                        severity=ErrorSeverity.WARNING,
                    )

            self._cache_updated = True
            self.service_manager.record_error(
                "SymbolService",
                "CACHE_LOAD_SUCCESS",
                f"品种信息缓存加载完成，共{len(self._symbols_cache)}个品种",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"加载品种信息缓存失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "CACHE_LOAD_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            raise

    async def get_all_symbols(
        self,
        exchange: Optional[str] = None,
        product: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[SymbolInfo]:
        """获取所有品种信息"""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                self._load_symbols_cache()

            symbols = list(self._symbols_cache.values())

            # 应用过滤条件
            filtered_symbols = []
            for symbol in symbols:
                if exchange and symbol.exchange != exchange:
                    continue
                if product and symbol.product != product:
                    continue
                if is_active is not None and symbol.is_active != is_active:
                    continue

                filtered_symbols.append(symbol)

            self.service_manager.record_error(
                "SymbolService",
                "GET_ALL_SYMBOLS_SUCCESS",
                f"获取品种列表成功，返回{len(filtered_symbols)}个品种，过滤条件: exchange={exchange}, product={product}, is_active={is_active}",
                severity=ErrorSeverity.INFO,
            )

            return filtered_symbols

        except Exception as e:
            error_msg = f"获取品种列表失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "GET_ALL_SYMBOLS_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    async def refresh_cache(self) -> bool:
        """刷新品种缓存（从内存重新组织）"""
        try:
            self.service_manager.record_error(
                "SymbolService",
                "REFRESH_CACHE_START",
                "开始刷新品种缓存",
                severity=ErrorSeverity.INFO,
            )

            self._load_symbols_cache()

            self.service_manager.record_error(
                "SymbolService",
                "REFRESH_CACHE_SUCCESS",
                f"品种缓存刷新完成，共{len(self._symbols_cache)}个品种",
                severity=ErrorSeverity.INFO,
            )
            return True

        except Exception as e:
            error_msg = f"刷新品种缓存失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "REFRESH_CACHE_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    async def reload_symbols_from_api(self) -> bool:
        """重新加载品种列表（调用API更新）"""
        try:
            self.service_manager.record_error(
                "SymbolService",
                "RELOAD_SYMBOLS_API_START",
                "开始通过API重新加载品种列表",
                severity=ErrorSeverity.INFO,
            )

            # 调用VnPy适配器的重新加载方法
            success = self.vnpy_adapter.reload_stock_list()

            if success:
                # 重新加载到缓存
                self._load_symbols_cache()

                self.service_manager.record_error(
                    "SymbolService",
                    "RELOAD_SYMBOLS_API_SUCCESS",
                    f"品种列表通过API重新加载成功，共{len(self._symbols_cache)}个品种",
                    severity=ErrorSeverity.INFO,
                )
                return True
            else:
                self.service_manager.record_error(
                    "SymbolService",
                    "RELOAD_SYMBOLS_API_FAILED",
                    "VnPy适配器报告API重新加载失败",
                    severity=ErrorSeverity.ERROR,
                )
                return False

        except Exception as e:
            error_msg = f"重新加载品种列表失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "RELOAD_SYMBOLS_API_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    async def get_symbol_detail(self, symbol: str, exchange: str) -> Optional[SymbolInfo]:
        """获取品种详情"""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                self._load_symbols_cache()

            cache_key = f"{symbol}.{exchange}"
            symbol_info = self._symbols_cache.get(cache_key)

            if symbol_info:
                self.service_manager.record_error(
                    "SymbolService",
                    "GET_SYMBOL_DETAIL_SUCCESS",
                    f"获取品种详情成功: {symbol}.{exchange}",
                    severity=ErrorSeverity.INFO,
                )
            else:
                self.service_manager.record_error(
                    "SymbolService",
                    "SYMBOL_NOT_FOUND",
                    f"品种不存在: {symbol}.{exchange}",
                    severity=ErrorSeverity.WARNING,
                )

            return symbol_info

        except Exception as e:
            error_msg = f"获取品种详情失败: {str(e)}"
            self.service_manager.record_error(
                "SymbolService",
                "GET_SYMBOL_DETAIL_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    def get_service_status(self) -> Dict[str, Any]:
        """获取品种服务状态"""
        return {
            "initialization_successful": self._initialization_successful,
            "cache_updated": self._cache_updated,
            "cache_size": len(self._symbols_cache),
            "vnpy_adapter_available": self.vnpy_adapter is not None,
            "vnpy_adapter_status": self.vnpy_adapter.get_status() if self.vnpy_adapter else None,
        }

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        try:
            if not self._symbols_cache:
                return {
                    "total_symbols": 0,
                    "cache_updated": self._cache_updated,
                    "exchanges_count": 0,
                    "products_count": 0,
                    "timestamp": datetime.now().isoformat(),
                }

            return {
                "total_symbols": len(self._symbols_cache),
                "cache_updated": self._cache_updated,
                "exchanges_count": len(set(s.exchange for s in self._symbols_cache.values())),
                "products_count": len(
                    set(s.product for s in self._symbols_cache.values() if s.product)
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.service_manager.record_error(
                "SymbolService",
                "GET_CACHE_STATISTICS_EXCEPTION",
                f"获取缓存统计信息失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        report_lines = []
        report_lines.append("🔍 品种服务状态报告")
        report_lines.append("=" * 50)

        # 基本状态
        status_icon = "✅" if self._initialization_successful else "❌"
        report_lines.append(
            f"📊 初始化状态: {status_icon} {'成功' if self._initialization_successful else '失败'}"
        )

        # 缓存状态
        cache_icon = "✅" if self._cache_updated else "⚠️"
        report_lines.append(
            f"💾 缓存状态: {cache_icon} {'已更新' if self._cache_updated else '未更新'}"
        )
        report_lines.append(f"📋 缓存大小: {len(self._symbols_cache)} 个品种")

        # VnPy适配器状态
        if self.vnpy_adapter:
            adapter_status = self.vnpy_adapter.get_status()
            adapter_icon = "✅" if adapter_status.get("vnpy_available", False) else "❌"
            report_lines.append(
                f"🔗 VnPy适配器: {adapter_icon} {adapter_status.get('status', 'unknown')}"
            )
        else:
            report_lines.append("🔗 VnPy适配器: ❌ 不可用")

        # 统计信息
        if self._symbols_cache:
            stats = self.get_cache_statistics()
            report_lines.append("\n📊 统计信息:")
            report_lines.append(f"  交易所数量: {stats.get('exchanges_count', 0)}")
            report_lines.append(f"  产品类型数量: {stats.get('products_count', 0)}")

        return "\n".join(report_lines)


# 导出公共接口
__all__ = ["SymbolService"]

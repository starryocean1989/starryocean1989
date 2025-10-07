# -*- coding: utf-8 -*-
"""
品种服务.

提供品种信息管理相关的业务逻辑。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from backend.services.base_service import BaseService
from backend.core.models import SymbolInfo

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService

logger = logging.getLogger(__name__)


class SymbolService(BaseService):
    """品种服务."""

    def __init__(self, vnpy_service: "VnpyService"):
        """初始化品种服务."""
        super().__init__("SymbolService")
        self.vnpy_service = vnpy_service
        self._symbols_cache: Dict[str, SymbolInfo] = {}
        self._cache_updated = False

    async def initialize(self) -> None:
        """初始化品种服务."""
        try:
            self.logger.info("正在初始化品种服务...")

            # 加载品种信息到缓存
            await self._load_symbols_cache()

            self.logger.info("品种服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("品种服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭品种服务."""
        try:
            self.logger.info("正在关闭品种服务...")

            # 清理缓存
            self._symbols_cache.clear()
            self._cache_updated = False

            self.logger.info("品种服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("品种服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查品种服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "cache_size": len(self._symbols_cache),
                "cache_updated": self._cache_updated,
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("品种服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _load_symbols_cache(self) -> None:
        """加载品种信息到缓存."""
        try:
            self.logger.info("正在加载品种信息到缓存...")

            # 从VnPy服务获取品种信息
            vnpy_symbols = self.vnpy_service.get_symbols()

            # 清空现有缓存
            self._symbols_cache.clear()

            # 转换并缓存品种信息
            for vnpy_symbol in vnpy_symbols:
                symbol_info = SymbolInfo(
                    id=None,
                    symbol=vnpy_symbol["symbol"],
                    exchange=vnpy_symbol["exchange"],
                    name=vnpy_symbol.get("name", vnpy_symbol["symbol"]),
                    product=vnpy_symbol.get("product", ""),
                    size=vnpy_symbol.get("size", 1),
                    pricetick=vnpy_symbol.get("pricetick", 0.01),
                    min_volume=1,
                    max_volume=1000000,
                    is_active=True,
                    listed_date=None,
                    expired_date=None,
                )

                # 使用symbol+exchange作为缓存键
                cache_key = f"{symbol_info.symbol}.{symbol_info.exchange}"
                self._symbols_cache[cache_key] = symbol_info

            self._cache_updated = True
            self.logger.info(
                "品种信息缓存加载完成: %d 个品种", len(self._symbols_cache)
            )

        except Exception as e:
            self.logger.error("加载品种信息缓存失败: %s", e)
            raise

    async def get_all_symbols(
        self,
        exchange: Optional[str] = None,
        product: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[SymbolInfo]:
        """获取所有品种信息."""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                await self._load_symbols_cache()

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

            self.logger.info("获取品种列表: %d 个品种", len(filtered_symbols))
            return filtered_symbols

        except Exception as e:
            self.logger.error("获取品种列表失败: %s", e)
            raise

    async def get_symbol_detail(
        self, symbol: str, exchange: str
    ) -> Optional[SymbolInfo]:
        """获取品种详情."""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                await self._load_symbols_cache()

            cache_key = f"{symbol}.{exchange}"
            symbol_info = self._symbols_cache.get(cache_key)

            if symbol_info:
                self.logger.info("获取品种详情: %s.%s", symbol, exchange)
            else:
                self.logger.warning("品种不存在: %s.%s", symbol, exchange)

            return symbol_info

        except Exception as e:
            self.logger.error("获取品种详情失败: %s", e)
            raise

    async def search_symbols(self, keyword: str) -> List[SymbolInfo]:
        """搜索品种."""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                await self._load_symbols_cache()

            keyword = keyword.lower()
            matching_symbols = []

            for symbol in self._symbols_cache.values():
                # 在品种代码、名称、产品类型中搜索
                if (
                    keyword in symbol.symbol.lower()
                    or keyword in symbol.name.lower()
                    or keyword in symbol.product.lower()
                ):
                    matching_symbols.append(symbol)

            self.logger.info(
                "搜索品种: 关键词='%s', 结果=%d 个", keyword, len(matching_symbols)
            )
            return matching_symbols

        except Exception as e:
            self.logger.error("搜索品种失败: %s", e)
            raise

    async def get_exchanges(self) -> List[str]:
        """获取所有交易所列表."""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                await self._load_symbols_cache()

            exchanges = set()
            for symbol in self._symbols_cache.values():
                exchanges.add(symbol.exchange)

            exchange_list = sorted(list(exchanges))
            self.logger.info("获取交易所列表: %d 个交易所", len(exchange_list))
            return exchange_list

        except Exception as e:
            self.logger.error("获取交易所列表失败: %s", e)
            raise

    async def get_products(self, exchange: Optional[str] = None) -> List[str]:
        """获取产品类型列表."""
        try:
            # 如果缓存未更新，重新加载
            if not self._cache_updated:
                await self._load_symbols_cache()

            products = set()
            for symbol in self._symbols_cache.values():
                if exchange and symbol.exchange != exchange:
                    continue
                if symbol.product:
                    products.add(symbol.product)

            product_list = sorted(list(products))
            self.logger.info("获取产品类型列表: %d 个产品类型", len(product_list))
            return product_list

        except Exception as e:
            self.logger.error("获取产品类型列表失败: %s", e)
            raise

    async def refresh_cache(self) -> None:
        """刷新品种缓存."""
        try:
            self.logger.info("正在刷新品种缓存...")
            await self._load_symbols_cache()
            self.logger.info("品种缓存刷新完成")

        except Exception as e:
            self.logger.error("刷新品种缓存失败: %s", e)
            raise

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "total_symbols": len(self._symbols_cache),
                "cache_updated": self._cache_updated,
                "exchanges_count": len(
                    set(s.exchange for s in self._symbols_cache.values())
                ),
                "products_count": len(
                    set(s.product for s in self._symbols_cache.values() if s.product)
                ),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["SymbolService"]

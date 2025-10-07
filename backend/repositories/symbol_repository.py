# -*- coding: utf-8 -*-
"""
品种仓库.

提供品种信息的数据库操作功能。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from .base_repository import InMemoryRepository

if TYPE_CHECKING:
    from backend.core.models import SymbolInfo

logger = logging.getLogger(__name__)


class SymbolRepository(InMemoryRepository["SymbolInfo"]):
    """品种仓库."""

    def __init__(self):
        """初始化品种仓库."""
        super().__init__("symbols")

    async def get_by_symbol_exchange(
        self, symbol: str, exchange: str
    ) -> Optional["SymbolInfo"]:
        """根据品种代码和交易所获取品种信息."""
        try:
            for symbol_info in self._data.values():
                if symbol_info.symbol == symbol and symbol_info.exchange == exchange:
                    self._log_operation(
                        "get_by_symbol_exchange", symbol=symbol, exchange=exchange
                    )
                    return symbol_info

            self.logger.warning("品种不存在: %s.%s", symbol, exchange)
            return None

        except Exception as e:
            self._log_error(
                "get_by_symbol_exchange", e, symbol=symbol, exchange=exchange
            )
            raise

    async def get_by_exchange(self, exchange: str) -> List["SymbolInfo"]:
        """根据交易所获取品种列表."""
        try:
            symbols = [s for s in self._data.values() if s.exchange == exchange]
            self._log_operation(
                "get_by_exchange", exchange=exchange, count=len(symbols)
            )
            return symbols

        except Exception as e:
            self._log_error("get_by_exchange", e, exchange=exchange)
            raise

    async def get_by_product(self, product: str) -> List["SymbolInfo"]:
        """根据产品类型获取品种列表."""
        try:
            symbols = [s for s in self._data.values() if s.product == product]
            self._log_operation("get_by_product", product=product, count=len(symbols))
            return symbols

        except Exception as e:
            self._log_error("get_by_product", e, product=product)
            raise

    async def get_active_symbols(self) -> List["SymbolInfo"]:
        """获取活跃品种列表."""
        try:
            symbols = [s for s in self._data.values() if s.is_active]
            self._log_operation("get_active_symbols", count=len(symbols))
            return symbols

        except Exception as e:
            self._log_error("get_active_symbols", e)
            raise

    async def search_symbols(self, keyword: str) -> List["SymbolInfo"]:
        """搜索品种."""
        try:
            keyword = keyword.lower()
            matching_symbols = []

            for symbol in self._data.values():
                if (
                    keyword in symbol.symbol.lower()
                    or keyword in symbol.name.lower()
                    or keyword in symbol.product.lower()
                ):
                    matching_symbols.append(symbol)

            self._log_operation(
                "search_symbols", keyword=keyword, count=len(matching_symbols)
            )
            return matching_symbols

        except Exception as e:
            self._log_error("search_symbols", e, keyword=keyword)
            raise

    async def get_exchanges(self) -> List[str]:
        """获取所有交易所列表."""
        try:
            exchanges = list(set(s.exchange for s in self._data.values()))
            exchanges.sort()
            self._log_operation("get_exchanges", count=len(exchanges))
            return exchanges

        except Exception as e:
            self._log_error("get_exchanges", e)
            raise

    async def get_products(self, exchange: Optional[str] = None) -> List[str]:
        """获取产品类型列表."""
        try:
            products = set()
            for symbol in self._data.values():
                if exchange and symbol.exchange != exchange:
                    continue
                if symbol.product:
                    products.add(symbol.product)

            product_list = sorted(list(products))
            self._log_operation(
                "get_products", exchange=exchange, count=len(product_list)
            )
            return product_list

        except Exception as e:
            self._log_error("get_products", e, exchange=exchange)
            raise

    async def bulk_create(self, symbols: List["SymbolInfo"]) -> List["SymbolInfo"]:
        """批量创建品种."""
        try:
            created_symbols = []

            for symbol in symbols:
                # 检查是否已存在
                existing = await self.get_by_symbol_exchange(
                    symbol.symbol, symbol.exchange
                )
                if existing:
                    self.logger.warning(
                        "品种已存在，跳过: %s.%s", symbol.symbol, symbol.exchange
                    )
                    continue

                # 创建品种
                created_symbol = await self.create(symbol)
                created_symbols.append(created_symbol)

            self._log_operation("bulk_create", count=len(created_symbols))
            self.logger.info("批量创建品种完成: %d 个", len(created_symbols))
            return created_symbols

        except Exception as e:
            self._log_error("bulk_create", e, count=len(symbols))
            raise

    async def update_by_symbol_exchange(
        self, symbol: str, exchange: str, updates: Dict[str, Any]
    ) -> Optional["SymbolInfo"]:
        """根据品种代码和交易所更新品种信息."""
        try:
            symbol_info = await self.get_by_symbol_exchange(symbol, exchange)
            if not symbol_info:
                self.logger.warning("品种不存在: %s.%s", symbol, exchange)
                return None

            # 更新字段
            for key, value in updates.items():
                if hasattr(symbol_info, key):
                    setattr(symbol_info, key, value)

            # 保存更新
            updated_symbol = await self.update(symbol_info)

            self._log_operation(
                "update_by_symbol_exchange",
                symbol=symbol,
                exchange=exchange,
                updates=list(updates.keys()),
            )
            return updated_symbol

        except Exception as e:
            self._log_error(
                "update_by_symbol_exchange",
                e,
                symbol=symbol,
                exchange=exchange,
                updates=updates,
            )
            raise

    async def delete_by_symbol_exchange(self, symbol: str, exchange: str) -> bool:
        """根据品种代码和交易所删除品种."""
        try:
            symbol_info = await self.get_by_symbol_exchange(symbol, exchange)
            if not symbol_info:
                self.logger.warning("品种不存在: %s.%s", symbol, exchange)
                return False

            # 获取ID并删除
            entity_id = symbol_info.id
            if entity_id:
                return await self.delete(entity_id)
            else:
                self.logger.error("品种缺少ID字段: %s.%s", symbol, exchange)
                return False

        except Exception as e:
            self._log_error(
                "delete_by_symbol_exchange", e, symbol=symbol, exchange=exchange
            )
            raise

    async def get_symbol_statistics(self) -> Dict[str, Any]:
        """获取品种统计信息."""
        try:
            total_symbols = len(self._data)
            active_symbols = len([s for s in self._data.values() if s.is_active])
            exchanges = len(set(s.exchange for s in self._data.values()))
            products = len(set(s.product for s in self._data.values() if s.product))

            stats = {
                "total_symbols": total_symbols,
                "active_symbols": active_symbols,
                "inactive_symbols": total_symbols - active_symbols,
                "exchanges_count": exchanges,
                "products_count": products,
                "timestamp": datetime.now().isoformat(),
            }

            self._log_operation("get_symbol_statistics", stats=stats)
            return stats

        except Exception as e:
            self._log_error("get_symbol_statistics", e)
            raise


# 导出公共接口
__all__ = ["SymbolRepository"]

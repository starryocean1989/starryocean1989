# -*- coding: utf-8 -*-
"""
北证数据解码器

北证股票数据格式特殊，需要特殊处理：
- 价格需要除以100
- 成交量需要除以100
"""

import logging
import pandas as pd

# 尝试导入native_compute（支持降级）
try:
    from backend.infrastructure.native.native_compute import (
        batch_compute,
        COMPUTE_AVAILABLE,
    )
    _USE_NATIVE_COMPUTE = COMPUTE_AVAILABLE
except ImportError:
    _USE_NATIVE_COMPUTE = False
    batch_compute = None

logger = logging.getLogger(__name__)


class BjStockDecoder:
    """北证数据解码器

    北证股票数据格式特殊，需要特殊处理：
    - 价格需要除以100
    - 成交量需要除以100
    """

    @staticmethod
    def decode_bj_stock(df: pd.DataFrame) -> pd.DataFrame:
        """解码北证股票数据

        Args:
            df: 原始数据

        Returns:
            解码后的数据
        """
        if df.empty:
            return df

        df = df.copy()

        # 🚀 性能优化：使用native_compute批量处理价格和成交量除法运算
        price_columns = ["open", "high", "low", "close"]

        if _USE_NATIVE_COMPUTE and batch_compute is not None:
            # 使用native_compute批量处理
            try:
                # 批量处理价格字段
                for col in price_columns:
                    if col in df.columns:
                        # 提取列值到列表
                        price_values = df[col].tolist()
                        # 使用native_compute批量除以100
                        converted_prices = batch_compute(price_values, "divide_by_100")  # type: ignore
                        # 写回DataFrame
                        df[col] = converted_prices

                # 批量处理成交量
                if "volume" in df.columns:
                    volume_values = df["volume"].tolist()
                    converted_volumes = batch_compute(volume_values, "divide_by_100")  # type: ignore
                    df["volume"] = converted_volumes

            except Exception as e:
                # 降级到Python实现
                logger.debug(
                    f"[BjStockDecoder] native_compute失败，降级到Python实现: {e}",
                    extra={"log_type": "SYSTEM"},
                )
                # 使用Python实现
                for col in price_columns:
                    if col in df.columns:
                        df[col] = df[col] / 100.0
                if "volume" in df.columns:
                    df["volume"] = df["volume"] / 100.0
        else:
            # 降级到Python实现（native_compute不可用）
            for col in price_columns:
                if col in df.columns:
                    df[col] = df[col] / 100.0
            if "volume" in df.columns:
                df["volume"] = df["volume"] / 100.0

        return df

    @staticmethod
    def is_bj_stock(symbol: str) -> bool:
        """判断是否为北证股票

        Args:
            symbol: 品种代码

        Returns:
            True表示是北证股票
        """
        return symbol.startswith(("4", "8", "9"))


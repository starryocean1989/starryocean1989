# -*- coding: utf-8 -*-
"""
通达信数据格式转换工具

提供TDX数据格式转换功能:
- K线数据转DataFrame
- 时间字段标准化
- 数据类型转换
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ==============================================================================
# K线数据转换
# ==============================================================================


def tdx_bars_to_dataframe(
    bars: List[dict],
    symbol: str,
    interval: str,
    normalize_datetime: bool = True,
) -> pd.DataFrame:
    """将TDX K线数据转换为标准DataFrame

    Args:
        bars: TDX返回的K线数据列表
        symbol: 品种代码
        interval: 周期 (1d/5m/1m等)
        normalize_datetime: 是否标准化时间字段

    Returns:
        标准化的DataFrame,包含以下列:
        - date: 日期时间
        - open: 开盘价
        - high: 最高价
        - low: 最低价
        - close: 收盘价
        - volume: 成交量
        - amount: 成交额

    示例:
        >>> bars = await api.get_security_bars(9, 1, "600000", 0, 100)
        >>> df = tdx_bars_to_dataframe(bars, symbol="600000", interval="1d")
        >>> print(df.head())
    """
    # 方法链穿透: AsyncTdxHq_API.get_security_bars / get_security_bars_by_interval -> tdx_bars_to_dataframe
    # 输入字典需包含价格(open/high/low/close)、成交量(vol)与可选成交额(amount)，
    # 时间字段优先使用(year/month/day[/hour/minute])，否则使用已有的 datetime 字段。
    # 边界处理: 空列表返回空DataFrame；缺列会记录warning但不中断；索引设置为 datetime 或 date。
    if not bars:
        return pd.DataFrame()

    # 转换为DataFrame
    df = pd.DataFrame(bars)

    # 标准化时间字段
    if normalize_datetime and "datetime" not in df.columns:
        df = _normalize_tdx_datetime(df)

    # 重命名列(统一命名规范)
    column_mapping = {
        "vol": "volume",  # 成交量
        "amount": "amount",  # 成交额
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
    }

    # 只重命名存在的列
    rename_dict = {k: v for k, v in column_mapping.items() if k in df.columns}
    if rename_dict:
        df = df.rename(columns=rename_dict)

    # 确保必要的列存在
    required_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.warning(f"缺少必要的列: {missing_columns}, symbol={symbol}, interval={interval}")

    # 设置索引
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime")
    elif "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")

    # 添加元数据
    df.attrs["symbol"] = symbol
    df.attrs["interval"] = interval

    return df


def _normalize_tdx_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """标准化TDX时间字段

    TDX返回的时间字段格式:
    - year, month, day: 年月日
    - hour, minute: 时分(分钟线)

    Args:
        df: 原始DataFrame

    Returns:
        添加了datetime列的DataFrame
    """
    if df.empty:
        return df

    # 检查必要的时间字段
    if "year" not in df.columns or "month" not in df.columns or "day" not in df.columns:
        logger.warning("缺少时间字段(year/month/day),无法标准化")
        return df

    # 构建datetime列
    try:
        # 日K线(无hour/minute字段)
        if "hour" not in df.columns or "minute" not in df.columns:
            df["datetime"] = pd.to_datetime(
                df[["year", "month", "day"]].rename(
                    columns={"year": "year", "month": "month", "day": "day"}
                )
            )
        else:
            # 分钟线(有hour/minute字段)
            df["datetime"] = pd.to_datetime(
                df[["year", "month", "day", "hour", "minute"]].rename(
                    columns={
                        "year": "year",
                        "month": "month",
                        "day": "day",
                        "hour": "hour",
                        "minute": "minute",
                    }
                )
            )

    except Exception as e:
        logger.error(f"时间字段标准化失败: {e}", exc_info=True)

    return df


# ==============================================================================
# 实时行情数据转换
# ==============================================================================


def tdx_quotes_to_dataframe(quotes: List[dict]) -> pd.DataFrame:
    """将TDX实时行情数据转换为DataFrame

    Args:
        quotes: TDX返回的实时行情数据列表

    Returns:
        DataFrame,包含实时行情字段

    示例:
        >>> quotes = await api.get_security_quotes([(1, "600000"), (0, "000001")])
        >>> df = tdx_quotes_to_dataframe(quotes)
        >>> print(df[["code", "price", "open", "high", "low"]])
    """
    # 方法链穿透: AsyncTdxHq_API.get_security_quotes -> tdx_quotes_to_dataframe
    # 输入需包含至少 'code' 字段以便设置索引；其余字段按原样保留，适合后续拼接或聚合。
    # 边界处理: 空列表返回空DataFrame；如无 'code' 字段则不设置索引。
    if not quotes:
        return pd.DataFrame()

    df = pd.DataFrame(quotes)

    # 设置索引
    if "code" in df.columns:
        df = df.set_index("code")

    return df


# ==============================================================================
# 股票列表数据转换
# ==============================================================================


def tdx_security_list_to_dataframe(security_list: List[dict]) -> pd.DataFrame:
    """将TDX股票列表数据转换为DataFrame

    Args:
        security_list: TDX返回的股票列表数据

    Returns:
        DataFrame,包含股票列表字段

    示例:
        >>> stocks = await api.get_security_list(market=1, start=0)
        >>> df = tdx_security_list_to_dataframe(stocks)
        >>> print(df[["code", "name", "category"]])
    """
    # 方法链穿透: get_security_list_all / get_security_list_batch -> tdx_security_list_to_dataframe
    # 输入通常包含 'code', 'name', 'category' 等字段；设置 'code' 为索引便于后续筛选与合并。
    if not security_list:
        return pd.DataFrame()

    df = pd.DataFrame(security_list)

    # 设置索引
    if "code" in df.columns:
        df = df.set_index("code")

    return df


# ==============================================================================
# 除权除息数据转换
# ==============================================================================


def tdx_xdxr_to_dataframe(xdxr_data: List[dict], symbol: str) -> pd.DataFrame:
    """将TDX除权除息数据转换为DataFrame

    Args:
        xdxr_data: TDX返回的除权除息数据
        symbol: 品种代码

    Returns:
        DataFrame,包含除权除息字段

    示例:
        >>> xdxr = await api.get_xdxr_info(market=1, code="600000")
        >>> df = tdx_xdxr_to_dataframe(xdxr, symbol="600000")
        >>> print(df[["date", "category", "fenhong", "peigu"]])
    """
    # 方法链穿透: AsyncTdxHq_API.get_xdxr_info -> tdx_xdxr_to_dataframe
    # 输入需包含日期三元组(year/month/day)以构建标准化 'date' 列；其他字段按原样保留。
    # 边界处理: 空列表返回空DataFrame；缺少日期字段时不构建 'date' 列。
    if not xdxr_data:
        return pd.DataFrame()

    df = pd.DataFrame(xdxr_data)

    # 构建日期列
    if "year" in df.columns and "month" in df.columns and "day" in df.columns:
        df["date"] = pd.to_datetime(
            df[["year", "month", "day"]].rename(
                columns={"year": "year", "month": "month", "day": "day"}
            )
        )
        df = df.set_index("date")

    # 添加元数据
    df.attrs["symbol"] = symbol

    return df


# ==============================================================================
# 财务数据转换
# ==============================================================================


def tdx_finance_to_dict(finance_info: dict, symbol: str) -> Dict[str, Any]:
    """将TDX财务数据转换为标准字典

    Args:
        finance_info: TDX返回的财务信息
        symbol: 品种代码

    Returns:
        标准化的财务数据字典

    示例:
        >>> finance = await api.get_finance_info(market=1, code="600000")
        >>> data = tdx_finance_to_dict(finance, symbol="600000")
        >>> print(data["ipo_date"], data["industry"])
    """
    if not finance_info:
        return {}

    # 复制原始数据
    result = finance_info.copy()

    # 添加品种代码
    result["symbol"] = symbol

    # 转换IPO日期（使用统一的解析函数）
    if "ipo_date" in result and result["ipo_date"]:
        ipo_date_int = result["ipo_date"]
        # 使用统一的解析函数（从api.finance导入）
        from ..api.finance import _parse_ipo_date_single

        parsed_date = _parse_ipo_date_single(ipo_date_int)
        if parsed_date:
            result["ipo_date_parsed"] = parsed_date

    return result


# ==============================================================================
# 通用转换函数
# ==============================================================================


def normalize_tdx_data(
    data: Any, data_type: str, symbol: Optional[str] = None, interval: Optional[str] = None
) -> pd.DataFrame:
    """通用TDX数据标准化函数

    Args:
        data: TDX返回的原始数据
        data_type: 数据类型 ('bars', 'quotes', 'security_list', 'xdxr', 'finance')
        symbol: 品种代码(可选)
        interval: 周期(可选)

    Returns:
        标准化的DataFrame

    示例:
        >>> bars = await api.get_security_bars(9, 1, "600000", 0, 100)
        >>> df = normalize_tdx_data(bars, data_type="bars", symbol="600000", interval="1d")
    """
    if data_type == "bars":
        return tdx_bars_to_dataframe(data, symbol or "", interval or "")
    elif data_type == "quotes":
        return tdx_quotes_to_dataframe(data)
    elif data_type == "security_list":
        return tdx_security_list_to_dataframe(data)
    elif data_type == "xdxr":
        return tdx_xdxr_to_dataframe(data, symbol or "")
    else:
        logger.warning(f"未知的数据类型: {data_type}")
        return pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame()


def bars_to_dataframe_safe(
    bars: Optional[List[dict]],
    symbol: str,
    interval: str,
    normalize_datetime: bool = True,
) -> pd.DataFrame:
    """
    安全转换K线数据为DataFrame（增强版，自动处理索引、列名标准化）

    Args:
        bars: TDX返回的K线数据列表（可能为None）
        symbol: 品种代码
        interval: 周期字符串 ("1d", "5m", "1m")
        normalize_datetime: 是否标准化时间字段（默认True）

    Returns:
        标准化的DataFrame，如果bars为None或空则返回空DataFrame

    Examples:
        >>> bars = await api.get_security_bars(9, 1, "600000", 0, 100)
        >>> df = bars_to_dataframe_safe(bars, "600000", "1d")
        >>> print(df.head())
    """
    # 处理None或空列表
    if not bars:
        return pd.DataFrame()

    try:
        # 使用现有的转换函数
        df = tdx_bars_to_dataframe(
            bars=bars,
            symbol=symbol,
            interval=interval,
            normalize_datetime=normalize_datetime,
        )

        # 确保索引是DatetimeIndex
        if not isinstance(df.index, pd.DatetimeIndex) and not df.empty:
            # 尝试从datetime列设置索引
            if "datetime" in df.columns:
                df["datetime"] = pd.to_datetime(df["datetime"])
                df = df.set_index("datetime")
            elif "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")

        return df

    except Exception as e:
        logger.warning(f"K线数据转换失败: symbol={symbol}, interval={interval}, 错误: {e}")
        return pd.DataFrame()


# ==============================================================================
# 导出
# ==============================================================================

__all__ = [
    "tdx_bars_to_dataframe",
    "tdx_quotes_to_dataframe",
    "tdx_security_list_to_dataframe",
    "tdx_xdxr_to_dataframe",
    "tdx_finance_to_dict",
    "normalize_tdx_data",
    "bars_to_dataframe_safe",
]

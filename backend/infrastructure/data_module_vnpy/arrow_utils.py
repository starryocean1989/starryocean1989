# -*- coding: utf-8 -*-
"""Arrow 序列化/反序列化工具.

提供 DataFrame ↔ Arrow IPC 字节流 的双向转换能力，并提供
base64 编解码帮助函数，方便在 JSON/RPC 通道中传输。

当环境缺少 ``pyarrow`` 时会自动降级返回 ``None`` 或抛出
``ImportError``，调用方需结合业务逻辑处理回退路径。
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Hashable, List, Optional, cast

import pandas as pd

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 外部依赖检测
    import pyarrow as pa
    import pyarrow.ipc as pa_ipc

    ARROW_AVAILABLE = True
except ImportError:  # pragma: no cover - 环境未安装 pyarrow
    pa = None  # type: ignore
    pa_ipc = None  # type: ignore
    ARROW_AVAILABLE = False


def _table_from_dataframe(df: pd.DataFrame):
    """将 DataFrame 转换为 pyarrow.Table，保持索引。"""

    if not ARROW_AVAILABLE or pa is None:
        raise ImportError("pyarrow 未安装，无法构建 Arrow 表")

    return pa.Table.from_pandas(df, preserve_index=True)


def dataframe_to_arrow_bytes(df: Optional[pd.DataFrame]) -> Optional[bytes]:
    """将 DataFrame 转换为 Arrow IPC 字节流.

    Args:
        df: 待转换的 DataFrame

    Returns:
        bytes 或 ``None`` （当 pyarrow 不可用或转换失败时）
    """

    if not ARROW_AVAILABLE or df is None:
        return None

    try:
        assert pa is not None and pa_ipc is not None
        table = _table_from_dataframe(df)
        sink = pa.BufferOutputStream()
        with pa_ipc.RecordBatchStreamWriter(sink, table.schema) as writer:
            writer.write_table(table)
        return sink.getvalue().to_pybytes()
    except Exception:  # pragma: no cover - 意外情况运行时记录
        logger.debug("Arrow 序列化失败，回退到其它格式", exc_info=True)
        return None


def arrow_bytes_to_dataframe(data: bytes) -> pd.DataFrame:
    """从 Arrow IPC 字节流还原为 DataFrame.

    Args:
        data: Arrow IPC 字节流

    Returns:
        pandas.DataFrame
    """

    if not ARROW_AVAILABLE:
        raise ImportError("pyarrow 未安装，无法解析 Arrow 字节流")

    if not data:
        return pd.DataFrame()

    assert pa is not None and pa_ipc is not None
    buffer_reader = pa.BufferReader(data)
    reader = pa_ipc.RecordBatchStreamReader(buffer_reader)
    table = reader.read_all()
    return table.to_pandas()  # 保留原始索引


def dataframe_to_arrow_buffer(df: Optional[pd.DataFrame]) -> Optional[memoryview]:
    """将 DataFrame 转换为 Arrow IPC buffer 的 memoryview.

    相比 ``dataframe_to_arrow_bytes``，该方法返回对 ``pyarrow.Buffer``
    的 ``memoryview``，避免额外复制，有利于在跨进程场景下实现
    更高效的零拷贝传输。

    Args:
        df: 待转换的 DataFrame

    Returns:
        memoryview 或 ``None`` （当 pyarrow 不可用或转换失败时）
    """

    if not ARROW_AVAILABLE or df is None:
        return None

    try:
        assert pa is not None and pa_ipc is not None
        table = _table_from_dataframe(df)
        sink = pa.BufferOutputStream()
        with pa_ipc.RecordBatchStreamWriter(sink, table.schema) as writer:
            writer.write_table(table)
        buffer = sink.getvalue()
        return memoryview(buffer)
    except Exception:  # pragma: no cover - 意外情况运行时记录
        logger.debug("Arrow 内存缓冲生成失败，回退到其它格式", exc_info=True)
        return None


def arrow_bytes_to_kline_records(data: bytes) -> List[Dict[str, Any]]:
    """将 Arrow IPC 字节流转换为 K 线记录列表."""

    df = arrow_bytes_to_dataframe(data)
    if df.empty:
        return []

    # 恢复索引到 "datetime" 字段
    index_name = df.index.name or "datetime"
    records_df = df.reset_index()
    first_column = cast(Hashable, records_df.columns[0])
    if first_column != "datetime":
        records_df.rename(columns={first_column: "datetime"}, inplace=True)

    records = records_df.to_dict("records")
    for record in records:
        dt_value = record.get("datetime")
        if dt_value is None:
            continue

        iso_method = getattr(dt_value, "isoformat", None)
        if callable(iso_method):
            record["datetime"] = iso_method()
        else:
            record["datetime"] = str(dt_value)

        for key in ("open", "high", "low", "close", "volume"):
            if key in record and record[key] is not None:
                try:
                    record[key] = float(record[key])
                except (TypeError, ValueError):  # 非数值数据保持原样
                    pass

    return records


def encode_arrow_bytes(data: bytes) -> str:
    """将二进制 Arrow 数据编码为 base64 字符串."""

    return base64.b64encode(data).decode("ascii")


def decode_arrow_base64(data_str: str) -> bytes:
    """将 base64 字符串解码为 Arrow 二进制数据."""

    return base64.b64decode(data_str.encode("ascii"))



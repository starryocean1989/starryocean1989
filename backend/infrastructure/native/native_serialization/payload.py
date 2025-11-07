# -*- coding: utf-8 -*-
"""统一数据载荷协议（Arrow / Records）.

提供 DataFrame → Payload 的标准化转换工具，支持优先选择 Arrow IPC
零拷贝传输，并在 Arrow 不可用时回退到 records(JSON) 格式。

同时提供消费侧辅助函数，便于解释载荷并恢复为 DataFrame 或记录序列。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Hashable, List, Literal, Optional, Union, cast

import logging

import pandas as pd

from backend.infrastructure.data_module_vnpy.arrow_utils import (
    ARROW_AVAILABLE,
    arrow_bytes_to_dataframe,
    dataframe_to_arrow_bytes,
)

PayloadFormat = Literal["arrow", "records"]
PayloadTransport = Literal["buffer", "json"]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DataFramePayload:
    """结构化数据载荷描述."""

    format: PayloadFormat
    transport: PayloadTransport
    data: Union[memoryview, bytes, List[Dict[str, Any]]]
    rows: int
    columns: List[str]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典."""

        payload = {
            "format": self.format,
            "transport": self.transport,
            "data": self.data,
            "rows": self.rows,
            "columns": self.columns,
        }

        if self.metadata:
            payload["metadata"] = self.metadata

        return payload


def _format_datetime_column(series: pd.Series) -> pd.Series:
    """将 datetime 列转换为 ISO 字符串."""

    if pd.api.types.is_datetime64_any_dtype(series):
        formatted = series.dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
        return formatted.str.rstrip("0").str.rstrip(".")
    return series.astype(str)


def _zero_copy_arrow_buffer(df: pd.DataFrame) -> Optional[memoryview]:
    """尝试通过 native zero_copy 序列化生成 Arrow IPC memoryview."""

    try:
        from backend.infrastructure.native.native_serialization import (  # noqa: WPS433 - 延迟导入避免循环
            SERIALIZATION_AVAILABLE,
            zero_copy_serialize,
        )
    except ImportError:
        return None

    if not SERIALIZATION_AVAILABLE:
        return None

    try:
        payload = zero_copy_serialize(df)  # type: ignore[misc]
    except Exception:  # pragma: no cover - 运行时回退
        logger.debug("zero_copy_serialize DataFrame 失败，回退 Arrow utils", exc_info=True)
        return None

    if isinstance(payload, memoryview):
        return payload
    if isinstance(payload, (bytes, bytearray)):
        return memoryview(payload)

    return None


def build_dataframe_payload(
    df: Optional[pd.DataFrame],
    *,
    prefer_format: PayloadFormat = "arrow",
    include_metadata: bool = True,
) -> DataFramePayload:
    """构建统一数据载荷.

    Args:
        df: 待序列化的 DataFrame
        prefer_format: 优先格式（"arrow" 或 "records"）
        include_metadata: 是否包含额外元数据

    Returns:
        DataFramePayload 实例
    """

    payload_metadata: Dict[str, Any] = {}

    if df is None or df.empty:
        if include_metadata and df is not None:
            payload_metadata = {
                "index_name": df.index.name,
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            }

        return DataFramePayload(
            format="records",
            transport="json",
            data=[],
            rows=0,
            columns=(df.columns.tolist() if df is not None else []),
            metadata=payload_metadata,
        )

    columns = df.columns.tolist()

    if include_metadata:
        payload_metadata = {
            "index_name": df.index.name,
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        }

    if prefer_format == "arrow" and ARROW_AVAILABLE:
        arrow_buffer = _zero_copy_arrow_buffer(df)
        if arrow_buffer is None:
            arrow_bytes = dataframe_to_arrow_bytes(df)
            if arrow_bytes is not None:
                arrow_buffer = memoryview(arrow_bytes)

        if arrow_buffer is not None:
            arrow_metadata = dict(payload_metadata) if payload_metadata else {}
            arrow_metadata.setdefault("encoding", "arrow-ipc")
            return DataFramePayload(
                format="arrow",
                transport="buffer",
                data=arrow_buffer,
                rows=len(df),
                columns=columns,
                metadata=arrow_metadata,
            )

    # records fallback
    records_df = df.reset_index()
    first_column = cast(Hashable, records_df.columns[0])
    if first_column != "datetime":
        records_df = records_df.rename(columns={first_column: "datetime"})

    if "datetime" in records_df.columns:
        datetime_series = records_df.loc[:, "datetime"]
        records_df.loc[:, "datetime"] = _format_datetime_column(datetime_series)

    # 统一将 NaN 转为 None，避免 JSON 序列化异常
    records_df = records_df.where(pd.notnull(records_df), None)

    records = records_df.to_dict("records")

    records_metadata = dict(payload_metadata) if payload_metadata else {}
    records_metadata.setdefault("encoding", "json-records")

    return DataFramePayload(
        format="records",
        transport="json",
        data=records,
        rows=len(records_df),
        columns=records_df.columns.tolist(),
        metadata=records_metadata,
    )


def payload_to_dataframe(payload: Dict[str, Any]) -> pd.DataFrame:
    """将载荷还原为 DataFrame."""

    fmt = payload.get("format")
    if fmt == "arrow":
        transport = payload.get("transport", "buffer")
        raw = payload.get("data")

        if raw is None:
            return pd.DataFrame()

        if transport == "buffer":
            arrow_bytes = bytes(raw)
        elif transport == "base64":  # 兼容旧字段
            from backend.infrastructure.data_module_vnpy.arrow_utils import decode_arrow_base64

            arrow_bytes = decode_arrow_base64(raw)
        else:
            raise ValueError(f"Unsupported transport: {transport}")

        return arrow_bytes_to_dataframe(arrow_bytes)

    if fmt == "records":
        records = payload.get("data") or []
        return pd.DataFrame.from_records(records)

    raise ValueError(f"Unsupported payload format: {fmt}")


def payload_to_records(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将载荷转换为记录列表."""

    fmt = payload.get("format")
    if fmt == "records":
        return payload.get("data", []) or []

    if fmt == "arrow":
        df = payload_to_dataframe(payload)
        if df.empty:
            return []

        normalized = df.reset_index()
        normalized_first_col = cast(Hashable, normalized.columns[0])
        if normalized_first_col != "datetime":
            normalized = normalized.rename(columns={normalized_first_col: "datetime"})

        if "datetime" in normalized.columns and pd.api.types.is_datetime64_any_dtype(
            normalized["datetime"]
        ):
            datetime_series = normalized.loc[:, "datetime"]
            normalized.loc[:, "datetime"] = _format_datetime_column(datetime_series)

        normalized = normalized.where(pd.notnull(normalized), None)
        return normalized.to_dict("records")

    return []



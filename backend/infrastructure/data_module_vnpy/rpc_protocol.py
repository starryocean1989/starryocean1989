"""RPC 消息协议封装.

该模块为三进程架构的数据 RPC 通道提供统一的消息编解码能力。

特性：

- 固定长度原生报文头 (32 bytes)：包含 magic、version、method_id、request_id 等字段；
- 元数据区：JSON 编码的轻量信息（方法名、参数、状态、错误等）；
- 二进制负载区：用于 Arrow IPC 等零拷贝数据回传；
- 兼容旧版 JSON 报文，自动降级解析。

模块同时被客户端与服务端复用，确保编码逻辑一致。
"""

from __future__ import annotations

import base64
import struct
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:  # 优先使用 orjson 以提升性能
    import orjson as _json  # type: ignore

    def _dumps(payload: Any) -> bytes:
        return _json.dumps(payload)


    def _loads(data: bytes | memoryview) -> Any:
        return _json.loads(data)


    JSON_LIBRARY = "orjson"
except ImportError:  # pragma: no cover - orjson 缺失时降级
    import json as _json

    def _dumps(payload: Any) -> bytes:
        return _json.dumps(payload, ensure_ascii=False).encode("utf-8")


    def _loads(data: bytes | memoryview) -> Any:
        if isinstance(data, memoryview):
            data = data.tobytes()
        if isinstance(data, bytes):
            return _json.loads(data.decode("utf-8"))
        raise TypeError(f"Unsupported data type for JSON loads: {type(data)!r}")


    JSON_LIBRARY = "json"


# ==================== 常量定义 ====================

MAGIC = 0x4E525031  # 'NRP1'
VERSION = 1
HEADER_STRUCT = struct.Struct("<I H H I I I I I")
HEADER_SIZE = HEADER_STRUCT.size  # 32 字节

# 标志位
FLAG_NATIVE = 0x0001
FLAG_BATCH = 0x0002
FLAG_BINARY_PAYLOAD = 0x0004
FLAG_ERROR = 0x0008


@dataclass(slots=True)
class RPCRequest:
    """解码后的 RPC 请求."""

    request_id: int
    method: str
    params: Dict[str, Any]
    method_id: Optional[int] = None
    flags: int = 0
    metadata: Dict[str, Any] | None = None
    payload: Optional[memoryview] = None
    is_native: bool = False


@dataclass(slots=True)
class RPCResponse:
    """解码后的 RPC 响应."""

    request_id: int
    result: Optional[Any]
    error: Optional[str]
    flags: int = 0
    metadata: Dict[str, Any] | None = None
    payload: Optional[memoryview] = None
    is_native: bool = False
    method_id: Optional[int] = None


def _ensure_bytes(data: bytes | bytearray | memoryview | Iterable[int]) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    return bytes(data)


def encode_native_request(
    method_id: int,
    params: Dict[str, Any],
    *,
    create_header,
    method_name: Optional[str] = None,
    payload: Optional[memoryview | bytes | bytearray] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    flags: int = 0,
) -> Tuple[int, bytes]:
    """构造原生协议请求报文."""

    binary_payload = memoryview(payload) if payload is not None else None
    payload_size = len(binary_payload) if binary_payload is not None else 0

    metadata: Dict[str, Any] = {
        "params": params,
        "timestamp": time.time(),
    }
    if method_name:
        metadata["method"] = method_name
    if extra_metadata:
        metadata.update(extra_metadata)

    metadata_bytes = _dumps(metadata)

    header_info = create_header(method_id, len(metadata_bytes) + payload_size)
    request_id = int(header_info.get("request_id", 0))
    header_flags = int(header_info.get("flags", 0)) | FLAG_NATIVE | flags
    if payload_size:
        header_flags |= FLAG_BINARY_PAYLOAD

    header_bytes = HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        HEADER_SIZE,
        method_id,
        request_id,
        header_flags,
        len(metadata_bytes),
        payload_size,
    )

    if binary_payload is None:
        return request_id, header_bytes + metadata_bytes

    # 需要将 header/metadata 与 payload 合并为单一 bytes 以保证消息边界
    return request_id, header_bytes + metadata_bytes + binary_payload.tobytes()


def decode_request(
    raw: bytes | bytearray | memoryview,
    *,
    method_resolver,
) -> RPCRequest:
    """解码任意协议的请求报文."""

    if isinstance(raw, (bytearray, memoryview)):
        buffer = bytes(raw)
    else:
        buffer = raw

    if len(buffer) >= HEADER_SIZE:
        magic = struct.unpack_from("<I", buffer, 0)[0]
        if magic == MAGIC:
            (
                _magic,
                version,
                header_size,
                method_id,
                request_id,
                flags,
                metadata_size,
                payload_size,
            ) = HEADER_STRUCT.unpack_from(buffer, 0)

            if version != VERSION or header_size != HEADER_SIZE:
                raise ValueError("Unsupported RPC header version")

            if len(buffer) < HEADER_SIZE + metadata_size + payload_size:
                raise ValueError("Incomplete RPC message payload")

            metadata_view = memoryview(buffer)[
                HEADER_SIZE : HEADER_SIZE + metadata_size
            ]
            metadata = _loads(metadata_view)

            params = metadata.get("params", {}) if isinstance(metadata, dict) else {}
            method_name = metadata.get("method") if isinstance(metadata, dict) else None
            # Ensure method_name is a string or None
            if method_name is not None and not isinstance(method_name, str):
                method_name = str(method_name)
            if not method_name and callable(method_resolver):
                try:
                    method_name = method_resolver(method_id)
                    # Ensure method_resolver result is also a string
                    if method_name is not None and not isinstance(method_name, str):
                        method_name = str(method_name)
                except Exception:
                    method_name = None

            payload_view: Optional[memoryview] = None
            if payload_size:
                payload_view = memoryview(buffer)[
                    HEADER_SIZE + metadata_size : HEADER_SIZE + metadata_size + payload_size
                ]

            return RPCRequest(
                request_id=request_id,
                method=str(method_name) if method_name else "",
                params=params if isinstance(params, dict) else {},
                method_id=method_id,
                flags=flags,
                metadata=metadata if isinstance(metadata, dict) else {},
                payload=payload_view,
                is_native=True,
            )

    # JSON 兼容路径
    message = _loads(buffer)
    if isinstance(message, dict):
        return RPCRequest(
            request_id=message.get("id") or 0,
            method=message.get("method", ""),
            params=message.get("params", {}),
            flags=0,
            metadata=message,
            payload=None,
            is_native=False,
        )
    raise ValueError("Unsupported RPC request format")


def encode_native_response(
    *,
    request_id: int,
    method_id: Optional[int],
    result: Any = None,
    error: Optional[str] = None,
    flags: int = 0,
    binary_payload: Optional[memoryview | bytes | bytearray] = None,
    metadata: Optional[Dict[str, Any]] = None,
    binary_field_path: Optional[Sequence[str]] = None,
) -> bytes:
    """构造原生协议响应."""

    binary_view = memoryview(binary_payload) if binary_payload is not None else None
    payload_size = len(binary_view) if binary_view is not None else 0

    response_meta: Dict[str, Any] = {
        "id": request_id,
        "result": result,
        "timestamp": time.time(),
    }
    if metadata:
        response_meta.update(metadata)
    if error:
        response_meta["error"] = error

    header_flags = FLAG_NATIVE | flags
    if binary_view is not None and payload_size:
        header_flags |= FLAG_BINARY_PAYLOAD
    if error:
        header_flags |= FLAG_ERROR

    if binary_view is not None and binary_field_path:
        response_meta.setdefault("binary_fields", []).append(
            {
                "path": list(binary_field_path),
                "length": payload_size,
            }
        )

    metadata_bytes = _dumps(response_meta)

    header_bytes = HEADER_STRUCT.pack(
        MAGIC,
        VERSION,
        HEADER_SIZE,
        int(method_id or 0),
        request_id,
        header_flags,
        len(metadata_bytes),
        payload_size,
    )

    if binary_view is None:
        return header_bytes + metadata_bytes

    return header_bytes + metadata_bytes + binary_view.tobytes()


def decode_response(raw: bytes | bytearray | memoryview) -> RPCResponse:
    """解码响应报文，自动识别协议类型."""

    if isinstance(raw, (bytearray, memoryview)):
        buffer = bytes(raw)
    else:
        buffer = raw

    if len(buffer) >= HEADER_SIZE:
        magic = struct.unpack_from("<I", buffer, 0)[0]
        if magic == MAGIC:
            (
                _magic,
                version,
                header_size,
                method_id,
                request_id,
                flags,
                metadata_size,
                payload_size,
            ) = HEADER_STRUCT.unpack_from(buffer, 0)

            if version != VERSION or header_size != HEADER_SIZE:
                raise ValueError("Unsupported RPC response header version")

            if len(buffer) < HEADER_SIZE + metadata_size + payload_size:
                raise ValueError("Incomplete RPC response payload")

            metadata_view = memoryview(buffer)[
                HEADER_SIZE : HEADER_SIZE + metadata_size
            ]
            metadata = _loads(metadata_view)

            result = metadata.get("result") if isinstance(metadata, dict) else None
            error = metadata.get("error") if isinstance(metadata, dict) else None

            payload_view: Optional[memoryview] = None
            if payload_size:
                payload_view = memoryview(buffer)[
                    HEADER_SIZE + metadata_size : HEADER_SIZE + metadata_size + payload_size
                ]

            return RPCResponse(
                request_id=request_id,
                result=result,
                error=error,
                flags=flags,
                metadata=metadata if isinstance(metadata, dict) else {},
                payload=payload_view,
                is_native=True,
                method_id=method_id,
            )

    # JSON 兼容路径
    message = _loads(buffer)
    if isinstance(message, dict):
        return RPCResponse(
            request_id=message.get("id") or 0,
            result=message.get("result"),
            error=message.get("error"),
            metadata=message,
            flags=0,
            payload=None,
            is_native=False,
        )
    raise ValueError("Unsupported RPC response format")


def attach_binary_fields(target: Dict[str, Any], binary_fields: Iterable[Dict[str, Any]], payload: Optional[memoryview]) -> None:
    """按路径将二进制负载绑定到结果字典中."""

    if payload is None:
        return

    for field in binary_fields:
        path = field.get("path")
        if not path:
            continue
        current: Any = target
        try:
            for key in path[:-1]:
                if isinstance(current, dict):
                    current = current.setdefault(key, {})
                else:
                    raise KeyError
            last_key = path[-1]
            if isinstance(current, dict):
                current[last_key] = payload
        except KeyError:
            continue


def prepare_json_payload(result: Dict[str, Any], binary_payload: memoryview) -> Dict[str, Any]:
    """将二进制数据转换为 JSON 友好的结构."""

    encoded = base64.b64encode(binary_payload.tobytes()).decode("ascii")
    prepared = dict(result)
    prepared["transport"] = "base64"
    prepared["data"] = encoded
    prepared.setdefault("metadata", {})
    prepared["metadata"].setdefault("encoding", "arrow-base64")
    return prepared


__all__ = [
    "MAGIC",
    "VERSION",
    "FLAG_NATIVE",
    "FLAG_BATCH",
    "FLAG_BINARY_PAYLOAD",
    "FLAG_ERROR",
    "RPCRequest",
    "RPCResponse",
    "encode_native_request",
    "decode_request",
    "encode_native_response",
    "decode_response",
    "attach_binary_fields",
    "prepare_json_payload",
    "JSON_LIBRARY",
]

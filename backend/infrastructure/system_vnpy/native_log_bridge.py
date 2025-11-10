# -*- coding: utf-8 -*-
"""Shared log ring bridge for multi-process logging."""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import pickle
import queue
import struct
import sys
import threading
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Callable, Iterable, Optional

LOGGER = logging.getLogger("backend.infrastructure.system_vnpy.native_log_bridge")

IS_SUPPORTED = sys.platform == "win32"

MAGIC = 0x4C4F4752
VERSION = 1
HEADER_SIZE = 64
DEFAULT_CAPACITY = 4 * 1024 * 1024


if IS_SUPPORTED:
    _cmpxchg64 = ctypes.windll.kernel32.InterlockedCompareExchange64
    _cmpxchg64.argtypes = [ctypes.c_void_p, ctypes.c_longlong, ctypes.c_longlong]
    _cmpxchg64.restype = ctypes.c_longlong

    _xadd64 = ctypes.windll.kernel32.InterlockedExchangeAdd64
    _xadd64.argtypes = [ctypes.c_void_p, ctypes.c_longlong]
    _xadd64.restype = ctypes.c_longlong
else:  # pragma: no cover - 非 Windows 平台降级
    def _cmpxchg64(ptr, value: int, expected: int) -> int:  # type: ignore[override]
        current = ptr.contents.value  # type: ignore[attr-defined]
        if current == expected:
            ptr.contents.value = value  # type: ignore[attr-defined]
        return current

    def _xadd64(ptr, value: int) -> int:  # type: ignore[override]
        current = ptr.contents.value  # type: ignore[attr-defined]
        ptr.contents.value = current + value  # type: ignore[attr-defined]
        return current


def _atomic_read(ptr) -> int:
    return int(_cmpxchg64(ptr, 0, 0))  # type: ignore[arg-type]


@dataclass
class SharedLogRingStats:
    capacity: int
    pending_bytes: int
    dropped_messages: int


class SharedLogRing:
    __slots__ = (
        "_shm",
        "_header",
        "_buffer",
        "capacity",
        "_write_value",
        "_read_value",
        "_write_ptr",
        "_read_ptr",
        "_dropped",
        "_closed",
    )

    def __init__(self, shm: shared_memory.SharedMemory, *, capacity: int) -> None:
        self._shm = shm
        self.capacity = capacity
        self._header = memoryview(self._shm.buf)[:HEADER_SIZE]
        self._buffer = memoryview(self._shm.buf)[HEADER_SIZE:]
        self._write_value = ctypes.c_longlong.from_buffer(self._header, 16)
        self._read_value = ctypes.c_longlong.from_buffer(self._header, 24)
        self._write_ptr = ctypes.cast(ctypes.addressof(self._write_value), ctypes.POINTER(ctypes.c_longlong))
        self._read_ptr = ctypes.cast(ctypes.addressof(self._read_value), ctypes.POINTER(ctypes.c_longlong))
        self._dropped = 0
        self._closed = False

    @property
    def name(self) -> str:
        return self._shm.name

    def export_token(self) -> str:
        payload = {
            "magic": MAGIC,
            "version": VERSION,
            "name": self._shm.name,
            "capacity": self.capacity,
        }
        raw = json.dumps(payload).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def stats(self) -> SharedLogRingStats:
        write = _atomic_read(self._write_ptr)
        read = _atomic_read(self._read_ptr)
        pending = max(0, min(self.capacity, write - read))
        return SharedLogRingStats(capacity=self.capacity, pending_bytes=pending, dropped_messages=self._dropped)

    def close(self, *, unlink: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._header.release()
        except Exception:
            pass
        try:
            self._buffer.release()
        except Exception:
            pass
        self._shm.close()
        if unlink:
            try:
                self._shm.unlink()
            except FileNotFoundError:
                pass

    def _reserve(self, size: int) -> Optional[int]:
        if size <= 0 or size > self.capacity:
            return None
        for _ in range(1024):
            read = _atomic_read(self._read_ptr)
            write = _atomic_read(self._write_ptr)
            used = write - read
            if used + size > self.capacity:
                return None
            prev = _cmpxchg64(self._write_ptr, write + size, write)  # type: ignore[arg-type]
            if prev == write:
                return write
        return None

    def _write_bytes(self, offset: int, payload: bytes) -> None:
        start = offset % self.capacity
        end = start + len(payload)
        if end <= self.capacity:
            self._buffer[start:end] = payload
        else:
            first = self.capacity - start
            self._buffer[start:] = payload[:first]
            self._buffer[: end - self.capacity] = payload[first:]

    def write(self, item: object) -> bool:
        try:
            packed = pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:
            LOGGER.exception("failed to pickle log record for shared ring")
            return False
        header = struct.pack("<I", len(packed))
        total = len(header) + len(packed)
        position = self._reserve(total)
        if position is None:
            self._dropped += 1
            return False
        self._write_bytes(position, header)
        self._write_bytes(position + len(header), packed)
        return True

    def _consume_one(self) -> Optional[bytes]:
        while True:
            read = _atomic_read(self._read_ptr)
            write = _atomic_read(self._write_ptr)
            if write - read < 4:
                return None
            start = read % self.capacity
            header = self._read_bytes(start, 4)
            if header is None:
                return None
            (length,) = struct.unpack("<I", header)
            if length == 0 or length > self.capacity:
                _xadd64(self._read_ptr, 4)  # type: ignore[arg-type]
                continue
            if write - read < 4 + length:
                return None
            payload = self._read_bytes(start + 4, length)
            if payload is None:
                return None
            _xadd64(self._read_ptr, 4 + length)  # type: ignore[arg-type]
            return payload

    def _read_bytes(self, offset: int, length: int) -> Optional[bytes]:
        start = offset % self.capacity
        end = start + length
        if end <= self.capacity:
            return bytes(self._buffer[start:end])
        first = self.capacity - start
        data = self._buffer[start:].tobytes()
        data += self._buffer[: end - self.capacity].tobytes()
        return data

    def read_batch(self, limit: int = 256) -> Iterable[object]:
        results = []
        for _ in range(max(1, limit)):
            payload = self._consume_one()
            if payload is None:
                break
            try:
                record = pickle.loads(payload)
            except Exception:
                LOGGER.exception("failed to unpickle log record from shared ring")
                continue
            results.append(record)
        return results


class SharedRingQueueAdapter:
    __slots__ = ("_ring", "shared_ring")

    def __init__(self, ring: SharedLogRing) -> None:
        self._ring = ring
        self.shared_ring = True

    def put(self, item: object) -> None:
        if not self._ring.write(item):
            raise queue.Full

    def put_nowait(self, item: object) -> None:
        self.put(item)

    def close(self) -> None:
        self._ring.close()


def create_shared_log_ring(capacity: int = DEFAULT_CAPACITY) -> Optional[SharedLogRing]:
    if not IS_SUPPORTED:
        LOGGER.debug("shared log ring is not supported on this platform")
        return None
    capacity = max(65536, int(capacity))
    total_size = HEADER_SIZE + capacity
    shm = shared_memory.SharedMemory(create=True, size=total_size)
    header = memoryview(shm.buf)[:HEADER_SIZE]
    struct.pack_into("<IIQQ", header, 0, MAGIC, VERSION, capacity, 0)
    struct.pack_into("<qq", header, 16, 0, 0)
    header.release()
    return SharedLogRing(shm, capacity=capacity)


def attach_shared_log_ring(token: str) -> Optional[SharedRingQueueAdapter]:
    if not token:
        return None
    try:
        payload = json.loads(base64.b64decode(token).decode("utf-8"))
    except Exception:
        LOGGER.exception("invalid shared log ring token")
        return None
    if payload.get("magic") != MAGIC:
        LOGGER.error("shared log ring magic mismatch")
        return None
    capacity = int(payload.get("capacity", 0))
    name = payload.get("name")
    if not name or capacity <= 0:
        return None
    total_size = HEADER_SIZE + capacity
    shm = shared_memory.SharedMemory(name=name, create=False, size=total_size)
    ring = SharedLogRing(shm, capacity=capacity)
    return SharedRingQueueAdapter(ring)


class SharedRingConsumer:
    __slots__ = ("_ring", "_callback", "_thread", "_stop_event", "_poll_interval")

    def __init__(
        self,
        ring: SharedLogRing,
        callback: Callable[[object], None],
        *,
        poll_interval: float = 0.002,
        name: str = "shared-log-ring",
    ) -> None:
        self._ring = ring
        self._callback = callback
        self._poll_interval = max(0.0005, float(poll_interval))
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, *, wait: bool = True) -> None:
        self._stop_event.set()
        if wait and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            batch = list(self._ring.read_batch())
            if not batch:
                self._stop_event.wait(self._poll_interval)
                continue
            for item in batch:
                try:
                    self._callback(item)
                except Exception:  # noqa: BLE001
                    LOGGER.exception("shared log ring callback failed")


__all__ = [
    "SharedLogRing",
    "SharedRingQueueAdapter",
    "SharedRingConsumer",
    "SharedLogRingStats",
    "create_shared_log_ring",
    "attach_shared_log_ring",
]

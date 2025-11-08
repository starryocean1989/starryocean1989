# -*- coding: utf-8 -*-
"""
快速运行验证脚本：
- 验证 TDX 批量读取（含零拷贝结果通道）日志与结构输出
- 验证 Windows 原生磁盘拓扑采集结构输出

运行方式：
    python scripts/quick_run_validation.py
"""

import logging
import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict

import pandas as pd

# 确保项目根目录在sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.infrastructure.tdx_asyncio.readers.data_reader import (
    TdxDataReader,
    _deserialize_df_from_shared_memory,
)
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor
from multiprocessing import shared_memory


def setup_logging() -> None:
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=fmt)
    # 放宽各组件日志级别，便于观察细节
    logging.getLogger("TdxDataReader").setLevel(logging.DEBUG)
    logging.getLogger("TdxDataReader.worker").setLevel(logging.DEBUG)
    logging.getLogger("TdxBinaryReader").setLevel(logging.DEBUG)
    logging.getLogger("monitor_toolkit").setLevel(logging.DEBUG)
    logging.getLogger("monitor_system").setLevel(logging.DEBUG)


def demo_zero_copy_channel() -> None:
    print("\n=== 零拷贝通道演示（合成DataFrame） ===")
    df = pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-01", periods=5, freq="D"),
            "open": [10, 10.1, 10.2, 10.3, 10.4],
            "high": [10.5, 10.6, 10.7, 10.8, 10.9],
            "low": [9.8, 9.9, 10.0, 10.1, 10.2],
            "close": [10.2, 10.25, 10.3, 10.35, 10.4],
            "amount": [1000, 1100, 1200, 1300, 1400],
            "volume": [10000, 11000, 12000, 13000, 14000],
        }
    )
    # 生成序列化payload（优先PyArrow IPC，否则回退pickle）
    payload_bytes: bytes
    try:
        import pyarrow as pa  # type: ignore
        table = pa.Table.from_pandas(df, preserve_index=False)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        buf = sink.getvalue()
        try:
            payload_bytes = bytes(buf)
        except Exception:
            payload_bytes = buf.to_pybytes()
        kind = "arrow_ipc"
    except Exception:
        import pickle
        payload_bytes = pickle.dumps(df, protocol=pickle.HIGHEST_PROTOCOL)
        kind = "pickle"

    # 保持共享内存句柄不释放，确保可通过name重新打开
    shm_obj = shared_memory.SharedMemory(name=None, create=True, size=len(payload_bytes))
    shm_obj.buf[: len(payload_bytes)] = payload_bytes
    shm_name = shm_obj.name
    print(f"写入共享内存: name={shm_name}, size={len(payload_bytes)}, kind={kind}")

    # 在句柄仍存活时执行按name的反序列化，模拟跨进程读取
    df2 = _deserialize_df_from_shared_memory(shm_name, len(payload_bytes))
    print(f"反序列化完成: shape={df2.shape}")
    print(df2.head())

    # 清理共享内存
    try:
        shm_obj.close()
        shm_obj.unlink()
    except Exception:
        pass


def demo_tdx_batch_read(tdx_root: str | None = None) -> None:
    print("\n=== TDX批量读取演示（包含零拷贝通道） ===")
    # 允许通过命令行参数覆盖TDX根目录
    if tdx_root:
        reader = TdxDataReader(Path(tdx_root))
    else:
        reader = TdxDataReader()  # 默认路径 C:/new_tdx
    symbols = ["600000", "000001", "300750"]
    print(f"TDX根目录: {reader.tdx_root}")
    if not os.path.exists(str(reader.tdx_root)):
        print("⚠️ 默认TDX目录不存在，读取将返回空DataFrame（验证管道与日志）")

    def progress_cb(done: int, total: int, msg: str):
        print(f"进度: {done}/{total} - {msg}")

    results: Dict[str, pd.DataFrame] = reader.fetch_batch_multiprocess(
        symbols=symbols,
        data_type="day",
        market=None,
        progress_callback=progress_cb,
        num_processes=2,
        max_coroutines=50,
    )

    print("\n读取结果摘要：")
    for sym, df in results.items():
        print(f"- {sym}: shape={df.shape}")
        if not df.empty:
            print(df.head())


def demo_physical_disks_info() -> None:
    print("\n=== 物理磁盘拓扑结构输出（Windows原生采集/缓存） ===")
    sm = SystemMonitor()
    info = sm.get_physical_disks_info()

    # JSON友好化处理（把枚举转为字符串）
    normalized = {}
    for k, v in info.items():
        nv = dict(v)
        dt = nv.get("disk_type")
        if hasattr(dt, "value"):
            nv["disk_type"] = dt.value
        normalized[k] = nv

    print(json.dumps(normalized, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="快速运行验证：TDX读取与磁盘拓扑")
    parser.add_argument(
        "--tdx-root",
        dest="tdx_root",
        type=str,
        default=None,
        help="通达信根目录路径，例如 C:/new_tdx",
    )
    args = parser.parse_args()

    setup_logging()
    demo_zero_copy_channel()
    demo_tdx_batch_read(args.tdx_root)
    demo_physical_disks_info()
# -*- coding: utf-8 -*-
"""
Native扩展模块统一导入

包含所有原生扩展模块：
- native_gil: GIL管理和CPU密集型任务执行器
- native_iocp: 异步文件I/O（Windows IOCP）
- native_ipc: 异步进程间通信（Windows Named Pipe + IOCP）
- native_memory: 内存操作（零拷贝、内存池）
- native_serialization: 序列化（批量、零拷贝）
- native_conversion: 数据转换（批量类型转换、批量字符串操作）
- native_collections: 高性能容器（LRU缓存、优先级队列）
- native_compute: 数值计算（批量数值运算、批量哈希计算）
- native_calendar: 高性能交易日历查询
"""

import importlib

__all__ = []

# 并发/同步 - native_gil
try:
    from .native_gil import (
        release_gil,
        restore_gil,
        execute_cpu_task,
        ThreadSafeQueue,
        ThreadSafeCounter,
        LockFreeQueue,
        LockFreeHashMap,
        HighPerfEvent,
        HighPerfCondition,
    )
    __all__.extend([
        'release_gil',
        'restore_gil',
        'execute_cpu_task',
        'ThreadSafeQueue',
        'ThreadSafeCounter',
        'LockFreeQueue',
        'LockFreeHashMap',
        'HighPerfEvent',
        'HighPerfCondition',
    ])
except ImportError:
    pass

# I/O操作 - native_iocp
try:
    from .native_iocp import (
        aopen,
        AsyncIOCPFile,
    )
    __all__.extend([
        'aopen',
        'AsyncIOCPFile',
    ])
    # 批量文件操作（可选）
    try:
        from .native_iocp import (
            batch_file_exists,
            batch_file_delete,
            batch_file_stat,
            fast_dir_walk,
            fast_dir_list,
        )
        __all__.extend([
            'batch_file_exists',
            'batch_file_delete',
            'batch_file_stat',
            'fast_dir_walk',
            'fast_dir_list',
        ])
    except ImportError:
        pass
except ImportError:
    pass

# 文件监控 - native_fs
try:
    from .native_fs import (
        FS_WATCH_AVAILABLE,
        DirectoryWatcher,
        watch_directory,
    )
    __all__.extend([
        'FS_WATCH_AVAILABLE',
        'DirectoryWatcher',
        'watch_directory',
    ])
except ImportError:
    FS_WATCH_AVAILABLE = False  # type: ignore
    DirectoryWatcher = None  # type: ignore
    watch_directory = None  # type: ignore

# IPC通信 - native_ipc
try:
    from .native_ipc import (
        AsyncIPCPipe,
        aopen_server,
        aopen_client,
    )
    __all__.extend([
        'AsyncIPCPipe',
        'aopen_server',
        'aopen_client',
    ])
except ImportError:
    pass

# 负载均衡优化 - native_load_balancer
try:
    from .native_load_balancer import (
        LOAD_BALANCER_AVAILABLE as NATIVE_LOAD_BALANCER_AVAILABLE,
        optimize as native_load_balancer_optimize,
    )
    __all__.extend([
        'NATIVE_LOAD_BALANCER_AVAILABLE',
        'native_load_balancer_optimize',
    ])
except ImportError:
    NATIVE_LOAD_BALANCER_AVAILABLE = False  # type: ignore
    native_load_balancer_optimize = None  # type: ignore

# 内存操作 - native_memory
try:
    from .native_memory import (
        ZeroCopyMemory,
        MemoryPool,
        batch_alloc,
        batch_free,
    )
    __all__.extend([
        'ZeroCopyMemory',
        'MemoryPool',
        'batch_alloc',
        'batch_free',
    ])
except ImportError:
    pass

# 序列化 - native_serialization
try:
    from .native_serialization import (
        batch_serialize,
        batch_deserialize,
        zero_copy_serialize,
    )
    __all__.extend([
        'batch_serialize',
        'batch_deserialize',
        'zero_copy_serialize',
    ])
except ImportError:
    pass

# Socket 缓冲指标 - native_socket_metrics
try:
    from .native_socket_metrics import (
        SOCKET_METRICS_AVAILABLE,
        get_socket_metrics,
    )
    __all__.extend([
        'SOCKET_METRICS_AVAILABLE',
        'get_socket_metrics',
    ])
except ImportError:
    SOCKET_METRICS_AVAILABLE = False  # type: ignore
    get_socket_metrics = None  # type: ignore

# 交易日历 - native_calendar
try:
    from .native_calendar import (
        NativeCalendar,
        NATIVE_CALENDAR_AVAILABLE,
    )
    __all__.extend([
        'NativeCalendar',
        'NATIVE_CALENDAR_AVAILABLE',
    ])
except ImportError:
    NATIVE_CALENDAR_AVAILABLE = False  # type: ignore
    NativeCalendar = None  # type: ignore

# SMART 监控 - native_smart_monitor
try:
    _native_smart_monitor_module = importlib.import_module(
        ".native_smart_monitor", __name__
    )
except ImportError:
    SMART_MONITOR_AVAILABLE = False  # type: ignore
    get_drive_temperature_data = None  # type: ignore
else:
    SMART_MONITOR_AVAILABLE = bool(
        getattr(_native_smart_monitor_module, "SMART_MONITOR_AVAILABLE", False)
    )
    get_drive_temperature_data = getattr(
        _native_smart_monitor_module, "get_drive_temperature_data", None
    )
    __all__.extend([
        'SMART_MONITOR_AVAILABLE',
        'get_drive_temperature_data',
    ])

# 数据转换 - native_conversion
try:
    from .native_conversion import (
        batch_convert,
        batch_encode,
        batch_decode,
    )
    __all__.extend([
        'batch_convert',
        'batch_encode',
        'batch_decode',
    ])
except ImportError:
    pass

# DataFrame 扩展 - native_dataframe_ops
try:
    from .native_dataframe_ops import (
        DATAFRAME_OPS_AVAILABLE,
        dataframe_to_records,
        dataframe_quality_counters,
    )
    __all__.extend([
        'DATAFRAME_OPS_AVAILABLE',
        'dataframe_to_records',
        'dataframe_quality_counters',
    ])
except ImportError:
    DATAFRAME_OPS_AVAILABLE = False  # type: ignore
    dataframe_to_records = None  # type: ignore
    dataframe_quality_counters = None  # type: ignore

# 流式统计 - native_statistics
STATISTICS_AVAILABLE: bool = False
create_streaming_metric = None
StreamingMetricHandle = None
try:
    from .native_statistics import (
        STATISTICS_AVAILABLE as _STATISTICS_AVAILABLE,
        create_streaming_metric as _create_streaming_metric,
        StreamingMetricHandle as _StreamingMetricHandle,
    )
    STATISTICS_AVAILABLE = bool(_STATISTICS_AVAILABLE)
    create_streaming_metric = _create_streaming_metric
    StreamingMetricHandle = _StreamingMetricHandle
except ImportError:
    pass
__all__.extend([
    'STATISTICS_AVAILABLE',
    'create_streaming_metric',
    'StreamingMetricHandle',
])

# 高性能容器 - native_collections
try:
    from .native_collections import (
        HighPerfLRUCache,
        HighPerfPriorityQueue,
    )
    __all__.extend([
        'HighPerfLRUCache',
        'HighPerfPriorityQueue',
    ])
except ImportError:
    pass

# 数值计算 - native_compute
try:
    from .native_compute import (
        batch_compute,
        batch_hash,
    )
    __all__.extend([
        'batch_compute',
        'batch_hash',
    ])
except ImportError:
    pass

# 日志缓冲 - native_log_pipeline
try:
    from .native_log_pipeline import (  # type: ignore
        Pipeline,
        create,
        flush_and_close,
        install,
    )
    __all__.extend([
        'Pipeline',
        'create',
        'install',
        'flush_and_close',
        'create_log_pipeline',
    ])
    create_log_pipeline = install
except ImportError:
    Pipeline = None  # type: ignore
    create = install = flush_and_close = None  # type: ignore
    create_log_pipeline = None  # type: ignore

# 进程指标 - native_process_metrics
try:
    from .native_process_metrics import (  # type: ignore
        PROCESS_METRICS_AVAILABLE,
        get_process_snapshot,
        get_system_metrics,
    )
    __all__.extend([
        'PROCESS_METRICS_AVAILABLE',
        'get_process_snapshot',
        'get_system_metrics',
    ])
except ImportError:
    PROCESS_METRICS_AVAILABLE = False  # type: ignore
    get_process_snapshot = None  # type: ignore
    get_system_metrics = None  # type: ignore

# 网络探测 - native_netprobe
try:
    from .native_netprobe import (  # type: ignore
        NETPROBE_AVAILABLE,
        batch_test_connections,
        test_connection,
    )
    __all__.extend([
        'NETPROBE_AVAILABLE',
        'batch_test_connections',
        'test_connection',
    ])
except ImportError:
    NETPROBE_AVAILABLE = False  # type: ignore
    batch_test_connections = None  # type: ignore
    test_connection = None  # type: ignore

# VNPY 数据转换 - native_vnpy_conversion
try:
    from . import native_vnpy_conversion as _vnpy_conversion  # type: ignore
    VNPY_CONVERSION_AVAILABLE = getattr(_vnpy_conversion, "CONVERSION_AVAILABLE", False)
    vnpy_batch_convert = getattr(_vnpy_conversion, "batch_convert", None)
    vnpy_convert_one = getattr(_vnpy_conversion, "convert_one", None)
    __all__.extend([
        'VNPY_CONVERSION_AVAILABLE',
        'vnpy_batch_convert',
        'vnpy_convert_one',
    ])
except ImportError:
    VNPY_CONVERSION_AVAILABLE = False  # type: ignore
    vnpy_batch_convert = vnpy_convert_one = None  # type: ignore

# 技术指标 - native_indicator
try:
    from .native_indicator import (  # type: ignore
        CORE_AVAILABLE as NATIVE_INDICATOR_CORE_AVAILABLE,
        INDICATOR_AVAILABLE as NATIVE_INDICATOR_AVAILABLE,
        calculate_indicator,
        calculate_indicator_batch,
        sma,
        ema,
        macd,
        rsi,
    )
    __all__.extend([
        'NATIVE_INDICATOR_CORE_AVAILABLE',
        'NATIVE_INDICATOR_AVAILABLE',
        'calculate_indicator',
        'calculate_indicator_batch',
        'sma',
        'ema',
        'macd',
        'rsi',
    ])
except ImportError:
    NATIVE_INDICATOR_CORE_AVAILABLE = False  # type: ignore
    NATIVE_INDICATOR_AVAILABLE = False  # type: ignore
    calculate_indicator = calculate_indicator_batch = None  # type: ignore
    sma = ema = macd = rsi = None  # type: ignore

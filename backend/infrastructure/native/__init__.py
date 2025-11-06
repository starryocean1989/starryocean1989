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
"""

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

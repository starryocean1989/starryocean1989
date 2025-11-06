# -*- coding: utf-8 -*-
# Native Collections扩展模块

## 概述

提供高性能数据结构，包括LRU缓存和优先级队列。

### 核心特性

- ✅ **高性能LRU缓存**：C实现的双向链表，线程安全
- ✅ **高性能优先级队列**：C实现的链表，线程安全

## 编译

```bash
cd backend/infrastructure/native/native_collections
python setup.py build_ext --inplace
```

## API

### LRU缓存

```python
from backend.infrastructure.native.native_collections import HighPerfLRUCache

cache = HighPerfLRUCache(10)  # maxsize
cache.set("key1", "value1")
cache.set("key2", "value2")
value = cache.get("key1")
size = cache.size()
```

### 优先级队列

```python
from backend.infrastructure.native.native_collections import HighPerfPriorityQueue

queue = HighPerfPriorityQueue()
queue.put("item1", 1)   # item, priority
queue.put("item2", 2)
queue.put("item3", 3)
item = queue.get()  # "item3" (最高优先级)
size = queue.size()
```

## 注意事项

- 使用C实现的双向链表（LRU缓存）和链表（优先级队列）
- 使用Windows临界区保证线程安全
- 仅支持Windows平台

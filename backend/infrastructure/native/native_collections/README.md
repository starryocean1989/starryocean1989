# -*- coding: utf-8 -*-
# Native Collections扩展模块

## 概述

提供高性能数据结构，包括LRU缓存、优先级队列以及组合撮合缓存。

### 核心特性

- ✅ **高性能LRU缓存**：C实现的双向链表，线程安全
- ✅ **高性能优先级队列**：C实现的链表，线程安全
- ✅ **组合撮合缓存**：面向网关的持仓/资金/成交原生容器，支持常数时间更新与成交聚合统计

## 编译

```bash
cd backend/infrastructure/native/native_collections
python setup.py build_ext --inplace
```

> 推荐使用 `backend/infrastructure/native/compile_all.bat` 一键构建，脚本会顺序编译全部扩展（含本模块），遇到错误自动暂停便于排查。

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

### 组合撮合缓存

```python
from backend.infrastructure.native.native_collections import HighPerfMatchCache

cache = HighPerfMatchCache()
cache.upsert_position(position)  # position需包含 gateway_name/vt_symbol/direction
cache.upsert_account(account)    # account需包含 gateway_name/accountid
cache.upsert_trade(trade)        # trade需包含 gateway_name/vt_tradeid/vt_symbol/direction/price/volume

positions = cache.get_positions("CTP")
accounts = cache.get_accounts("CTP")
trades = cache.get_trades("CTP")
stats = cache.get_trade_stats("CTP", "rb2405.SHFE")
```

## 注意事项

- 使用C实现的双向链表（LRU缓存）和链表（优先级队列）
- 使用Windows临界区保证线程安全
- 仅支持Windows平台

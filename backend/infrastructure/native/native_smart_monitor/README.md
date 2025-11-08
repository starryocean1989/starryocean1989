# -*- coding: utf-8 -*-
# native_smart_monitor 扩展

`native_smart_monitor` 提供 Windows 平台下基于 `DeviceIoControl` 的硬盘 SMART 原生采集能力，避免依赖 WMI/COM，降低监控进程的 CPU 占用与失败率。

## 提供的能力

- `get_drive_temperature_data()`
  - 枚举 `PhysicalDrive0..N`，查询设备基本信息（型号、序列号、容量、总线类型）。
  - 发送 SMART `SMART_RCV_DRIVE_DATA` 指令解析关键属性（温度、开机时长、坏道计数等）。
  - 根据温度与坏道情况给出简易健康状态（ok/warning/critical/unavailable）。
  - 以 `List[Dict]` 返回结构化数据，字段包括：
    - `drive_index`: 物理磁盘序号
    - `device_path`: `\\.\PhysicalDriveX`
    - `model` / `serial_number` / `bus_type`
    - `size_bytes`
    - `smart_supported`
    - `temperature_celsius` / `warning_threshold_celsius` / `critical_threshold_celsius`
    - `reallocated_sectors` / `pending_sectors` / `uncorrectable_errors` / `power_on_hours`
    - `status`: `ok` / `warning` / `critical` / `unavailable`
    - `attributes`: 原始 SMART 属性列表（每项包含 id/value/worst/raw）

## 编译

```bash
cd backend/infrastructure/native/native_smart_monitor
python setup.py build_ext --inplace
```

或使用一键脚本：

```bash
cd backend/infrastructure/native
compile_all.bat
```

## 使用示例

```python
from backend.infrastructure.native.native_smart_monitor import (
    SMART_MONITOR_AVAILABLE,
    get_drive_temperature_data,
)

if SMART_MONITOR_AVAILABLE:
    drives = get_drive_temperature_data()
    for drive in drives:
        print(drive["device_path"], drive["temperature_celsius"], drive["status"])
else:
    print("native_smart_monitor 不可用")
```

## 降级策略

- 模块导入失败时，`SMART_MONITOR_AVAILABLE = False`，调用接口会抛出 `ImportError`。
- 个别磁盘因权限或硬件限制无法读取 SMART 信息时，该磁盘会标记 `smart_supported = False`，其余字段尽量保留（型号、容量等）。



# -*- coding: utf-8 -*-
# Data Module vnpy 集成完成说明

## 概述

已成功完成 data_module_vnpy 模块的三个 v2.0 新功能的前后端集成：
1. **轮询转推送网关** (Polling Gateway)
2. **虚拟推送网关** (Virtual Gateway)
3. **数据标准化读取器** (TDX Data Reader)

## 完成的工作

### 1. 后端服务层扩展

#### data_center_service.py
- ✅ 删除 `data_engine` 数据源
- ✅ 添加 `polling_gateway` 和 `virtual_gateway` 数据源
- ✅ 新增方法：
  - `start_polling_gateway(config)` - 启动轮询转推送网关
  - `stop_polling_gateway()` - 停止轮询网关
  - `get_polling_gateway_status()` - 获取轮询网关状态
  - `start_virtual_gateway(config)` - 启动虚拟推送网关
  - `stop_virtual_gateway()` - 停止虚拟网关
  - `get_virtual_gateway_status()` - 获取虚拟网关状态

#### system_manager_service.py
- ✅ 新增数据标准化读取器方法：
  - `get_available_data_readers()` - 获取可用的数据读取器列表
  - `read_tdx_data(config)` - 读取通达信数据并标准化保存
  - `get_tdx_reader_config()` - 获取通达信读取器配置

### 2. 前端UI更新

#### 数据中心 UI (data_center/main_view.py)
- ✅ 删除 `data_engine` 数据源
- ✅ 添加 `轮询转推送` 数据源，包含：
  - 配置对话框（轮询间隔、订阅品种）
  - 启动/停止按钮
  - 状态显示
- ✅ 添加 `虚拟推送` 数据源，包含：
  - 配置对话框（起始时间、推送速度、订阅品种）
  - 启动/停止按钮
  - 状态显示
- ✅ 新增方法：
  - `_configure_gateway(gateway_id)` - 配置网关
  - `_start_gateway(gateway_id)` - 启动网关
  - `_stop_gateway(gateway_id)` - 停止网关

#### 系统管理 UI (system_manager/main_view.py)
- ✅ 完全重构工具集合界面
- ✅ 添加数据标准化读取器面板，包含：
  - 数据源类型选择（通达信）
  - 数据类型选择（日线/5分钟线/1分钟线）
  - 市场选择（上证/深证/北证）
  - 通达信根目录配置
  - 品种代码输入
  - 批量读取并保存按钮
  - 状态显示
- ✅ 新增方法：
  - `_browse_tdx_root()` - 浏览通达信根目录
  - `_load_tdx_reader_config()` - 加载配置
  - `_read_and_save_tdx_data()` - 读取并保存数据

## 功能说明

### 轮询转推送网关

**用途**：将 mootdx 等轮询型数据源转换为推送型数据源，符合 vnpy gateway 标准。

**配置项**：
- 轮询间隔：1-600秒（默认60秒）
- 订阅品种：逗号分隔的品种代码

**使用流程**：
1. 在数据中心界面 → 数据源管理
2. 点击"轮询转推送"行的"配置"按钮
3. 填写轮询间隔和订阅品种
4. 点击"启动"按钮
5. 网关将在交易时间段自动轮询并推送数据

### 虚拟推送网关

**用途**：在非交易时段使用历史数据模拟实时推送，用于回测和测试。

**配置项**：
- 起始时间：选择历史数据的起始时间点
- 推送速度：0.1-10.0倍（1.0为实时速度）
- 订阅品种：逗号分隔的品种代码

**使用流程**：
1. 在数据中心界面 → 数据源管理
2. 点击"虚拟推送"行的"配置"按钮
3. 选择起始时间、推送速度和订阅品种
4. 点击"启动"按钮
5. 网关将从指定时间点开始按顺序推送历史数据

**注意**：轮询网关和虚拟网关互斥，同时只能运行一个。

### 数据标准化读取器

**用途**：读取通达信本地二进制数据文件，并标准化保存为 Parquet 格式。

**配置项**：
- 数据源类型：通达信（未来可扩展其他类型）
- 数据类型：日线/5分钟线/1分钟线
- 市场：上证/深证/北证
- 通达信根目录：例如 `C:\new_tdx`
- 品种代码：逗号分隔的6位代码

**数据路径映射**：
- 日线数据：`{tdx_root}/vipdoc/{market}/lday/{symbol}.day`
- 5分钟线：`{tdx_root}/vipdoc/{market}/fzline/{symbol}.lc5`
- 1分钟线：`{tdx_root}/vipdoc/{market}/minline/{symbol}.lc1`

**使用流程**：
1. 在系统管理界面 → 工具集合
2. 选择数据类型和市场
3. 输入通达信根目录（或点击浏览按钮）
4. 输入品种代码（例如：600000,000001,000002）
5. 点击"批量读取并保存"按钮
6. 查看状态显示，确认读取结果

## 技术要点

### 网关生命周期管理
- 使用 vnpy 的 `MainEngine` 和 `EventEngine`
- 网关状态：未连接、运行中、已停止
- 确保同时只有一个推送网关运行（互斥控制）

### 数据流转
```
UI → DataCenterService → data_module_vnpy (底层包)
↑                                        ↓
└─────── 状态/事件推送 ←─────── EventEngine
```

### 错误处理
- 配置验证：起始时间格式、通达信目录有效性
- 运行时错误：数据源连接失败、文件不存在
- UI友好提示：使用 show_error/show_info/show_warning

## 文件清单

### 修改的文件
1. `backend/services/data_center_service.py` - 添加网关管理方法（+330行）
2. `backend/services/system_manager_service.py` - 添加读取器方法（+164行）
3. `ui/components/data_center/main_view.py` - 更新数据源管理UI（+190行）
4. `ui/components/system_manager/main_view.py` - 添加读取器工具面板（+170行）

### 底层包文件（已存在，无需修改）
- `backend/infrastructure/data_module_vnpy/polling_gateway.py`
- `backend/infrastructure/data_module_vnpy/virtual_gateway.py`
- `backend/infrastructure/data_module_vnpy/data_readers/tdx_reader.py`

## 测试建议

### 轮询网关测试
1. 配置几个测试品种（如：600000,000001）
2. 设置轮询间隔为10秒（便于测试）
3. 启动网关，观察日志输出
4. 检查是否在交易时间正常轮询
5. 停止网关，验证清理逻辑

### 虚拟网关测试
1. 确保本地有历史1分钟线数据
2. 配置起始时间为过去某个有数据的时间点
3. 设置推送速度为10.0（加快测试）
4. 启动网关，观察数据推送
5. 停止网关，验证清理逻辑

### 数据读取器测试
1. 确认通达信软件已安装且有数据
2. 配置通达信根目录
3. 输入1-2个测试品种代码
4. 执行批量读取
5. 检查数据是否正确保存到 Parquet 文件
6. 验证数据格式和完整性

## 已知限制

1. **轮询网关**：
   - 单服务器连接（未实现多服务器并行）
   - 交易时间判断为硬编码（不支持节假日判断）

2. **虚拟网关**：
   - 仅支持1分钟线数据
   - 需要预先下载历史数据

3. **数据读取器**：
   - 当前仅支持通达信格式
   - 批量读取无进度显示（未来可增强）

## 后续优化建议

1. 添加网关运行状态实时刷新
2. 虚拟网关增加暂停/恢复功能
3. 数据读取器增加进度条
4. 配置持久化到配置文件
5. 增加更多数据格式支持

## 总结

所有计划的功能已完整实现，前后端链路打通，可以开始使用和测试。如遇到问题，请查看日志文件：
- `logs/terminal_v0.50.log` - 主日志
- `logs/backend_process.log` - 后端进程日志

集成完成时间：2024-10-11


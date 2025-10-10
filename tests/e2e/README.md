# 数据中心E2E测试文档

## 概述

本目录包含数据中心模块的端到端（E2E）测试，特别是"重新加载品种"按钮功能的完整测试流程。

## 测试文件结构

```
tests/e2e/
├── __init__.py                          # 包初始化
├── conftest.py                          # 测试夹具配置
├── test_data_center_reload_symbols.py   # 品种重载E2E测试
└── README.md                            # 本文档
```

## 测试覆盖范围

### 主测试套件：`TestDataCenterReloadSymbols`

#### 1. `test_symbol_cache_generation` - 测试点1：缓存文件生成验证

**测试目标**：验证点击"重新加载品种"按钮后，系统能正确生成包含6000-7000个品种的缓存文件。

**验证标准**：
- ✅ 文件存在：`data/cache/stock_list.parquet`
- ✅ 文件大小 > 100KB（确保不是空文件）
- ✅ 数据结构正确：包含必需字段（code, name, market等）
- ✅ 品种总数：6000 <= count <= 7000
- ✅ 包含过滤后的API品种（5200+个）
- ✅ 包含spblock.dat解析品种（如果配置了通达信路径）
- ✅ 无重复品种代码

**技术实现**：
- 使用真实的 mootdx API 调用
- 调用 `china_stock_engine.reload_stock_list()`
- 读取并验证 Parquet 格式的缓存文件

#### 2. `test_frontend_list_update` - 测试点2：前端列表更新验证

**测试目标**：验证缓存更新后，前端品种列表组件能自动刷新并正确展示数据。

**验证标准**：
- ✅ `DataCenter.all_symbols_data` 已更新
- ✅ 数据数量与缓存一致
- ✅ `symbols_count_label` 显示正确数量
- ✅ `symbols_table` 已渲染数据
- ✅ 表格行数符合分页设置（默认50行/页）
- ✅ 可以进行筛选和搜索操作

**技术实现**：
- 使用 pytest-qt 测试 PySide6 界面
- 模拟用户点击按钮
- 验证 UI 组件状态和数据
- 测试交互功能（筛选、搜索）

#### 3. `test_complete_reload_flow` - 完整E2E集成测试

**测试目标**：端到端验证完整的用户操作流程。

**测试流程**：
```
用户点击按钮 → API调用 → 缓存生成 → 前端更新 → UI渲染
```

**验证点**：
- 缓存文件在合理时间内生成
- 缓存数据符合质量标准
- 前端数据与缓存保持一致
- UI正确展示品种列表

### 快速测试（冒烟测试）

#### `test_service_availability` - 服务可用性测试

验证数据中心服务和 ChinaStockEngine 是否正确初始化。

#### `test_widget_creation` - 界面组件创建测试

验证数据中心界面组件及其关键UI元素是否正确创建。

## 运行测试

### 前置条件

1. **安装依赖**：
```bash
pip install pytest pytest-qt pytest-timeout pandas
```

2. **环境要求**：
- Python 3.10+
- 完整的后端服务环境
- PySide6 Qt环境
- 网络连接（真实API调用）

### 运行命令

#### 运行所有E2E测试
```bash
pytest tests/e2e/ -v
```

#### 运行特定测试文件
```bash
pytest tests/e2e/test_data_center_reload_symbols.py -v
```

#### 运行特定测试用例
```bash
# 只运行测试点1
pytest tests/e2e/test_data_center_reload_symbols.py::TestDataCenterReloadSymbols::test_symbol_cache_generation -v

# 只运行测试点2
pytest tests/e2e/test_data_center_reload_symbols.py::TestDataCenterReloadSymbols::test_frontend_list_update -v

# 只运行完整E2E测试
pytest tests/e2e/test_data_center_reload_symbols.py::TestDataCenterReloadSymbols::test_complete_reload_flow -v
```

#### 使用标记筛选
```bash
# 运行所有数据中心相关测试
pytest -m "data_center" -v

# 运行所有E2E测试
pytest -m "e2e" -v

# 组合标记
pytest -m "e2e and data_center" -v
```

#### 快速冒烟测试
```bash
# 只运行快速测试（不包含耗时的完整测试）
pytest tests/e2e/test_data_center_reload_symbols.py::test_service_availability -v
pytest tests/e2e/test_data_center_reload_symbols.py::test_widget_creation -v
```

### 测试输出

测试运行时会输出详细的日志信息，包括：
- API调用进度
- 缓存文件验证结果
- 市场品种分布统计
- UI更新状态
- 各阶段耗时

示例输出：
```
===============================================================================
开始测试点1：验证缓存文件生成
===============================================================================
调用china_stock_engine.reload_stock_list()...
API调用完成，耗时: 45.32 秒
✅ API调用成功
✅ 缓存文件存在: data/cache/stock_list.parquet
✅ 缓存文件大小合理: 325.48 KB
✅ 数据结构正确，包含必需字段: ['code', 'name', 'market']
✅ 品种总数在预期范围内: 6453 (6000-7000)
✅ 无重复品种代码
✅ 包含API筛选的品种: 5234 个 (预期5200+)
✅ 包含spblock.dat解析的品种: 1219 个
市场分布:
  - 上证A股: 2145 个
  - 深证A股: 2987 个
  - 北证A股: 102 个
  - T+0基金: 876 个
  - 含可转债: 343 个
===============================================================================
✅ 测试点1通过：缓存文件生成成功
   - 总品种数: 6453
   - 文件路径: data/cache/stock_list.parquet
===============================================================================
```

## 测试配置

### 超时设置

- **主测试套件**：180秒（真实API调用需要时间）
- **快速测试**：30秒

### 夹具（Fixtures）

测试使用以下夹具：

1. **`qapp`**（会话级别）：Qt应用实例
2. **`cache_dir`**（函数级别）：缓存目录，自动备份和恢复
3. **`data_center_service`**（函数级别）：数据中心服务实例
4. **`data_center_widget`**（函数级别）：数据中心界面组件
5. **`china_stock_engine`**（函数级别）：ChinaStockEngine实例

### 自动清理

测试会自动：
- 备份现有缓存文件
- 测试完成后恢复备份
- 清理测试创建的UI组件
- 不会影响开发环境

## 故障排查

### 常见问题

#### 1. 测试超时
**症状**：测试在180秒内未完成
**原因**：网络慢或API响应慢
**解决**：
- 检查网络连接
- 增加超时时间：`@pytest.mark.timeout(300)`
- 使用更快的网络环境

#### 2. 品种数量不符合预期
**症状**：品种总数不在6000-7000之间
**原因**：
- API返回数据异常
- spblock.dat文件不可用或已过期
**解决**：
- 检查 mootdx API 状态
- 更新 spblock.dat 文件
- 检查通达信路径配置

#### 3. UI组件未更新
**症状**：`test_frontend_list_update` 失败
**原因**：Qt事件循环未正确处理
**解决**：
- 增加等待时间
- 检查 `wait_for_ui_update` 函数
- 确保Qt应用正确初始化

#### 4. 缓存文件损坏
**症状**：无法读取 Parquet 文件
**原因**：文件写入未完成或格式错误
**解决**：
- 删除缓存文件重新生成
- 检查磁盘空间
- 检查文件权限

### 调试技巧

#### 1. 增加日志输出
```bash
pytest tests/e2e/test_data_center_reload_symbols.py -v -s --log-cli-level=DEBUG
```

#### 2. 进入调试模式
```bash
pytest tests/e2e/test_data_center_reload_symbols.py --pdb
```

#### 3. 只运行失败的测试
```bash
pytest tests/e2e/test_data_center_reload_symbols.py --lf
```

#### 4. 查看详细的traceback
```bash
pytest tests/e2e/test_data_center_reload_symbols.py -v --tb=long
```

## 性能指标

### 预期执行时间

| 测试用例 | 预期时间 | 说明 |
|---------|---------|------|
| `test_symbol_cache_generation` | 30-60秒 | 取决于网络速度 |
| `test_frontend_list_update` | 30-60秒 | 包含UI交互 |
| `test_complete_reload_flow` | 60-120秒 | 完整流程 |
| `test_service_availability` | < 5秒 | 快速检查 |
| `test_widget_creation` | < 5秒 | 快速检查 |

### 资源使用

- **内存**：约200-300MB（加载6000+品种数据）
- **磁盘**：缓存文件约200-400KB
- **网络**：约5-10MB下载（API请求）

## 持续集成

### CI/CD配置示例

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-qt pytest-timeout

      - name: Run E2E tests
        run: |
          pytest tests/e2e/ -v --timeout=180
```

## 维护说明

### 更新测试数据

如果品种数量范围需要调整：

1. 修改 `validate_cache_file()` 中的验证范围
2. 更新文档中的说明
3. 相应调整断言条件

### 添加新测试

1. 在 `test_data_center_reload_symbols.py` 中添加新的测试方法
2. 使用合适的 pytest 标记
3. 更新本文档
4. 确保测试相互独立

## 相关文档

- [pytest文档](https://docs.pytest.org/)
- [pytest-qt文档](https://pytest-qt.readthedocs.io/)
- [PySide6文档](https://doc.qt.io/qtforpython/)
- [数据中心模块功能链条](../../docs/3.需求与底层功能映射/数据中心模块功能链条和底层功能来源.md)

## 联系方式

如有问题或建议，请联系项目维护者或提交Issue。


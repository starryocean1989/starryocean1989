# -*- coding: utf-8 -*-
# E2E端到端测试套件

## 📋 概述

本目录包含完整的E2E端到端测试体系，使用真实后端服务验证所有功能链路。

## 🎯 测试策略

### E2E端到端测试（真实后端）

- **目标**: 验证真实的数据流和完整业务流程
- **特点**: 使用真实的后端服务、VnPy和数据库
- **优势**: 发现集成问题，验证数据一致性，确保生产可用性
- **覆盖**: 21个测试用例，覆盖所有核心业务流程
- **运行**: `python tests/run_e2e_tests.py`

## 🔄 测试架构

```
tests/
├── test_e2e/                        # E2E端到端测试（真实后端）
│   ├── test_e2e_symbol_cache.py     # 品种缓存与展示
│   ├── test_e2e_data_download.py    # 增量数据下载
│   ├── test_e2e_backtest.py         # 策略回测引擎
│   ├── test_e2e_datasource_management.py  # 数据源管理
│   ├── test_e2e_local_data_query.py       # 本地数据查询
│   ├── test_e2e_data_quality_check_repair.py  # 数据质量检查与修复
│   ├── test_e2e_data_gap_detection.py     # 数据缺口检测
│   ├── test_e2e_download_progress_monitoring.py  # 下载进度监控
│   ├── test_e2e_symbol_filter_pagination.py    # 品种筛选与分页
│   ├── test_e2e_market_chart_display.py   # 行情图表显示
│   ├── test_e2e_market_board_indicators.py  # 行情看板指标
│   ├── test_e2e_realtime_data_recording.py  # 实时数据推送与录制
│   ├── test_e2e_strategy_instance_lifecycle.py  # 策略实例生命周期
│   ├── test_e2e_vnpy_strategy_template_adaptation.py  # VnPy策略模板适配
│   ├── test_e2e_gateway.py              # 交易网关连接
│   ├── test_e2e_portfolio_monitoring.py  # 组合监控
│   ├── test_e2e_alert_management.py     # 告警管理
│   ├── test_e2e_service_health_check.py  # 服务健康检查
│   ├── test_e2e_ai_assistant_integration.py  # AI助手集成
│   ├── conftest.py                      # E2E测试配置
│   └── utils/                           # E2E测试工具
│       ├── app_runner.py                # 后端应用启动器
│       ├── db_helper.py                 # VnPy数据库验证工具
│       ├── service_accessor.py          # 后端服务状态访问器
│       ├── wait_helpers.py              # 异步等待助手
│       ├── strategy_helper.py           # 策略验证助手
│       └── chart_helper.py              # 图表验证助手
│
├── conftest.py                          # 全局pytest配置
├── run_e2e_tests.py                     # E2E测试运行脚本
├── requirements-test.txt                # 测试依赖
└── reports/                             # 测试报告目录
    └── test_results.html                # HTML测试报告
```

## 🚀 快速开始

### 环境准备

1. **安装测试依赖**
   ```bash
   pip install -r requirements-test.txt
   ```

2. **配置数据库**
   - 确保VnPy数据库配置正确
   - 检查 `config/terminal_config.json` 中的数据库设置

3. **启动后端服务**（可选，测试会自动启动）
   ```bash
   python start_terminal.py
   ```

### 运行测试

#### 运行所有E2E测试
```bash
python tests/run_e2e_tests.py
```

#### 运行特定测试文件
```bash
pytest tests/test_e2e/test_e2e_symbol_cache.py -v
```

#### 运行特定测试用例
```bash
pytest tests/test_e2e/test_e2e_data_download.py::TestDataDownloadE2E::test_incremental_download_with_cache -v
```

#### 只运行标记为e2e的测试
```bash
pytest -m e2e -v
```

#### 生成HTML报告
```bash
pytest tests/test_e2e/ --html=tests/reports/test_results.html --self-contained-html
```

## 📊 测试覆盖范围

### 1. 数据中心模块 (9个测试)

#### 1.1 品种列表管理
- ✅ test_e2e_symbol_cache.py
  - 品种列表缓存生成
  - 品种列表UI展示
  - 缓存快速刷新

#### 1.2 数据下载
- ✅ test_e2e_data_download.py
  - 增量数据下载流程
  - 品种缓存调用验证
  - 数据保存格式验证
  - 任务取消功能

- ✅ test_e2e_download_progress_monitoring.py
  - 下载进度实时监控
  - 进度百分比计算
  - 状态变更通知

#### 1.3 数据管理
- ✅ test_e2e_datasource_management.py
  - 数据源连接管理
  - 连接状态监控
  - 数据推送与自动录制

- ✅ test_e2e_local_data_query.py
  - 本地数据查询
  - 时间范围筛选
  - 品种筛选

- ✅ test_e2e_data_quality_check_repair.py
  - 数据完整性检查
  - 数据准确性验证
  - 自动修复功能

- ✅ test_e2e_data_gap_detection.py
  - 数据缺口检测
  - 缺口识别算法

- ✅ test_e2e_symbol_filter_pagination.py
  - 品种筛选功能
  - 分页显示

### 2. 行情看板模块 (3个测试)

#### 2.1 行情显示
- ✅ test_e2e_market_chart_display.py
  - K线图表显示
  - 周期切换
  - 指标叠加

- ✅ test_e2e_market_board_indicators.py
  - 行情指标计算
  - 实时更新
  - 多品种展示

- ✅ test_e2e_realtime_data_recording.py
  - 实时数据推送
  - 自动录制功能
  - 数据融合

### 3. 策略中心模块 (4个测试)

#### 3.1 回测功能
- ✅ test_e2e_backtest.py
  - CTA策略回测
  - 期权策略回测
  - 组合策略回测
  - 脚本交易回测
  - 价差交易回测

#### 3.2 策略管理
- ✅ test_e2e_strategy_instance_lifecycle.py
  - 策略部署
  - 策略池管理
  - 批量启动/停止
  - 状态流转

- ✅ test_e2e_vnpy_strategy_template_adaptation.py
  - VnPy策略模板识别
  - 监控界面适配
  - portfoliostrategy特殊处理

### 4. 交易网关模块 (1个测试)

- ✅ test_e2e_gateway.py
  - 网关连接（已跳过，待实现mock）
  - 委托/成交管理

### 5. 组合投资模块 (1个测试)

- ✅ test_e2e_portfolio_monitoring.py
  - 自动组合识别
  - 绩效指标监控
  - 风险指标监控

### 6. 系统管理模块 (3个测试)

- ✅ test_e2e_alert_management.py
  - 告警规则配置
  - 告警触发与通知

- ✅ test_e2e_service_health_check.py
  - 服务健康检查
  - 状态监控

- ✅ test_e2e_ai_assistant_integration.py
  - AI助手集成测试

## 🛠️ 测试工具

### app_runner.py
后端应用生命周期管理，支持：
- 异步启动/停止后端服务
- 服务健康检查
- 测试隔离

### db_helper.py
VnPy数据库验证工具，提供：
- Bar数据统计
- 数据格式验证
- 数据质量检查
- 测试数据清理

### service_accessor.py
后端服务状态访问器，可以：
- 获取品种缓存统计
- 验证下载任务状态
- 检查数据源连接状态
- 访问策略池信息

### wait_helpers.py
异步等待助手，包含：
- `wait_until_condition` - 通用条件等待
- `wait_for_cache_loaded` - 品种缓存加载等待
- `wait_for_task_completion` - 任务完成等待
- `wait_for_service_state` - 服务状态等待
- `wait_for_connection_state` - 连接状态等待
- `wait_for_ui_update` - UI更新等待

### strategy_helper.py
策略验证助手，支持：
- 策略部署验证
- 状态流转验证
- 模板识别
- 批量控制验证

### chart_helper.py
图表验证助手，提供：
- 图表数据验证
- 渲染性能测试
- 指标叠加验证

## 📝 测试编写规范

### 1. 使用条件等待，避免固定sleep
```python
# ❌ 不推荐
await asyncio.sleep(1.0)

# ✅ 推荐
from tests.test_e2e.utils.wait_helpers import wait_for_cache_loaded
await wait_for_cache_loaded(symbol_service, service_accessor, min_size=1, timeout=5.0)
```

### 2. 使用ServiceAccessor访问服务状态
```python
# ❌ 不推荐 - 直接访问私有字段
cache_size = symbol_service._symbols_cache

# ✅ 推荐 - 使用ServiceAccessor
from tests.test_e2e.utils.service_accessor import ServiceAccessor
accessor = ServiceAccessor()
stats = accessor.get_cache_stats(symbol_service)
cache_size = stats["cache_size"]
```

### 3. 合理设置超时时间
```python
# 快速操作（UI交互）：2.0s
# 中速操作（服务状态）：5.0s
# 慢速操作（数据加载）：10.0s
# 长时操作（任务执行）：30.0s

await wait_for_cache_loaded(
    symbol_service,
    service_accessor,
    min_size=1,
    timeout=5.0  # 中速操作
)
```

### 4. 使用pytest标记
```python
@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(60)  # 设置测试超时
class TestSymbolCacheE2E:
    async def test_symbol_cache_generation(self):
        ...
```

### 5. 清理测试数据
```python
@pytest.fixture
def clean_cache():
    """清理品种缓存."""
    yield
    # 测试后清理
    symbol_service._symbols_cache.clear()
```

## 🔍 调试指南

### 查看详细日志
```bash
pytest tests/test_e2e/test_e2e_symbol_cache.py -v -s --log-cli-level=DEBUG
```

### 只运行失败的测试
```bash
pytest tests/test_e2e/ --lf
```

### 进入调试模式
```bash
pytest tests/test_e2e/test_e2e_symbol_cache.py --pdb
```

### 查看测试覆盖率
```bash
pytest tests/test_e2e/ --cov=backend --cov-report=html
```

## 📚 相关文档

- [E2E测试使用指南](./E2E测试使用指南.md)
- [E2E测试项目最终总结](./E2E测试项目最终总结.md)
- [E2E测试扩展完成报告](./E2E测试扩展完成报告.md)
- [E2E稳定化修复总结](../E2E测试稳定化修复完成总结.md)

## 🐛 已知问题

1. **跳过的测试**
   - `test_e2e_gateway.py` - 需要真实网关连接（待实现mock）
   - `test_e2e_backtest.py::test_backtest_execution_framework` - 回测引擎待实现

2. **待优化项**
   - 部分测试依赖私有字段（计划解耦）
   - 数据源操作顺序需要规范化
   - 异常捕获需要细化

详见：`C:\Users\USER\Desktop\terminal_v0.50\E2E测试稳定化修复完成总结.md`

## 🤝 贡献指南

1. 新增测试应遵循现有的命名和结构规范
2. 使用`wait_helpers`而非固定sleep
3. 添加清晰的日志输出
4. 编写有意义的断言消息
5. 在测试类文档字符串中说明测试覆盖范围

---

**最后更新**: 2025-10-08
**维护者**: 开发团队
**测试数量**: 21个E2E测试用例

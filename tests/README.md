# UI交互功能回路测试套件

## 📋 概述

本测试套件实现了完整的UI交互功能回路测试，覆盖**43个功能链路**，验证从UI点击操作到UI反馈接收的完整业务回路。

## 🎯 测试目标

- **完全自动化**: 使用pytest-qt模拟所有UI交互
- **端到端验证**: UI → 后端API → 数据库 → 返回UI显示
- **业务逻辑验证**: 数据下载、策略回测、交易执行等完整流程

## 📊 测试覆盖

### 测试统计

| 功能界面 | 功能链路数 | 测试文件 | 状态 |
|---------|-----------|---------|------|
| 系统管理 | 8 | test_01_system_manager.py | ✅ |
| 数据中心 | 7 | test_02_data_center.py | ✅ |
| 行情看板 | 6 | test_03_market_board.py | ✅ |
| 策略中心 | 8 | test_04_strategy_center.py | ✅ |
| 交易网关 | 10 | test_05_trading_gateway.py | ✅ |
| 组合投资 | 4 | test_06_portfolio.py | ✅ |
| **总计** | **43** | **6个文件** | ✅ |

## 🚀 快速开始

### 1. 安装测试依赖

```bash
pip install -r tests/requirements-test.txt
```

### 2. 运行测试

#### 方式一：使用Python脚本（推荐）

```bash
python tests/run_ui_tests.py
```

#### 方式二：直接使用pytest

```bash
# 运行所有UI测试
pytest tests/test_ui_integration -v

# 运行特定模块测试
pytest tests/test_ui_integration/test_01_system_manager.py -v

# 使用标记运行测试
pytest -m data_center -v
```

### 3. 生成HTML报告

```bash
pytest tests/test_ui_integration --html=tests/reports/test_results.html --self-contained-html
```

## 📁 目录结构

```
tests/
├── conftest.py                          # pytest配置和全局fixtures
├── requirements-test.txt                # 测试依赖
├── run_ui_tests.py                      # 测试运行脚本
├── test_ui_integration/                 # UI集成测试主目录
│   ├── __init__.py
│   ├── base_ui_test.py                 # UI测试基类
│   ├── fixtures/                        # 测试fixtures
│   │   ├── app_fixture.py              # 应用实例fixture
│   │   ├── ui_fixture.py               # UI组件fixture
│   │   └── mock_backend.py             # 后端mock fixture
│   ├── utils/                           # 测试工具
│   │   ├── ui_interactor.py            # UI交互工具类
│   │   ├── signal_recorder.py          # 信号记录器
│   │   ├── feedback_verifier.py        # 反馈验证器
│   │   └── wait_helpers.py             # 等待辅助函数
│   ├── test_01_system_manager.py       # 系统管理测试(8条)
│   ├── test_02_data_center.py          # 数据中心测试(7条)
│   ├── test_03_market_board.py         # 行情看板测试(6条)
│   ├── test_04_strategy_center.py      # 策略中心测试(8条)
│   ├── test_05_trading_gateway.py      # 交易网关测试(10条)
│   └── test_06_portfolio.py            # 组合投资测试(4条)
└── reports/                             # 测试报告输出目录
```

## 🔧 测试框架

### 核心组件

1. **BaseUITest**: UI测试基类，提供通用测试方法
2. **UIInteractor**: UI交互工具，封装所有UI操作
3. **SignalRecorder**: 信号记录器，捕获和验证Qt信号
4. **FeedbackVerifier**: 反馈验证器，验证UI反馈完整性
5. **wait_helpers**: 等待辅助函数，处理异步操作

### 测试流程

```python
# 标准测试流程
def test_feature_loop(ui_interactor, signal_recorder, feedback_verifier):
    # 1. 准备阶段
    ui_interactor.navigate_to_interface("目标界面")

    # 2. 操作阶段
    with signal_recorder.capture():
        ui_interactor.click_button("操作按钮")
        ui_interactor.input_text(input_widget, "测试数据")

    # 3. 等待阶段
    wait_for_feedback(timeout=5)

    # 4. 验证阶段
    assert signal_recorder.verify_signal_emitted("expected_signal")
    assert feedback_verifier.verify_ui_state(expected_state)
    assert feedback_verifier.verify_data_displayed(expected_data)
```

## 📝 测试标记

使用pytest标记来分类和筛选测试：

```bash
# 按功能模块运行
pytest -m system_manager -v
pytest -m data_center -v
pytest -m market_board -v
pytest -m strategy_center -v
pytest -m trading_gateway -v
pytest -m portfolio -v

# 运行所有UI测试
pytest -m ui -v

# 运行回路测试
pytest -m loop -v
```

## ✅ 验收标准

### 测试通过标准

1. ✅ 所有43个功能链路测试用例全部通过
2. ✅ UI交互 → 后端处理 → UI反馈回路完整
3. ✅ 反馈验证准确率 ≥ 95%
4. ✅ 测试覆盖率 ≥ 90%
5. ✅ 测试报告生成完整

### 质量指标

- **测试执行时间**: 全量测试 ≤ 30分钟
- **测试稳定性**: 重复执行成功率 ≥ 98%
- **错误定位准确性**: 失败原因明确指向具体链路

## 🐛 故障排查

### 常见问题

1. **pytest-qt未安装**
   ```bash
   pip install pytest-qt
   ```

2. **QApplication错误**
   - 确保只有一个QApplication实例
   - 检查qtbot fixture是否正确使用

3. **组件未找到**
   - 检查组件名称是否正确
   - 验证组件是否已加载完成
   - 增加等待时间

4. **信号未捕获**
   - 确认信号已正确连接
   - 检查信号名称拼写
   - 验证信号发射时机

## 📊 测试报告

测试完成后，HTML报告会生成在 `tests/reports/test_results.html`

报告包含：
- 测试执行总览（通过/失败/跳过）
- 每个功能链路的详细结果
- 失败用例的错误堆栈
- 测试执行时间统计

## 🔄 持续集成

可以将测试集成到CI/CD流程中：

```yaml
# .github/workflows/ui-tests.yml
name: UI Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install dependencies
        run: pip install -r tests/requirements-test.txt
      - name: Run UI tests
        run: python tests/run_ui_tests.py
```

## 📖 参考文档

- [pytest-qt文档](https://pytest-qt.readthedocs.io/)
- [PySide6文档](https://doc.qt.io/qtforpython/)
- [功能链条分解文档](../docs/1.权威需求文档/功能链条分解文档.md)

## 🤝 贡献

欢迎提交问题和改进建议！

## 📄 许可证

本测试套件遵循项目主许可证。


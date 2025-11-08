# UI Components 组件库

> 统一的UI组件和主题系统，整合了原 `shared_widgets` 和 `themes` 文件夹的所有功能

## 📁 文件结构

```
ui/components/
├── __init__.py                    # 统一导出接口
├── README.md                      # 本文档
│
├── widgets.py                     # UI组件合集（合并了3个文件）
│   ├── ErrorCategory/ErrorSeverity  # 枚举类
│   ├── BaseWidget                   # 基础Widget类
│   ├── MetricCard/MiniSparkline     # Dashboard组件
│   ├── GaugeWidget/StatusIndicator  # Dashboard组件
│   ├── CompactTable                 # Dashboard组件
│   └── MonacoEditorWidget           # Monaco编辑器
│
├── theme_system.py                # 主题系统（合并了2个类）
│   ├── DashboardTheme            # 静态主题配置类
│   └── ThemeManager              # 动态主题管理器
│
├── charts.py                      # 图表组件
├── basic_monitors.py              # 交易监控组件
│
├── themes.json                    # 主题配置（合并了dark/light）
├── theme_preference.json          # 用户主题偏好
├── modern_dark_style.qss          # 暗色QSS样式
└── modern_light_style.qss         # 亮色QSS样式
```

## 🎨 主题系统

### DashboardTheme（静态配置）

提供统一的色板、字体规格和样式生成器，用于Dashboard组件的样式定制。

**色板定义：**
```python
from ui.components import DashboardTheme

# 访问颜色
bg_color = DashboardTheme.bg_primary
text_color = DashboardTheme.text_primary
success_color = DashboardTheme.success
```

**样式生成器：**
```python
# 卡片样式
card_style = DashboardTheme.get_card_style(elevated=True, height=200)

# 指标数值样式
value_style = DashboardTheme.get_metric_value_style(color="#3B82F6", size=36)

# 按钮样式
button_style = DashboardTheme.get_button_style(primary=True)

# 表格样式
table_style = DashboardTheme.get_compact_table_style()

# 进度条样式
progress_style = DashboardTheme.get_progress_bar_style(color="#10B981")
```

**颜色工具函数：**
```python
# 根据状态获取颜色
status_color = DashboardTheme.get_status_color("success")  # 返回绿色

# 根据指标类型获取颜色
metric_color = DashboardTheme.get_metric_color("cpu")  # 返回橙色
```

### ThemeManager（动态管理）

负责应用主题和颜色管理，支持主题切换和持久化。

**初始化和应用：**
```python
from ui.components import ThemeManager

# 创建主题管理器
theme_manager = ThemeManager()

# 应用主题到应用程序
theme_manager.apply_theme(app)

# 加载用户偏好的主题
preferred_theme = theme_manager.load_theme_preference()
```

**主题切换：**
```python
# 切换到暗色主题
success = theme_manager.switch_theme("dark", app)

# 切换到亮色主题
success = theme_manager.switch_theme("light", app)

# 获取可用主题列表
available_themes = theme_manager.get_available_themes()
```

**主题配置：**
```python
# 获取主题颜色
primary_color = theme_manager.get_color("primary", default="#1e88e5")

# 重新加载主题
theme_manager.reload_theme()
```

## 🧩 组件使用

### 基础组件

#### BaseWidget
所有自定义Widget的基类，提供统一的初始化和生命周期管理。

```python
from ui.components import BaseWidget

class MyCustomWidget(BaseWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        # 实现UI初始化
        pass
```

#### MonacoEditorWidget
基于QPlainTextEdit + Pygments的代码编辑器组件（Monaco风格），在启用
`native_qhighlighter` 扩展后可切换到 C++ 正则驱动的高性能高亮方案。

特性：
- Python语法高亮（Monaco暗色主题）
- 原生语法高亮（可选，NATIVE_QHIGHLIGHTER 默认开启，失败自动降级）
- 行号显示
- 当前行高亮
- 自动缩进
- 零外部依赖（无需WebEngine）

```python
from ui.components import MonacoEditorWidget

# 创建编辑器
editor = MonacoEditorWidget()
editor.setText("print('Hello World')")

# 获取代码
code = editor.text()
```

> 📌 **原生高亮说明**：若需编译原生高亮扩展，可在
> `ui/native_extensions/native_qhighlighter` 执行 `python setup.py build_ext --inplace`。
> 当扩展不可用或设置 `NATIVE_QHIGHLIGHTER=0` 时会自动回退到 Python 实现。

### 图表组件

```python
from ui.components import ChartWidget, ChartToolbar, IndicatorPlotWidget

# 创建K线图表
chart = ChartWidget()
chart.plot_candles(data)

# 创建指标图表
indicator_plot = IndicatorPlotWidget()
indicator_plot.plot_line(data, name="MA5")
```

### Dashboard组件

```python
from ui.components import (
    MetricCard,
    MiniSparkline,
    GaugeWidget,
    StatusIndicator,
    CompactTable
)

# 指标卡片
card = MetricCard(
    title="CPU使用率",
    value="45.2",
    unit="%",
    color="#F97316",
    show_sparkline=True
)
card.update_value(50.5)

# 迷你趋势图
sparkline = MiniSparkline()
sparkline.add_point(45.2)

# 仪表盘
gauge = GaugeWidget(min_val=0, max_val=100, title="内存")
gauge.update_value(65.5)

# 状态指示器
status = StatusIndicator(status="success", text="正常运行")

# 紧凑型表格
table = CompactTable(headers=["列1", "列2", "列3"])
table.add_row(["数据1", "数据2", "数据3"])
```

### 监控组件

```python
from ui.components import (
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor
)

# 订单监控
order_monitor = OrderMonitor()

# 成交监控
trade_monitor = TradeMonitor()

# 持仓监控
position_monitor = PositionMonitor()

# 账户监控
account_monitor = AccountMonitor()
```

## 📦 导入方式

### 推荐方式（从包导入）

```python
# 导入主题系统
from ui.components import DashboardTheme, ThemeManager

# 导入基础组件
from ui.components import BaseWidget, MonacoEditorWidget

# 导入图表组件
from ui.components import ChartWidget, ChartToolbar

# 导入Dashboard组件
from ui.components import MetricCard, GaugeWidget, StatusIndicator

# 导入监控组件
from ui.components import OrderMonitor, TradeMonitor
```

### 直接导入（不推荐）

```python
# 如果确实需要从模块直接导入
from ui.components.theme_system import DashboardTheme
from ui.components.base_widget import BaseWidget
```

## 🔧 配置文件

### 主题配置文件（JSON）

**dark_theme.json / light_theme.json**
```json
{
  "name": "暗色主题",
  "version": "1.0.0",
  "colors": {
    "background": {
      "main": "#121212",
      "secondary": "#1e1e1e"
    },
    "text": {
      "primary": "#ffffff",
      "secondary": "#b3b3b3",
      "disabled": "#808080"
    },
    "primary": "#1e88e5"
  },
  "typography": {
    "font_family": "Microsoft YaHei, SimSun, sans-serif",
    "font_size": {
      "sm": 12,
      "md": 14,
      "lg": 16
    }
  },
  "border_radius": {
    "sm": 4,
    "md": 8,
    "lg": 12
  }
}
```

### QSS样式文件

**modern_dark_style.qss / modern_light_style.qss**

Qt样式表文件，定义了详细的控件样式。可直接编辑以自定义外观。

### 用户偏好文件

**theme_preference.json**
```json
{
  "theme": "dark"
}
```

自动保存用户选择的主题，下次启动时自动加载。

## 🎯 最佳实践

### 1. 使用统一的导入方式

```python
# ✅ 推荐
from ui.components import DashboardTheme, MetricCard

# ❌ 不推荐
from ui.components.theme_system import DashboardTheme
from ui.components.dashboard_components import MetricCard
```

### 2. 复用主题配置

```python
# ✅ 使用DashboardTheme的统一配置
widget.setStyleSheet(DashboardTheme.get_card_style())

# ❌ 不要硬编码颜色和样式
widget.setStyleSheet("background-color: #1E293B;")
```

### 3. 主题切换

```python
# ✅ 使用ThemeManager切换主题
theme_manager.switch_theme("dark", app)

# ❌ 不要手动修改样式表
app.setStyleSheet(...)
```

### 4. 响应主题变化

如果组件需要响应主题切换，建议实现刷新方法：

```python
class MyWidget(BaseWidget):
    def refresh_theme(self):
        """响应主题变化，刷新组件样式"""
        self.setStyleSheet(DashboardTheme.get_card_style())
```

## 📝 更新日志

### v1.0.0 (2025-10-23)

- ✅ 合并 `ui/shared_widgets` 和 `ui/themes` 为 `ui/components`
- ✅ 整合 `DashboardTheme` 和 `ThemeManager` 到 `theme_system.py`
- ✅ 扁平化文件结构，减少文件数量
- ✅ 统一导入导出接口
- ✅ 更新所有项目中的导入引用
- ✅ 提供完整的使用文档

## 🤝 贡献指南

在添加新组件时，请遵循以下规范：

1. 所有组件继承自 `BaseWidget`
2. 使用 `DashboardTheme` 的颜色和样式配置
3. 在 `__init__.py` 中添加导出
4. 更新本 README 文档
5. 添加UTF-8编码声明：`# -*- coding: utf-8 -*-`

## 📞 支持

如有问题或建议，请联系开发团队或提交Issue。


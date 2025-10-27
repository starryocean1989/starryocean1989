# -*- coding: utf-8 -*-
"""统一主题系统 - Dashboard主题配置 + 主题管理器.

本模块整合了两个主题相关类：
1. DashboardTheme: 提供统一的色板、字体规格和样式生成器（静态配置）
2. ThemeManager: 负责应用主题和颜色管理（动态管理）
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from PySide6.QtGui import QColor, QFont, QPalette

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

# ✅ 添加用户反馈logger
logger_user = logging.getLogger("ui.user_feedback")


class DashboardTheme:
    """Dashboard主题配置类 - 提供统一的色板和样式生成器."""

    # 统一色板
    COLORS: Dict[str, str] = {
        # 背景色
        "bg_primary": "#0F172A",  # 主背景（更深）
        "bg_card": "#1E293B",  # 卡片背景
        "bg_elevated": "#334155",  # 悬浮/高亮背景
        # 主题色
        "primary": "#3B82F6",  # 主蓝色
        "primary_hover": "#2563EB",  # 悬停蓝
        "primary_dim": "#1E3A8A",  # 暗蓝背景
        # 文本色
        "text_primary": "#F1F5F9",  # 主文本（白）
        "text_secondary": "#94A3B8",  # 次要文本（灰）
        "text_dim": "#64748B",  # 暗淡文本
        # 状态色
        "success": "#10B981",  # 成功（绿）
        "warning": "#F59E0B",  # 警告（黄）
        "error": "#EF4444",  # 错误（红）
        "critical": "#DC2626",  # 严重（深红）
        # 指标类型色
        "cpu": "#F97316",  # CPU橙色
        "memory": "#10B981",  # 内存绿色
        "disk": "#8B5CF6",  # 磁盘紫色
        "network": "#3B82F6",  # 网络蓝色
        "temp": "#EF4444",  # 温度红色
        # 边框色
        "border": "#334155",
        "border_light": "#475569",
    }

    # 统一字体规格
    FONTS: Dict[str, str] = {
        "title": "font-size: 18px; font-weight: bold;",
        "subtitle": "font-size: 14px; font-weight: 600;",
        "body": "font-size: 13px;",
        "metric_value": "font-size: 32px; font-weight: bold;",
        "metric_label": "font-size: 11px; color: #94A3B8;",
        "table": "font-size: 12px;",
    }

    # 便捷访问颜色（类属性）
    bg_primary = COLORS["bg_primary"]
    bg_card = COLORS["bg_card"]
    bg_elevated = COLORS["bg_elevated"]
    primary = COLORS["primary"]
    text_primary = COLORS["text_primary"]
    text_secondary = COLORS["text_secondary"]
    text_dim = COLORS["text_dim"]
    success = COLORS["success"]
    warning = COLORS["warning"]
    error = COLORS["error"]
    critical = COLORS["critical"]
    cpu = COLORS["cpu"]
    memory = COLORS["memory"]
    disk = COLORS["disk"]
    network = COLORS["network"]
    temp = COLORS["temp"]
    border = COLORS["border"]
    border_light = COLORS["border_light"]

    @staticmethod
    def get_card_style(elevated: bool = False, height: Optional[int] = None) -> str:
        """获取卡片样式.

        Args:
            elevated: 是否悬浮/高亮效果
            height: 固定高度（像素）

        Returns:
            CSS样式字符串
        """
        bg = DashboardTheme.COLORS["bg_elevated"] if elevated else DashboardTheme.COLORS["bg_card"]
        height_str = f"height: {height}px;" if height else ""
        return f"""
            QWidget {{
                background-color: {bg};
                border: 1px solid {DashboardTheme.COLORS["border"]};
                border-radius: 8px;
                padding: 10px;
                {height_str}
            }}
        """

    @staticmethod
    def get_metric_value_style(color: Optional[str] = None, size: int = 32) -> str:
        """获取指标数值样式.

        Args:
            color: 自定义颜色（十六进制），为None则使用默认主文本色
            size: 字体大小（像素）

        Returns:
            CSS样式字符串
        """
        color = color or DashboardTheme.COLORS["text_primary"]
        return f"""
            QLabel {{
                font-size: {size}px;
                font-weight: bold;
                color: {color};
            }}
        """

    @staticmethod
    def get_title_style(color: Optional[str] = None) -> str:
        """获取标题样式.

        Args:
            color: 自定义颜色

        Returns:
            CSS样式字符串
        """
        color = color or DashboardTheme.COLORS["text_primary"]
        return f"""
            QLabel {{
                {DashboardTheme.FONTS["title"]}
                color: {color};
            }}
        """

    @staticmethod
    def get_subtitle_style(color: Optional[str] = None) -> str:
        """获取副标题样式.

        Args:
            color: 自定义颜色

        Returns:
            CSS样式字符串
        """
        color = color or DashboardTheme.COLORS["text_secondary"]
        return f"""
            QLabel {{
                {DashboardTheme.FONTS["subtitle"]}
                color: {color};
            }}
        """

    @staticmethod
    def get_body_style(color: Optional[str] = None) -> str:
        """获取正文样式.

        Args:
            color: 自定义颜色

        Returns:
            CSS样式字符串
        """
        color = color or DashboardTheme.COLORS["text_primary"]
        return f"""
            QLabel {{
                {DashboardTheme.FONTS["body"]}
                color: {color};
            }}
        """

    @staticmethod
    def get_checkbox_style() -> str:
        """获取复选框样式.

        Returns:
            CSS样式字符串
        """
        return f"""
            QCheckBox {{
                color: {DashboardTheme.COLORS["text_primary"]};
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DashboardTheme.COLORS["border"]};
                border-radius: 3px;
                background-color: {DashboardTheme.COLORS["bg_card"]};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DashboardTheme.COLORS["primary"]};
                border-color: {DashboardTheme.COLORS["primary"]};
            }}
        """

    @staticmethod
    def get_metric_label_style() -> str:
        """获取指标标签样式.

        Returns:
            CSS样式字符串
        """
        return f"""
            QLabel {{
                {DashboardTheme.FONTS["metric_label"]}
            }}
        """

    @staticmethod
    def get_compact_table_style() -> str:
        """获取紧凑型表格样式.

        Returns:
            CSS样式字符串
        """
        return f"""
            QTableWidget {{
                background-color: {DashboardTheme.COLORS["bg_card"]};
                border: 1px solid {DashboardTheme.COLORS["border"]};
                border-radius: 4px;
                {DashboardTheme.FONTS["table"]}
                gridline-color: {DashboardTheme.COLORS["border"]};
            }}
            QTableWidget::item {{
                padding: 4px;
                border: none;
            }}
            QTableWidget::item:alternate {{
                background-color: {DashboardTheme.COLORS["bg_primary"]};
            }}
            QTableWidget::item:selected {{
                background-color: {DashboardTheme.COLORS["primary_dim"]};
                color: {DashboardTheme.COLORS["text_primary"]};
            }}
            QTableWidget::item:hover {{
                background-color: {DashboardTheme.COLORS["bg_elevated"]};
            }}
            QHeaderView::section {{
                background-color: {DashboardTheme.COLORS["bg_elevated"]};
                color: {DashboardTheme.COLORS["text_secondary"]};
                padding: 6px;
                border: none;
                border-bottom: 2px solid {DashboardTheme.COLORS["primary"]};
                font-weight: 600;
            }}
        """

    @staticmethod
    def get_progress_bar_style(color: Optional[str] = None) -> str:
        """获取进度条样式.

        Args:
            color: 进度条颜色（十六进制），为None则使用主题蓝色

        Returns:
            CSS样式字符串
        """
        color = color or DashboardTheme.COLORS["primary"]
        return f"""
            QProgressBar {{
                border: 2px solid {DashboardTheme.COLORS["border"]};
                border-radius: 5px;
                background-color: {DashboardTheme.COLORS["bg_primary"]};
                text-align: center;
                height: 20px;
                font-size: 11px;
                color: {DashboardTheme.COLORS["text_primary"]};
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """

    @staticmethod
    def get_button_style(primary: bool = False) -> str:
        """获取按钮样式.

        Args:
            primary: 是否主按钮（蓝色）

        Returns:
            CSS样式字符串
        """
        if primary:
            return f"""
                QPushButton {{
                    background-color: {DashboardTheme.COLORS["primary"]};
                    color: {DashboardTheme.COLORS["text_primary"]};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {DashboardTheme.COLORS["primary_hover"]};
                }}
                QPushButton:pressed {{
                    background-color: {DashboardTheme.COLORS["primary_dim"]};
                }}
                QPushButton:disabled {{
                    background-color: {DashboardTheme.COLORS["bg_elevated"]};
                    color: {DashboardTheme.COLORS["text_dim"]};
                }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: {DashboardTheme.COLORS["bg_elevated"]};
                    color: {DashboardTheme.COLORS["text_secondary"]};
                    border: 1px solid {DashboardTheme.COLORS["border"]};
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {DashboardTheme.COLORS["border_light"]};
                    color: {DashboardTheme.COLORS["text_primary"]};
                }}
                QPushButton:pressed {{
                    background-color: {DashboardTheme.COLORS["border"]};
                }}
                QPushButton:disabled {{
                    background-color: {DashboardTheme.COLORS["bg_card"]};
                    color: {DashboardTheme.COLORS["text_dim"]};
                    border-color: {DashboardTheme.COLORS["border"]};
                }}
            """

    @staticmethod
    def get_status_color(status: str) -> str:
        """根据状态获取颜色.

        Args:
            status: 状态字符串 (normal/success, warning, error/critical)

        Returns:
            颜色十六进制字符串
        """
        status_lower = status.lower()
        if status_lower in ["normal", "success", "online", "healthy"]:
            return DashboardTheme.COLORS["success"]
        elif status_lower in ["warning", "warn"]:
            return DashboardTheme.COLORS["warning"]
        elif status_lower in ["error", "critical", "offline", "failed"]:
            return DashboardTheme.COLORS["error"]
        else:
            return DashboardTheme.COLORS["text_secondary"]

    @staticmethod
    def get_metric_color(metric_type: str) -> str:
        """根据指标类型获取颜色.

        Args:
            metric_type: 指标类型 (cpu, memory, disk, network, temp)

        Returns:
            颜色十六进制字符串
        """
        metric_type_lower = metric_type.lower()
        if "cpu" in metric_type_lower:
            return DashboardTheme.COLORS["cpu"]
        elif "mem" in metric_type_lower:
            return DashboardTheme.COLORS["memory"]
        elif "disk" in metric_type_lower:
            return DashboardTheme.COLORS["disk"]
        elif "net" in metric_type_lower or "network" in metric_type_lower:
            return DashboardTheme.COLORS["network"]
        elif "temp" in metric_type_lower:
            return DashboardTheme.COLORS["temp"]
        else:
            return DashboardTheme.COLORS["primary"]


class ThemeManager:
    """主题管理系统 - 负责应用主题和颜色管理."""

    def __init__(self, theme_path: Optional[str] = None):
        """初始化主题管理器."""
        # ✅ 使用规范命名
        self._logger = logging.getLogger("ui.components.theme")
        self.current_theme = "dark"
        self.theme_path = theme_path or str(Path(__file__).parent / "themes.json")
        self.themes: Dict[str, Dict[str, Any]] = {}
        self.all_themes: Dict[str, Dict[str, Any]] = {}
        self._load_themes()

    @property
    def logger(self):
        """获取日志器."""
        return self._logger

    @logger.setter
    def logger(self, value):
        """设置日志器."""
        self._logger = value

    def _load_themes(self):
        """加载主题配置."""
        try:
            with open(self.theme_path, "r", encoding="utf-8") as f:
                self.all_themes = json.load(f)
            # 加载当前主题
            self.themes = self.all_themes.get(self.current_theme, self.all_themes.get("dark", {}))
            self._logger.info("成功加载主题: %s (当前: %s)", self.theme_path, self.current_theme)
        except (json.JSONDecodeError, OSError) as e:
            self._logger.error("加载主题失败: %s", e)
            self._create_default_theme()

    def _create_default_theme(self):
        """创建默认主题."""
        self.themes = {
            "default": {
                "name": "默认暗黑主题",
                "version": "1.0.0",
                "colors": {
                    "background": "#121212",
                    "surface": "#1e1e1e",
                    "primary": "#1e88e5",
                    "text": "#ffffff",
                    "border": "#404040",
                },
            }
        }

    def apply_theme(self, app: "QApplication"):
        """应用主题到应用程序."""
        try:
            theme = self.themes
            if not theme:
                self._logger.warning("主题配置为空，使用默认主题")
                self._create_default_theme()
                theme = self.themes

            # 🔧 修复: 安全地应用主题，避免Qt连接问题
            try:
                self._set_dark_palette(app, theme)
            except Exception as e:
                self._logger.warning("设置调色板失败，跳过: %s", e)

            try:
                self._set_global_font(app, theme)
            except Exception as e:
                self._logger.warning("设置字体失败，跳过: %s", e)

            # 尝试加载QSS样式表文件
            qss_path = Path(__file__).parent / "modern_dark_style.qss"
            if qss_path.exists():
                try:
                    with open(qss_path, "r", encoding="utf-8") as f:
                        qss_content = f.read()
                    app.setStyleSheet(qss_content)
                    self._logger.info("成功加载QSS样式表: %s", qss_path)
                except (OSError, UnicodeDecodeError) as e:
                    self._logger.warning("加载QSS失败，使用默认样式: %s", e)
            else:
                # 如果QSS文件不存在，应用基本样式
                self._logger.info("QSS文件不存在，应用基本样式")
                try:
                    self._apply_basic_style(app)
                except Exception as e:
                    self._logger.warning("应用基本样式失败: %s", e)

            self._logger.info("主题应用成功")
        except (ValueError, TypeError, AttributeError) as e:
            self._logger.error("应用主题失败: %s", e)

    def _set_dark_palette(self, app: "QApplication", theme: Dict[str, Any]):
        """设置暗黑主题调色板."""
        colors = theme.get("colors", {})
        dark_palette = QPalette()
        # 窗口背景
        background = colors.get("background", {})
        window_bg = background.get("main", "#121212") if isinstance(background, dict) else "#121212"
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(window_bg))
        # 窗口文本
        text = colors.get("text", {})
        window_text = text.get("primary", "#ffffff") if isinstance(text, dict) else "#ffffff"
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(window_text))
        # 基础颜色
        surface = colors.get("surface", {})
        base_bg = surface.get("main", "#1e1e1e") if isinstance(surface, dict) else "#1e1e1e"
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(base_bg))
        base_text = text.get("primary", "#ffffff") if isinstance(text, dict) else "#ffffff"
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(base_text))
        # 交替基础颜色
        alternate_bg = (
            background.get("secondary", "#1e1e1e") if isinstance(background, dict) else "#1e1e1e"
        )
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(alternate_bg))
        # 按钮颜色
        button = colors.get("button", {})
        button_bg = button.get("default", "#2d2d2d") if isinstance(button, dict) else "#2d2d2d"
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(button_bg))
        button_text = text.get("primary", "#ffffff") if isinstance(text, dict) else "#ffffff"
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(button_text))
        # 高亮颜色
        highlight_bg = colors.get("primary", "#1e88e5")
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(highlight_bg))
        highlight_text = text.get("primary", "#ffffff") if isinstance(text, dict) else "#ffffff"
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(highlight_text))
        # 链接颜色
        link_color = colors.get("primary", "#1e88e5")
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(link_color))
        # 工具提示
        tooltip = colors.get("tooltip", {})
        tooltip_bg = (
            tooltip.get("background", "#383838") if isinstance(tooltip, dict) else "#383838"
        )
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tooltip_bg))
        tooltip_text = tooltip.get("text", "#ffffff") if isinstance(tooltip, dict) else "#ffffff"
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(tooltip_text))
        # 禁用状态
        disabled_bg = button.get("disabled", "#1a1a1a") if isinstance(button, dict) else "#1a1a1a"
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(disabled_bg)
        )
        disabled_text = text.get("disabled", "#808080") if isinstance(text, dict) else "#808080"
        dark_palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(disabled_text),
        )
        app.setPalette(dark_palette)
        # 设置全局样式表
        self._apply_global_stylesheet(app, colors)

    def _apply_global_stylesheet(self, app: "QApplication", colors: Dict[str, Any]):
        """应用全局样式表."""

        # 安全获取颜色值
        def safe_get_color(path: str, default: str) -> str:
            keys = path.split(".")
            current = colors
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current if isinstance(current, str) else default

        # 获取主题配置
        theme = self.themes
        border_radius = theme.get("border_radius", {})
        border_radius_md = border_radius.get("md", 8) if isinstance(border_radius, dict) else 8
        border_radius_sm = border_radius.get("sm", 4) if isinstance(border_radius, dict) else 4
        stylesheet = f"""
        QMainWindow {{
            background-color: {safe_get_color('background.main', '#121212')};
        }}
        QWidget {{
            color: {safe_get_color('text.primary', '#ffffff')};
            background-color: {safe_get_color('background.main', '#121212')};
        }}
        QTabWidget::pane {{
            border: 1px solid {safe_get_color('border.main', '#404040')};
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
        }}
        QTabBar::tab {{
            background-color: {safe_get_color('tab.background', '#1e1e1e')};
            color: {safe_get_color('text.secondary', '#b3b3b3')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
            padding: 8px 16px;
        }}
        QTabBar::tab:selected {{
            background-color: {safe_get_color('tab.selected', '#2d2d2d')};
            color: {safe_get_color('text.primary', '#ffffff')};
        }}
        QTabBar::tab:hover {{
            background-color: {safe_get_color('tab.hover', '#383838')};
        }}
        QPushButton {{
            background-color: {safe_get_color('button.default', '#2d2d2d')};
            color: {safe_get_color('text.primary', '#ffffff')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
            padding: 8px 16px;
            border-radius: {border_radius_md}px;
        }}
        QPushButton:hover {{
            background-color: {safe_get_color('button.hover', '#383838')};
        }}
        QPushButton:pressed {{
            background-color: {safe_get_color('button.pressed', '#1e1e1e')};
        }}
        QPushButton:disabled {{
            background-color: {safe_get_color('button.disabled', '#1a1a1a')};
            color: {safe_get_color('text.disabled', '#808080')};
        }}
        QLineEdit {{
            background-color: {safe_get_color('input.background', '#2d2d2d')};
            color: {safe_get_color('text.primary', '#ffffff')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
            padding: 4px 8px;
            border-radius: {border_radius_sm}px;
        }}
        QLineEdit:focus {{
            border-color: {safe_get_color('input.focus', '#1e88e5')};
        }}
        QComboBox {{
            background-color: {safe_get_color('input.background', '#2d2d2d')};
            color: {safe_get_color('text.primary', '#ffffff')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
            padding: 4px 8px;
            border-radius: {border_radius_sm}px;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
            color: {safe_get_color('text.primary', '#ffffff')};
            selection-background-color: {safe_get_color('primary',
                                                        '#1e88e5')};
        }}
        QScrollBar:vertical {{
            background-color: {safe_get_color('scrollbar.background',
                                              '#2d2d2d')};
            width: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {safe_get_color('scrollbar.thumb', '#404040')};
            min-height: 20px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {safe_get_color('scrollbar.hover', '#4a4a4a')};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            height: 0px;
        }}
        QGroupBox {{
            font-weight: bold;
            border: 2px solid {safe_get_color('border.main', '#404040')};
            border-radius: {border_radius_md}px;
            margin-top: 1ex;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px 0 5px;
        }}
        QTreeWidget {{
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
            color: {safe_get_color('text.primary', '#ffffff')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
        }}
        QTreeWidget::item {{
            padding: 4px;
        }}
        QTreeWidget::item:selected {{
            background-color: {safe_get_color('primary', '#1e88e5')};
        }}
        QTreeWidget::branch {{
            background: transparent;
        }}
        QHeaderView::section {{
            background-color: {safe_get_color('surface.secondary', '#2d2d2d')};
            color: {safe_get_color('text.primary', '#ffffff')};
            padding: 8px;
            border: 1px solid {safe_get_color('border.main', '#404040')};
        }}
        QTableWidget {{
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
            color: {safe_get_color('text.primary', '#ffffff')};
            border: 1px solid {safe_get_color('border.main', '#404040')};
            gridline-color: {safe_get_color('border.secondary', '#2d2d2d')};
        }}
        QTableWidget::item {{
            padding: 4px;
        }}
        QTableWidget::item:selected {{
            background-color: {safe_get_color('primary', '#1e88e5')};
        }}
        QLabel:disabled {{
            color: {safe_get_color('text.disabled', '#808080')};
        }}
        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 2px solid {safe_get_color('border.main', '#404040')};
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
        }}
        QCheckBox::indicator:checked {{
            background-color: {safe_get_color('primary', '#1e88e5')};
        }}
        QRadioButton {{
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 2px solid {safe_get_color('border.main', '#404040')};
            background-color: {safe_get_color('surface.main', '#1e1e1e')};
            border-radius: 8px;
        }}
        QRadioButton::indicator:checked {{
            background-color: {safe_get_color('primary', '#1e88e5')};
        }}
        """
        app.setStyleSheet(stylesheet)

    def _set_global_font(self, app: "QApplication", theme: Dict[str, Any]):
        """设置全局字体."""
        typography = theme.get("typography", {})
        font_family = typography.get("font_family", "Microsoft YaHei, SimSun, sans-serif")
        font_size = typography.get("font_size", {}).get("md", 14)
        font = QFont(font_family, font_size)
        app.setFont(font)

    def _apply_basic_style(self, app: "QApplication"):
        """应用基本样式（当QSS文件不存在时）."""
        basic_style = """
        QMainWindow {
            background-color: #121212;
            color: #ffffff;
        }
        QWidget {
            background-color: #121212;
            color: #ffffff;
        }
        QPushButton {
            background-color: #2d2d2d;
            color: #ffffff;
            border: 1px solid #404040;
            padding: 8px 16px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #383838;
        }
        QListWidget {
            background-color: #2d2d2d;
            color: #ffffff;
            border: none;
        }
        QListWidget::item:selected {
            background-color: #1e88e5;
        }
        """
        app.setStyleSheet(basic_style)

    def get_color(self, color_path: str, default: str = "#ffffff") -> str:
        """获取主题颜色."""
        colors = self.themes.get("colors", {})
        keys = color_path.split(".")
        current = colors
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current if isinstance(current, str) else default

    def reload_theme(self):
        """重新加载主题."""
        self._load_themes()
        self._logger.info("主题重新加载完成")

    def switch_theme(self, theme_name: str, app: "QApplication") -> bool:
        """
        切换主题

        Args:
            theme_name: 主题名称（"dark"或"light"）
            app: QApplication实例

        Returns:
            bool: 是否成功
        """
        try:
            # 从统一的主题文件加载
            themes_file = Path(__file__).parent / "themes.json"

            qss_files = {
                "dark": Path(__file__).parent / "modern_dark_style.qss",
                "light": Path(__file__).parent / "modern_light_style.qss",
            }

            if not themes_file.exists():
                self._logger.error("主题配置文件不存在: %s", themes_file)
                return False

            # 加载所有主题配置
            with open(themes_file, "r", encoding="utf-8") as f:
                self.all_themes = json.load(f)

            # 检查主题是否存在
            if theme_name not in self.all_themes:
                self._logger.error("主题不存在: %s", theme_name)
                return False

            # 设置当前主题
            self.themes = self.all_themes[theme_name]
            self.current_theme = theme_name

            # 应用QSS样式
            qss_file = qss_files.get(theme_name)
            if qss_file and qss_file.exists():
                with open(qss_file, "r", encoding="utf-8") as f:
                    qss_content = f.read()
                app.setStyleSheet(qss_content)
                self._logger.info("成功切换到%s主题", theme_name)
                # ✅ 用户操作反馈
                logger_user.info("用户切换主题: %s", theme_name)
            else:
                # 回退到调色板方式
                self._set_dark_palette(app, self.themes)
                self._logger.warning("QSS文件不存在，使用调色板方式应用%s主题", theme_name)

            # 保存主题选择
            self._save_theme_preference(theme_name)

            return True

        except (OSError, json.JSONDecodeError) as e:
            self._logger.error("切换主题失败: %s", e)
            return False

    def _save_theme_preference(self, theme_name: str) -> None:
        """保存主题偏好设置"""
        try:
            pref_file = Path(__file__).parent / "theme_preference.json"
            with open(pref_file, "w", encoding="utf-8") as f:
                json.dump({"theme": theme_name}, f)
            self._logger.info("保存主题偏好: %s", theme_name)
        except (OSError, TypeError) as e:
            self._logger.error("保存主题偏好失败: %s", e)

    def load_theme_preference(self) -> str:
        """加载主题偏好设置"""
        try:
            pref_file = Path(__file__).parent / "theme_preference.json"
            if pref_file.exists():
                with open(pref_file, "r", encoding="utf-8") as f:
                    pref = json.load(f)
                    theme = pref.get("theme", "dark")
                    self._logger.info("加载主题偏好: %s", theme)
                    return theme
        except (OSError, json.JSONDecodeError) as e:
            self._logger.error("加载主题偏好失败: %s", e)
        return "dark"

    def get_available_themes(self) -> list:
        """获取可用主题列表"""
        # 如果已加载所有主题，直接返回键列表
        if self.all_themes:
            return list(self.all_themes.keys())

        # 否则尝试从文件加载
        try:
            themes_file = Path(__file__).parent / "themes.json"
            if themes_file.exists():
                with open(themes_file, "r", encoding="utf-8") as f:
                    all_themes = json.load(f)
                    return list(all_themes.keys())
        except (OSError, json.JSONDecodeError) as e:
            self._logger.error("获取可用主题列表失败: %s", e)

        return ["dark", "light"]  # 默认返回

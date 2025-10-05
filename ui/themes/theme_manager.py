# -*- coding: utf-8 -*-
"""主题管理系统 - 负责应用主题和颜色管理."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from PySide6.QtGui import QColor, QFont, QPalette

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


class ThemeManager:
    """主题管理系统."""

    def __init__(self, theme_path: Optional[str] = None):
        """初始化主题管理器."""
        self._logger = logging.getLogger(self.__class__.__name__)
        self.current_theme = "dark"
        self.theme_path = (theme_path or
                           str(Path(__file__).parent / "dark_theme.json"))
        self.themes: Dict[str, Dict[str, Any]] = {}
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
            with open(self.theme_path, 'r', encoding='utf-8') as f:
                self.themes = json.load(f)
            self._logger.info("成功加载主题: %s", self.theme_path)
        except (json.JSONDecodeError, OSError) as e:
            self._logger.error("加载主题失败: %s", e)
            self._create_default_theme()

    def _create_default_theme(self):
        """创建默认主题."""
        self.themes = {
            "name": "默认暗黑主题",
            "version": "1.0.0",
            "colors": {
                "background": "#121212",
                "surface": "#1e1e1e",
                "primary": "#1e88e5",
                "text": "#ffffff",
                "border": "#404040"
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

            self._set_dark_palette(app, theme)
            self._set_global_font(app, theme)
            self._logger.info("主题应用成功")
        except (ValueError, TypeError, AttributeError) as e:
            self._logger.error("应用主题失败: %s", e)

    def _set_dark_palette(self, app: "QApplication", theme: Dict[str, Any]):
        """设置暗黑主题调色板."""
        colors = theme.get("colors", {})

        dark_palette = QPalette()

        # 窗口背景
        background = colors.get("background", {})
        window_bg = (background.get("main", "#121212")
                     if isinstance(background, dict) else "#121212")
        dark_palette.setColor(QPalette.Window, QColor(window_bg))

        # 窗口文本
        text = colors.get("text", {})
        window_text = (text.get("primary", "#ffffff")
                       if isinstance(text, dict) else "#ffffff")
        dark_palette.setColor(QPalette.WindowText, QColor(window_text))

        # 基础颜色
        surface = colors.get("surface", {})
        base_bg = (surface.get("main", "#1e1e1e")
                   if isinstance(surface, dict) else "#1e1e1e")
        dark_palette.setColor(QPalette.Base, QColor(base_bg))

        base_text = (text.get("primary", "#ffffff")
                     if isinstance(text, dict) else "#ffffff")
        dark_palette.setColor(QPalette.Text, QColor(base_text))

        # 交替基础颜色
        alternate_bg = (background.get("secondary", "#1e1e1e")
                        if isinstance(background, dict) else "#1e1e1e")
        dark_palette.setColor(QPalette.AlternateBase, QColor(alternate_bg))

        # 按钮颜色
        button = colors.get("button", {})
        button_bg = (button.get("default", "#2d2d2d")
                     if isinstance(button, dict) else "#2d2d2d")
        dark_palette.setColor(QPalette.Button, QColor(button_bg))

        button_text = (text.get("primary", "#ffffff")
                       if isinstance(text, dict) else "#ffffff")
        dark_palette.setColor(QPalette.ButtonText, QColor(button_text))

        # 高亮颜色
        highlight_bg = colors.get("primary", "#1e88e5")
        dark_palette.setColor(QPalette.Highlight, QColor(highlight_bg))

        highlight_text = (text.get("primary", "#ffffff")
                          if isinstance(text, dict) else "#ffffff")
        dark_palette.setColor(QPalette.HighlightedText, QColor(highlight_text))

        # 链接颜色
        link_color = colors.get("primary", "#1e88e5")
        dark_palette.setColor(QPalette.Link, QColor(link_color))

        # 工具提示
        tooltip = colors.get("tooltip", {})
        tooltip_bg = (tooltip.get("background", "#383838")
                      if isinstance(tooltip, dict) else "#383838")
        dark_palette.setColor(QPalette.ToolTipBase, QColor(tooltip_bg))

        tooltip_text = (tooltip.get("text", "#ffffff")
                        if isinstance(tooltip, dict) else "#ffffff")
        dark_palette.setColor(QPalette.ToolTipText, QColor(tooltip_text))

        # 禁用状态
        disabled_bg = (button.get("disabled", "#1a1a1a")
                       if isinstance(button, dict) else "#1a1a1a")
        dark_palette.setColor(QPalette.Disabled, QPalette.Button,
                              QColor(disabled_bg))

        disabled_text = (text.get("disabled", "#808080")
                         if isinstance(text, dict) else "#808080")
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText,
                              QColor(disabled_text))

        app.setPalette(dark_palette)

        # 设置全局样式表
        self._apply_global_stylesheet(app, colors)

    def _apply_global_stylesheet(self, app: "QApplication",
                                 colors: Dict[str, Any]):
        """应用全局样式表."""
        # 安全获取颜色值
        def safe_get_color(path: str, default: str) -> str:
            keys = path.split('.')
            current = colors
            for key in keys:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
            return current if isinstance(current, str) else default

        # 获取主题配置
        theme = self.themes
        border_radius = theme.get('border_radius', {})
        border_radius_md = (border_radius.get('md', 8)
                            if isinstance(border_radius, dict) else 8)
        border_radius_sm = (border_radius.get('sm', 4)
                            if isinstance(border_radius, dict) else 4)

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
        font_family = typography.get(
            "font_family", "Microsoft YaHei, SimSun, sans-serif"
        )
        font_size = typography.get("font_size", {}).get("md", 14)

        font = QFont(font_family, font_size)
        app.setFont(font)

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

# -*- coding: utf-8 -*-
"""策略中心界面 - 现代IDE风格.

采用现代IDE架构：
- 左侧：文件管理器（支持右键菜单、拖拽、搜索）
- 中央：多标签编辑器（支持多文件同时编辑）
- 右侧：AI助手（可隐藏）
- 底部：回测面板、终端、调试控制台（可折叠）
"""

import os
import re
import shutil
import sys
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from backend.core.base import get_service_manager
from backend.core.service_base import LoggerMixin
from ui.shared_widgets.base_widget import BaseWidget


# ==================== Monaco Editor 导入 ====================
# 导入Monaco Editor（异步加载版）
_editor_widget_available = False
_editor_widget_class = None
_editor_widget_name = None

try:
    from ui.shared_widgets.monaco_editor_widget import MonacoEditorWidget, HAS_WEBENGINE

    if HAS_WEBENGINE:
        _editor_widget_class = MonacoEditorWidget
        _editor_widget_available = True
        _editor_widget_name = "Monaco Editor"
        print("✓ Monaco Editor 可用（异步加载版）")
    else:
        print("✗ Monaco Editor 不可用 (缺少 PySide6-WebEngine)")
except ImportError as e:
    print(f"✗ Monaco Editor 导入失败: {e}")


# ==================== 编辑器标签组件 ====================
class EditorTabWidget(QTabWidget, LoggerMixin):
    """多标签编辑器组件.

    功能：
    - 多文件同时打开和编辑
    - 标签可关闭、可拖拽排序
    - 未保存文件显示圆点标记
    - 标签右键菜单（关闭、关闭其他、关闭全部、复制路径）
    - 快捷键切换标签（Ctrl+Tab）
    """

    # 信号
    file_opened = Signal(str)  # 文件打开信号
    file_closed = Signal(str)  # 文件关闭信号
    file_saved = Signal(str)  # 文件保存信号
    current_file_changed = Signal(str)  # 当前文件切换信号

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化多标签编辑器."""
        super().__init__(parent)

        # 编辑器字典：{file_path: 编辑器组件}
        self.editors: Dict[str, Any] = {}

        # 未保存文件集合
        self.unsaved_files: Set[str] = set()

        # 最近关闭的标签（用于恢复）
        self.recently_closed: list = []

        # 设置UI
        self._setup_ui()

        # 连接信号
        self._connect_signals()

        # 设置快捷键
        self._setup_shortcuts()

        self.logger.info("多标签编辑器初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        # 设置标签位置
        self.setTabPosition(QTabWidget.TabPosition.North)

        # 标签可关闭
        self.setTabsClosable(True)

        # 标签可移动（拖拽排序）
        self.setMovable(True)

        # 文档模式（类似浏览器标签）
        self.setDocumentMode(True)

        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _connect_signals(self):
        """连接信号槽."""
        # 标签关闭按钮点击
        self.tabCloseRequested.connect(self._on_tab_close_requested)

        # 当前标签切换
        self.currentChanged.connect(self._on_current_changed)

    def _setup_shortcuts(self):
        """设置快捷键."""
        # Ctrl+Tab: 切换到下一个标签
        next_tab_shortcut = QShortcut(QKeySequence("Ctrl+Tab"), self)
        next_tab_shortcut.activated.connect(self._switch_to_next_tab)

        # Ctrl+Shift+Tab: 切换到上一个标签
        prev_tab_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        prev_tab_shortcut.activated.connect(self._switch_to_prev_tab)

        # Ctrl+W: 关闭当前标签
        close_tab_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        close_tab_shortcut.activated.connect(self._close_current_tab)

        # Ctrl+Shift+T: 恢复最近关闭的标签
        reopen_shortcut = QShortcut(QKeySequence("Ctrl+Shift+T"), self)
        reopen_shortcut.activated.connect(self._reopen_last_closed)

    # ==================== 文件操作 ====================

    def open_file(self, file_path: str) -> bool:
        """打开文件.

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否成功打开
        """
        try:
            self.logger.info("🔍 [DEBUG] ===== editor_tabs.open_file 被调用 =====")
            self.logger.info(f"🔍 [DEBUG] 原始路径: {file_path}")

            # 规范化路径
            file_path = str(Path(file_path).resolve())
            self.logger.info(f"🔍 [DEBUG] 规范化后路径: {file_path}")
            self.logger.info(f"🔍 [DEBUG] 文件是否存在: {Path(file_path).exists()}")

            # 如果文件已打开，切换到对应标签
            if file_path in self.editors:
                index = self._get_tab_index_by_path(file_path)
                if index >= 0:
                    self.setCurrentIndex(index)
                    self.logger.info(f"切换到已打开的文件: {file_path}")
                    return True

            # 检查文件是否存在
            if not Path(file_path).exists():
                self.logger.error(f"文件不存在: {file_path}")
                QMessageBox.warning(self, "文件不存在", f"无法打开文件，文件不存在:\n{file_path}")
                return False

            # 读取文件内容
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.logger.info(f"成功读取文件内容，长度: {len(content)}")
            except Exception as read_error:
                self.logger.error(f"读取文件失败: {read_error}", exc_info=True)
                QMessageBox.critical(self, "读取失败", f"无法读取文件:\n{str(read_error)}")
                return False

            # 🔧 创建Monaco Editor（异步加载版）
            try:
                self.logger.info("🔍 [DEBUG] 开始创建Monaco编辑器")

                if not _editor_widget_available or _editor_widget_class is None:
                    self.logger.error("Monaco Editor不可用")
                    QMessageBox.critical(
                        self,
                        "编辑器不可用",
                        "Monaco Editor组件未正确加载。\n\n"
                        "请安装编辑器依赖：\n"
                        "pip install PySide6-WebEngine",
                    )
                    return False

                self.logger.info("🔍 [DEBUG] === 开始创建Monaco Editor实例 ===")

                try:
                    editor = _editor_widget_class()
                    self.logger.info("✓ Monaco Editor __init__ 完成")
                except Exception as init_error:
                    self.logger.error(f"🔴 Monaco __init__ 失败: {init_error}", exc_info=True)
                    raise

                try:
                    # 设置内容（Monaco Editor 会自动处理异步加载）
                    self.logger.info("🔍 [DEBUG] 准备设置内容...")
                    editor.setPlainText(content)
                    self.logger.info("✓ 内容设置完成")
                except Exception as content_error:
                    self.logger.error(f"🔴 setPlainText 失败: {content_error}", exc_info=True)
                    raise

                # 🔧 检查是否是模板文件，设置为只读
                normalized_path = file_path.replace("\\", "/")
                is_template = "strategies/templates/" in normalized_path
                if is_template:
                    editor.setReadOnly(True)
                    self.logger.info(f"✓ 模板文件设置为只读: {file_path}")

                # 检查编辑器状态
                if hasattr(editor, "isReady"):
                    is_ready = editor.isReady()
                    self.logger.info(f"编辑器内容设置完成（就绪状态: {is_ready}）")
                else:
                    self.logger.info("编辑器内容设置完成")

                # 🔧 修复：延迟连接信号，避免初始化时触发
                self.logger.info("🔍 [DEBUG] 准备连接内容变化信号")

                # 监控内容变化（兼容不同编辑器的信号）
                try:
                    if hasattr(editor, "textChanged"):
                        # CodeEditor 使用 textChanged 信号
                        editor.textChanged.connect(lambda: self._on_content_changed(file_path))
                        self.logger.info("✓ 内容变化信号连接成功（textChanged）")
                    elif hasattr(editor, "contentChanged"):
                        # MonacoEditorWidget 使用 contentChanged 信号
                        # 注意：不使用content参数，避免潜在的递归
                        editor.contentChanged.connect(lambda _: self._on_content_changed(file_path))
                        self.logger.info("✓ 内容变化信号连接成功（contentChanged）")
                    else:
                        self.logger.warning("编辑器不支持内容变化信号")
                except Exception as signal_error:
                    self.logger.error(f"⚠️ 信号连接失败: {signal_error}", exc_info=True)

            except Exception as editor_error:
                self.logger.error(f"创建编辑器失败: {editor_error}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "编辑器错误",
                    f"无法创建编辑器组件:\n{str(editor_error)}\n\n"
                    f"错误详情: {type(editor_error).__name__}\n\n"
                    "请检查编辑器依赖是否正确安装。",
                )
                return False

            # 🔧 修复：验证编辑器对象有效性
            if not editor or not hasattr(editor, "toPlainText"):
                self.logger.error("编辑器对象无效或缺少必要方法")
                QMessageBox.critical(self, "编辑器错误", "编辑器对象创建失败，缺少必要方法")
                return False

            # 保存编辑器引用
            self.editors[file_path] = editor

            # 添加标签
            file_name = Path(file_path).name
            self.logger.info(f"🔍 [DEBUG] 准备添加标签: {file_name}")

            try:
                index = self.addTab(editor, file_name)
                self.logger.info(f"🔍 [DEBUG] 标签添加成功，索引: {index}")

                # 设置标签提示（显示完整路径）
                self.setTabToolTip(index, file_path)

                # 切换到新标签
                self.setCurrentIndex(index)
                self.logger.info("🔍 [DEBUG] 已切换到新标签")

                # 发送信号
                self.file_opened.emit(file_path)

                self.logger.info(f"✓ 成功打开文件: {file_path}")
                return True
            except Exception as tab_error:
                self.logger.error(f"🔴 添加标签失败: {tab_error}", exc_info=True)
                # 清理已创建的编辑器
                if file_path in self.editors:
                    del self.editors[file_path]
                QMessageBox.critical(self, "标签错误", f"无法添加标签:\n{str(tab_error)}")
                return False

        except Exception as e:
            self.logger.error(f"打开文件失败: {file_path}, 错误: {e}", exc_info=True)
            QMessageBox.critical(self, "打开失败", f"打开文件时发生未知错误:\n{str(e)}")
            return False

    def close_file(self, file_path: str, force: bool = False) -> bool:
        """关闭文件.

        Args:
            file_path: 文件路径
            force: 是否强制关闭（不提示保存）

        Returns:
            bool: 是否成功关闭
        """
        try:
            if file_path not in self.editors:
                return False

            # 检查是否有未保存内容
            if not force and file_path in self.unsaved_files:
                reply = QMessageBox.question(
                    self,
                    "保存文件",
                    f"文件 '{Path(file_path).name}' 有未保存的修改。是否保存？",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )

                if reply == QMessageBox.StandardButton.Save:
                    # 保存文件
                    self.save_file(file_path)
                elif reply == QMessageBox.StandardButton.Cancel:
                    # 取消关闭
                    return False

            # 获取标签索引
            index = self._get_tab_index_by_path(file_path)
            if index >= 0:
                # 添加到最近关闭列表
                self.recently_closed.append(file_path)
                if len(self.recently_closed) > 10:
                    self.recently_closed.pop(0)

                # 移除标签
                self.removeTab(index)

            # 清理引用
            del self.editors[file_path]
            self.unsaved_files.discard(file_path)

            # 发送信号
            self.file_closed.emit(file_path)

            self.logger.info(f"成功关闭文件: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"关闭文件失败: {file_path}, 错误: {e}", exc_info=True)
            return False

    def save_file(self, file_path: Optional[str] = None) -> bool:
        """保存文件.

        Args:
            file_path: 文件路径（None表示保存当前文件）

        Returns:
            bool: 是否成功保存
        """
        try:
            # 如果未指定路径，保存当前文件
            if file_path is None:
                file_path = self.get_current_file_path()

            if not file_path or file_path not in self.editors:
                return False

            # 检查是否是只读模板文件
            normalized_path = file_path.replace("\\", "/")
            is_template = "strategies/templates/" in normalized_path
            if is_template:
                QMessageBox.warning(
                    self,
                    "无法保存",
                    f"文件 '{Path(file_path).name}' 是系统模板文件，不允许修改。\n\n"
                    "如需创建自定义策略，请使用「新建」功能。",
                )
                self.logger.warning(f"尝试保存只读模板文件被阻止: {file_path}")
                return False

            # 获取编辑器内容
            editor = self.editors[file_path]
            content = editor.toPlainText()

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # 清除未保存标记
            self.unsaved_files.discard(file_path)
            self._update_tab_title(file_path)

            # 发送信号
            self.file_saved.emit(file_path)

            self.logger.info(f"成功保存文件: {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"保存文件失败: {file_path}, 错误: {e}", exc_info=True)
            return False

    def save_all_files(self) -> int:
        """保存所有未保存的文件.

        Returns:
            int: 保存的文件数量
        """
        count = 0
        for file_path in list(self.unsaved_files):
            if self.save_file(file_path):
                count += 1

        self.logger.info(f"保存了 {count} 个文件")
        return count

    def close_all_files(self, force: bool = False) -> bool:
        """关闭所有文件.

        Args:
            force: 是否强制关闭（不提示保存）

        Returns:
            bool: 是否成功关闭所有文件
        """
        # 获取所有文件路径
        file_paths = list(self.editors.keys())

        for file_path in file_paths:
            if not self.close_file(file_path, force):
                # 用户取消了关闭
                return False

        return True

    # ==================== 编辑器访问 ====================

    def get_current_editor(self) -> Optional[Any]:
        """获取当前活动的编辑器.

        Returns:
            Optional[Any]: 当前编辑器组件，如果没有则返回None
        """
        current_widget = self.currentWidget()
        # 检查是否是编辑器组件（有 toPlainText 方法）
        if current_widget and hasattr(current_widget, "toPlainText"):
            return current_widget
        return None

    def get_current_file_path(self) -> Optional[str]:
        """获取当前文件路径.

        Returns:
            Optional[str]: 当前文件路径，如果没有则返回None
        """
        current_editor = self.get_current_editor()
        if current_editor:
            # 从字典中查找对应的路径
            for file_path, editor in self.editors.items():
                if editor == current_editor:
                    return file_path
        return None

    def get_all_file_paths(self) -> list:
        """获取所有打开的文件路径.

        Returns:
            list: 文件路径列表
        """
        return list(self.editors.keys())

    # ==================== 内部方法 ====================

    def _get_tab_index_by_path(self, file_path: str) -> int:
        """根据文件路径获取标签索引.

        Args:
            file_path: 文件路径

        Returns:
            int: 标签索引，未找到返回-1
        """
        editor = self.editors.get(file_path)
        if editor:
            return self.indexOf(editor)
        return -1

    def _on_content_changed(self, file_path: str):
        """内容变化回调.

        Args:
            file_path: 文件路径
        """
        # 检查是否是只读模板文件
        normalized_path = file_path.replace("\\", "/")
        is_template = "strategies/templates/" in normalized_path

        # 只读文件不应被标记为未保存
        if not is_template:
            # 标记为未保存
            self.unsaved_files.add(file_path)

            # 更新标签标题
            self._update_tab_title(file_path)

    def _update_tab_title(self, file_path: str):
        """更新标签标题.

        Args:
            file_path: 文件路径
        """
        index = self._get_tab_index_by_path(file_path)
        if index >= 0:
            file_name = Path(file_path).name

            # 检查是否是只读模板
            normalized_path = file_path.replace("\\", "/")
            is_template = "strategies/templates/" in normalized_path

            # 如果未保存，添加圆点标记
            if file_path in self.unsaved_files:
                title = f"● {file_name}"
            else:
                title = file_name

            # 如果是只读模板，添加[只读]标记
            if is_template:
                title = f"[只读] {title}"

            self.setTabText(index, title)

    def _on_tab_close_requested(self, index: int):
        """标签关闭按钮点击回调.

        Args:
            index: 标签索引
        """
        # 获取对应的文件路径
        widget = self.widget(index)
        for file_path, editor in self.editors.items():
            if editor == widget:
                self.close_file(file_path)
                break

    def _on_current_changed(self, index: int):
        """当前标签切换回调.

        Args:
            index: 新的标签索引
        """
        if index >= 0:
            file_path = self.get_current_file_path()
            if file_path:
                self.current_file_changed.emit(file_path)

    def _switch_to_next_tab(self):
        """切换到下一个标签."""
        current_index = self.currentIndex()
        next_index = (current_index + 1) % self.count()
        if next_index != current_index:
            self.setCurrentIndex(next_index)

    def _switch_to_prev_tab(self):
        """切换到上一个标签."""
        current_index = self.currentIndex()
        prev_index = (current_index - 1) % self.count()
        if prev_index != current_index:
            self.setCurrentIndex(prev_index)

    def _close_current_tab(self):
        """关闭当前标签."""
        file_path = self.get_current_file_path()
        if file_path:
            self.close_file(file_path)

    def _reopen_last_closed(self):
        """恢复最近关闭的标签."""
        if self.recently_closed:
            file_path = self.recently_closed.pop()
            if Path(file_path).exists():
                self.open_file(file_path)
                self.logger.info(f"恢复最近关闭的文件: {file_path}")

    def _show_context_menu(self, pos):
        """显示右键菜单.

        Args:
            pos: 鼠标位置
        """
        # 获取点击的标签索引
        tab_bar = self.tabBar()
        index = tab_bar.tabAt(pos)

        if index < 0:
            return

        # 创建菜单
        menu = QMenu(self)

        close_action = menu.addAction("关闭")
        close_others_action = menu.addAction("关闭其他")
        close_all_action = menu.addAction("关闭全部")
        menu.addSeparator()
        copy_path_action = menu.addAction("复制路径")

        # 执行菜单
        action = menu.exec(tab_bar.mapToGlobal(pos))

        if not action:
            return

        # 获取对应的文件路径
        widget = self.widget(index)
        current_file_path = None
        for file_path, editor in self.editors.items():
            if editor == widget:
                current_file_path = file_path
                break

        if not current_file_path:
            return

        # 处理菜单操作
        if action == close_action:
            self.close_file(current_file_path)

        elif action == close_others_action:
            # 关闭其他所有标签
            other_paths = [p for p in self.editors.keys() if p != current_file_path]
            for file_path in other_paths:
                self.close_file(file_path)

        elif action == close_all_action:
            self.close_all_files()

        elif action == copy_path_action:
            # 复制路径到剪贴板
            from PySide6.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            clipboard.setText(current_file_path)
            self.logger.info(f"已复制路径到剪贴板: {current_file_path}")


# ==================== 文件管理器组件 ====================
class FileExplorerTree(QTreeWidget, LoggerMixin):
    """增强文件管理器树形组件."""

    # 信号
    file_double_clicked = Signal(str)  # 文件双击信号
    file_selected = Signal(str)  # 文件选择信号

    def __init__(self, root_dir: str, parent: Optional[QWidget] = None):
        """初始化文件管理器.

        Args:
            root_dir: 根目录路径
            parent: 父组件
        """
        super().__init__(parent)

        self.root_dir = Path(root_dir).resolve()

        # 剪贴板（用于复制/剪切/粘贴）
        self.clipboard: List[Path] = []
        self.clipboard_mode = None  # 'copy' or 'cut'

        # 设置UI
        self._setup_ui()

        # 连接信号
        self._connect_signals()

        # 加载文件树
        self.refresh()

        self.logger.info(f"文件管理器初始化完成，根目录: {self.root_dir}")

    def _setup_ui(self):
        """设置用户界面."""
        # 隐藏表头
        self.setHeaderHidden(True)

        # 启用多选
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

        # 启用拖拽
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)

        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # 设置样式
        self.setAlternatingRowColors(True)

    def _connect_signals(self):
        """连接信号槽."""
        # 双击事件
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

        # 选择事件
        self.itemSelectionChanged.connect(self._on_selection_changed)

    # ==================== 文件树构建 ====================

    def refresh(self):
        """刷新文件树."""
        try:
            self.clear()

            # 添加根节点（带文件夹图标）
            root_item = QTreeWidgetItem()
            root_item.setText(0, f"📁 {self.root_dir.name}")
            root_item.setData(
                0, Qt.ItemDataRole.UserRole, {"type": "directory", "path": str(self.root_dir)}
            )
            root_item.setExpanded(True)
            # 确保显示子节点指示器（展开/折叠箭头）
            root_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            self.addTopLevelItem(root_item)

            # 递归加载子目录和文件
            self._load_directory(root_item, self.root_dir)

            self.logger.info("文件树刷新完成")

        except Exception as e:
            self.logger.error(f"刷新文件树失败: {e}", exc_info=True)

    def _load_directory(self, parent_item: QTreeWidgetItem, directory: Path):
        """递归加载目录内容.

        Args:
            parent_item: 父节点
            directory: 目录路径
        """
        try:
            if not directory.is_dir():
                return

            # 获取目录内容
            items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            self.logger.debug(f"加载目录 {directory}，找到 {len(items)} 个项目")

            for item_path in items:
                # 跳过隐藏文件和__pycache__
                if item_path.name.startswith(".") or item_path.name == "__pycache__":
                    self.logger.debug(f"跳过: {item_path.name}")
                    continue

                self.logger.debug(f"处理: {item_path.name} (是目录: {item_path.is_dir()})")

                # 创建树节点
                item = QTreeWidgetItem()

                if item_path.is_dir():
                    # 文件夹
                    item.setText(0, f"📁 {item_path.name}")
                    item.setData(
                        0, Qt.ItemDataRole.UserRole, {"type": "directory", "path": str(item_path)}
                    )
                    # 确保文件夹节点显示展开/折叠箭头
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                    parent_item.addChild(item)

                    # 递归加载子目录
                    self._load_directory(item, item_path)

                else:
                    # 文件
                    icon = self._get_file_icon(item_path)
                    item.setText(0, f"{icon} {item_path.name}")
                    item.setData(
                        0, Qt.ItemDataRole.UserRole, {"type": "file", "path": str(item_path)}
                    )
                    parent_item.addChild(item)

        except PermissionError:
            self.logger.warning(f"无权限访问目录: {directory}")
        except Exception as e:
            self.logger.error(f"加载目录失败: {directory}, 错误: {e}")

    def _get_file_icon(self, file_path: Path) -> str:
        """获取文件图标（Emoji）.

        Args:
            file_path: 文件路径

        Returns:
            str: 图标字符
        """
        suffix = file_path.suffix.lower()

        # Python文件
        if suffix == ".py":
            return "🐍"
        # JSON文件
        elif suffix == ".json":
            return "📋"
        # Markdown文件
        elif suffix in [".md", ".markdown"]:
            return "📝"
        # 文本文件
        elif suffix in [".txt", ".log"]:
            return "📄"
        # 配置文件
        elif suffix in [".ini", ".cfg", ".conf", ".yaml", ".yml"]:
            return "⚙️"
        # 其他
        else:
            return "📄"

    # ==================== 事件处理 ====================

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """节点双击事件.

        Args:
            item: 树节点
            column: 列索引
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # 如果是文件，发送双击信号
        if data["type"] == "file":
            # 🔧 修复：规范化路径（确保使用绝对路径）
            file_path = str(Path(data["path"]).resolve())
            self.file_double_clicked.emit(file_path)
            self.logger.info(f"双击文件: {file_path}")

    def _on_selection_changed(self):
        """选择变化事件."""
        selected_items = self.selectedItems()
        if selected_items:
            item = selected_items[0]
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data["type"] == "file":
                self.file_selected.emit(data["path"])

    # ==================== 右键菜单 ====================

    def _show_context_menu(self, pos):
        """显示右键菜单.

        Args:
            pos: 鼠标位置
        """
        item = self.itemAt(pos)

        # 创建菜单
        menu = QMenu(self)

        # 新建菜单
        new_file_action = menu.addAction("📄 新建文件")
        new_folder_action = menu.addAction("📁 新建文件夹")

        menu.addSeparator()

        # 编辑菜单（需要选中项）
        rename_action = None
        delete_action = None
        copy_action = None
        cut_action = None
        if item:
            rename_action = menu.addAction("✏️ 重命名")
            delete_action = menu.addAction("🗑️ 删除")
            menu.addSeparator()
            copy_action = menu.addAction("📋 复制")
            cut_action = menu.addAction("✂️ 剪切")

        # 粘贴菜单（需要剪贴板有内容）
        paste_action = None
        if self.clipboard:
            paste_action = menu.addAction("📌 粘贴")

        menu.addSeparator()
        refresh_action = menu.addAction("🔄 刷新")

        # 执行菜单
        action = menu.exec(self.mapToGlobal(pos))

        if not action:
            return

        # 处理菜单操作
        try:
            if action == new_file_action:
                self._create_new_file(item)
            elif action == new_folder_action:
                self._create_new_folder(item)
            elif item and action == rename_action:
                self._rename_item(item)
            elif item and action == delete_action:
                self._delete_item(item)
            elif item and action == copy_action:
                self._copy_item(item)
            elif item and action == cut_action:
                self._cut_item(item)
            elif self.clipboard and action == paste_action:
                self._paste_item(item)
            elif action == refresh_action:
                self.refresh()

        except Exception as e:
            self.logger.error(f"菜单操作失败: {e}", exc_info=True)
            QMessageBox.critical(self, "错误", f"操作失败: {str(e)}")

    def _create_new_file(self, parent_item: Optional[QTreeWidgetItem]):
        """创建新文件.

        Args:
            parent_item: 父节点（如果为None，则在根目录创建）
        """
        # 确定父目录
        if parent_item:
            data = parent_item.data(0, Qt.ItemDataRole.UserRole)
            if data["type"] == "directory":
                parent_dir = Path(data["path"])
            else:
                # 如果选中的是文件，使用其父目录
                parent_dir = Path(data["path"]).parent
        else:
            parent_dir = self.root_dir

        # 输入文件名
        file_name, ok = QInputDialog.getText(
            self, "新建文件", "请输入文件名:", text="new_strategy.py"
        )

        if ok and file_name:
            file_path = parent_dir / file_name

            # 检查文件是否已存在
            if file_path.exists():
                QMessageBox.warning(self, "警告", f"文件已存在: {file_name}")
                return

            # 创建文件
            file_path.touch()

            # 刷新文件树
            self.refresh()

            self.logger.info(f"创建新文件: {file_path}")
            QMessageBox.information(self, "成功", f"文件创建成功: {file_name}")

    def _create_new_folder(self, parent_item: Optional[QTreeWidgetItem]):
        """创建新文件夹.

        Args:
            parent_item: 父节点
        """
        # 确定父目录
        if parent_item:
            data = parent_item.data(0, Qt.ItemDataRole.UserRole)
            if data["type"] == "directory":
                parent_dir = Path(data["path"])
            else:
                parent_dir = Path(data["path"]).parent
        else:
            parent_dir = self.root_dir

        # 输入文件夹名
        folder_name, ok = QInputDialog.getText(self, "新建文件夹", "请输入文件夹名:")

        if ok and folder_name:
            folder_path = parent_dir / folder_name

            # 检查是否已存在
            if folder_path.exists():
                QMessageBox.warning(self, "警告", f"文件夹已存在: {folder_name}")
                return

            # 创建文件夹
            folder_path.mkdir(parents=True)

            # 刷新文件树
            self.refresh()

            self.logger.info(f"创建新文件夹: {folder_path}")
            QMessageBox.information(self, "成功", f"文件夹创建成功: {folder_name}")

    def _rename_item(self, item: QTreeWidgetItem):
        """重命名项.

        Args:
            item: 树节点
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        old_path = Path(data["path"])
        old_name = old_path.name

        # 输入新名称
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新名称:", text=old_name)

        if ok and new_name and new_name != old_name:
            new_path = old_path.parent / new_name

            # 检查是否已存在
            if new_path.exists():
                QMessageBox.warning(self, "警告", f"名称已存在: {new_name}")
                return

            # 重命名
            old_path.rename(new_path)

            # 刷新文件树
            self.refresh()

            self.logger.info(f"重命名: {old_path} -> {new_path}")
            QMessageBox.information(self, "成功", f"重命名成功: {old_name} -> {new_name}")

    def _delete_item(self, item: QTreeWidgetItem):
        """删除项.

        Args:
            item: 树节点
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        path = Path(data["path"])

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除 '{path.name}' 吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 删除文件或目录
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

            # 刷新文件树
            self.refresh()

            self.logger.info(f"删除: {path}")
            QMessageBox.information(self, "成功", f"删除成功: {path.name}")

    def _copy_item(self, item: QTreeWidgetItem):
        """复制项.

        Args:
            item: 树节点
        """
        selected_items = self.selectedItems()
        self.clipboard = []

        for selected_item in selected_items:
            data = selected_item.data(0, Qt.ItemDataRole.UserRole)
            self.clipboard.append(Path(data["path"]))

        self.clipboard_mode = "copy"

        self.logger.info(f"复制 {len(self.clipboard)} 个项")

    def _cut_item(self, item: QTreeWidgetItem):
        """剪切项.

        Args:
            item: 树节点
        """
        selected_items = self.selectedItems()
        self.clipboard = []

        for selected_item in selected_items:
            data = selected_item.data(0, Qt.ItemDataRole.UserRole)
            self.clipboard.append(Path(data["path"]))

        self.clipboard_mode = "cut"

        self.logger.info(f"剪切 {len(self.clipboard)} 个项")

    def _paste_item(self, target_item: Optional[QTreeWidgetItem]):
        """粘贴项.

        Args:
            target_item: 目标节点
        """
        if not self.clipboard:
            return

        # 确定目标目录
        if target_item:
            data = target_item.data(0, Qt.ItemDataRole.UserRole)
            if data["type"] == "directory":
                target_dir = Path(data["path"])
            else:
                target_dir = Path(data["path"]).parent
        else:
            target_dir = self.root_dir

        # 执行复制或移动
        for source_path in self.clipboard:
            target_path = target_dir / source_path.name

            # 检查是否已存在
            if target_path.exists():
                QMessageBox.warning(self, "警告", f"目标已存在: {source_path.name}")
                continue

            try:
                if self.clipboard_mode == "copy":
                    # 复制
                    if source_path.is_dir():
                        shutil.copytree(source_path, target_path)
                    else:
                        shutil.copy2(source_path, target_path)
                    self.logger.info(f"复制: {source_path} -> {target_path}")

                elif self.clipboard_mode == "cut":
                    # 移动
                    shutil.move(str(source_path), str(target_path))
                    self.logger.info(f"移动: {source_path} -> {target_path}")

            except Exception as e:
                self.logger.error(f"粘贴失败: {e}")
                QMessageBox.critical(self, "错误", f"粘贴失败: {str(e)}")

        # 清空剪贴板（仅剪切模式）
        if self.clipboard_mode == "cut":
            self.clipboard.clear()
            self.clipboard_mode = None

        # 刷新文件树
        self.refresh()

        QMessageBox.information(self, "成功", "粘贴成功")


class FileExplorerWidget(QWidget, LoggerMixin):
    """文件管理器组件（包含搜索框）."""

    # 信号
    file_double_clicked = Signal(str)
    file_selected = Signal(str)

    def __init__(self, root_dir: str, parent: Optional[QWidget] = None):
        """初始化文件管理器组件.

        Args:
            root_dir: 根目录
            parent: 父组件
        """
        super().__init__(parent)

        self.root_dir = root_dir

        # 设置UI
        self._setup_ui()

        # 连接信号
        self._connect_signals()

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 搜索框
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setMinimumWidth(40)
        refresh_btn.setMaximumWidth(50)
        refresh_btn.setMinimumHeight(25)
        refresh_btn.setToolTip("刷新文件列表")
        # 设置字体大小以确保emoji正常显示
        refresh_btn.setStyleSheet(
            """
            QPushButton {
                font-size: 16px;
                padding: 2px;
            }
        """
        )
        refresh_btn.clicked.connect(self._refresh_tree)
        search_layout.addWidget(refresh_btn)

        layout.addLayout(search_layout)

        # 文件树
        self.tree = FileExplorerTree(self.root_dir)
        layout.addWidget(self.tree)

    def _connect_signals(self):
        """连接信号槽."""
        # 转发文件树信号
        self.tree.file_double_clicked.connect(self.file_double_clicked.emit)
        self.tree.file_selected.connect(self.file_selected.emit)

        # 搜索框变化
        self.search_input.textChanged.connect(self._on_search_text_changed)

    def _refresh_tree(self):
        """刷新文件树."""
        self.tree.refresh()
        self.logger.info("文件树已刷新")

    def _on_search_text_changed(self, text: str):
        """搜索文本变化.

        Args:
            text: 搜索文本
        """
        # 简单的文件名过滤
        self._filter_tree(text.lower())

    def _filter_tree(self, filter_text: str):
        """过滤文件树.

        Args:
            filter_text: 过滤文本
        """
        # 遍历所有节点
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()

            # 获取节点文本（移除图标）
            text = item.text(0)
            if text.startswith(("📁", "🐍", "📋", "📝", "📄", "⚙️")):
                text = text[2:]  # 移除图标和空格

            # 检查是否匹配
            if not filter_text or filter_text in text.lower():
                item.setHidden(False)
            else:
                item.setHidden(True)

            iterator += 1

    def refresh(self):
        """刷新文件树."""
        self.tree.refresh()


# ==================== 搜索面板组件 ====================
class SearchPanel(QWidget, LoggerMixin):
    """全局搜索和替换面板."""

    # 信号
    file_selected = Signal(str, int)  # 选择文件和行号

    def __init__(self, search_root: str, parent: Optional[QWidget] = None):
        """初始化搜索面板.

        Args:
            search_root: 搜索根目录
            parent: 父组件
        """
        super().__init__(parent)

        self.search_root = Path(search_root)
        self.search_results: List[Dict] = []

        # 设置UI
        self._setup_ui()

        self.logger.info(f"搜索面板初始化完成，搜索根目录: {self.search_root}")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)

        # 搜索输入区
        search_group = QGroupBox("搜索")
        search_layout = QVBoxLayout(search_group)

        # 搜索框
        search_input_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容...")
        self.search_input.returnPressed.connect(self._do_search)
        search_input_layout.addWidget(self.search_input)

        search_btn = QPushButton("🔍 搜索")
        search_btn.clicked.connect(self._do_search)
        search_input_layout.addWidget(search_btn)

        search_layout.addLayout(search_input_layout)

        # 替换框
        replace_layout = QHBoxLayout()
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("替换为...")
        replace_layout.addWidget(self.replace_input)

        replace_btn = QPushButton("替换")
        replace_btn.clicked.connect(self._do_replace)
        replace_layout.addWidget(replace_btn)

        replace_all_btn = QPushButton("全部替换")
        replace_all_btn.clicked.connect(self._do_replace_all)
        replace_layout.addWidget(replace_all_btn)

        search_layout.addLayout(replace_layout)

        # 搜索选项
        options_layout = QHBoxLayout()

        self.case_sensitive_cb = QCheckBox("大小写敏感")
        options_layout.addWidget(self.case_sensitive_cb)

        self.regex_cb = QCheckBox("正则表达式")
        options_layout.addWidget(self.regex_cb)

        self.whole_word_cb = QCheckBox("全词匹配")
        options_layout.addWidget(self.whole_word_cb)

        options_layout.addStretch()

        search_layout.addLayout(options_layout)

        layout.addWidget(search_group)

        # 搜索结果区
        results_group = QGroupBox("搜索结果")
        results_layout = QVBoxLayout(results_group)

        # 结果统计标签
        self.result_count_label = QLabel("就绪")
        results_layout.addWidget(self.result_count_label)

        # 结果树
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["文件 / 行号 : 内容"])
        self.result_tree.itemDoubleClicked.connect(self._on_result_double_clicked)
        results_layout.addWidget(self.result_tree)

        layout.addWidget(results_group)

    def _do_search(self):
        """执行搜索."""
        pattern = self.search_input.text().strip()
        if not pattern:
            self.logger.warning("搜索内容为空")
            return

        # 清空之前的结果
        self.result_tree.clear()
        self.search_results.clear()

        # 获取搜索选项
        case_sensitive = self.case_sensitive_cb.isChecked()
        is_regex = self.regex_cb.isChecked()
        whole_word = self.whole_word_cb.isChecked()

        self.logger.info(f"开始搜索: '{pattern}', 正则={is_regex}, 大小写={case_sensitive}")

        try:
            # 搜索所有.py文件
            files = list(self.search_root.rglob("*.py"))
            total_matches = 0

            for file_path in files:
                # 跳过__pycache__
                if "__pycache__" in str(file_path):
                    continue

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # 搜索每一行
                    matches = []
                    for line_num, line in enumerate(lines, 1):
                        if self._match_line(line, pattern, case_sensitive, is_regex, whole_word):
                            matches.append({"line_num": line_num, "content": line.rstrip()})
                            total_matches += 1

                    # 如果有匹配，添加到结果树
                    if matches:
                        self.search_results.append({"file": str(file_path), "matches": matches})
                        self._add_file_to_tree(file_path, matches)

                except Exception as e:
                    self.logger.error(f"搜索文件失败: {file_path}, 错误: {e}")

            # 更新统计
            file_count = len(self.search_results)
            self.result_count_label.setText(
                f"找到 {total_matches} 处匹配（共 {file_count} 个文件）"
            )

            self.logger.info(f"搜索完成: {total_matches} 处匹配")

        except Exception as e:
            self.logger.error(f"搜索失败: {e}", exc_info=True)

    def _match_line(
        self, line: str, pattern: str, case_sensitive: bool, is_regex: bool, whole_word: bool
    ) -> bool:
        """检查行是否匹配搜索模式.

        Args:
            line: 行内容
            pattern: 搜索模式
            case_sensitive: 是否大小写敏感
            is_regex: 是否正则表达式
            whole_word: 是否全词匹配

        Returns:
            bool: 是否匹配
        """
        try:
            if is_regex:
                # 正则表达式模式
                flags = 0 if case_sensitive else re.IGNORECASE
                return bool(re.search(pattern, line, flags))
            else:
                # 普通搜索
                if whole_word:
                    # 全词匹配
                    pattern_escaped = re.escape(pattern)
                    pattern_regex = rf"\b{pattern_escaped}\b"
                    flags = 0 if case_sensitive else re.IGNORECASE
                    return bool(re.search(pattern_regex, line, flags))
                else:
                    # 普通子字符串匹配
                    if case_sensitive:
                        return pattern in line
                    else:
                        return pattern.lower() in line.lower()
        except re.error:
            # 正则表达式错误
            return False

    def _add_file_to_tree(self, file_path: Path, matches: List[Dict]):
        """添加文件到结果树.

        Args:
            file_path: 文件路径
            matches: 匹配列表
        """
        # 创建文件节点
        file_item = QTreeWidgetItem()
        file_item.setText(0, f"📄 {file_path.name} ({len(matches)}处)")
        file_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "file", "path": str(file_path)})
        self.result_tree.addTopLevelItem(file_item)

        # 添加匹配行
        for match in matches:
            line_item = QTreeWidgetItem()
            line_text = f"  行 {match['line_num']}: {match['content'][:80]}"
            line_item.setText(0, line_text)
            line_item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                {
                    "type": "match",
                    "path": str(file_path),
                    "line_num": match["line_num"],
                    "content": match["content"],
                },
            )
            file_item.addChild(line_item)

        # 展开文件节点
        file_item.setExpanded(True)

    def _on_result_double_clicked(self, item: QTreeWidgetItem, column: int):
        """结果双击事件.

        Args:
            item: 树节点
            column: 列索引
        """
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        if data["type"] == "match":
            # 跳转到文件和行号
            file_path = data["path"]
            line_num = data["line_num"]
            self.file_selected.emit(file_path, line_num)
            self.logger.info(f"跳转到: {file_path}:{line_num}")

    def _do_replace(self):
        """替换当前选中的匹配."""
        selected_items = self.result_tree.selectedItems()
        if not selected_items:
            self.logger.warning("未选择要替换的项")
            return

        replace_text = self.replace_input.text()
        search_text = self.search_input.text()

        replace_count = 0

        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data["type"] == "match":
                file_path = Path(data["path"])
                line_num = data["line_num"]

                try:
                    # 读取文件
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    # 替换指定行
                    if 0 < line_num <= len(lines):
                        old_line = lines[line_num - 1]
                        new_line = old_line.replace(search_text, replace_text)
                        lines[line_num - 1] = new_line

                        # 写回文件
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)

                        replace_count += 1
                        self.logger.info(f"已替换: {file_path}:{line_num}")

                except Exception as e:
                    self.logger.error(f"替换失败: {file_path}:{line_num}, 错误: {e}")

        if replace_count > 0:
            self.logger.info(f"完成替换: {replace_count} 处")
            # 重新搜索以更新结果
            self._do_search()

    def _do_replace_all(self):
        """替换所有匹配."""
        if not self.search_results:
            self.logger.warning("没有搜索结果")
            return

        replace_text = self.replace_input.text()
        search_text = self.search_input.text()

        replace_count = 0

        for result in self.search_results:
            file_path = Path(result["file"])

            try:
                # 读取文件
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # 替换所有匹配
                new_content = content.replace(search_text, replace_text)

                if new_content != content:
                    # 写回文件
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    replace_count += len(result["matches"])
                    self.logger.info(f"已替换文件: {file_path}")

            except Exception as e:
                self.logger.error(f"替换文件失败: {file_path}, 错误: {e}")

        if replace_count > 0:
            self.logger.info(f"完成全部替换: {replace_count} 处")
            # 重新搜索以更新结果
            self._do_search()


# ==================== 终端组件 ====================
class TerminalWidget(QWidget, LoggerMixin):
    """内置终端组件."""

    # 信号
    command_executed = Signal(str)  # 命令执行信号

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化终端组件."""
        super().__init__(parent)

        # 命令历史
        self.command_history: List[str] = []
        self.history_index = -1
        self.max_history = 100

        # Python环境
        self.python_globals = {}
        self.python_locals = {}

        # 设置UI
        self._setup_ui()

        # 初始化Python环境
        self._init_python_env()

        # 显示欢迎信息
        self._show_welcome()

        self.logger.info("终端组件初始化完成")

    def _setup_ui(self):
        """设置用户界面."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 输出区域
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas, Monaco, Courier New", 10))
        self.output_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
            }
        """
        )
        layout.addWidget(self.output_text)

        # 输入区域
        input_layout = QHBoxLayout()

        # 提示符
        prompt_label = QPushButton(">>>")
        prompt_label.setMaximumWidth(40)
        prompt_label.setFlat(True)
        prompt_label.setStyleSheet(
            """
            QPushButton {
                background-color: #1E1E1E;
                color: #4EC9B0;
                border: none;
                font-family: 'Consolas, Monaco, Courier New';
                font-size: 10pt;
                text-align: right;
                padding-right: 5px;
            }
        """
        )
        input_layout.addWidget(prompt_label)

        # 输入框
        self.input_line = QLineEdit()
        self.input_line.setFont(QFont("Consolas, Monaco, Courier New", 10))
        self.input_line.setStyleSheet(
            """
            QLineEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                padding: 3px;
            }
        """
        )
        self.input_line.returnPressed.connect(self._execute_command)
        input_layout.addWidget(self.input_line)

        # 清空按钮
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self._clear_output)
        input_layout.addWidget(clear_btn)

        layout.addLayout(input_layout)

        # 设置焦点
        self.input_line.setFocus()

    def _init_python_env(self):
        """初始化Python环境."""
        # 导入常用模块
        self.python_globals = {
            "__name__": "__console__",
            "__doc__": None,
        }

        # 导入常用库
        try:
            import numpy as np
            import pandas as pd

            self.python_globals["np"] = np
            self.python_globals["pd"] = pd
            self.python_globals["Path"] = Path

            self.logger.info("Python环境初始化完成（numpy, pandas, Path）")
        except ImportError as e:
            self.logger.warning(f"导入模块失败: {e}")

    def _show_welcome(self):
        """显示欢迎信息."""
        welcome_text = f"""
<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>
<span style='color: #DCDCAA;'>欢迎使用策略中心 Python 终端</span>
<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>

<span style='color: #9CDCFE;'>Python版本:</span> {sys.version}

<span style='color: #9CDCFE;'>可用模块:</span> numpy (np), pandas (pd), Path

<span style='color: #9CDCFE;'>提示:</span>
  • 输入Python代码并按Enter执行
  • 使用 ↑↓ 键浏览命令历史
  • 输入 help() 查看帮助
  • 输入 clear() 清空屏幕

<span style='color: #4EC9B0;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>
"""
        self.output_text.append(welcome_text)

    def _execute_command(self):
        """执行命令."""
        command = self.input_line.text().strip()
        if not command:
            return

        # 添加到历史
        self.command_history.append(command)
        if len(self.command_history) > self.max_history:
            self.command_history.pop(0)
        self.history_index = len(self.command_history)

        # 清空输入框
        self.input_line.clear()

        # 显示命令
        self._append_output(f"<span style='color: #4EC9B0;'>&gt;&gt;&gt;</span> {command}")

        # 特殊命令处理
        if command == "clear()" or command == "clear":
            self._clear_output()
            return

        if command == "help()" or command == "help":
            self._show_help()
            return

        # 执行Python代码
        self._execute_python(command)

        # 发送信号
        self.command_executed.emit(command)

    def _execute_python(self, code: str):
        """执行Python代码.

        Args:
            code: Python代码
        """
        try:
            # 重定向stdout和stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = StringIO()
            sys.stderr = StringIO()

            try:
                # 尝试作为表达式执行（有返回值）
                result = eval(code, self.python_globals, self.python_locals)

                # 获取输出
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()

                # 显示输出
                if stdout_output:
                    self._append_output(f"<span style='color: #CE9178;'>{stdout_output}</span>")

                if stderr_output:
                    self._append_output(f"<span style='color: #F48771;'>{stderr_output}</span>")

                # 显示返回值（除了None）
                if result is not None:
                    self._append_output(f"<span style='color: #DCDCAA;'>{repr(result)}</span>")

            except SyntaxError:
                # 作为语句执行（无返回值）
                sys.stdout = StringIO()
                sys.stderr = StringIO()

                exec(code, self.python_globals, self.python_locals)

                # 获取输出
                stdout_output = sys.stdout.getvalue()
                stderr_output = sys.stderr.getvalue()

                # 显示输出
                if stdout_output:
                    self._append_output(f"<span style='color: #CE9178;'>{stdout_output}</span>")

                if stderr_output:
                    self._append_output(f"<span style='color: #F48771;'>{stderr_output}</span>")

            finally:
                # 恢复stdout和stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        except Exception as e:
            # 显示错误
            error_msg = f"{type(e).__name__}: {str(e)}"
            self._append_output(f"<span style='color: #F48771;'>❌ {error_msg}</span>")
            self.logger.error(f"Python代码执行失败: {e}", exc_info=True)

    def _append_output(self, text: str):
        """添加输出文本.

        Args:
            text: 输出文本
        """
        self.output_text.append(text)

        # 滚动到底部
        cursor = self.output_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.output_text.setTextCursor(cursor)

    def _clear_output(self):
        """清空输出."""
        self.output_text.clear()
        self._show_welcome()

    def _show_help(self):
        """显示帮助信息."""
        help_text = """
<span style='color: #DCDCAA;'>━━━ 帮助信息 ━━━</span>

<span style='color: #9CDCFE;'>可用命令:</span>
  • clear() - 清空屏幕
  • help() - 显示此帮助信息
  • dir(obj) - 列出对象的属性
  • type(obj) - 查看对象类型
  • help(obj) - 查看对象帮助文档

<span style='color: #9CDCFE;'>可用模块:</span>
  • np - NumPy
  • pd - Pandas
  • Path - pathlib.Path

<span style='color: #9CDCFE;'>示例:</span>
  &gt;&gt;&gt; 1 + 1
  &gt;&gt;&gt; print("Hello, World!")
  &gt;&gt;&gt; import math
  &gt;&gt;&gt; math.sqrt(16)
  &gt;&gt;&gt; df = pd.DataFrame({'A': [1, 2, 3]})
"""
        self._append_output(help_text)

    def keyPressEvent(self, event):
        """按键事件."""
        if event.key() == Qt.Key.Key_Up:
            # 向上浏览历史
            if self.command_history and self.history_index > 0:
                self.history_index -= 1
                self.input_line.setText(self.command_history[self.history_index])

        elif event.key() == Qt.Key.Key_Down:
            # 向下浏览历史
            if self.command_history and self.history_index < len(self.command_history) - 1:
                self.history_index += 1
                self.input_line.setText(self.command_history[self.history_index])
            elif self.history_index == len(self.command_history) - 1:
                self.history_index = len(self.command_history)
                self.input_line.clear()

        else:
            super().keyPressEvent(event)

    def write(self, text: str):
        """写入输出（用于重定向输出）.

        Args:
            text: 输出文本
        """
        self._append_output(text.rstrip())

    def execute_code(self, code: str):
        """执行代码（外部调用）.

        Args:
            code: Python代码
        """
        self._append_output(f"<span style='color: #4EC9B0;'>&gt;&gt;&gt;</span> {code}")
        self._execute_python(code)


class StrategyCenter(BaseWidget, LoggerMixin):
    """策略中心主界面 - 现代IDE风格."""

    def __init__(self, parent=None):
        """初始化策略中心."""
        # 初始化服务管理器
        self.service_manager = get_service_manager()
        self.strategy_service = None

        # 初始化UI组件
        self.file_explorer: Optional[FileExplorerWidget] = None
        self.editor_tabs: Optional[EditorTabWidget] = None
        self.ai_assistant_widget: Optional[QWidget] = None
        self.ai_assistant_btn: Optional[QPushButton] = None
        self.ai_response: Optional[QTextEdit] = None
        self.user_input: Optional[QLineEdit] = None

        # 标签页组件
        self.content_tab: Optional[QTabWidget] = None
        self.editor_tab: Optional[QWidget] = None
        self.backtest_tab: Optional[QWidget] = None

        # 回测相关组件
        self.backtest_panel: Optional[QWidget] = None
        self.backtest_target_combo: Optional[QComboBox] = None
        self.renderer_type_combo: Optional[QComboBox] = None
        self.start_date_input: Optional[QLineEdit] = None
        self.end_date_input: Optional[QLineEdit] = None
        self.run_backtest_btn: Optional[QPushButton] = None
        self.stop_backtest_btn: Optional[QPushButton] = None
        self.backtest_progress: Optional[QProgressBar] = None
        self.backtest_status_label: Optional[QLabel] = None
        self.backtest_results: Optional[QTextEdit] = None

        # 回测任务追踪
        self.current_backtest_task_id: Optional[str] = None
        self.backtest_timer: Optional[QTimer] = None

        # 调用父类初始化
        super().__init__(parent, "策略中心")
        self.logger.info("策略中心界面初始化开始")

        # 初始化服务
        self._initialize_service()

    def _initialize_service(self):
        """获取策略中心服务."""
        try:
            self.strategy_service = self.service_manager.get_service("strategy_center_service")
            if self.strategy_service:
                self.logger.info("策略中心服务获取成功")
            else:
                self.logger.warning("策略中心服务未注册")
        except Exception as e:
            self.logger.error("获取策略中心服务失败: %s", e)
            self.show_error(f"服务获取失败: {e}")

    def setup_ui(self):
        """设置用户界面 - 左侧策略管理器 + 右侧子页面切换."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 创建主分割器（水平）
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：策略/指标管理器（固定组件）
        left_widget = self._create_strategy_manager()
        main_splitter.addWidget(left_widget)

        # 右侧：子界面区域（QTabWidget切换）
        right_widget = self._create_content_tabs()
        main_splitter.addWidget(right_widget)

        # 设置初始大小比例：左侧250，右侧800
        main_splitter.setSizes([250, 800])

        main_layout.addWidget(main_splitter)

        # 在所有组件创建完成后连接信号
        self.connect_signals()

    def _create_strategy_manager(self) -> QWidget:
        """创建策略/指标管理器（固定组件）.

        Returns:
            QWidget: 策略管理器组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📁 策略/指标管理器")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 文件管理器（使用增强版，使用绝对路径确保正确）
        strategies_dir = Path(__file__).parent.parent.parent.parent / "strategies"
        self.file_explorer = FileExplorerWidget(str(strategies_dir.resolve()))
        layout.addWidget(self.file_explorer)

        self.logger.info("文件管理器根目录: %s", strategies_dir.resolve())

        return widget

    def _create_content_tabs(self) -> QWidget:
        """创建右侧内容标签页（子界面切换）.

        Returns:
            QWidget: 内容标签页组件
        """
        # 创建标签页容器
        self.content_tab = QTabWidget()
        self.content_tab.setDocumentMode(True)

        # Tab1: 策略编写（IDE编辑器）
        self.editor_tab = self._create_editor_tab()
        self.content_tab.addTab(self.editor_tab, "📝 策略编写")

        # Tab2: 策略回测
        self.backtest_tab = self._create_backtest_tab()
        self.content_tab.addTab(self.backtest_tab, "📊 策略回测")

        return self.content_tab

    def _create_editor_tab(self) -> QWidget:
        """创建策略编写标签页.

        Returns:
            QWidget: 编辑器标签页组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # 编辑器 + AI助手（水平分割）
        editor_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 多标签编辑器
        self.editor_tabs = EditorTabWidget()
        editor_splitter.addWidget(self.editor_tabs)

        # AI助手
        self.ai_assistant_widget = self._create_ai_assistant()
        editor_splitter.addWidget(self.ai_assistant_widget)
        self.ai_assistant_widget.setVisible(False)

        editor_splitter.setSizes([800, 300])

        layout.addWidget(editor_splitter)

        return widget

    def _create_backtest_tab(self) -> QWidget:
        """创建策略回测标签页.

        Returns:
            QWidget: 回测标签页组件
        """
        # 使用现有的回测面板创建方法
        return self._create_backtest_panel()

    def _create_toolbar(self) -> QWidget:
        """创建工具栏.

        Returns:
            QWidget: 工具栏组件
        """
        toolbar = QWidget()
        # 设置固定高度，防止工具栏占据过多空间
        toolbar.setFixedHeight(45)

        layout = QHBoxLayout(toolbar)
        # 设置合理的边距
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(5)  # 设置统一的紧凑间距

        # 文件操作按钮组
        new_btn = QPushButton("📄 新建")
        new_btn.setMinimumWidth(80)
        new_btn.setMaximumWidth(100)
        new_btn.clicked.connect(self._create_new_strategy)
        layout.addWidget(new_btn)

        save_btn = QPushButton("💾 保存")
        save_btn.setMinimumWidth(80)
        save_btn.setMaximumWidth(100)
        save_btn.clicked.connect(self._save_current_file)
        layout.addWidget(save_btn)

        save_all_btn = QPushButton("💾 保存全部")
        save_all_btn.setMinimumWidth(100)
        save_all_btn.setMaximumWidth(120)
        save_all_btn.clicked.connect(self._save_all_files)
        layout.addWidget(save_all_btn)

        # 格式化按钮
        format_btn = QPushButton("⚡ 格式化")
        format_btn.setMinimumWidth(90)
        format_btn.setMaximumWidth(110)
        format_btn.clicked.connect(self._format_code)
        layout.addWidget(format_btn)

        # 添加视觉分隔符
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setFixedHeight(25)
        layout.addWidget(separator)

        # AI助手按钮
        self.ai_assistant_btn = QPushButton("🤖 AI助手")
        self.ai_assistant_btn.setCheckable(True)
        self.ai_assistant_btn.setMinimumWidth(100)
        self.ai_assistant_btn.setMaximumWidth(120)
        self.ai_assistant_btn.toggled.connect(self._toggle_ai_assistant)
        layout.addWidget(self.ai_assistant_btn)

        # 添加弹性空间，将后续内容推到右边
        layout.addStretch()

        # 当前文件路径标签
        current_file_label = QLabel("就绪")
        current_file_label.setStyleSheet("color: #888; padding-right: 10px;")
        layout.addWidget(current_file_label)

        # 连接信号：当前文件切换时更新标签
        if self.editor_tabs:
            self.editor_tabs.current_file_changed.connect(
                lambda path: current_file_label.setText(f"📄 {Path(path).name}")
            )

        return toolbar

    def _create_ai_assistant(self) -> QWidget:
        """创建AI助手组件.

        Returns:
            QWidget: AI助手组件
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # AI回答区域
        response_group = QGroupBox("AI助手回答")
        response_layout = QVBoxLayout(response_group)

        self.ai_response = QTextEdit()
        self.ai_response.setPlaceholderText("AI助手将在这里回答您的问题...")
        response_layout.addWidget(self.ai_response)

        layout.addWidget(response_group)

        # 用户指令区域
        input_group = QGroupBox("您的指令")
        input_layout = QVBoxLayout(input_group)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("请输入您的问题或指令...")
        self.user_input.returnPressed.connect(self._send_to_ai)
        input_layout.addWidget(self.user_input)

        send_btn = QPushButton("发送")
        send_btn.clicked.connect(self._send_to_ai)
        input_layout.addWidget(send_btn)

        layout.addWidget(input_group)

        return widget

    def _create_backtest_panel(self) -> QWidget:
        """创建回测面板.

        Returns:
            QWidget: 回测面板组件
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # 回测配置
        config_group = QGroupBox("回测配置")
        config_layout = QHBoxLayout(config_group)

        # 左侧配置
        left_form = QVBoxLayout()
        left_form.addWidget(QLabel("策略/指标:"))

        self.backtest_target_combo = QComboBox()
        self._load_strategy_list()
        left_form.addWidget(self.backtest_target_combo)

        left_form.addWidget(QLabel("展示模板:"))
        self.renderer_type_combo = QComboBox()
        self.renderer_type_combo.addItems(
            ["默认展示", "CTA策略", "算法交易", "期权策略", "组合策略", "价差交易", "脚本交易"]
        )
        left_form.addWidget(self.renderer_type_combo)

        config_layout.addLayout(left_form)

        # 右侧配置
        right_form = QVBoxLayout()
        right_form.addWidget(QLabel("开始日期:"))

        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        right_form.addWidget(self.start_date_input)

        right_form.addWidget(QLabel("结束日期:"))
        self.end_date_input = QLineEdit()
        self.end_date_input.setPlaceholderText("YYYY-MM-DD")
        right_form.addWidget(self.end_date_input)

        config_layout.addLayout(right_form)

        layout.addWidget(config_group)

        # 回测控制
        control_layout = QHBoxLayout()

        self.run_backtest_btn = QPushButton("▶️ 运行回测")
        self.run_backtest_btn.clicked.connect(self._run_backtest)
        control_layout.addWidget(self.run_backtest_btn)

        self.stop_backtest_btn = QPushButton("⏹️ 停止回测")
        self.stop_backtest_btn.clicked.connect(self._stop_backtest)
        self.stop_backtest_btn.setEnabled(False)
        control_layout.addWidget(self.stop_backtest_btn)

        control_layout.addStretch()

        layout.addLayout(control_layout)

        # 回测进度
        progress_group = QGroupBox("回测进度")
        progress_layout = QVBoxLayout(progress_group)

        self.backtest_progress = QProgressBar()
        progress_layout.addWidget(self.backtest_progress)

        self.backtest_status_label = QLabel("准备就绪")
        progress_layout.addWidget(self.backtest_status_label)

        layout.addWidget(progress_group)

        # 回测结果
        results_group = QGroupBox("回测结果")
        results_layout = QVBoxLayout(results_group)

        self.backtest_results = QTextEdit()
        self.backtest_results.setPlaceholderText("回测结果将显示在这里...")
        results_layout.addWidget(self.backtest_results)

        layout.addWidget(results_group)

        return panel

    # ==================== 事件处理 ====================

    def connect_signals(self):
        """连接信号槽."""
        try:
            # 文件管理器信号
            if self.file_explorer:
                self.file_explorer.file_double_clicked.connect(self._on_file_double_clicked)
                self.logger.info("文件管理器信号已连接")

            # 编辑器标签信号
            if self.editor_tabs:
                self.editor_tabs.file_saved.connect(self._on_file_saved)
                self.logger.info("编辑器标签信号已连接")
        except Exception as e:
            self.logger.error("连接信号失败: %s", e, exc_info=True)

    def _on_file_double_clicked(self, file_path: str):
        """文件双击事件 - 根据当前标签页执行不同操作.

        Args:
            file_path: 文件路径
        """
        try:
            self.logger.info("🔍 [DEBUG] 双击事件触发，接收到文件路径: %s", file_path)
            self.logger.info(
                "🔍 [DEBUG] 路径类型: %s, 长度: %s",
                type(file_path),
                len(file_path) if file_path else 0,
            )

            if not file_path:
                self.logger.warning("文件路径为空，无法处理")
                return

            # 检查当前在哪个标签页
            if not hasattr(self, "content_tab") or not self.content_tab:
                self.logger.error("内容标签页组件未初始化")
                return

            current_tab_index = self.content_tab.currentIndex()
            self.logger.info(
                "🔍 [DEBUG] 当前标签页索引: %s, 文件: %s", current_tab_index, file_path
            )

            # 0 = 策略编写标签页：打开文件到编辑器
            if current_tab_index == 0:
                self._handle_file_open_for_editing(file_path)

            # 1 = 策略回测标签页：选中该策略作为回测目标
            elif current_tab_index == 1:
                self._handle_file_select_for_backtest(file_path)

            else:
                self.logger.warning("未知的标签页索引: %s", current_tab_index)

        except Exception as e:
            self.logger.error("双击文件处理失败: %s, 错误: %s", file_path, e, exc_info=True)
            self.show_error(f"处理文件时发生错误:\n{str(e)}")

    def _handle_file_open_for_editing(self, file_path: str):
        """在策略编写标签页中打开文件.

        Args:
            file_path: 文件路径
        """
        if not self.editor_tabs:
            self.logger.error("编辑器标签组件未初始化")
            self.show_error("编辑器组件未准备好，请稍后再试")
            return

        self.logger.info("在编辑器中打开文件: %s", file_path)
        success = self.editor_tabs.open_file(file_path)

        if success:
            self.logger.info("文件在编辑器中打开成功: %s", file_path)
        else:
            self.logger.warning("文件打开失败: %s", file_path)

    def _handle_file_select_for_backtest(self, file_path: str):
        """在策略回测标签页中选中文件作为回测目标.

        Args:
            file_path: 文件路径
        """
        self.logger.info("🔍 [DEBUG] _handle_file_select_for_backtest 被调用")
        self.logger.info("🔍 [DEBUG] 完整文件路径: %s", file_path)

        # 获取文件名（不含路径）
        file_name = Path(file_path).name
        self.logger.info("🔍 [DEBUG] 提取的文件名: %s", file_name)

        # 检查是否是Python文件
        if not file_name.endswith(".py"):
            self.logger.warning("文件不是Python文件: %s", file_name)
            self.show_warning(f"只能选择Python策略文件进行回测\n选中的文件: {file_name}")
            return

        # 在回测目标下拉框中选择该策略
        if not self.backtest_target_combo:
            self.logger.error("回测目标下拉框未初始化")
            return

        # 🔧 修复：每次选择时都刷新策略列表，确保列表最新
        self.logger.info("🔍 [DEBUG] 开始刷新策略列表")
        self._load_strategy_list()

        # 打印当前下拉框中的所有项
        self.logger.info("🔍 [DEBUG] 下拉框中的项数: %s", self.backtest_target_combo.count())
        for i in range(self.backtest_target_combo.count()):
            item_text = self.backtest_target_combo.itemText(i)
            self.logger.info(
                "🔍 [DEBUG] 下拉框项 [%s]: '%s' (长度: %s)", i, item_text, len(item_text)
            )

        # 查找并选中该策略
        self.logger.info("🔍 [DEBUG] 尝试查找文件名: '%s' (长度: %s)", file_name, len(file_name))
        index = self.backtest_target_combo.findText(file_name)
        self.logger.info("🔍 [DEBUG] findText 返回索引: %s", index)

        if index >= 0:
            self.backtest_target_combo.setCurrentIndex(index)
            self.logger.info("✓ 已选中回测策略: %s", file_name)
            self.show_info(f"✓ 已选中回测策略: {file_name}")
        else:
            self.logger.error("✗ 回测列表中未找到策略: %s", file_name)
            self.logger.error(
                "🔍 [DEBUG] 匹配失败详情 - 查找: '%s', 列表: %s",
                file_name,
                [
                    self.backtest_target_combo.itemText(i)
                    for i in range(self.backtest_target_combo.count())
                ],
            )
            self.show_warning(
                f"✗ 无法在回测列表中找到策略: {file_name}\n\n可能原因：\n1. 文件不在 strategies/user_strategies 目录\n2. 文件名不符合Python文件命名规范"
            )

    def _on_file_saved(self, file_path: str):
        """文件保存事件.

        Args:
            file_path: 文件路径
        """
        self.logger.info("文件已保存: %s", file_path)
        self.show_info(f"文件已保存: {Path(file_path).name}")

    def _create_new_strategy(self):
        """新建策略."""
        if not self.strategy_service:
            self.show_error("策略中心服务不可用")
            return

        from PySide6.QtWidgets import QInputDialog

        # 弹出对话框让用户输入策略名称
        strategy_name, ok = QInputDialog.getText(
            self, "新建策略", "请输入策略名称:", text="my_strategy"
        )

        if ok and strategy_name:
            # 确保文件名有.py后缀
            if not strategy_name.endswith(".py"):
                strategy_name = f"{strategy_name}.py"

            # 创建策略文件
            result = self.strategy_service.create_strategy_file(
                file_path=strategy_name, template_type="cta"
            )

            if result.get("success"):
                self.show_info(f"策略 '{strategy_name}' 创建成功")

                # 刷新文件树
                if self.file_explorer:
                    self.file_explorer.refresh()

                # 🔧 修复：刷新回测策略列表
                self._load_strategy_list()
                self.logger.info("已刷新回测策略列表")

                # 打开新创建的文件
                file_path = f"strategies/user_strategies/{strategy_name}"
                if self.editor_tabs:
                    self.editor_tabs.open_file(file_path)
            else:
                self.show_error(f"创建策略失败: {result.get('message', '未知错误')}")

    def _save_current_file(self):
        """保存当前文件."""
        if self.editor_tabs:
            if self.editor_tabs.save_file():
                self.show_info("文件已保存")
            else:
                self.show_warning("没有打开的文件")

    def _save_all_files(self):
        """保存所有文件."""
        if self.editor_tabs:
            count = self.editor_tabs.save_all_files()
            if count > 0:
                self.show_info(f"已保存 {count} 个文件")
            else:
                self.show_info("没有需要保存的文件")

    def _format_code(self):
        """格式化代码."""
        current_editor = self.editor_tabs.get_current_editor() if self.editor_tabs else None

        if not current_editor:
            self.show_warning("没有打开的文件")
            return

        code = current_editor.toPlainText()
        if not code.strip():
            self.show_warning("代码为空")
            return

        try:
            import autopep8  # type: ignore[import-untyped]

            formatted_code = autopep8.fix_code(code)
            current_editor.setPlainText(formatted_code)
            self.show_info("代码格式化完成")
        except ImportError:
            self.show_warning("需要安装autopep8: pip install autopep8")

    def _toggle_ai_assistant(self, checked: bool):
        """切换AI助手显示.

        Args:
            checked: 是否显示
        """
        if self.ai_assistant_widget:
            self.ai_assistant_widget.setVisible(checked)

        if self.ai_assistant_btn:
            # 按钮文本保持简洁，通过按钮选中状态显示是否激活
            text = "🤖 AI助手 ✓" if checked else "🤖 AI助手"
            self.ai_assistant_btn.setText(text)

    def _send_to_ai(self):
        """发送消息给AI助手."""
        if not self.user_input or not self.ai_response:
            return

        message = self.user_input.text().strip()
        if not message:
            return

        # 显示用户消息
        self.ai_response.append(f"\n>>> 用户: {message}\n")
        self.user_input.clear()

        # 获取AI助手服务
        try:
            ai_service = self.service_manager.get_service("ai_assistant_service")
            if not ai_service:
                self.ai_response.append("❌ AI助手服务不可用\n")
                return

            # 获取当前编辑器中的代码作为上下文
            context = {}
            current_editor = self.editor_tabs.get_current_editor() if self.editor_tabs else None
            if current_editor:
                current_code = current_editor.toPlainText()
                if current_code.strip():
                    context["strategy_code"] = current_code

            # 调用AI服务
            response = ai_service.chat(message, context=context)

            if not response.get("success"):
                error_msg = response.get("message", "未知错误")
                self.ai_response.append(f"❌ AI调用失败: {error_msg}\n")
                return

            # 处理AI回复
            message_type = response.get("message_type", "text")

            if message_type == "code":
                # 纯代码 - 插入到编辑器
                code = response.get("code", "")
                if code and current_editor:
                    current_editor.insertPlainText(f"\n{code}\n")
                    self.ai_response.append("✅ 代码已插入到编辑器\n")

            elif message_type == "text":
                # 纯文本 - 显示在AI反馈区
                text = response.get("text", response.get("message", ""))
                self.ai_response.append(f"🤖 AI助手:\n{text}\n")

            elif message_type == "mixed":
                # 混合内容
                code = response.get("code", "")
                text = response.get("text", "")

                if text:
                    self.ai_response.append(f"🤖 AI助手:\n{text}\n")

                if code and current_editor:
                    current_editor.insertPlainText(f"\n{code}\n")
                    self.ai_response.append("\n✅ 代码部分已插入到编辑器\n")

            # 如果AI修改了文件，刷新文件树
            files_modified = response.get("files_modified", [])
            if files_modified:
                self.ai_response.append(f"\n📁 AI助手已保存文件: {', '.join(files_modified)}\n")

                # 刷新文件树
                if self.file_explorer:
                    self.file_explorer.refresh()

                # 如果只修改了一个文件，自动打开
                if len(files_modified) == 1 and self.editor_tabs:
                    file_path = files_modified[0]
                    self.editor_tabs.open_file(file_path)
                    self.ai_response.append(f"✅ 文件已打开: {file_path}\n")

        except Exception as e:
            self.logger.error("AI助手调用失败: %s", e)
            self.ai_response.append(f"❌ 错误: {str(e)}\n")

    def _load_strategy_list(self):
        """加载策略列表到下拉框."""
        if not self.backtest_target_combo:
            self.logger.error("🔍 [DEBUG] backtest_target_combo 未初始化")
            return

        try:
            self.logger.info("🔍 [DEBUG] ===== 开始加载策略列表 =====")

            # 先清空下拉框，避免重复添加
            self.backtest_target_combo.clear()
            self.logger.info("🔍 [DEBUG] 已清空下拉框")

            # 🔧 关键修复：使用绝对路径确保正确找到目录
            strategy_dir = (
                Path(__file__).parent.parent.parent.parent / "strategies" / "user_strategies"
            )
            abs_strategy_dir = str(strategy_dir.resolve())
            self.logger.info("🔍 [DEBUG] 策略目录（绝对）: %s", abs_strategy_dir)
            self.logger.info("🔍 [DEBUG] 当前工作目录: %s", os.getcwd())
            self.logger.info("🔍 [DEBUG] 目录是否存在: %s", strategy_dir.exists())

            if strategy_dir.exists():
                all_files = list(strategy_dir.iterdir())
                self.logger.info("🔍 [DEBUG] 目录中所有文件: %s", [f.name for f in all_files])

                strategy_files = [
                    f.name
                    for f in all_files
                    if f.is_file() and f.name.endswith(".py") and not f.name.startswith("__")
                ]
                self.logger.info("🔍 [DEBUG] 过滤后的策略文件: %s", strategy_files)

                if strategy_files:
                    self.backtest_target_combo.addItems(strategy_files)
                    self.logger.info("✓ 已加载 %s 个策略文件", len(strategy_files))

                    # 打印每个添加的文件的详细信息
                    for f in strategy_files:
                        self.logger.info(
                            "🔍 [DEBUG] 添加文件: '%s' (长度: %s, repr: %s)", f, len(f), repr(f)
                        )
                else:
                    self.backtest_target_combo.addItem("(无可用策略)")
                    self.logger.warning("🔍 [DEBUG] 未找到符合条件的策略文件")
            else:
                self.backtest_target_combo.addItem("(策略目录不存在)")
                self.logger.error("策略目录不存在: %s", strategy_dir)

            self.logger.info("🔍 [DEBUG] ===== 策略列表加载完成 =====")

        except Exception as e:
            self.logger.error("加载策略列表失败: %s", e, exc_info=True)

    def _run_backtest(self):
        """运行回测."""
        if not self.strategy_service:
            self.show_error("策略中心服务不可用")
            return

        strategy_name = (
            self.backtest_target_combo.currentText() if self.backtest_target_combo else ""
        )
        start_date = self.start_date_input.text() if self.start_date_input else ""
        end_date = self.end_date_input.text() if self.end_date_input else ""

        if not strategy_name or not start_date or not end_date:
            self.show_warning("请填写完整的回测参数")
            return

        self.show_info(f"开始运行回测: {strategy_name}")

        if self.run_backtest_btn:
            self.run_backtest_btn.setEnabled(False)
        if self.stop_backtest_btn:
            self.stop_backtest_btn.setEnabled(True)
        if self.backtest_progress:
            self.backtest_progress.setValue(0)
        if self.backtest_status_label:
            self.backtest_status_label.setText("回测运行中...")

        # 获取展示模板类型
        renderer_type_text = (
            self.renderer_type_combo.currentText() if self.renderer_type_combo else "默认展示"
        )
        renderer_type_map = {
            "默认展示": "default",
            "CTA策略": "cta",
            "算法交易": "algo",
            "期权策略": "option",
            "组合策略": "portfolio",
            "价差交易": "spread",
            "脚本交易": "script",
        }
        renderer_type = renderer_type_map.get(renderer_type_text, "default")

        # 通过strategy_service运行回测
        backtest_config = {
            "start_date": start_date,
            "end_date": end_date,
            "capital": 1000000,
            "symbol": "000001",
            "exchange": "SZSE",
            "interval": "1d",
            "renderer_type": renderer_type,
        }

        result = self.strategy_service.start_backtest(
            strategy_file=strategy_name, config=backtest_config
        )

        if result.get("success"):
            self.current_backtest_task_id = result.get("task_id")
            self.show_info("回测已启动，正在后台运行...")

            # 启动进度监控定时器
            self.backtest_timer = QTimer()
            self.backtest_timer.timeout.connect(self._check_backtest_progress)
            self.backtest_timer.start(1000)  # 每秒检查一次
        else:
            self.show_error(f"启动回测失败: {result.get('message', '未知错误')}")
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

    def _check_backtest_progress(self):
        """检查回测进度."""
        if not self.strategy_service or not hasattr(self, "current_backtest_task_id"):
            return

        status = self.strategy_service.get_backtest_status(self.current_backtest_task_id)

        if not status:
            return

        progress = status.get("progress", 0)
        task_status = status.get("status", "unknown")

        # 更新进度条
        if self.backtest_progress:
            self.backtest_progress.setValue(progress)

        # 更新状态
        if self.backtest_status_label:
            self.backtest_status_label.setText(f"回测进度: {progress}%")

        # 检查是否完成
        if task_status == "completed":
            result = status.get("result", {})

            # 显示结果
            result_text = "=== 回测结果 ===\n"
            result_text += f"总收益率: {result.get('total_return', 0)*100:.2f}%\n"
            result_text += f"夏普比率: {result.get('sharpe_ratio', 0):.2f}\n"
            result_text += f"最大回撤: {result.get('max_drawdown', 0)*100:.2f}%\n"
            result_text += f"交易次数: {result.get('total_trades', 0)}\n"
            result_text += f"胜率: {result.get('winning_rate', 0)*100:.2f}%\n"
            result_text += f"\n{result.get('message', '')}"

            if self.backtest_results:
                self.backtest_results.setText(result_text)

            self.show_info("回测已完成")

            # 停止定时器
            if self.backtest_timer is not None:
                self.backtest_timer.stop()

            # 恢复按钮状态
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

        elif task_status == "failed":
            error = status.get("result", {}).get("error", "未知错误")
            self.show_error(f"回测失败: {error}")

            if self.backtest_results:
                self.backtest_results.setText(f"回测失败:\n{error}")

            # 停止定时器
            if self.backtest_timer is not None:
                self.backtest_timer.stop()

            # 恢复按钮状态
            if self.run_backtest_btn:
                self.run_backtest_btn.setEnabled(True)
            if self.stop_backtest_btn:
                self.stop_backtest_btn.setEnabled(False)

    def _stop_backtest(self):
        """停止回测."""
        self.show_info("停止回测")
        if self.run_backtest_btn:
            self.run_backtest_btn.setEnabled(True)
        if self.stop_backtest_btn:
            self.stop_backtest_btn.setEnabled(False)

    def refresh_data(self):
        """刷新数据."""
        # 刷新文件树
        if self.file_explorer:
            self.file_explorer.refresh()

        self.logger.info("策略中心数据已手动刷新")

    def on_close(self):
        """关闭处理."""
        # 提示保存未保存的文件
        if self.editor_tabs:
            if self.editor_tabs.unsaved_files:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self,
                    "保存文件",
                    f"有 {len(self.editor_tabs.unsaved_files)} 个文件未保存。是否保存？",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Save,
                )

                if reply == QMessageBox.StandardButton.Save:
                    self.editor_tabs.save_all_files()
                elif reply == QMessageBox.StandardButton.Cancel:
                    return False

        self.logger.info("策略中心界面已关闭")
        return True

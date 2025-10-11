# -*- coding: utf-8 -*-
"""多标签编辑器组件.

提供类似VSCode的多标签编辑体验：
- 多个文件同时打开
- 标签可关闭、拖拽排序
- 未保存状态提示
- 快捷键切换标签
"""

from pathlib import Path
from typing import Dict, Optional, Set, Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QTabWidget,
    QMenu,
    QMessageBox,
    QWidget,
)

from backend.core.utils import LoggerMixin

# 导入Monaco Editor（异步加载版）
_editor_widget_available = False
_editor_widget_class = None
_editor_widget_name = None

try:
    from ui.widgets.monaco_editor_widget import MonacoEditorWidget, HAS_WEBENGINE

    if HAS_WEBENGINE:
        _editor_widget_class = MonacoEditorWidget
        _editor_widget_available = True
        _editor_widget_name = "Monaco Editor"
        print("✓ Monaco Editor 可用（异步加载版）")
    else:
        print("✗ Monaco Editor 不可用 (缺少 PySide6-WebEngine)")
except ImportError as e:
    print(f"✗ Monaco Editor 导入失败: {e}")


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
            self.logger.info(f"🔍 [DEBUG] ===== editor_tabs.open_file 被调用 =====")
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
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, "文件不存在", f"无法打开文件，文件不存在:\n{file_path}")
                return False

            # 读取文件内容
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.logger.info(f"成功读取文件内容，长度: {len(content)}")
            except Exception as read_error:
                self.logger.error(f"读取文件失败: {read_error}", exc_info=True)
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self, "读取失败", f"无法读取文件:\n{str(read_error)}")
                return False

            # 🔧 创建Monaco Editor（异步加载版）
            try:
                self.logger.info(f"🔍 [DEBUG] 开始创建Monaco编辑器")

                if not _editor_widget_available or _editor_widget_class is None:
                    self.logger.error("Monaco Editor不可用")
                    from PySide6.QtWidgets import QMessageBox

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
                from PySide6.QtWidgets import QMessageBox

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
                from PySide6.QtWidgets import QMessageBox

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
                self.logger.info(f"🔍 [DEBUG] 已切换到新标签")

                # 发送信号
                self.file_opened.emit(file_path)

                self.logger.info(f"✓ 成功打开文件: {file_path}")
                return True
            except Exception as tab_error:
                self.logger.error(f"🔴 添加标签失败: {tab_error}", exc_info=True)
                # 清理已创建的编辑器
                if file_path in self.editors:
                    del self.editors[file_path]
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.critical(self, "标签错误", f"无法添加标签:\n{str(tab_error)}")
                return False

        except Exception as e:
            self.logger.error(f"打开文件失败: {file_path}, 错误: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

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

            # 如果未保存，添加圆点标记
            if file_path in self.unsaved_files:
                title = f"● {file_name}"
            else:
                title = file_name

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

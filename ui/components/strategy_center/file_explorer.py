# -*- coding: utf-8 -*-
"""增强文件管理器组件.

提供类似VSCode的文件管理体验：
- 右键菜单（新建、重命名、删除、复制、粘贴）
- 拖拽支持
- 多选支持
- 搜索过滤
- 文件图标
"""

import shutil
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QHBoxLayout,
    QPushButton,
)

from backend.core.utils import LoggerMixin


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

            # 添加根节点
            root_item = QTreeWidgetItem()
            root_item.setText(0, self.root_dir.name)
            root_item.setData(
                0, Qt.ItemDataRole.UserRole, {"type": "directory", "path": str(self.root_dir)}
            )
            root_item.setExpanded(True)
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

            for item_path in items:
                # 跳过隐藏文件和__pycache__
                if item_path.name.startswith(".") or item_path.name == "__pycache__":
                    continue

                # 创建树节点
                item = QTreeWidgetItem()

                if item_path.is_dir():
                    # 文件夹
                    item.setText(0, f"📁 {item_path.name}")
                    item.setData(
                        0, Qt.ItemDataRole.UserRole, {"type": "directory", "path": str(item_path)}
                    )
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
            file_path = data["path"]
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
        if item:
            rename_action = menu.addAction("✏️ 重命名")
            delete_action = menu.addAction("🗑️ 删除")
            menu.addSeparator()
            copy_action = menu.addAction("📋 复制")
            cut_action = menu.addAction("✂️ 剪切")

        # 粘贴菜单（需要剪贴板有内容）
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
        new_name, ok = QInputDialog.getText(self, "重命名", f"请输入新名称:", text=old_name)

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
        refresh_btn.setMaximumWidth(30)
        refresh_btn.setToolTip("刷新")
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

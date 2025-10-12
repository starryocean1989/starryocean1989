# -*- coding: utf-8 -*-
"""品种搜索组件 - 支持实时联想和拼音搜索.

提供智能搜索功能：
- 实时下拉匹配
- 品种代码匹配
- 品种名称匹配
- 拼音首字母匹配
"""

import logging
from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QCompleter
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

# 尝试导入pypinyin，如果不可用则使用降级方案
try:
    from pypinyin import lazy_pinyin, Style

    HAS_PINYIN = True
    logger.info("✅ pypinyin可用，启用拼音搜索")
except ImportError:
    HAS_PINYIN = False
    logger.warning("⚠️ pypinyin不可用，拼音搜索功能已禁用")


class SymbolSearchWidget(QComboBox):
    """品种搜索组件.

    支持实时联想和拼音搜索的品种选择器。
    """

    # 信号：品种选择改变
    symbol_selected = Signal(str)

    def __init__(self, parent=None):
        """初始化品种搜索组件.

        Args:
            parent: 父组件
        """
        super().__init__(parent)

        # 所有品种列表（完整数据）
        self._all_symbols: List[dict] = []
        
        # 防止递归标志
        self._updating = False

        # 设置为可编辑
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        # 设置补全器
        self.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        # 连接信号
        self.lineEdit().textChanged.connect(self._on_text_changed)
        self.currentTextChanged.connect(self._on_selection_changed)

        # 设置占位文本
        self.lineEdit().setPlaceholderText("搜索品种（支持代码/名称/拼音）...")

        logger.info("品种搜索组件初始化完成")

    def set_symbols(self, symbols: List):
        """设置品种列表.

        Args:
            symbols: 品种列表，可以是字符串列表或字典列表
        """
        try:
            self._all_symbols = []

            for symbol in symbols:
                if isinstance(symbol, dict):
                    # 字典格式：{code: "000001", name: "平安银行"}
                    code = symbol.get("code", "")
                    name = symbol.get("name", "")
                    if code and name:
                        self._all_symbols.append(
                            {
                                "code": code,
                                "name": name,
                                "display": f"{code} - {name}",
                                "pinyin": self._get_pinyin_initials(name) if HAS_PINYIN else "",
                            }
                        )
                elif isinstance(symbol, str):
                    # 字符串格式："000001 - 平安银行"
                    if " - " in symbol:
                        parts = symbol.split(" - ", 1)
                        code = parts[0].strip()
                        name = parts[1].strip()
                        self._all_symbols.append(
                            {
                                "code": code,
                                "name": name,
                                "display": symbol,
                                "pinyin": self._get_pinyin_initials(name) if HAS_PINYIN else "",
                            }
                        )
                    else:
                        # 只有代码
                        self._all_symbols.append(
                            {
                                "code": symbol,
                                "name": "",
                                "display": symbol,
                                "pinyin": "",
                            }
                        )

            # 初始显示所有品种
            self._update_display_list(self._all_symbols)

            logger.info(f"✅ 已加载 {len(self._all_symbols)} 个品种")

        except Exception as e:
            logger.error(f"设置品种列表失败: {e}", exc_info=True)

    def _get_pinyin_initials(self, text: str) -> str:
        """获取文本的拼音首字母.

        Args:
            text: 中文文本

        Returns:
            拼音首字母字符串（小写）
        """
        if not HAS_PINYIN or not text:
            return ""

        try:
            # 获取拼音首字母
            initials = lazy_pinyin(text, style=Style.FIRST_LETTER)
            return "".join(initials).lower()
        except Exception as e:
            logger.warning(f"获取拼音首字母失败: {e}")
            return ""

    def _on_text_changed(self, text: str):
        """文本变化处理.

        Args:
            text: 当前文本
        """
        # 防止递归调用
        if self._updating:
            return
            
        try:
            self._updating = True
            
            if not text:
                # 空文本，显示所有品种
                self._update_display_list(self._all_symbols)
                return

            # 过滤匹配的品种
            matched = self._filter_symbols(text)
            self._update_display_list(matched)

            # 如果有匹配项，自动展开下拉列表（但只在用户输入时）
            if matched and len(text.strip()) > 0 and self.lineEdit().hasFocus():
                self.showPopup()
                
        finally:
            self._updating = False

    def _filter_symbols(self, search_text: str) -> List[dict]:
        """过滤匹配的品种.

        Args:
            search_text: 搜索文本

        Returns:
            匹配的品种列表
        """
        if not search_text:
            return self._all_symbols

        search_text_lower = search_text.lower().strip()
        matched = []

        for symbol in self._all_symbols:
            code = symbol["code"].lower()
            name = symbol["name"].lower()
            pinyin = symbol.get("pinyin", "")

            # 匹配条件：代码包含、名称包含、拼音首字母匹配
            if (
                search_text_lower in code
                or search_text_lower in name
                or (pinyin and search_text_lower in pinyin)
            ):
                matched.append(symbol)

        logger.debug(f"搜索 '{search_text}' 找到 {len(matched)} 个匹配品种")
        return matched

    def _update_display_list(self, symbols: List[dict]):
        """更新下拉列表显示.

        Args:
            symbols: 要显示的品种列表
        """
        # 防止递归调用
        if self._updating:
            return
            
        try:
            # 保存当前文本
            current_text = self.lineEdit().text()

            # 阻止信号，避免触发不必要的事件
            self.blockSignals(True)

            # 清空并重新添加
            self.clear()
            for symbol in symbols:
                self.addItem(symbol["display"])

            # 恢复文本
            self.setEditText(current_text)

            # 恢复信号
            self.blockSignals(False)
            
        except Exception as e:
            logger.error(f"更新显示列表失败: {e}", exc_info=True)

    def _on_selection_changed(self, text: str):
        """选择改变处理.

        Args:
            text: 选择的文本
        """
        if text and " - " in text:
            # 提取品种代码
            code = text.split(" - ")[0].strip()
            self.symbol_selected.emit(code)
            logger.debug(f"选择品种: {text}")

    def get_selected_code(self) -> Optional[str]:
        """获取当前选择的品种代码.

        Returns:
            品种代码，如果未选择则返回None
        """
        current_text = self.currentText()
        if current_text and " - " in current_text:
            return current_text.split(" - ")[0].strip()
        return None

    def set_selected_code(self, code: str):
        """设置选择的品种代码.

        Args:
            code: 品种代码
        """
        for i in range(self.count()):
            item_text = self.itemText(i)
            if item_text.startswith(f"{code} - "):
                self.setCurrentIndex(i)
                logger.debug(f"设置选择品种: {item_text}")
                break

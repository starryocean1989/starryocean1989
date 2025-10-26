# -*- coding: utf-8 -*-
"""
测试服务器刷新按钮是否能正确恢复（使用QThread+Signal机制）。

验证目标：
1. 按钮点击后禁用
2. 后台测速完成后按钮恢复
3. 可以重复点击

运行方式：
    python ui/tests/test_server_retest_button.py
"""

import sys
import os
from PySide6.QtWidgets import QApplication, QPushButton, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import QThread, Signal, Qt
import time

# 确保可以导入顶层包
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class MockService:
    """模拟数据中心服务。"""

    def retest_server_pool(self):
        """模拟测速（耗时3秒）。"""
        print("后台测速开始...")
        time.sleep(3)
        print("后台测速完成")
        return {"success": True, "stats": {"available": 148, "total": 700}}


class ServerRetestThread(QThread):
    """服务器重新测速工作线程（Qt原生）。"""

    finished_signal = Signal(dict)  # 完成信号，传递结果

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service

    def run(self):
        """后台执行测速。"""
        result = None
        try:
            if self.service and hasattr(self.service, "retest_server_pool"):
                result = self.service.retest_server_pool()
            else:
                result = {"success": False, "message": "后端未实现刷新API"}
        except Exception as e:  # pylint: disable=broad-except
            result = {"success": False, "message": str(e)}

        # 发射信号（线程安全，Qt会自动调度到主线程）
        self.finished_signal.emit(result)


class TestWindow(QWidget):
    """测试窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("测试服务器刷新按钮")
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("可用服务器: 未测试")
        self.status_label.setStyleSheet(
            "color: #0066cc; font-weight: bold; padding: 8px; "
            "background-color: #f0f8ff; border-radius: 4px;"
        )
        layout.addWidget(self.status_label)

        self.refresh_btn = QPushButton("🔄 刷新（测速3秒）")
        self.refresh_btn.clicked.connect(self._retest_servers)
        layout.addWidget(self.refresh_btn)

        self.info_label = QLabel("点击刷新按钮，观察按钮是否在3秒后恢复")
        layout.addWidget(self.info_label)

        self.service = MockService()
        self._retest_thread = None
        self._click_count = 0

    def _retest_servers(self):
        """手动触发服务器池重新测速并刷新状态（使用QThread+Signal）。"""
        try:
            self._click_count += 1
            print(f"\n=== 第 {self._click_count} 次点击 ===")

            # UI 禁用，提示中
            self.refresh_btn.setEnabled(False)
            self.status_label.setText("⏳ 正在重新测速...")
            self.status_label.setStyleSheet(
                "color: #0066cc; font-weight: bold; padding: 8px; "
                "background-color: #f0f8ff; border-radius: 4px;"
            )
            print("✓ 按钮已禁用")

            # 创建并启动线程
            self._retest_thread = ServerRetestThread(self.service, self)

            # 连接信号（QueuedConnection确保在主线程执行）
            self._retest_thread.finished_signal.connect(
                self._on_retest_finished, Qt.ConnectionType.QueuedConnection
            )

            # 启动线程
            self._retest_thread.start()
            print("✓ 后台测速线程已启动（QThread）")

        except Exception as e:  # pylint: disable=broad-except
            print(f"✗ 刷新服务器池失败: {e}")
            # 恢复按钮状态
            if self.refresh_btn:
                self.refresh_btn.setEnabled(True)

    def _on_retest_finished(self, result: dict):
        """测速完成回调（在主线程中执行，线程安全）。"""
        try:
            print("✓ 回调函数被调用（主线程）")
            success = bool(result.get("success"))
            if success:
                stats = result.get("stats", {})
                available = stats.get("available", 0)
                total = stats.get("total", 0)
                self.status_label.setText(f"✅ 可用服务器: {available}/{total}")
                self.status_label.setStyleSheet(
                    "color: #00aa00; font-weight: bold; padding: 8px; "
                    "background-color: #f0fff0; border-radius: 4px;"
                )
                print(f"✓ UI更新成功：{available}/{total} 可用")
            else:
                msg = result.get("message", "刷新失败")
                self.status_label.setText(f"⚠️ 刷新失败: {msg}")
                self.status_label.setStyleSheet(
                    "color: #ff6600; font-weight: bold; padding: 8px; "
                    "background-color: #fff8f0; border-radius: 4px;"
                )
                print(f"✗ UI更新失败：{msg}")
        except Exception as e:  # pylint: disable=broad-except
            print(f"✗ UI更新异常: {e}")
        finally:
            # 确保按钮始终恢复（在主线程，线程安全）
            if self.refresh_btn:
                self.refresh_btn.setEnabled(True)
                print("✓ 刷新按钮已恢复启用\n")


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    window = TestWindow()
    window.show()

    print("=" * 60)
    print("测试说明：")
    print("1. 点击【刷新】按钮，观察按钮变灰（禁用）")
    print("2. 等待3秒后，观察按钮是否恢复蓝色（启用）")
    print("3. 再次点击按钮，验证是否可以重复操作")
    print("=" * 60)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

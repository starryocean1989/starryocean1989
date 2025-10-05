# -*- coding: utf-8 -*-
"""运维与诊断中心 - 进程与热更新控制 + 依赖与环境自检."""

import os
from contextlib import suppress
from pathlib import Path
from typing import Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
)
from PySide6.QtCore import QTimer

try:
    import psutil  # 用于读取进程与系统信息
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

CMD_FILE = Path("logs/launcher.cmd")
PIDS_FILE = Path("logs/launcher.pids")
LOG_FILES = [
    Path("logs/terminal_v0.50.log"),
    Path("logs/launcher.log"),
    Path("logs/hot_reload.log"),
]


class OpsCenter(QWidget):
    """运维与诊断中心."""

    def __init__(self, parent=None):
        """Initialize the OpsCenter widget."""
        super().__init__(parent)
        self.setObjectName("OpsCenter")
        self._setup_ui()
        self._connect_signals()
        self._refresh_all()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 进程与热更新控制
        process_group = QGroupBox("进程与热更新控制")
        process_layout = QVBoxLayout(process_group)

        status_layout = QHBoxLayout()
        self.backend_status = QLabel("后端: 未知")
        self.ui_status = QLabel("UI: 未知")
        self.watchdog_status = QLabel("守护: 未知")
        status_layout.addWidget(self.backend_status)
        status_layout.addWidget(self.ui_status)
        status_layout.addWidget(self.watchdog_status)
        status_layout.addStretch()
        process_layout.addLayout(status_layout)

        btn_layout = QHBoxLayout()
        self.restart_ui_btn = QPushButton("重启 UI")
        self.restart_backend_btn = QPushButton("重启 后端")
        self.restart_all_btn = QPushButton("重启 全部")
        self.toggle_hot_reload_btn = QPushButton("热更新: 发送测试指令")
        btn_layout.addWidget(self.restart_ui_btn)
        btn_layout.addWidget(self.restart_backend_btn)
        btn_layout.addWidget(self.restart_all_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.toggle_hot_reload_btn)
        process_layout.addLayout(btn_layout)

        layout.addWidget(process_group)

        # 依赖与环境自检
        diag_group = QGroupBox("依赖与环境自检")
        diag_layout = QVBoxLayout(diag_group)

        self.deps_table = QTableWidget(0, 2)
        self.deps_table.setHorizontalHeaderLabels(["依赖", "状态"])
        self.deps_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.deps_table.verticalHeader().setVisible(False)
        diag_layout.addWidget(self.deps_table)

        self.run_check_btn = QPushButton("重新检测")
        diag_layout.addWidget(self.run_check_btn)

        layout.addWidget(diag_group)

        # 日志查看
        log_group = QGroupBox("运行日志（最近）")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_group)

        layout.addStretch()

    def _connect_signals(self):
        self.restart_ui_btn.clicked.connect(
            lambda: self._write_cmd("restart_ui")
        )
        self.restart_backend_btn.clicked.connect(
            lambda: self._write_cmd("restart_backend")
        )
        self.restart_all_btn.clicked.connect(
            lambda: self._write_cmd("restart_all")
        )
        self.toggle_hot_reload_btn.clicked.connect(
            lambda: self._write_cmd("restart_all")
        )
        self.run_check_btn.clicked.connect(self._refresh_dependencies)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_all)
        self.refresh_timer.start(3000)

    def _refresh_all(self):
        self._refresh_status()
        self._refresh_dependencies()
        self._refresh_logs()

    def _write_cmd(self, cmd: str):
        with suppress(Exception):
            CMD_FILE.parent.mkdir(exist_ok=True)
            CMD_FILE.write_text(cmd, encoding="utf-8")

    def _read_pids(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"backend_pid": None, "ui_pid": None}
        if PIDS_FILE.exists():
            with suppress(Exception):
                for line in PIDS_FILE.read_text(encoding="utf-8").splitlines():
                    if line.startswith("backend_pid="):
                        val = line.split("=", 1)[1].strip()
                        result["backend_pid"] = (
                            int(val) if val.isdigit() else None
                        )
                    elif line.startswith("ui_pid="):
                        val = line.split("=", 1)[1].strip()
                        result["ui_pid"] = int(val) if val.isdigit() else None
        return result

    def _is_process_alive(self, pid: int) -> bool:
        if not pid:
            return False
        if not PSUTIL_AVAILABLE:
            # 无psutil时仅依据PID是否存在文件
            with suppress(Exception):
                os.kill(pid, 0)
                return True
            return False
        with suppress(Exception):
            p = psutil.Process(pid)
            return p.is_running()
        return False

    def _refresh_status(self):
        pids = self._read_pids()
        backend_alive = self._is_process_alive(pids.get("backend_pid"))
        ui_alive = self._is_process_alive(pids.get("ui_pid"))

        self.backend_status.setText(
            f"后端: {'运行中' if backend_alive else '未运行'} "
            f"({pids.get('backend_pid')})"
        )
        self.ui_status.setText(
            f"UI: {'运行中' if ui_alive else '未运行'} "
            f"({pids.get('ui_pid')})"
        )
        # 守护状态无法直接判断，这里根据PID文件存在性与刷新频率推测
        watchdog = "运行中" if PIDS_FILE.exists() else "未知"
        self.watchdog_status.setText(f"守护: {watchdog}")

    def _refresh_dependencies(self):
        deps = [
            ("PySide6", "PySide6"),
            ("pyqtgraph", "pyqtgraph"),
            ("talib", "talib"),
            ("psutil", "psutil"),
        ]
        self.deps_table.setRowCount(len(deps))
        for i, (name, module_name) in enumerate(deps):
            status = "❌ 缺失"
            with suppress(Exception):
                __import__(module_name)
                status = "✅ 可用"
            self.deps_table.setItem(i, 0, QTableWidgetItem(name))
            self.deps_table.setItem(i, 1, QTableWidgetItem(status))

    def _refresh_logs(self):
        lines: List[str] = []
        for lf in LOG_FILES:
            if lf.exists():
                with suppress(Exception):
                    content = lf.read_text(encoding="utf-8").splitlines()
                    tail = content[-50:] if len(content) > 50 else content
                    lines.append(f"== {lf.name} ==")
                    lines.extend(tail)
        self.log_view.setPlainText("\n".join(lines))


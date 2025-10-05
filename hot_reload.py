# -*- coding: utf-8 -*-
"""
热更新监控脚本
监控文件变化，自动重启相关服务
"""

import os
import sys
import time
import hashlib
import threading
import subprocess
from pathlib import Path
from typing import Dict, Set, Optional, Union
import logging


class HotReloadMonitor:
    """热更新监控器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.logger = self._setup_logging()

        # 文件监控配置
        self.watch_extensions = {'.py', '.json', '.yaml', '.yml'}
        self.watch_paths = [
            project_root / 'backend',
            project_root / 'ui',
            project_root / 'start_terminal.py'
        ]

        # 文件哈希缓存
        self.file_hashes: Dict[str, str] = {}
        self.ignored_files: Set[str] = set()
        self._last_changed_paths: Set[str] = set()

        # 重启配置
        self.restart_delay = 1.0
        self.restart_backoff = 2.0
        self.max_restart_attempts = 3

        # 状态管理
        self.monitoring = False
        self.restart_count = 0
        self.last_restart_time = 0
        self.monitor_thread: Optional[threading.Thread] = None

        # 忽略某些文件/目录
        self._init_ignore_patterns()

    def _setup_logging(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger("HotReload")
        logger.setLevel(logging.INFO)

        # 避免重复添加处理器
        if logger.handlers:
            return logger

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger

    def _init_ignore_patterns(self):
        """初始化忽略模式"""
        ignore_patterns = [
            '__pycache__',
            '.git',
            '.vscode',
            'node_modules',
            'logs',
            '*.pyc',
            '*.pyo',
            '.DS_Store',
            'Thumbs.db',
            '*.log',
            '*.tmp'
        ]

        for pattern in ignore_patterns:
            if pattern.startswith('*'):
                # 文件扩展名模式
                self.ignored_files.add(pattern[1:])  # 去掉*
            else:
                # 目录模式
                ignore_path = self.project_root / pattern
                if ignore_path.exists():
                    self._add_ignore_path(ignore_path)

    def _add_ignore_path(self, path: Path):
        """添加忽略路径"""
        if path.is_file():
            self.ignored_files.add(str(path.relative_to(self.project_root)))
        elif path.is_dir():
            for file_path in path.rglob('*'):
                if file_path.is_file():
                    self.ignored_files.add(str(file_path.relative_to(self.project_root)))

    def _should_ignore_file(self, file_path: str) -> bool:
        """检查是否应该忽略文件"""
        # 检查扩展名
        if any(file_path.endswith(ignored) for ignored in self.ignored_files if ignored.startswith('.')):
            return True

        # 检查路径模式
        if any(ignored in file_path for ignored in self.ignored_files if not ignored.startswith('.')):
            return True

        return False

    def _calculate_file_hash(self, file_path: Path) -> Optional[str]:
        """计算文件哈希"""
        try:
            if not file_path.exists() or not file_path.is_file():
                return None

            # 只监控指定扩展名的文件
            if file_path.suffix not in self.watch_extensions:
                return None

            # 忽略的文件
            relative_path = str(file_path.relative_to(self.project_root))
            if self._should_ignore_file(relative_path):
                return None

            # 计算哈希
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()

        except Exception as e:
            self.logger.debug(f"计算文件哈希失败 {file_path}: {e}")
            return None

    def _scan_all_files(self) -> Dict[str, str]:
        """扫描所有监控文件"""
        current_hashes = {}

        for watch_path in self.watch_paths:
            if not watch_path.exists():
                continue

            for file_path in watch_path.rglob('*'):
                if file_path.is_file():
                    file_hash = self._calculate_file_hash(file_path)
                    if file_hash:
                        relative_path = str(file_path.relative_to(self.project_root))
                        current_hashes[relative_path] = file_hash

        return current_hashes

    def start_monitoring(self):
        """启动监控"""
        if self.monitoring:
            return

        self.logger.info("启动热更新监控...")

        # 初始扫描
        self.file_hashes = self._scan_all_files()
        self.logger.info(f"初始扫描完成，监控 {len(self.file_hashes)} 个文件")

        # 启动监控线程
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.logger.info("✅ 热更新监控已启动")

    def stop_monitoring(self):
        """停止监控"""
        if not self.monitoring:
            return

        self.monitoring = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        self.logger.info("热更新监控已停止")

    def _monitor_loop(self):
        """监控循环"""
        consecutive_failures = 0

        while self.monitoring:
            try:
                # 扫描文件变化
                changes_detected = self._check_file_changes()

                if changes_detected:
                    self.logger.info("检测到文件变化，正在重启服务...")
                    self._restart_services()
                    consecutive_failures = 0
                else:
                    consecutive_failures = 0

                # 等待下次检查
                time.sleep(2)

            except Exception as e:
                consecutive_failures += 1
                self.logger.error(f"监控循环异常: {e}")

                if consecutive_failures >= 5:
                    self.logger.error("连续失败过多，暂停监控")
                    break

                time.sleep(5)

    def _check_file_changes(self) -> bool:
        """检查文件变化"""
        current_hashes = self._scan_all_files()
        changes_detected = False
        changed_paths: Set[str] = set()

        # 检查新增和修改的文件
        for file_path, current_hash in current_hashes.items():
            if file_path not in self.file_hashes:
                self.logger.info(f"新增文件: {file_path}")
                changes_detected = True
                changed_paths.add(file_path)
            elif self.file_hashes[file_path] != current_hash:
                self.logger.info(f"文件修改: {file_path}")
                changes_detected = True
                changed_paths.add(file_path)

        # 检查删除的文件
        for file_path in self.file_hashes:
            if file_path not in current_hashes:
                self.logger.info(f"文件删除: {file_path}")
                changes_detected = True
                changed_paths.add(file_path)

        # 更新哈希缓存
        if changes_detected:
            self.file_hashes = current_hashes
            self._last_changed_paths = changed_paths

        return changes_detected

    def _restart_services(self):
        """重启服务：根据变更范围向启动器发送命令"""
        current_time = time.time()

        # 防止频繁重启
        if current_time - self.last_restart_time < self.restart_delay:
            self.logger.warning("重启过于频繁，跳过本次重启")
            return

        # 检查重启次数限制
        if self.restart_count >= self.max_restart_attempts:
            self.logger.error("重启次数过多，可能存在循环依赖")
            return

        self.restart_count += 1
        self.last_restart_time = current_time

        try:
            self.logger.info(f"执行第 {self.restart_count} 次重启...")

            # 计算重启范围
            changed = list(self._last_changed_paths) if self._last_changed_paths else []
            restart_cmd = "restart_all"
            if changed:
                ui_changed = any(p.startswith("ui/") for p in changed)
                backend_changed = any(p.startswith("backend/") for p in changed)
                if ui_changed and not backend_changed:
                    restart_cmd = "restart_ui"
                elif backend_changed and not ui_changed:
                    restart_cmd = "restart_backend"
                else:
                    restart_cmd = "restart_all"

            # 写入指令到启动器命令文件
            cmd_file = self.project_root / "logs" / "launcher.cmd"
            try:
                cmd_file.parent.mkdir(exist_ok=True)
                cmd_file.write_text(restart_cmd, encoding="utf-8")
                self.logger.info(f"已发送重启指令: {restart_cmd}")
            except Exception as e:
                self.logger.error(f"写入指令文件失败: {e}")

            # 去抖延时
            time.sleep(self.restart_delay)

            self.logger.info("服务重启指令发送完成")

        except Exception as e:
            self.logger.error(f"重启服务失败: {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        return {
            "monitoring": self.monitoring,
            "files_watched": len(self.file_hashes),
            "restart_count": self.restart_count,
            "last_restart": self.last_restart_time,
            "ignored_files": len(self.ignored_files)
        }

    def add_watch_path(self, path: Union[str, Path]):
        """添加监控路径"""
        watch_path = Path(path)
        if watch_path not in self.watch_paths:
            self.watch_paths.append(watch_path)
            self.logger.info(f"添加监控路径: {watch_path}")

    def remove_watch_path(self, path: Union[str, Path]):
        """移除监控路径"""
        watch_path = Path(path)
        if watch_path in self.watch_paths:
            self.watch_paths.remove(watch_path)
            self.logger.info(f"移除监控路径: {watch_path}")

    def add_ignore_pattern(self, pattern: str):
        """添加忽略模式"""
        if pattern.startswith('*'):
            self.ignored_files.add(pattern[1:])
        else:
            ignore_path = self.project_root / pattern
            if ignore_path.exists():
                self._add_ignore_path(ignore_path)
        self.logger.info(f"添加忽略模式: {pattern}")

    def trigger_manual_restart(self):
        """手动触发重启"""
        self.logger.info("手动触发服务重启...")
        self._restart_services()


def main():
    """主函数"""
    print("🔥 热更新监控器")
    print("=" * 40)

    project_root = Path(__file__).parent
    monitor = HotReloadMonitor(project_root)

    print("📁 监控路径:")
    for path in monitor.watch_paths:
        print(f"  - {path}")

    print(f"\n📊 监控文件数量: {len(monitor.file_hashes)}")
    print(f"📊 忽略文件数量: {len(monitor.ignored_files)}")

    # 启动监控
    monitor.start_monitoring()

    print("\n🚀 热更新监控已启动")
    print("💡 提示:")
    print("  - 修改Python文件会自动重启服务")
    print("  - 按 Ctrl+C 退出")
    print("  - 查看日志了解监控状态")

    try:
        # 显示状态
        while True:
            time.sleep(10)
            status = monitor.get_status()
            print(f"\r📊 监控中... 重启次数: {status['restart_count']}", end="", flush=True)

    except KeyboardInterrupt:
        print("\n\n🛑 用户请求停止监控")
        monitor.stop_monitoring()
        print("✅ 热更新监控已停止")


if __name__ == "__main__":
    main()

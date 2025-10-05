# -*- coding: utf-8 -*-
"""
星辰金融终端启动脚本（稳定版）.

- 虚拟环境激活
- 启动后端与UI
- 守护线程与指令监听（logs/launcher.cmd）
- PID文件写入（logs/launcher.pids）
- 日志记录（logs/launcher.log）
"""

import contextlib
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class TerminalLauncher:
    """终端启动器（稳健实现）."""

    def __init__(self) -> None:
        """初始化终端启动器."""
        self.project_root = Path(__file__).parent
        self.venv_path = self.project_root / "venv310"
        self.backend_path = self.project_root / "backend"
        self.ui_path = self.project_root / "ui"
        self.logs_path = self.project_root / "logs"

        # 进程管理
        self.backend_process: Optional[subprocess.Popen] = None
        self.ui_process: Optional[subprocess.Popen] = None

        # 线程
        self.watchdog_thread: Optional[threading.Thread] = None
        self.cmd_listener_thread: Optional[threading.Thread] = None

        # 文件
        self.cmd_file = self.logs_path / "launcher.cmd"
        self.pids_file = self.logs_path / "launcher.pids"

        # 配置
        self.enable_hot_reload = True
        self.auto_restart = True
        self.restart_delay = 2.0

        # 日志
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """设置日志处理器."""
        self.logs_path.mkdir(exist_ok=True)
        logger = logging.getLogger("TerminalLauncher")
        logger.setLevel(logging.INFO)

        # 避免重复添加处理器
        if not any(isinstance(h, logging.FileHandler)
                   for h in logger.handlers):
            file_handler = logging.FileHandler(
                self.logs_path / "launcher.log", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            fmt = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)

        if not any(isinstance(h, logging.StreamHandler)
                   for h in logger.handlers):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            fmt = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s")
            console_handler.setFormatter(fmt)
            logger.addHandler(console_handler)

        return logger

    def check_venv(self) -> bool:
        """检查虚拟环境是否可用."""
        if not self.venv_path.exists():
            self.logger.error("虚拟环境不存在: %s", self.venv_path)
            return False

        if os.name == "nt":
            activate_script = self.venv_path / "Scripts" / "activate.bat"
        else:
            activate_script = self.venv_path / "bin" / "activate"

        if not activate_script.exists():
            self.logger.error("激活脚本不存在: %s", activate_script)
            return False

        return True

    def activate_venv(self) -> Dict[str, Any]:
        """激活虚拟环境并返回子进程环境配置."""
        if not self.check_venv():
            raise RuntimeError("虚拟环境检查失败")

        if os.name == "nt":
            scripts_path = self.venv_path / "Scripts"
            python_path = scripts_path / "python.exe"
            path_to_add = scripts_path
        else:
            bin_path = self.venv_path / "bin"
            python_path = bin_path / "python"
            path_to_add = bin_path

        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(self.venv_path)
        env["PATH"] = (str(path_to_add) + os.pathsep +
                       env.get("PATH", ""))
        env["PYTHONPATH"] = (str(self.project_root) + os.pathsep +
                             env.get("PYTHONPATH", ""))

        return {"env": env, "python_path": str(python_path)}

    def _write_pids(self) -> None:
        """写入 PID 文件."""
        try:
            self.logs_path.mkdir(exist_ok=True)
            backend_pid = (
                self.backend_process.pid
                if self.backend_process and self.backend_process.poll() is None
                else ""
            )
            ui_pid = (self.ui_process.pid
                      if self.ui_process and
                      self.ui_process.poll() is None else "")
            with open(self.pids_file, "w", encoding="utf-8") as f:
                f.write(f"backend_pid={backend_pid}\n")
                f.write(f"ui_pid={ui_pid}\n")
        except OSError as e:
            self.logger.debug("写入PID文件失败: %s", e)

    def start_backend(self) -> bool:
        """启动后端服务."""
        try:
            if self.backend_process and self.backend_process.poll() is None:
                self.logger.info(
                    "后端已在运行（PID=%s），跳过重复启动",
                    self.backend_process.pid)
                self._write_pids()
                return True

            venv = self.activate_venv()
            backend_main = self.backend_path / "core" / "vnpy_integration.py"
            if not backend_main.exists():
                self.logger.error("后端主文件不存在: %s", backend_main)
                return False

            self.logger.info("启动后端服务...")
            self.backend_process = subprocess.Popen(
                [venv["python_path"], str(backend_main)],
                cwd=str(self.project_root),
                env=venv["env"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.logger.info(
                "后端启动成功，PID=%s", self.backend_process.pid)
            self._write_pids()
            return True
        except (subprocess.SubprocessError, OSError, RuntimeError) as e:
            self.logger.error("启动后端失败: %s", e)
            return False

    def start_ui(self) -> bool:
        """启动UI界面."""
        try:
            if self.ui_process and self.ui_process.poll() is None:
                self.logger.info(
                    "UI已在运行（PID=%s），跳过重复启动",
                    self.ui_process.pid)
                self._write_pids()
                return True

            venv = self.activate_venv()
            ui_main = self.ui_path / "main_window.py"
            if not ui_main.exists():
                self.logger.error("UI主文件不存在: %s", ui_main)
                return False

            self.logger.info("启动UI界面...")
            self.ui_process = subprocess.Popen(
                [venv["python_path"], str(ui_main)],
                cwd=str(self.project_root),
                env=venv["env"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.logger.info(
                "UI启动成功，PID=%s", self.ui_process.pid)
            self._write_pids()
            return True
        except (subprocess.SubprocessError, OSError, RuntimeError) as e:
            self.logger.error("启动UI失败: %s", e)
            return False

    def stop_all(self) -> None:
        """停止所有子进程."""
        self.logger.info("停止所有服务...")
        # 清空命令文件以防意外重启
        with contextlib.suppress(Exception):
            if self.cmd_file.exists():
                self.cmd_file.unlink(missing_ok=True)

        # 停止后端
        if self.backend_process:
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=10)
                self.logger.info("后端进程已停止")
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
                self.logger.warning("后端进程被强制终止")
            except (subprocess.SubprocessError, OSError) as e:
                self.logger.error("停止后端进程失败: %s", e)
            finally:
                self.backend_process = None

        # 停止UI
        if self.ui_process:
            try:
                self.ui_process.terminate()
                self.ui_process.wait(timeout=10)
                self.logger.info("UI进程已停止")
            except subprocess.TimeoutExpired:
                self.ui_process.kill()
                self.logger.warning("UI进程被强制终止")
            except (subprocess.SubprocessError, OSError) as e:
                self.logger.error("停止UI进程失败: %s", e)
            finally:
                self.ui_process = None

        self._write_pids()

    def restart_all(self) -> bool:
        """重启所有服务."""
        self.logger.info("重启所有服务...")
        self.stop_all()
        time.sleep(self.restart_delay)
        ok_back = self.start_backend()
        ok_ui = self.start_ui()
        if ok_back and ok_ui:
            self.logger.info("所有服务重启完成")
            return True
        self.logger.error("服务重启失败")
        return False

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态并刷新PID文件."""
        status = {
            "backend_running": (
                self.backend_process is not None
                and self.backend_process.poll() is None
            ),
            "ui_running": (
                self.ui_process is not None
                and self.ui_process.poll() is None
            ),
            "backend_pid": (
                self.backend_process.pid
                if self.backend_process and self.backend_process.poll() is None
                else None
            ),
            "ui_pid": (self.ui_process.pid
                       if self.ui_process and
                       self.ui_process.poll() is None else None),
            "watchdog_running": (self.watchdog_thread is not None and
                                 self.watchdog_thread.is_alive()),
            "hot_reload_enabled": self.enable_hot_reload,
            "auto_restart_enabled": self.auto_restart,
        }
        self._write_pids()
        return status

    def run_diagnostics(self) -> Dict[str, Any]:
        """运行启动前诊断."""
        info = {
            "venv_ok": self.check_venv(),
            "backend_main_exists": (
                self.backend_path / "core" / "vnpy_integration.py").exists(),
            "ui_main_exists": (
                self.ui_path / "main_window.py").exists(),
            "logs_writable": (
                os.access(str(self.logs_path), os.W_OK)
                if self.logs_path.exists()
                else True
            ),
        }
        return info

    def _watchdog_loop(self) -> None:
        """守护线程：仅在非零退出码时重启，正常退出不重启."""
        self.logger.info("守护线程已启动")
        while True:
            try:
                # 后端进程退出检查
                if (self.backend_process and
                        self.backend_process.poll() is not None):
                    exit_code = self.backend_process.returncode
                    if exit_code != 0:
                        self.logger.warning(
                            "检测到后端异常退出(code=%s)，准备重启",
                            exit_code)
                        if self.auto_restart:
                            time.sleep(self.restart_delay)
                            self.start_backend()
                    else:
                        self.logger.info("后端正常退出(code=0)，不自动重启")
                    self.backend_process = None

                # UI进程退出检查
                if self.ui_process and self.ui_process.poll() is not None:
                    exit_code = self.ui_process.returncode
                    if exit_code != 0:
                        self.logger.warning(
                            "检测到UI异常退出(code=%s)，准备重启", exit_code)
                        if self.auto_restart:
                            time.sleep(self.restart_delay)
                            self.start_ui()
                    else:
                        self.logger.info("UI正常退出(code=0)，不自动重启")
                    self.ui_process = None

                time.sleep(3)
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                self.logger.error("守护线程异常: %s", e)
                time.sleep(3)

    def _command_listener_loop(self) -> None:
        """指令监听：读取 logs/launcher.cmd 执行 restart 命令."""
        self.logger.info("指令监听线程已启动")
        self.logs_path.mkdir(exist_ok=True)
        while True:
            try:
                if self.cmd_file.exists():
                    content = ""
                    try:
                        content = self.cmd_file.read_text(
                            encoding="utf-8").strip()
                    except (OSError, UnicodeDecodeError):
                        content = ""
                    if content:
                        self.logger.info("收到指令: %s", content)
                        # 清空指令文件避免重复
                        with contextlib.suppress(Exception):
                            self.cmd_file.write_text("", encoding="utf-8")
                        if content == "restart_all":
                            self.restart_all()
                        elif content == "restart_ui":
                            if (self.ui_process and
                                    self.ui_process.poll() is None):
                                try:
                                    self.ui_process.terminate()
                                    self.ui_process.wait(timeout=10)
                                except (subprocess.SubprocessError, OSError):
                                    with contextlib.suppress(Exception):
                                        self.ui_process.kill()
                                finally:
                                    self.ui_process = None
                            time.sleep(self.restart_delay)
                            self.start_ui()
                        elif content == "restart_backend":
                            if (self.backend_process and
                                    self.backend_process.poll() is None):
                                try:
                                    self.backend_process.terminate()
                                    self.backend_process.wait(timeout=10)
                                except (subprocess.SubprocessError, OSError):
                                    with contextlib.suppress(Exception):
                                        self.backend_process.kill()
                                finally:
                                    self.backend_process = None
                            time.sleep(self.restart_delay)
                            self.start_backend()
                time.sleep(1)
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                self.logger.error("指令监听异常: %s", e)
                time.sleep(2)

    def start_watchdog(self) -> None:
        """启动守护与指令监听线程."""
        if not (self.watchdog_thread and self.watchdog_thread.is_alive()):
            self.watchdog_thread = threading.Thread(
                target=self._watchdog_loop, daemon=True)
            self.watchdog_thread.start()
        if not (self.cmd_listener_thread and
                self.cmd_listener_thread.is_alive()):
            self.cmd_listener_thread = threading.Thread(
                target=self._command_listener_loop, daemon=True)
            self.cmd_listener_thread.start()
        self.logger.info("守护与指令监听线程已就绪")


def main() -> int:
    """主启动函数."""
    print("🚀 星辰金融终端启动器（稳定版）")
    print("=" * 50)

    launcher = TerminalLauncher()

    print("🔍 运行诊断...")
    diag = launcher.run_diagnostics()
    fail_keys = [k for k, v in diag.items() if not v]
    if fail_keys:
        print("❌ 诊断失败：")
        for k in fail_keys:
            print(f"  - {k}: 失败")
        return 1
    print("✅ 诊断通过")

    print("\n🏃‍♂️ 启动服务...")
    if not launcher.start_backend():
        print("❌ 后端启动失败")
        return 1

    time.sleep(2)

    if not launcher.start_ui():
        print("❌ UI启动失败")
        launcher.stop_all()
        return 1

    print("✅ 所有服务启动完成")
    launcher.start_watchdog()

    status = launcher.get_status()
    print("📊 当前状态：")
    print(f"  - 后端运行: {'✅' if status['backend_running'] else '❌'} "
          f"(PID={status['backend_pid']})")
    print(f"  - UI运行: {'✅' if status['ui_running'] else '❌'} "
          f"(PID={status['ui_pid']})")
    print(f"  - 热更新: {'✅' if status['hot_reload_enabled'] else '❌'}")

    print("\n💡 提示：Ctrl+C 退出；变更代码后可向 logs/launcher.cmd 写入")
    print("     restart_ui 或 restart_backend 测试热更新")

    try:
        while True:
            time.sleep(1)
            _ = launcher.get_status()
    except KeyboardInterrupt:
        print("\n👋 用户退出，正在停止服务...")
        launcher.stop_all()
        print("✅ 已退出")
        return 0


def quick_start() -> int:
    """快速启动（简化版）."""
    launcher = TerminalLauncher()
    try:
        if launcher.start_backend() and launcher.start_ui():
            launcher.start_watchdog()
            print("✅ 快速启动成功（Ctrl+C退出）")
            while True:
                time.sleep(1)
        else:
            print("❌ 快速启动失败")
            return 1
    except KeyboardInterrupt:
        print("\n🛑 用户退出")
    finally:
        launcher.stop_all()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        sys.exit(quick_start())
    else:
        sys.exit(main())

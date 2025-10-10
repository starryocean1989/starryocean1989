# -*- coding: utf-8 -*-
"""
星辰金融终端启动脚本（简化版）.

纯Python桌面应用启动器 - 无热更新机制
"""

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


def setup_logging() -> logging.Logger:
    """设置日志."""
    logger = logging.getLogger("TerminalStarter")
    logger.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（可选）
    logs_path = Path(__file__).parent / "logs"
    logs_path.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(logs_path / "terminal_start.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


def check_venv(venv_path: Path, logger: logging.Logger) -> bool:
    """检查虚拟环境."""
    if not venv_path.exists():
        logger.error("❌ 虚拟环境不存在: %s", venv_path)
        return False

    if os.name == "nt":
        python_exe = venv_path / "Scripts" / "python.exe"
    else:
        python_exe = venv_path / "bin" / "python"

    if not python_exe.exists():
        logger.error("❌ Python解释器不存在: %s", python_exe)
        return False

    logger.info("✅ 虚拟环境检查通过")
    return True


def check_ui_main(ui_path: Path, logger: logging.Logger) -> bool:
    """检查UI主文件."""
    ui_main = ui_path / "main_window.py"
    if not ui_main.exists():
        logger.error("❌ UI主文件不存在: %s", ui_main)
        return False

    logger.info("✅ UI主文件检查通过")
    return True


def activate_venv(venv_path: Path, project_root: Path) -> dict:
    """激活虚拟环境并返回环境变量."""
    if os.name == "nt":
        scripts_path = venv_path / "Scripts"
        python_path = scripts_path / "python.exe"
        path_to_add = scripts_path
    else:
        bin_path = venv_path / "bin"
        python_path = bin_path / "python"
        path_to_add = bin_path

    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_path)
    env["PATH"] = str(path_to_add) + os.pathsep + env.get("PATH", "")

    # 确保项目根目录在PYTHONPATH中（必须在最前面）
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        env["PYTHONPATH"] = str(project_root) + os.pathsep + existing_pythonpath
    else:
        env["PYTHONPATH"] = str(project_root)

    # 设置配置文件路径，确保启动时加载配置
    config_file = project_root / "config" / "terminal_config.json"
    env["CONFIG_FILE"] = str(config_file)

    # 设置Python解释器路径，用于PySide6 WebEngine和其他子进程
    env["PYTHONEXECUTABLE"] = str(python_path)
    env["QT_WEBENGINE_PYTHON_EXECUTABLE"] = str(python_path)

    return {"env": env, "python_path": str(python_path)}


def start_ui(
    python_path: str, ui_main: Path, project_root: Path, env: dict, logger: logging.Logger
) -> Optional[subprocess.Popen]:
    """启动UI进程."""
    try:
        logger.info("🚀 正在启动UI界面...")

        process = subprocess.Popen(
            [python_path, str(ui_main)],
            cwd=str(project_root),
            env=env,
            # 移除stdout/stderr重定向，让输出直接显示
            # stdout=subprocess.PIPE,
            # stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        # 等待一小段时间确保进程启动
        time.sleep(0.5)

        # 检查进程是否立即退出
        if process.poll() is not None:
            logger.error("❌ UI进程启动后立即退出 (退出码: %d)", process.returncode)
            # 读取错误输出
            if process.stderr:
                stderr = process.stderr.read()
                if stderr:
                    logger.error("错误输出:\n%s", stderr)
                    # 同时在控制台显示错误
                    print(f"\n❌ UI启动错误:\n{stderr}")
            if process.stdout:
                stdout = process.stdout.read()
                if stdout:
                    logger.error("标准输出:\n%s", stdout)
            return None

        logger.info("✅ UI启动成功 (PID: %d)", process.pid)
        return process

    except Exception as e:
        logger.error("❌ 启动UI失败: %s", e, exc_info=True)
        return None


def main() -> int:
    """主函数."""
    print("=" * 60)
    print("🚀 星辰金融终端启动器")
    print("=" * 60)
    print()

    # 设置日志
    logger = setup_logging()

    # 路径设置
    project_root = Path(__file__).parent
    venv_path = project_root / "venv310"
    ui_path = project_root / "ui"

    logger.info("项目根目录: %s", project_root)
    logger.info("虚拟环境: %s", venv_path)

    # 1. 诊断检查
    print("🔍 运行启动前诊断...")
    print()

    checks = {
        "虚拟环境": check_venv(venv_path, logger),
        "UI主文件": check_ui_main(ui_path, logger),
    }

    failed = [name for name, result in checks.items() if not result]

    if failed:
        print()
        print("❌ 诊断失败，以下检查未通过:")
        for name in failed:
            print(f"  - {name}")
        print()
        print("💡 请确保:")
        print("  1. 虚拟环境已正确创建 (venv310/)")
        print("  2. UI主文件存在 (ui/main_window.py)")
        print()
        return 1

    print("✅ 诊断通过")
    print()

    # 2. 激活虚拟环境
    print("⚙️  配置运行环境...")
    venv_config = activate_venv(venv_path, project_root)
    logger.info("Python路径: %s", venv_config["python_path"])
    print("✅ 环境配置完成")
    print()

    # 3. 启动UI
    print("🏃 启动应用程序...")
    ui_main = ui_path / "main_window.py"
    ui_process = start_ui(
        venv_config["python_path"], ui_main, project_root, venv_config["env"], logger
    )

    if not ui_process:
        print()
        print("❌ 应用启动失败")
        print()
        print("💡 请检查:")
        print("  1. 查看日志文件: logs/terminal_start.log")
        print("  2. 确保所有依赖已安装")
        print("  3. 确保没有其他实例在运行")
        print()
        return 1

    print()
    print("=" * 60)
    print("✅ 应用启动成功!")
    print("=" * 60)
    print()
    print("📊 进程信息:")
    print(f"  - PID: {ui_process.pid}")
    print(f"  - Python: {venv_config['python_path']}")
    print()
    print("💡 使用提示:")
    print("  - 按 Ctrl+C 退出应用")
    print("  - 查看日志: logs/terminal_start.log")
    print()
    print("📝 架构说明:")
    print("  本项目是纯Python桌面应用")
    print("  UI层直接调用Backend服务层")
    print("  Backend层集成VNPY量化框架")
    print()

    # 4. 等待进程结束
    try:
        logger.info("等待UI进程结束...")
        ui_process.wait()
        exit_code = ui_process.returncode

        if exit_code == 0:
            logger.info("UI进程正常退出")
            print("\n✅ 应用正常退出")
        else:
            logger.warning("UI进程异常退出 (退出码: %d)", exit_code)
            print(f"\n⚠️  应用异常退出 (退出码: {exit_code})")
            print("💡 请查看日志文件了解详情")

        return exit_code

    except KeyboardInterrupt:
        print("\n\n👋 用户请求退出...")
        logger.info("用户中断，正在停止UI进程...")

        try:
            ui_process.terminate()
            ui_process.wait(timeout=10)
            logger.info("UI进程已停止")
            print("✅ 应用已退出")
        except subprocess.TimeoutExpired:
            logger.warning("UI进程未响应，强制终止")
            ui_process.kill()
            print("⚠️  应用已强制退出")

        return 0

    except Exception as e:
        logger.error("运行时错误: %s", e, exc_info=True)
        print(f"\n❌ 运行时错误: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

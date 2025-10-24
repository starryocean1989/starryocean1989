# -*- coding: utf-8 -*-
"""
监控进程清理工具 - 用于清理可能残留的监控进程和释放端口

使用场景:
- 测试前清理旧的监控进程
- 端口被占用时强制释放
- 开发调试时重置环境
"""

import logging
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def find_process_by_port(port: int) -> list:
    """查找占用指定端口的进程."""
    logger.info(f"查找占用端口 {port} 的进程...")

    processes = []
    try:
        if platform.system() == "Windows":
            # Windows: 使用 netstat
            cmd = f"netstat -ano | findstr :{port}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            pid = int(parts[-1])
                            if pid not in processes:
                                processes.append(pid)
                        except ValueError:
                            continue
        else:
            # Linux/Mac: 使用 lsof
            cmd = f"lsof -i :{port} -t"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.split("\n"):
                line = line.strip()
                if line:
                    try:
                        processes.append(int(line))
                    except ValueError:
                        continue

    except Exception as e:
        logger.error(f"查找进程失败: {e}")

    return processes


def kill_process(pid: int) -> bool:
    """终止指定PID的进程."""
    try:
        if platform.system() == "Windows":
            subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, check=True)
        else:
            os.kill(pid, 9)  # SIGKILL

        logger.info(f"✅ 已终止进程 PID={pid}")
        return True

    except subprocess.CalledProcessError:
        logger.warning(f"⚠️  进程 PID={pid} 可能已不存在")
        return False
    except Exception as e:
        logger.error(f"❌ 终止进程失败 PID={pid}: {e}")
        return False


def find_monitor_processes() -> list:
    """查找所有监控进程."""
    logger.info("查找监控进程...")

    processes = []
    try:
        if platform.system() == "Windows":
            # 查找Python进程中包含monitor_process_entry.py的
            cmd = "wmic process where \"name='python.exe' or name='pythonw.exe'\" get ProcessId,CommandLine /format:csv"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.split("\n"):
                if "monitor_process_entry.py" in line or "monitor_core.py" in line:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        try:
                            pid = int(parts[-1].strip())
                            processes.append(pid)
                        except ValueError:
                            continue
        else:
            # Linux/Mac
            cmd = "ps aux | grep 'monitor_process_entry.py\\|monitor_core.py' | grep -v grep"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            for line in result.stdout.split("\n"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        processes.append(int(parts[1]))
                    except ValueError:
                        continue

    except Exception as e:
        logger.error(f"查找监控进程失败: {e}")

    return processes


def cleanup_monitor_processes():
    """清理所有监控进程."""
    print("=" * 60)
    print("监控进程清理工具")
    print("=" * 60)
    print()

    # 1. 查找并终止监控进程
    logger.info("步骤1: 查找监控进程...")
    monitor_pids = find_monitor_processes()

    if monitor_pids:
        logger.info(f"发现 {len(monitor_pids)} 个监控进程")
        for pid in monitor_pids:
            print(f"  🔍 发现监控进程 PID={pid}")
            kill_process(pid)
        time.sleep(1)
    else:
        logger.info("✅ 未发现运行中的监控进程")
        print("  ✅ 未发现运行中的监控进程")

    print()

    # 2. 检查并释放端口
    logger.info("步骤2: 检查ZMQ端口...")
    ports = [5555, 5556, 5557]

    for port in ports:
        pids = find_process_by_port(port)
        if pids:
            logger.warning(f"端口 {port} 被占用")
            print(f"  ⚠️  端口 {port} 被占用")
            for pid in pids:
                print(f"     PID={pid}")
                # 只终止监控进程，不终止其他进程
                if (
                    pid in monitor_pids
                    or input(f"     是否终止进程 PID={pid}? (y/n): ").lower() == "y"
                ):
                    kill_process(pid)
        else:
            logger.info(f"✅ 端口 {port} 空闲")
            print(f"  ✅ 端口 {port} 空闲")

    print()

    # 3. 等待端口完全释放
    logger.info("步骤3: 等待端口释放...")
    print("  ⏳ 等待2秒让端口完全释放...")
    time.sleep(2)

    # 验证端口状态
    all_clear = True
    for port in ports:
        pids = find_process_by_port(port)
        if pids:
            logger.error(f"❌ 端口 {port} 仍被占用: {pids}")
            print(f"  ❌ 端口 {port} 仍被占用")
            all_clear = False

    print()
    print("=" * 60)
    if all_clear:
        logger.info("✅ 清理完成，所有端口已释放")
        print("✅ 清理完成")
        print("   可以安全启动监控进程")
    else:
        logger.warning("⚠️  部分端口仍被占用，可能需要手动处理")
        print("⚠️  部分端口仍被占用")
        print("   建议重启系统或手动终止占用进程")
    print("=" * 60)


def main():
    """主函数."""
    try:
        cleanup_monitor_processes()
    except KeyboardInterrupt:
        print("\n\n清理操作被用户中断")
    except Exception as e:
        logger.error(f"清理失败: {e}", exc_info=True)
        print(f"\n❌ 清理失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

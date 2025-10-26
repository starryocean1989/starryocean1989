# -*- coding: utf-8 -*-
"""
SystemManager 自动化调试脚本
- 启动程序
- 等待收集日志
- 分析日志
- 输出诊断报告
"""
import subprocess
import time
import os
import sys
from pathlib import Path

# 切换到项目根目录
PROJECT_ROOT = Path(__file__).parent
os.chdir(PROJECT_ROOT)

# 日志文件路径
LOG_FILE = PROJECT_ROOT / "logs" / "systemmanager_debug.log"
REPORT_FILE = PROJECT_ROOT / "logs" / "debug_report.txt"


def setup_debug_logging():
    """配置SystemManager使用文件日志"""
    code = """
import logging
from pathlib import Path

# 确保logs目录存在
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 创建专门的DEBUG日志记录器
debug_logger = logging.getLogger("SystemManager.DEBUG")
debug_logger.setLevel(logging.DEBUG)

# 清除旧的handler
for handler in debug_logger.handlers[:]:
    debug_logger.removeHandler(handler)

# 文件handler（DEBUG级别）
file_handler = logging.FileHandler("logs/systemmanager_debug.log", mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# 格式化器
formatter = logging.Formatter(
    "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
file_handler.setFormatter(formatter)
debug_logger.addHandler(file_handler)

# 注入到SystemManager
import sys
sys.modules["__debug_logger__"] = debug_logger
print("[DEBUG] ✅ 调试日志已配置: logs/systemmanager_debug.log")
"""

    # 写入启动脚本
    startup_code_file = PROJECT_ROOT / "logs" / "_debug_inject.py"
    startup_code_file.parent.mkdir(exist_ok=True)
    startup_code_file.write_text(code, encoding="utf-8")
    return startup_code_file


def modify_systemmanager_for_debug():
    """修改SystemManager代码以使用DEBUG日志"""
    sm_file = PROJECT_ROOT / "ui" / "modules" / "system_manager_view.py"
    content = sm_file.read_text(encoding="utf-8")

    # 检查是否已经注入
    if "__debug_logger__" in content:
        print("[DEBUG] SystemManager 已注入调试日志")
        return True

    # 在__init__的super().__init__之后注入
    inject_code = """

        # 🔍 调试注入：使用专门的DEBUG文件日志
        try:
            import sys
            if "__debug_logger__" in sys.modules:
                self._debug_logger = sys.modules["__debug_logger__"]
                self._debug_logger.info("=" * 60)
                self._debug_logger.info("SystemManager 调试会话开始")
                self._debug_logger.info("=" * 60)
            else:
                self._debug_logger = self.logger
        except:
            self._debug_logger = self.logger
"""

    # 找到 super().__init__(parent, "系统管理") 后面插入
    marker = '        super().__init__(parent, "系统管理")'
    if marker in content:
        content = content.replace(marker, marker + inject_code)
        sm_file.write_text(content, encoding="utf-8")
        print("[DEBUG] ✅ 已注入调试日志到 SystemManager")
        return True
    else:
        print("[DEBUG] ❌ 未找到注入点")
        return False


def inject_debug_logs():
    """在关键方法中注入DEBUG日志"""
    sm_file = PROJECT_ROOT / "ui" / "modules" / "system_manager_view.py"
    content = sm_file.read_text(encoding="utf-8")

    # 替换关键日志点为DEBUG logger
    replacements = [
        # 事件处理器
        ('self.logger.info("[EventHandler]', 'self._debug_logger.info("[EventHandler]'),
        ('self.logger.warning("[EventHandler]', 'self._debug_logger.warning("[EventHandler]'),
        ('self.logger.error("[EventHandler]', 'self._debug_logger.error("[EventHandler]'),
        # UI更新
        ('self.logger.info("[UIUpdate]', 'self._debug_logger.info("[UIUpdate]'),
        ('self.logger.error("[UIUpdate]', 'self._debug_logger.error("[UIUpdate]'),
    ]

    modified = False
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            modified = True

    if modified:
        sm_file.write_text(content, encoding="utf-8")
        print("[DEBUG] ✅ 已注入详细DEBUG日志")

    return modified


def start_terminal():
    """启动终端程序（后台运行）"""
    print("\n" + "=" * 60)
    print("🚀 启动星辰金融终端...")
    print("=" * 60)

    # 使用Python启动脚本
    python_exe = PROJECT_ROOT / "venv310" / "Scripts" / "python.exe"
    startup_script = PROJECT_ROOT / "start_async_fixed.py"

    if not python_exe.exists():
        print(f"❌ 未找到Python: {python_exe}")
        return None

    if not startup_script.exists():
        print(f"❌ 未找到启动脚本: {startup_script}")
        return None

    # 确保日志目录存在
    LOG_FILE.parent.mkdir(exist_ok=True)

    # 先导入DEBUG logger配置
    setup_code = setup_debug_logging()

    # 启动进程（后台运行，重定向输出）
    process = subprocess.Popen(
        [str(python_exe), str(startup_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(PROJECT_ROOT),
    )

    print(f"✅ 进程已启动 (PID: {process.pid})")
    return process


def wait_and_collect_logs(duration=15):
    """等待并收集日志"""
    print(f"\n⏳ 等待 {duration} 秒收集日志...")
    for i in range(duration):
        time.sleep(1)
        if i % 5 == 4:
            print(f"   {i+1}/{duration} 秒...")
    print("✅ 日志收集完成")


def analyze_logs():
    """分析日志文件"""
    print("\n" + "=" * 60)
    print("📊 分析日志...")
    print("=" * 60)

    if not LOG_FILE.exists():
        print(f"❌ 日志文件不存在: {LOG_FILE}")
        return None

    content = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
    lines = content.split("\n")

    # 统计关键事件
    stats = {
        "首次事件": 0,
        "事件计数": 0,
        "节流跳过": 0,
        "待处理跳过": 0,
        "安排更新": 0,
        "开始更新": 0,
        "更新完成": 0,
        "标志重置": 0,
        "更新失败": 0,
    }

    event_numbers = []
    last_event_num = 0

    for line in lines:
        if "[EventHandler]" in line:
            if "首次接收" in line:
                stats["首次事件"] += 1
            elif "已接收" in line and "个事件" in line:
                stats["事件计数"] += 1
                # 提取事件编号
                try:
                    num = int(line.split("已接收 ")[1].split(" ")[0])
                    event_numbers.append(num)
                    last_event_num = num
                except:
                    pass
            elif "已有待处理更新，跳过" in line:
                stats["待处理跳过"] += 1
            elif "安排UI更新" in line:
                stats["安排更新"] += 1

        elif "[UIUpdate]" in line:
            if "节流跳过" in line:
                stats["节流跳过"] += 1
            elif "开始更新UI" in line:
                stats["开始更新"] += 1
            elif "UI更新完成" in line:
                stats["更新完成"] += 1
            elif "标志已重置" in line:
                stats["标志重置"] += 1
            elif "更新失败" in line:
                stats["更新失败"] += 1

    # 生成报告
    report = []
    report.append("=" * 60)
    report.append("SystemManager 调试报告")
    report.append("=" * 60)
    report.append("")
    report.append(f"日志文件: {LOG_FILE}")
    report.append(f"总行数: {len(lines)}")
    report.append("")
    report.append("事件统计:")
    report.append("-" * 40)
    for key, value in stats.items():
        report.append(f"  {key:15s}: {value:5d}")
    report.append("")

    if event_numbers:
        report.append(f"事件编号范围: {min(event_numbers)} ~ {max(event_numbers)}")
        report.append(f"最后事件编号: {last_event_num}")
    report.append("")

    # 诊断
    report.append("诊断结果:")
    report.append("-" * 40)

    if stats["首次事件"] == 0:
        report.append("❌ 未接收到任何事件 → 事件订阅失败")
    elif stats["首次事件"] > 0 and last_event_num <= 1:
        report.append("❌ 只接收到首次事件，后续事件丢失 → 事件订阅问题")
    elif stats["待处理跳过"] > stats["标志重置"]:
        report.append(f"❌ 节流标志卡死: 跳过{stats['待处理跳过']}次, 重置{stats['标志重置']}次")
    elif stats["安排更新"] > 0 and stats["开始更新"] == 0:
        report.append("❌ UI更新未执行 → QTimer.singleShot 调度失败")
    elif stats["开始更新"] > stats["更新完成"]:
        report.append(f"❌ UI更新中断: 开始{stats['开始更新']}次, 完成{stats['更新完成']}次")
    elif last_event_num > 1 and stats["标志重置"] > 0:
        report.append("✅ 事件接收正常，节流机制正常")
        report.append(f"   共接收 {last_event_num} 个事件")
        report.append(f"   节流跳过 {stats['节流跳过']} 次")
        report.append(f"   更新完成 {stats['更新完成']} 次")
    else:
        report.append("⚠️ 无法确定状态，需要查看详细日志")

    report.append("")
    report.append("=" * 60)

    report_text = "\n".join(report)
    print(report_text)

    # 保存报告
    REPORT_FILE.parent.mkdir(exist_ok=True)
    REPORT_FILE.write_text(report_text, encoding="utf-8")
    print(f"\n📄 报告已保存: {REPORT_FILE}")

    return stats


def main():
    """主流程"""
    print("=" * 60)
    print("SystemManager 自动化调试工具")
    print("=" * 60)

    # 步骤1: 修改代码注入DEBUG日志
    print("\n[步骤1] 注入调试日志...")
    if not modify_systemmanager_for_debug():
        print("❌ 注入失败，退出")
        return
    inject_debug_logs()

    # 步骤2: 启动程序
    process = start_terminal()
    if not process:
        print("❌ 启动失败，退出")
        return

    try:
        # 步骤3: 等待收集日志
        wait_and_collect_logs(duration=15)

        # 步骤4: 分析日志
        stats = analyze_logs()

        # 步骤5: 终止程序
        print("\n🛑 终止程序...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("✅ 程序已终止")

        # 步骤6: 返回诊断结果
        if stats:
            if stats["待处理跳过"] > stats["标志重置"]:
                print("\n❌ 发现节流标志卡死问题！")
                return False
            elif stats["首次事件"] > 0 and stats["标志重置"] > 0:
                print("\n✅ 系统正常运行！")
                return True

        print("\n⚠️ 需要手动检查日志")
        return None

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        process.terminate()
        return None
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        process.terminate()
        return None


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result else 1)

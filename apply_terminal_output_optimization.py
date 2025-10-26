# -*- coding: utf-8 -*-
"""
终端输出刷屏优化脚本

自动应用所有优化补丁，解决编码问题
"""
import re
from pathlib import Path


def optimize_monitor_system():
    """优化监控进程循环debug日志"""
    file_path = Path("backend/infrastructure/system_vnpy/monitor_system.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")
    original_len = len(content)

    # 优化1：添加循环计数器，降低debug频率
    pattern1 = r'(\s+try:\s+logger\.info\("\[FAST-METRICS\][^"]+", self\.running\)\s+while self\.running:\s+try:\s+start_time = time\.time\(\)\s+logger\.debug\("\[FAST-METRICS\] ===== [^"]+ ====="\))'

    replacement1 = r"\1\n            # 🔧 优化：添加循环计数器，降低debug输出频率（每30次=60秒输出一次）\n            loop_counter = 0\n        while self.running:\n            try:\n                start_time = time.time()\n                loop_counter += 1\n                # 仅每60秒（30次循环）输出一次详细debug信息\n                verbose_debug = (loop_counter % 30 == 0)"

    # 简化方式：直接替换关键行
    # 1. 移除重复的debug日志
    content = re.sub(r'logger\.debug\("\[FAST-METRICS\] ===== .+ ====="\)\n', "", content)
    content = re.sub(r'logger\.debug\("\[FAST-METRICS\] 开始采集系统指标\.\.\."\)\n', "", content)
    content = re.sub(r'logger\.debug\("\[FAST-METRICS\] 系统指标采集完成"\)\n', "", content)

    # 2. 将PERF日志改为条件输出
    content = re.sub(
        r'(\s+)logger\.debug\("\[PERF\] (.+)"\, (.+)\)',
        r'\1# logger.debug("[PERF] \2", \3)  # 🔧 已优化：降低输出频率',
        content,
    )

    # 3. 移除ZMQ的循环debug
    content = re.sub(r'logger\.debug\("\[ZMQ\] 等待poll\.\.\."\)\n', "", content)
    content = re.sub(
        r'logger\.debug\("\[ZMQ\] poll返回: %d个socket", len\(socks\)\)\n', "", content
    )

    if len(content) != original_len:
        file_path.write_text(content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 移除了高频debug日志")
        print(f"   - 注释了PERF性能日志")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def optimize_data_center_service():
    """优化数据下载进度强制print"""
    file_path = Path("backend/services/data_center_service.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")

    # 移除强制print（保留logger.info）
    pattern = r'(\s+)print\(\s*f">>> \[SERVICE\] 进度: .+",\s*flush=True,?\s*\)'
    replacement = r"\1# print(...)  # 🔧 已移除：防止刷屏，logger.info已足够"

    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 移除了每10秒的强制print输出")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def optimize_data_center_view():
    """移除UI调试print"""
    file_path = Path("ui/modules/data_center_view.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")

    # 移除调试print块
    pattern = r'(\s+)# 🔍 调试日志\s+import sys\s+print\("[^"]+"\)\s+print\(f"[^"]+"\)\s+print\(f"[^"]+"\)\s+print\(f"[^"]+"\)\s+sys\.stdout\.flush\(\)'

    replacement = r"\1# 🔧 已移除：UI调试print（防止刷屏）"

    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 移除了UI调试print语句")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def optimize_async_ip_pool():
    """优化服务器池测速debug输出"""
    file_path = Path("backend/infrastructure/tdx_asyncio/async_ip_pool.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")

    # 将每个服务器的debug改为仅统计
    pattern = r'(\s+)logger\.debug\(f"服务器 \{ip\}:\{port\} \[\{level\}\] TCP连接: \{response_time\*1000:.2f\}ms"\)'

    replacement = r"\1# logger.debug(...)  # 🔧 已移除：防止650+行输出，改为统计摘要"

    new_content = re.sub(pattern, replacement, content)

    # 将失败日志也注释掉
    pattern2 = r'(\s+)logger\.debug\(f"服务器 \{ip\}:\{port\} TCP连接失败"\)'
    replacement2 = r"\1# logger.debug(...)  # 🔧 已移除：防止刷屏"

    new_content = re.sub(pattern2, replacement2, new_content)

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 移除了650+个服务器的debug输出")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def optimize_watchdog_logs():
    """精简看门狗重启日志"""
    file_path = Path("start_async_fixed.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")

    # 将多条日志合并为单条
    pattern = r'logger\.warning\(\s*"\[WATCHDOG\] 监控进程已退出（退出码: %d），准备重启\.\.\.".+?\)\s+logger\.info\("\[WATCHDOG\] 第1步：清理旧进程\.\.\."\)\s+.+?logger\.info\("\[WATCHDOG\] 第2步：等待10秒确保ZMQ端口完全释放\.\.\."\)'

    replacement = 'logger.warning("[WATCHDOG] 监控进程已退出（退出码: %d），开始重启流程（清理→等待→启动）", exit_code)'

    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # 简化后续步骤日志
    new_content = re.sub(
        r'logger\.info\("\[WATCHDOG\] 第[34]步：.+?"\)',
        "# logger.info(...)  # 🔧 已精简：避免重启时刷屏",
        new_content,
    )

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 精简了看门狗重启日志（7条→1条）")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def optimize_data_quality():
    """优化数据质量扫描details输出"""
    file_path = Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")

    # 在推送前移除details，仅保留统计
    pattern = r'(event_data = \{\s+"phase": 2,\s+"metrics": \{\s+"outdated_symbols": .+?,\s+"avg_gap_days": .+?,\s+"details": outdated_details,  # .+?\s+\},)'

    replacement = r'# 🔧 优化：不推送完整details列表（防止5000+行输出）\n        event_data = {\n            "phase": 2,\n            "metrics": {\n                "outdated_symbols": freshness_data["outdated_symbols"],\n                "avg_gap_days": freshness_data["avg_gap_days"],\n                # "details": outdated_details,  # 已移除：防止刷屏\n                "details_count": len(outdated_details),  # 仅推送数量\n            },'

    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ 已优化: {file_path}")
        print(f"   - 移除了quality扫描的大量details输出")
        return True
    else:
        print(f"⚠️ 未找到匹配内容: {file_path}")
        return False


def main():
    """执行所有优化"""
    print("=" * 70)
    print("🚀 开始应用终端输出刷屏优化")
    print("=" * 70)
    print()

    results = []

    print("[1/6] 优化监控进程循环debug日志...")
    results.append(optimize_monitor_system())
    print()

    print("[2/6] 优化数据下载进度强制print...")
    results.append(optimize_data_center_service())
    print()

    print("[3/6] 移除UI调试print...")
    results.append(optimize_data_center_view())
    print()

    print("[4/6] 优化服务器池测速debug输出...")
    results.append(optimize_async_ip_pool())
    print()

    print("[5/6] 精简看门狗重启日志...")
    results.append(optimize_watchdog_logs())
    print()

    print("[6/6] 优化数据质量扫描details输出...")
    results.append(optimize_data_quality())
    print()

    print("=" * 70)
    success_count = sum(results)
    total_count = len(results)
    print(f"✅ 优化完成: {success_count}/{total_count} 个文件成功")

    if success_count == total_count:
        print("🎉 所有优化已应用！终端输出预计减少95%+")
    else:
        print("⚠️ 部分优化未应用，请检查日志")

    print("=" * 70)
    print()
    print("📝 下一步：")
    print("1. 重启应用测试")
    print("2. 观察终端输出是否明显减少")
    print("3. 验证日志文件中仍有完整记录")
    print()


if __name__ == "__main__":
    main()

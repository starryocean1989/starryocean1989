# -*- coding: utf-8 -*-
"""
终端输出优化验证脚本

检查所有修改是否正确应用
"""
import re
from pathlib import Path


def verify_file_modification(file_path: Path, checks: list) -> tuple[bool, list]:
    """
    验证文件修改

    Args:
        file_path: 文件路径
        checks: 检查项列表 [(pattern, expected_result, description)]

    Returns:
        (是否全部通过, 失败的检查)
    """
    if not file_path.exists():
        return False, [f"文件不存在: {file_path}"]

    content = file_path.read_text(encoding="utf-8")
    failures = []

    for pattern, expected, description in checks:
        if isinstance(expected, bool):
            found = bool(re.search(pattern, content, re.MULTILINE | re.DOTALL))
            if found != expected:
                failures.append(f"❌ {description}: {'找到' if found else '未找到'}")
        else:
            matches = len(re.findall(pattern, content, re.MULTILINE))
            if expected == "0":
                if matches > 0:
                    failures.append(f"❌ {description}: 仍有{matches}处")
            elif matches == 0:
                failures.append(f"❌ {description}: 未找到修改标记")

    return len(failures) == 0, failures


def main():
    """执行所有验证"""
    print("=" * 70)
    print("🔍 验证终端输出优化")
    print("=" * 70)
    print()

    all_pass = True

    # 验证1：监控进程
    print("[1/6] 验证监控进程优化...")
    checks = [
        (r'logger\.debug\("\[FAST-METRICS\] ===== ', "0", "循环debug已移除"),
        (r'logger\.debug\("\[FAST-METRICS\] 开始采集系统指标', "0", "采集开始debug已移除"),
        (r'# logger\.debug\("\[PERF\]', True, "PERF日志已注释"),
        (r'logger\.debug\("\[ZMQ\] 等待poll', "0", "ZMQ循环debug已移除"),
    ]
    passed, failures = verify_file_modification(
        Path("backend/infrastructure/system_vnpy/monitor_system.py"), checks
    )
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 验证2：数据下载进度
    print("[2/6] 验证数据下载进度优化...")
    checks = [
        (r"# print\(\.\.\.?\)  # 🔧 已移除：防止刷屏", True, "进度print已移除"),
        (r'print\(\s*f">>> \[SERVICE\] 进度:', "0", "强制print已移除"),
    ]
    passed, failures = verify_file_modification(
        Path("backend/services/data_center_service.py"), checks
    )
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 验证3：UI调试print
    print("[3/6] 验证UI调试print移除...")
    checks = [
        (r'print\("\\n🔍 \[DEBUG\]', "0", "DEBUG print已移除"),
        (r"# 🔧 已移除：UI调试print", True, "有移除标记"),
    ]
    passed, failures = verify_file_modification(Path("ui/modules/data_center_view.py"), checks)
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 验证4：服务器池测速
    print("[4/6] 验证服务器池测速优化...")
    checks = [
        (r"# logger\.debug\(\.\.\.?\)  # 🔧 已移除", True, "测速debug已注释"),
        (r'logger\.debug\(f"服务器 \{ip\}:\{port\} \[', "0", "逐个服务器debug已移除"),
    ]
    passed, failures = verify_file_modification(
        Path("backend/infrastructure/tdx_asyncio/async_ip_pool.py"), checks
    )
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 验证5：看门狗日志
    print("[5/6] 验证看门狗日志精简...")
    checks = [
        (r"# logger\.info\(\.\.\.?\)  # 🔧 已精简", True, "看门狗日志已精简"),
    ]
    passed, failures = verify_file_modification(Path("start_async_fixed.py"), checks)
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 验证6：数据质量扫描
    print("[6/6] 验证数据质量扫描优化...")
    checks = [
        (r'"details_count": len\(outdated_details\)', True, "details改为count"),
        (r'# "details": outdated_details,  # 已移除', True, "完整details已移除"),
    ]
    passed, failures = verify_file_modification(
        Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py"), checks
    )
    if passed:
        print("  ✅ 通过")
    else:
        print("  ❌ 失败:")
        for f in failures:
            print(f"    {f}")
        all_pass = False
    print()

    # 总结
    print("=" * 70)
    if all_pass:
        print("✅ 所有验证通过！")
        print()
        print("📊 预期效果：")
        print("  - 正常运行：每分钟输出从180+条 → 2-3条（减少98%）")
        print("  - 数据下载：15000任务从150+条 → 0条（完全移除）")
        print("  - 服务器测速：650+条 → 1条统计（减少99.8%）")
        print("  - 质量扫描：5000+条 → 20条摘要（减少99.6%）")
        print()
        print("🎉 终端输出已优化，预计减少95%+")
    else:
        print("❌ 部分验证失败，请检查")

    print("=" * 70)
    print()
    print("📝 下一步：")
    print("1. 运行 `.\\启动终端（增强版）.bat` 测试")
    print("2. 观察终端输出是否明显减少")
    print("3. 检查 logs/terminal_v0.50.log 确认日志完整")
    print()

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())

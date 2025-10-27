# -*- coding: utf-8 -*-
"""
修复monitor_system.py的日志埋点

修复内容：
1. 自适应阈值学习日志（P1）
2. SMART检测告警（P1）
3. 异常处理完善（P1）
"""

import re
from pathlib import Path


def fix_threshold_learning_log(content: str) -> str:
    """修复自适应阈值学习日志"""

    # 在样本不足时添加日志
    pattern1 = r"(if sample_count < config\.min_samples:)"
    replacement1 = r"""\1
            logger.debug(
                "阈值学习: 指标=%s, 样本不足=%d/%d (使用默认阈值)",
                metric_name, sample_count, config.min_samples
            )"""
    content = re.sub(pattern1, replacement1, content, count=1)

    # 替换简单的阈值更新日志为详细日志
    old_log = r"""logger\.info\(
\s*".*\[%s\]: warning=%.2f, critical=%.2f.*",
\s*metric_name,
\s*warning_threshold or 0,
\s*critical_threshold or 0,
\s*sample_count,
\s*\)"""

    new_log = """# 详细的学习过程日志
        logger.info(
            "阈值学习完成: 指标=%s, 样本=%d, "
            "均值=%.2f, 标准差=%.2f, P95=%.2f, P99=%.2f, "
            "告警阈值=%.2f->%.2f, 严重阈值=%.2f->%.2f",
            metric_name,
            sample_count,
            mean,
            stddev,
            p95,
            p99,
            config.default_warning or 0,
            warning_threshold or 0,
            config.default_critical or 0,
            critical_threshold or 0,
        )"""

    content = re.sub(old_log, new_log, content, flags=re.MULTILINE)

    return content


def fix_smart_alerts(content: str) -> str:
    """添加SMART检测告警"""

    # 在get_smart_data方法中，smart_data添加到result后，添加健康评估
    pattern = r"(if smart_data:\s*\n\s*result\[disk_name\] = smart_data)"

    replacement = r"""\1

                        # 健康评估告警
                        if smart_data.assessment == "FAILING":
                            logger_alert.critical(
                                "硬盘即将故障: 硬盘=%s, 型号=%s, 序列号=%s",
                                smart_data.disk_name,
                                smart_data.model,
                                smart_data.serial,
                            )
                        elif smart_data.assessment == "WARNING":
                            logger_alert.warning(
                                "硬盘健康警告: 硬盘=%s, 重分配扇区=%s, 待处理扇区=%s",
                                smart_data.disk_name,
                                smart_data.reallocated_sectors or 0,
                                smart_data.pending_sectors or 0,
                            )

                        # 温度告警
                        if smart_data.temperature and smart_data.temperature > 60:
                            logger_alert.warning(
                                "硬盘温度过高: 硬盘=%s, 温度=%d°C",
                                smart_data.disk_name,
                                smart_data.temperature,
                            )"""

    content = re.sub(pattern, replacement, content, count=1)

    return content


def fix_exception_handling(content: str) -> str:
    """完善异常处理"""

    # 将简单的logger.error(..., e)改为logger.exception
    # 查找模式：except Exception as e: ... logger.error(..., e)
    pattern = r"(except Exception as \w+:[\s\S]*?)logger\.error\((.*?), (\w+)\)"

    def replace_with_exception(match):
        prefix = match.group(1)
        msg = match.group(2)
        var = match.group(3)
        # 只有在没有exc_info=True的情况下才替换
        if "exc_info=True" in match.group(0):
            return match.group(0)
        return f"{prefix}logger.exception({msg}, {var})"

    content = re.sub(pattern, replace_with_exception, content)

    return content


def main():
    """主函数"""
    monitor_file = Path("backend/infrastructure/system_vnpy/monitor_system.py")

    if not monitor_file.exists():
        print(f"❌ 文件不存在: {monitor_file}")
        return

    print(f"📖 读取文件: {monitor_file}")
    content = monitor_file.read_text(encoding="utf-8")

    print("🔧 应用修复...")

    # 应用所有修复
    content = fix_threshold_learning_log(content)
    print("   ✅ 修复自适应阈值学习日志")

    content = fix_smart_alerts(content)
    print("   ✅ 添加SMART检测告警")

    content = fix_exception_handling(content)
    print("   ✅ 完善异常处理")

    # 备份原文件
    backup_file = monitor_file.with_suffix(".py.backup")
    backup_file.write_text(monitor_file.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"💾 备份原文件: {backup_file}")

    # 写入修复后的文件
    monitor_file.write_text(content, encoding="utf-8")
    print(f"✅ 已写入修复后的文件")

    print("\n🎉 修复完成！")
    print("\n建议：")
    print(
        "1. 检查文件语法：python -m py_compile backend/infrastructure/system_vnpy/monitor_system.py"
    )
    print("2. 对比差异：git diff backend/infrastructure/system_vnpy/monitor_system.py")
    print(
        "3. 如有问题，恢复备份：mv backend/infrastructure/system_vnpy/monitor_system.py.backup backend/infrastructure/system_vnpy/monitor_system.py"
    )


if __name__ == "__main__":
    main()

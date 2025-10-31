# -*- coding: utf-8 -*-
"""
验证UI质量组件颜色反馈修复

检查：
1. 日志中是否有质量数据输出
2. 是否有组件样式设置日志
3. 扫描按钮是否被启用
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("verify_ui_feedback")


def verify_logs():
    """检查日志文件，确认UI组件更新和颜色反馈"""
    terminal_log = project_root / "logs" / "terminal.log"

    if not terminal_log.exists():
        logger.error("日志文件不存在: %s", terminal_log)
        return False

    # 读取最近1000行
    with open(terminal_log, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[-1000:]

    # 统计关键事件
    quality_data_log_count = 0
    ui_update_count = 0
    scan_btn_enabled_count = 0
    slot_calls = []

    for line in lines:
        if "📊 质量数据:" in line:
            quality_data_log_count += 1
            logger.info("✓ 找到质量数据日志: %s", line.strip()[-100:])
        if "[Slot] _update_quality_overview_ui 被调用" in line:
            ui_update_count += 1
            slot_calls.append(line.strip())
        if "数据扫描按钮已启用" in line:
            scan_btn_enabled_count += 1
            logger.info("✓ 找到扫描按钮启用日志: %s", line.strip())

    logger.info("\n" + "=" * 70)
    logger.info("验证结果:")
    logger.info("  - 质量数据日志: %d 条", quality_data_log_count)
    logger.info("  - UI更新Slot调用: %d 次", ui_update_count)
    logger.info("  - 扫描按钮启用: %d 次", scan_btn_enabled_count)
    logger.info("=" * 70)

    # 诊断
    success = True

    if quality_data_log_count == 0:
        logger.error("❌ 没有质量数据日志！组件可能没有收到数据")
        success = False
    else:
        logger.info("✅ 质量数据日志正常")

    if ui_update_count == 0:
        logger.error("❌ UI更新Slot未被调用！Signal/Slot机制可能失败")
        success = False
    else:
        logger.info("✅ UI更新Slot正常调用 (%d次)", ui_update_count)

    if scan_btn_enabled_count == 0:
        logger.warning("⚠️ 扫描按钮未启用！用户无法手动扫描")
        # 不算失败，因为可能还有其他启用路径
    else:
        logger.info("✅ 扫描按钮已启用")

    # 详细输出Slot调用
    if slot_calls:
        logger.info("\n" + "=" * 70)
        logger.info("Slot调用详情:")
        for call in slot_calls:
            logger.info("  %s", call[-120:])
        logger.info("=" * 70)

    return success


if __name__ == "__main__":
    logger.info("开始验证UI质量组件颜色反馈修复...")
    logger.info("=" * 70)

    success = verify_logs()

    if success:
        logger.info("\n✅ 验证通过：UI质量组件更新正常")
        logger.info("\n请在UI中确认：")
        logger.info("  1. 所有质量指标都有颜色（0=绿色，>0=橙/红色）")
        logger.info("  2. 扫描按钮可以点击（非灰色）")
        logger.info("  3. 状态指示器显示为✅（非🔄）")
        sys.exit(0)
    else:
        logger.error("\n❌ 验证失败：UI质量组件更新存在问题")
        logger.error("\n请检查：")
        logger.error("  1. Signal/Slot连接是否正确")
        logger.error("  2. 后端是否推送了质量事件")
        logger.error("  3. UI组件是否正确初始化")
        sys.exit(1)

# -*- coding: utf-8 -*-
"""
UI交互功能回路测试运行脚本.

执行完整的UI测试套件，并生成HTML报告。
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def run_tests():
    """运行UI测试套件."""
    logger.info("=" * 80)
    logger.info("开始执行UI交互功能回路测试")
    logger.info("测试范围: 43个功能链路，6个功能界面")
    logger.info("=" * 80)

    # 确保报告目录存在
    reports_dir = project_root / "tests" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 构建pytest命令
    pytest_cmd = [
        "pytest",
        "tests/test_ui_integration",
        "-v",
        "--tb=short",
        "--html=tests/reports/test_results.html",
        "--self-contained-html",
        "-m",
        "ui",
        "--maxfail=5",
    ]

    logger.info(f"执行命令: {' '.join(pytest_cmd)}")

    try:
        # 运行pytest
        result = subprocess.run(
            pytest_cmd, cwd=str(project_root), capture_output=False, text=True
        )

        logger.info("=" * 80)
        if result.returncode == 0:
            logger.info("✅ 所有测试通过!")
        else:
            logger.warning(f"⚠️ 测试完成，退出码: {result.returncode}")

        logger.info(f"测试报告已生成: tests/reports/test_results.html")
        logger.info("=" * 80)

        return result.returncode

    except FileNotFoundError:
        logger.error("pytest未安装或未找到")
        logger.error("请运行: pip install -r tests/requirements-test.txt")
        return 1
    except Exception as e:
        logger.error(f"测试执行失败: {e}")
        return 1


def main():
    """主函数."""
    exit_code = run_tests()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

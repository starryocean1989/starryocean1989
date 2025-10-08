# -*- coding: utf-8 -*-
"""
E2E测试运行脚本.

提供便捷的E2E测试执行入口，支持多种运行模式。
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)


def run_e2e_tests(
    verbose: bool = True,
    html_report: bool = False,
    test_file: str = None,
    timeout: int = 120,
) -> int:
    """
    运行E2E测试.

    Args:
        verbose: 是否输出详细信息
        html_report: 是否生成HTML报告
        test_file: 指定测试文件（可选）
        timeout: 测试超时时间（秒）

    Returns:
        退出代码（0表示成功）
    """
    try:
        import pytest
    except ImportError:
        print("错误：pytest未安装，请先运行：pip install -r tests/requirements-test.txt")
        return 1

    # 构建pytest参数
    args = []

    # 测试目录或文件
    if test_file:
        test_path = Path("tests/test_e2e") / test_file
        args.append(str(test_path))
    else:
        args.append("tests/test_e2e")

    # 详细输出
    if verbose:
        args.extend(["-v", "-s"])

    # 超时设置
    args.append(f"--timeout={timeout}")

    # 显示详细错误信息
    args.append("--tb=short")

    # 显示测试摘要
    args.append("-ra")

    # 标记过滤（只运行e2e测试）
    args.extend(["-m", "e2e"])

    # HTML报告
    if html_report:
        report_path = Path("tests/reports/e2e_results.html")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        args.extend(["--html=" + str(report_path), "--self-contained-html"])

    # 添加日志级别
    args.extend(["--log-cli-level=INFO"])

    print("=" * 80)
    print("E2E端到端集成测试")
    print("=" * 80)
    print(f"测试路径: {args[0]}")
    print(f"超时设置: {timeout}秒")
    print(f"详细输出: {verbose}")
    print(f"HTML报告: {html_report}")
    print("=" * 80)
    print()

    # 运行pytest
    exit_code = pytest.main(args)

    print()
    print("=" * 80)
    if exit_code == 0:
        print("✅ E2E测试全部通过!")
    else:
        print(f"❌ E2E测试失败，退出代码: {exit_code}")

    if html_report:
        print(f"📊 HTML报告已生成: {report_path}")

    print("=" * 80)

    return exit_code


def main():
    """主函数."""
    parser = argparse.ArgumentParser(
        description="运行E2E端到端集成测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 运行所有E2E测试
  python tests/run_e2e_tests.py

  # 运行特定测试文件
  python tests/run_e2e_tests.py --file test_e2e_symbol_cache.py

  # 生成HTML报告
  python tests/run_e2e_tests.py --html

  # 简洁输出模式
  python tests/run_e2e_tests.py --quiet

  # 增加超时时间
  python tests/run_e2e_tests.py --timeout 180
        """,
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        help="指定要运行的测试文件名（例如: test_e2e_symbol_cache.py）",
    )

    parser.add_argument(
        "--html",
        action="store_true",
        help="生成HTML测试报告",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="简洁输出模式（不显示详细信息）",
    )

    parser.add_argument(
        "--timeout",
        "-t",
        type=int,
        default=120,
        help="测试超时时间（秒），默认120秒",
    )

    args = parser.parse_args()

    # 运行测试
    exit_code = run_e2e_tests(
        verbose=not args.quiet,
        html_report=args.html,
        test_file=args.file,
        timeout=args.timeout,
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()

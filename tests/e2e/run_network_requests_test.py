# -*- coding: utf-8 -*-
"""网络请求E2E测试独立运行脚本.

提供命令行接口，支持多种测试场景和参数组合。

使用示例：
    # 测试所有场景
    python tests/e2e/run_network_requests_test.py --scenario all

    # 测试交易日历的所有场景
    python tests/e2e/run_network_requests_test.py --request-type calendar --scenario all

    # 测试完整启动流程（缓存不存在）
    python tests/e2e/run_network_requests_test.py --full-startup --scenario missing

    # 详细输出
    python tests/e2e/run_network_requests_test.py --verbose
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到sys.path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest


def parse_args():
    """解析命令行参数."""
    parser = argparse.ArgumentParser(
        description="网络请求E2E测试运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  %(prog)s --scenario all
  %(prog)s --request-type calendar --scenario all
  %(prog)s --full-startup --scenario missing
  %(prog)s --verbose
        """,
    )

    parser.add_argument(
        "--scenario",
        choices=["missing", "expired", "valid", "corrupted", "all"],
        default="all",
        help="测试场景（默认：all）",
    )

    parser.add_argument(
        "--request-type",
        choices=["calendar", "server", "symbol", "ipo", "kline", "all"],
        default="all",
        help="请求类型（默认：all）",
    )

    parser.add_argument("--full-startup", action="store_true", help="测试完整启动流程")

    parser.add_argument("--performance", action="store_true", help="运行性能对比测试")

    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")

    parser.add_argument("--report", type=str, help="生成测试报告（指定输出文件路径）")

    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")

    return parser.parse_args()


def build_pytest_args(args):
    """根据命令行参数构建pytest参数."""
    pytest_args = ["-v"]

    # 详细输出
    if args.verbose:
        pytest_args.append("-s")

    # 测试文件路径
    test_file = project_root / "tests" / "e2e" / "test_network_requests_e2e.py"

    # 根据请求类型和场景构建测试用例过滤
    test_filters = []

    if args.full_startup:
        # 完整启动流程测试
        test_filters.append("test_full_startup_flow")
    elif args.performance:
        # 性能对比测试
        test_filters.append("test_performance")
    else:
        # 按请求类型过滤
        if args.request_type != "all":
            type_map = {
                "calendar": "trading_calendar",
                "server": "server_pool",
                "symbol": "symbol_list",
                "ipo": "ipo_date",
                "kline": "kline_download",
            }
            test_filters.append(type_map[args.request_type])

        # 按场景过滤
        if args.scenario != "all":
            test_filters.append(f"cache_{args.scenario}")

    # 构建-k参数（用于pytest的测试过滤）
    if test_filters:
        filter_expr = " and ".join(test_filters)
        pytest_args.extend(["-k", filter_expr])

    # 添加测试文件
    pytest_args.append(str(test_file))

    # JSON报告
    if args.report:
        pytest_args.append(f"--json-report")
        pytest_args.append(f"--json-report-file={args.report}")

    return pytest_args


def print_header():
    """打印测试头部信息."""
    print("=" * 80)
    print("网络请求E2E测试套件".center(80))
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()


def print_summary(exit_code, elapsed_time):
    """打印测试总结."""
    print()
    print("=" * 80)
    print("测试完成".center(80))
    print("=" * 80)
    status = "✅ 通过" if exit_code == 0 else "❌ 失败"
    print(f"测试结果: {status}")
    print(f"总耗时: {elapsed_time:.2f}秒")
    print("=" * 80)


def generate_markdown_report(json_report_path):
    """从JSON报告生成Markdown报告.

    Args:
        json_report_path: JSON报告文件路径
    """
    try:
        with open(json_report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        # 生成Markdown报告
        md_report_path = json_report_path.replace(".json", ".md")

        with open(md_report_path, "w", encoding="utf-8") as f:
            f.write("# 网络请求E2E测试报告\n\n")
            f.write(f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 测试概览
            summary = report_data.get("summary", {})
            f.write("## 测试概览\n\n")
            f.write(f"- 总用例数: {summary.get('total', 0)}\n")
            f.write(f"- 通过: {summary.get('passed', 0)}\n")
            f.write(f"- 失败: {summary.get('failed', 0)}\n")
            f.write(f"- 跳过: {summary.get('skipped', 0)}\n")
            f.write(f"- 总耗时: {summary.get('duration', 0):.2f}秒\n\n")

            # 通过率
            total = summary.get("total", 1)
            passed = summary.get("passed", 0)
            pass_rate = (passed / total * 100) if total > 0 else 0
            f.write(f"**通过率**: {pass_rate:.1f}%\n\n")

            # 测试用例详情
            f.write("## 测试用例详情\n\n")
            tests = report_data.get("tests", [])
            for test in tests:
                name = test.get("nodeid", "").split("::")[-1]
                outcome = test.get("outcome", "unknown")
                duration = test.get("duration", 0)

                status_icon = "✅" if outcome == "passed" else "❌" if outcome == "failed" else "⏭️"
                f.write(f"### {status_icon} {name}\n\n")
                f.write(f"- 状态: {outcome}\n")
                f.write(f"- 耗时: {duration:.2f}秒\n\n")

                # 如果失败，显示错误信息
                if outcome == "failed":
                    call = test.get("call", {})
                    longrepr = call.get("longrepr", "")
                    if longrepr:
                        f.write("**错误信息**:\n```\n")
                        f.write(longrepr)
                        f.write("\n```\n\n")

        print(f"\n✅ Markdown报告已生成: {md_report_path}")

    except Exception as e:
        print(f"\n⚠️ 生成Markdown报告失败: {e}")


def main():
    """主函数."""
    args = parse_args()

    # 打印头部
    if not args.no_color:
        print_header()

    # 构建pytest参数
    pytest_args = build_pytest_args(args)

    print(f"执行命令: pytest {' '.join(pytest_args)}")
    print()

    # 运行pytest
    start_time = time.time()
    exit_code = pytest.main(pytest_args)
    elapsed_time = time.time() - start_time

    # 打印总结
    if not args.no_color:
        print_summary(exit_code, elapsed_time)

    # 生成Markdown报告
    if args.report:
        generate_markdown_report(args.report)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())


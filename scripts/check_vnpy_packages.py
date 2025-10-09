# -*- coding: utf-8 -*-
"""
VNPY扩展包检查脚本

检查所有vnpy扩展包的安装状态，生成详细报告。
"""

import sys
from importlib import import_module
from typing import Dict, List, Tuple


# VNPY扩展包定义
VNPY_PACKAGES = {
    "核心包": {
        "vnpy": {
            "name": "VNPY核心框架",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy.git",
        },
    },
    "数据库": {
        "vnpy_sqlite": {
            "name": "SQLite数据库",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_sqlite.git",
        },
    },
    "策略引擎": {
        "vnpy_ctastrategy": {
            "name": "CTA策略引擎",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_ctastrategy.git",
        },
        "vnpy_ctabacktester": {
            "name": "CTA回测引擎",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_ctabacktester.git",
        },
        "vnpy_portfoliostrategy": {
            "name": "组合策略引擎",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_portfoliostrategy.git",
        },
        "vnpy_algotrading": {
            "name": "算法交易引擎",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_algotrading.git",
        },
        "vnpy_spreadtrading": {
            "name": "价差交易引擎",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_spreadtrading.git",
        },
        "vnpy_optionmaster": {
            "name": "期权策略引擎",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_optionmaster.git",
        },
        "vnpy_scripttrader": {
            "name": "脚本交易引擎",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_scripttrader.git",
        },
    },
    "交易网关": {
        "vnpy_ctp": {
            "name": "CTP期货网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_ctp.git",
        },
        "vnpy_ctptest": {
            "name": "CTP测试网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_ctptest.git",
        },
        "vnpy_mini": {
            "name": "CTP Mini网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_mini.git",
        },
        "vnpy_sopt": {
            "name": "期权网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_sopt.git",
        },
        "vnpy_tts": {
            "name": "仿真交易网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_tts.git",
        },
        "vnpy_paperaccount": {
            "name": "模拟交易网关",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_paperaccount.git",
        },
        "vnpy_ib": {
            "name": "IB网关",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_ib.git",
        },
    },
    "数据服务": {
        "vnpy_datarecorder": {
            "name": "数据录制服务",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_datarecorder.git",
        },
        "vnpy_riskmanager": {
            "name": "风险管理服务",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_riskmanager.git",
        },
    },
    "数据源": {
        "vnpy_tushare": {
            "name": "Tushare数据源",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_tushare.git",
        },
        "vnpy_rqdata": {
            "name": "RQData数据源",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_rqdata.git",
        },
        "vnpy_ifind": {
            "name": "iFind数据源",
            "required": False,
            "git_url": "https://github.com/vnpy/vnpy_ifind.git",
        },
    },
    "图表可视化": {
        "vnpy_chartwizard": {
            "name": "图表可视化",
            "required": True,
            "git_url": "https://github.com/vnpy/vnpy_chartwizard.git",
        },
    },
}


def check_package(package_name: str) -> Tuple[bool, str]:
    """检查单个包是否已安装.

    Args:
        package_name: 包名

    Returns:
        (是否安装, 版本信息)
    """
    try:
        module = import_module(package_name)
        version = getattr(module, "__version__", "未知版本")
        return True, version
    except ImportError:
        return False, ""


def generate_report() -> Dict:
    """生成检查报告.

    Returns:
        检查报告字典
    """
    report = {
        "total": 0,
        "installed": 0,
        "missing": 0,
        "required_missing": 0,
        "categories": {},
    }

    for category, packages in VNPY_PACKAGES.items():
        category_report = {"packages": []}

        for package_name, package_info in packages.items():
            is_installed, version = check_package(package_name)

            package_status = {
                "name": package_name,
                "display_name": package_info["name"],
                "installed": is_installed,
                "version": version,
                "required": package_info["required"],
                "git_url": package_info["git_url"],
            }

            category_report["packages"].append(package_status)

            report["total"] += 1
            if is_installed:
                report["installed"] += 1
            else:
                report["missing"] += 1
                if package_info["required"]:
                    report["required_missing"] += 1

        report["categories"][category] = category_report

    return report


def print_report(report: Dict):
    """打印检查报告.

    Args:
        report: 检查报告
    """
    print("=" * 80)
    print("VNPY扩展包安装状态检查报告")
    print("=" * 80)
    print()

    # 总览
    print(f"📊 总览:")
    print(f"   - 总包数: {report['total']}")
    print(f"   - 已安装: {report['installed']} ✅")
    print(f"   - 未安装: {report['missing']} ⚠️")
    print(f"   - 必需但未安装: {report['required_missing']} ❌")
    print()

    # 分类详情
    for category, data in report["categories"].items():
        print(f"📦 {category}")
        print("-" * 80)

        for package in data["packages"]:
            status = "✅" if package["installed"] else "❌"
            required = "[必需]" if package["required"] else "[可选]"

            if package["installed"]:
                print(
                    f"   {status} {package['display_name']:20s} {required:6s} "
                    f"(版本: {package['version']})"
                )
            else:
                print(f"   {status} {package['display_name']:20s} {required:6s} " f"(未安装)")

        print()

    # 安装建议
    if report["missing"] > 0:
        print("=" * 80)
        print("📝 安装建议")
        print("=" * 80)
        print()

        if report["required_missing"] > 0:
            print("⚠️  以下必需包未安装，请优先安装：")
            print()

            for category, data in report["categories"].items():
                required_missing = [
                    p for p in data["packages"] if p["required"] and not p["installed"]
                ]

                if required_missing:
                    print(f"   {category}:")
                    for package in required_missing:
                        print(f"      pip install git+{package['git_url']}")
                    print()

        optional_missing = []
        for category, data in report["categories"].items():
            for package in data["packages"]:
                if not package["required"] and not package["installed"]:
                    optional_missing.append(package)

        if optional_missing:
            print("💡 以下可选包未安装，根据需要安装：")
            print()
            for package in optional_missing:
                print(f"      pip install git+{package['git_url']}")
            print()

        print("或使用一键安装脚本：")
        print("   python scripts/install_vnpy_packages.py --essential  # 安装必需包")
        print("   python scripts/install_vnpy_packages.py --all        # 安装全部包")
        print()


def main():
    """主函数."""
    print("正在检查VNPY扩展包安装状态...\n")

    report = generate_report()
    print_report(report)

    # 返回退出码
    if report["required_missing"] > 0:
        print("❌ 有必需的包未安装，请先安装后再启动系统。")
        sys.exit(1)
    elif report["missing"] > 0:
        print("⚠️  有可选的包未安装，部分功能可能不可用。")
        sys.exit(0)
    else:
        print("✅ 所有包已正确安装！")
        sys.exit(0)


if __name__ == "__main__":
    main()

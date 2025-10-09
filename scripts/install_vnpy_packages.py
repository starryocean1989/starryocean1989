# -*- coding: utf-8 -*-
"""
VNPY扩展包一键安装脚本

支持按类别安装vnpy扩展包，使用git安装。
"""

import argparse
import subprocess
import sys
from typing import List, Dict


# VNPY扩展包定义（与check_vnpy_packages.py保持一致）
VNPY_PACKAGES = {
    "核心包": {
        "vnpy_sqlite": {
            "name": "SQLite数据库",
            "git_url": "https://github.com/vnpy/vnpy_sqlite.git",
        },
    },
    "策略引擎": {
        "vnpy_ctastrategy": {
            "name": "CTA策略引擎",
            "git_url": "https://github.com/vnpy/vnpy_ctastrategy.git",
        },
        "vnpy_ctabacktester": {
            "name": "CTA回测引擎",
            "git_url": "https://github.com/vnpy/vnpy_ctabacktester.git",
        },
        "vnpy_portfoliostrategy": {
            "name": "组合策略引擎",
            "git_url": "https://github.com/vnpy/vnpy_portfoliostrategy.git",
        },
        "vnpy_algotrading": {
            "name": "算法交易引擎",
            "git_url": "https://github.com/vnpy/vnpy_algotrading.git",
        },
        "vnpy_spreadtrading": {
            "name": "价差交易引擎",
            "git_url": "https://github.com/vnpy/vnpy_spreadtrading.git",
        },
        "vnpy_optionmaster": {
            "name": "期权策略引擎",
            "git_url": "https://github.com/vnpy/vnpy_optionmaster.git",
        },
        "vnpy_scripttrader": {
            "name": "脚本交易引擎",
            "git_url": "https://github.com/vnpy/vnpy_scripttrader.git",
        },
    },
    "交易网关": {
        "vnpy_ctp": {
            "name": "CTP期货网关",
            "git_url": "https://github.com/vnpy/vnpy_ctp.git",
        },
        "vnpy_ctptest": {
            "name": "CTP测试网关",
            "git_url": "https://github.com/vnpy/vnpy_ctptest.git",
        },
        "vnpy_mini": {
            "name": "CTP Mini网关",
            "git_url": "https://github.com/vnpy/vnpy_mini.git",
        },
        "vnpy_sopt": {
            "name": "期权网关",
            "git_url": "https://github.com/vnpy/vnpy_sopt.git",
        },
        "vnpy_tts": {
            "name": "仿真交易网关",
            "git_url": "https://github.com/vnpy/vnpy_tts.git",
        },
        "vnpy_paperaccount": {
            "name": "模拟交易网关",
            "git_url": "https://github.com/vnpy/vnpy_paperaccount.git",
        },
        "vnpy_ib": {
            "name": "IB网关",
            "git_url": "https://github.com/vnpy/vnpy_ib.git",
        },
    },
    "数据服务": {
        "vnpy_datarecorder": {
            "name": "数据录制服务",
            "git_url": "https://github.com/vnpy/vnpy_datarecorder.git",
        },
        "vnpy_riskmanager": {
            "name": "风险管理服务",
            "git_url": "https://github.com/vnpy/vnpy_riskmanager.git",
        },
    },
    "数据源": {
        "vnpy_tushare": {
            "name": "Tushare数据源",
            "git_url": "https://github.com/vnpy/vnpy_tushare.git",
        },
        "vnpy_rqdata": {
            "name": "RQData数据源",
            "git_url": "https://github.com/vnpy/vnpy_rqdata.git",
        },
        "vnpy_ifind": {
            "name": "iFind数据源",
            "git_url": "https://github.com/vnpy/vnpy_ifind.git",
        },
    },
    "图表可视化": {
        "vnpy_chartwizard": {
            "name": "图表可视化",
            "git_url": "https://github.com/vnpy/vnpy_chartwizard.git",
        },
    },
}

# 必需包列表
ESSENTIAL_PACKAGES = [
    "vnpy_sqlite",
    "vnpy_ctastrategy",
    "vnpy_ctabacktester",
    "vnpy_paperaccount",
    "vnpy_datarecorder",
    "vnpy_riskmanager",
    "vnpy_chartwizard",
]


def install_package(git_url: str, package_name: str) -> bool:
    """安装单个包.

    Args:
        git_url: Git仓库URL
        package_name: 包名

    Returns:
        是否安装成功
    """
    try:
        print(f"正在安装 {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", f"git+{git_url}"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print(f"✅ {package_name} 安装成功")
            return True
        else:
            print(f"❌ {package_name} 安装失败")
            print(f"   错误信息: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ {package_name} 安装失败: {str(e)}")
        return False


def get_packages_to_install(categories: List[str], essential_only: bool) -> Dict:
    """获取要安装的包列表.

    Args:
        categories: 要安装的类别列表
        essential_only: 是否只安装必需包

    Returns:
        包字典
    """
    packages_to_install = {}

    for category, packages in VNPY_PACKAGES.items():
        if categories and category not in categories:
            continue

        for package_name, package_info in packages.items():
            if essential_only and package_name not in ESSENTIAL_PACKAGES:
                continue

            packages_to_install[package_name] = package_info

    return packages_to_install


def main():
    """主函数."""
    parser = argparse.ArgumentParser(description="VNPY扩展包一键安装脚本")
    parser.add_argument(
        "--essential",
        action="store_true",
        help="只安装必需包",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="安装所有包",
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=list(VNPY_PACKAGES.keys()),
        help="按类别安装",
    )
    parser.add_argument(
        "--packages",
        type=str,
        nargs="+",
        help="指定要安装的包名列表",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("VNPY扩展包安装脚本")
    print("=" * 80)
    print()

    # 确定要安装的包
    packages_to_install = {}

    if args.packages:
        # 安装指定包
        for package_name in args.packages:
            found = False
            for category, packages in VNPY_PACKAGES.items():
                if package_name in packages:
                    packages_to_install[package_name] = packages[package_name]
                    found = True
                    break
            if not found:
                print(f"⚠️  未找到包: {package_name}")

    elif args.essential:
        # 安装必需包
        packages_to_install = get_packages_to_install([], essential_only=True)
        print("📦 安装必需包...")

    elif args.all:
        # 安装所有包
        packages_to_install = get_packages_to_install([], essential_only=False)
        print("📦 安装所有包...")

    elif args.category:
        # 按类别安装
        packages_to_install = get_packages_to_install([args.category], essential_only=False)
        print(f"📦 安装类别: {args.category}")

    else:
        # 默认安装必需包
        packages_to_install = get_packages_to_install([], essential_only=True)
        print("📦 安装必需包（默认）...")
        print("   使用 --all 安装所有包，或使用 --help 查看更多选项")

    if not packages_to_install:
        print("❌ 没有需要安装的包")
        sys.exit(1)

    print()
    print(f"将安装 {len(packages_to_install)} 个包:")
    for package_name, package_info in packages_to_install.items():
        print(f"   - {package_info['name']} ({package_name})")
    print()

    # 询问确认
    confirm = input("是否继续安装？[y/N] ")
    if confirm.lower() not in ["y", "yes"]:
        print("❌ 安装已取消")
        sys.exit(0)

    print()
    print("=" * 80)
    print("开始安装...")
    print("=" * 80)
    print()

    # 安装包
    success_count = 0
    failed_count = 0

    for package_name, package_info in packages_to_install.items():
        if install_package(package_info["git_url"], package_name):
            success_count += 1
        else:
            failed_count += 1
        print()

    # 总结
    print("=" * 80)
    print("安装完成")
    print("=" * 80)
    print(f"✅ 成功: {success_count}")
    print(f"❌ 失败: {failed_count}")
    print()

    if failed_count > 0:
        print("⚠️  部分包安装失败，请检查错误信息")
        sys.exit(1)
    else:
        print("🎉 所有包安装成功！")
        print()
        print("运行以下命令验证安装:")
        print("   python scripts/check_vnpy_packages.py")
        sys.exit(0)


if __name__ == "__main__":
    main()

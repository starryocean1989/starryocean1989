# -*- coding: utf-8 -*-
"""
安装缺失的vnpy策略扩展包.

根据用户选择安装未安装的策略引擎包。
"""

import subprocess
import sys
from pathlib import Path

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / "venv310" / "Scripts" / "python.exe"

# 策略包列表
STRATEGY_PACKAGES = {
    "1": {
        "name": "CTA策略",
        "package": "vnpy_ctastrategy",
        "description": "趋势跟踪策略引擎",
        "status": "✅ 已安装",
    },
    "2": {
        "name": "算法交易",
        "package": "vnpy_algotrading",
        "description": "TWAP、VWAP等算法交易",
        "status": "❌ 未安装",
    },
    "3": {
        "name": "期权策略",
        "package": "vnpy_optionmaster",
        "description": "期权定价和交易策略",
        "status": "❌ 未安装",
    },
    "4": {
        "name": "组合策略",
        "package": "vnpy_portfoliostrategy",
        "description": "多品种组合策略引擎",
        "status": "❌ 未安装",
    },
    "5": {
        "name": "脚本交易",
        "package": "vnpy_scripttrader",
        "description": "Python脚本交易引擎",
        "status": "❌ 未安装",
    },
    "6": {
        "name": "价差交易",
        "package": "vnpy_spreadtrading",
        "description": "跨期套利、跨品种套利",
        "status": "✅ 已安装",
    },
}


def print_header():
    """打印头部."""
    print("=" * 60)
    print("VnPy策略扩展包安装工具")
    print("=" * 60)
    print()


def print_packages():
    """打印策略包列表."""
    print("当前策略包状态：")
    print()
    for key, info in STRATEGY_PACKAGES.items():
        print(f"  {key}. {info['status']} {info['name']}")
        print(f"     包名: {info['package']}")
        print(f"     说明: {info['description']}")
        print()


def install_package(package_name: str) -> bool:
    """安装指定的包.

    Args:
        package_name: 包名

    Returns:
        bool: 是否成功
    """
    try:
        print(f"正在安装 {package_name}...")
        print("-" * 60)

        # 使用虚拟环境的pip安装
        result = subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print(f"✅ {package_name} 安装成功！")
            return True
        else:
            print(f"❌ {package_name} 安装失败")
            print("错误信息：")
            print(result.stderr)
            return False

    except Exception as e:
        print(f"❌ 安装过程出错: {e}")
        return False


def main():
    """主函数."""
    print_header()
    print_packages()

    print("=" * 60)
    print("安装选项：")
    print()
    print("  输入包编号（如 2）：安装单个包")
    print("  输入多个编号（如 2,4,5）：批量安装")
    print("  输入 all：安装所有未安装的包")
    print("  输入 q：退出")
    print()
    print("=" * 60)

    choice = input("请选择要安装的包: ").strip().lower()

    if choice == "q":
        print("退出安装程序")
        return

    # 解析选择
    to_install = []

    if choice == "all":
        # 安装所有未安装的包
        for key, info in STRATEGY_PACKAGES.items():
            if "未安装" in info["status"]:
                to_install.append((key, info))
    else:
        # 安装指定的包
        selected_keys = [k.strip() for k in choice.split(",")]
        for key in selected_keys:
            if key in STRATEGY_PACKAGES:
                info = STRATEGY_PACKAGES[key]
                if "未安装" in info["status"]:
                    to_install.append((key, info))
                else:
                    print(f"⚠️  {info['name']} 已经安装，跳过")
            else:
                print(f"⚠️  无效的编号: {key}")

    if not to_install:
        print()
        print("没有需要安装的包")
        return

    # 确认安装
    print()
    print(f"将要安装以下 {len(to_install)} 个包：")
    for key, info in to_install:
        print(f"  • {info['name']} ({info['package']})")
    print()

    confirm = input("确认安装？(y/n): ").strip().lower()
    if confirm != "y":
        print("取消安装")
        return

    # 开始安装
    print()
    print("=" * 60)
    print("开始安装...")
    print("=" * 60)
    print()

    success_count = 0
    failed_packages = []

    for key, info in to_install:
        package_name = info["package"]
        if install_package(package_name):
            success_count += 1
        else:
            failed_packages.append(info["name"])
        print()

    # 安装总结
    print("=" * 60)
    print("安装完成")
    print("=" * 60)
    print()
    print(f"成功安装: {success_count} 个")
    if failed_packages:
        print(f"安装失败: {len(failed_packages)} 个")
        print("失败的包：")
        for name in failed_packages:
            print(f"  • {name}")
    print()

    if success_count > 0:
        print("💡 提示：")
        print("  安装完成后，请重启交易终端以使用新安装的策略引擎")
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户取消安装")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n程序错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

# -*- coding: utf-8 -*-
"""
系统健康检查脚本

运行此脚本验证所有修复是否生效。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def print_section(title):
    """打印章节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def check_python_env():
    """检查Python环境"""
    print_section("1. Python环境检查")

    print(f"✅ Python版本: {sys.version}")
    print(f"✅ Python路径: {sys.executable}")

    # 检查虚拟环境
    venv_path = project_root / "venv310"
    if venv_path.exists():
        print(f"✅ 虚拟环境: {venv_path}")
    else:
        print(f"⚠️  虚拟环境不存在: {venv_path}")

def check_core_packages():
    """检查核心包"""
    print_section("2. 核心依赖包检查")

    packages = [
        ("pydantic", "2.12.2"),
        ("pydantic_core", "2.41.4"),
        ("aiofiles", None),
    ]

    for package_name, expected_version in packages:
        try:
            module = __import__(package_name)
            version = getattr(module, "__version__", "未知版本")
            status = "✅"
            if expected_version and version != expected_version:
                status = f"⚠️  (预期: {expected_version})"
            print(f"{status} {package_name}: {version}")
        except ImportError:
            print(f"❌ {package_name}: 未安装")

def check_vnpy_packages():
    """检查vnpy扩展包"""
    print_section("3. VnPy扩展包检查")

    vnpy_packages = {
        "vnpy_sqlite": "SQLite数据库驱动",
        "vnpy_chartwizard": "图表可视化",
        "vnpy_riskmanager": "风险管理",
        "vnpy_ctastrategy": "CTA策略引擎",
        "vnpy_algotrading": "算法交易引擎",
        "vnpy_optionmaster": "期权策略引擎",
        "vnpy_portfoliostrategy": "组合策略引擎",
        "vnpy_spreadtrading": "价差交易引擎",
    }

    installed_count = 0
    for package_name, description in vnpy_packages.items():
        try:
            module = __import__(package_name)
            version = getattr(module, "__version__", "未知版本")
            print(f"✅ {package_name} {version} - {description}")
            installed_count += 1
        except ImportError:
            print(f"❌ {package_name} - {description}")

    print(f"\n已安装: {installed_count}/{len(vnpy_packages)}")

def check_project_structure():
    """检查项目结构"""
    print_section("4. 项目结构检查")

    required_paths = [
        ("backend", "后端代码目录"),
        ("ui", "前端UI目录"),
        ("config/terminal_config.json", "配置文件"),
        ("data/terminal.db", "数据库文件"),
        ("strategies/user_strategies", "用户策略目录"),
        ("start_async_fixed.py", "启动脚本"),
    ]

    for path_str, description in required_paths:
        path = project_root / path_str
        if path.exists():
            print(f"✅ {path_str} - {description}")
        else:
            print(f"❌ {path_str} - {description}")

def check_strategy_files():
    """检查策略文件"""
    print_section("5. 策略文件检查")

    strategy_dir = project_root / "strategies" / "user_strategies"
    if not strategy_dir.exists():
        print("❌ 策略目录不存在")
        return

    # 递归查找所有.py文件
    strategy_files = list(strategy_dir.rglob("*.py"))
    strategy_files = [f for f in strategy_files if not f.name.startswith("__")]

    if strategy_files:
        print(f"✅ 找到 {len(strategy_files)} 个策略文件:")
        for f in strategy_files[:5]:  # 只显示前5个
            rel_path = f.relative_to(strategy_dir)
            print(f"   - {rel_path}")
        if len(strategy_files) > 5:
            print(f"   ... 还有 {len(strategy_files) - 5} 个文件")
    else:
        print("⚠️  未找到策略文件")

def check_database():
    """检查数据库"""
    print_section("6. 数据库检查")

    try:
        import sqlite3
        db_path = project_root / "data" / "terminal.db"

        if not db_path.exists():
            print("⚠️  数据库文件不存在")
            return

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 检查backtest_tasks表结构
        cursor.execute("PRAGMA table_info(backtest_tasks)")
        columns = [row[1] for row in cursor.fetchall()]

        required_columns = ["id", "strategy_id", "parameters", "status", "progress", "created_at"]
        missing_columns = [col for col in required_columns if col not in columns]

        if missing_columns:
            print(f"⚠️  backtest_tasks表缺少列: {missing_columns}")
        else:
            print("✅ backtest_tasks表结构正确")
            print(f"   列: {', '.join(columns)}")

        conn.close()
    except Exception as e:
        print(f"❌ 数据库检查失败: {e}")

def check_imports():
    """检查关键模块导入"""
    print_section("7. 关键模块导入检查")

    modules = [
        "backend.core.base",
        "backend.services.data_center_service",
        "backend.services.strategy_center_service",
        "ui.main_window",
    ]

    for module_name in modules:
        try:
            __import__(module_name)
            print(f"✅ {module_name}")
        except Exception as e:
            print(f"❌ {module_name}: {str(e)[:50]}...")

def main():
    """主函数"""
    print("\n" + "🔍 星辰金融终端 - 系统健康检查".center(70, "="))
    print(f"项目根目录: {project_root}\n")

    try:
        check_python_env()
        check_core_packages()
        check_vnpy_packages()
        check_project_structure()
        check_strategy_files()
        check_database()
        check_imports()

        print_section("检查完成")
        print("\n✅ 如果上述检查全部通过，系统应该可以正常启动。")
        print("🚀 运行以下命令启动系统:")
        print("   启动终端（增强版）.bat")
        print("   或")
        print(f"   {sys.executable} start_async_fixed.py")
        print()

    except Exception as e:
        print(f"\n❌ 检查过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())


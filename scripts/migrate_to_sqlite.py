# -*- coding: utf-8 -*-
"""
数据迁移脚本

将现有的JSON配置和数据迁移到SQLite数据库。
保留历史K线数据在Parquet格式。
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.core.sqlite_manager import get_sqlite_manager


def migrate_config_file(config_file: Path, module_name: str, sqlite_manager):
    """迁移配置文件.

    Args:
        config_file: 配置文件路径
        module_name: 模块名称
        sqlite_manager: SQLite管理器
    """
    if not config_file.exists():
        print(f"⚠️  配置文件不存在: {config_file}")
        return

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 递归保存配置
        def save_config_recursive(data, prefix=""):
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key

                if isinstance(value, dict):
                    # 嵌套字典，递归处理
                    save_config_recursive(value, full_key)
                else:
                    # 转换为字符串保存
                    value_str = json.dumps(value, ensure_ascii=False)
                    sqlite_manager.save_config(
                        module=module_name,
                        key=full_key,
                        value=value_str,
                        description=f"从 {config_file.name} 迁移",
                    )

        save_config_recursive(config_data)
        print(f"✅ 配置迁移成功: {config_file.name} -> {module_name}")

    except Exception as e:
        print(f"❌ 配置迁移失败: {config_file} - {e}")


def main():
    """主函数."""
    print("=" * 80)
    print("数据迁移脚本 - SQLite")
    print("=" * 80)
    print()

    # 初始化SQLite管理器
    print("初始化SQLite数据库...")
    sqlite_manager = get_sqlite_manager()

    if not sqlite_manager._initialized:
        print("❌ SQLite管理器初始化失败")
        print("   请确保vnpy_sqlite已安装：")
        print("   pip install git+https://github.com/vnpy/vnpy_sqlite.git")
        sys.exit(1)

    print("✅ SQLite数据库初始化成功")
    print()

    # 迁移配置文件
    print("开始迁移配置文件...")
    print("-" * 80)

    config_dir = project_root / "config"
    if config_dir.exists():
        # 终端配置
        terminal_config = config_dir / "terminal_config.json"
        if terminal_config.exists():
            migrate_config_file(terminal_config, "terminal", sqlite_manager)

        # 数据中心配置
        data_config = config_dir / "data_center_config.json"
        if data_config.exists():
            migrate_config_file(data_config, "data_center", sqlite_manager)

        # 交易网关配置
        trading_config = config_dir / "trading_gateway_config.json"
        if trading_config.exists():
            migrate_config_file(trading_config, "trading_gateway", sqlite_manager)

        # 策略中心配置
        strategy_config = config_dir / "strategy_center_config.json"
        if strategy_config.exists():
            migrate_config_file(strategy_config, "strategy_center", sqlite_manager)

        # AI助手配置
        ai_config = config_dir / "ai_assistant_config.json"
        if ai_config.exists():
            migrate_config_file(ai_config, "ai_assistant", sqlite_manager)

    print()
    print("=" * 80)
    print("配置迁移完成")
    print("=" * 80)
    print()

    # 说明
    print("📝 说明:")
    print("   - 配置数据已迁移到SQLite数据库")
    print("   - 历史K线数据保留在Parquet格式（data/目录）")
    print("   - 品种列表缓存保留在Parquet格式（data/cache/stock_list.parquet）")
    print("   - 录制数据将使用Parquet格式（data/recorded/）")
    print()

    print("📊 数据库位置:")
    print(f"   {sqlite_manager.db_path}")
    print()

    print("✅ 迁移完成！")
    print()

    # 验证迁移
    print("验证迁移结果...")
    modules = ["terminal", "data_center", "trading_gateway", "strategy_center", "ai_assistant"]

    for module in modules:
        configs = sqlite_manager.get_module_configs(module)
        if configs:
            print(f"   ✅ {module}: {len(configs)} 个配置项")
        else:
            print(f"   ⚠️  {module}: 无配置数据")

    print()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
基本功能测试脚本

测试data_module_vnpy的基本功能是否正常工作
"""

import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """测试模块导入"""
    try:
        from data_module_vnpy.config import config_manager
        print("✓ 配置管理模块导入成功")

        from data_module_vnpy.stock_fetcher import StockFetcher
        print("✓ 数据获取模块导入成功")

        from data_module_vnpy.storage import StorageManager
        print("✓ 存储管理模块导入成功")

        from data_module_vnpy.validator import DataValidator
        print("✓ 数据校验模块导入成功")

        from data_module_vnpy.file_watcher import FileWatcherManager
        print("✓ 文件监控模块导入成功")

        from data_module_vnpy.block_parser import BlockParser
        print("✓ 板块解析模块导入成功")

        return True

    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False

def test_config():
    """测试配置管理"""
    try:
        from data_module_vnpy.config import config_manager

        # 测试获取配置
        cache_dir = config_manager.get_cache_dir()
        data_dir = config_manager.get_data_dir()
        base_date = config_manager.get_base_date()

        print(f"✓ 缓存目录: {cache_dir}")
        print(f"✓ 数据目录: {data_dir}")
        print(f"✓ 基日: {base_date}")

        return True

    except Exception as e:
        print(f"✗ 配置测试失败: {e}")
        return False

def test_storage():
    """测试存储管理"""
    try:
        from data_module_vnpy.storage import StorageManager

        storage = StorageManager()
        symbols = storage.list_symbols()

        print(f"✓ 存储管理器初始化成功")
        print(f"✓ 发现 {len(symbols)} 个品种")

        return True

    except Exception as e:
        print(f"✗ 存储测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始测试 data_module_vnpy 基本功能...")
    print("=" * 50)

    tests = [
        ("模块导入", test_imports),
        ("配置管理", test_config),
        ("存储管理", test_storage),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n测试: {test_name}")
        print("-" * 30)

        if test_func():
            passed += 1
            print(f"✓ {test_name} 测试通过")
        else:
            print(f"✗ {test_name} 测试失败")

    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！data_module_vnpy 基本功能正常")
    else:
        print("⚠️  部分测试失败，请检查相关模块")

if __name__ == "__main__":
    main()

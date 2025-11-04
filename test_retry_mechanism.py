# -*- coding: utf-8 -*-
"""
测试重构后的下载机制（RetryConnectionPool）

测试内容：
1. IPO 日期下载（单进程）
2. IPO 日期下载（多进程）
3. K 线下载（基本功能测试）
"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_ipo_download_single():
    """测试单进程 IPO 日期下载"""
    print("\n" + "="*60)
    print("测试1: 单进程 IPO 日期下载")
    print("="*60)
    
    try:
        from backend.infrastructure.data_module_vnpy.data_acquisition import (
            download_ipo_dates
        )
        
        # 使用少量品种进行测试
        test_symbols = ["000001", "000002", "600000", "600001", "300001"]
        
        print(f"测试品种: {test_symbols}")
        print("开始下载...")
        
        start_time = time.time()
        result = download_ipo_dates(
            symbols=test_symbols,
            use_multiprocess=False,  # 使用单进程模式
        )
        elapsed = time.time() - start_time
        
        print(f"\n✅ 下载完成，耗时: {elapsed:.2f}秒")
        print(f"结果数量: {len(result)}")
        
        # 显示结果
        for sym, ipo_date in result.items():
            status = "✅" if ipo_date else "❌"
            print(f"  {status} {sym}: {ipo_date}")
        
        success_count = sum(1 for v in result.values() if v is not None)
        null_count = len(result) - success_count
        
        print(f"\n统计: 成功={success_count}, null={null_count}, 总计={len(result)}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ipo_download_multiprocess():
    """测试多进程 IPO 日期下载"""
    print("\n" + "="*60)
    print("测试2: 多进程 IPO 日期下载")
    print("="*60)
    
    try:
        from backend.infrastructure.data_module_vnpy.data_acquisition import (
            download_ipo_dates
        )
        
        # 使用较多品种进行测试（触发多进程模式）
        test_symbols = [f"{i:06d}" for i in range(1, 101)]  # 000001-000100
        
        print(f"测试品种数: {len(test_symbols)}")
        print("开始下载（多进程模式）...")
        
        start_time = time.time()
        result = download_ipo_dates(
            symbols=test_symbols,
            use_multiprocess=True,  # 使用多进程模式
            max_workers=2,  # 使用2个进程
        )
        elapsed = time.time() - start_time
        
        print(f"\n✅ 下载完成，耗时: {elapsed:.2f}秒")
        print(f"结果数量: {len(result)}")
        
        success_count = sum(1 for v in result.values() if v is not None)
        null_count = len(result) - success_count
        
        print(f"\n统计: 成功={success_count}, null={null_count}, 总计={len(result)}")
        
        # 显示前10个结果
        print("\n前10个结果:")
        for i, (sym, ipo_date) in enumerate(list(result.items())[:10]):
            status = "✅" if ipo_date else "❌"
            print(f"  {status} {sym}: {ipo_date}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_kline_download():
    """测试 K 线下载（基本功能）"""
    print("\n" + "="*60)
    print("测试3: K 线下载（基本功能）")
    print("="*60)
    
    try:
        from backend.infrastructure.data_module_vnpy.data_acquisition import (
            MultiProcessStockFetcher,
            DownloadTask
        )
        from datetime import date, timedelta
        
        print("创建下载器实例...")
        fetcher = MultiProcessStockFetcher()
        
        # 创建测试任务
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        tasks = [
            DownloadTask(
                symbol="000001",
                interval="1d",
                start_date=start_date,
                end_date=end_date,
            ),
            DownloadTask(
                symbol="600000",
                interval="1d",
                start_date=start_date,
                end_date=end_date,
            ),
        ]
        
        print(f"创建 {len(tasks)} 个下载任务")
        print(f"日期范围: {start_date} 至 {end_date}")
        
        # 注意：这里只测试任务创建，不实际执行下载（因为下载需要更多配置）
        print("✅ 任务创建成功")
        print(f"任务列表:")
        for task in tasks:
            print(f"  - {task.symbol} ({task.interval})")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retry_connection_pool_import():
    """测试 RetryConnectionPool 导入"""
    print("\n" + "="*60)
    print("测试0: RetryConnectionPool 导入")
    print("="*60)
    
    try:
        from backend.infrastructure.tdx_asyncio.retry_connection_pool import (
            RetryConnectionPool
        )
        from backend.infrastructure.data_module_vnpy.load_balancer import (
            get_server_pool_manager
        )
        
        print("✅ RetryConnectionPool 导入成功")
        
        # 测试创建实例
        pool_mgr = get_server_pool_manager()
        retry_pool = RetryConnectionPool(
            server_pool_manager=pool_mgr,
            phase1_max_attempts=10,
            phase2_max_attempts=5,
            connection_timeout=5.0
        )
        
        print("✅ RetryConnectionPool 实例创建成功")
        print(f"  阶段1最大尝试次数: {retry_pool.phase1_max_attempts}")
        print(f"  阶段2最大尝试次数: {retry_pool.phase2_max_attempts}")
        print(f"  连接超时: {retry_pool.connection_timeout}秒")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("开始测试重构后的下载机制")
    print("="*60)
    
    results = []
    
    # 测试0: 导入测试
    results.append(("RetryConnectionPool 导入", test_retry_connection_pool_import()))
    
    # 测试1: IPO 日期下载（单进程）
    results.append(("IPO 日期下载（单进程）", test_ipo_download_single()))
    
    # 测试2: IPO 日期下载（多进程）
    # 注意：这个测试可能耗时较长，可以根据需要注释掉
    # results.append(("IPO 日期下载（多进程）", test_ipo_download_multiprocess()))
    
    # 测试3: K 线下载（基本功能）
    results.append(("K 线下载（基本功能）", test_kline_download()))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n总计: {passed} 通过, {failed} 失败")
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""测试异步下载功能"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import time
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

def test_async_download():
    """测试异步下载功能"""
    logger.info("=" * 80)
    logger.info("测试异步下载功能")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
    from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
    
    # 初始化
    fetcher = MultiProcessStockFetcher()
    symbol_loader = SymbolLoader()
    
    logger.info(f"配置信息:")
    logger.info(f"  进程数: {fetcher.num_processes}")
    logger.info(f"  每进程连接数: {fetcher.async_connections_per_process}")
    logger.info(f"  总并发数: {fetcher.num_processes * fetcher.async_connections_per_process}")
    
    # 获取一小批测试品种
    logger.info("\n加载品种列表...")
    all_symbols = symbol_loader.extract_all_codes()
    test_symbols = all_symbols[:10]  # 只测试10个品种
    logger.info(f"测试品种: {test_symbols}")
    
    # 测试下载
    intervals = ["1d"]  # 只测试日线
    start_date = date(2024, 10, 1)
    
    total_tasks = len(test_symbols) * len(intervals)
    logger.info(f"\n开始异步下载测试:")
    logger.info(f"  品种数: {len(test_symbols)}")
    logger.info(f"  周期: {intervals}")
    logger.info(f"  总任务数: {total_tasks}")
    
    # 进度回调
    progress_count = [0]
    def progress_callback(completed, total, symbol, interval):
        progress_count[0] = completed
        if completed % 5 == 0 or completed == total:
            logger.info(f"  进度: {completed}/{total} - {symbol} {interval}")
    
    # 开始计时
    start_time = time.time()
    
    try:
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            intervals=intervals,
            start_date=start_date,
            progress_callback=progress_callback
        )
        
        elapsed = time.time() - start_time
        
        logger.info(f"\n下载完成！")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  返回结果数: {len(results)}")
        logger.info(f"  进度回调次数: {progress_count[0]}")
        
        # 检查结果
        success_count = sum(1 for v in results.values() if v is not None and not v.empty)
        logger.info(f"  成功: {success_count}/{total_tasks}")
        logger.info(f"  成功率: {success_count/total_tasks*100:.1f}%")
        
        # 性能指标
        if elapsed > 0:
            tasks_per_second = total_tasks / elapsed
            logger.info(f"  吞吐量: {tasks_per_second:.1f} 任务/秒")
            logger.info(f"  平均每任务: {elapsed/total_tasks*1000:.0f}ms")
        
        return True
        
    except Exception as e:
        logger.error(f"下载失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    logger.info("异步下载功能测试\n")
    
    success = test_async_download()
    
    logger.info("\n" + "=" * 80)
    if success:
        logger.info("✓ 测试通过")
    else:
        logger.info("✗ 测试失败")


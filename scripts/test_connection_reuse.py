"""测试连接复用性能提升"""
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import time
from datetime import date
from mootdx.quotes import Quotes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def test_without_reuse():
    """测试：每次任务都创建新连接（旧方式）"""
    logger.info("=" * 80)
    logger.info("测试1：每次任务创建新连接（旧方式）")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager, _download_single_kline
    
    server_manager = ServerManager()
    if server_manager.verification_status != "completed":
        server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
    
    servers = server_manager.get_available_servers(1)
    server = servers[0]
    
    symbols = ["600000", "600016", "600036", "600048", "600050"]
    interval = "1d"
    start_date = date(2024, 10, 1)
    
    logger.info(f"下载 {len(symbols)} 个品种，每次创建新连接")
    start_time = time.time()
    
    success_count = 0
    for symbol in symbols:
        try:
            # ❌ 每次都创建新连接
            quotes = Quotes.factory(server=server, timeout=30, heartbeat=False)
            data = _download_single_kline(quotes, symbol, interval, start_date)
            quotes.close()
            
            if data is not None and not data.empty:
                success_count += 1
                logger.info(f"  ✓ {symbol}: {len(data)} 条数据")
        except Exception as e:
            logger.error(f"  ✗ {symbol}: {e}")
    
    elapsed = time.time() - start_time
    logger.info(f"完成：{success_count}/{len(symbols)} 成功")
    logger.info(f"总耗时：{elapsed:.2f}秒")
    logger.info(f"平均每个：{elapsed/len(symbols):.2f}秒")
    
    return elapsed


def test_with_reuse():
    """测试：复用连接（新方式）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2：复用连接（新方式）")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager, _download_single_kline
    
    server_manager = ServerManager()
    if server_manager.verification_status != "completed":
        server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
    
    servers = server_manager.get_available_servers(1)
    server = servers[0]
    
    symbols = ["600000", "600016", "600036", "600048", "600050"]
    interval = "1d"
    start_date = date(2024, 10, 1)
    
    logger.info(f"下载 {len(symbols)} 个品种，复用同一连接")
    start_time = time.time()
    
    # ✅ 只创建一次连接
    quotes = Quotes.factory(server=server, timeout=30, heartbeat=False)
    logger.info(f"连接已建立：{server[0]}:{server[1]}")
    
    success_count = 0
    for symbol in symbols:
        try:
            # ✅ 复用连接
            data = _download_single_kline(quotes, symbol, interval, start_date)
            
            if data is not None and not data.empty:
                success_count += 1
                logger.info(f"  ✓ {symbol}: {len(data)} 条数据")
        except Exception as e:
            logger.error(f"  ✗ {symbol}: {e}")
    
    quotes.close()
    
    elapsed = time.time() - start_time
    logger.info(f"完成：{success_count}/{len(symbols)} 成功")
    logger.info(f"总耗时：{elapsed:.2f}秒")
    logger.info(f"平均每个：{elapsed/len(symbols):.2f}秒")
    
    return elapsed


if __name__ == "__main__":
    logger.info("测试连接复用性能提升\n")
    
    # 测试1：不复用
    time1 = test_without_reuse()
    
    # 等待2秒
    time.sleep(2)
    
    # 测试2：复用
    time2 = test_with_reuse()
    
    # 对比
    logger.info("\n" + "=" * 80)
    logger.info("性能对比")
    logger.info("=" * 80)
    logger.info(f"不复用连接：{time1:.2f}秒")
    logger.info(f"复用连接：  {time2:.2f}秒")
    logger.info(f"性能提升：  {(time1/time2):.2f}倍")
    logger.info(f"节省时间：  {time1-time2:.2f}秒 ({(time1-time2)/time1*100:.1f}%)")


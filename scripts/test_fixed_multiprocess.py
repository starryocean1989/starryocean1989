#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的MultiProcessStockFetcher

验证修复是否解决了多进程问题
"""

import sys
import os
import logging
import time
from datetime import date, datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_fixed_multiprocess.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def test_fixed_multiprocess():
    """测试修复后的多进程下载器"""
    logger.info("=" * 60)
    logger.info("测试修复后的MultiProcessStockFetcher")
    logger.info("=" * 60)
    
    try:
        # 创建下载器
        fetcher = MultiProcessStockFetcher()
        
        # 设置较少的进程数进行测试
        fetcher.set_server_count(3)
        
        # 测试品种和周期
        test_symbols = ["000001", "000002", "600000"]
        test_intervals = ["1d"]
        start_date = "2024-01-01"
        
        logger.info(f"开始测试:")
        logger.info(f"  品种: {test_symbols}")
        logger.info(f"  周期: {test_intervals}")
        logger.info(f"  开始日期: {start_date}")
        logger.info(f"  进程数: {fetcher.num_processes}")
        
        # 定义进度回调
        def progress_callback(completed, total, symbol, interval):
            logger.info(f"进度: {completed}/{total} - {symbol} {interval}")
        
        # 开始下载
        start_time = time.time()
        
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=test_intervals,
            progress_callback=progress_callback
        )
        
        elapsed_time = time.time() - start_time
        
        # 分析结果
        logger.info("=" * 60)
        logger.info("下载结果分析:")
        logger.info("=" * 60)
        
        success_count = 0
        total_data_count = 0
        
        for key, data in results.items():
            if data is not None and not data.empty:
                success_count += 1
                total_data_count += len(data)
                logger.info(f"✓ {key}: {len(data)} 条数据")
                logger.info(f"  时间范围: {data.index.min()} ~ {data.index.max()}")
            else:
                logger.warning(f"✗ {key}: 无数据")
        
        logger.info("=" * 60)
        logger.info("测试总结:")
        logger.info("=" * 60)
        logger.info(f"总耗时: {elapsed_time:.2f} 秒")
        logger.info(f"成功下载: {success_count}/{len(results)} 个品种")
        logger.info(f"总数据量: {total_data_count} 条")
        logger.info(f"平均速度: {total_data_count/elapsed_time:.1f} 条/秒")
        
        # 判断测试是否成功
        if success_count > 0:
            logger.info("✓ 修复后的多进程下载器工作正常")
            return True
        else:
            logger.error("✗ 修复后的多进程下载器仍有问题")
            return False
            
    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        return False

def test_different_process_counts():
    """测试不同进程数的效果"""
    logger.info("=" * 60)
    logger.info("测试不同进程数的效果")
    logger.info("=" * 60)
    
    process_counts = [1, 2, 3, 5]
    test_symbols = ["000001", "000002"]
    test_intervals = ["1d"]
    start_date = "2024-01-01"
    
    results = {}
    
    for process_count in process_counts:
        logger.info(f"\n测试进程数: {process_count}")
        
        try:
            fetcher = MultiProcessStockFetcher()
            fetcher.set_server_count(process_count)
            
            start_time = time.time()
            
            download_results = fetcher.download_incremental_kline(
                symbols=test_symbols,
                start_date=start_date,
                intervals=test_intervals
            )
            
            elapsed_time = time.time() - start_time
            
            success_count = sum(1 for data in download_results.values() 
                              if data is not None and not data.empty)
            total_data = sum(len(data) for data in download_results.values() 
                           if data is not None and not data.empty)
            
            results[process_count] = {
                'success_count': success_count,
                'total_data': total_data,
                'elapsed_time': elapsed_time,
                'speed': total_data / elapsed_time if elapsed_time > 0 else 0
            }
            
            logger.info(f"  成功: {success_count}/{len(download_results)}")
            logger.info(f"  数据量: {total_data} 条")
            logger.info(f"  耗时: {elapsed_time:.2f} 秒")
            logger.info(f"  速度: {total_data/elapsed_time:.1f} 条/秒")
            
        except Exception as e:
            logger.error(f"  测试失败: {e}")
            results[process_count] = None
    
    # 输出对比结果
    logger.info("\n" + "=" * 60)
    logger.info("进程数对比结果:")
    logger.info("=" * 60)
    logger.info("进程数 | 成功数 | 数据量 | 耗时(秒) | 速度(条/秒)")
    logger.info("-" * 50)
    
    for process_count, result in results.items():
        if result:
            logger.info(f"{process_count:6d} | {result['success_count']:6d} | "
                       f"{result['total_data']:6d} | {result['elapsed_time']:8.2f} | "
                       f"{result['speed']:10.1f}")
        else:
            logger.info(f"{process_count:6d} | {'失败':>6} | {'--':>6} | {'--':>8} | {'--':>10}")

if __name__ == "__main__":
    logger.info("开始测试修复后的MultiProcessStockFetcher")
    logger.info("=" * 80)
    
    # 基础功能测试
    basic_test_result = test_fixed_multiprocess()
    
    if basic_test_result:
        # 如果基础测试通过，进行性能对比测试
        test_different_process_counts()
    
    logger.info("\n" + "=" * 80)
    if basic_test_result:
        logger.info("✓ 所有测试通过！MultiProcessStockFetcher修复成功")
    else:
        logger.error("✗ 测试失败，需要进一步调试")


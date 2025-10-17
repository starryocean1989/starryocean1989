#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前后端联调测试脚本

模拟前端点击下载按钮，测试完整的数据下载流程：
前端 -> DataCenterService -> ChinaStockEngine -> MultiProcessStockFetcher -> 多进程下载
"""

import sys
import os
import logging
from datetime import datetime, date, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.data_center_service import DataCenterService
from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine
from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
from backend.core.base import set_china_stock_engine, get_china_stock_engine

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_frontend_backend_integration.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def test_full_integration():
    """测试完整的前后端集成"""
    logger.info("=" * 80)
    logger.info("前后端联调测试开始")
    logger.info("=" * 80)
    
    try:
        # ==================== 第0步：初始化全局引擎 ====================
        logger.info("\n【第0步】初始化全局ChinaStockEngine...")
        
        # 检查是否已有全局引擎
        existing_engine = get_china_stock_engine()
        if existing_engine:
            logger.info("✓ 全局ChinaStockEngine已存在")
            engine = existing_engine
        else:
            logger.info("创建新的ChinaStockEngine...")
            engine = ChinaStockEngine()
            set_china_stock_engine(engine)
            logger.info("✓ 全局ChinaStockEngine已设置")
        
        # ==================== 第1步：初始化服务 ====================
        logger.info("\n【第1步】初始化数据中心服务...")
        data_center_service = DataCenterService()
        logger.info("✓ DataCenterService 初始化成功")
        
        # 检查ChinaStockEngine
        if data_center_service.china_stock_engine:
            logger.info("✓ ChinaStockEngine 可用")
            engine = data_center_service.china_stock_engine
            
            # 检查股票抓取器
            if hasattr(engine, 'stock_fetcher') and engine.stock_fetcher:
                logger.info("✓ MultiProcessStockFetcher 可用")
                fetcher = engine.stock_fetcher
                logger.info(f"  进程数: {fetcher.num_processes}")
                logger.info(f"  超时时间: {fetcher.timeout}秒")
                logger.info(f"  重试次数: {fetcher.retry_times}")
            else:
                logger.warning("✗ MultiProcessStockFetcher 不可用，需要延迟初始化")
        else:
            logger.error("✗ ChinaStockEngine 不可用")
            return False
        
        # ==================== 第2步：检查服务器状态 ====================
        logger.info("\n【第2步】检查服务器状态...")
        
        # 触发延迟初始化
        engine._ensure_lazy_init()
        
        if hasattr(engine, 'stock_fetcher') and engine.stock_fetcher:
            fetcher = engine.stock_fetcher
            server_manager = fetcher.server_manager
            
            # 检查服务器验证状态
            status = server_manager.get_server_status()
            logger.info(f"服务器验证状态: {status['status']}")
            logger.info(f"可用服务器数: {status['available_count']}/{status['total_count']}")
            
            if status['available_count'] == 0:
                logger.info("服务器未验证，启动验证...")
                server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
                status = server_manager.get_server_status()
                logger.info(f"验证后可用服务器: {status['available_count']}/{status['total_count']}")
            
            if status['available_count'] > 0:
                logger.info("✓ 服务器状态正常")
                # 显示前5个可用服务器
                available_servers = server_manager.get_available_servers(5)
                logger.info(f"前5个可用服务器: {available_servers}")
            else:
                logger.error("✗ 没有可用服务器")
                return False
        else:
            logger.error("✗ 无法获取股票抓取器")
            return False
        
        # ==================== 第3步：检查品种列表 ====================
        logger.info("\n【第3步】检查品种列表...")
        
        symbol_loader = engine.symbol_loader
        classified_stocks = symbol_loader.load_from_cache()
        
        if not classified_stocks:
            logger.info("品种缓存为空，重新加载...")
            reload_result = symbol_loader.reload_and_classify()
            if reload_result.get("success"):
                logger.info(f"✓ 品种加载成功: {reload_result.get('total_count', 0)} 个")
                classified_stocks = symbol_loader.load_from_cache()
            else:
                logger.error("✗ 品种加载失败")
                return False
        else:
            total_count = sum(len(stocks) for stocks in classified_stocks.values())
            logger.info(f"✓ 品种缓存已存在: {total_count} 个")
        
        # ==================== 第4步：模拟前端下载请求 ====================
        logger.info("\n【第4步】模拟前端下载请求...")
        
        # 设置下载参数（模拟前端）
        start_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        logger.info(f"下载参数:")
        logger.info(f"  开始日期: {start_date}")
        logger.info(f"  天数范围: 5天")
        
        # 调用服务层方法（模拟前端调用）
        logger.info("\n调用 data_center_service.start_incremental_download()...")
        result = data_center_service.start_incremental_download(start_date)
        
        logger.info("=" * 60)
        logger.info("下载结果:")
        logger.info("=" * 60)
        logger.info(f"成功: {result.get('success')}")
        logger.info(f"任务ID: {result.get('task_id')}")
        logger.info(f"消息: {result.get('message')}")
        
        if result.get('success'):
            logger.info("✓ 下载请求成功启动")
            
            # ==================== 第5步：监控下载进度 ====================
            logger.info("\n【第5步】监控下载进度...")
            
            import time
            max_wait_time = 60  # 最多等待60秒
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                progress = fetcher.get_download_progress()
                
                if progress['is_downloading']:
                    logger.info(f"下载中: {progress['completed']}/{progress['total']} - "
                               f"{progress.get('current_symbol', '')} {progress.get('current_interval', '')}")
                    time.sleep(2)
                else:
                    logger.info("下载已完成或未开始")
                    break
            
            logger.info("✓ 下载流程完成")
            return True
        else:
            logger.error(f"✗ 下载请求失败: {result.get('message')}")
            return False
        
    except Exception as e:
        logger.error(f"联调测试异常: {e}", exc_info=True)
        return False

def test_multiprocess_fetcher_directly():
    """直接测试MultiProcessStockFetcher"""
    logger.info("\n" + "=" * 80)
    logger.info("直接测试MultiProcessStockFetcher")
    logger.info("=" * 80)
    
    try:
        # 创建下载器
        fetcher = MultiProcessStockFetcher()
        logger.info(f"✓ MultiProcessStockFetcher创建成功")
        logger.info(f"  进程数: {fetcher.num_processes}")
        
        # 验证服务器
        logger.info("\n验证服务器...")
        fetcher.server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
        status = fetcher.server_manager.get_server_status()
        logger.info(f"可用服务器: {status['available_count']}/{status['total_count']}")
        
        if status['available_count'] == 0:
            logger.error("✗ 没有可用服务器")
            return False
        
        # 测试下载
        logger.info("\n开始测试下载...")
        test_symbols = ["000001", "600000"]
        test_intervals = ["1d"]
        start_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
        
        logger.info(f"测试参数:")
        logger.info(f"  品种: {test_symbols}")
        logger.info(f"  周期: {test_intervals}")
        logger.info(f"  开始日期: {start_date}")
        
        # 定义进度回调
        def progress_callback(completed, total, symbol, interval):
            logger.info(f"进度: {completed}/{total} - {symbol} {interval}")
        
        # 执行下载
        import time
        download_start = time.time()
        
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=test_intervals,
            progress_callback=progress_callback
        )
        
        download_time = time.time() - download_start
        
        # 分析结果
        logger.info("\n" + "=" * 60)
        logger.info("下载结果分析:")
        logger.info("=" * 60)
        
        success_count = 0
        total_data = 0
        
        for key, data in results.items():
            if data is not None and not data.empty:
                success_count += 1
                total_data += len(data)
                logger.info(f"✓ {key}: {len(data)} 条数据")
            else:
                logger.warning(f"✗ {key}: 无数据")
        
        logger.info("=" * 60)
        logger.info(f"总耗时: {download_time:.2f} 秒")
        logger.info(f"成功率: {success_count}/{len(results)}")
        logger.info(f"总数据: {total_data} 条")
        
        if success_count > 0:
            logger.info("✓ 直接测试成功")
            return True
        else:
            logger.error("✗ 直接测试失败")
            return False
        
    except Exception as e:
        logger.error(f"直接测试异常: {e}", exc_info=True)
        return False

def test_server_configuration():
    """测试服务器配置功能"""
    logger.info("\n" + "=" * 80)
    logger.info("测试服务器配置功能")
    logger.info("=" * 80)
    
    try:
        fetcher = MultiProcessStockFetcher()
        
        # 测试不同的进程数配置
        process_counts = [1, 3, 5, 10]
        
        for count in process_counts:
            logger.info(f"\n设置进程数为: {count}")
            fetcher.set_server_count(count)
            logger.info(f"✓ 进程数已设置: {fetcher.num_processes}")
        
        logger.info("✓ 服务器配置功能正常")
        return True
        
    except Exception as e:
        logger.error(f"服务器配置测试异常: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("开始前后端联调测试")
    logger.info("=" * 80)
    
    # 测试1：服务器配置
    test1 = test_server_configuration()
    
    # 测试2：直接测试MultiProcessStockFetcher
    test2 = test_multiprocess_fetcher_directly()
    
    # 测试3：完整集成测试
    test3 = test_full_integration()
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结:")
    logger.info("=" * 80)
    logger.info(f"服务器配置测试: {'✓ 通过' if test1 else '✗ 失败'}")
    logger.info(f"直接下载测试: {'✓ 通过' if test2 else '✗ 失败'}")
    logger.info(f"完整集成测试: {'✓ 通过' if test3 else '✗ 失败'}")
    
    if all([test1, test2, test3]):
        logger.info("\n✓✓✓ 所有测试通过！前后端联调成功！")
        logger.info("可以正常使用多服务器、多进程下载功能")
    else:
        logger.error("\n✗✗✗ 部分测试失败，请查看日志详情")

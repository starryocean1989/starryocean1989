#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MultiProcessStockFetcher 控制变量法调试脚本

使用控制变量法逐步测试各个组件，找出多进程无法获取数据的问题
"""

import sys
import os
import logging
import time
import traceback
from datetime import date, datetime
from multiprocessing import Manager, Process, Queue
from typing import Dict, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.infrastructure.data_module_vnpy.data_fetcher import (
    MultiProcessStockFetcher,
    ServerManager,
    TdxDateTimeDecoder,
    download_worker_pooled,
    _download_single_kline
)
from mootdx.quotes import Quotes

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_multiprocess_debug.log')
    ]
)
logger = logging.getLogger(__name__)

class MultiProcessDebugger:
    """多进程调试器"""
    
    def __init__(self):
        self.test_symbols = ["000001", "000002", "600000"]  # 测试品种
        self.test_intervals = ["1d"]  # 先测试日线
        self.start_date = "2024-01-01"
        
    def test_1_single_process_direct(self):
        """测试1: 单进程直接调用mootdx"""
        logger.info("=" * 60)
        logger.info("测试1: 单进程直接调用mootdx")
        logger.info("=" * 60)
        
        try:
            # 直接使用mootdx获取数据
            quotes = Quotes.factory(server=("119.147.212.81", 7709), timeout=30, heartbeat=False)
            
            for symbol in self.test_symbols:
                logger.info(f"测试品种: {symbol}")
                data = _download_single_kline(quotes, symbol, "1d", self.start_date)
                if data is not None and not data.empty:
                    logger.info(f"✓ {symbol} 获取成功: {len(data)} 条数据")
                    logger.info(f"  数据列: {list(data.columns)}")
                    logger.info(f"  时间范围: {data.index.min()} ~ {data.index.max()}")
                else:
                    logger.warning(f"✗ {symbol} 获取失败或数据为空")
            
            quotes.close()
            logger.info("测试1完成: 单进程直接调用成功")
            return True
            
        except Exception as e:
            logger.error(f"测试1失败: {e}", exc_info=True)
            return False
    
    def test_2_server_manager(self):
        """测试2: ServerManager功能"""
        logger.info("=" * 60)
        logger.info("测试2: ServerManager功能")
        logger.info("=" * 60)
        
        try:
            server_manager = ServerManager()
            logger.info(f"总服务器数: {len(server_manager.all_servers)}")
            
            # 验证服务器
            server_manager.verify_all_servers_sync(timeout=5, max_workers=10)
            
            status = server_manager.get_server_status()
            logger.info(f"验证状态: {status['status']}")
            logger.info(f"可用服务器: {status['available_count']}/{status['total_count']}")
            
            if status['available_count'] > 0:
                available_servers = server_manager.get_available_servers(3)
                logger.info(f"前3个可用服务器: {available_servers}")
                return True
            else:
                logger.error("没有可用服务器")
                return False
                
        except Exception as e:
            logger.error(f"测试2失败: {e}", exc_info=True)
            return False
    
    def test_3_single_worker_function(self):
        """测试3: 单个worker函数"""
        logger.info("=" * 60)
        logger.info("测试3: 单个worker函数")
        logger.info("=" * 60)
        
        try:
            # 创建Manager对象
            manager = Manager()
            task_queue = manager.Queue()
            result_queue = manager.Queue()
            progress_queue = manager.Queue()
            server_list = manager.list([("119.147.212.81", 7709)])
            server_index = manager.Value('i', 0)
            stop_event = manager.Event()
            pause_event = manager.Event()
            pause_event.set()
            
            # 添加测试任务
            task_queue.put(("000001", "1d", self.start_date))
            
            # 启动单个worker进程
            worker_process = Process(
                target=download_worker_pooled,
                args=(
                    0,  # worker_id
                    task_queue,
                    result_queue,
                    progress_queue,
                    server_list,
                    server_index,
                    30,  # timeout
                    3,   # retry_times
                    stop_event,
                    pause_event,
                )
            )
            
            worker_process.start()
            logger.info("启动单个worker进程")
            
            # 等待结果
            start_time = time.time()
            while time.time() - start_time < 30:  # 最多等待30秒
                if not worker_process.is_alive():
                    break
                time.sleep(0.1)
            
            # 收集结果
            results = []
            while not result_queue.empty():
                try:
                    result = result_queue.get_nowait()
                    results.append(result)
                    logger.info(f"收到结果: {result[0]}")
                except:
                    break
            
            # 收集进度
            progress_count = 0
            while not progress_queue.empty():
                try:
                    progress = progress_queue.get_nowait()
                    progress_count += 1
                    logger.info(f"收到进度: {progress}")
                except:
                    break
            
            worker_process.join(timeout=5)
            if worker_process.is_alive():
                worker_process.terminate()
                worker_process.join()
            
            logger.info(f"测试3完成: 收到{len(results)}个结果, {progress_count}个进度")
            return len(results) > 0
            
        except Exception as e:
            logger.error(f"测试3失败: {e}", exc_info=True)
            return False
    
    def test_4_multiprocess_fetcher_basic(self):
        """测试4: MultiProcessStockFetcher基础功能"""
        logger.info("=" * 60)
        logger.info("测试4: MultiProcessStockFetcher基础功能")
        logger.info("=" * 60)
        
        try:
            fetcher = MultiProcessStockFetcher()
            logger.info(f"进程数: {fetcher.num_processes}")
            logger.info(f"超时时间: {fetcher.timeout}")
            logger.info(f"重试次数: {fetcher.retry_times}")
            
            # 测试服务器管理器
            available_servers = fetcher.server_manager.get_available_servers()
            logger.info(f"可用服务器数: {len(available_servers)}")
            
            if len(available_servers) == 0:
                logger.warning("没有可用服务器，尝试验证...")
                fetcher.server_manager.verify_all_servers_sync(timeout=3, max_workers=20)
                available_servers = fetcher.server_manager.get_available_servers()
                logger.info(f"验证后可用服务器数: {len(available_servers)}")
            
            return len(available_servers) > 0
            
        except Exception as e:
            logger.error(f"测试4失败: {e}", exc_info=True)
            return False
    
    def test_5_multiprocess_download_simple(self):
        """测试5: 多进程下载简单测试"""
        logger.info("=" * 60)
        logger.info("测试5: 多进程下载简单测试")
        logger.info("=" * 60)
        
        try:
            fetcher = MultiProcessStockFetcher()
            
            # 设置较少的进程数进行测试
            fetcher.set_server_count(2)
            
            # 只测试一个品种
            test_symbols = ["000001"]
            test_intervals = ["1d"]
            
            logger.info(f"开始下载: {test_symbols} x {test_intervals}")
            
            results = fetcher.download_incremental_kline(
                symbols=test_symbols,
                start_date=self.start_date,
                intervals=test_intervals,
                progress_callback=self._progress_callback
            )
            
            logger.info(f"下载完成，结果数: {len(results)}")
            for key, data in results.items():
                if data is not None and not data.empty:
                    logger.info(f"✓ {key}: {len(data)} 条数据")
                else:
                    logger.warning(f"✗ {key}: 无数据")
            
            return len(results) > 0 and any(data is not None and not data.empty for data in results.values())
            
        except Exception as e:
            logger.error(f"测试5失败: {e}", exc_info=True)
            return False
    
    def test_6_multiprocess_download_full(self):
        """测试6: 多进程下载完整测试"""
        logger.info("=" * 60)
        logger.info("测试6: 多进程下载完整测试")
        logger.info("=" * 60)
        
        try:
            fetcher = MultiProcessStockFetcher()
            fetcher.set_server_count(3)
            
            logger.info(f"开始完整下载: {self.test_symbols} x {self.test_intervals}")
            
            results = fetcher.download_incremental_kline(
                symbols=self.test_symbols,
                start_date=self.start_date,
                intervals=self.test_intervals,
                progress_callback=self._progress_callback
            )
            
            logger.info(f"完整下载完成，结果数: {len(results)}")
            
            success_count = 0
            for key, data in results.items():
                if data is not None and not data.empty:
                    logger.info(f"✓ {key}: {len(data)} 条数据")
                    success_count += 1
                else:
                    logger.warning(f"✗ {key}: 无数据")
            
            logger.info(f"成功率: {success_count}/{len(results)}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"测试6失败: {e}", exc_info=True)
            return False
    
    def _progress_callback(self, completed, total, symbol, interval):
        """进度回调函数"""
        logger.info(f"进度: {completed}/{total} - {symbol} {interval}")
    
    def run_all_tests(self):
        """运行所有测试"""
        logger.info("开始MultiProcessStockFetcher控制变量法调试")
        logger.info("=" * 80)
        
        tests = [
            ("单进程直接调用", self.test_1_single_process_direct),
            ("ServerManager功能", self.test_2_server_manager),
            ("单个worker函数", self.test_3_single_worker_function),
            ("MultiProcessStockFetcher基础", self.test_4_multiprocess_fetcher_basic),
            ("多进程下载简单", self.test_5_multiprocess_download_simple),
            ("多进程下载完整", self.test_6_multiprocess_download_full),
        ]
        
        results = {}
        for test_name, test_func in tests:
            logger.info(f"\n开始测试: {test_name}")
            try:
                result = test_func()
                results[test_name] = result
                logger.info(f"测试 {test_name}: {'✓ 通过' if result else '✗ 失败'}")
            except Exception as e:
                logger.error(f"测试 {test_name} 异常: {e}", exc_info=True)
                results[test_name] = False
        
        # 输出测试总结
        logger.info("\n" + "=" * 80)
        logger.info("测试总结:")
        logger.info("=" * 80)
        for test_name, result in results.items():
            status = "✓ 通过" if result else "✗ 失败"
            logger.info(f"{test_name}: {status}")
        
        # 分析问题
        self._analyze_results(results)
        
        return results
    
    def _analyze_results(self, results):
        """分析测试结果，找出问题所在"""
        logger.info("\n" + "=" * 80)
        logger.info("问题分析:")
        logger.info("=" * 80)
        
        if results.get("单进程直接调用", False):
            logger.info("✓ 单进程直接调用正常 - mootdx基础功能正常")
        else:
            logger.error("✗ 单进程直接调用失败 - mootdx基础功能有问题")
            return
        
        if results.get("ServerManager功能", False):
            logger.info("✓ ServerManager正常 - 服务器验证功能正常")
        else:
            logger.error("✗ ServerManager失败 - 服务器验证有问题")
            return
        
        if results.get("单个worker函数", False):
            logger.info("✓ 单个worker函数正常 - 进程间通信正常")
        else:
            logger.error("✗ 单个worker函数失败 - 进程间通信有问题")
            return
        
        if results.get("MultiProcessStockFetcher基础", False):
            logger.info("✓ MultiProcessStockFetcher基础正常 - 类初始化正常")
        else:
            logger.error("✗ MultiProcessStockFetcher基础失败 - 类初始化有问题")
            return
        
        if results.get("多进程下载简单", False):
            logger.info("✓ 多进程下载简单正常 - 基础多进程功能正常")
        else:
            logger.error("✗ 多进程下载简单失败 - 基础多进程功能有问题")
            return
        
        if results.get("多进程下载完整", False):
            logger.info("✓ 多进程下载完整正常 - 完整多进程功能正常")
        else:
            logger.error("✗ 多进程下载完整失败 - 完整多进程功能有问题")
            return
        
        logger.info("\n所有测试通过！MultiProcessStockFetcher功能正常。")

if __name__ == "__main__":
    debugger = MultiProcessDebugger()
    debugger.run_all_tests()


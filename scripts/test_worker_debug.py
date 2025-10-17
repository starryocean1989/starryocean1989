#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker函数详细调试脚本

专门测试download_worker_pooled函数的进程间通信问题
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
    download_worker_pooled,
    _download_single_kline
)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('test_worker_debug.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

def test_worker_communication():
    """测试worker进程间通信"""
    logger.info("=" * 60)
    logger.info("测试Worker进程间通信")
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
        test_task = ("000001", "1d", "2024-01-01")
        task_queue.put(test_task)
        logger.info(f"添加测试任务: {test_task}")
        
        # 启动worker进程
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
        
        logger.info("启动worker进程...")
        worker_process.start()
        
        # 监控进程状态
        start_time = time.time()
        timeout = 30
        
        while time.time() - start_time < timeout:
            if not worker_process.is_alive():
                logger.info("Worker进程已结束")
                break
            
            # 检查队列状态
            task_size = task_queue.qsize()
            result_size = result_queue.qsize()
            progress_size = progress_queue.qsize()
            
            if task_size == 0 and (result_size > 0 or progress_size > 0):
                logger.info(f"任务完成，结果队列: {result_size}, 进度队列: {progress_size}")
                break
            
            time.sleep(0.5)
        
        # 收集结果
        results = []
        while not result_queue.empty():
            try:
                result = result_queue.get_nowait()
                results.append(result)
                logger.info(f"收到结果: {result[0]} (数据长度: {len(result[1]) if result[1] else 0})")
            except Exception as e:
                logger.error(f"获取结果异常: {e}")
                break
        
        # 收集进度
        progress_count = 0
        while not progress_queue.empty():
            try:
                progress = progress_queue.get_nowait()
                progress_count += 1
                logger.info(f"收到进度: {progress}")
            except Exception as e:
                logger.error(f"获取进度异常: {e}")
                break
        
        # 等待进程结束
        worker_process.join(timeout=5)
        if worker_process.is_alive():
            logger.warning("强制终止worker进程")
            worker_process.terminate()
            worker_process.join()
        
        logger.info(f"测试完成: 收到{len(results)}个结果, {progress_count}个进度")
        
        # 分析结果
        if len(results) > 0:
            logger.info("✓ Worker通信正常")
            return True
        else:
            logger.error("✗ Worker通信失败 - 没有收到结果")
            return False
            
    except Exception as e:
        logger.error(f"测试异常: {e}", exc_info=True)
        return False

def test_direct_download():
    """直接测试_download_single_kline函数"""
    logger.info("=" * 60)
    logger.info("直接测试_download_single_kline函数")
    logger.info("=" * 60)
    
    try:
        from mootdx.quotes import Quotes
        
        quotes = Quotes.factory(server=("119.147.212.81", 7709), timeout=30, heartbeat=False)
        
        data = _download_single_kline(quotes, "000001", "1d", "2024-01-01")
        
        if data is not None and not data.empty:
            logger.info(f"✓ 直接下载成功: {len(data)} 条数据")
            logger.info(f"  数据列: {list(data.columns)}")
            logger.info(f"  时间范围: {data.index.min()} ~ {data.index.max()}")
            quotes.close()
            return True
        else:
            logger.error("✗ 直接下载失败或数据为空")
            quotes.close()
            return False
            
    except Exception as e:
        logger.error(f"直接下载异常: {e}", exc_info=True)
        return False

def test_simple_worker():
    """简化的worker测试"""
    logger.info("=" * 60)
    logger.info("简化的worker测试")
    logger.info("=" * 60)
    
    def simple_worker(worker_id, task_queue, result_queue):
        """简化的worker函数"""
        logger = logging.getLogger(f"SimpleWorker-{worker_id}")
        logger.info(f"Worker {worker_id} 启动")
        
        try:
            task = task_queue.get(timeout=10)
            logger.info(f"Worker {worker_id} 收到任务: {task}")
            
            # 模拟处理
            result = f"processed_{task}"
            result_queue.put((worker_id, result))
            logger.info(f"Worker {worker_id} 发送结果: {result}")
            
        except Exception as e:
            logger.error(f"Worker {worker_id} 异常: {e}")
    
    try:
        # 创建Manager对象
        manager = Manager()
        task_queue = manager.Queue()
        result_queue = manager.Queue()
        
        # 添加测试任务
        task_queue.put("test_task")
        
        # 启动worker进程
        worker_process = Process(
            target=simple_worker,
            args=(0, task_queue, result_queue)
        )
        
        worker_process.start()
        logger.info("启动简化worker进程")
        
        # 等待结果
        start_time = time.time()
        while time.time() - start_time < 15:
            if not worker_process.is_alive():
                break
            time.sleep(0.1)
        
        # 收集结果
        results = []
        while not result_queue.empty():
            try:
                result = result_queue.get_nowait()
                results.append(result)
                logger.info(f"收到简化结果: {result}")
            except:
                break
        
        worker_process.join(timeout=5)
        if worker_process.is_alive():
            worker_process.terminate()
            worker_process.join()
        
        if len(results) > 0:
            logger.info("✓ 简化worker通信正常")
            return True
        else:
            logger.error("✗ 简化worker通信失败")
            return False
            
    except Exception as e:
        logger.error(f"简化worker测试异常: {e}", exc_info=True)
        return False

def test_manager_objects():
    """测试Manager对象"""
    logger.info("=" * 60)
    logger.info("测试Manager对象")
    logger.info("=" * 60)
    
    try:
        manager = Manager()
        
        # 测试各种Manager对象
        test_list = manager.list([1, 2, 3])
        test_dict = manager.dict({"key": "value"})
        test_value = manager.Value('i', 42)
        test_queue = manager.Queue()
        test_event = manager.Event()
        
        logger.info(f"Manager.list: {list(test_list)}")
        logger.info(f"Manager.dict: {dict(test_dict)}")
        logger.info(f"Manager.Value: {test_value.value}")
        
        test_queue.put("test_item")
        item = test_queue.get()
        logger.info(f"Manager.Queue: {item}")
        
        test_event.set()
        logger.info(f"Manager.Event: {test_event.is_set()}")
        
        logger.info("✓ Manager对象测试正常")
        return True
        
    except Exception as e:
        logger.error(f"Manager对象测试异常: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    logger.info("开始Worker函数详细调试")
    logger.info("=" * 80)
    
    tests = [
        ("Manager对象测试", test_manager_objects),
        ("直接下载测试", test_direct_download),
        ("简化worker测试", test_simple_worker),
        ("Worker通信测试", test_worker_communication),
    ]
    
    results = {}
    for test_name, test_func in tests:
        logger.info(f"\n开始测试: {test_name}")
        try:
            result = test_func()
            results[test_name] = result
            status = "✓ 通过" if result else "✗ 失败"
            logger.info(f"测试 {test_name}: {status}")
        except Exception as e:
            logger.error(f"测试 {test_name} 异常: {e}", exc_info=True)
            results[test_name] = False
    
    # 输出测试总结
    logger.info("\n" + "=" * 80)
    logger.info("Worker调试总结:")
    logger.info("=" * 80)
    for test_name, result in results.items():
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{test_name}: {status}")
    
    # 分析问题
    if results.get("Manager对象测试", False):
        logger.info("✓ Manager对象正常")
    else:
        logger.error("✗ Manager对象有问题")
    
    if results.get("直接下载测试", False):
        logger.info("✓ 直接下载正常")
    else:
        logger.error("✗ 直接下载有问题")
    
    if results.get("简化worker测试", False):
        logger.info("✓ 简化worker通信正常")
    else:
        logger.error("✗ 简化worker通信有问题")
    
    if results.get("Worker通信测试", False):
        logger.info("✓ 完整worker通信正常")
    else:
        logger.error("✗ 完整worker通信有问题")


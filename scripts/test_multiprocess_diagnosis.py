"""多进程下载诊断测试 - 控制变量法"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import time
from datetime import datetime, date

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/multiprocess_diagnosis.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

def test_1_server_connection():
    """测试1：验证服务器连接"""
    logger.info("=" * 80)
    logger.info("测试1：验证服务器连接")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager
    
    server_manager = ServerManager()
    logger.info(f"初始服务器数: {len(server_manager.all_servers)}")
    
    logger.info("开始验证服务器...")
    server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
    
    available = len(server_manager.available_servers)
    logger.info(f"✓ 可用服务器: {available}")
    logger.info(f"前5个可用服务器: {server_manager.available_servers[:5]}")
    
    return available > 0


def test_2_single_symbol_download():
    """测试2：单个品种单周期下载"""
    logger.info("\n" + "=" * 80)
    logger.info("测试2：单个品种单周期下载（单进程）")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager
    from mootdx.quotes import Quotes
    from backend.infrastructure.data_module_vnpy.data_fetcher import _download_single_kline
    
    # 获取服务器
    server_manager = ServerManager()
    if server_manager.verification_status != "completed":
        server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
    
    servers = server_manager.get_available_servers(1)
    if not servers:
        logger.error("❌ 没有可用服务器")
        return False
    
    server = servers[0]
    logger.info(f"使用服务器: {server[0]}:{server[1]}")
    
    # 测试下载
    symbol = "600000"  # 浦发银行
    interval = "1d"
    start_date = date(2024, 10, 1)
    
    logger.info(f"下载测试: {symbol} {interval} from {start_date}")
    
    try:
        quotes = Quotes.factory(server=server, timeout=30, heartbeat=False)
        start_time = time.time()
        
        data = _download_single_kline(quotes, symbol, interval, start_date)
        
        elapsed = time.time() - start_time
        quotes.close()
        
        if data is not None and not data.empty:
            logger.info(f"✓ 下载成功: {len(data)} 条数据，耗时 {elapsed:.2f}秒")
            logger.info(f"数据示例:\n{data.head()}")
            return True
        else:
            logger.error("❌ 下载失败: 数据为空")
            return False
            
    except Exception as e:
        logger.error(f"❌ 下载异常: {e}", exc_info=True)
        return False


def test_3_multiprocess_small_batch():
    """测试3：多进程下载小批量（5个品种，2个周期）"""
    logger.info("\n" + "=" * 80)
    logger.info("测试3：多进程下载小批量（10个任务）")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
    
    # 小批量测试数据
    symbols = ["600000", "600016", "600036", "600048", "600050"]
    intervals = ["1d", "1m"]
    start_date = date(2024, 10, 1)
    
    total_tasks = len(symbols) * len(intervals)
    logger.info(f"总任务数: {total_tasks}")
    logger.info(f"品种: {symbols}")
    logger.info(f"周期: {intervals}")
    
    # 创建下载器（使用较少进程）
    fetcher = MultiProcessStockFetcher()
    fetcher.num_processes = 3  # 只用3个进程
    logger.info(f"进程数: {fetcher.num_processes}")
    
    # 进度回调
    progress_list = []
    def progress_callback(completed, total, symbol, interval):
        progress_list.append((completed, symbol, interval))
        if completed % 5 == 0 or completed == total:
            logger.info(f"进度: {completed}/{total} - {symbol} {interval}")
    
    # 开始下载
    logger.info("开始下载...")
    start_time = time.time()
    
    try:
        results = fetcher.download_batch(
            symbols=symbols,
            intervals=intervals,
            start_date=start_date,
            progress_callback=progress_callback
        )
        
        elapsed = time.time() - start_time
        logger.info(f"\n下载完成，耗时 {elapsed:.2f}秒")
        logger.info(f"返回结果数: {len(results)}")
        logger.info(f"进度回调次数: {len(progress_list)}")
        
        # 检查结果
        success_count = sum(1 for k, v in results.items() if v is not None and not v.empty)
        logger.info(f"✓ 成功下载: {success_count}/{total_tasks}")
        
        if success_count > 0:
            logger.info("前3个结果:")
            for i, (key, df) in enumerate(list(results.items())[:3]):
                if df is not None and not df.empty:
                    logger.info(f"  {key}: {len(df)} 条数据")
        
        return success_count >= total_tasks * 0.5  # 至少50%成功
        
    except Exception as e:
        logger.error(f"❌ 下载失败: {e}", exc_info=True)
        return False


def test_4_worker_process_status():
    """测试4：检查worker进程状态"""
    logger.info("\n" + "=" * 80)
    logger.info("测试4：检查worker进程启动和运行状态")
    logger.info("=" * 80)
    
    from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
    import multiprocessing
    
    fetcher = MultiProcessStockFetcher()
    fetcher.num_processes = 2  # 只用2个进程测试
    
    logger.info("初始化多进程对象...")
    fetcher._init_multiprocess_objects()
    
    # 添加测试任务
    test_symbols = ["600000", "600016"]
    test_intervals = ["1d"]
    start_date = date(2024, 10, 1)
    
    for symbol in test_symbols:
        for interval in test_intervals:
            fetcher.task_queue.put((symbol, interval, start_date))
    
    logger.info(f"任务队列大小: {fetcher.task_queue.qsize()}")
    
    # 准备服务器列表
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager
    server_manager = ServerManager()
    if server_manager.verification_status != "completed":
        server_manager.verify_all_servers_sync(timeout=5, max_workers=20)
    
    servers = server_manager.get_available_servers(3)
    server_list = fetcher.manager.list(servers)
    server_index = fetcher.manager.Value('i', 0)
    
    logger.info(f"可用服务器数: {len(server_list)}")
    
    # 启动worker进程
    logger.info("启动worker进程...")
    fetcher._start_worker_pool(server_list, server_index)
    
    logger.info(f"进程数: {len(fetcher.processes)}")
    
    # 检查进程状态
    time.sleep(2)  # 等待2秒
    
    alive_count = 0
    for i, p in enumerate(fetcher.processes):
        is_alive = p.is_alive()
        logger.info(f"进程 {i}: PID={p.pid}, alive={is_alive}, exitcode={p.exitcode}")
        if is_alive:
            alive_count += 1
    
    logger.info(f"存活进程数: {alive_count}/{len(fetcher.processes)}")
    
    # 监控一段时间
    logger.info("监控10秒...")
    for sec in range(10):
        time.sleep(1)
        
        try:
            task_size = fetcher.task_queue.qsize()
            progress_size = fetcher.progress_queue.qsize()
            result_size = fetcher.result_queue.qsize()
            
            logger.info(f"[{sec+1}s] 任务队列: {task_size}, 进度队列: {progress_size}, 结果队列: {result_size}")
            
            # 收集进度
            while True:
                try:
                    progress = fetcher.progress_queue.get_nowait()
                    logger.info(f"  收到进度: {progress}")
                except:
                    break
                    
        except Exception as e:
            logger.error(f"监控错误: {e}")
    
    # 停止进程
    logger.info("停止所有进程...")
    if fetcher.stop_event:
        fetcher.stop_event.set()
    
    time.sleep(1)
    
    for i, p in enumerate(fetcher.processes):
        if p.is_alive():
            logger.warning(f"进程 {i} 仍在运行，强制终止")
            p.terminate()
            p.join(timeout=2)
    
    logger.info("测试完成")
    return alive_count > 0


def test_5_queue_communication():
    """测试5：队列通信测试"""
    logger.info("\n" + "=" * 80)
    logger.info("测试5：队列通信测试")
    logger.info("=" * 80)
    
    from multiprocessing import Manager, Process, Event
    import queue
    
    manager = Manager()
    task_queue = manager.Queue()
    result_queue = manager.Queue()
    progress_queue = manager.Queue()
    stop_event = manager.Event()
    pause_event = manager.Event()
    pause_event.set()  # 初始为运行状态
    
    # 简单的worker函数
    def simple_worker(worker_id, task_q, result_q, progress_q, stop_evt, pause_evt):
        logger_w = logging.getLogger(f"SimpleWorker-{worker_id}")
        logger_w.info(f"Worker {worker_id} 启动，PID: {os.getpid()}")
        
        processed = 0
        while not stop_evt.is_set():
            pause_evt.wait()
            
            try:
                task = task_q.get(timeout=0.5)
                logger_w.info(f"Worker {worker_id} 收到任务: {task}")
                
                # 模拟处理
                time.sleep(0.5)
                
                result_q.put((f"result_{task}", f"data_{task}"))
                progress_q.put((f"task_{task}", "success"))
                processed += 1
                
            except queue.Empty:
                logger_w.info(f"Worker {worker_id} 队列为空，退出")
                break
        
        logger_w.info(f"Worker {worker_id} 完成，处理了 {processed} 个任务")
    
    # 添加测试任务
    for i in range(5):
        task_queue.put(i)
    
    logger.info(f"添加了 5 个测试任务")
    
    # 启动2个worker
    processes = []
    for i in range(2):
        p = Process(
            target=simple_worker,
            args=(i, task_queue, result_queue, progress_queue, stop_event, pause_event)
        )
        p.start()
        processes.append(p)
        logger.info(f"启动进程 {i}, PID: {p.pid}")
    
    # 监控进度
    completed = 0
    timeout_count = 0
    max_timeout = 100
    
    logger.info("开始收集进度...")
    while completed < 5:
        try:
            progress = progress_queue.get(timeout=0.1)
            completed += 1
            logger.info(f"收到进度 {completed}/5: {progress}")
            timeout_count = 0
        except queue.Empty:
            timeout_count += 1
            if timeout_count >= max_timeout:
                logger.error(f"超时！已完成: {completed}/5")
                break
    
    # 收集结果
    logger.info("收集结果...")
    results = []
    while True:
        try:
            result = result_queue.get_nowait()
            results.append(result)
            logger.info(f"收到结果: {result}")
        except queue.Empty:
            break
    
    logger.info(f"总共收到 {len(results)} 个结果")
    
    # 停止进程
    stop_event.set()
    for p in processes:
        p.join(timeout=2)
    
    return len(results) == 5


if __name__ == "__main__":
    logger.info("开始多进程诊断测试...")
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"当前工作目录: {os.getcwd()}")
    
    results = {}
    
    # 测试1
    try:
        results['test_1_server'] = test_1_server_connection()
    except Exception as e:
        logger.error(f"测试1失败: {e}", exc_info=True)
        results['test_1_server'] = False
    
    # 测试2
    try:
        results['test_2_single'] = test_2_single_symbol_download()
    except Exception as e:
        logger.error(f"测试2失败: {e}", exc_info=True)
        results['test_2_single'] = False
    
    # 测试5：先测试队列通信
    try:
        results['test_5_queue'] = test_5_queue_communication()
    except Exception as e:
        logger.error(f"测试5失败: {e}", exc_info=True)
        results['test_5_queue'] = False
    
    # 测试4
    try:
        results['test_4_worker'] = test_4_worker_process_status()
    except Exception as e:
        logger.error(f"测试4失败: {e}", exc_info=True)
        results['test_4_worker'] = False
    
    # 测试3
    if results.get('test_4_worker', False):
        try:
            results['test_3_batch'] = test_3_multiprocess_small_batch()
        except Exception as e:
            logger.error(f"测试3失败: {e}", exc_info=True)
            results['test_3_batch'] = False
    else:
        logger.warning("跳过测试3（测试4失败）")
        results['test_3_batch'] = False
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)
    for test_name, test_result in results.items():
        status = "✓ 通过" if test_result else "✗ 失败"
        logger.info(f"{test_name}: {status}")
    
    passed = sum(1 for v in results.values() if v)
    logger.info(f"\n通过率: {passed}/{len(results)}")


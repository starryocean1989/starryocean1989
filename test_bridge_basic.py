import sys
import logging
import time
from backend.infrastructure.data_module_vnpy.native_scheduler_bridge import NativeSchedulerBridge

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def test_basic_functionality():
    """测试 NativeSchedulerBridge 基本功能"""
    logger.info("\n=== 开始测试 NativeSchedulerBridge 基本功能 ===")
    
    try:
        # 1. 测试初始化
        logger.info("\n1. 测试初始化...")
        bridge = NativeSchedulerBridge({
            "test_category": {"queue_capacity": 10, "max_workers": 2}
        })
        logger.info(f"✅ Bridge 初始化成功，可用: {bridge.available}")
        
        # 2. 测试任务提交
        logger.info("\n2. 测试简单任务提交...")
        def simple_task(x, y):
            logger.info(f"执行任务: {x} + {y}")
            time.sleep(0.5)  # 模拟耗时操作
            return x + y
        
        future = bridge.submit("test_category", simple_task, args=(3, 4))
        result = future.result(timeout=2.0)
        logger.info(f"✅ 任务执行结果: {result} (期望: 7)")
        assert result == 7, f"任务结果错误: 期望 7, 得到 {result}"
        
        # 3. 测试并发任务
        logger.info("\n3. 测试并发任务...")
        def long_running_task(task_id, duration):
            logger.info(f"任务 {task_id} 开始执行 (预计耗时: {duration}秒)")
            time.sleep(duration)
            logger.info(f"任务 {task_id} 完成")
            return f"task_{task_id}_done"
        
        futures = []
        for i in range(3):
            future = bridge.submit("test_category", long_running_task, args=(i, 1.0))
            futures.append(future)
        
        # 等待所有任务完成
        results = []
        for i, future in enumerate(futures):
            try:
                result = future.result(timeout=5.0)
                results.append(result)
                logger.info(f"✅ 任务 {i} 完成: {result}")
            except Exception as e:
                logger.error(f"❌ 任务 {i} 执行失败: {e}")
                raise
        
        # 4. 测试统计信息
        logger.info("\n4. 检查统计信息...")
        stats = bridge.stats()
        logger.info(f"调度器统计: {stats}")
        
        # 5. 测试关闭
        logger.info("\n5. 测试关闭...")
        bridge.shutdown()
        logger.info("✅ 桥接器已关闭")
        
        return True
        
    except Exception as e:
        logger.exception(f"❌ 测试失败: {e}")
        return False
    finally:
        logger.info("\n=== 测试结束 ===")

if __name__ == "__main__":
    success = test_basic_functionality()
    if success:
        print("\n🎉 所有测试通过！")
    else:
        print("\n❌ 测试失败，请查看日志获取详细信息")

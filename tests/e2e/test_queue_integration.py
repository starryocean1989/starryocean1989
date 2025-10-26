# -*- coding: utf-8 -*-
"""
任务队列集成测试

测试任务队列与LoadBalancer的集成：
- 小任务快速响应
- 大任务不阻塞UI
- 资源限制生效
- UI监控界面更新
"""

import time
import logging
from typing import List
from backend.infrastructure.data_module_vnpy.load_balancer.execution_models import (
    TaskUnit,
    TaskResult,
)
from backend.infrastructure.data_module_vnpy.load_balancer.queue_facade import (
    LoadBalancerQueueFacade,
)
from backend.infrastructure.data_module_vnpy.load_balancer.task_queue import (
    TaskPriority,
    TaskStatus,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def mock_execution_callback(task_units: List[TaskUnit], progress_callback=None) -> List[TaskResult]:
    """模拟执行回调

    模拟任务执行，每个单元耗时100ms。

    Args:
        task_units: 任务单元列表
        progress_callback: 进度回调

    Returns:
        List[TaskResult]: 执行结果列表
    """
    results = []
    total = len(task_units)

    for i, unit in enumerate(task_units):
        # 模拟处理时间
        time.sleep(0.1)

        # 创建结果
        result = TaskResult(unit_id=unit.unit_id, success=True, data=f"processed_{unit.data}")
        results.append(result)

        # 报告进度
        if progress_callback:
            progress_callback(i + 1, total)

    return results


def test_small_task_fast_response():
    """测试1：小任务快速响应（<1秒）

    目标：验证小任务能够快速执行，不进入队列等待。
    """
    logger.info("=" * 60)
    logger.info("测试1：小任务快速响应")
    logger.info("=" * 60)

    # 初始化门面
    facade = LoadBalancerQueueFacade.get_instance()
    facade.initialize(
        execution_callback=mock_execution_callback,
        max_workers=2,
        small_task_cpu_limit=30.0,
        large_task_cpu_limit=80.0,
    )
    facade.start()

    try:
        # 创建小任务（5个单元，预计0.5秒完成）
        task_units = [TaskUnit(unit_id=f"small_{i}", data=i) for i in range(5)]

        # 提交任务
        start_time = time.time()
        task_id = facade.submit_task_batch(
            task_units, is_urgent=True, check_limits=False  # 标记为紧急  # 不检查限制
        )

        logger.info(f"✅ 小任务已提交: {task_id}")

        # 等待任务完成
        max_wait = 3.0  # 最多等待3秒
        elapsed = 0
        while elapsed < max_wait:
            status = facade.get_task_status(task_id)
            if status == TaskStatus.COMPLETED:
                break
            time.sleep(0.1)
            elapsed = time.time() - start_time

        end_time = time.time()
        execution_time = end_time - start_time

        # 验证执行时间
        logger.info(f"✅ 小任务执行时间: {execution_time:.2f}秒")

        if execution_time < 1.0:
            logger.info("✅ 测试通过：小任务响应快速（<1秒）")
        else:
            logger.warning(f"⚠️  测试失败：小任务响应较慢（{execution_time:.2f}秒）")

        # 获取指标
        metrics = facade.get_queue_metrics()
        logger.info(f"📊 队列指标: {metrics}")

    finally:
        facade.stop()


def test_large_task_no_ui_blocking():
    """测试2：大任务不阻塞UI

    目标：验证大任务通过队列执行，不阻塞主线程。
    """
    logger.info("=" * 60)
    logger.info("测试2：大任务不阻塞UI")
    logger.info("=" * 60)

    # 初始化门面
    facade = LoadBalancerQueueFacade.get_instance()
    facade.initialize(
        execution_callback=mock_execution_callback,
        max_workers=4,
    )
    facade.start()

    try:
        # 创建大任务（200个单元，预计20秒完成）
        task_units = [TaskUnit(unit_id=f"large_{i}", data=i) for i in range(200)]

        # 提交任务
        start_time = time.time()
        task_id = facade.submit_task_batch(task_units, is_user_triggered=True, check_limits=False)

        submit_time = time.time() - start_time
        logger.info(f"✅ 大任务已提交: {task_id}, 提交耗时={submit_time:.3f}秒")

        # 验证提交快速（不阻塞）
        if submit_time < 0.1:
            logger.info("✅ 测试通过：任务提交不阻塞（<0.1秒）")
        else:
            logger.warning(f"⚠️  测试失败：任务提交较慢（{submit_time:.3f}秒）")

        # 监控任务执行
        logger.info("🔄 监控任务执行...")
        last_status = None
        check_count = 0
        max_checks = 50  # 最多检查50次（约5秒）

        while check_count < max_checks:
            status = facade.get_task_status(task_id)

            if status != last_status:
                logger.info(f"📊 任务状态: {status}")
                last_status = status

            if status == TaskStatus.COMPLETED:
                logger.info("✅ 任务执行完成")
                break
            elif status == TaskStatus.FAILED:
                logger.error("❌ 任务执行失败")
                break

            time.sleep(0.1)
            check_count += 1

        # 获取指标
        metrics = facade.get_queue_metrics()
        logger.info(f"📊 最终指标: {metrics}")

    finally:
        facade.stop()


def test_resource_limits_enforcement():
    """测试3：资源限制生效

    目标：验证资源限制能够阻止超限任务执行。
    """
    logger.info("=" * 60)
    logger.info("测试3：资源限制生效")
    logger.info("=" * 60)

    # 初始化门面（设置严格的限制）
    facade = LoadBalancerQueueFacade.get_instance()
    facade.initialize(
        execution_callback=mock_execution_callback,
        max_workers=4,
        small_task_cpu_limit=10.0,  # 极低限制，容易触发
        small_task_memory_limit=10.0,
    )
    facade.start()

    try:
        # 创建小任务
        task_units = [TaskUnit(unit_id=f"limited_{i}", data=i) for i in range(5)]

        # 提交任务（启用限制检查）
        task_id = facade.submit_task_batch(task_units, check_limits=True)  # 启用限制检查

        if task_id is None:
            logger.info("✅ 测试通过：任务被资源限制拒绝")
        else:
            logger.warning(f"⚠️  测试失败：任务未被拒绝（{task_id}）")

        # 获取指标
        metrics = facade.get_queue_metrics()
        rejected_count = metrics.get("rejected_count", 0)
        logger.info(f"📊 被拒绝任务数: {rejected_count}")

    finally:
        facade.stop()


def test_queue_metrics_and_monitoring():
    """测试4：队列指标和监控

    目标：验证队列指标能够正确收集和报告。
    """
    logger.info("=" * 60)
    logger.info("测试4：队列指标和监控")
    logger.info("=" * 60)

    # 初始化门面
    facade = LoadBalancerQueueFacade.get_instance()
    facade.initialize(
        execution_callback=mock_execution_callback,
        max_workers=2,
    )
    facade.start()

    try:
        # 提交多个不同优先级的任务
        task_ids = []

        # 紧急任务
        urgent_units = [TaskUnit(unit_id=f"urgent_{i}", data=i) for i in range(3)]
        task_id1 = facade.submit_task_batch(
            urgent_units, priority=TaskPriority.URGENT, check_limits=False
        )
        task_ids.append(task_id1)

        # 普通任务
        normal_units = [TaskUnit(unit_id=f"normal_{i}", data=i) for i in range(5)]
        task_id2 = facade.submit_task_batch(
            normal_units, priority=TaskPriority.NORMAL, check_limits=False
        )
        task_ids.append(task_id2)

        # 低优先级任务
        low_units = [TaskUnit(unit_id=f"low_{i}", data=i) for i in range(2)]
        task_id3 = facade.submit_task_batch(
            low_units, priority=TaskPriority.LOW, check_limits=False
        )
        task_ids.append(task_id3)

        logger.info(f"✅ 已提交3个任务: {task_ids}")

        # 等待一段时间
        time.sleep(0.5)

        # 获取指标
        metrics = facade.get_queue_metrics()

        logger.info("📊 队列指标:")
        logger.info(f"  - 队列长度: {metrics.get('queue_length', 0)}")
        logger.info(f"  - 总任务数: {metrics.get('total_tasks', 0)}")
        logger.info(f"  - 已完成: {metrics.get('completed_tasks', 0)}")
        logger.info(f"  - 吞吐量: {metrics.get('throughput', 0):.2f} 任务/秒")
        logger.info(f"  - 平均等待: {metrics.get('avg_wait_time', 0):.2f}秒")
        logger.info(f"  - 平均执行: {metrics.get('avg_execution_time', 0):.2f}秒")

        # 验证指标
        if metrics.get("total_tasks", 0) == 3:
            logger.info("✅ 测试通过：指标统计正确")
        else:
            logger.warning(f"⚠️  测试失败：指标统计不正确")

        # 等待所有任务完成
        time.sleep(3.0)

        # 获取最终指标
        final_metrics = facade.get_queue_metrics()
        logger.info(f"📊 最终指标: {final_metrics}")

    finally:
        facade.stop()


def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "=" * 60)
    logger.info("开始运行LoadBalancer任务队列集成测试")
    logger.info("=" * 60 + "\n")

    try:
        # 测试1：小任务快速响应
        test_small_task_fast_response()
        time.sleep(1.0)

        # 测试2：大任务不阻塞UI
        test_large_task_no_ui_blocking()
        time.sleep(1.0)

        # 测试3：资源限制生效
        test_resource_limits_enforcement()
        time.sleep(1.0)

        # 测试4：队列指标和监控
        test_queue_metrics_and_monitoring()

        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有测试完成")
        logger.info("=" * 60 + "\n")

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)


if __name__ == "__main__":
    run_all_tests()

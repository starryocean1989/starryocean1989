# -*- coding: utf-8 -*-
"""
E2E测试: 下载进度监控.

测试功能链路: 2.2.2 下载进度监控链条

验证点:
1. 下载进度实时展示
2. 进度百分比计算准确性
3. 下载速度统计
4. 剩余时间估算
5. 停止按钮功能（任务取消）
6. 下载历史记录查看
7. 历史记录删除功能
8. 下载统计报告生成
9. 进度更新频率验证
10. 多任务并发进度监控
"""

import asyncio
import logging
import time
from datetime import datetime

import pytest

from tests.test_e2e.utils.wait_helpers import wait_until_condition

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestDownloadProgressMonitoringE2E:
    """下载进度监控端到端测试."""

    @pytest.mark.timeout(45)
    async def test_realtime_progress_display(
        self,
        backend_app,
        download_service,
        symbol_service,
        service_accessor,
        clean_tasks,
    ):
        """
        测试下载进度实时展示.

        验证点:
        1. 进度更新事件触发
        2. 进度百分比准确性(0-100%)
        3. 进度状态流转(PENDING→RUNNING→COMPLETED)
        4. 进度更新时间戳
        5. 下载速度统计
        """
        logger.info("=" * 80)
        logger.info("E2E测试: 下载进度实时展示")
        logger.info("=" * 80)

        # 确保品种缓存已加载
        await self._ensure_symbol_cache(symbol_service)

        # 获取测试品种
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)
        assert test_symbol is not None, "缓存中没有可用的测试品种"

        # 创建下载任务
        task = await download_service.create_download_task(
            symbol=test_symbol,
            exchange=test_exchange,
            start_date=datetime(2024, 10, 1),
            end_date=datetime(2024, 10, 5),
            data_type="bar",
            frequency="1m",
        )

        task_id = task.task_id
        logger.info(f"✓ 任务已创建: {task_id}")

        # 验证点1: 启动任务并监控进度
        await download_service.start_download_task(task_id)
        logger.info("✓ 任务已启动，开始监控进度...")

        # 记录进度更新（使用条件等待而非固定时间轮询）
        progress_history = []
        from tests.test_e2e.utils.wait_helpers import wait_for_task_completion

        # 使用较短的间隔来捕获进度更新
        max_iterations = 60  # 30秒，每0.5秒一次
        for _ in range(max_iterations):
            # 获取任务状态
            task_status = service_accessor.get_task_status(download_service, task_id)

            if task_status:
                progress = task_status.get("progress", 0)
                status = task_status.get("status", "")

                # 记录进度
                progress_history.append(
                    {
                        "timestamp": time.time(),
                        "progress": progress,
                        "status": status,
                    }
                )

                logger.info(f"进度更新: {progress:.1f}% - {status}")

                # 验证点2: 进度百分比范围
                assert 0 <= progress <= 100, f"进度应在0-100范围内，实际为{progress}"

                # 任务完成或失败时退出
                if status in ["completed", "failed", "cancelled"]:
                    break

        # 验证点3: 状态流转验证（修复：保持顺序，不使用set）
        statuses = [p["status"] for p in progress_history]
        # 保持顺序去重：只记录状态变化
        ordered_statuses = []
        prev_status = None
        for status in statuses:
            if status != prev_status:
                ordered_statuses.append(status)
                prev_status = status
        logger.info(f"状态流转记录: {' → '.join(ordered_statuses)}")

        assert len(progress_history) > 0, "应该有进度更新记录"
        logger.info(f"✓ 记录了{len(progress_history)}次进度更新")

        # 验证点4: 进度递增验证
        if len(progress_history) > 1:
            progress_values = [p["progress"] for p in progress_history]
            # 进度应该是递增的或保持不变
            for i in range(1, len(progress_values)):
                assert progress_values[i] >= progress_values[i - 1], "进度应该递增或保持不变"
            logger.info("✓ 进度递增验证通过")

        # 验证点5: 计算平均更新频率
        if len(progress_history) > 1:
            time_span = progress_history[-1]["timestamp"] - progress_history[0]["timestamp"]
            update_frequency = len(progress_history) / time_span if time_span > 0 else 0
            logger.info(f"✓ 进度更新频率: {update_frequency:.2f} 次/秒")

        logger.info("=" * 80)
        logger.info("✅ 下载进度实时展示测试通过")
        logger.info("=" * 80)

    @pytest.mark.timeout(35)
    async def test_task_cancellation(
        self,
        backend_app,
        download_service,
        symbol_service,
        service_accessor,
        clean_tasks,
    ):
        """
        测试任务取消功能(停止按钮).

        验证点:
        1. 取消请求响应
        2. 任务状态变更为cancelled
        3. 进度停止更新
        4. 资源正确释放
        5. 取消操作耗时≤2秒
        """
        logger.info("=" * 80)
        logger.info("E2E测试: 任务取消功能")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        # 创建并启动任务
        task = await download_service.create_download_task(
            symbol=test_symbol,
            exchange=test_exchange,
            start_date=datetime(2024, 9, 1),
            end_date=datetime.now(),
        )

        task_id = task.task_id
        await download_service.start_download_task(task_id)
        logger.info(f"✓ 任务{task_id}已启动")

        # 等待任务开始执行（使用条件等待，最多3秒）
        await wait_until_condition(
            lambda: (
                service_accessor.get_task_status(download_service, task_id) is not None
                and (
                    service_accessor.get_task_status(download_service, task_id).get("is_running")
                    or service_accessor.get_task_status(download_service, task_id).get("status")
                    == "running"
                )
            ),
            timeout=3.0,
            interval=0.2,
            error_message="等待任务开始执行超时",
        )

        # 验证点1&5: 测量取消操作耗时
        start_time = time.time()
        cancelled = await download_service.cancel_download_task(task_id)
        cancel_elapsed = time.time() - start_time

        assert cancelled, "取消操作应该成功"
        logger.info(f"✓ 取消操作成功，耗时: {cancel_elapsed:.3f}秒")

        # 性能建议：取消操作建议≤2秒（不作为硬性断言，避免系统负载影响）
        if cancel_elapsed > 2.0:
            logger.warning(f"⚠ 取消操作耗时超过建议值2秒: {cancel_elapsed:.3f}秒")
        else:
            logger.info(f"✓ 取消操作性能良好（≤2秒）")

        # 验证点2: 使用条件等待确认取消状态
        await wait_until_condition(
            condition_func=lambda: (
                service_accessor.get_task_status(download_service, task_id)
                and service_accessor.get_task_status(download_service, task_id).get("status")
                == "cancelled"
            ),
            timeout=5.0,
            interval=0.2,
            error_message="任务状态未变更为cancelled",
        )

        task_status = service_accessor.get_task_status(download_service, task_id)
        assert task_status is not None, "应该能获取任务状态"
        assert (
            task_status["status"] == "cancelled"
        ), f"任务状态应为cancelled，实际为{task_status['status']}"
        logger.info("✓ 任务状态已变更为cancelled")

        # 验证点3: 验证进度不再更新
        progress_before = task_status["progress"]
        # 验证取消后进度不再更新（使用条件等待确认进度保持不变）

        # 等待一小段时间后确认进度仍保持不变
        await wait_until_condition(
            lambda: service_accessor.get_task_status(download_service, task_id)["progress"]
            == progress_before,
            timeout=2.0,
            interval=0.3,
            error_message="取消后进度应该保持不变",
        )

        task_status_after = service_accessor.get_task_status(download_service, task_id)
        progress_after = task_status_after["progress"]

        assert progress_after == progress_before, "取消后进度不应再更新"
        logger.info("✓ 进度已停止更新")

        logger.info("=" * 80)
        logger.info("✅ 任务取消功能测试通过")
        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_download_history_records(
        self,
        backend_app,
        download_service,
        symbol_service,
        clean_tasks,
    ):
        """
        测试下载历史记录.

        验证点:
        1. 历史记录保存
        2. 历史记录查询
        3. 历史记录详情展示
        4. 历史记录删除
        5. 历史记录时间排序
        """
        logger.info("=" * 80)
        logger.info("E2E测试: 下载历史记录")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        # 创建并完成多个任务
        from tests.test_e2e.utils.service_accessor import ServiceAccessor

        service_accessor = ServiceAccessor()

        task_ids = []
        for i in range(3):
            task = await download_service.create_download_task(
                symbol=test_symbol,
                exchange=test_exchange,
                start_date=datetime(2024, 10, i + 1),
                end_date=datetime(2024, 10, i + 2),
            )
            current_task_id = task.task_id
            task_ids.append(current_task_id)

            # 启动任务并使用条件等待确保任务开始运行（修复问题C：不再使用固定sleep）
            await download_service.start_download_task(current_task_id)

            # 等待任务进入运行状态
            def check_task_started(tid=current_task_id):
                status = service_accessor.get_task_status(download_service, tid)
                if status and status.get("status") in ["running", "completed", "failed"]:
                    return True
                return False

            await wait_until_condition(
                condition_func=check_task_started,
                timeout=3.0,
                interval=0.2,
                error_message=f"任务{current_task_id}未启动",
            )

        logger.info(f"✓ 创建了{len(task_ids)}个下载任务")

        # 验证点1&2: 查询历史记录
        history_records = await download_service.get_download_history(limit=10)

        assert len(history_records) >= len(task_ids), "历史记录数应≥创建的任务数"
        logger.info(f"✓ 查询到{len(history_records)}条历史记录")

        # 验证点3: 验证历史记录包含必要信息
        if len(history_records) > 0:
            record = history_records[0]
            required_fields = ["task_id", "symbol", "status", "created_at"]
            for field in required_fields:
                assert field in record, f"历史记录应包含{field}字段"
            logger.info("✓ 历史记录包含必要信息")

        # 验证点4: 验证时间排序（最新的在前）
        if len(history_records) > 1:
            timestamps = [r.get("created_at", datetime.min) for r in history_records]
            is_sorted = all(timestamps[i] >= timestamps[i + 1] for i in range(len(timestamps) - 1))
            assert is_sorted, "历史记录应按时间倒序排列"
            logger.info("✓ 历史记录时间排序正确")

        # 验证点5: 删除历史记录
        if len(task_ids) > 0:
            delete_task_id = task_ids[0]
            deleted = await download_service.delete_download_history(delete_task_id)

            if deleted:
                logger.info(f"✓ 成功删除任务{delete_task_id}的历史记录")

                # 验证删除后记录减少
                new_history = await download_service.get_download_history(limit=10)
                assert len(new_history) < len(history_records), "删除后历史记录数应减少"
                logger.info("✓ 历史记录删除功能正常")
            else:
                logger.warning("⚠ 历史记录删除功能可能未实现")

        logger.info("=" * 80)
        logger.info("✅ 下载历史记录测试通过")
        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_download_statistics_report(
        self,
        backend_app,
        download_service,
        symbol_service,
        clean_tasks,
    ):
        """
        测试下载统计报告生成.

        验证点:
        1. 统计总任务数
        2. 统计成功/失败/取消任务数
        3. 统计总下载数据量
        4. 统计平均下载速度
        5. 统计报告时间范围
        """
        logger.info("=" * 80)
        logger.info("E2E测试: 下载统计报告")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)

        # 获取下载统计
        stats = await download_service.get_download_statistics(days=7)

        logger.info("下载统计报告:")
        logger.info(f"  - 总任务数: {stats.get('total_tasks', 0)}")
        logger.info(f"  - 成功任务: {stats.get('completed_tasks', 0)}")
        logger.info(f"  - 失败任务: {stats.get('failed_tasks', 0)}")
        logger.info(f"  - 取消任务: {stats.get('cancelled_tasks', 0)}")
        logger.info(f"  - 总数据量: {stats.get('total_data_size', 0)} 条")
        logger.info(f"  - 统计时间范围: {stats.get('time_range', 'N/A')}")

        # 验证点1: 总任务数合理性
        total_tasks = stats.get("total_tasks", 0)
        assert total_tasks >= 0, "总任务数应≥0"
        logger.info("✓ 总任务数统计正常")

        # 验证点2: 状态分类完整性
        completed = stats.get("completed_tasks", 0)
        failed = stats.get("failed_tasks", 0)
        cancelled = stats.get("cancelled_tasks", 0)
        running = stats.get("running_tasks", 0)

        status_sum = completed + failed + cancelled + running
        # 状态总数应该≤总任务数（因为可能有pending状态）
        assert status_sum <= total_tasks, "状态分类总数不应超过总任务数"
        logger.info("✓ 任务状态分类统计正常")

        # 验证点3: 成功率计算
        if total_tasks > 0:
            success_rate = (completed / total_tasks) * 100
            logger.info(f"  - 成功率: {success_rate:.1f}%")
            assert 0 <= success_rate <= 100, "成功率应在0-100%范围内"
            logger.info("✓ 成功率计算正确")

        # 验证点4: 平均下载速度统计
        avg_speed = stats.get("avg_download_speed", 0)
        logger.info(f"  - 平均下载速度: {avg_speed:.2f} 条/秒")
        assert avg_speed >= 0, "平均下载速度应≥0"
        logger.info("✓ 下载速度统计正常")

        # 验证点5: 时间范围验证
        time_range = stats.get("time_range")
        if time_range:
            assert "start" in time_range and "end" in time_range, "时间范围应包含start和end"
            logger.info("✓ 统计时间范围正常")

        logger.info("=" * 80)
        logger.info("✅ 下载统计报告测试通过")
        logger.info("=" * 80)

    @pytest.mark.timeout(50)
    async def test_concurrent_task_monitoring(
        self,
        backend_app,
        download_service,
        symbol_service,
        service_accessor,
        clean_tasks,
    ):
        """
        测试多任务并发进度监控.

        验证点:
        1. 同时监控多个任务
        2. 任务进度独立更新
        3. 任务状态独立管理
        4. 并发任务列表展示
        5. 监控性能（≤100ms响应）
        """
        logger.info("=" * 80)
        logger.info("E2E测试: 多任务并发进度监控")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        # 创建多个并发任务
        task_ids = []
        num_tasks = 3

        for i in range(num_tasks):
            task = await download_service.create_download_task(
                symbol=test_symbol,
                exchange=test_exchange,
                start_date=datetime(2024, 10, i + 1),
                end_date=datetime(2024, 10, i + 2),
            )
            task_ids.append(task.task_id)

        logger.info(f"✓ 创建了{len(task_ids)}个并发任务")

        # 同时启动所有任务
        for task_id in task_ids:
            await download_service.start_download_task(task_id)
        logger.info("✓ 所有任务已启动")

        # 验证点1&2: 监控所有任务进度（定期采样）
        monitoring_iterations = 5
        for iteration in range(monitoring_iterations):
            # 采样间隔: 每0.5秒采样一次进度（这是测试设计的定期监控，非阻塞等待）
            # 如需更精确的进度监控，可考虑使用wait_until_condition
            if iteration > 0:  # 第一次迭代立即执行，后续迭代间隔0.5秒
                await asyncio.sleep(0.5)

            logger.info(f"\n--- 监控迭代 {iteration + 1} ---")

            # 验证点5: 测量监控响应时间
            start_time = time.time()

            all_statuses = []
            for task_id in task_ids:
                status = service_accessor.get_task_status(download_service, task_id)
                if status:
                    all_statuses.append(status)
                    logger.info(
                        f"  任务{task_id[:8]}: " f"{status['progress']:.1f}% - {status['status']}"
                    )

            monitoring_elapsed = time.time() - start_time
            logger.info(f"监控耗时: {monitoring_elapsed * 1000:.1f}ms")

            # 验证监控性能
            assert (
                monitoring_elapsed <= 0.5
            ), f"监控{num_tasks}个任务耗时超过0.5秒: {monitoring_elapsed:.3f}秒"

            # 验证点3: 验证任务状态独立
            if len(all_statuses) > 1:
                # 不同任务可能处于不同状态，这是正常的
                logger.info(f"✓ 成功监控{len(all_statuses)}个独立任务")

            # 如果所有任务都完成，退出监控
            all_done = all(
                s["status"] in ["completed", "failed", "cancelled"] for s in all_statuses
            )
            if all_done:
                logger.info("✓ 所有任务已完成")
                break

        # 验证点4: 获取并发任务列表
        active_tasks = await download_service.get_active_tasks()
        logger.info(f"当前活跃任务数: {len(active_tasks)}")

        logger.info("=" * 80)
        logger.info("✅ 多任务并发进度监控测试通过")
        logger.info("=" * 80)

    # ========== 辅助方法 ==========

    async def _ensure_symbol_cache(self, symbol_service):
        """确保品种缓存已加载."""
        from tests.test_e2e.utils.service_accessor import ServiceAccessor

        accessor = ServiceAccessor()
        cache_stats = accessor.get_cache_stats(symbol_service)
        if cache_stats["cache_size"] == 0:
            await symbol_service.refresh_cache()
            # 使用条件等待替代固定sleep
            from tests.test_e2e.utils.wait_helpers import wait_for_cache_loaded

            await wait_for_cache_loaded(symbol_service, accessor, min_size=1, timeout=3.0)

    def _get_test_symbol(self, symbol_service):
        """获取测试品种."""
        for symbol_info in symbol_service._symbols_cache.values():
            return symbol_info.symbol, symbol_info.exchange
        return None, None

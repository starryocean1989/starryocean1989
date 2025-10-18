# -*- coding: utf-8 -*-
"""
服务器池问题诊断脚本

直接测试AsyncSmartIPPool的启动流程，找出为什么测速任务没有完成
"""

import asyncio
import logging
import time
from backend.infrastructure.tdx_asyncio import AsyncSmartIPPool, HQ_HOSTS_ALL

# 配置详细日志
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("Diagnosis")


async def test_smart_pool():
    """测试AsyncSmartIPPool的启动流程"""
    logger.info("=" * 60)
    logger.info("开始诊断测试")
    logger.info("=" * 60)

    try:
        # 创建智能IP池（只使用10个服务器进行快速测试）
        servers = [(h[1], h[2]) for h in HQ_HOSTS_ALL[:10]]
        logger.info(f"准备测试 {len(servers)} 个服务器")

        pool = AsyncSmartIPPool(
            servers=servers, update_interval=600.0, test_timeout=2.0, max_fail_time=10.0
        )

        logger.info("AsyncSmartIPPool 创建成功")
        logger.info("=" * 60)

        # 测试start方法
        logger.info("开始调用 pool.start()...")
        start_time = time.time()

        # 添加30秒超时
        try:
            await asyncio.wait_for(pool.start(), timeout=30.0)
            elapsed = time.time() - start_time
            logger.info(f"✅ pool.start() 完成，耗时 {elapsed:.2f}秒")
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.error(f"❌ pool.start() 超时（>{elapsed:.0f}秒）")
            logger.error("测速任务卡住，这是问题的根源！")
            return False

        # 检查结果
        logger.info("=" * 60)
        if pool.sorted_servers:
            logger.info(f"✅ 测速成功：{len(pool.sorted_servers)} 个可用服务器")
            logger.info(f"最快服务器：{pool.sorted_servers[0]}")
        else:
            logger.error("❌ 测速完成但没有可用服务器")

        return True

    except Exception as e:
        logger.error(f"❌ 测试过程出现异常: {e}", exc_info=True)
        return False


def main():
    """主函数"""
    logger.info("启动诊断脚本...")
    logger.info("Python asyncio 版本检查：")
    logger.info(f"  asyncio.wait_for: {hasattr(asyncio, 'wait_for')}")

    # 运行测试
    result = asyncio.run(test_smart_pool())

    if result:
        logger.info("✅ 诊断完成：测速正常")
    else:
        logger.error("❌ 诊断完成：发现问题")


if __name__ == "__main__":
    main()

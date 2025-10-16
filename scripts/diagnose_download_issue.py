# -*- coding: utf-8 -*-
"""诊断下载问题 - 直接模拟前端调用流程."""
import sys
import logging
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 配置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    """模拟前端下载流程."""
    logger.info("=" * 80)
    logger.info("模拟前端下载流程诊断")
    logger.info("=" * 80)

    try:
        # 直接使用vnpy引擎
        from vnpy.event import EventEngine
        from vnpy.trader.engine import MainEngine
        from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine

        # 创建vnpy引擎
        logger.info("创建vnpy引擎...")
        event_engine = EventEngine()
        main_engine = MainEngine(event_engine)

        # 创建中国股票引擎
        logger.info("创建ChinaStockEngine...")
        china_stock_engine = ChinaStockEngine(main_engine, event_engine)

        logger.info("=" * 80)
        logger.info("开始测试下载...")
        logger.info("=" * 80)

        # 直接调用引擎的下载方法
        start_date = "2025-10-06"  # 最近10天

        logger.info(f"调用 download_incremental(start_date={start_date})")
        success = china_stock_engine.download_incremental(start_date=start_date)

        logger.info("=" * 80)
        logger.info(f"download_incremental 返回值: {success}")
        logger.info(f"  类型: {type(success)}")
        logger.info("=" * 80)

        # 等待下载线程运行
        import time

        logger.info("等待5秒，让下载线程执行...")
        time.sleep(5)

        # 检查进度
        progress = china_stock_engine.get_download_progress()
        logger.info("当前下载进度:")
        logger.info(f"  {progress}")

        # 再等待
        logger.info("继续等待15秒...")
        time.sleep(15)

        # 再次检查进度
        progress = china_stock_engine.get_download_progress()
        logger.info("最终下载进度:")
        logger.info(f"  {progress}")

    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()

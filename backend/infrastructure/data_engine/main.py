# -*- coding: utf-8 -*-

"""数据引擎主程序入口."""

import asyncio
import logging
from datetime import datetime
from typing import List

from .adapters.tdx_adapter import TDXDataAdapter as TdxAdapter
from .engine import DataEngine
from .models import Quote
from .scheduler import AbstractAdapter, Scheduler
from .utils import setup_logging
from .vnpy_datafeed import VnpyDataPusher

logger = logging.getLogger(__name__)


class TDXAdapterWrapper(AbstractAdapter):
    """TDX适配器包装器,使其兼容AbstractAdapter接口."""

    def __init__(self, tdx_adapter: TdxAdapter):
        """初始化TDX适配器包装器."""
        self.tdx_adapter = tdx_adapter

    async def get_quotes(self) -> List[Quote]:
        """获取行情数据并转换为Quote对象."""
        # 获取一些默认的股票代码
        symbols = ["000001", "000002", "600000", "600036"]
        raw_quotes = await self.tdx_adapter.get_quotes(symbols)

        quotes = []
        for raw_quote in raw_quotes:
            try:
                quote = Quote(
                    symbol=raw_quote.get("symbol", ""),
                    price=float(raw_quote.get("price", 0.0)),
                    volume=int(raw_quote.get("volume", 0)),
                    timestamp=datetime.now()
                )
                quotes.append(quote)
            except (ValueError, TypeError) as e:
                logger.warning("转换行情数据失败: %s", e)
                continue

        return quotes


async def main() -> None:
    """主函数,启动数据引擎服务."""
    # 1. 设置日志
    setup_logging(level=logging.INFO)

    # 2. 初始化组件
    #    - 数据适配器:负责从不同数据源获取数据
    #    - VnPy数据推送器:负责将数据推送到VnPy系统
    #    - 调度器:负责协调各个适配器的数据获取
    #    - 数据引擎:负责整体的数据处理流程

    # 配置适配器
    tdx_config = {
        "host": "localhost",
        "port": 7709,
        "timeout": 30,
        "max_retry": 3,
    }
    tdx_adapter = TdxAdapter(tdx_config)
    adapters = [TDXAdapterWrapper(tdx_adapter)]  # 可以添加更多适配器

    # 3. 创建数据推送器
    pusher = VnpyDataPusher()

    # 4. 创建调度器
    scheduler = Scheduler(adapters)

    # 5. 创建数据引擎
    engine = DataEngine(scheduler, pusher, poll_interval=1)

    try:
        # 7. 启动数据引擎
        logger.info("启动数据引擎...")
        await engine.start()

        logger.info("数据引擎启动成功,等待键盘中断...")

        # 8. 保持运行
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("收到键盘中断信号,停止数据引擎...")

    except (OSError, ValueError, TypeError) as e:
        logger.error("数据引擎运行出错: %s", e)

    finally:
        # 9. 停止数据引擎
        logger.info("停止数据引擎...")
        await engine.stop()
        logger.info("数据引擎已停止")


if __name__ == "__main__":
    # 运行主函数
    asyncio.run(main())

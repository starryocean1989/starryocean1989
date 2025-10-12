# -*- coding: utf-8 -*-
"""
多进程工作器模块

为多进程数据下载提供工作进程函数
每个进程有独立的GIL，实现真正的并行计算
"""

import logging
import queue
import time
from datetime import datetime, timedelta, date
from typing import Optional, Tuple

import pandas as pd

# 导入日期时间解码器
from backend.infrastructure.data_module_vnpy.datetime_decoder import TdxDateTimeDecoder


def download_worker_process(
    worker_id: int,
    server: Tuple[str, int],
    task_queue,
    result_queue,
    progress_queue,
    stop_event,
    pause_event,
):
    """
    工作进程函数（每个进程有独立的GIL）

    Args:
        worker_id: 工作进程ID
        server: 服务器地址(ip, port)
        task_queue: 任务队列
        result_queue: 结果队列
        progress_queue: 进度队列
        stop_event: 停止事件（multiprocessing.Event）
        pause_event: 暂停事件（multiprocessing.Event）
    """
    # 进程内创建独立的日志和连接
    logger = logging.getLogger(f"Worker-{worker_id}")
    logger.setLevel(logging.INFO)

    quotes = None
    processed_count = 0

    try:
        # 创建独立的mootdx连接
        logger.info("进程 %d 正在连接服务器 %s:%d", worker_id, server[0], server[1])

        # 优先使用mootdx.Quotes（支持ETF）
        try:
            from mootdx.quotes import Quotes

            quotes = Quotes.factory(server=server, timeout=5, heartbeat=False)
            logger.info(
                "✅ 进程 %d 使用mootdx.Quotes连接成功: %s:%d", worker_id, server[0], server[1]
            )

        except Exception as e:
            logger.warning("进程 %d mootdx.Quotes连接失败: %s，尝试TdxHq_API降级", worker_id, e)

            # 降级方案：使用TdxHq_API
            try:
                from tdxpy.hq import TdxHq_API

                client = TdxHq_API(heartbeat=False, auto_retry=False, raise_exception=False)
                client.connect(server[0], server[1], time_out=5)

                # 简单的包装器
                class QuotesWrapper:
                    def __init__(self, client, server_info):
                        self.client = client
                        self.server = server_info

                    def bars(self, symbol, frequency, start=0, offset=800, **kwargs):
                        """兼容mootdx.Quotes.bars接口"""
                        # 频率映射
                        freq_map = {
                            "1m": 8,
                            "1min": 8,
                            "5m": 0,
                            "5min": 0,
                            "15m": 1,
                            "15min": 1,
                            "30m": 2,
                            "30min": 2,
                            "1h": 3,
                            "60min": 3,
                            "1d": 9,
                            "day": 9,
                        }
                        category = freq_map.get(frequency, 9)

                        # 市场判断：0=深圳，1=上海，2=北交所
                        if symbol.startswith(("6", "688")):
                            market = 1  # 上海
                        elif symbol.startswith(("8", "9", "4")):
                            market = 2  # 北交所
                        else:
                            market = 0  # 深圳

                        # 使用传入的offset参数（与mootdx.Quotes.bars()一致）
                        offset = min(int(offset), 800)

                        # 获取数据
                        data = self.client.get_security_bars(
                            category, market, symbol, 0, int(offset)
                        )

                        if not data:
                            return None

                        # 转换为DataFrame
                        df = pd.DataFrame(data)

                        if df.empty:
                            return None

                        # 🚀 关键：使用TdxDateTimeDecoder解码日期时间字段
                        df = TdxDateTimeDecoder.decode_dataframe(df, frequency)

                        # 字段名称标准化
                        if "vol" in df.columns and "volume" not in df.columns:
                            df["volume"] = df["vol"]

                        # 设置index
                        if not df.empty and "datetime" in df.columns:
                            df.index = df["datetime"]

                        return df

                    def close(self):
                        try:
                            self.client.close()
                        except:
                            pass

                quotes = QuotesWrapper(client, server)
                logger.info(
                    "✅ 进程 %d 使用TdxHq_API降级连接成功: %s:%d", worker_id, server[0], server[1]
                )

            except Exception as inner_e:
                logger.error("进程 %d 所有连接方式均失败: %s", worker_id, inner_e)
                return

        # 工作循环
        while not stop_event.is_set():
            # 检查暂停
            if not pause_event.is_set():
                time.sleep(0.1)
                continue

            try:
                # 从队列获取任务（timeout避免永久阻塞）
                task = task_queue.get(timeout=0.5)

                symbol, interval, start_date = task

                # 执行下载
                try:
                    data = _download_single_kline(quotes, symbol, interval, start_date, logger)

                    # 将DataFrame转换为可序列化的dict
                    if data is not None and isinstance(data, pd.DataFrame) and not data.empty:
                        # 转换为dict格式（可序列化）
                        try:
                            data_dict = {
                                "datetime": (
                                    data["datetime"].astype(str).tolist()
                                    if "datetime" in data.columns
                                    else []
                                ),
                                "open": data["open"].tolist() if "open" in data.columns else [],
                                "high": data["high"].tolist() if "high" in data.columns else [],
                                "low": data["low"].tolist() if "low" in data.columns else [],
                                "close": data["close"].tolist() if "close" in data.columns else [],
                                "volume": (
                                    data["volume"].tolist() if "volume" in data.columns else []
                                ),
                            }
                            result_queue.put((f"{symbol}_{interval}", data_dict))
                            logger.debug(
                                "进程 %d: ✅ %s %s - %d条数据",
                                worker_id,
                                symbol,
                                interval,
                                len(data),
                            )
                        except Exception as conv_err:
                            logger.error(
                                "进程 %d: DataFrame转换失败 %s %s: %s",
                                worker_id,
                                symbol,
                                interval,
                                conv_err,
                            )
                            result_queue.put((f"{symbol}_{interval}", None))
                    else:
                        logger.warning("进程 %d: ⚠️ %s %s 返回空数据", worker_id, symbol, interval)
                        result_queue.put((f"{symbol}_{interval}", None))

                    # 更新进度
                    progress_queue.put((symbol, interval))
                    processed_count += 1

                except Exception as download_err:
                    logger.error(
                        "进程 %d 下载失败 %s %s: %s", worker_id, symbol, interval, download_err
                    )
                    result_queue.put((f"{symbol}_{interval}", None))
                    progress_queue.put((symbol, interval))

            except queue.Empty:
                # 队列空，继续等待
                continue
            except Exception as e:
                logger.error("进程 %d 任务处理异常: %s", worker_id, e)

        logger.info("进程 %d 收到停止信号，已处理 %d 个任务", worker_id, processed_count)

    except Exception as e:
        logger.error("进程 %d 初始化失败: %s", worker_id, e, exc_info=True)

    finally:
        # 清理连接
        if quotes:
            try:
                quotes.close()
                logger.info("进程 %d 连接已关闭", worker_id)
            except:
                pass


def _download_single_kline(
    quotes, symbol: str, interval: str, start_date, logger
) -> Optional[pd.DataFrame]:
    """
    下载单个品种的K线数据

    Args:
        quotes: Quotes实例（或QuotesWrapper）
        symbol: 品种代码
        interval: 周期
        start_date: 开始日期
        logger: 日志对象

    Returns:
        DataFrame或None
    """
    try:
        # 转换日期格式
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

        # 计算从开始日期到现在的天数
        days_diff = (date.today() - start_date).days

        # 转换周期格式
        frequency_map = {
            "1d": 9,  # 日线
            "5m": 0,  # 5分钟
            "1m": 8,  # 1分钟
            "15m": 1,
            "30m": 2,
            "1h": 3,
        }

        frequency = frequency_map.get(interval, 9)

        # 根据周期设置合理的下载数量
        if interval == "1d":
            offset = min(int(days_diff * 1.5), 800)
        elif interval == "5m":
            offset = min(int(days_diff * 50), 800)
        elif interval == "1m":
            offset = min(int(days_diff * 250), 800)
        else:
            offset = 800

        # 确定市场代码
        # 🚀 正确映射（mootdx/TdxHq_API标准）：深圳=0, 上海=1, 北京=2
        if symbol.startswith(("6", "688")):
            market = 1  # 上海（主板+科创板）
        elif symbol.startswith(("50", "51", "56", "58")):
            # 上海ETF/LOF
            # 50xxxx → 上海LOF
            # 51xxxx → 上海ETF（国债ETF、H股ETF等）
            # 56xxxx → 上海黄金ETF
            # 58xxxx → 上海ETF
            market = 1  # 上海
        elif symbol.startswith(("8", "9", "4")):
            # 北交所：82/83/87/88/43开头
            market = 2  # 北交所
        else:
            # 深圳：000/001/002/300/301开头
            # 深圳ETF/LOF：15xxxx/16xxxx/52xxxx
            market = 0  # 深圳

        # 添加重试机制
        max_retries = 3
        retry_delay = 0.5
        data = None

        for retry in range(max_retries):
            if retry > 0:
                time.sleep(retry_delay)

            try:
                # 🚀 北交所特殊处理：mootdx.Quotes.bars()不支持market=2
                is_beijing = symbol.startswith(("8", "9", "4"))

                if (
                    is_beijing
                    and hasattr(quotes, "client")
                    and hasattr(quotes.client, "get_security_bars")
                ):
                    # 北交所品种：直接使用底层TdxHq_API
                    logger.debug("北交所品种 %s 使用TdxHq_API", symbol)
                    raw_data = quotes.client.get_security_bars(
                        int(frequency), int(market), str(symbol), 0, int(offset)
                    )

                    if not raw_data:
                        data = None
                    else:
                        # 转换为DataFrame并解码
                        data = pd.DataFrame(raw_data)
                        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

                        # 设置index
                        if not data.empty and "datetime" in data.columns:
                            data.index = data["datetime"]

                        # 标准化列名
                        if "vol" in data.columns:
                            data["volume"] = data["vol"]

                elif hasattr(quotes, "bars"):
                    # 其他品种：使用bars()方法
                    data = quotes.bars(
                        symbol=str(symbol), frequency=interval, start=0, offset=int(offset)
                    )

                    # bars()已返回DataFrame，只需标准化列名
                    if data is not None and not data.empty:
                        # 标准化列名
                        if "vol" in data.columns and "volume" not in data.columns:
                            data["volume"] = data["vol"]

                elif hasattr(quotes, "client"):
                    # 降级：直接使用client
                    raw_data = quotes.client.get_security_bars(
                        int(frequency), int(market), str(symbol), 0, int(offset)
                    )

                    if not raw_data:
                        data = None
                    else:
                        # 转换为DataFrame并解码
                        data = pd.DataFrame(raw_data)
                        data = TdxDateTimeDecoder.decode_dataframe(data, interval)

                        # 设置index
                        if not data.empty and "datetime" in data.columns:
                            data.index = data["datetime"]

                        # 标准化列名
                        if "vol" in data.columns:
                            data["volume"] = data["vol"]
                else:
                    logger.warning("quotes对象无可用方法")
                    return None

            except Exception as api_error:
                logger.debug("API调用失败: %s, 错误: %s", symbol, str(api_error)[:50])
                data = None

            # 如果成功获取到数据，跳出重试循环
            if data is not None and not data.empty:
                break

        # 最终检查
        if data is None or data.empty:
            return None

        # 确保有必要的字段
        required_fields = ["datetime", "open", "high", "low", "close", "volume"]
        missing_fields = [f for f in required_fields if f not in data.columns]

        if missing_fields:
            logger.debug(
                "数据缺少字段 %s: %s（实际字段: %s）", symbol, missing_fields, data.columns.tolist()
            )
            return None

        return data

    except Exception as e:
        logger.debug("下载失败 %s %s: %s", symbol, interval, e)
        return None

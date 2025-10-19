# -*- coding: utf-8 -*-
"""
通达信二进制数据读取器

读取通达信软件本地保存的二进制K线数据文件，并标准化保存为Parquet格式。

支持的数据类型：
- 日线数据: vipdoc/{market}/lday/{symbol}.day
- 5分钟线: vipdoc/{market}/fzline/{symbol}.lc5
- 1分钟线: vipdoc/{market}/minline/{symbol}.lc1

市场代码：
- sh: 上证
- sz: 深证
- bj: 北证
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.infrastructure.tdx_asyncio import (
    read_day_data,
    read_minute_data,
    read_lc5_data,
)

from .base_reader import BaseReader
from .bj_decoder import BjStockDecoder
from ..config import config_manager
from ..data_quality import StorageManager


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器"""

    # 市场代码映射
    MARKET_CODES = {
        "sh": "上证",
        "sz": "深证",
        "bj": "北证",
    }

    # 数据类型映射
    DATA_TYPE_MAPPING = {
        "day": {"interval": "1d", "subdir": "lday", "ext": ".day"},
        "5min": {"interval": "5m", "subdir": "fzline", "ext": ".lc5"},
        "1min": {"interval": "1m", "subdir": "minline", "ext": ".lc1"},
    }

    def __init__(self, source_path: Optional[Path] = None):
        """
        初始化通达信数据读取器

        Args:
            source_path: 通达信软件根目录（如不指定则从配置读取）
        """
        if source_path is None:
            source_path = config_manager.get_tdx_reader_root_dir()
            if source_path is None:
                raise ValueError("通达信根目录未配置")

        super().__init__(source_path)

        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()
        # 不再使用 mootdx Reader，改用 tdx_asyncio 的异步读取器
        # 北证数据解码器（tdx_asyncio不支持北证，使用自定义解码器）
        self.bj_decoder = BjStockDecoder()

    def read(
        self,
        symbol: str,
        data_type: str = "day",
        market: str = "sh",
    ) -> Any:
        """
        读取通达信二进制数据

        Args:
            symbol: 品种代码（6位）
            data_type: 数据类型（'day', '5min', '1min'）
            market: 市场代码（'sh', 'sz', 'bj'）

        Returns:
            读取的原始数据

        Raises:
            ValueError: 参数不合法
            FileNotFoundError: 数据文件不存在
        """
        # 验证参数
        if data_type not in self.DATA_TYPE_MAPPING:
            raise ValueError(
                f"不支持的数据类型: {data_type}, "
                f"支持的类型: {list(self.DATA_TYPE_MAPPING.keys())}"
            )

        if market not in self.MARKET_CODES:
            raise ValueError(
                f"不支持的市场代码: {market}, " f"支持的市场: {list(self.MARKET_CODES.keys())}"
            )

        # 构建文件路径
        type_info = self.DATA_TYPE_MAPPING[data_type]
        subdir = type_info["subdir"]
        ext = type_info["ext"]

        # 路径格式: {tdx_root}/vipdoc/{market}/{subdir}/{market}{symbol}{ext}
        # 注意：通达信的文件名格式是 {market}{symbol}{ext}，例如 sh600000.day
        data_file = self.source_path / "vipdoc" / market / subdir / f"{market}{symbol}{ext}"

        if not data_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {data_file}")

        try:
            # 判断是否为北证市场，使用不同的解码器
            if market == "bj":
                # 使用自定义北证解码器
                if data_type == "day":
                    df = self.bj_decoder.read_day_file(data_file)
                elif data_type == "5min":
                    df = self.bj_decoder.read_5min_file(data_file)
                elif data_type == "1min":
                    df = self.bj_decoder.read_1min_file(data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

                self.logger.info("使用北证解码器读取: %s", data_file.name)
            else:
                # 使用 tdx_asyncio 异步读取器读取上证/深证数据
                async def _read_async():
                    if data_type == "day":
                        return await read_day_data(data_file)
                    elif data_type == "1min":
                        return await read_minute_data(data_file)
                    elif data_type == "5min":
                        return await read_lc5_data(data_file)
                    else:
                        raise ValueError(f"不支持的数据类型: {data_type}")

                df = asyncio.run(_read_async())

            if df is None or df.empty:
                return pd.DataFrame()

            # 添加元数据
            df.attrs["symbol"] = symbol
            df.attrs["data_type"] = data_type
            df.attrs["market"] = market
            df.attrs["interval"] = type_info["interval"]

            return df

        except Exception as e:
            self.logger.error("读取通达信数据失败: %s, 错误: %s", data_file, e)
            raise

    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """
        标准化通达信数据格式

        Args:
            raw_data: 原始数据（mootdx.reader返回的DataFrame）

        Returns:
            标准化后的DataFrame
        """
        if raw_data is None or (isinstance(raw_data, pd.DataFrame) and raw_data.empty):
            return pd.DataFrame()

        df = raw_data.copy()

        # 获取元数据
        symbol = df.attrs.get("symbol", "")
        interval = df.attrs.get("interval", "1d")

        # mootdx.reader 返回的数据：index是日期，列是 open, high, low, close, amount, volume
        # 标准化列名
        column_mapping = {
            "date": "datetime",
            "time": "datetime",
            "vol": "volume",
            "amount": "turnover",
        }

        # 先重命名列（如果存在date列，重命名为datetime）
        rename_map = {}
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                rename_map[old_name] = new_name

        if rename_map:
            df = df.rename(columns=rename_map)

        # 如果没有datetime列，尝试从索引获取
        if "datetime" not in df.columns:
            if df.index.name is None or "date" in str(df.index.name).lower():
                df = df.reset_index()
                # 第一列是日期
                if len(df.columns) > 0:
                    first_col = str(df.columns[0])  # 确保是字符串类型
                    if first_col not in ["datetime", "open", "high"]:
                        df = df.rename(columns={first_col: "datetime"})

        # 检查并删除重复的列名
        if df.columns.duplicated().any():
            self.logger.warning(
                "检测到重复列名: %s, 正在去重", df.columns[df.columns.duplicated()].tolist()
            )
            # 保留第一次出现的列
            df = df.loc[:, ~df.columns.duplicated()]

        # 确保datetime列是datetime类型
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
        else:
            # 如果没有 datetime 列，尝试从 index 获取
            df["datetime"] = pd.to_datetime(df.index, errors="coerce")
            df = df[df["datetime"].notna()].copy()

        # 确保数值列是float类型
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 添加品种和周期信息
        df["symbol"] = symbol
        df["interval"] = interval

        # 按时间排序并去重
        if "datetime" in df.columns:
            # 确保 df 是 DataFrame 类型，避免类型推断问题
            if isinstance(df, pd.DataFrame):
                df = df.sort_values("datetime")
                # 去除重复的日期记录（保留最后一条）
                df = df.drop_duplicates(subset=["datetime"], keep="last")
                # 重置索引，避免索引重复
                df = df.reset_index(drop=True)

        # 验证格式
        try:
            # 确保传入的是 DataFrame
            if isinstance(df, pd.DataFrame):
                self.validate_dataframe(df)
        except ValueError as e:
            self.logger.error("数据格式验证失败: %s", e)
            raise
        # 确保返回的是 DataFrame
        if isinstance(df, pd.DataFrame):
            return df
        else:
            # 如果不是 DataFrame，返回空 DataFrame
            return pd.DataFrame()

    def save(
        self, dataframe: pd.DataFrame, target_path: Optional[Path] = None, merge: bool = True
    ) -> bool:
        """
        保存标准化后的数据到Parquet格式

        Args:
            dataframe: 标准化后的DataFrame
            target_path: 目标保存路径（不使用，由StorageManager管理路径）
            merge: 是否使用增量更新模式（True=合并去重，False=覆盖）

        Returns:
            是否保存成功
        """
        if dataframe.empty:
            self.logger.warning("数据为空，跳过保存")
            return False

        try:
            # 提取品种和周期信息
            symbol = dataframe["symbol"].iloc[0]
            interval = dataframe["interval"].iloc[0]

            # 选择保存模式
            if merge:
                # 增量更新：合并现有数据和新数据，去重
                # 先查询现有数据
                existing_df = self.storage_manager.query_kline(symbol, interval)

                if existing_df is not None and not existing_df.empty:
                    # 确保两个 DataFrame 的索引都是干净的（快速处理，无需检查）
                    existing_df = existing_df.reset_index(drop=True)
                    dataframe = dataframe.reset_index(drop=True)

                    # 合并新旧数据
                    merged_df = pd.concat([existing_df, dataframe], ignore_index=True)

                    # 按 datetime 排序并去重
                    if "datetime" in merged_df.columns:
                        merged_df = merged_df.sort_values("datetime")
                        merged_df = merged_df.drop_duplicates(subset=["datetime"], keep="last")
                        # 重置索引，确保索引连续且无重复
                        merged_df = merged_df.reset_index(drop=True)

                    # 保存合并后的数据
                    file_path = self.storage_manager.save_kline(symbol, interval, merged_df)
                    if file_path:
                        self.logger.info(
                            "数据增量保存成功: %s %s (合并模式，合并后共 %d 条)",
                            symbol,
                            interval,
                            len(merged_df),
                        )
                        return True
                    else:
                        self.logger.error("数据增量保存失败: %s %s", symbol, interval)
                        return False
                else:
                    # 如果没有现有数据，直接保存
                    file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                    if file_path:
                        self.logger.info("数据保存成功: %s %s (首次保存)", symbol, interval)
                        return True
                    else:
                        self.logger.error("数据保存失败: %s %s", symbol, interval)
                        return False
            else:
                # 覆盖模式：直接覆盖原有数据
                file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                if file_path:
                    self.logger.info(
                        "数据保存成功: %s %s -> %s (覆盖模式)", symbol, interval, file_path
                    )
                    return True
                else:
                    self.logger.error("数据保存失败: %s %s", symbol, interval)
                    return False

        except Exception as e:
            # 增强错误输出，确保能看到
            import traceback

            error_detail = traceback.format_exc()
            self.logger.error("❌ 保存数据时出错: %s", e, exc_info=True)
            print(f"❌ 保存失败: {e}")
            print(error_detail)
            return False

    def read_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量读取多个品种的数据

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场代码

        Returns:
            品种代码到DataFrame的映射字典
        """
        results = {}

        for symbol in symbols:
            try:
                df = self.read(symbol=symbol, data_type=data_type, market=market)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                self.logger.error("读取 %s 失败: %s", symbol, e)

        self.logger.info("批量读取完成: 成功 %d/%d", len(results), len(symbols))
        return results

    def process_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
        progress_callback=None,
        max_workers: int = 4,
        stop_check=None,
        batch_save_size: int = 10,  # 🔍 DEBUG: 批量保存大小（默认10个品种/次）
    ) -> Dict[str, bool]:
        """
        批量处理多个品种的数据（读取 -> 标准化 -> 批量保存）

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场代码
            progress_callback: 进度回调函数 callback(current, total, symbol, success)
            max_workers: 最大线程数
            stop_check: 停止检查函数，返回True时停止处理
            batch_save_size: 批量保存大小（每N个品种保存一次）

        Returns:
            品种代码到处理结果的映射字典
        """
        results = {}
        total = len(symbols)

        # 🔍 DEBUG: 打印批量处理开始信息（强制输出到控制台）
        print(f"\n{'='*60}")
        print(f"📖 TdxBinaryReader 开始批量处理:")
        print(f"  - 品种数量: {total}")
        print(f"  - 数据类型: {data_type}")
        print(f"  - 市场代码: {market}")
        print(f"  - 线程数: {max_workers}")
        print(f"  - 批量保存阈值: {batch_save_size} 个品种/次")
        print(f"{'='*60}\n")

        self.logger.info("📖 TdxBinaryReader 开始批量处理:")
        self.logger.info("  - 品种数量: %d", total)
        self.logger.info("  - 数据类型: %s", data_type)
        self.logger.info("  - 市场代码: %s", market)
        self.logger.info("  - 线程数: %d", max_workers)
        self.logger.info("  - 批量保存阈值: %d 个品种/次", batch_save_size)

        # 批量保存缓冲区
        save_buffer = []  # 存储 (symbol, interval, dataframe) 元组

        # 批量保存函数
        def batch_save():
            """批量保存缓冲区中的数据"""
            if not save_buffer:
                print("⚠️  批量保存: 缓冲区为空，跳过保存")
                return

            # 🔍 DEBUG: 强制打印到控制台
            buffer_size = len(save_buffer)
            print(f"\n{'─'*60}")
            print(f"💾 开始批量保存 {buffer_size} 个品种的数据...")

            # 🔍 DEBUG: 打印批量保存开始信息
            self.logger.info(f"💾 开始批量保存 {buffer_size} 个品种的数据...")

            saved_count = 0
            failed_symbols = []
            for symbol, interval, df in save_buffer:
                try:
                    # 🔍 DEBUG: 打印每个品种的保存尝试
                    print(f"  → 正在保存: {symbol} ({interval}), {len(df)} 条记录")

                    success = self.save(df)
                    if success:
                        saved_count += 1
                        print(f"    ✅ 保存成功")
                        self.logger.debug(f"  ✅ 保存成功: {symbol} ({interval}), {len(df)} 条记录")
                    else:
                        failed_symbols.append(symbol)
                        print(f"    ❌ 保存失败（返回False）")
                        self.logger.warning(f"  ❌ 保存失败: {symbol} ({interval})")
                except Exception as e:
                    failed_symbols.append(symbol)
                    print(f"    ❌ 保存异常: {e}")
                    self.logger.error(f"  ❌ 保存异常: {symbol} ({interval}) - {e}", exc_info=True)

            # 🔍 DEBUG: 打印批量保存结果统计
            print(f"📦 批量保存完成: 成功 {saved_count}/{buffer_size}, 失败 {len(failed_symbols)}")
            print(f"{'─'*60}\n")

            self.logger.info(f"📦 批量保存完成: 成功 {saved_count}/{buffer_size}")
            if failed_symbols:
                failed_summary = f"  失败品种: {', '.join(failed_symbols[:10])}"
                if len(failed_symbols) > 10:
                    failed_summary += f" ... 还有{len(failed_symbols)-10}个"
                self.logger.warning(failed_summary)

            save_buffer.clear()

        # 如果只有少量品种或max_workers=1，使用单线程
        if total <= 5 or max_workers == 1:
            self.logger.info(f"🔄 使用单线程模式处理 {total} 个品种")

            for i, symbol in enumerate(symbols, 1):
                # 检查停止标志
                if stop_check and stop_check():
                    self.logger.info("⛔ 检测到停止标志，中断处理")
                    # 保存剩余数据
                    batch_save()
                    break

                try:
                    # 🔍 DEBUG: 打印当前处理的品种
                    self.logger.debug(f"  [{i}/{total}] 开始处理: {symbol}")

                    # 读取数据
                    raw_data = self.read(symbol=symbol, data_type=data_type, market=market)

                    # 标准化
                    df = self.standardize(raw_data)

                    # 添加到缓冲区而不是立即保存
                    if not df.empty:
                        interval = df["interval"].iloc[0] if "interval" in df.columns else "1d"
                        save_buffer.append((symbol, interval, df))
                        print(
                            f"  [{i}/{total}] ✅ {symbol} 已读取 {len(df)} 条记录，加入缓冲区(当前: {len(save_buffer)})"
                        )
                        self.logger.debug(
                            f"  [{i}/{total}] ✅ {symbol} 已读取 {len(df)} 条记录，加入保存缓冲区"
                        )
                    else:
                        print(f"  [{i}/{total}] ⚠️  {symbol} 数据为空")
                        self.logger.debug(f"  [{i}/{total}] ⚠️  {symbol} 数据为空")

                    # 达到批量保存阈值，执行保存
                    if len(save_buffer) >= batch_save_size:
                        print(f"\n🔔 达到批量保存阈值({batch_save_size})，触发保存...")
                        self.logger.info(f"📦 达到批量保存阈值({batch_save_size})，触发保存...")
                        batch_save()

                    results[symbol] = True

                    # 进度回调
                    if progress_callback:
                        progress_callback(i, total, symbol, True)

                except Exception as e:
                    # 详细错误日志，包含堆栈跟踪
                    self.logger.error(f"  [{i}/{total}] ❌ 处理 {symbol} 失败: {e}", exc_info=True)
                    results[symbol] = False
                    if progress_callback:
                        progress_callback(i, total, symbol, False)

            # 保存剩余数据
            if save_buffer:
                self.logger.info(f"📦 保存剩余 {len(save_buffer)} 个品种的数据...")
                batch_save()
            else:
                self.logger.info("✅ 所有数据已保存，无剩余数据")
        else:
            # 多线程处理
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import threading

            self.logger.info(f"🔄 使用多线程模式处理 {total} 个品种，线程数: {max_workers}")

            results_lock = threading.Lock()
            buffer_lock = threading.Lock()
            completed_count = [0]  # 使用列表以便在闭包中修改

            def process_one_symbol(symbol: str) -> tuple:
                """处理单个品种（读取+标准化，不保存）"""
                try:
                    # 步骤1：读取数据
                    raw_data = self.read(symbol=symbol, data_type=data_type, market=market)

                    # 步骤2：标准化
                    df = self.standardize(raw_data)

                    # 步骤3：添加到缓冲区（不立即保存）
                    if not df.empty:
                        interval = df["interval"].iloc[0] if "interval" in df.columns else "1d"
                        with buffer_lock:
                            save_buffer.append((symbol, interval, df))
                            buffer_len = len(save_buffer)
                            # 达到批量保存阈值，执行保存
                            if buffer_len >= batch_save_size:
                                self.logger.info(
                                    f"📦 达到批量保存阈值({batch_save_size})，触发保存..."
                                )
                                batch_save()

                        self.logger.debug(f"  ✅ {symbol} 已读取 {len(df)} 条记录")
                    else:
                        self.logger.debug(f"  ⚠️  {symbol} 数据为空")

                    return (symbol, True)
                except Exception as e:
                    # 详细错误日志，包含堆栈跟踪
                    self.logger.error(f"  ❌ 处理 {symbol} 失败: {e}", exc_info=True)
                    return (symbol, False)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                self.logger.info(f"📤 提交 {total} 个处理任务到线程池...")
                future_to_symbol = {
                    executor.submit(process_one_symbol, symbol): symbol for symbol in symbols
                }

                # 处理完成的任务
                for future in as_completed(future_to_symbol):
                    # 检查停止标志
                    if stop_check and stop_check():
                        self.logger.info("⛔ 检测到停止标志，中断批量处理")
                        # 取消未开始的任务
                        for f in future_to_symbol:
                            if not f.done():
                                f.cancel()
                        break

                    symbol, success = future.result()

                    with results_lock:
                        results[symbol] = success
                        completed_count[0] += 1

                        # 每处理50个品种输出一次进度
                        if completed_count[0] % 50 == 0:
                            self.logger.info(
                                f"📊 进度: {completed_count[0]}/{total} ({completed_count[0]*100//total}%)"
                            )

                        # 进度回调
                        if progress_callback:
                            progress_callback(completed_count[0], total, symbol, success)

            # 保存剩余数据
            with buffer_lock:
                if save_buffer:
                    self.logger.info(f"📦 保存剩余 {len(save_buffer)} 个品种的数据...")
                    batch_save()
                else:
                    self.logger.info("✅ 所有数据已保存，无剩余数据")

        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count
        self.logger.info("=" * 60)
        self.logger.info(f"✅ 批量处理完成: 成功 {success_count}/{len(symbols)}, 失败 {fail_count}")
        self.logger.info("=" * 60)

        return results

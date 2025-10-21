# -*- coding: utf-8 -*-
"""
数据质量管理模块

负责数据存储、校验、感知、文件监控和系统健康检查，包括：
- 数据存储管理（Parquet格式）
- 数据校验和感知
- 文件监控和变化检测（增强防抖机制）
- 系统健康检查
- 数据质量概览和报告

合并来源：storage.py + validator.py + data_sensor.py + file_watcher.py (v2)
"""

# ==================== 导入声明 ====================
import logging
import os
import time
import threading
from threading import Thread, Event as ThreadEvent
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from ..config import config_manager

# ==================== IPO日期缓存管理 ====================


class IPODateCache:
    """IPO日期持久化缓存管理器

    实现两级缓存架构：
    - L1: 内存字典（进程运行期间有效）
    - L2: JSON文件（永久存储，带日期验证）
    """

    def __init__(self, cache_file: Optional[Path] = None):
        """初始化IPO缓存

        Args:
            cache_file: 缓存文件路径，默认使用data/cache/ipo_dates.json
        """
        self.logger = logging.getLogger(__name__)

        # L1缓存：内存字典
        self._memory_cache: Dict[str, Optional[date]] = {}

        # L2缓存：JSON文件
        if cache_file is None:
            cache_dir = config_manager.get_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file = cache_dir / "ipo_dates.json"
        else:
            self.cache_file = cache_file
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._lock = threading.RLock()

        # 缓存日期（用于验证）
        self._cache_date: Optional[str] = None

        # 统计信息
        self._stats = {
            "hits": 0,
            "misses": 0,
            "errors": 0,
            "api_calls": 0,
            "api_success": 0,
            "api_timeout": 0,
        }

        # 加载持久化缓存
        self._load_from_file()

    def _load_from_file(self) -> None:
        """从品种列表缓存加载IPO数据（优先），兼容旧的独立缓存"""
        try:
            from ..cache_manager import DailyCacheManager

            # 1. 优先尝试从品种列表缓存加载
            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "stock_list_classified.json"
            )

            if cache_data:
                # 从品种列表缓存中提取IPO数据
                classified = cache_data.get("classified", {})
                loaded_count = 0

                for category, stocks in classified.items():
                    for stock in stocks:
                        symbol = stock.get("code")
                        ipo_date_str = stock.get("ipo_date")

                        if symbol and ipo_date_str:
                            try:
                                self._memory_cache[symbol] = datetime.strptime(
                                    ipo_date_str, "%Y-%m-%d"
                                ).date()
                                loaded_count += 1
                            except ValueError:
                                pass

                if loaded_count > 0:
                    self._cache_date = cache_date
                    self.logger.info(f"✓ 从品种列表缓存加载了 {loaded_count} 个IPO日期")
                    return

            # 2. 降级：尝试从旧的独立 ipo_dates.json 加载
            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                "ipo_dates.json"
            )

            if not cache_data:
                self.logger.info("IPO缓存文件不存在，将创建新缓存")
                return

            self.logger.info("⚠️ 使用旧的 ipo_dates.json 缓存（建议重新下载）")

            # 🔧 兼容旧格式：检查cache_date是否为None
            if cache_date is None:
                self.logger.warning("IPO缓存无日期信息（旧格式），将标记为过时")
                # 使用当前日期减1天的字符串，确保被标记为过时
                self._cache_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
            else:
                # 解析日期
                if isinstance(cache_date, str):
                    self._cache_date = cache_date
                elif isinstance(cache_date, date):
                    self._cache_date = cache_date.strftime("%Y-%m-%d")
                else:
                    self.logger.warning("无效的缓存日期格式: %s", type(cache_date))
                    self._cache_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

            # 解析缓存数据
            for symbol, ipo_date_value in cache_data.items():
                if ipo_date_value:
                    try:
                        # 🔧 兼容旧格式：处理字典格式的IPO日期
                        if isinstance(ipo_date_value, dict):
                            # 旧格式可能是 {"ipo_date": "2020-01-01", ...}
                            ipo_date_str = ipo_date_value.get("ipo_date") or ipo_date_value.get(
                                "date"
                            )
                            if not ipo_date_str:
                                self.logger.warning("字典格式的IPO日期缺少有效字段: %s", symbol)
                                self._memory_cache[symbol] = None
                                continue
                        else:
                            # 新格式：直接是字符串
                            ipo_date_str = ipo_date_value

                        self._memory_cache[symbol] = datetime.strptime(
                            ipo_date_str, "%Y-%m-%d"
                        ).date()
                    except (ValueError, AttributeError) as e:
                        self.logger.warning(
                            "无效的IPO日期格式: %s -> %s (%s)", symbol, ipo_date_value, e
                        )
                        self._memory_cache[symbol] = None
                else:
                    # 缓存了None值（表示查询失败）
                    self._memory_cache[symbol] = None

            if not is_valid:
                self.logger.warning("IPO日期缓存已过时（日期: %s）", cache_date)
            else:
                self.logger.info(
                    "✓ IPO缓存加载完成: %d条记录（日期: %s）", len(self._memory_cache), cache_date
                )

        except Exception as e:
            self.logger.error("加载IPO缓存失败: %s", e, exc_info=True)
            self._memory_cache.clear()
            self._cache_date = None

    def _save_to_file(self) -> None:
        """保存缓存到文件（已废弃，IPO数据现在保存在品种列表缓存中）"""
        self.logger.warning("IPODateCache._save_to_file 已废弃，IPO数据现在由品种列表缓存管理")
        # 不再执行实际保存
        return

    def get(self, symbol: str) -> Tuple[Optional[date], bool]:
        """从缓存获取IPO日期

        Args:
            symbol: 品种代码

        Returns:
            (ipo_date, is_cached): IPO日期和是否来自缓存
        """
        with self._lock:
            if symbol in self._memory_cache:
                self._stats["hits"] += 1
                return self._memory_cache[symbol], True
            else:
                self._stats["misses"] += 1
                return None, False

    def set(self, symbol: str, ipo_date: Optional[date], save_immediately: bool = False) -> None:
        """设置IPO日期到缓存

        Args:
            symbol: 品种代码
            ipo_date: IPO日期（None表示查询失败）
            save_immediately: 是否立即保存到文件
        """
        with self._lock:
            self._memory_cache[symbol] = ipo_date

            # 🔍 调试：每1000个品种输出一次
            if len(self._memory_cache) % 1000 == 0:
                self.logger.debug("IPO缓存已添加 %d 个品种", len(self._memory_cache))

            if save_immediately:
                self._save_to_file()

    def batch_save(self) -> None:
        """批量保存缓存到文件"""
        with self._lock:
            self._save_to_file()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_queries = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_queries * 100) if total_queries > 0 else 0

            return {
                **self._stats,
                "total_queries": total_queries,
                "hit_rate": round(hit_rate, 2),
                "cache_size": len(self._memory_cache),
            }

    def record_api_call(self, success: bool, timeout: bool = False) -> None:
        """记录API调用统计"""
        with self._lock:
            self._stats["api_calls"] += 1
            if success:
                self._stats["api_success"] += 1
            elif timeout:
                self._stats["api_timeout"] += 1
            else:
                self._stats["errors"] += 1

    def is_cache_outdated(self) -> bool:
        """检查缓存是否过时（次日0时失效）

        Returns:
            bool: True=缓存已过时，False=缓存有效
        """
        try:
            from ..cache_manager import DailyCacheManager

            return not DailyCacheManager.is_cache_valid(self._cache_date)
        except Exception:
            return True  # 异常时认为缓存过时

    def incremental_update(self, all_symbols: List[str], progress_callback=None) -> Dict[str, int]:
        """增量/减量更新IPO日期（与品种列表联动）

        Args:
            all_symbols: 当前所有品种代码列表
            progress_callback: 进度回调函数 callback(current, total)

        Returns:
            Dict: 更新统计信息 {
                "added": int,  # 新增品种数
                "removed": int,  # 删除品种数
                "download_succeeded": int,  # 下载成功数
                "download_failed": int  # 下载失败数
            }
        """
        with self._lock:
            cached_symbols = set(self._memory_cache.keys())
            current_symbols = set(all_symbols)

            # 计算差异
            new_symbols = current_symbols - cached_symbols
            removed_symbols = cached_symbols - current_symbols

            self.logger.info(
                "IPO缓存增量更新：新增 %d 个，删除 %d 个",
                len(new_symbols),
                len(removed_symbols),
            )

            # 清理已删除品种的缓存
            for symbol in removed_symbols:
                if symbol in self._memory_cache:
                    del self._memory_cache[symbol]

            # 下载新增品种的IPO日期
            download_result = {"total": 0, "succeeded": 0, "failed": 0}

            if new_symbols:
                self.logger.info("检测到 %d 个新增品种，开始下载IPO日期...", len(new_symbols))
                try:
                    from ..data_acquisition.data_fetcher import download_ipo_dates

                    # 🔧 包装进度回调以适配download_ipo_dates的接口
                    completed = [0]
                    total_count = len(new_symbols)

                    def wrapped_progress_callback(symbol: str, status: str) -> None:
                        """包装进度回调：symbol, status -> current, total"""
                        completed[0] += 1
                        if progress_callback:
                            progress_callback(completed[0], total_count)

                    download_result = download_ipo_dates(
                        list(new_symbols),
                        force_refresh=False,
                        use_adaptive=True,
                        progress_callback=wrapped_progress_callback if progress_callback else None,
                    )
                    self.logger.info(
                        "IPO日期下载完成：成功 %d 个，失败 %d 个",
                        download_result.get("succeeded", 0),
                        download_result.get("failed", 0),
                    )
                except Exception as e:
                    self.logger.error("下载IPO日期失败: %s", e, exc_info=True)

            # 保存更新后的缓存
            self._save_to_file()

            return {
                "added": len(new_symbols),
                "removed": len(removed_symbols),
                "download_succeeded": download_result.get("succeeded", 0),
                "download_failed": download_result.get("failed", 0),
            }


# ==================== 数据存储管理 ====================


class StorageManager:
    """存储管理器"""

    def __init__(self):
        """初始化存储管理器"""
        self.data_dir = config_manager.get_data_dir()
        self.logger = logging.getLogger(__name__)

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_kline(self, symbol: str, interval: str, dataframe: pd.DataFrame) -> Optional[Path]:
        """
        保存K线数据到Parquet文件

        Args:
            symbol: 品种代码
            interval: K线周期
            dataframe: K线数据DataFrame

        Returns:
            Optional[Path]: 保存的文件路径；当 DataFrame 为空或保存失败时返回 None
        """
        try:
            if dataframe is None or dataframe.empty:
                self.logger.warning("DataFrame为空，跳过保存: %s %s", symbol, interval)
                return None

            # 创建品种目录
            symbol_dir = self.data_dir / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)

            # 创建周期目录
            interval_dir = symbol_dir / interval
            interval_dir.mkdir(parents=True, exist_ok=True)

            # 保存文件
            file_path = interval_dir / "data.parquet"

            # 🔍 DEBUG: 强制打印到控制台
            print(f"      🔍 准备保存: {symbol} ({interval})")
            print(f"         数据目录: {self.data_dir}")
            print(f"         完整路径: {file_path}")
            print(f"         数据记录数: {len(dataframe)}")

            # 🔍 DEBUG: 打印即将保存的完整路径
            self.logger.debug(f"🔍 准备保存数据: {symbol} ({interval})")
            self.logger.debug(f"   数据目录: {self.data_dir}")
            self.logger.debug(f"   完整路径: {file_path}")
            self.logger.debug(f"   数据记录数: {len(dataframe)}")

            # 使用zstd压缩保存
            dataframe.to_parquet(file_path, compression="zstd", index=False)

            # 🔍 DEBUG: 强制打印保存成功信息
            print(f"      ✅ 保存成功！文件路径: {file_path.absolute()}")

            # 🔍 DEBUG: 保存成功后打印完整的文件路径
            self.logger.info(f"💾 保存成功: {symbol} ({interval}), {len(dataframe)}条记录")
            self.logger.info(f"   → 文件路径: {file_path.absolute()}")
            return file_path

        except Exception as e:
            self.logger.error(f"❌ 保存失败: {symbol} ({interval}) - {e}", exc_info=True)
            return None

    def query_kline(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        查询K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            Optional[pd.DataFrame]: 查询结果；当文件不存在或读取失败时返回 None
        """
        try:
            file_path = self.data_dir / symbol / interval / "data.parquet"

            if not file_path.exists():
                self.logger.debug("数据文件不存在: %s", file_path)
                return None

            # 读取数据
            df = pd.read_parquet(file_path)  # type: ignore

            if df.empty:
                return df

            # 确保 datetime 列存在且无重复（优化：直接处理，减少检查）
            if "datetime" in df.columns and len(df) > 0:
                # 快速去重：直接排序和去重，不检查
                df = df.sort_values("datetime")
                df = df.drop_duplicates(subset=["datetime"], keep="last")
                df = df.reset_index(drop=True)

            # 过滤日期
            if start_date is not None:
                if isinstance(start_date, str):
                    start_date = pd.to_datetime(start_date).date()  # type: ignore
                if "datetime" in df.columns:
                    df = df[df["datetime"] >= pd.Timestamp(start_date)]  # type: ignore
                else:
                    df = df[df.index >= pd.Timestamp(start_date)]  # type: ignore

            if end_date is not None:
                if isinstance(end_date, str):
                    end_date = pd.to_datetime(end_date).date()  # type: ignore
                if "datetime" in df.columns:
                    df = df[df["datetime"] <= pd.Timestamp(end_date)]  # type: ignore
                else:
                    df = df[df.index <= pd.Timestamp(end_date)]  # type: ignore

            # 优化：减少日志输出
            # 确保返回类型为 DataFrame
            return df if isinstance(df, pd.DataFrame) else None

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", symbol, interval, e)
            return None

    def get_local_data_index(self) -> List[str]:
        """获取本地数据索引（已下载的品种代码列表）

        快速扫描模式：只检查文件是否存在且大小>0，不验证内容完整性。
        完整性验证由数据质量感知系统处理，避免启动时的性能瓶颈。

        Returns:
            List[str]: 品种代码列表（按代码排序）
        """
        try:
            symbol_codes = []

            # 快速扫描：只检查目录和文件存在性
            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                symbol_code = symbol_dir.name

                # 检查是否有任何周期的数据文件（只检查存在性和大小）
                has_data = False
                for interval_dir in symbol_dir.iterdir():
                    if interval_dir.is_dir():
                        data_file = interval_dir / "data.parquet"
                        if data_file.exists() and data_file.stat().st_size > 0:
                            has_data = True
                            break

                if has_data:
                    symbol_codes.append(symbol_code)

            # 按代码排序
            symbol_codes.sort()

            self.logger.info("快速扫描本地数据索引完成，共 %d 个品种", len(symbol_codes))
            return symbol_codes

        except Exception as e:
            self.logger.error("获取本地数据索引失败: %s", e)
            return []

    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            stats = {
                "total_symbols": 0,
                "total_files": 0,
                "total_size_mb": 0,
                "intervals": {},
            }

            for symbol_dir in self.data_dir.iterdir():
                if symbol_dir.is_dir():
                    stats["total_symbols"] += 1

                    for interval_dir in symbol_dir.iterdir():
                        if interval_dir.is_dir():
                            interval = interval_dir.name
                            if interval not in stats["intervals"]:
                                stats["intervals"][interval] = {"files": 0, "size_mb": 0}

                            for file_path in interval_dir.iterdir():
                                if file_path.is_file() and file_path.suffix == ".parquet":
                                    stats["total_files"] += 1
                                    stats["intervals"][interval]["files"] += 1

                                    file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                                    stats["total_size_mb"] += file_size
                                    stats["intervals"][interval]["size_mb"] += file_size

            return stats

        except Exception as e:
            self.logger.error("获取存储统计失败: %s", e)
            return {}

    def scan_and_repair_corrupted_files(
        self, auto_delete: bool = False, progress_callback=None
    ) -> Dict[str, Any]:
        """扫描并修复损坏的Parquet文件.

        Args:
            auto_delete: 是否自动删除损坏文件
            progress_callback: 进度回调函数

        Returns:
            Dict: 扫描结果 {"corrupted": [...], "deleted": [...]}
        """
        try:
            corrupted_files = []
            deleted_files = []

            # 遍历所有数据文件
            total_files = 0
            processed_files = 0

            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue

                    for file_path in interval_dir.iterdir():
                        if file_path.is_file() and file_path.suffix == ".parquet":
                            total_files += 1

            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue

                    for file_path in interval_dir.iterdir():
                        if file_path.is_file() and file_path.suffix == ".parquet":
                            processed_files += 1

                            # 更新进度
                            if progress_callback:
                                progress = processed_files / total_files if total_files > 0 else 0
                                progress_callback(progress, f"检查文件: {file_path.name}")

                            try:
                                # 尝试读取文件来检查是否损坏
                                df = pd.read_parquet(file_path)  # type: ignore
                                if df.empty:
                                    corrupted_files.append(str(file_path))
                                    if auto_delete:
                                        file_path.unlink()
                                        deleted_files.append(str(file_path))
                            except Exception as e:
                                self.logger.warning("发现损坏文件: %s, 错误: %s", file_path, e)
                                corrupted_files.append(str(file_path))
                                if auto_delete:
                                    try:
                                        file_path.unlink()
                                        deleted_files.append(str(file_path))
                                    except Exception as del_e:
                                        self.logger.error(
                                            "删除损坏文件失败: %s, 错误: %s", file_path, del_e
                                        )

            result = {
                "corrupted": corrupted_files,
                "deleted": deleted_files,
                "total_scanned": processed_files,
                "corrupted_count": len(corrupted_files),
                "deleted_count": len(deleted_files),
            }

            self.logger.info(
                "文件扫描完成: 扫描 %d 个文件，发现 %d 个损坏文件%s",
                processed_files,
                len(corrupted_files),
                f"，删除 {len(deleted_files)} 个" if auto_delete else "",
            )

            return result

        except Exception as e:
            self.logger.error("扫描损坏文件失败: %s", e)
            return {"corrupted": [], "deleted": [], "error": str(e)}


# ==================== 数据校验器 ====================


@dataclass
class ValidationResult:
    """数据校验结果"""

    symbol: str
    interval: str
    check_time: datetime
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    record_count: int
    date_range: Tuple[Optional[date], Optional[date]]
    missing_dates: List[date]
    logic_errors: List[Dict[str, Any]]
    format_errors: List[Dict[str, Any]]


@dataclass
class ValidationSummary:
    """校验汇总"""

    total_symbols: int
    valid_symbols: int
    invalid_symbols: int
    total_errors: int
    total_warnings: int
    check_time: datetime
    base_date: date


class DataValidator:
    """数据校验器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()

        # 交易日历实例（用于数据更新状态检测）
        self._trading_calendar = None
        self._latest_trading_day_cache = None  # 缓存最新交易日，避免重复查询

        # IPO缓存实例
        self._ipo_cache = IPODateCache()

    def preload_ipo_dates_batch(
        self, symbols: List[str], force_refresh: bool = False
    ) -> Dict[str, Any]:
        """批量预加载IPO日期

        在数据质量扫描前调用，避免单个查询的低效率

        Args:
            symbols: 品种列表
            force_refresh: 是否强制刷新

        Returns:
            下载结果统计
        """
        from ..data_acquisition.data_fetcher import download_ipo_dates

        self.logger.info(f"批量预加载IPO日期: {len(symbols)}个品种")

        result = download_ipo_dates(symbols=symbols, force_refresh=force_refresh, use_adaptive=True)

        self.logger.info(
            f"IPO批量下载完成: 总计{result['total']}, "
            f"跳过缓存{result['cached']}, "
            f"下载{result['downloaded']}, "
            f"成功{result['succeeded']}, "
            f"失败{result['failed']}"
        )

        return result

    def _get_ipo_date(self, symbol: str) -> Optional[date]:
        """获取单个品种IPO日期（优先缓存）

        改为完全依赖缓存，不再主动查询
        如果缓存未命中，返回None并记录警告

        Args:
            symbol: 品种代码

        Returns:
            上市日期，缓存未命中返回None
        """
        cached_date, is_cached = self._ipo_cache.get(symbol)

        if is_cached:
            return cached_date
        else:
            # 🔧 降级为DEBUG，避免启动时大量警告
            self.logger.debug("品种 %s IPO日期未缓存", symbol)
            return None

    def _validate_ipo_date(self, symbol: str, ipo_date: date) -> Optional[date]:
        """验证IPO日期合理性

        Args:
            symbol: 品种代码
            ipo_date: 待验证的IPO日期

        Returns:
            验证通过返回原日期，否则返回None
        """
        today = date.today()

        # 规则1：不能超过今天+30天
        if ipo_date > today + timedelta(days=30):
            self.logger.warning("品种 %s IPO日期异常（未来日期）: %s，拒绝", symbol, ipo_date)
            return None

        # 规则2：不能早于1990年
        if ipo_date.year < 1990:
            self.logger.warning("品种 %s IPO日期异常（过早）: %s，拒绝", symbol, ipo_date)
            return None

        return ipo_date

    def _compute_effective_start_date(
        self, symbol: str, data_start: Optional[date], base_date: Optional[date]
    ) -> date:
        """计算有效起始日期（智能起点计算算法）

        不使用推测，通过逻辑计算得出唯一正确值。

        逻辑：
        1. 如果IPO日期可用，使用IPO日期
        2. 否则使用max(数据起点, 基准日期)
        3. 如果都不可用，使用默认值2020-01-01

        Args:
            symbol: 品种代码
            data_start: 本地数据起点
            base_date: 配置的基准日期

        Returns:
            有效起始日期
        """
        # 1. 尝试获取IPO日期
        ipo_date = self._get_ipo_date(symbol)

        # 2. 计算有效起点
        candidates = []

        if ipo_date:
            candidates.append(ipo_date)

        if data_start:
            candidates.append(data_start)

        if base_date:
            candidates.append(base_date)

        # 3. 选择最大值（最近的日期）
        if candidates:
            effective_start = max(candidates)
            self.logger.debug(
                "品种 %s 有效起点: %s (IPO=%s, 数据起点=%s, 基准日=%s)",
                symbol,
                effective_start,
                ipo_date,
                data_start,
                base_date,
            )
            return effective_start
        else:
            # 4. 所有都不可用，使用默认值
            default_date = date(2020, 1, 1)
            self.logger.debug("品种 %s 使用默认起点: %s", symbol, default_date)
            return default_date

    def validate_symbol(self, symbol: str, interval: str) -> ValidationResult:
        """校验单个品种的数据"""
        try:
            # 查询数据
            df = self.storage_manager.query_kline(symbol, interval)

            if df is None or df.empty:
                return ValidationResult(
                    symbol=symbol,
                    interval=interval,
                    check_time=datetime.now(),
                    is_valid=False,
                    errors=["数据不存在"],
                    warnings=[],
                    record_count=0,
                    date_range=(None, None),
                    missing_dates=[],
                    logic_errors=[],
                    format_errors=[],
                )

            # 执行校验
            errors, warnings = self._validate_dataframe(df)

            # 计算日期范围
            date_range: Tuple[Optional[date], Optional[date]] = (None, None)
            try:
                if not df.empty and pd.api.types.is_datetime64_any_dtype(df.index):
                    min_val = df.index.min()
                    max_val = df.index.max()
                    if bool(pd.notna(min_val)) and bool(pd.notna(max_val)):
                        min_ts = pd.Timestamp(min_val)  # type: ignore
                        max_ts = pd.Timestamp(max_val)  # type: ignore
                        date_range = (min_ts.date(), max_ts.date())
                elif not df.empty and "datetime" in df.columns:
                    # 如果索引不是datetime类型，尝试使用datetime列
                    if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                        dt_min_val = df["datetime"].min()
                        dt_max_val = df["datetime"].max()
                        if bool(pd.notna(dt_min_val)) and bool(pd.notna(dt_max_val)):
                            dt_min = pd.Timestamp(dt_min_val)  # type: ignore
                            dt_max = pd.Timestamp(dt_max_val)  # type: ignore
                            date_range = (dt_min.date(), dt_max.date())
                    else:
                        # 尝试转换datetime列
                        datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                        if not datetime_series.isna().all():
                            dt_min_val = datetime_series.min()
                            dt_max_val = datetime_series.max()
                            if bool(pd.notna(dt_min_val)) and bool(pd.notna(dt_max_val)):
                                dt_min = pd.Timestamp(dt_min_val)  # type: ignore
                                dt_max = pd.Timestamp(dt_max_val)  # type: ignore
                                # 确保返回的是 date 类型而不是 NaTType
                                min_date_val = dt_min.date()
                                max_date_val = dt_max.date()
                                if isinstance(min_date_val, date) and isinstance(
                                    max_date_val, date
                                ):
                                    date_range = (min_date_val, max_date_val)
            except Exception:
                # 如果日期计算失败，保持为None
                pass

            return ValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=datetime.now(),
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                record_count=len(df),
                date_range=date_range,
                missing_dates=self._check_missing_dates(df, symbol=symbol),
                logic_errors=self._check_logic_errors(df),
                format_errors=self._check_format_errors(df),
            )

        except Exception as e:
            self.logger.error("校验失败: %s %s, %s", symbol, interval, e)
            return ValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=datetime.now(),
                is_valid=False,
                errors=[f"校验异常: {e}"],
                warnings=[],
                record_count=0,
                date_range=(None, None),
                missing_dates=[],
                logic_errors=[],
                format_errors=[],
            )

    def _validate_dataframe(self, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """校验DataFrame数据"""
        errors = []
        warnings = []

        # 检查必需列
        required_columns = ["datetime", "open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            errors.append(f"缺少必需列: {missing_columns}")

        # 检查数据类型
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    errors.append(f"{col}列不是数值类型")
                elif bool(df[col].isna().any()):
                    errors.append(f"{col}列包含空值")

        # 检查逻辑关系
        if all(col in df.columns for col in ["high", "low", "open", "close"]):
            # 检查high >= low
            if (df["high"] < df["low"]).any():
                errors.append("存在high < low的错误")

            # 检查价格合理性
            if (df["open"] <= 0).any() or (df["close"] <= 0).any():
                warnings.append("存在开盘价或收盘价<=0的情况")

        return errors, warnings

    def _check_missing_dates(self, df: pd.DataFrame, symbol: str = None) -> List[date]:
        """检查缺失日期（优化版：使用智能起点计算算法）

        Args:
            df: 数据DataFrame
            symbol: 品种代码（可选，用于获取上市日期）

        Returns:
            缺失的交易日列表
        """
        if df.empty or "datetime" not in df.columns:
            return []

        try:
            # 1. 获取数据中的实际日期
            date_series = self._extract_date_series(df)
            if date_series is None or date_series.empty:
                return []

            actual_dates = self._convert_to_date_set(date_series)
            if not actual_dates:
                return []

            # 2. 获取数据范围
            data_start = min(actual_dates)
            data_end = max(actual_dates)

            # 3. 获取基准日期
            base_date = config_manager.get_base_date()

            # 4. 计算有效起点（使用智能起点计算算法）
            effective_start = self._compute_effective_start_date(
                symbol=symbol, data_start=data_start, base_date=base_date
            )

            # 5. 确定检测终点（不能超过最近一个交易日）
            latest_trading_day = self._get_latest_trading_day()
            if latest_trading_day:
                check_end_date = min(data_end, latest_trading_day)
            else:
                # 如果获取最近交易日失败，使用今天作为上限
                check_end_date = min(data_end, date.today())

            # 6. 验证日期范围
            if effective_start > check_end_date:
                self.logger.warning(
                    "品种 %s 日期范围异常: effective_start(%s) > check_end_date(%s), "
                    "数据范围[%s~%s], 基准日=%s, 跳过缺失检测",
                    symbol,
                    effective_start,
                    check_end_date,
                    data_start,
                    data_end,
                    base_date,
                )
                return []

            # 7. 使用交易日历获取期望的交易日范围
            expected_trading_days = self._get_trading_days_range(effective_start, check_end_date)

            if not expected_trading_days:
                self.logger.debug("交易日历获取失败，跳过缺失日期检测")
                return []

            # 8. 计算缺失的交易日
            expected_dates = {
                datetime.strptime(d, "%Y-%m-%d").date() for d in expected_trading_days
            }
            missing_dates = list(expected_dates - actual_dates)
            missing_dates.sort()

            # 9. 日志输出
            if symbol and missing_dates:
                self.logger.debug(
                    "品种 %s 缺失检测: 数据范围[%s~%s], 检测范围[%s~%s], "
                    "基准日=%s, 最近交易日=%s, 期望=%d个, 实际=%d个, 缺失=%d个",
                    symbol,
                    data_start,
                    data_end,
                    effective_start,
                    check_end_date,
                    base_date,
                    latest_trading_day,
                    len(expected_dates),
                    len(actual_dates),
                    len(missing_dates),
                )

            return missing_dates

        except Exception as e:
            self.logger.error("检查缺失日期失败: %s", e, exc_info=True)
            return []

    def _extract_date_series(self, df: pd.DataFrame):
        """从DataFrame提取日期序列"""
        if not pd.api.types.is_datetime64_any_dtype(df.index):
            if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                return df["datetime"]
            else:
                return pd.to_datetime(df["datetime"], errors="coerce")
        else:
            return df.index

    def _convert_to_date_set(self, date_series) -> set:
        """将日期序列转换为date对象集合"""
        date_series = date_series.dropna()
        if date_series.empty:
            return set()

        try:
            if isinstance(date_series, pd.Series):
                return set(date_series.dt.date)
            else:
                return {pd.Timestamp(d).date() for d in date_series}
        except (AttributeError, TypeError):
            return set()

    def _get_trading_days_range(self, start_date: date, end_date: date) -> List[str]:
        """获取交易日范围（利用TradingCalendar的24h缓存）"""
        try:
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

            if self._trading_calendar is None:
                self._trading_calendar = TradingCalendar()

            # 使用线程池执行异步调用（避免事件循环冲突）
            def run_async_in_thread():
                """在新线程中运行异步代码"""
                try:
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(
                            self._trading_calendar.get_trading_days_in_range(
                                start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
                            )
                        )
                        return result
                    finally:
                        new_loop.close()
                        asyncio.set_event_loop(None)
                except Exception as e:
                    self.logger.error("线程内部异常: %s", e, exc_info=True)
                    raise

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_async_in_thread)
                try:
                    result = future.result(timeout=30)
                    if not result:
                        self.logger.debug("交易日范围为空: %s 至 %s", start_date, end_date)
                    return result
                except FutureTimeoutError:
                    self.logger.error("获取交易日范围超时（30秒）: %s 至 %s", start_date, end_date)
                    return []

        except FutureTimeoutError:
            self.logger.error("获取交易日范围超时: %s 至 %s", start_date, end_date)
            return []
        except Exception as e:
            self.logger.error("获取交易日范围失败: %s", e, exc_info=True)
            return []

    def _check_logic_errors(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查逻辑错误"""
        errors = []

        try:
            if "high" in df.columns and "low" in df.columns:
                invalid_high_low = df[df["high"] < df["low"]]
                for idx, row in invalid_high_low.iterrows():
                    # 转换索引为日期
                    try:
                        idx_date: Optional[date] = pd.Timestamp(idx).date() if pd.notna(idx) else None  # type: ignore
                    except (ValueError, TypeError):
                        idx_date = None
                    errors.append(
                        {
                            "type": "high_low_error",
                            "date": idx_date,
                            "high": row["high"],
                            "low": row["low"],
                        }
                    )

        except Exception as e:
            self.logger.error("检查逻辑错误失败: %s", e)

        return errors

    def _check_format_errors(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查格式错误"""
        errors = []

        try:
            # 检查数值类型
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                if col in df.columns:
                    # 使用 pd.isna() 而不是 .isna() 属性
                    non_numeric_mask = pd.isna(pd.to_numeric(df[col], errors="coerce"))
                    non_numeric = df[non_numeric_mask]
                    for idx, row in non_numeric.iterrows():
                        # 转换索引为日期
                        try:
                            idx_date: Optional[date] = pd.Timestamp(idx).date() if pd.notna(idx) else None  # type: ignore
                        except (ValueError, TypeError):
                            idx_date = None
                        errors.append(
                            {
                                "type": "format_error",
                                "column": col,
                                "date": idx_date,
                                "value": row[col],
                            }
                        )

        except Exception as e:
            self.logger.error("检查格式错误失败: %s", e)

        return errors

    def validate_all_data(self) -> ValidationSummary:
        """校验所有品种的数据

        Returns:
            ValidationSummary: 校验汇总结果
        """
        try:
            self.logger.info("开始全量数据校验...")

            # 获取所有品种（需要从配置文件或数据库获取品种列表）
            # 这里简化处理，假设从配置获取
            try:
                from ..config import config_manager

                reference_symbols = config_manager.get("chinastock.symbols", [])
                if not reference_symbols:
                    # 如果配置中没有品种列表，返回空结果
                    return ValidationSummary(
                        total_symbols=0,
                        valid_symbols=0,
                        invalid_symbols=0,
                        total_errors=0,
                        total_warnings=0,
                        check_time=datetime.now(),
                        base_date=date.today(),
                    )
            except Exception:
                reference_symbols = []

            # 校验所有品种
            total_symbols = len(reference_symbols)
            valid_symbols = 0
            invalid_symbols = 0
            total_errors = 0
            total_warnings = 0

            for symbol in reference_symbols:
                try:
                    # 校验所有时间周期
                    intervals = ["1d", "5m", "1m"]
                    for interval in intervals:
                        result = self.validate_symbol(symbol, interval)
                        if result.is_valid:
                            valid_symbols += 1
                        else:
                            invalid_symbols += 1
                            total_errors += len(result.errors)
                            total_warnings += len(result.warnings)

                except Exception as e:
                    self.logger.error("校验品种 %s 失败: %s", symbol, e)
                    invalid_symbols += 1

            return ValidationSummary(
                total_symbols=total_symbols,
                valid_symbols=valid_symbols,
                invalid_symbols=invalid_symbols,
                total_errors=total_errors,
                total_warnings=total_warnings,
                check_time=datetime.now(),
                base_date=date.today(),
            )

        except Exception as e:
            self.logger.error("全量数据校验失败: %s", e)
            return ValidationSummary(
                total_symbols=0,
                valid_symbols=0,
                invalid_symbols=0,
                total_errors=0,
                total_warnings=0,
                check_time=datetime.now(),
                base_date=date.today(),
            )

    def check_data_freshness(self, symbol: str, interval: str = "1d") -> Dict[str, Any]:
        """检查数据更新状态（数据是否包含最新交易日）

        Args:
            symbol: 品种代码
            interval: K线周期，默认"1d"

        Returns:
            Dict: {
                "latest_trading_day": date,      # 最新交易日
                "local_latest_date": date,       # 本地最新数据日期
                "gap_days": int,                 # 滞后天数（交易日）
                "is_up_to_date": bool,          # 是否最新
                "has_data": bool                 # 是否有数据
            }
        """
        try:
            # 获取最新交易日（使用缓存避免重复查询）
            latest_trading_day = self._get_latest_trading_day()

            if latest_trading_day is None:
                # 交易日历获取失败，使用降级方案
                self.logger.warning("无法获取交易日历，使用当前日期作为降级方案")
                latest_trading_day = date.today()

            # 读取本地数据
            df = self.storage_manager.query_kline(symbol, interval)

            if df is None or df.empty:
                return {
                    "latest_trading_day": latest_trading_day,
                    "local_latest_date": None,
                    "gap_days": -1,  # -1表示无数据
                    "is_up_to_date": False,
                    "has_data": False,
                }

            # 获取本地最新数据日期
            local_latest_date = self._get_latest_date_from_df(df)

            if local_latest_date is None:
                return {
                    "latest_trading_day": latest_trading_day,
                    "local_latest_date": None,
                    "gap_days": -1,
                    "is_up_to_date": False,
                    "has_data": False,
                }

            # 计算滞后天数（交易日维度）
            gap_days = self._calculate_trading_days_gap(local_latest_date, latest_trading_day)

            # 判断是否最新（允许1个交易日的延迟）
            is_up_to_date = gap_days <= 1

            return {
                "latest_trading_day": latest_trading_day,
                "local_latest_date": local_latest_date,
                "gap_days": gap_days,
                "is_up_to_date": is_up_to_date,
                "has_data": True,
            }

        except Exception as e:
            self.logger.error("检查数据更新状态失败: %s %s, %s", symbol, interval, e)
            return {
                "latest_trading_day": date.today(),
                "local_latest_date": None,
                "gap_days": -1,
                "is_up_to_date": False,
                "has_data": False,
            }

    def _get_latest_trading_day(self) -> Optional[date]:
        """获取最新交易日（带缓存）"""
        try:
            # 检查缓存是否有效（当天缓存）
            if self._latest_trading_day_cache is not None:
                cache_date, cached_value = self._latest_trading_day_cache
                if cache_date == date.today():
                    return cached_value

            # 缓存失效，重新获取
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio
            from concurrent.futures import ThreadPoolExecutor

            if self._trading_calendar is None:
                self._trading_calendar = TradingCalendar()

            # 🆕 使用线程池执行异步调用（避免事件循环冲突）
            def run_async_in_thread():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self._trading_calendar.get_previous_trading_day()
                    )
                finally:
                    new_loop.close()

            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_in_thread)
                    result_str = future.result(timeout=10)
            except Exception as e:
                self.logger.error("交易日历异步调用失败: %s", e, exc_info=True)
                return None

            if result_str:
                # 解析日期字符串 "YYYY-MM-DD"
                latest_day = datetime.strptime(result_str, "%Y-%m-%d").date()
                # 更新缓存
                self._latest_trading_day_cache = (date.today(), latest_day)
                return latest_day

            return None

        except Exception as e:
            self.logger.error("获取最新交易日失败: %s", e)
            return None

    def _get_latest_date_from_df(self, df: pd.DataFrame) -> Optional[date]:
        """从DataFrame中获取最新数据日期"""
        try:
            if df.empty:
                return None

            # 尝试从索引获取
            if pd.api.types.is_datetime64_any_dtype(df.index):
                max_val = df.index.max()
                if bool(pd.notna(max_val)):
                    return pd.Timestamp(max_val).date()  # type: ignore

            # 尝试从datetime列获取
            if "datetime" in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                    max_val = df["datetime"].max()
                    if bool(pd.notna(max_val)):
                        return pd.Timestamp(max_val).date()  # type: ignore
                else:
                    # 尝试转换
                    datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                    max_val = datetime_series.max()
                    if bool(pd.notna(max_val)):
                        return pd.Timestamp(max_val).date()  # type: ignore

            return None

        except Exception as e:
            self.logger.error("获取最新数据日期失败: %s", e)
            return None

    def _calculate_trading_days_gap(self, local_date: date, latest_trading_day: date) -> int:
        """计算滞后的交易日天数"""
        try:
            if local_date >= latest_trading_day:
                return 0

            # 使用交易日历计算交易日数量
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio

            if self._trading_calendar is None:
                self._trading_calendar = TradingCalendar()

            # 同步包装异步调用
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._trading_calendar.get_trading_days_in_range(
                            local_date.strftime("%Y-%m-%d"), latest_trading_day.strftime("%Y-%m-%d")
                        ),
                        loop,
                    )
                    trading_days = future.result(timeout=5)
                else:
                    trading_days = asyncio.run(
                        self._trading_calendar.get_trading_days_in_range(
                            local_date.strftime("%Y-%m-%d"), latest_trading_day.strftime("%Y-%m-%d")
                        )
                    )
            except RuntimeError:
                trading_days = asyncio.run(
                    self._trading_calendar.get_trading_days_in_range(
                        local_date.strftime("%Y-%m-%d"), latest_trading_day.strftime("%Y-%m-%d")
                    )
                )

            # 交易日列表包含起始日期，所以gap = len - 1
            gap = max(0, len(trading_days) - 1)
            return gap

        except Exception as e:
            self.logger.error("计算交易日差距失败: %s", e)
            # 降级方案：使用自然日差距
            return (latest_trading_day - local_date).days


# ==================== 数据感知器 ====================


@dataclass
class QualityOverview:
    """数据质量概览"""

    total_symbols: int
    missing_symbols: int  # 品种缺失（完全无数据）
    error_symbols: int
    warning_symbols: int
    quality_score: int
    last_scan_time: datetime
    base_date: date
    scanned_intervals: List[str]
    details: List[Dict[str, Any]]

    # 🆕 数据更新状态字段
    outdated_symbols: int = 0  # 数据过时的品种数
    avg_gap_days: int = 0  # 平均滞后天数（交易日）
    max_gap_days: int = 0  # 最大滞后天数（交易日）
    
    # 🆕 数据缺失与滞后字段
    data_missing_symbols: int = 0  # 数据缺失（有数据但部分日期缺失，排除数据滞后）
    data_lagging_days: int = 0  # 数据滞后天数（连续的全品种缺失）


@dataclass
class SymbolQuality:
    """单个品种的质量信息"""

    symbol: str
    intervals: Dict[str, ValidationResult]
    overall_score: int
    has_errors: bool
    has_warnings: bool
    is_missing: bool


class DataSensor:
    """数据感知器"""

    def __init__(self, event_engine=None):
        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()
        self.validator = DataValidator()
        self.event_engine = event_engine

        # 缓存质量概览
        self._quality_overview: Optional[QualityOverview] = None

        # 文件监控器
        self.data_file_watcher: Optional[DataFileWatcher] = None

        # 🆕 混合异步架构组件（延迟初始化）
        self._resource_monitor = None
        self._file_scanner = None
        self._scheduler = None
        self._async_executor = None
        self._cpu_worker = None
        self._hybrid_async_enabled = False

    def scan_all_data(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
    ) -> QualityOverview:
        """扫描所有数据质量（优化版：并发扫描，只返回有问题的品种详情）"""
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        if not force_refresh and self._quality_overview is not None:
            return self._quality_overview

        try:
            # 🆕 优化1：跳过无数据的品种
            local_data_index = self.storage_manager.get_local_data_index()
            symbols_with_data = [s for s in reference_symbols if s in local_data_index]

            self.logger.info(
                "开始数据质量扫描: 总品种%d个，本地有数据%d个（将并发扫描）",
                len(reference_symbols),
                len(symbols_with_data),
            )

            # 🆕 添加terminal输出
            import sys

            print(
                f"   开始扫描：总品种{len(reference_symbols)}个，本地有数据{len(symbols_with_data)}个"
            )
            print(f"   扫描周期：{', '.join(intervals)}")
            sys.stdout.flush()

            total_symbols = len(reference_symbols)
            missing_symbols = total_symbols - len(symbols_with_data)
            error_symbols = 0
            warning_symbols = 0

            # 🆕 数据更新状态统计
            outdated_symbols = 0
            gap_days_list = []  # 收集所有滞后天数用于计算平均值

            symbol_qualities = []
            scanned_intervals = []

            # 🆕 优化2：使用线程池并发扫描
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import threading

            lock = threading.Lock()

            def scan_single(symbol):
                """扫描单个品种（线程安全）"""
                try:
                    symbol_quality = self._scan_symbol_quality(symbol, intervals)
                    return symbol_quality
                except Exception as e:
                    self.logger.error("扫描品种 %s 失败: %s", symbol, e)
                    return None

            # 使用线程池并发扫描（最多10个线程）
            # 🆕 计算进度报告步长（每5%报告一次）
            total_symbols = len(symbols_with_data)
            progress_step = max(1, total_symbols // 20)  # 每5%报告一次

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(scan_single, s): s for s in symbols_with_data}

                completed = 0
                for future in as_completed(futures):
                    symbol_quality = future.result()
                    if symbol_quality:
                        with lock:
                            symbol_qualities.append(symbol_quality)

                            if symbol_quality.has_errors:
                                error_symbols += 1
                            if symbol_quality.has_warnings:
                                warning_symbols += 1

                            scanned_intervals.extend(intervals)

                        completed += 1

                        # 🆕 报告进度（每5%或每500个品种）
                        if completed % progress_step == 0 or completed % 500 == 0:
                            percent = int((completed / total_symbols) * 100)
                            if progress_callback:
                                progress_callback(percent)
                            if completed % 500 == 0:
                                # 🆕 添加terminal输出
                                print(f"   扫描进度: {completed}/{total_symbols} ({percent}%)")
                                sys.stdout.flush()
                                self.logger.info(
                                    "扫描进度: %d/%d (%d%%)", completed, total_symbols, percent
                                )

            # 🆕 批量检测数据更新状态（仅检测1d周期，避免重复）
            self.logger.info("开始检测数据更新状态...")

            # 批量统计变量（每1000个品种报告一次）
            batch_size = 1000
            batch_success = []
            batch_errors = []
            batch_count = 0

            for idx, symbol in enumerate(symbols_with_data, 1):
                try:
                    freshness = self.validator.check_data_freshness(symbol, "1d")
                    if freshness["has_data"]:
                        gap_days = freshness["gap_days"]
                        if gap_days > 1:  # 滞后超过1个交易日则算过时
                            outdated_symbols += 1
                        if gap_days >= 0:  # -1表示无数据，不计入平均值
                            gap_days_list.append(gap_days)
                    batch_success.append(symbol)
                except Exception as e:
                    batch_errors.append((symbol, str(e)))
                    self.logger.debug("检测品种 %s 数据更新状态失败: %s", symbol, e)

                batch_count += 1

                # 每1000个品种或最后一批，输出统计
                if batch_count == batch_size or idx == len(symbols_with_data):
                    total_in_batch = len(batch_success) + len(batch_errors)
                    if batch_errors:
                        # 有错误的情况
                        first_symbols = [e[0] for e in batch_errors[:3]]
                        error_summary = f"{', '.join(first_symbols)}等{len(batch_errors)}个品种"
                        # 统计错误类型
                        error_types = {}
                        for _, err_msg in batch_errors:
                            if "交易日历获取失败" in err_msg:
                                error_types["交易日历获取失败"] = (
                                    error_types.get("交易日历获取失败", 0) + 1
                                )
                            elif "cannot schedule new futures" in err_msg:
                                error_types["线程池关闭错误"] = (
                                    error_types.get("线程池关闭错误", 0) + 1
                                )
                            else:
                                error_types["其他错误"] = error_types.get("其他错误", 0) + 1

                        error_detail = ", ".join([f"{k}({v}个)" for k, v in error_types.items()])
                        print(f"   ⚠️ {error_summary}检测失败: {error_detail}")
                    else:
                        # 全部成功
                        first_symbols = batch_success[:3]
                        print(f"   ✓ {', '.join(first_symbols)}等{total_in_batch}个品种成功验证")

                    sys.stdout.flush()

                    # 重置批次统计
                    batch_success = []
                    batch_errors = []
                    batch_count = 0

            # 计算数据更新状态指标
            avg_gap_days = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0
            max_gap_days = max(gap_days_list) if gap_days_list else 0

            # 🆕 计算数据滞后和数据缺失
            print("\n" + "🔍 开始调用 _calculate_lagging_and_missing...", flush=True)
            data_lagging_days, data_missing_symbols = self._calculate_lagging_and_missing(
                symbols_with_data=symbols_with_data,
                reference_symbols=reference_symbols,
                base_date=date.today(),  # TODO: 从配置读取
                interval="1d"
            )
            print(f"✅ 计算结果: 滞后={data_lagging_days}天, 缺失={data_missing_symbols}个品种\n", flush=True)

            # 计算整体质量评分
            if total_symbols > 0:
                quality_score = int(
                    (
                        (
                            total_symbols
                            - missing_symbols
                            - error_symbols * 2
                            - warning_symbols * 0.5
                        )
                        / total_symbols
                    )
                    * 100
                )
            else:
                quality_score = 100

            quality_score = max(0, min(100, quality_score))

            # 🆕 优化3：只保留有问题的品种详情
            problem_details = [
                {
                    "symbol": sq.symbol,
                    "status": self._determine_status(sq),
                    "score": sq.overall_score,
                    "has_errors": sq.has_errors,
                    "has_warnings": sq.has_warnings,
                    "is_missing": sq.is_missing,
                    "issues": self._collect_issues(sq),
                }
                for sq in symbol_qualities
                if sq.has_errors or sq.has_warnings or sq.is_missing
            ]

            # 🆕 按问题严重程度排序
            problem_details.sort(
                key=lambda d: {"missing": 1, "error": 2, "warning": 3}.get(d["status"], 4)
            )
            
            print(f"📋 问题品种详情: {len(problem_details)}个有问题品种", flush=True)
            if problem_details:
                print(f"   前3个问题品种: {[d['symbol'] + '(' + d['status'] + ')' for d in problem_details[:3]]}", flush=True)

            overview = QualityOverview(
                total_symbols=total_symbols,
                missing_symbols=missing_symbols,
                error_symbols=error_symbols,
                warning_symbols=warning_symbols,
                quality_score=quality_score,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=list(set(scanned_intervals)),
                details=problem_details,  # 🆕 只包含有问题的品种
                # 🆕 数据更新状态
                outdated_symbols=outdated_symbols,
                avg_gap_days=avg_gap_days,
                max_gap_days=max_gap_days,
                # 🆕 数据缺失与滞后
                data_missing_symbols=data_missing_symbols,
                data_lagging_days=data_lagging_days,
            )

            self._quality_overview = overview

            #  发送事件
            if self.event_engine:
                self._send_quality_update_event(overview)

            # 🆕 保存IPO缓存
            self.validator._ipo_cache.batch_save()

            # 🆕 输出IPO缓存统计信息
            cache_stats = self.validator._ipo_cache.get_stats()
            self.logger.info(
                "✓ 数据质量扫描完成: 评分=%d, 总计=%d, 缺失=%d, 错误=%d, 警告=%d, 过时=%d, 平均滞后=%d天, 问题品种=%d个",
                quality_score,
                total_symbols,
                missing_symbols,
                error_symbols,
                warning_symbols,
                outdated_symbols,
                avg_gap_days,
                len(problem_details),
            )

            self.logger.info(
                "📈 IPO缓存统计: 缓存大小=%d, 命中率=%.1f%%, API调用=%d次, 成功率=%.1f%%, 超时=%d次",
                cache_stats["cache_size"],
                cache_stats["hit_rate"],
                cache_stats["api_calls"],
                (
                    (cache_stats["api_success"] / cache_stats["api_calls"] * 100)
                    if cache_stats["api_calls"] > 0
                    else 0
                ),
                cache_stats["api_timeout"],
            )

            # 🆕 添加terminal摘要输出
            import sys

            print("\n" + "   " + "-" * 60)
            print(f"   扫描完成摘要：")
            print(f"   - 总品种数：{total_symbols}")
            print(f"   - 本地有数据：{total_symbols - missing_symbols}")
            print(f"   - 缺失品种：{missing_symbols}")
            print(f"   - 错误品种：{error_symbols}")
            print(f"   - 警告品种：{warning_symbols}")
            print(f"   - 过时品种：{outdated_symbols}")
            print(f"   - 平均滞后：{avg_gap_days}天")
            print(f"   - 质量评分：{quality_score}/100")
            print(
                f"   IPO缓存：{cache_stats['cache_size']}个品种，命中率{cache_stats['hit_rate']:.1f}%"
            )
            print("   " + "-" * 60)
            sys.stdout.flush()

            return overview

        except Exception as e:
            self.logger.error("数据质量扫描失败: %s", e, exc_info=True)
            return QualityOverview(
                total_symbols=0,
                missing_symbols=0,
                error_symbols=0,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=[],
                details=[],
            )

    def trigger_scan_with_symbols(
        self,
        symbol_loader,
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
    ) -> QualityOverview:
        """
        触发数据质量扫描（自动获取品种列表，从core.py迁移）

        Args:
            symbol_loader: SymbolLoader实例（用于获取品种列表）
            intervals: 扫描周期列表（可选，默认 ["1d", "5m", "1m"]）
            force_refresh: 是否强制刷新（忽略缓存）
            progress_callback: 进度回调函数 callback(percent)

        Returns:
            质量概览
        """
        try:
            # 从SymbolLoader获取所有品种代码
            reference_symbols = symbol_loader.extract_all_codes()

            if not reference_symbols:
                self.logger.warning("品种列表为空，无法执行扫描")
                return QualityOverview(
                    total_symbols=0,
                    missing_symbols=0,
                    error_symbols=0,
                    warning_symbols=0,
                    quality_score=0,
                    last_scan_time=datetime.now(),
                    base_date=date.today(),
                    scanned_intervals=[],
                    details=[],
                )

            self.logger.info("开始数据质量扫描，品种数量: %d", len(reference_symbols))

            # 执行扫描
            overview = self.scan_all_data(
                reference_symbols=reference_symbols,
                intervals=intervals,
                force_refresh=force_refresh,
                progress_callback=progress_callback,
            )

            return overview

        except Exception as e:
            self.logger.error("触发数据质量扫描失败: %s", e, exc_info=True)
            return QualityOverview(
                total_symbols=0,
                missing_symbols=0,
                error_symbols=0,
                warning_symbols=0,
                quality_score=0,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=[],
                details=[],
            )

    def start_sensing_async(self, symbol_loader):
        """
        启动数据感知（异步，从core.py迁移）

        Args:
            symbol_loader: SymbolLoader实例
        """
        import threading

        def scan_in_background():
            try:
                self.logger.info("【后台线程】开始数据质量扫描...")

                # 使用统一方法（自动获取品种列表）
                overview = self.trigger_scan_with_symbols(
                    symbol_loader=symbol_loader,
                    force_refresh=True,
                )

                self.logger.info(
                    "【后台线程】数据质量扫描完成: 评分=%s, 缺失=%s, 错误=%s",
                    overview.quality_score,
                    overview.missing_symbols,
                    overview.error_symbols,
                )

                # 启动文件监控
                self.start_file_watcher()

            except Exception as e:
                self.logger.error("【后台线程】数据质量扫描失败: %s", e, exc_info=True)

        # 启动守护线程
        scan_thread = threading.Thread(
            target=scan_in_background,
            daemon=True,
            name="DataSensingScanThread",
        )
        scan_thread.start()
        self.logger.info("数据感知后台扫描线程已启动")

    def start_file_watcher(self) -> bool:
        """
        启动数据文件监控（从core.py迁移）

        Returns:
            是否启动成功
        """
        from ..config import config_manager

        try:
            if self.data_file_watcher and self.data_file_watcher.is_running:
                self.logger.warning("数据文件监控已在运行")
                return False

            # 创建文件监控器
            data_dir = config_manager.get_data_dir()
            self.data_file_watcher = DataFileWatcher(
                data_dir=data_dir,
                callback=self.on_file_changed,
            )

            # 启动监控
            success = self.data_file_watcher.start()

            if success:
                self.logger.info("✅ 数据文件监控已启动")
            else:
                self.logger.warning("⚠️ 数据文件监控启动失败（可能是watchdog不可用）")

            return success

        except Exception as e:
            self.logger.error("启动数据文件监控失败: %s", e, exc_info=True)
            return False

    def stop_sensing(self) -> bool:
        """
        停止数据感知（从core.py迁移）

        Returns:
            是否停止成功
        """
        try:
            # 停止文件监控
            if self.data_file_watcher:
                self.data_file_watcher.stop()
                self.data_file_watcher = None
                self.logger.info("数据文件监控已停止")

            return True

        except Exception as e:
            self.logger.error("停止数据感知失败: %s", e)
            return False

    def _determine_status(self, symbol_quality: SymbolQuality) -> str:
        """确定品种状态

        Args:
            symbol_quality: 品种质量信息

        Returns:
            状态字符串：missing/error/warning/normal
        """
        if symbol_quality.is_missing:
            return "missing"
        elif symbol_quality.has_errors:
            return "error"
        elif symbol_quality.has_warnings:
            return "warning"
        else:
            return "normal"

    def _collect_issues(self, symbol_quality: SymbolQuality) -> str:
        """收集品种的问题描述

        Args:
            symbol_quality: 品种质量信息

        Returns:
            问题描述字符串（最多显示3个问题）
        """
        issues = []

        for interval, result in symbol_quality.intervals.items():
            # 收集错误
            if result.errors:
                for error in result.errors[:2]:  # 每个周期最多2个错误
                    issues.append(f"[{interval}] {error}")

            # 收集警告
            if result.warnings:
                for warning in result.warnings[:2]:  # 每个周期最多2个警告
                    issues.append(f"[{interval}] {warning}")

            # 如果已收集足够问题，提前退出
            if len(issues) >= 3:
                break

        if not issues:
            return "无问题"

        # 最多显示3个问题
        return "; ".join(issues[:3])

    def _calculate_lagging_and_missing(
        self,
        symbols_with_data: List[str],
        reference_symbols: List[str],
        base_date: date,
        interval: str = "1d"
    ) -> tuple:
        """计算数据滞后和数据缺失
        
        逻辑：
        1. 从最新交易日往前遍历
        2. 找到第一段连续的"所有品种都缺失数据"的日期范围 → 数据滞后
        3. 这段范围之前的日期，有数据的品种中，缺失部分日期的品种数 → 数据缺失
        
        Args:
            symbols_with_data: 本地有数据的品种列表
            reference_symbols: 参考品种列表（全部品种）
            base_date: 基准日期
            interval: 时间周期（默认1d）
        
        Returns:
            (data_lagging_days, data_missing_symbols)
        """
        import sys
        print("\n" + "="*70, file=sys.stderr)
        print("🔍 [DEBUG] 开始计算数据滞后和数据缺失", file=sys.stderr)
        print(f"   本地有数据品种: {len(symbols_with_data)}个", file=sys.stderr)
        print(f"   参考品种: {len(reference_symbols)}个", file=sys.stderr)
        print(f"   基准日期: {base_date}", file=sys.stderr)
        print("="*70, file=sys.stderr)
        sys.stderr.flush()
        
        try:
            from backend.infrastructure.tdx_asyncio.calendar import TradingCalendar
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            # 获取交易日历
            trading_calendar_obj = TradingCalendar()
            
            # 在新线程中运行异步代码
            def run_async_in_thread():
                """在新线程中运行异步代码"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    today = date.today()
                    # 获取今年和去年的交易日历
                    df_this_year = new_loop.run_until_complete(
                        trading_calendar_obj.get_trading_calendar(today.year)
                    )
                    df_last_year = new_loop.run_until_complete(
                        trading_calendar_obj.get_trading_calendar(today.year - 1)
                    )
                    # 合并两年的交易日
                    trading_days = []
                    if df_this_year is not None and not df_this_year.empty:
                        trading_days.extend(df_this_year['date'].tolist())
                    if df_last_year is not None and not df_last_year.empty:
                        trading_days.extend(df_last_year['date'].tolist())
                    return trading_days
                finally:
                    new_loop.close()
            
            try:
                print("   步骤1: 获取交易日历...", file=sys.stderr)
                sys.stderr.flush()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(run_async_in_thread)
                    trading_calendar = future.result(timeout=10)
                print(f"   ✓ 获取到交易日: {len(trading_calendar) if trading_calendar else 0}天", file=sys.stderr)
                sys.stderr.flush()
            except Exception as e:
                print(f"   ✗ 交易日历获取失败: {e}", file=sys.stderr)
                sys.stderr.flush()
                self.logger.error("交易日历异步调用失败: %s", e, exc_info=True)
                return (0, 0)
            
            if not trading_calendar:
                print("   ✗ 交易日历为空", file=sys.stderr)
                sys.stderr.flush()
                self.logger.warning("交易日历不可用，无法计算数据滞后和缺失")
                return (0, 0)
            
            # 获取从base_date到今天的所有交易日
            today = date.today()
            trading_days = [
                d for d in trading_calendar
                if isinstance(d, date) and base_date <= d <= today
            ]
            
            if not trading_days:
                return (0, 0)
            
            trading_days.sort()
            latest_trading_day = trading_days[-1]
            
            # 步骤1：从最新交易日往前遍历，统计每个交易日有数据的品种数
            # 构建每个品种的数据日期集合
            print(f"   步骤2: 构建品种数据日期集合（{len(symbols_with_data)}个品种）...", file=sys.stderr)
            sys.stderr.flush()
            symbol_date_sets = {}
            for idx, symbol in enumerate(symbols_with_data):
                try:
                    # 获取品种的所有数据
                    df = self.storage_manager.query_kline(symbol, interval)
                    if df is not None and not df.empty:
                        # 从DataFrame中提取日期
                        if 'date' in df.columns:
                            data_dates = [d.date() if isinstance(d, datetime) else d for d in df['date'].tolist()]
                        elif df.index.name == 'date' or 'datetime' in str(df.index.dtype):
                            data_dates = [d.date() if isinstance(d, datetime) else d for d in df.index.tolist()]
                        else:
                            continue
                        symbol_date_sets[symbol] = set(data_dates)
                    
                    # 每1000个品种输出一次进度
                    if (idx + 1) % 1000 == 0:
                        print(f"      已处理 {idx + 1}/{len(symbols_with_data)} 品种", file=sys.stderr)
                        sys.stderr.flush()
                except Exception as e:
                    self.logger.debug(f"获取品种{symbol}数据日期失败: {e}")
                    continue
            
            print(f"   ✓ 构建完成，有效品种: {len(symbol_date_sets)}个", file=sys.stderr)
            sys.stderr.flush()
            
            # 步骤2：从最新交易日往前找连续的全品种缺失段
            print(f"   步骤3: 计算数据滞后天数（从{len(trading_days)}个交易日倒序检查）...", file=sys.stderr)
            sys.stderr.flush()
            data_lagging_days = 0
            lagging_start_idx = len(trading_days)  # 数据滞后开始的索引（不含）
            
            for idx in range(len(trading_days) - 1, -1, -1):
                trading_day = trading_days[idx]
                # 统计这一天有数据的品种数
                symbols_with_data_on_day = sum(
                    1 for date_set in symbol_date_sets.values()
                    if trading_day in date_set
                )
                
                if symbols_with_data_on_day == 0:
                    # 这一天所有品种都缺失数据
                    data_lagging_days += 1
                else:
                    # 找到第一个有数据的日期，滞后计算结束
                    lagging_start_idx = idx + 1
                    print(f"   ✓ 数据滞后: {data_lagging_days}天 (从{trading_days[idx]}往后)", file=sys.stderr)
                    sys.stderr.flush()
                    break
            
            # 步骤3：统计数据缺失品种数（排除滞后日期）
            # 数据缺失定义：在非滞后日期范围内，品种有数据但部分日期缺失
            print(f"   步骤4: 计算数据缺失品种数（检查非滞后日期范围）...", file=sys.stderr)
            sys.stderr.flush()
            data_missing_symbols = 0
            
            if lagging_start_idx > 0:
                # 只检查非滞后的日期范围
                non_lagging_trading_days = trading_days[:lagging_start_idx]
                
                if non_lagging_trading_days:
                    expected_days_count = len(non_lagging_trading_days)
                    print(f"      非滞后日期范围: {expected_days_count}个交易日", file=sys.stderr)
                    sys.stderr.flush()
                    
                    for symbol, date_set in symbol_date_sets.items():
                        # 统计该品种在非滞后日期范围内的数据完整性
                        actual_days_in_range = sum(
                            1 for d in non_lagging_trading_days
                            if d in date_set
                        )
                        
                        # 如果有数据但不完整，计为数据缺失
                        if 0 < actual_days_in_range < expected_days_count:
                            data_missing_symbols += 1
                    
                    print(f"   ✓ 数据缺失: {data_missing_symbols}个品种", file=sys.stderr)
                    sys.stderr.flush()
            else:
                print(f"   ✓ 数据缺失: 0个品种（全部数据滞后）", file=sys.stderr)
                sys.stderr.flush()
            
            print("\n" + "="*70, file=sys.stderr)
            print(f"✅ [DEBUG] 计算完成", file=sys.stderr)
            print(f"   数据滞后: {data_lagging_days}天", file=sys.stderr)
            print(f"   数据缺失: {data_missing_symbols}个品种", file=sys.stderr)
            print("="*70 + "\n", file=sys.stderr)
            sys.stderr.flush()
            
            self.logger.info(
                f"数据滞后与缺失统计: 滞后{data_lagging_days}天, "
                f"数据缺失{data_missing_symbols}个品种"
            )
            
            return (data_lagging_days, data_missing_symbols)
            
        except Exception as e:
            print(f"\n❌ [DEBUG] 计算失败: {e}", file=sys.stderr)
            sys.stderr.flush()
            self.logger.error(f"计算数据滞后和缺失失败: {e}", exc_info=True)
            return (0, 0)

    def _scan_symbol_quality(self, symbol: str, intervals: List[str]) -> SymbolQuality:
        """扫描单个品种的质量"""
        interval_results = {}

        for interval in intervals:
            try:
                result = self.validator.validate_symbol(symbol, interval)
                interval_results[interval] = result

                # 检查是否有数据
                has_data = result.record_count > 0

                if not has_data:
                    return SymbolQuality(
                        symbol=symbol,
                        intervals=interval_results,
                        overall_score=0,
                        has_errors=True,
                        has_warnings=False,
                        is_missing=True,
                    )

            except Exception as e:
                self.logger.error("扫描品种 %s %s 失败: %s", symbol, interval, e)
                interval_results[interval] = ValidationResult(
                    symbol=symbol,
                    interval=interval,
                    check_time=datetime.now(),
                    is_valid=False,
                    errors=[f"扫描失败: {e}"],
                    warnings=[],
                    record_count=0,
                    date_range=(None, None),
                    missing_dates=[],
                    logic_errors=[],
                    format_errors=[],
                )

        # 计算整体评分
        has_errors = any(r.errors for r in interval_results.values())
        has_warnings = any(r.warnings for r in interval_results.values())

        # 计算平均评分（简单算法）
        valid_results = [r for r in interval_results.values() if r.record_count > 0]
        if valid_results:
            avg_score = sum(100 if r.is_valid else 50 for r in valid_results) / len(valid_results)
        else:
            avg_score = 0

        return SymbolQuality(
            symbol=symbol,
            intervals=interval_results,
            overall_score=int(avg_score),
            has_errors=has_errors,
            has_warnings=has_warnings,
            is_missing=False,
        )

    def _send_quality_update_event(self, overview: QualityOverview):
        """发送质量更新事件"""
        try:
            if not self.event_engine:
                return

            from vnpy.event import Event

            event_data = {
                "overview": {
                    "total_symbols": overview.total_symbols,
                    "missing_symbols": overview.missing_symbols,
                    "error_symbols": overview.error_symbols,
                    "warning_symbols": overview.warning_symbols,
                    "quality_score": overview.quality_score,
                    "last_scan_time": overview.last_scan_time.isoformat(),
                    # 🆕 数据更新状态
                    "outdated_symbols": overview.outdated_symbols,
                    "avg_gap_days": overview.avg_gap_days,
                    "max_gap_days": overview.max_gap_days,
                    # 🆕 数据缺失与滞后
                    "data_missing_symbols": overview.data_missing_symbols,
                    "data_lagging_days": overview.data_lagging_days,
                },
                "timestamp": datetime.now(),
            }

            event = Event("eDataQualityUpdate", event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发送质量更新事件失败: %s", e)

    def on_file_changed(self, event_type: str, file_path: Path) -> None:
        """
        文件变化回调方法

        当数据文件发生变化时，清除质量概览缓存以便下次重新计算

        Args:
            event_type: 事件类型 (created/modified/moved/deleted)
            file_path: 发生变化的文件路径
        """
        try:
            self.logger.info("检测到数据文件变化 [%s]: %s", event_type, file_path)
            # 清除缓存，下次访问时会重新扫描
            self._quality_overview = None
            self.logger.info("数据质量缓存已清除，将在下次访问时重新扫描")
        except Exception as e:
            self.logger.error("处理文件变化事件失败: %s", e)

    def get_quality_overview(self) -> Optional[QualityOverview]:
        """
        获取质量概览

        Returns:
            Optional[QualityOverview]: 若尚未扫描或缓存已清空则返回 None
        """
        return self._quality_overview

    # 🆕 ==================== 自适应数据质量扫描 ====================

    def scan_all_data_adaptive(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
    ) -> QualityOverview:
        """自适应数据质量扫描（增量推送版）

        根据设备性能和数据规模自动选择最优扫描策略，并分阶段推送结果。

        Args:
            reference_symbols: 参考品种列表
            intervals: 扫描周期列表
            force_refresh: 是否强制刷新
            progress_callback: 进度回调

        Returns:
            QualityOverview: 质量概览
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        # 检查配置
        from ..config import config_manager

        enable_adaptive = config_manager.is_quality_scan_adaptive_enabled()
        enable_detailed = config_manager.is_quality_scan_detailed_enabled()
        enable_incremental_push = config_manager.is_quality_scan_incremental_push_enabled()

        if not enable_adaptive:
            # 使用传统扫描模式
            self.logger.info("使用传统扫描模式（自适应已禁用）")
            return self.scan_all_data(
                reference_symbols, intervals, force_refresh, progress_callback
            )

        # 启用自适应模式
        self.logger.info("启用自适应扫描模式")

        try:
            # 计算自适应配置
            from .hybrid_async_engine import AdaptiveQualityConfig

            config = AdaptiveQualityConfig.calculate_optimal_config(
                symbols_count=len(reference_symbols),
                enable_detailed_scan=enable_detailed,
            )

            # 输出配置摘要
            config_summary = AdaptiveQualityConfig.get_config_summary(config)
            self.logger.info("\n" + config_summary)
            print("\n" + config_summary)

            # 阶段0：立即推送基础指标
            self._push_phase_0_metrics(reference_symbols, enable_incremental_push)

            # 阶段1：快速扫描本地数据索引
            local_symbols_data = self._scan_phase_1_local_index(reference_symbols)
            self._push_phase_1_metrics(local_symbols_data, enable_incremental_push)

            # 阶段2：批量检查数据更新状态
            freshness_data = self._scan_phase_2_freshness(
                local_symbols_data["local_symbols"], config, progress_callback
            )
            self._push_phase_2_metrics(freshness_data, enable_incremental_push)

            # 阶段3：详细质量扫描（可选）
            quality_data = {}
            if enable_detailed:
                quality_data = self._scan_phase_3_quality(
                    local_symbols_data["local_symbols"],
                    intervals,
                    config,
                    progress_callback,
                )
                self._push_phase_3_metrics(quality_data, enable_incremental_push)

            # 阶段4：计算最终评分并推送
            overview = self._calculate_and_push_final_score(
                reference_symbols,
                local_symbols_data,
                freshness_data,
                quality_data,
                intervals,
                enable_incremental_push,
            )

            self._quality_overview = overview
            return overview

        except Exception as e:
            self.logger.error("自适应扫描失败，降级到传统模式: %s", e, exc_info=True)
            return self.scan_all_data(
                reference_symbols, intervals, force_refresh, progress_callback
            )

    def _push_phase_0_metrics(
        self, reference_symbols: List[str], enable_push: bool
    ):
        """阶段0：立即推送基础指标"""
        if not enable_push or not self.event_engine:
            return

        from ..events import EVENT_QUALITY_SCAN_PHASE, Event
        from datetime import datetime

        event_data = {
            "phase": 0,
            "metrics": {"total_symbols": len(reference_symbols)},
            "status": "scanning",
            "progress_percent": 0,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(f"📊 推送阶段0指标: 总品种 {len(reference_symbols)}")

    def _scan_phase_1_local_index(self, reference_symbols: List[str]) -> Dict:
        """阶段1：快速扫描本地数据索引"""
        import sys

        print("\n[阶段1/4] 快速扫描本地数据索引")
        sys.stdout.flush()

        local_symbol_codes = self.storage_manager.get_local_data_index()
        downloaded_count = len(local_symbol_codes)
        missing_count = len(reference_symbols) - downloaded_count

        print(f"  ✓ 已下载: {downloaded_count} 个品种")
        print(f"  ✓ 缺失: {missing_count} 个品种")
        sys.stdout.flush()

        return {
            "local_symbols": local_symbol_codes,
            "downloaded_count": downloaded_count,
            "missing_count": missing_count,
        }

    def _push_phase_1_metrics(self, local_data: Dict, enable_push: bool):
        """阶段1：推送本地数据索引指标"""
        if not enable_push or not self.event_engine:
            return

        from ..events import EVENT_QUALITY_SCAN_PHASE, Event
        from datetime import datetime

        event_data = {
            "phase": 1,
            "metrics": {
                "downloaded_symbols": local_data["downloaded_count"],
                "missing_symbols": local_data["missing_count"],
            },
            "status": "checking_freshness",
            "progress_percent": 25,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(
            f"📊 推送阶段1指标: 已下载 {local_data['downloaded_count']}, "
            f"缺失 {local_data['missing_count']}"
        )

    def _scan_phase_2_freshness(
        self, local_symbols: List[str], config: Dict, progress_callback
    ) -> Dict:
        """阶段2：批量检查数据更新状态"""
        import sys

        print("\n[阶段2/4] 检查数据更新状态")
        sys.stdout.flush()

        outdated_symbols = 0
        gap_days_list = []
        batch_size = config.get("batch_size", 500)

        for idx, symbol in enumerate(local_symbols, 1):
            try:
                freshness = self.validator.check_data_freshness(symbol, "1d")
                if freshness["has_data"]:
                    gap_days = freshness["gap_days"]
                    if gap_days > 1:
                        outdated_symbols += 1
                    if gap_days >= 0:
                        gap_days_list.append(gap_days)
            except Exception:
                pass

            # 定期输出进度
            if idx % batch_size == 0 or idx == len(local_symbols):
                percent = int((idx / len(local_symbols)) * 100)
                print(f"  进度: {idx}/{len(local_symbols)} ({percent}%)")
                sys.stdout.flush()
                if progress_callback:
                    progress_callback(25 + percent * 0.25)  # 25%-50%

        avg_gap_days = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0

        print(f"  ✓ 过时品种: {outdated_symbols}")
        print(f"  ✓ 平均滞后: {avg_gap_days} 个交易日")
        sys.stdout.flush()

        return {
            "outdated_symbols": outdated_symbols,
            "avg_gap_days": avg_gap_days,
            "gap_days_list": gap_days_list,
        }

    def _push_phase_2_metrics(self, freshness_data: Dict, enable_push: bool):
        """阶段2：推送数据更新状态指标"""
        if not enable_push or not self.event_engine:
            return

        from ..events import EVENT_QUALITY_SCAN_PHASE, Event
        from datetime import datetime

        event_data = {
            "phase": 2,
            "metrics": {
                "outdated_symbols": freshness_data["outdated_symbols"],
                "avg_gap_days": freshness_data["avg_gap_days"],
            },
            "status": "scanning_quality" if enable_push else "calculating_score",
            "progress_percent": 50,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(
            f"📊 推送阶段2指标: 过时 {freshness_data['outdated_symbols']}, "
            f"平均滞后 {freshness_data['avg_gap_days']} 天"
        )

    def _scan_phase_3_quality(
        self,
        local_symbols: List[str],
        intervals: List[str],
        config: Dict,
        progress_callback,
    ) -> Dict:
        """阶段3：详细质量扫描（错误/警告检查）"""
        import sys
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        print("\n[阶段3/4] 详细质量扫描（错误/警告）")
        sys.stdout.flush()

        max_workers = config.get("max_workers", 10)
        error_symbols = 0
        warning_symbols = 0
        symbol_qualities = []
        lock = threading.Lock()

        def scan_single(symbol):
            try:
                return self._scan_symbol_quality(symbol, intervals)
            except Exception as e:
                self.logger.error("扫描品种 %s 失败: %s", symbol, e)
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_single, s): s for s in local_symbols}

            completed = 0
            for future in as_completed(futures):
                symbol_quality = future.result()
                if symbol_quality:
                    with lock:
                        symbol_qualities.append(symbol_quality)
                        if symbol_quality.has_errors:
                            error_symbols += 1
                        if symbol_quality.has_warnings:
                            warning_symbols += 1

                completed += 1

                # 定期输出进度
                if completed % 500 == 0 or completed == len(local_symbols):
                    percent = int((completed / len(local_symbols)) * 100)
                    print(f"  进度: {completed}/{len(local_symbols)} ({percent}%)")
                    sys.stdout.flush()
                    if progress_callback:
                        progress_callback(50 + percent * 0.4)  # 50%-90%

        print(f"  ✓ 错误品种: {error_symbols}")
        print(f"  ✓ 警告品种: {warning_symbols}")
        sys.stdout.flush()

        return {
            "error_symbols": error_symbols,
            "warning_symbols": warning_symbols,
            "symbol_qualities": symbol_qualities,
        }

    def _push_phase_3_metrics(self, quality_data: Dict, enable_push: bool):
        """阶段3：推送详细质量指标"""
        if not enable_push or not self.event_engine:
            return

        from ..events import EVENT_QUALITY_SCAN_PHASE, Event
        from datetime import datetime

        event_data = {
            "phase": 3,
            "metrics": {
                "error_symbols": quality_data["error_symbols"],
                "warning_symbols": quality_data["warning_symbols"],
            },
            "status": "calculating_score",
            "progress_percent": 90,
            "timestamp": datetime.now().isoformat(),
        }

        event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
        self.event_engine.put(event)
        self.logger.info(
            f"📊 推送阶段3指标: 错误 {quality_data['error_symbols']}, "
            f"警告 {quality_data['warning_symbols']}"
        )

    def _calculate_and_push_final_score(
        self,
        reference_symbols: List[str],
        local_data: Dict,
        freshness_data: Dict,
        quality_data: Dict,
        intervals: List[str],
        enable_push: bool,
    ) -> QualityOverview:
        """阶段4：计算最终评分并推送"""
        import sys

        print("\n[阶段4/4] 计算最终评分")
        sys.stdout.flush()

        total_symbols = len(reference_symbols)
        missing_symbols = local_data["missing_count"]
        outdated_symbols = freshness_data["outdated_symbols"]
        avg_gap_days = freshness_data["avg_gap_days"]

        error_symbols = quality_data.get("error_symbols", 0)
        warning_symbols = quality_data.get("warning_symbols", 0)
        symbol_qualities = quality_data.get("symbol_qualities", [])

        # 计算质量评分
        if total_symbols > 0:
            quality_score = int(
                ((total_symbols - missing_symbols - error_symbols * 2 - warning_symbols * 0.5) / total_symbols) * 100
            )
        else:
            quality_score = 100

        quality_score = max(0, min(100, quality_score))

        print(f"  ✓ 最终评分: {quality_score}")
        sys.stdout.flush()

        # 🆕 计算数据滞后和数据缺失
        print(f"  步骤4.1: 计算数据滞后和数据缺失...")
        sys.stdout.flush()
        local_symbols = local_data.get("local_symbols", [])
        data_lagging_days, data_missing_symbols = self._calculate_lagging_and_missing(
            symbols_with_data=local_symbols,
            reference_symbols=reference_symbols,
            base_date=date.today(),
            interval="1d"
        )
        print(f"  ✓ 数据滞后: {data_lagging_days}天, 数据缺失: {data_missing_symbols}个品种")
        sys.stdout.flush()

        # 构建详情（只包含有问题的品种）
        problem_details = [
            {
                "symbol": sq.symbol,
                "status": self._determine_status(sq),
                "score": sq.overall_score,
                "has_errors": sq.has_errors,
                "has_warnings": sq.has_warnings,
                "is_missing": sq.is_missing,
                "issues": self._collect_issues(sq),
            }
            for sq in symbol_qualities
            if sq.has_errors or sq.has_warnings or sq.is_missing
        ]

        overview = QualityOverview(
            total_symbols=total_symbols,
            missing_symbols=missing_symbols,
            error_symbols=error_symbols,
            warning_symbols=warning_symbols,
            quality_score=quality_score,
            last_scan_time=datetime.now(),
            base_date=date.today(),
            scanned_intervals=list(set(intervals)),
            details=problem_details,
            outdated_symbols=outdated_symbols,
            avg_gap_days=avg_gap_days,
            data_missing_symbols=data_missing_symbols,  # 🆕 添加数据缺失
            data_lagging_days=data_lagging_days,  # 🆕 添加数据滞后
        )

        # 推送最终指标
        if enable_push and self.event_engine:
            from ..events import EVENT_QUALITY_SCAN_PHASE, Event

            event_data = {
                "phase": 4,
                "metrics": {"quality_score": quality_score},
                "status": "complete",
                "progress_percent": 100,
                "timestamp": datetime.now().isoformat(),
            }

            event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
            self.event_engine.put(event)
            self.logger.info(f"📊 推送阶段4指标: 最终评分 {quality_score}")

        # 推送传统的质量更新事件（兼容现有代码）
        if self.event_engine:
            self._send_quality_update_event(overview)

        return overview

    # 🆕 ==================== 混合异步架构扫描 ====================

    def _init_hybrid_async_components(self):
        """延迟初始化混合异步组件"""
        if self._hybrid_async_enabled:
            return
        
        try:
            from .hybrid_async_engine import (
                ResourceMonitor,
                FileMetadataScanner,
                SmartScheduler,
                AsyncIOExecutor,
                CPUIntensiveWorker,
            )
            
            self._resource_monitor = ResourceMonitor()
            self._file_scanner = FileMetadataScanner()
            self._scheduler = SmartScheduler(self._resource_monitor)
            self._async_executor = AsyncIOExecutor(self.storage_manager, self.validator)
            self._cpu_worker = CPUIntensiveWorker(data_dir=str(self.storage_manager.data_dir))
            
            self._hybrid_async_enabled = True
            self.logger.info("✅ 混合异步架构组件已初始化")
        
        except ImportError as e:
            self.logger.warning(f"混合异步组件导入失败，将使用传统扫描: {e}")
            self._hybrid_async_enabled = False

    async def scan_all_data_hybrid_async(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
        progress_callback=None,
    ) -> QualityOverview:
        """混合异步扫描（终极性能版）
        
        四层架构：协程+线程+进程，智能调度，极致性能
        """
        if intervals is None:
            intervals = ["1d", "5m", "1m"]
        
        # 初始化组件
        self._init_hybrid_async_components()
        
        if not self._hybrid_async_enabled:
            # 降级到传统扫描
            self.logger.warning("混合异步架构未启用，降级到传统扫描")
            return self.scan_all_data(reference_symbols, intervals, force_refresh, progress_callback)
        
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime
        import sys
        
        # 启动资源监控
        self._resource_monitor.start_monitoring()
        
        print("\n========== 混合异步数据质量扫描 ==========")
        print(f"品种数量: {len(reference_symbols)}")
        print(f"扫描周期: {', '.join(intervals)}")
        sys.stdout.flush()
        
        # ========== 阶段0：立即推送基础指标 (<1ms) ==========
        self._push_phase_0_metrics(reference_symbols, True)
        if progress_callback:
            progress_callback(0)
        
        # ========== 阶段1：异步扫描文件元数据 (0.5-1秒) ==========
        print("\n[阶段1/4] 异步扫描文件元数据...")
        sys.stdout.flush()
        
        file_metadata = await self._file_scanner.scan_all_files_async(
            self.storage_manager.data_dir,
            max_concurrency=1000
        )
        
        local_symbols = list(set(meta.symbol for meta in file_metadata.values() if meta.has_data and meta.symbol))
        local_symbols.sort()
        
        print(f"  ✓ 已下载: {len(local_symbols)} 个品种")
        print(f"  ✓ 缺失: {len(reference_symbols) - len(local_symbols)} 个品种")
        sys.stdout.flush()
        
        self._push_phase_1_metrics(
            {"local_symbols": local_symbols, "downloaded_count": len(local_symbols), "missing_count": len(reference_symbols) - len(local_symbols)},
            True
        )
        if progress_callback:
            progress_callback(25)
        
        # ========== 阶段2：异步批量检查更新状态 (1-2秒) ==========
        print("\n[阶段2/4] 异步批量检查更新状态...")
        sys.stdout.flush()
        
        freshness_results = await self._async_executor.batch_check_freshness_async(
            local_symbols, interval="1d", max_concurrency=500
        )
        
        outdated = sum(1 for r in freshness_results if r.get("gap_days", -1) > 1)
        gap_days_list = [r.get("gap_days", -1) for r in freshness_results if r.get("gap_days", -1) >= 0]
        avg_gap = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0
        
        print(f"  ✓ 过时品种: {outdated}")
        print(f"  ✓ 平均滞后: {avg_gap} 个交易日")
        sys.stdout.flush()
        
        self._push_phase_2_metrics(
            {"outdated_symbols": outdated, "avg_gap_days": avg_gap, "gap_days_list": gap_days_list},
            True
        )
        if progress_callback:
            progress_callback(50)
        
        # ========== 阶段3：混合并行质量扫描 (5-10秒) ==========
        print("\n[阶段3/4] 混合并行质量扫描...")
        sys.stdout.flush()
        
        # 创建任务
        validation_tasks = self._scheduler.create_validation_tasks(local_symbols, intervals, file_metadata)
        
        # 智能调度
        scheduled = self._scheduler.schedule_tasks(validation_tasks)
        
        print(f"  任务调度: 协程{len(scheduled['async'])}个, "
              f"线程{len(scheduled['thread'])}个, 进程{len(scheduled['process'])}个")
        sys.stdout.flush()
        
        # 三层并行执行
        async_results, thread_results, process_results = await asyncio.gather(
            self._execute_async_tasks(scheduled["async"]),
            self._execute_thread_tasks(scheduled["thread"]),
            self._execute_process_tasks(scheduled["process"])
        )
        
        # 聚合结果
        all_results = []
        for results in [async_results, thread_results, process_results]:
            if results:
                all_results.extend([r for r in results if r is not None])
        
        error_count = sum(1 for r in all_results if r.get("has_errors", False))
        warning_count = sum(1 for r in all_results if r.get("has_warnings", False))
        
        print(f"  ✓ 错误品种: {error_count}")
        print(f"  ✓ 警告品种: {warning_count}")
        sys.stdout.flush()
        
        self._push_phase_3_metrics(
            {"error_symbols": error_count, "warning_symbols": warning_count, "symbol_qualities": []},
            True
        )
        if progress_callback:
            progress_callback(90)
        
        # ========== 阶段4：计算最终评分和数据缺失 ==========
        print("\n[阶段4/4] 计算最终评分和数据缺失...")
        sys.stdout.flush()
        
        total_symbols = len(reference_symbols)
        missing_symbols = len(reference_symbols) - len(local_symbols)
        
        # 🆕 计算数据滞后和数据缺失
        print(f"  步骤4.1: 计算数据滞后和数据缺失...")
        sys.stdout.flush()
        data_lagging_days, data_missing_symbols = self._calculate_lagging_and_missing(
            symbols_with_data=local_symbols,
            reference_symbols=reference_symbols,
            base_date=date.today(),
            interval="1d"
        )
        print(f"  ✓ 数据滞后: {data_lagging_days}天, 数据缺失: {data_missing_symbols}个品种")
        sys.stdout.flush()
        
        # 🆕 构建问题品种详情
        print(f"  步骤4.2: 构建问题品种详情...")
        sys.stdout.flush()
        problem_details = []
        for result in all_results:
            if result.get("has_errors") or result.get("has_warnings") or result.get("is_missing"):
                symbol = result.get("symbol", "")
                status = "missing" if result.get("is_missing") else ("error" if result.get("has_errors") else "warning")
                problem_details.append({
                    "symbol": symbol,
                    "status": status,
                    "score": result.get("overall_score", 0),
                    "has_errors": result.get("has_errors", False),
                    "has_warnings": result.get("has_warnings", False),
                    "is_missing": result.get("is_missing", False),
                    "issues": result.get("issues", ""),
                })
        
        # 按问题严重程度排序
        problem_details.sort(
            key=lambda d: {"missing": 1, "error": 2, "warning": 3}.get(d["status"], 4)
        )
        print(f"  ✓ 问题品种: {len(problem_details)}个")
        sys.stdout.flush()
        
        # 计算质量评分
        quality_score = int(
            ((total_symbols - missing_symbols - error_count * 2 - warning_count * 0.5) / total_symbols) * 100
        ) if total_symbols > 0 else 100
        quality_score = max(0, min(100, quality_score))
        
        print(f"  ✓ 最终评分: {quality_score}")
        sys.stdout.flush()
        
        overview = QualityOverview(
            total_symbols=total_symbols,
            missing_symbols=missing_symbols,
            error_symbols=error_count,
            warning_symbols=warning_count,
            quality_score=quality_score,
            last_scan_time=datetime.now(),
            base_date=date.today(),
            scanned_intervals=list(set(intervals)),
            details=problem_details,  # 🔧 修复：使用实际的问题品种详情
            outdated_symbols=outdated,
            avg_gap_days=avg_gap,
            data_missing_symbols=data_missing_symbols,  # 🆕 添加数据缺失
            data_lagging_days=data_lagging_days,  # 🆕 添加数据滞后
        )
        
        self._quality_overview = overview
        
        # 推送最终指标
        from ..events import EVENT_QUALITY_SCAN_PHASE, Event
        if self.event_engine:
            event_data = {
                "phase": 4,
                "metrics": {"quality_score": quality_score},
                "status": "complete",
                "progress_percent": 100,
                "timestamp": datetime.now().isoformat(),
            }
            event = Event(EVENT_QUALITY_SCAN_PHASE, event_data)
            self.event_engine.put(event)
        
        if progress_callback:
            progress_callback(100)
        
        # 推送传统事件（兼容）
        if self.event_engine:
            self._send_quality_update_event(overview)
        
        # 停止资源监控
        self._resource_monitor.stop_monitoring()
        
        print("\n========== 扫描完成 ==========\n")
        sys.stdout.flush()
        
        return overview

    async def _execute_async_tasks(self, tasks: List) -> List:
        """执行协程层任务（1000+并发）"""
        if not tasks:
            return []
        
        try:
            results = []
            for task in tasks:
                result = await self._async_executor.process_task_async(task)
                if result:
                    results.append(result)
            return results
        except Exception as e:
            self.logger.error(f"协程层执行失败: {e}", exc_info=True)
            return []

    async def _execute_thread_tasks(self, tasks: List) -> List:
        """执行线程层任务（20-50并发）"""
        if not tasks:
            return []
        
        try:
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            loop = asyncio.get_event_loop()
            
            def process_in_thread(task):
                try:
                    return self._async_executor._validate_symbol_sync(task.symbol, task.interval)
                except Exception as e:
                    self.logger.debug(f"线程任务失败 {task.symbol}: {e}")
                    return None
            
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [loop.run_in_executor(executor, process_in_thread, t) for t in tasks]
                results = await asyncio.gather(*futures, return_exceptions=True)
                return [r for r in results if r is not None and not isinstance(r, Exception)]
        
        except Exception as e:
            self.logger.error(f"线程层执行失败: {e}", exc_info=True)
            return []

    async def _execute_process_tasks(self, tasks: List) -> List:
        """执行进程层任务（4-8并发）"""
        if not tasks:
            return []
        
        try:
            import asyncio
            
            # 提取品种和周期
            symbols = list(set(t.symbol for t in tasks))
            intervals = list(set(t.interval for t in tasks))
            
            # 在executor中执行进程池任务
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                self._cpu_worker.validate_data_parallel,
                symbols,
                intervals
            )
            return results
        
        except Exception as e:
            self.logger.error(f"进程层执行失败: {e}", exc_info=True)
            return []

    def scan_all_data_hybrid_sync(self, *args, **kwargs) -> QualityOverview:
        """同步包装器（向后兼容）"""
        import asyncio
        return asyncio.run(self.scan_all_data_hybrid_async(*args, **kwargs))


# ==================== 文件监控器 ====================


class DataFileWatcher:
    """数据文件监控器"""

    def __init__(self, data_dir: Path, callback=None):
        self.data_dir = data_dir
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        self._observer = None
        self._handler = None
        self._running = False

        try:
            from watchdog.observers import Observer  # type: ignore
            from watchdog.events import FileSystemEventHandler  # type: ignore

            self.Observer = Observer
            self.FileSystemEventHandler = FileSystemEventHandler  # type: ignore
            self.watchdog_available = True

        except ImportError:
            self.watchdog_available = False

    def start(self) -> bool:
        """
        启动监控

        Returns:
            bool: 启动成功返回 True；watchdog 不可用或启动失败返回 False
        """
        if not self.watchdog_available:
            self.logger.warning("watchdog不可用，文件监控功能将被禁用")
            return False

        if self._running:
            self.logger.warning("文件监控已在运行")
            return True

        try:
            self._observer = self.Observer()
            self._handler = DataFileEventHandler(self.callback)

            # 监控数据目录及其子目录
            self._observer.schedule(self._handler, str(self.data_dir), recursive=True)  # type: ignore
            self._observer.start()

            self._running = True
            self.logger.info("文件监控已启动: %s", self.data_dir)
            return True

        except Exception as e:
            self.logger.error("启动文件监控失败: %s", e)
            return False

    def stop(self):
        """
        停止监控

        Returns:
            None
        """
        if not self._running:
            return

        try:
            if self._observer:
                self._observer.stop()
                self._observer.join(timeout=5)

            self._running = False
            self.logger.info("文件监控已停止")

        except Exception as e:
            self.logger.error("停止文件监控失败: %s", e)

    def is_running(self) -> bool:
        """检查是否在运行"""
        return self._running


# 兼容 watchdog 不可用场景
try:
    from watchdog.events import FileSystemEventHandler as _FSHandler  # type: ignore

    _WATCHDOG_AVAILABLE = True
except Exception:  # pragma: no cover
    _WATCHDOG_AVAILABLE = False

    # 提供一个空基类
    class _FSHandler:  # type: ignore
        def dispatch(self, event):  # type: ignore
            """空实现"""
            pass


class DataFileEventHandler(_FSHandler):
    """数据文件事件处理器（继承FileSystemEventHandler，提供安全dispatch和增强防抖）"""

    def __init__(self, callback, debounce_seconds: float = 5.0):
        if _WATCHDOG_AVAILABLE:
            super().__init__()
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        # 增强的防抖机制（线程延迟方案）
        self.debounce_seconds = debounce_seconds
        self.pending_event = ThreadEvent()
        self.last_event_time = 0.0
        self._debounce_thread: Optional[Thread] = None

    # 核心：提供安全的 dispatch，避免异常导致观察线程崩溃
    def dispatch(self, event):  # type: ignore[override]
        try:
            # 仅委托父类分发；父类会按事件类型调用 on_created/on_modified 等
            if _WATCHDOG_AVAILABLE:
                return super().dispatch(event)
        except Exception as e:  # 防御性：不让线程崩溃
            try:
                ev_path = getattr(event, "src_path", None) or getattr(event, "dest_path", None)
            except Exception:
                ev_path = None
            self.logger.error("watchdog 事件分发失败: %s, event=%s", e, ev_path)

    def on_modified(self, event):
        """文件修改事件"""
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "modified")

    def on_created(self, event):
        """文件创建事件"""
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "created")

    # 可选：移动/删除事件（不触发重算，但保留记录）
    def on_moved(self, event):  # noqa: D401
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "dest_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "moved")

    def on_deleted(self, event):  # noqa: D401
        if getattr(event, "is_directory", False):
            return
        path = getattr(event, "src_path", None)
        if path and self._is_data_file(path):
            self._handle_file_change(path, "deleted")

    def _is_data_file(self, file_path: str) -> bool:
        """检查是否为数据文件"""
        path = Path(file_path)
        return path.suffix == ".parquet" and "data" in path.name

    def _handle_file_change(self, file_path: str, event_type: str):
        """处理文件变化（带线程延迟防抖）"""
        current_time = time.time()

        # 如果距离上次事件时间太短，取消之前的延迟任务
        if current_time - self.last_event_time < self.debounce_seconds:
            self.pending_event.set()  # 取消之前的任务

        self.last_event_time = current_time
        self.pending_event.clear()

        # 启动延迟任务
        self._debounce_thread = Thread(
            target=self._delayed_callback, args=(file_path, event_type), daemon=True
        )
        self._debounce_thread.start()

    def _delayed_callback(self, file_path: str, event_type: str):
        """延迟回调执行"""
        if self.pending_event.wait(self.debounce_seconds):
            # 事件被取消
            self.logger.debug("防抖取消事件: %s %s", file_path, event_type)
            return

        # 执行回调
        if self.callback:
            try:
                self.callback(event_type, str(Path(file_path)))
            except Exception as e:
                self.logger.error("文件变化回调失败: %s", e, exc_info=True)


# ==================== 系统健康检查 ====================


class HealthChecker:
    """系统健康检查器

    验证关键目录与最小数据可用性
    """

    @staticmethod
    def check_system_health() -> Dict[str, Any]:
        """
        健康检查：验证关键目录与最小数据可用性

        Returns:
            {"ready": bool, "message": str, "details": {...}}
        """
        details: Dict[str, Any] = {}
        ready = True
        message = "OK"
        logger = logging.getLogger(__name__)

        try:
            cache_dir = config_manager.get_cache_dir()
            data_dir = config_manager.get_data_dir()
            details["cache_dir"] = str(cache_dir)
            details["data_dir"] = str(data_dir)

            # 目录存在性与可写性
            cache_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            details["cache_dir_exists"] = cache_dir.exists()
            details["data_dir_exists"] = data_dir.exists()

            # 尝试写入/读取探针文件（权限检测）
            probe = cache_dir / ".probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                details["cache_dir_writable"] = True
                with probe.open("r", encoding="utf-8") as f:
                    _ = f.read()
                probe.unlink(missing_ok=True)
            except Exception:
                details["cache_dir_writable"] = False
                ready = False
                message = "cache_dir 不可写"

            # 最小数据可用性（非强制）
            parquet_count = 0
            try:
                for root, _, files in os.walk(data_dir):
                    for fn in files:
                        if fn.lower().endswith(".parquet"):
                            parquet_count += 1
                            if parquet_count >= 1:
                                break
                    if parquet_count >= 1:
                        break
            except Exception:
                pass
            details["parquet_files"] = parquet_count

            if parquet_count == 0 and ready:
                message = "未检测到最小数据集（可后续通过增量下载或导入TDX生成）"

        except Exception as e:
            ready = False
            message = f"健康检查异常: {e}"
            logger.error("健康检查异常: %s", e, exc_info=True)

        return {"ready": bool(ready), "message": message, "details": details}


# ==================== 全局实例 ====================

# 全局数据质量管理器
storage_manager = StorageManager()
data_validator = DataValidator()
data_sensor = DataSensor()
data_file_watcher = DataFileWatcher(config_manager.get_data_dir())

# ==================== 向后兼容别名 ====================

# 为保持向后兼容，提供别名（file_watcher.py 已合并至此）
KlineFileWatcher = DataFileWatcher
KlineFileHandler = DataFileEventHandler

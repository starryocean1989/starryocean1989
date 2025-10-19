# -*- coding: utf-8 -*-
"""
数据质量管理模块

负责数据存储、校验、感知和文件监控，包括：
- 数据存储管理（Parquet格式）
- 数据校验和感知
- 文件监控和变化检测
- 数据质量概览和报告

合并来源：storage.py + validator.py + data_sensor.py + file_watcher.py
"""

# ==================== 导入声明 ====================
import logging
import json
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import asyncio

import pandas as pd

from ..config import config_manager

# ==================== IPO日期缓存管理 ====================


class IPODateCache:
    """IPO日期持久化缓存管理器

    实现两级缓存架构：
    - L1: 内存字典（进程运行期间有效）
    - L2: JSON文件（永久存储）
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
        """从JSON文件加载缓存"""
        try:
            if not self.cache_file.exists():
                self.logger.info("IPO缓存文件不存在，将创建新缓存")
                return

            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 解析缓存数据
            cache_data = data.get("data", {})
            for symbol, info in cache_data.items():
                ipo_date_str = info.get("ipo_date")
                if ipo_date_str:
                    try:
                        self._memory_cache[symbol] = datetime.strptime(
                            ipo_date_str, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        self.logger.warning("无效的IPO日期格式: %s -> %s", symbol, ipo_date_str)
                else:
                    # 缓存了None值（表示查询失败）
                    self._memory_cache[symbol] = None

            self.logger.info("✓ IPO缓存加载完成: %d条记录", len(self._memory_cache))

        except json.JSONDecodeError as e:
            self.logger.error("IPO缓存文件损坏: %s, 将重建缓存", e)
            self._memory_cache.clear()
        except Exception as e:
            self.logger.error("加载IPO缓存失败: %s", e)

    def _save_to_file(self) -> None:
        """保存缓存到JSON文件"""
        try:
            # 构建JSON数据结构
            cache_data = {}
            for symbol, ipo_date in self._memory_cache.items():
                cache_data[symbol] = {
                    "ipo_date": ipo_date.strftime("%Y-%m-%d") if ipo_date else None,
                    "update_time": datetime.now().strftime("%Y-%m-%d"),
                    "source": "tdx_api",
                }

            data = {
                "version": "1.0",
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": cache_data,
            }

            # 写入文件（原子操作）
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            temp_file.replace(self.cache_file)
            self.logger.debug("IPO缓存已保存: %d条记录", len(cache_data))

        except Exception as e:
            self.logger.error("保存IPO缓存失败: %s", e)

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

            if save_immediately:
                self._save_to_file()

    def batch_save(self) -> None:
        """批量保存缓存到文件"""
        with self._lock:
            self._save_to_file()

    def get_stats(self) -> Dict[str, int]:
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

        扫描data/kline目录，返回所有至少有一个周期有效数据的品种代码。

        注意：不仅检查文件是否存在，还要确保文件有有效记录（与数据质量概览一致）

        Returns:
            List[str]: 品种代码列表（按代码排序）
        """
        try:
            symbol_codes = []

            # 扫描数据目录
            for symbol_dir in self.data_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue

                symbol_code = symbol_dir.name

                # 检查是否有任何周期的有效数据（文件存在且有记录）
                has_data = False
                for interval_dir in symbol_dir.iterdir():
                    if interval_dir.is_dir():
                        data_file = interval_dir / "data.parquet"
                        if data_file.exists():
                            # 🔧 改进：检查文件是否有有效数据，而不仅仅是文件存在
                            try:
                                import pandas as pd

                                df = pd.read_parquet(data_file)
                                if df is not None and not df.empty:
                                    has_data = True
                                    break
                            except Exception:
                                # 文件损坏或无法读取，跳过
                                continue

                if has_data:
                    symbol_codes.append(symbol_code)

            # 按代码排序
            symbol_codes.sort()

            self.logger.info("扫描本地数据索引完成，共 %d 个品种有有效数据", len(symbol_codes))
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
            self.logger.warning(
                f"品种 {symbol} IPO日期未缓存，建议先调用 preload_ipo_dates_batch()"
            )
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
                self.logger.warning("交易日历获取失败，跳过缺失日期检测")
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
                        self.logger.warning("交易日范围为空: %s 至 %s", start_date, end_date)
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
    missing_symbols: int
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

    def scan_all_data(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
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
                        if completed % 500 == 0:
                            self.logger.info("扫描进度: %d/%d", completed, len(symbols_with_data))

            # 🆕 批量检测数据更新状态（仅检测1d周期，避免重复）
            self.logger.info("开始检测数据更新状态...")
            for symbol in symbols_with_data:
                try:
                    freshness = self.validator.check_data_freshness(symbol, "1d")
                    if freshness["has_data"]:
                        gap_days = freshness["gap_days"]
                        if gap_days > 1:  # 滞后超过1个交易日则算过时
                            outdated_symbols += 1
                        if gap_days >= 0:  # -1表示无数据，不计入平均值
                            gap_days_list.append(gap_days)
                except Exception as e:
                    self.logger.debug("检测品种 %s 数据更新状态失败: %s", symbol, e)

            # 计算数据更新状态指标
            avg_gap_days = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0
            max_gap_days = max(gap_days_list) if gap_days_list else 0

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
    ) -> QualityOverview:
        """
        触发数据质量扫描（自动获取品种列表，从core.py迁移）

        Args:
            symbol_loader: SymbolLoader实例（用于获取品种列表）
            intervals: 扫描周期列表（可选，默认 ["1d", "5m", "1m"]）
            force_refresh: 是否强制刷新（忽略缓存）

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
                },
                "timestamp": datetime.now(),
            }

            event = Event("eDataQualityUpdate", event_data)
            self.event_engine.put(event)

        except Exception as e:
            self.logger.error("发送质量更新事件失败: %s", e)

    def on_file_changed(self, file_path: Path) -> None:
        """
        文件变化回调方法

        当数据文件发生变化时，清除质量概览缓存以便下次重新计算

        Args:
            file_path: 发生变化的文件路径
        """
        try:
            self.logger.info("检测到数据文件变化: %s", file_path)
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
    """数据文件事件处理器（继承FileSystemEventHandler，提供安全dispatch）"""

    def __init__(self, callback):
        if _WATCHDOG_AVAILABLE:
            super().__init__()
        self.callback = callback
        self.logger = logging.getLogger(__name__)

        # 防抖动：记录最近处理的文件和时间
        self.recent_files: Dict[str, Tuple[datetime, str]] = {}
        self.debounce_seconds = 2

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
        """处理文件变化"""
        now = datetime.now()

        # 防抖动：忽略短时间内重复的事件
        if file_path in self.recent_files:
            last_time, last_type = self.recent_files[file_path]
            if (now - last_time).seconds < self.debounce_seconds and event_type == last_type:
                self.logger.debug("忽略重复的文件事件: %s %s", file_path, event_type)
                return

        # 更新最近处理记录
        self.recent_files[file_path] = (now, event_type)

        # 调用回调函数
        if self.callback:
            try:
                self.callback(Path(file_path))
            except Exception as e:
                self.logger.error("文件变化回调失败: %s", e)


# ==================== 全局实例 ====================

# 全局数据质量管理器
storage_manager = StorageManager()
data_validator = DataValidator()
data_sensor = DataSensor()
data_file_watcher = DataFileWatcher(config_manager.get_data_dir())

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
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from .config import config_manager

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

            # 使用zstd压缩保存
            dataframe.to_parquet(file_path, compression="zstd", index=False)

            self.logger.info("保存K线数据成功: %s %s, %d条记录", symbol, interval, len(dataframe))
            return file_path

        except Exception as e:
            self.logger.error("保存K线数据失败: %s %s, %s", symbol, interval, e)
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
                self.logger.warning("数据文件不存在: %s", file_path)
                return None

            # 读取数据
            df = pd.read_parquet(file_path)

            if df.empty:
                return df

            # 过滤日期
            if start_date is not None:
                if isinstance(start_date, str):
                    start_date = pd.to_datetime(start_date).date()
                df = df[df.index >= pd.Timestamp(start_date)]

            if end_date is not None:
                if isinstance(end_date, str):
                    end_date = pd.to_datetime(end_date).date()
                df = df[df.index <= pd.Timestamp(end_date)]

            self.logger.info("查询数据成功: %s %s, %d条记录", symbol, interval, len(df))
            return df

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", symbol, interval, e)
            return None

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
            date_range = (None, None)
            try:
                if not df.empty and pd.api.types.is_datetime64_any_dtype(df.index):
                    date_range = (df.index.min().date(), df.index.max().date())
                elif not df.empty and "datetime" in df.columns:
                    # 如果索引不是datetime类型，尝试使用datetime列
                    if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                        date_range = (df["datetime"].min().date(), df["datetime"].max().date())
                    else:
                        # 尝试转换datetime列
                        datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                        if not datetime_series.isna().all():
                            date_range = (
                                datetime_series.min().date(),
                                datetime_series.max().date(),
                            )
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
                missing_dates=self._check_missing_dates(df),
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
                elif df[col].isna().any():
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

    def _check_missing_dates(self, df: pd.DataFrame) -> List[date]:
        """检查缺失日期"""
        if df.empty or "datetime" not in df.columns:
            return []

        try:
            # 确保使用datetime列作为日期源
            if not pd.api.types.is_datetime64_any_dtype(df.index):
                # 如果索引不是datetime类型，使用datetime列
                if pd.api.types.is_datetime64_any_dtype(df["datetime"]):
                    date_series = df["datetime"]
                else:
                    # 尝试转换datetime列
                    date_series = pd.to_datetime(df["datetime"], errors="coerce")
            else:
                # 索引是datetime类型
                date_series = df.index

            # 移除无效日期
            date_series = date_series.dropna()

            if date_series.empty:
                return []

            # 获取日期范围
            min_date = date_series.min()
            max_date = date_series.max()

            # 确保是datetime类型，然后转换为date
            if pd.api.types.is_datetime64_any_dtype(date_series):
                start_date = min_date.date()
                end_date = max_date.date()
            else:
                # 如果不是datetime类型，尝试转换
                try:
                    start_date = pd.to_datetime(min_date).date()
                    end_date = pd.to_datetime(max_date).date()
                except (ValueError, TypeError):
                    return []

            # 生成完整日期范围
            expected_dates = pd.date_range(start=start_date, end=end_date, freq="D")

            # 找出缺失的日期
            try:
                if pd.api.types.is_datetime64_any_dtype(date_series):
                    actual_dates = set(date_series.dt.date)
                else:
                    actual_dates = set(
                        pd.to_datetime(date_series, errors="coerce").dt.date.dropna()
                    )
            except (AttributeError, TypeError):
                return []

            expected_date_set = set(expected_dates.date)

            missing_dates = list(expected_date_set - actual_dates)
            missing_dates.sort()

            return missing_dates

        except Exception as e:
            self.logger.error("检查缺失日期失败: %s", e)
            return []

    def _check_logic_errors(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """检查逻辑错误"""
        errors = []

        try:
            if "high" in df.columns and "low" in df.columns:
                invalid_high_low = df[df["high"] < df["low"]]
                for idx, row in invalid_high_low.iterrows():
                    errors.append(
                        {
                            "type": "high_low_error",
                            "date": idx.date(),
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
                    non_numeric = df[pd.to_numeric(df[col], errors="coerce").isna()]
                    for idx, row in non_numeric.iterrows():
                        errors.append(
                            {
                                "type": "format_error",
                                "column": col,
                                "date": idx.date(),
                                "value": row[col],
                            }
                        )

        except Exception as e:
            self.logger.error("检查格式错误失败: %s", e)

        return errors


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

    def scan_all_data(
        self,
        reference_symbols: List[str],
        intervals: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> QualityOverview:
        """扫描所有数据质量"""
        if intervals is None:
            intervals = ["1d", "5m", "1m"]

        if not force_refresh and self._quality_overview is not None:
            return self._quality_overview

        try:
            self.logger.info("开始全量数据质量扫描...")

            total_symbols = len(reference_symbols)
            missing_symbols = 0
            error_symbols = 0
            warning_symbols = 0

            symbol_qualities = []
            scanned_intervals = []

            for symbol in reference_symbols:
                symbol_quality = self._scan_symbol_quality(symbol, intervals)
                symbol_qualities.append(symbol_quality)

                if symbol_quality.is_missing:
                    missing_symbols += 1
                if symbol_quality.has_errors:
                    error_symbols += 1
                if symbol_quality.has_warnings:
                    warning_symbols += 1

                scanned_intervals.extend(intervals)

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

            overview = QualityOverview(
                total_symbols=total_symbols,
                missing_symbols=missing_symbols,
                error_symbols=error_symbols,
                warning_symbols=warning_symbols,
                quality_score=quality_score,
                last_scan_time=datetime.now(),
                base_date=date.today(),
                scanned_intervals=list(set(scanned_intervals)),
                details=[
                    {
                        "symbol": sq.symbol,
                        "overall_score": sq.overall_score,
                        "has_errors": sq.has_errors,
                        "has_warnings": sq.has_warnings,
                        "is_missing": sq.is_missing,
                    }
                    for sq in symbol_qualities
                ],
            )

            self._quality_overview = overview

            # 发送事件
            if self.event_engine:
                self._send_quality_update_event(overview)

            self.logger.info(
                "数据质量扫描完成: 评分=%d, 总计=%d, 缺失=%d, 错误=%d, 警告=%d",
                quality_score,
                total_symbols,
                missing_symbols,
                error_symbols,
                warning_symbols,
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
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            self.Observer = Observer
            self.FileSystemEventHandler = FileSystemEventHandler
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
            self._observer.schedule(self._handler, str(self.data_dir), recursive=True)
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
    from watchdog.events import FileSystemEventHandler as _FSHandler
except Exception:  # pragma: no cover
    class _FSHandler:  # type: ignore
        pass


class DataFileEventHandler(_FSHandler):
    """数据文件事件处理器（继承FileSystemEventHandler，提供安全dispatch）"""

    def __init__(self, callback):
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

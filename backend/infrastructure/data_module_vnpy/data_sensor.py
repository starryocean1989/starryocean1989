# -*- coding: utf-8 -*-
"""
数据感知模块

负责自动感知本地数据质量，包括：
- 启动时全量扫描所有品种（日线/5min/1min）
- 文件变化时增量更新
- 缓存扫描结果，避免重复检查
- 通过vnpy事件引擎推送质量更新
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from pathlib import Path

from vnpy.event import EventEngine, Event

from .config import config_manager
from .storage import StorageManager
from .validator import DataValidator, ValidationResult


# vnpy事件类型常量
EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"  # 数据质量更新事件
EVENT_DATA_SCAN_COMPLETE = "eDataScanComplete"  # 扫描完成事件
EVENT_DATA_FILE_CHANGED = "eDataFileChanged"  # 文件变化事件


@dataclass
class QualityOverview:
    """数据质量概览"""

    total_symbols: int
    missing_symbols: int  # 缺失品种数（品种列表中有但数据不存在）
    error_symbols: int  # 有错误的品种数
    warning_symbols: int  # 有警告的品种数
    quality_score: int  # 整体质量评分（0-100）
    last_scan_time: datetime
    base_date: date
    scanned_intervals: List[str]  # 已扫描的周期列表
    details: List[Dict[str, Any]]  # 详细列表（可选）


@dataclass
class SymbolQuality:
    """单个品种的质量信息"""

    symbol: str
    intervals: Dict[str, ValidationResult]  # 各周期的验证结果
    overall_score: int  # 综合质量评分
    has_errors: bool
    has_warnings: bool
    is_missing: bool  # 是否完全缺失


class DataSensor:
    """数据感知器

    负责扫描和监控数据质量，提供自动感知功能。
    """

    def __init__(self, event_engine: Optional[EventEngine] = None):
        """初始化数据感知器

        Args:
            event_engine: vnpy事件引擎（用于推送质量更新事件）
        """
        self.logger = logging.getLogger(__name__)
        self.event_engine = event_engine

        # 组件
        self.storage_manager = StorageManager()
        self.validator = DataValidator()

        # 质量缓存
        self.quality_cache: Dict[str, SymbolQuality] = {}
        self.quality_overview: Optional[QualityOverview] = None
        self.last_scan_time: Optional[datetime] = None

        # 参考品种列表（用于检测缺失品种）
        self.reference_symbols: List[str] = []

        # 扫描配置
        self.scan_intervals = ["1d", "5min", "1min"]  # 要扫描的周期

        # 扫描状态
        self.is_scanning = False
        self.scan_lock = threading.Lock()

        self.logger.info("数据感知器已初始化")

    def scan_all_data(
        self,
        reference_symbols: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> QualityOverview:
        """全量扫描所有品种的数据质量

        Args:
            reference_symbols: 参考品种列表（用于检测缺失）
            force_refresh: 是否强制刷新（忽略缓存）

        Returns:
            质量概览
        """
        with self.scan_lock:
            if self.is_scanning:
                self.logger.warning("扫描正在进行中，跳过重复扫描")
                return self.quality_overview or self._create_empty_overview()

            self.is_scanning = True

        try:
            self.logger.info("=" * 60)
            self.logger.info("开始全量扫描数据质量...")
            self.logger.info("=" * 60)

            # 更新参考品种列表
            if reference_symbols:
                self.reference_symbols = reference_symbols
                self.logger.info("参考品种数: %s", len(self.reference_symbols))

            # 获取本地存在的品种
            existing_symbols = self.storage_manager.list_symbols()
            self.logger.info("本地品种数: %s", len(existing_symbols))

            # 检测缺失品种
            missing_symbols = self._detect_missing_symbols(self.reference_symbols, existing_symbols)
            self.logger.info("缺失品种数: %s", len(missing_symbols))

            # 扫描所有存在的品种
            quality_results: Dict[str, SymbolQuality] = {}
            for symbol in existing_symbols:
                symbol_quality = self.scan_symbol(symbol, force_refresh)
                if symbol_quality:
                    quality_results[symbol] = symbol_quality

            # 缓存结果
            self.quality_cache = quality_results

            # 生成质量概览
            overview = self._generate_overview(quality_results, missing_symbols)
            self.quality_overview = overview
            self.last_scan_time = datetime.now()

            self.logger.info("=" * 60)
            self.logger.info("扫描完成!")
            self.logger.info(
                "总品种: %s, 缺失: %s, 错误: %s, 警告: %s, 评分: %s",
                overview.total_symbols,
                overview.missing_symbols,
                overview.error_symbols,
                overview.warning_symbols,
                overview.quality_score,
            )
            self.logger.info("=" * 60)

            # 发送扫描完成事件
            self._emit_scan_complete_event(overview)

            return overview

        except Exception as e:
            self.logger.error("全量扫描失败: %s", e, exc_info=True)
            return self._create_empty_overview()

        finally:
            self.is_scanning = False

    def scan_symbol(self, symbol: str, force_refresh: bool = False) -> Optional[SymbolQuality]:
        """扫描单个品种的数据质量

        Args:
            symbol: 品种代码
            force_refresh: 是否强制刷新

        Returns:
            品种质量信息
        """
        try:
            # 检查缓存
            if not force_refresh and symbol in self.quality_cache:
                cached_quality = self.quality_cache[symbol]
                # 如果缓存时间小于1小时，直接返回
                if self.last_scan_time and (datetime.now() - self.last_scan_time).seconds < 3600:
                    return cached_quality

            # 扫描各个周期
            interval_results: Dict[str, ValidationResult] = {}
            available_intervals = self.storage_manager.list_intervals(symbol)

            for interval in self.scan_intervals:
                if interval in available_intervals:
                    result = self.validator.validate_symbol(symbol, interval)
                    if result:
                        interval_results[interval] = result

            # 如果没有任何数据，标记为缺失
            if not interval_results:
                return SymbolQuality(
                    symbol=symbol,
                    intervals={},
                    overall_score=0,
                    has_errors=False,
                    has_warnings=False,
                    is_missing=True,
                )

            # 计算综合质量评分
            overall_score = self._calculate_overall_score(interval_results)
            has_errors = any(not r.is_valid for r in interval_results.values())
            has_warnings = any(len(r.warnings) > 0 for r in interval_results.values())

            symbol_quality = SymbolQuality(
                symbol=symbol,
                intervals=interval_results,
                overall_score=overall_score,
                has_errors=has_errors,
                has_warnings=has_warnings,
                is_missing=False,
            )

            # 更新缓存
            self.quality_cache[symbol] = symbol_quality

            return symbol_quality

        except Exception as e:
            self.logger.error("扫描品种 %s 失败: %s", symbol, e)
            return None

    def get_quality_overview(self) -> Optional[QualityOverview]:
        """获取质量概览

        Returns:
            质量概览（如果尚未扫描则返回None）
        """
        return self.quality_overview

    def get_symbol_quality(self, symbol: str) -> Optional[SymbolQuality]:
        """获取单个品种的质量信息

        Args:
            symbol: 品种代码

        Returns:
            品种质量信息
        """
        return self.quality_cache.get(symbol)

    def detect_missing_symbols(self) -> List[str]:
        """检测缺失的品种列表

        Returns:
            缺失的品种代码列表
        """
        existing_symbols = set(self.storage_manager.list_symbols())
        return self._detect_missing_symbols(self.reference_symbols, list(existing_symbols))

    def update_reference_symbols(self, symbols: List[str]) -> None:
        """更新参考品种列表

        Args:
            symbols: 新的参考品种列表
        """
        self.reference_symbols = symbols
        self.logger.info("参考品种列表已更新: %s 个品种", len(symbols))

    def on_file_changed(self, file_path: Path) -> None:
        """文件变化回调

        当监控到数据文件变化时调用，触发增量扫描。

        Args:
            file_path: 变化的文件路径
        """
        try:
            # 解析文件路径获取品种和周期
            # 路径格式：data/kline/{symbol}/{interval}/data.parquet
            parts = file_path.parts
            if len(parts) >= 3 and parts[-1] == "data.parquet":
                symbol = parts[-3]
                interval = parts[-2]

                self.logger.info("检测到文件变化: %s %s", symbol, interval)

                # 重新扫描该品种
                symbol_quality = self.scan_symbol(symbol, force_refresh=True)

                if symbol_quality:
                    # 更新概览
                    self._update_overview_incremental(symbol, symbol_quality)

                    # 发送质量更新事件
                    self._emit_quality_update_event(symbol, symbol_quality)

        except Exception as e:
            self.logger.error("处理文件变化失败: %s", e)

    def _detect_missing_symbols(
        self,
        reference_symbols: List[str],
        existing_symbols: List[str],
    ) -> List[str]:
        """检测缺失的品种

        Args:
            reference_symbols: 参考品种列表
            existing_symbols: 现有品种列表

        Returns:
            缺失的品种列表
        """
        if not reference_symbols:
            return []

        reference_set = set(reference_symbols)
        existing_set = set(existing_symbols)
        missing = reference_set - existing_set

        return sorted(missing)

    def _calculate_overall_score(self, interval_results: Dict[str, ValidationResult]) -> int:
        """计算品种的综合质量评分

        Args:
            interval_results: 各周期的验证结果

        Returns:
            综合评分（0-100）
        """
        if not interval_results:
            return 0

        # 计算各周期的评分
        scores = []
        for result in interval_results.values():
            score = self._calculate_single_score(result)
            scores.append(score)

        # 返回平均分
        return int(sum(scores) / len(scores))

    def _calculate_single_score(self, result: ValidationResult) -> int:
        """计算单个周期的质量评分

        Args:
            result: 验证结果

        Returns:
            质量评分（0-100）
        """
        base_score = 100

        # 1. 数据缺失扣分
        if result.record_count == 0:
            return 0

        # 2. 缺失日期扣分
        if result.missing_dates:
            # 假设基日到今天约1000个交易日
            missing_ratio = len(result.missing_dates) / 1000
            base_score -= int(missing_ratio * 40)  # 最多扣40分

        # 3. 错误扣分
        base_score -= len(result.errors) * 10  # 每个错误扣10分

        # 4. 警告扣分
        base_score -= len(result.warnings) * 5  # 每个警告扣5分

        return max(0, min(100, base_score))

    def _generate_overview(
        self,
        quality_results: Dict[str, SymbolQuality],
        missing_symbols: List[str],
    ) -> QualityOverview:
        """生成质量概览

        Args:
            quality_results: 品种质量结果
            missing_symbols: 缺失的品种列表

        Returns:
            质量概览
        """
        # 统计
        total_symbols = (
            len(self.reference_symbols) if self.reference_symbols else len(quality_results)
        )
        missing_count = len(missing_symbols)
        error_count = sum(1 for q in quality_results.values() if q.has_errors)
        warning_count = sum(1 for q in quality_results.values() if q.has_warnings)

        # 计算整体质量评分
        if quality_results:
            scores = [q.overall_score for q in quality_results.values()]
            overall_score = int(sum(scores) / len(scores))
        else:
            overall_score = 0

        # 如果有缺失品种，降低评分
        if missing_count > 0 and total_symbols > 0:
            missing_penalty = int((missing_count / total_symbols) * 30)  # 最多扣30分
            overall_score = max(0, overall_score - missing_penalty)

        # 生成详细列表（仅包含有问题的品种，用于UI展示）
        details = []

        # 1. 先添加缺失品种（优先级最高）
        for symbol in missing_symbols[:50]:  # 最多50个缺失品种
            detail = {
                "symbol": symbol,
                "score": 0,
                "status": "missing",  # 状态：缺失
                "has_errors": False,
                "has_warnings": False,
                "issues": ["品种数据完全缺失"],  # 问题列表
                "intervals": {},
            }
            details.append(detail)

        # 2. 添加有问题的已存在品种
        for symbol, quality in quality_results.items():
            if quality.has_errors or quality.has_warnings or quality.overall_score < 80:
                # 确定状态
                if quality.has_errors:
                    status = "error"
                elif quality.has_warnings:
                    status = "warning"
                else:
                    status = "normal"

                # 收集所有问题
                issues = []
                intervals_detail = {}

                for interval, result in quality.intervals.items():
                    intervals_detail[interval] = {
                        "record_count": result.record_count,
                        "missing_dates": len(result.missing_dates),
                        "errors": len(result.errors),
                        "warnings": len(result.warnings),
                    }

                    # 收集该周期的错误和警告
                    for error in result.errors:
                        issues.append(f"[{interval}] {error}")
                    for warning in result.warnings:
                        issues.append(f"[{interval}] {warning}")

                    # 添加缺失日期信息
                    if result.missing_dates:
                        issues.append(f"[{interval}] 缺失 {len(result.missing_dates)} 个交易日")

                detail = {
                    "symbol": symbol,
                    "score": quality.overall_score,
                    "status": status,
                    "has_errors": quality.has_errors,
                    "has_warnings": quality.has_warnings,
                    "issues": issues,  # 问题列表
                    "intervals": intervals_detail,
                }

                details.append(detail)

        # 按状态优先级排序：缺失(1) → 错误(2) → 警告(3) → 正常(4)，同状态按评分排序
        status_priority = {"missing": 1, "error": 2, "warning": 3, "normal": 4}
        details.sort(key=lambda x: (status_priority.get(x["status"], 5), x["score"]))

        return QualityOverview(
            total_symbols=total_symbols,
            missing_symbols=missing_count,
            error_symbols=error_count,
            warning_symbols=warning_count,
            quality_score=overall_score,
            last_scan_time=datetime.now(),
            base_date=config_manager.get_base_date(),
            scanned_intervals=self.scan_intervals,
            details=details[:100],  # 最多返回100个有问题的品种
        )

    def _update_overview_incremental(self, symbol: str, symbol_quality: SymbolQuality) -> None:
        """增量更新质量概览

        Args:
            symbol: 品种代码
            symbol_quality: 品种质量信息
        """
        if not self.quality_overview:
            return

        # 更新缓存中的品种质量
        self.quality_cache[symbol] = symbol_quality

        # 重新计算统计数据
        # （简化处理：重新生成整个概览）
        existing_symbols = list(self.quality_cache.keys())
        missing_symbols = self._detect_missing_symbols(self.reference_symbols, existing_symbols)
        self.quality_overview = self._generate_overview(self.quality_cache, missing_symbols)

    def _create_empty_overview(self) -> QualityOverview:
        """创建空的质量概览

        Returns:
            空概览
        """
        return QualityOverview(
            total_symbols=0,
            missing_symbols=0,
            error_symbols=0,
            warning_symbols=0,
            quality_score=0,
            last_scan_time=datetime.now(),
            base_date=config_manager.get_base_date(),
            scanned_intervals=self.scan_intervals,
            details=[],
        )

    def _emit_scan_complete_event(self, overview: QualityOverview) -> None:
        """发送扫描完成事件

        Args:
            overview: 质量概览
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "type": "scan_complete",
                "total_symbols": overview.total_symbols,
                "missing_symbols": overview.missing_symbols,
                "error_symbols": overview.error_symbols,
                "warning_symbols": overview.warning_symbols,
                "quality_score": overview.quality_score,
                "scan_time": overview.last_scan_time.isoformat(),
            }

            event = Event(EVENT_DATA_SCAN_COMPLETE, event_data)
            self.event_engine.put(event)

            self.logger.info("已发送扫描完成事件")

        except Exception as e:
            self.logger.error("发送扫描完成事件失败: %s", e)

    def _emit_quality_update_event(self, symbol: str, quality: SymbolQuality) -> None:
        """发送质量更新事件

        Args:
            symbol: 品种代码
            quality: 品种质量信息
        """
        if not self.event_engine:
            return

        try:
            event_data = {
                "type": "quality_update",
                "symbol": symbol,
                "score": quality.overall_score,
                "has_errors": quality.has_errors,
                "has_warnings": quality.has_warnings,
                "is_missing": quality.is_missing,
            }

            event = Event(EVENT_DATA_QUALITY_UPDATE, event_data)
            self.event_engine.put(event)

            self.logger.debug("已发送品种 %s 质量更新事件", symbol)

        except Exception as e:
            self.logger.error("发送质量更新事件失败: %s", e)

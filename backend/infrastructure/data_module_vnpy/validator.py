# -*- coding: utf-8 -*-
"""
数据感知与校验模块

负责数据质量检查和感知，包括：
- 品种缺失感知：对比最新品种列表缓存
- 历史数据缺失：检查基日至今的连续性
- 逻辑错误：high < low, open/close 超出范围
- 格式错误：price/volume非数值
- 缓存检查结果，增量检查机制
- 多线程/多进程处理
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import json
import logging
from dataclasses import dataclass, asdict

from .config import config_manager
from .storage import StorageManager


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
    results: List[ValidationResult]


class DataValidator:
    """数据校验器"""

    def __init__(self):
        """初始化数据校验器"""
        self.storage_manager = StorageManager()
        self.logger = logging.getLogger(__name__)
        self.base_date = config_manager.get_base_date()
        self.max_workers = config_manager.get_max_workers()

        # 校验结果缓存
        self.cache_file = config_manager.get_cache_dir() / "validation_results.json"
        self._cached_results = {}
        self._load_cached_results()

    def validate_all_data(self, force_refresh: bool = False) -> ValidationSummary:
        """
        校验所有数据

        Args:
            force_refresh: 是否强制刷新校验结果

        Returns:
            校验汇总结果
        """
        self.logger.info("开始校验所有数据...")

        # 获取所有品种
        symbols = self.storage_manager.list_symbols()
        if not symbols:
            self.logger.warning("未发现任何品种数据")
            return ValidationSummary(
                total_symbols=0, valid_symbols=0, invalid_symbols=0,
                total_errors=0, total_warnings=0, check_time=datetime.now(),
                base_date=self.base_date, results=[]
            )

        # 并行校验所有品种
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_symbol = {}

            for symbol in symbols:
                intervals = self.storage_manager.list_intervals(symbol)
                for interval in intervals:
                    future = executor.submit(self._validate_single_data, symbol, interval, force_refresh)
                    future_to_symbol[future] = (symbol, interval)

            for future in as_completed(future_to_symbol):
                symbol, interval = future_to_symbol[future]
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.error(f"校验 {symbol} {interval} 失败: {e}")

        # 生成汇总
        summary = self._generate_summary(results)

        # 缓存结果
        self._cache_results(summary)

        self.logger.info(f"数据校验完成: {summary.valid_symbols}/{summary.total_symbols} 有效")
        return summary

    def validate_symbol(self, symbol: str, interval: str = None) -> Union[ValidationResult, List[ValidationResult]]:
        """
        校验指定品种数据

        Args:
            symbol: 品种代码
            interval: K线周期，如果为None则校验所有周期

        Returns:
            校验结果
        """
        if interval:
            return self._validate_single_data(symbol, interval)
        else:
            intervals = self.storage_manager.list_intervals(symbol)
            results = []
            for interval in intervals:
                result = self._validate_single_data(symbol, interval)
                if result:
                    results.append(result)
            return results

    def check_missing_symbols(self, reference_stocks: List[str]) -> List[str]:
        """
        检查缺失的品种

        Args:
            reference_stocks: 参考品种列表

        Returns:
            缺失的品种列表
        """
        try:
            existing_symbols = set(self.storage_manager.list_symbols())
            reference_symbols = set(reference_stocks)
            missing_symbols = reference_symbols - existing_symbols

            self.logger.info(f"发现 {len(missing_symbols)} 个缺失品种")
            return sorted(missing_symbols)

        except Exception as e:
            self.logger.error(f"检查缺失品种失败: {e}")
            return []

    def check_missing_dates(self, symbol: str, interval: str,
                          start_date: date = None, end_date: date = None) -> List[date]:
        """
        检查缺失的日期

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期，默认使用基日
            end_date: 结束日期，默认使用今天

        Returns:
            缺失的日期列表
        """
        try:
            if start_date is None:
                start_date = self.base_date
            if end_date is None:
                end_date = date.today()

            # 获取现有数据
            data = self.storage_manager.query_kline(symbol, interval, start_date, end_date)
            if data is None or data.empty:
                return self._generate_date_range(start_date, end_date, interval)

            # 生成期望的日期范围
            expected_dates = set(self._generate_date_range(start_date, end_date, interval))

            # 获取实际日期
            if 'datetime' in data.columns:
                actual_dates = set(data['datetime'].dt.date)
            else:
                return list(expected_dates)

            # 找出缺失的日期
            missing_dates = expected_dates - actual_dates

            return sorted(missing_dates)

        except Exception as e:
            self.logger.error(f"检查 {symbol} {interval} 缺失日期失败: {e}")
            return []

    def check_logic_errors(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        检查逻辑错误

        Args:
            data: K线数据DataFrame

        Returns:
            逻辑错误列表
        """
        errors = []

        try:
            # 检查高价低于低价
            if 'high' in data.columns and 'low' in data.columns:
                invalid_high_low = data[data['high'] < data['low']]
                for idx, row in invalid_high_low.iterrows():
                    errors.append({
                        "type": "high_low_invalid",
                        "row": int(idx),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "message": f"高价 {row['high']} 低于低价 {row['low']}"
                    })

            # 检查开盘价和收盘价超出高低价范围
            if all(col in data.columns for col in ['open', 'high', 'low']):
                invalid_open = data[(data['open'] > data['high']) | (data['open'] < data['low'])]
                for idx, row in invalid_open.iterrows():
                    errors.append({
                        "type": "open_out_of_range",
                        "row": int(idx),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "message": f"开盘价 {row['open']} 超出高低价范围 [{row['low']}, {row['high']}]"
                    })

            if all(col in data.columns for col in ['close', 'high', 'low']):
                invalid_close = data[(data['close'] > data['high']) | (data['close'] < data['low'])]
                for idx, row in invalid_close.iterrows():
                    errors.append({
                        "type": "close_out_of_range",
                        "row": int(idx),
                        "close": float(row['close']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "message": f"收盘价 {row['close']} 超出高低价范围 [{row['low']}, {row['high']}]"
                    })

            # 检查负值
            price_columns = ['open', 'high', 'low', 'close']
            for col in price_columns:
                if col in data.columns:
                    negative_prices = data[data[col] < 0]
                    for idx, row in negative_prices.iterrows():
                        errors.append({
                            "type": "negative_price",
                            "row": int(idx),
                            "column": col,
                            "value": float(row[col]),
                            "message": f"{col} 价格 {row[col]} 为负值"
                        })

            # 检查成交量负值
            if 'volume' in data.columns:
                negative_volume = data[data['volume'] < 0]
                for idx, row in negative_volume.iterrows():
                    errors.append({
                        "type": "negative_volume",
                        "row": int(idx),
                        "value": float(row['volume']),
                        "message": f"成交量 {row['volume']} 为负值"
                    })

        except Exception as e:
            self.logger.error(f"检查逻辑错误失败: {e}")

        return errors

    def check_format_errors(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        检查格式错误

        Args:
            data: K线数据DataFrame

        Returns:
            格式错误列表
        """
        errors = []

        try:
            # 检查数值列的数据类型
            numeric_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_columns:
                if col in data.columns:
                    # 检查是否有非数值数据
                    non_numeric = data[~pd.to_numeric(data[col], errors='coerce').notna()]
                    for idx, row in non_numeric.iterrows():
                        errors.append({
                            "type": "non_numeric",
                            "row": int(idx),
                            "column": col,
                            "value": str(row[col]),
                            "message": f"{col} 列包含非数值数据: {row[col]}"
                        })

            # 检查缺失值
            for col in numeric_columns:
                if col in data.columns:
                    missing_values = data[data[col].isna()]
                    if not missing_values.empty:
                        for idx, row in missing_values.iterrows():
                            errors.append({
                                "type": "missing_value",
                                "row": int(idx),
                                "column": col,
                                "message": f"{col} 列包含缺失值"
                            })

            # 检查datetime列
            if 'datetime' in data.columns:
                invalid_datetime = data[~pd.to_datetime(data['datetime'], errors='coerce').notna()]
                for idx, row in invalid_datetime.iterrows():
                    errors.append({
                        "type": "invalid_datetime",
                        "row": int(idx),
                        "value": str(row['datetime']),
                        "message": f"datetime 列包含无效日期: {row['datetime']}"
                    })

        except Exception as e:
            self.logger.error(f"检查格式错误失败: {e}")

        return errors

    def get_validation_summary(self) -> Optional[ValidationSummary]:
        """
        获取最新的校验汇总

        Returns:
            校验汇总结果
        """
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 重建ValidationSummary对象
                results = []
                for result_data in data.get('results', []):
                    result = ValidationResult(**result_data)
                    results.append(result)

                summary = ValidationSummary(
                    total_symbols=data['total_symbols'],
                    valid_symbols=data['valid_symbols'],
                    invalid_symbols=data['invalid_symbols'],
                    total_errors=data['total_errors'],
                    total_warnings=data['total_warnings'],
                    check_time=datetime.fromisoformat(data['check_time']),
                    base_date=datetime.fromisoformat(data['base_date']).date(),
                    results=results
                )

                return summary

            except Exception as e:
                self.logger.error(f"读取校验汇总失败: {e}")

        return None

    def _validate_single_data(self, symbol: str, interval: str, force_refresh: bool = False) -> Optional[ValidationResult]:
        """
        校验单个数据文件

        Args:
            symbol: 品种代码
            interval: K线周期
            force_refresh: 是否强制刷新

        Returns:
            校验结果
        """
        try:
            # 检查缓存
            cache_key = f"{symbol}_{interval}"
            if not force_refresh and cache_key in self._cached_results:
                cached_result = self._cached_results[cache_key]
                if datetime.now() - cached_result['check_time'] < timedelta(hours=1):
                    return ValidationResult(**cached_result)

            # 获取数据
            data = self.storage_manager.query_kline(symbol, interval)
            if data is None or data.empty:
                return ValidationResult(
                    symbol=symbol, interval=interval, check_time=datetime.now(),
                    is_valid=False, errors=["数据文件不存在或为空"], warnings=[],
                    record_count=0, date_range=(None, None), missing_dates=[],
                    logic_errors=[], format_errors=[]
                )

            # 执行各种检查
            errors = []
            warnings = []

            # 逻辑错误检查
            logic_errors = self.check_logic_errors(data)
            if logic_errors:
                errors.extend([error['message'] for error in logic_errors])

            # 格式错误检查
            format_errors = self.check_format_errors(data)
            if format_errors:
                errors.extend([error['message'] for error in format_errors])

            # 缺失日期检查
            missing_dates = self.check_missing_dates(symbol, interval)
            if missing_dates:
                warnings.append(f"缺失 {len(missing_dates)} 个交易日")

            # 生成结果
            result = ValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=datetime.now(),
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                record_count=len(data),
                date_range=(
                    data['datetime'].min().date() if 'datetime' in data.columns else None,
                    data['datetime'].max().date() if 'datetime' in data.columns else None
                ),
                missing_dates=missing_dates,
                logic_errors=logic_errors,
                format_errors=format_errors
            )

            # 更新缓存
            self._cached_results[cache_key] = asdict(result)

            return result

        except Exception as e:
            self.logger.error(f"校验 {symbol} {interval} 失败: {e}")
            return None

    def _generate_date_range(self, start_date: date, end_date: date, interval: str) -> List[date]:
        """
        生成期望的日期范围

        Args:
            start_date: 开始日期
            end_date: 结束日期
            interval: K线周期

        Returns:
            日期列表
        """
        dates = []
        current_date = start_date

        while current_date <= end_date:
            # 跳过周末（假设只有工作日有交易数据）
            if current_date.weekday() < 5:  # 0-4 表示周一到周五
                dates.append(current_date)

            current_date += timedelta(days=1)

        return dates

    def _generate_summary(self, results: List[ValidationResult]) -> ValidationSummary:
        """
        生成校验汇总

        Args:
            results: 校验结果列表

        Returns:
            校验汇总
        """
        total_symbols = len(results)
        valid_symbols = sum(1 for r in results if r.is_valid)
        invalid_symbols = total_symbols - valid_symbols
        total_errors = sum(len(r.errors) for r in results)
        total_warnings = sum(len(r.warnings) for r in results)

        return ValidationSummary(
            total_symbols=total_symbols,
            valid_symbols=valid_symbols,
            invalid_symbols=invalid_symbols,
            total_errors=total_errors,
            total_warnings=total_warnings,
            check_time=datetime.now(),
            base_date=self.base_date,
            results=results
        )

    def _cache_results(self, summary: ValidationSummary) -> None:
        """
        缓存校验结果

        Args:
            summary: 校验汇总
        """
        try:
            cache_data = {
                "total_symbols": summary.total_symbols,
                "valid_symbols": summary.valid_symbols,
                "invalid_symbols": summary.invalid_symbols,
                "total_errors": summary.total_errors,
                "total_warnings": summary.total_warnings,
                "check_time": summary.check_time.isoformat(),
                "base_date": summary.base_date.isoformat(),
                "results": [asdict(result) for result in summary.results]
            }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            self.logger.error(f"缓存校验结果失败: {e}")

    def _load_cached_results(self) -> None:
        """
        加载缓存的校验结果
        """
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for result_data in data.get('results', []):
                    cache_key = f"{result_data['symbol']}_{result_data['interval']}"
                    self._cached_results[cache_key] = result_data

        except Exception as e:
            self.logger.error(f"加载缓存校验结果失败: {e}")

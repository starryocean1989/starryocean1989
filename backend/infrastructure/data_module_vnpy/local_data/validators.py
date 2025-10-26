# -*- coding: utf-8 -*-
"""
数据验证器模块 - 极限合并版

本模块已完成极限合并：将原3个独立文件合并为1个统一文件validators.py

合并前文件清单：
1. stateless_validator.py (461行) - 无状态验证器（快速批量验证）
2. gpu_validator.py (285行) - GPU加速验证器（CUDA/OpenCL加速）
3. incremental_scan.py (265行) - 增量扫描器（监控文件变化）

合并后：validators.py (~1,011行)

负责数据质量验证：
- 无状态验证器：快速批量验证数据完整性和质量
- GPU加速验证：利用GPU并行计算加速大规模数据验证
- 增量扫描：监控数据文件变化，触发增量验证

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-26
"""


# ==============================================================================
# 第1部分：无状态验证器（原stateless_validator.py）
# ==============================================================================


from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


# ==================== 数据类 ====================


@dataclass
class StatelessValidationResult:
    """无状态验证结果"""

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
    freshness_score: float  # 数据新鲜度得分 (0-100)
    completeness_score: float  # 数据完整性得分 (0-100)


@dataclass
class ValidationContext:
    """验证上下文（共享数据）

    包含验证所需的所有静态数据，通过共享内存传递给子进程。
    """

    # IPO日期字典 {symbol: date}
    ipo_dates: Dict[str, date]

    # 交易日集合
    trading_days: Set[date]

    # 最新交易日
    latest_trading_day: date

    # 基准日期（用于计算有效起始日期）
    base_date: date

    # 验证规则配置
    min_records_threshold: int = 100  # 最小记录数阈值
    freshness_days_warning: int = 7  # 数据滞后警告阈值（天）
    freshness_days_error: int = 30  # 数据滞后错误阈值（天）


# ==================== 无状态验证器 ====================


class StatelessValidator:
    """无状态验证器（纯函数验证器）

    所有方法都是静态方法，不依赖实例状态，完全可序列化。

    使用示例：
        # 准备验证上下文（一次性）
        context = ValidationContext(
            ipo_dates=ipo_dates_dict,
            trading_days=trading_days_set,
            latest_trading_day=latest_day,
            base_date=base_date
        )

        # 验证单个品种（可在多进程中执行）
        result = StatelessValidator.validate_symbol(
            symbol="000001",
            interval="1d",
            df=df,
            context=context
        )
    """

    # ==================== 核心验证方法 ====================

    @staticmethod
    def validate_symbol(
        symbol: str, interval: str, df: pd.DataFrame, context: ValidationContext
    ) -> StatelessValidationResult:
        """验证单个品种的数据（纯函数，完全无状态）

        Args:
            symbol: 品种代码
            interval: 时间间隔
            df: 数据DataFrame
            context: 验证上下文

        Returns:
            StatelessValidationResult: 验证结果
        """
        check_time = datetime.now()

        # 数据为空检查
        if df is None or df.empty:
            return StatelessValidationResult(
                symbol=symbol,
                interval=interval,
                check_time=check_time,
                is_valid=False,
                errors=["数据不存在或为空"],
                warnings=[],
                record_count=0,
                date_range=(None, None),
                missing_dates=[],
                logic_errors=[],
                format_errors=[],
                freshness_score=0.0,
                completeness_score=0.0,
            )

        # 执行各项验证
        errors = []
        warnings = []

        # 1. 格式验证
        format_errors = StatelessValidator.validate_format(df)
        if format_errors:
            errors.extend([err["message"] for err in format_errors])

        # 2. 逻辑验证
        logic_errors = StatelessValidator.validate_logic(df)
        if logic_errors:
            warnings.extend([err["message"] for err in logic_errors])

        # 3. 计算日期范围
        date_range = StatelessValidator.calculate_date_range(df)

        # 4. 完整性验证
        missing_dates, completeness_warnings = StatelessValidator.validate_completeness(
            df=df,
            symbol=symbol,
            date_range=date_range,
            context=context,
        )
        warnings.extend(completeness_warnings)

        # 5. 新鲜度验证
        freshness_warnings = StatelessValidator.validate_freshness(
            df=df, date_range=date_range, context=context
        )
        warnings.extend(freshness_warnings)

        # 6. 计算质量得分
        freshness_score = StatelessValidator.calculate_freshness_score(
            date_range=date_range, context=context
        )
        completeness_score = StatelessValidator.calculate_completeness_score(
            df=df, missing_dates=missing_dates, date_range=date_range, context=context
        )

        # 判断是否有效
        is_valid = len(errors) == 0

        return StatelessValidationResult(
            symbol=symbol,
            interval=interval,
            check_time=check_time,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            record_count=len(df),
            date_range=date_range,
            missing_dates=missing_dates,
            logic_errors=logic_errors,
            format_errors=format_errors,
            freshness_score=freshness_score,
            completeness_score=completeness_score,
        )

    # ==================== 子验证方法 ====================

    @staticmethod
    def validate_format(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """格式验证（纯函数）

        检查：
        - 必需列是否存在
        - 数据类型是否正确
        - 是否有NaN值

        Args:
            df: 数据DataFrame

        Returns:
            格式错误列表
        """
        errors = []

        # 检查必需列
        required_columns = ["datetime", "open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]

        if missing_columns:
            errors.append(
                {
                    "type": "missing_columns",
                    "message": f"缺少必需列: {', '.join(missing_columns)}",
                    "details": {"missing": missing_columns},
                }
            )

        # 检查数值列是否有NaN
        if not errors:  # 只有在列存在时才检查
            numeric_columns = ["open", "high", "low", "close", "volume"]
            for col in numeric_columns:
                if col in df.columns:
                    nan_count = df[col].isna().sum()
                    if nan_count > 0:
                        errors.append(
                            {
                                "type": "nan_values",
                                "message": f"列 {col} 包含 {nan_count} 个NaN值",
                                "details": {"column": col, "nan_count": int(nan_count)},
                            }
                        )

        return errors

    @staticmethod
    def validate_logic(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """逻辑验证（纯函数）

        检查：
        - high >= low
        - high >= open, close
        - low <= open, close
        - volume >= 0

        Args:
            df: 数据DataFrame

        Returns:
            逻辑错误列表
        """
        errors = []

        if df.empty:
            return errors

        try:
            # 检查价格逻辑
            if all(col in df.columns for col in ["high", "low", "open", "close"]):
                # high < low
                invalid_high_low = df[df["high"] < df["low"]]
                if not invalid_high_low.empty:
                    errors.append(
                        {
                            "type": "invalid_high_low",
                            "message": f"{len(invalid_high_low)}行数据 high < low",
                            "details": {"count": len(invalid_high_low)},
                        }
                    )

                # high < open or high < close
                invalid_high = df[(df["high"] < df["open"]) | (df["high"] < df["close"])]
                if not invalid_high.empty:
                    errors.append(
                        {
                            "type": "invalid_high",
                            "message": f"{len(invalid_high)}行数据 high 小于 open/close",
                            "details": {"count": len(invalid_high)},
                        }
                    )

                # low > open or low > close
                invalid_low = df[(df["low"] > df["open"]) | (df["low"] > df["close"])]
                if not invalid_low.empty:
                    errors.append(
                        {
                            "type": "invalid_low",
                            "message": f"{len(invalid_low)}行数据 low 大于 open/close",
                            "details": {"count": len(invalid_low)},
                        }
                    )

            # 检查成交量
            if "volume" in df.columns:
                invalid_volume = df[df["volume"] < 0]
                if not invalid_volume.empty:
                    errors.append(
                        {
                            "type": "negative_volume",
                            "message": f"{len(invalid_volume)}行数据成交量为负",
                            "details": {"count": len(invalid_volume)},
                        }
                    )

        except Exception as e:
            errors.append(
                {
                    "type": "logic_check_error",
                    "message": f"逻辑验证失败: {str(e)}",
                    "details": {"error": str(e)},
                }
            )

        return errors

    @staticmethod
    def calculate_date_range(
        df: pd.DataFrame,
    ) -> Tuple[Optional[date], Optional[date]]:
        """计算数据日期范围（纯函数）

        Args:
            df: 数据DataFrame

        Returns:
            (起始日期, 结束日期) 或 (None, None)
        """
        if df.empty:
            return (None, None)

        try:
            # 尝试从索引获取
            if pd.api.types.is_datetime64_any_dtype(df.index):
                min_val = df.index.min()
                max_val = df.index.max()
                if pd.notna(min_val) and pd.notna(max_val):  # type: ignore
                    min_ts = pd.Timestamp(min_val)  # type: ignore
                    max_ts = pd.Timestamp(max_val)  # type: ignore
                    return (min_ts.date(), max_ts.date())

            # 尝试从datetime列获取
            if "datetime" in df.columns:
                datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                if not datetime_series.isna().all():  # type: ignore
                    min_val = datetime_series.min()
                    max_val = datetime_series.max()
                    if pd.notna(min_val) and pd.notna(max_val):  # type: ignore
                        min_ts = pd.Timestamp(min_val)  # type: ignore
                        max_ts = pd.Timestamp(max_val)  # type: ignore
                        return (min_ts.date(), max_ts.date())  # type: ignore

        except Exception:
            pass

        return (None, None)

    @staticmethod
    def validate_completeness(
        df: pd.DataFrame,
        symbol: str,
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> Tuple[List[date], List[str]]:
        """完整性验证（纯函数）

        检查数据是否覆盖所有交易日。

        Args:
            df: 数据DataFrame
            symbol: 品种代码
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            (缺失日期列表, 警告列表)
        """
        warnings = []
        missing_dates = []

        if date_range[0] is None or date_range[1] is None:
            warnings.append("无法计算日期范围，跳过完整性检查")
            return (missing_dates, warnings)

        start_date, end_date = date_range

        # 获取IPO日期
        ipo_date = context.ipo_dates.get(symbol)

        # 计算有效起始日期
        effective_start = StatelessValidator.compute_effective_start_date(
            ipo_date=ipo_date, data_start=start_date, base_date=context.base_date
        )

        # 计算应该存在的交易日
        expected_days = {
            d
            for d in context.trading_days
            if effective_start <= d <= min(end_date, context.latest_trading_day)  # type: ignore
        }

        # 从DataFrame获取实际存在的日期
        actual_days: set = set()
        try:
            if pd.api.types.is_datetime64_any_dtype(df.index):
                actual_days = {pd.Timestamp(d).date() for d in df.index}  # type: ignore
            elif "datetime" in df.columns:
                datetime_series = pd.to_datetime(df["datetime"], errors="coerce")
                actual_days = {pd.Timestamp(d).date() for d in datetime_series if pd.notna(d)}  # type: ignore
        except Exception:
            pass

        # 计算缺失日期
        missing_dates = sorted(list(expected_days - actual_days))  # type: ignore

        if missing_dates:
            warnings.append(f"缺失 {len(missing_dates)} 个交易日数据")

        return (missing_dates, warnings)

    @staticmethod
    def validate_freshness(
        df: pd.DataFrame,  # noqa: ARG004
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> List[str]:
        """新鲜度验证（纯函数）

        检查数据是否及时更新。

        Args:
            df: 数据DataFrame
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            警告列表
        """
        warnings = []

        if date_range[1] is None:
            warnings.append("无法计算最新日期，跳过新鲜度检查")
            return warnings

        end_date = date_range[1]
        latest_trading_day = context.latest_trading_day

        # 计算滞后天数
        lag_days = (latest_trading_day - end_date).days

        if lag_days > context.freshness_days_error:
            warnings.append(f"数据严重滞后: {lag_days}天（> {context.freshness_days_error}天）")
        elif lag_days > context.freshness_days_warning:
            warnings.append(f"数据滞后: {lag_days}天（> {context.freshness_days_warning}天）")

        return warnings

    @staticmethod
    def calculate_freshness_score(
        date_range: Tuple[Optional[date], Optional[date]], context: ValidationContext
    ) -> float:
        """计算新鲜度得分（纯函数）

        Args:
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            新鲜度得分 (0-100)
        """
        if date_range[1] is None:
            return 0.0

        end_date = date_range[1]
        latest_trading_day = context.latest_trading_day

        lag_days = (latest_trading_day - end_date).days

        # 计算得分：无滞后=100分，每滞后1天扣3分，最低0分
        score = max(0.0, 100.0 - lag_days * 3.0)

        return score

    @staticmethod
    def calculate_completeness_score(
        df: pd.DataFrame,  # noqa: ARG004
        missing_dates: List[date],
        date_range: Tuple[Optional[date], Optional[date]],
        context: ValidationContext,
    ) -> float:
        """计算完整性得分（纯函数）

        Args:
            df: 数据DataFrame
            missing_dates: 缺失日期列表
            date_range: 数据日期范围
            context: 验证上下文

        Returns:
            完整性得分 (0-100)
        """
        if date_range[0] is None or date_range[1] is None:
            return 0.0

        start_date, end_date = date_range

        # 计算应该存在的交易日数量
        expected_days_count = len([d for d in context.trading_days if start_date <= d <= end_date])  # type: ignore

        if expected_days_count == 0:
            return 100.0  # 没有应该存在的交易日，认为是完整的

        # 计算缺失率
        missing_rate = len(missing_dates) / expected_days_count

        # 计算得分：无缺失=100分，缺失率每增加1%扣1分，最低0分
        score = max(0.0, 100.0 - missing_rate * 100.0)

        return score

    # ==================== 辅助方法 ====================

    @staticmethod
    def compute_effective_start_date(
        ipo_date: Optional[date], data_start: Optional[date], base_date: Optional[date]
    ) -> date:
        """计算有效起始日期（纯函数）

        Args:
            ipo_date: IPO日期
            data_start: 数据起始日期
            base_date: 基准日期

        Returns:
            有效起始日期
        """
        candidates: list = []

        if ipo_date:
            candidates.append(ipo_date)

        if data_start:
            candidates.append(data_start)

        if base_date:
            candidates.append(base_date)

        if candidates:
            return max(candidates)  # type: ignore  # 使用最近的日期
        else:
            return date(2020, 1, 1)  # 默认值


# ==================== 顶层函数（用于multiprocessing） ====================


def validate_symbol_stateless(task_data: Dict[str, Any]) -> StatelessValidationResult:
    """顶层函数：无状态验证单个品种（用于multiprocessing.Pool.map）

    Args:
        task_data: 任务数据字典，包含：
            - symbol: 品种代码
            - interval: 时间间隔
            - df: 数据DataFrame
            - context: ValidationContext对象

    Returns:
        StatelessValidationResult: 验证结果
    """
    return StatelessValidator.validate_symbol(
        symbol=task_data["symbol"],
        interval=task_data["interval"],
        df=task_data["df"],
        context=task_data["context"],
    )



# ==============================================================================
# 第2部分：GPU加速验证器（原gpu_validator.py）
# ==============================================================================


import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

# 尝试导入GPU库
try:
    import cupy as cp

    HAS_CUPY = True
except ImportError:
    HAS_CUPY = False
    cp = None

try:
    from numba import cuda

    HAS_NUMBA_CUDA = True
except ImportError:
    HAS_NUMBA_CUDA = False
    cuda = None


# ==================== GPU检测器 ====================


class GPUDetector:
    """GPU检测器

    检测系统GPU可用性和性能。
    """

    @staticmethod
    def detect_gpu() -> Dict[str, Any]:
        """检测GPU可用性

        Returns:
            GPU信息字典
        """
        info = {
            "has_gpu": False,
            "has_cupy": HAS_CUPY,
            "has_numba_cuda": HAS_NUMBA_CUDA,
            "gpu_count": 0,
            "gpu_names": [],
            "total_memory_gb": 0.0,
            "recommended": False,
        }

        # 检测CuPy
        if HAS_CUPY:
            try:
                # 测试GPU访问
                _ = cp.cuda.Device(0)  # type: ignore
                info["has_gpu"] = True
                info["gpu_count"] = cp.cuda.runtime.getDeviceCount()  # type: ignore
                info["gpu_names"] = [cp.cuda.Device(i).name for i in range(info["gpu_count"])]

                # 获取GPU内存
                meminfo = cp.cuda.Device(0).mem_info
                info["total_memory_gb"] = meminfo[1] / (1024**3)

                # 推荐使用GPU：内存>4GB
                info["recommended"] = info["total_memory_gb"] > 4.0

            except Exception as e:
                logging.warning("CuPy GPU检测失败: %s", e)

        # 检测Numba CUDA
        elif HAS_NUMBA_CUDA:
            try:
                if cuda.is_available():  # type: ignore
                    info["has_gpu"] = True
                    info["gpu_count"] = len(cuda.gpus)  # type: ignore
                    info["gpu_names"] = [str(gpu) for gpu in cuda.gpus]  # type: ignore
                    # Numba不提供详细内存信息
                    info["recommended"] = True
            except Exception as e:
                logging.warning("Numba CUDA检测失败: %s", e)

        return info

    @staticmethod
    def log_gpu_info():
        """打印GPU信息到日志"""
        logger = logging.getLogger(__name__)
        info = GPUDetector.detect_gpu()

        if info["has_gpu"]:
            logger.info("=" * 60)
            logger.info("🚀 检测到GPU支持")
            logger.info("  - GPU数量: %d", info["gpu_count"])
            logger.info("  - GPU名称: %s", ", ".join(info["gpu_names"]))
            if info["total_memory_gb"] > 0:
                logger.info("  - GPU内存: %.1f GB", info["total_memory_gb"])
            logger.info("  - 推荐使用GPU: %s", "是" if info["recommended"] else "否（内存<4GB）")
            logger.info("=" * 60)
        else:
            logger.info("ℹ️  未检测到GPU支持，将使用CPU模式")

        return info


# ==================== GPU加速验证器 ====================


class GPUValidator:
    """GPU加速验证器

    自动检测GPU并使用最佳加速方式。

    使用示例：
        validator = GPUValidator()

        if validator.is_gpu_available:
            # GPU加速验证
            result = validator.validate_dataframe_gpu(df)
        else:
            # CPU验证
            result = validator.validate_dataframe_cpu(df)
    """

    def __init__(self, force_cpu: bool = False):
        """初始化GPU验证器

        Args:
            force_cpu: 是否强制使用CPU（即使GPU可用）
        """
        self.logger = logging.getLogger(__name__)
        self.force_cpu = force_cpu

        # 检测GPU
        self.gpu_info = GPUDetector.detect_gpu()
        self.is_gpu_available = self.gpu_info["has_gpu"] and not force_cpu

        if self.is_gpu_available:
            self.logger.info("✅ GPU验证器初始化完成（GPU模式）")
        else:
            self.logger.info("✅ GPU验证器初始化完成（CPU模式）")

    # ==================== 逻辑验证（GPU加速） ====================

    def validate_price_logic_gpu(self, df: pd.DataFrame) -> Dict[str, int]:
        """GPU加速价格逻辑验证

        验证：
        - high >= low
        - high >= open, close
        - low <= open, close

        Args:
            df: 数据DataFrame

        Returns:
            错误统计字典
        """
        if not self.is_gpu_available or not HAS_CUPY:
            # 降级到CPU
            return self._validate_price_logic_cpu(df)

        try:
            # 转换到GPU
            high_gpu = cp.asarray(df["high"].values)  # type: ignore
            low_gpu = cp.asarray(df["low"].values)  # type: ignore
            open_gpu = cp.asarray(df["open"].values)  # type: ignore
            close_gpu = cp.asarray(df["close"].values)  # type: ignore

            # GPU并行计算
            invalid_high_low = cp.sum(high_gpu < low_gpu)  # type: ignore
            invalid_high_open = cp.sum(high_gpu < open_gpu)  # type: ignore
            invalid_high_close = cp.sum(high_gpu < close_gpu)  # type: ignore
            invalid_low_open = cp.sum(low_gpu > open_gpu)  # type: ignore
            invalid_low_close = cp.sum(low_gpu > close_gpu)  # type: ignore

            # 转换回CPU
            return {
                "invalid_high_low": int(invalid_high_low.get()),  # type: ignore
                "invalid_high_open": int(invalid_high_open.get()),  # type: ignore
                "invalid_high_close": int(invalid_high_close.get()),  # type: ignore
                "invalid_low_open": int(invalid_low_open.get()),  # type: ignore
                "invalid_low_close": int(invalid_low_close.get()),  # type: ignore
            }

        except Exception as e:
            self.logger.warning("GPU验证失败，降级到CPU: %s", e)
            return self._validate_price_logic_cpu(df)

    def _validate_price_logic_cpu(self, df: pd.DataFrame) -> Dict[str, int]:
        """CPU价格逻辑验证（降级版本）"""
        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        open_price = df["open"].to_numpy()
        close = df["close"].to_numpy()

        return {
            "invalid_high_low": int(np.sum(high < low)),
            "invalid_high_open": int(np.sum(high < open_price)),
            "invalid_high_close": int(np.sum(high < close)),
            "invalid_low_open": int(np.sum(low > open_price)),
            "invalid_low_close": int(np.sum(low > close)),
        }

    # ==================== 统计计算（GPU加速） ====================

    def calculate_statistics_gpu(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """GPU加速统计计算

        计算：均值、标准差、最小值、最大值

        Args:
            df: 数据DataFrame
            column: 列名

        Returns:
            统计结果字典
        """
        if not self.is_gpu_available or not HAS_CUPY:
            return self._calculate_statistics_cpu(df, column)

        try:
            # 转换到GPU
            data_gpu = cp.asarray(df[column].values)  # type: ignore

            # GPU并行计算统计量
            mean_val = float(cp.mean(data_gpu).get())  # type: ignore
            std_val = float(cp.std(data_gpu).get())  # type: ignore
            min_val = float(cp.min(data_gpu).get())  # type: ignore
            max_val = float(cp.max(data_gpu).get())  # type: ignore

            return {
                "mean": mean_val,
                "std": std_val,
                "min": min_val,
                "max": max_val,
            }

        except Exception as e:
            self.logger.warning("GPU统计计算失败，降级到CPU: %s", e)
            return self._calculate_statistics_cpu(df, column)

    def _calculate_statistics_cpu(self, df: pd.DataFrame, column: str) -> Dict[str, float]:
        """CPU统计计算（降级版本）"""
        data = df[column].to_numpy()

        return {
            "mean": float(np.mean(data)),
            "std": float(np.std(data)),
            "min": float(np.min(data)),
            "max": float(np.max(data)),
        }

    # ==================== 批量验证 ====================

    def validate_batch_gpu(self, dataframes: List[pd.DataFrame]) -> List[Dict[str, Any]]:
        """GPU批量验证

        Args:
            dataframes: DataFrame列表

        Returns:
            验证结果列表
        """
        results = []

        for i, df in enumerate(dataframes):
            try:
                # 价格逻辑验证
                logic_errors = self.validate_price_logic_gpu(df)

                # 统计计算
                close_stats = self.calculate_statistics_gpu(df, "close")

                results.append(
                    {
                        "index": i,
                        "success": True,
                        "logic_errors": logic_errors,
                        "close_stats": close_stats,
                    }
                )

            except Exception as e:
                results.append({"index": i, "success": False, "error": str(e)})

        return results

    # ==================== 性能基准测试 ====================

    def benchmark(self, df: pd.DataFrame, iterations: int = 100) -> Dict[str, float]:
        """性能基准测试

        对比GPU和CPU性能。

        Args:
            df: 测试数据
            iterations: 迭代次数

        Returns:
            性能对比结果
        """
        import time

        self.logger.info("开始性能基准测试：%d次迭代", iterations)

        # CPU测试
        start = time.time()
        for _ in range(iterations):
            self._validate_price_logic_cpu(df)
        cpu_time = time.time() - start

        # GPU测试
        if self.is_gpu_available:
            start = time.time()
            for _ in range(iterations):
                self.validate_price_logic_gpu(df)
            gpu_time = time.time() - start

            speedup = cpu_time / gpu_time if gpu_time > 0 else 0.0

            self.logger.info("CPU时间: %.3f秒", cpu_time)
            self.logger.info("GPU时间: %.3f秒", gpu_time)
            self.logger.info("GPU加速比: %.2fx", speedup)

            return {
                "cpu_time": cpu_time,
                "gpu_time": gpu_time,
                "speedup": speedup,
                "gpu_available": True,
            }
        else:
            self.logger.info("CPU时间: %.3f秒", cpu_time)
            self.logger.info("GPU不可用，无法测试GPU性能")

            return {"cpu_time": cpu_time, "gpu_available": False}


# ==================== 便捷函数 ====================


def create_gpu_validator(force_cpu: bool = False) -> GPUValidator:
    """便捷函数：创建GPU验证器

    Args:
        force_cpu: 是否强制使用CPU

    Returns:
        GPUValidator实例
    """
    return GPUValidator(force_cpu=force_cpu)


def detect_and_log_gpu():
    """便捷函数：检测并打印GPU信息"""
    return GPUDetector.log_gpu_info()



# ==============================================================================
# 第3部分：增量扫描器（原incremental_scan.py）
# ==============================================================================


import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ==================== 数据类 ====================


@dataclass
class ScanRecord:
    """扫描记录"""

    symbol: str
    interval: str
    last_scan_time: datetime
    file_mtime: float  # 文件修改时间（Unix时间戳）
    file_size: int  # 文件大小（字节）
    checksum: Optional[str] = None  # 文件校验和（可选）


@dataclass
class ScanMetadata:
    """扫描元数据"""

    last_full_scan: datetime  # 上次全量扫描时间
    last_incremental_scan: Optional[datetime] = None  # 上次增量扫描时间
    total_symbols: int = 0  # 总品种数
    scan_count: int = 0  # 扫描次数


# ==================== 增量扫描管理器 ====================


class IncrementalScanManager:
    """增量扫描管理器

    维护扫描历史，识别需要扫描的品种。

    使用示例：
        manager = IncrementalScanManager(cache_dir="./cache")

        # 首次全量扫描
        all_symbols = get_all_symbols()
        manager.mark_full_scan(all_symbols, interval="1d")

        # 后续增量扫描（只扫描变化的）
        changed_symbols = manager.get_changed_symbols(
            all_symbols,
            interval="1d",
            data_dir="/path/to/data"
        )

        # 扫描后更新记录
        for symbol in changed_symbols:
            manager.update_scan_record(symbol, interval="1d", file_path=file_path)
    """

    def __init__(self, cache_dir: str = "./cache", metadata_file: str = "scan_metadata.json"):
        """初始化增量扫描管理器

        Args:
            cache_dir: 缓存目录
            metadata_file: 元数据文件名
        """
        self.logger = logging.getLogger(__name__)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.cache_dir / metadata_file
        self.records_file = self.cache_dir / "scan_records.json"

        # 扫描记录 {f"{symbol}_{interval}": ScanRecord}
        self._records: Dict[str, ScanRecord] = {}

        # 扫描元数据
        self._metadata: Optional[ScanMetadata] = None

        # 加载缓存
        self._load_cache()

    # ==================== 核心方法 ====================

    def get_changed_symbols(
        self, all_symbols: List[str], interval: str, data_dir: str
    ) -> List[str]:
        """获取变化的品种列表

        对比文件修改时间，识别需要扫描的品种。

        Args:
            all_symbols: 所有品种列表
            interval: 时间间隔
            data_dir: 数据目录

        Returns:
            变化的品种列表
        """
        changed_symbols = []
        data_path = Path(data_dir)

        for symbol in all_symbols:
            key = f"{symbol}_{interval}"
            record = self._records.get(key)

            # 构建文件路径（根据实际存储结构调整）
            file_path = self._build_file_path(symbol, interval, data_path)

            if not file_path.exists():
                # 文件不存在，跳过
                continue

            # 获取文件状态
            file_stat = os.stat(file_path)
            file_mtime = file_stat.st_mtime
            file_size = file_stat.st_size

            # 判断是否变化
            if record is None:
                # 无记录，需要扫描
                changed_symbols.append(symbol)
            elif file_mtime > record.file_mtime:
                # 文件修改时间晚于上次扫描，需要扫描
                changed_symbols.append(symbol)
            elif file_size != record.file_size:
                # 文件大小变化，需要扫描
                changed_symbols.append(symbol)

        self.logger.info(
            f"增量扫描检测: {len(all_symbols)}个品种中 {len(changed_symbols)}个需要扫描 "
            f"(减少{(1 - len(changed_symbols)/len(all_symbols))*100:.1f}%)"
        )

        return changed_symbols

    def mark_full_scan(self, all_symbols: List[str], interval: str, data_dir: Optional[str] = None):
        """标记全量扫描完成

        Args:
            all_symbols: 所有品种列表
            interval: 时间间隔
            data_dir: 数据目录（可选）
        """
        scan_time = datetime.now()

        # 更新所有品种的扫描记录
        if data_dir:
            data_path = Path(data_dir)
            for symbol in all_symbols:
                file_path = self._build_file_path(symbol, interval, data_path)
                if file_path.exists():
                    self.update_scan_record(symbol, interval, str(file_path))

        # 更新元数据
        if self._metadata is None:
            self._metadata = ScanMetadata(
                last_full_scan=scan_time, total_symbols=len(all_symbols), scan_count=1
            )
        else:
            self._metadata.last_full_scan = scan_time
            self._metadata.total_symbols = len(all_symbols)
            self._metadata.scan_count += 1

        # 保存缓存
        self._save_cache()

        self.logger.info(f"✅ 全量扫描标记完成: {len(all_symbols)}个品种, 时间: {scan_time}")

    def update_scan_record(self, symbol: str, interval: str, file_path: str):
        """更新单个品种的扫描记录

        Args:
            symbol: 品种代码
            interval: 时间间隔
            file_path: 文件路径
        """
        key = f"{symbol}_{interval}"
        path = Path(file_path)

        if not path.exists():
            self.logger.warning(f"文件不存在，无法更新扫描记录: {file_path}")
            return

        # 获取文件状态
        file_stat = os.stat(path)

        # 创建或更新记录
        self._records[key] = ScanRecord(
            symbol=symbol,
            interval=interval,
            last_scan_time=datetime.now(),
            file_mtime=file_stat.st_mtime,
            file_size=file_stat.st_size,
        )

    def clear_records(self):
        """清除所有扫描记录（强制下次全量扫描）"""
        self._records.clear()
        self._metadata = None
        self._save_cache()
        self.logger.info("✅ 扫描记录已清除")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_records": len(self._records),
            "metadata": asdict(self._metadata) if self._metadata else None,
            "cache_file": str(self.records_file),
        }

    # ==================== 辅助方法 ====================

    def _build_file_path(self, symbol: str, interval: str, data_dir: Path) -> Path:
        """构建文件路径

        根据实际存储结构构建文件路径。

        Args:
            symbol: 品种代码
            interval: 时间间隔
            data_dir: 数据目录

        Returns:
            文件路径
        """
        # 示例：data_dir/interval/symbol.parquet
        # 根据实际存储结构调整
        return data_dir / interval / f"{symbol}.parquet"

    def _load_cache(self):
        """加载缓存"""
        # 加载扫描记录
        if self.records_file.exists():
            try:
                with open(self.records_file, "r", encoding="utf-8") as f:
                    records_data = json.load(f)

                for key, data in records_data.items():
                    # 反序列化datetime
                    data["last_scan_time"] = datetime.fromisoformat(data["last_scan_time"])
                    self._records[key] = ScanRecord(**data)

                self.logger.info(f"✅ 加载扫描记录: {len(self._records)}条")
            except Exception as e:
                self.logger.warning(f"加载扫描记录失败: {e}")

        # 加载元数据
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    metadata_data = json.load(f)

                # 反序列化datetime
                metadata_data["last_full_scan"] = datetime.fromisoformat(
                    metadata_data["last_full_scan"]
                )
                if metadata_data.get("last_incremental_scan"):
                    metadata_data["last_incremental_scan"] = datetime.fromisoformat(
                        metadata_data["last_incremental_scan"]
                    )

                self._metadata = ScanMetadata(**metadata_data)
                self.logger.info(f"✅ 加载扫描元数据: {self._metadata}")
            except Exception as e:
                self.logger.warning(f"加载扫描元数据失败: {e}")

    def _save_cache(self):
        """保存缓存"""
        # 保存扫描记录
        try:
            records_data = {}
            for key, record in self._records.items():
                data = asdict(record)
                # 序列化datetime
                data["last_scan_time"] = data["last_scan_time"].isoformat()
                records_data[key] = data

            with open(self.records_file, "w", encoding="utf-8") as f:
                json.dump(records_data, f, ensure_ascii=False, indent=2)

            self.logger.debug(f"✅ 保存扫描记录: {len(self._records)}条")
        except Exception as e:
            self.logger.error(f"保存扫描记录失败: {e}")

        # 保存元数据
        if self._metadata:
            try:
                metadata_data = asdict(self._metadata)
                # 序列化datetime
                metadata_data["last_full_scan"] = metadata_data["last_full_scan"].isoformat()
                if metadata_data.get("last_incremental_scan"):
                    metadata_data["last_incremental_scan"] = metadata_data[
                        "last_incremental_scan"
                    ].isoformat()

                with open(self.metadata_file, "w", encoding="utf-8") as f:
                    json.dump(metadata_data, f, ensure_ascii=False, indent=2)

                self.logger.debug(f"✅ 保存扫描元数据")
            except Exception as e:
                self.logger.error(f"保存扫描元数据失败: {e}")


# ==================== 便捷函数 ====================


def create_incremental_scan_manager(cache_dir: str = "./cache") -> IncrementalScanManager:
    """便捷函数：创建增量扫描管理器

    Args:
        cache_dir: 缓存目录

    Returns:
        IncrementalScanManager实例
    """
    return IncrementalScanManager(cache_dir=cache_dir)


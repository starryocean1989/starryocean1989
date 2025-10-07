# -*- coding: utf-8 -*-
"""
数据验证工具.

提供数据验证、格式检查和转换功能。
"""

import logging
import re
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """验证错误异常."""

    def __init__(
        self, message: str, field: Optional[str] = None, value: Optional[Any] = None
    ):
        """初始化验证错误."""
        super().__init__(message)
        self.message = message
        self.field = field
        self.value = value


class DataValidator:
    """数据验证器."""

    @staticmethod
    def validate_required(value: Any, field_name: str) -> None:
        """验证必需字段."""
        if value is None or value == "":
            raise ValidationError(f"{field_name}不能为空", field_name, value)

    @staticmethod
    def validate_string(
        value: Any,
        field_name: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        pattern: Optional[str] = None,
        required: bool = True,
    ) -> str:
        """验证字符串."""
        if not required and (value is None or value == ""):
            return ""

        DataValidator.validate_required(value, field_name)

        if not isinstance(value, str):
            raise ValidationError(f"{field_name}必须是字符串", field_name, value)

        if min_length is not None and len(value) < min_length:
            raise ValidationError(
                f"{field_name}长度不能少于{min_length}个字符", field_name, value
            )

        if max_length is not None and len(value) > max_length:
            raise ValidationError(
                f"{field_name}长度不能超过{max_length}个字符", field_name, value
            )

        if pattern and not re.match(pattern, value):
            raise ValidationError(f"{field_name}格式不正确", field_name, value)

        return value

    @staticmethod
    def validate_integer(
        value: Any,
        field_name: str,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
        required: bool = True,
    ) -> int:
        """验证整数."""
        if not required and value is None:
            return 0

        DataValidator.validate_required(value, field_name)

        try:
            int_value = int(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name}必须是整数", field_name, value)

        if min_value is not None and int_value < min_value:
            raise ValidationError(f"{field_name}不能小于{min_value}", field_name, value)

        if max_value is not None and int_value > max_value:
            raise ValidationError(f"{field_name}不能大于{max_value}", field_name, value)

        return int_value

    @staticmethod
    def validate_float(
        value: Any,
        field_name: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        required: bool = True,
    ) -> float:
        """验证浮点数."""
        if not required and value is None:
            return 0.0

        DataValidator.validate_required(value, field_name)

        try:
            float_value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name}必须是数字", field_name, value)

        if min_value is not None and float_value < min_value:
            raise ValidationError(f"{field_name}不能小于{min_value}", field_name, value)

        if max_value is not None and float_value > max_value:
            raise ValidationError(f"{field_name}不能大于{max_value}", field_name, value)

        return float_value

    @staticmethod
    def validate_decimal(
        value: Any,
        field_name: str,
        min_value: Optional[Decimal] = None,
        max_value: Optional[Decimal] = None,
        precision: Optional[int] = None,
        required: bool = True,
    ) -> Decimal:
        """验证Decimal."""
        if not required and value is None:
            return Decimal("0")

        DataValidator.validate_required(value, field_name)

        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(f"{field_name}必须是有效数字", field_name, value)

        if min_value is not None and decimal_value < min_value:
            raise ValidationError(f"{field_name}不能小于{min_value}", field_name, value)

        if max_value is not None and decimal_value > max_value:
            raise ValidationError(f"{field_name}不能大于{max_value}", field_name, value)

        if precision is not None:
            # 检查小数位数
            exponent = decimal_value.as_tuple().exponent
            # 处理exponent可能为字符串的情况（如'n', 'N', 'F'）
            if isinstance(exponent, int) and exponent < -precision:
                raise ValidationError(
                    f"{field_name}小数位数不能超过{precision}位", field_name, value
                )

        return decimal_value

    @staticmethod
    def validate_boolean(value: Any, field_name: str, required: bool = True) -> bool:
        """验证布尔值."""
        if not required and value is None:
            return False

        DataValidator.validate_required(value, field_name)

        if isinstance(value, bool):
            return value
        elif isinstance(value, str):
            if value.lower() in ("true", "1", "yes", "on"):
                return True
            elif value.lower() in ("false", "0", "no", "off"):
                return False
            else:
                raise ValidationError(f"{field_name}必须是布尔值", field_name, value)
        else:
            raise ValidationError(f"{field_name}必须是布尔值", field_name, value)

    @staticmethod
    def validate_datetime(
        value: Any,
        field_name: str,
        format_str: Optional[str] = None,
        required: bool = True,
    ) -> datetime:
        """验证日期时间."""
        if not required and value is None:
            return datetime.now()

        DataValidator.validate_required(value, field_name)

        if isinstance(value, datetime):
            return value
        elif isinstance(value, str):
            if format_str:
                try:
                    return datetime.strptime(value, format_str)
                except ValueError:
                    raise ValidationError(
                        f"{field_name}格式不正确，应为{format_str}", field_name, value
                    )
            else:
                # 尝试常见格式
                formats = [
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y/%m/%d",
                ]

                for fmt in formats:
                    try:
                        return datetime.strptime(value, fmt)
                    except ValueError:
                        continue

                raise ValidationError(f"{field_name}日期格式不正确", field_name, value)
        else:
            raise ValidationError(f"{field_name}必须是日期时间", field_name, value)

    @staticmethod
    def validate_date(value: Any, field_name: str, required: bool = True) -> date:
        """验证日期."""
        if not required and value is None:
            return date.today()

        DataValidator.validate_required(value, field_name)

        if isinstance(value, date):
            return value
        elif isinstance(value, datetime):
            return value.date()
        elif isinstance(value, str):
            formats = ["%Y-%m-%d", "%Y/%m/%d"]

            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue

            raise ValidationError(f"{field_name}日期格式不正确", field_name, value)
        else:
            raise ValidationError(f"{field_name}必须是日期", field_name, value)

    @staticmethod
    def validate_choice(
        value: Any, field_name: str, choices: List[Any], required: bool = True
    ) -> Any:
        """验证选择值."""
        if not required and value is None:
            return None

        DataValidator.validate_required(value, field_name)

        if value not in choices:
            raise ValidationError(
                f"{field_name}必须是以下值之一: {', '.join(map(str, choices))}",
                field_name,
                value,
            )

        return value

    @staticmethod
    def validate_list(
        value: Any,
        field_name: str,
        item_type: Optional[type] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        required: bool = True,
    ) -> List[Any]:
        """验证列表."""
        if not required and value is None:
            return []

        DataValidator.validate_required(value, field_name)

        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"{field_name}必须是列表", field_name, value)

        list_value = list(value)

        if min_length is not None and len(list_value) < min_length:
            raise ValidationError(
                f"{field_name}长度不能少于{min_length}", field_name, value
            )

        if max_length is not None and len(list_value) > max_length:
            raise ValidationError(
                f"{field_name}长度不能超过{max_length}", field_name, value
            )

        if item_type:
            for i, item in enumerate(list_value):
                if not isinstance(item, item_type):
                    raise ValidationError(
                        f"{field_name}[{i}]必须是{item_type.__name__}类型",
                        f"{field_name}[{i}]",
                        item,
                    )

        return list_value

    @staticmethod
    def validate_dict(
        value: Any,
        field_name: str,
        required_keys: Optional[List[str]] = None,
        required: bool = True,
    ) -> Dict[str, Any]:
        """验证字典."""
        if not required and value is None:
            return {}

        DataValidator.validate_required(value, field_name)

        if not isinstance(value, dict):
            raise ValidationError(f"{field_name}必须是字典", field_name, value)

        if required_keys:
            for key in required_keys:
                if key not in value:
                    raise ValidationError(
                        f"{field_name}缺少必需字段: {key}", f"{field_name}.{key}", None
                    )

        return value


class SymbolValidator:
    """品种代码验证器."""

    @staticmethod
    def validate_symbol(symbol: str) -> str:
        """验证品种代码."""
        if not symbol:
            raise ValidationError("品种代码不能为空", "symbol", symbol)

        # 品种代码应该是字母数字组合，长度在2-20之间
        if not re.match(r"^[A-Za-z0-9]{2,20}$", symbol):
            raise ValidationError(
                "品种代码格式不正确，应为2-20位字母数字组合", "symbol", symbol
            )

        return symbol.upper()

    @staticmethod
    def validate_exchange(exchange: str) -> str:
        """验证交易所代码."""
        valid_exchanges = [
            "SSE",
            "SZSE",
            "SHFE",
            "DCE",
            "CZCE",
            "INE",
            "CFFEX",
            "GFEX",
            "HKEX",
            "NASDAQ",
            "NYSE",
        ]

        exchange_upper = exchange.upper()
        if exchange_upper not in valid_exchanges:
            raise ValidationError(
                f"交易所代码无效，应为: {', '.join(valid_exchanges)}",
                "exchange",
                exchange,
            )

        return exchange_upper


class TimeValidator:
    """时间验证器."""

    @staticmethod
    def validate_trading_time(dt: datetime) -> bool:
        """验证是否为交易时间."""
        # 简单的时间验证，实际应该根据具体市场规则
        weekday = dt.weekday()
        hour = dt.hour
        minute = dt.minute

        # 工作日 9:00-15:00
        if weekday < 5:  # 周一到周五
            if 9 <= hour <= 15:
                return True

        return False

    @staticmethod
    def validate_time_range(
        start_time: datetime, end_time: datetime, max_days: int = 365
    ) -> None:
        """验证时间范围."""
        if start_time >= end_time:
            raise ValidationError("开始时间必须早于结束时间")

        days_diff = (end_time - start_time).days
        if days_diff > max_days:
            raise ValidationError(f"时间范围不能超过{max_days}天")


class ValidationResult:
    """验证结果."""

    def __init__(self):
        """初始化验证结果."""
        self.is_valid = True
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[str] = []

    def add_error(self, field: str, message: str, value: Any = None) -> None:
        """添加错误."""
        self.is_valid = False
        self.errors.append({"field": field, "message": message, "value": value})

    def add_warning(self, message: str) -> None:
        """添加警告."""
        self.warnings.append(message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# 导出公共接口
__all__ = [
    "ValidationError",
    "DataValidator",
    "SymbolValidator",
    "TimeValidator",
    "ValidationResult",
]

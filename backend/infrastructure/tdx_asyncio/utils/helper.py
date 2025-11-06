# -*- coding: utf-8 -*-
# cython: language_level=3
import struct
import threading
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple, List

# 🚀 性能优化：导入native_compute用于批量get_price解析
try:
    from backend.infrastructure.native.native_compute import (
        batch_get_price as _batch_get_price_native,
    )

    BATCH_GET_PRICE_AVAILABLE = True
except ImportError:
    BATCH_GET_PRICE_AVAILABLE = False
    _batch_get_price_native = None

from ..network.constants import SECURITY_COEFFICIENT, TDXParams
from .logger import logger

# 队列跳过统计（进程级别，背压控制）
_queue_skip_stats: Dict[str, Dict[str, int]] = {}
_queue_skip_lock = threading.Lock()

# 告警专用logger
logger_alert = logging.getLogger("tdx_asyncio.alert")


def get_price(data, pos):
    """
    分析了一下，貌似是类似utf-8的编码方式保存有符号数字

    :param data:
    :param pos:
    :return:
    """

    pos_byte = 6

    bdata = index_bytes(data, pos)
    int_data = bdata & 0x3F

    if bdata & 0x40:
        sign = True
    else:
        sign = False

    if bdata & 0x80:
        while True:
            pos += 1

            bdata = index_bytes(data, pos)

            int_data += (bdata & 0x7F) << pos_byte
            pos_byte += 7

            if bdata & 0x80:
                pass
            else:
                break

    pos += 1

    if sign:
        int_data = -int_data

    return int_data, pos


def batch_get_price(data: bytes, start_pos: int, count: int) -> Tuple[List[int], int]:
    """
    批量解析get_price（使用native优化）

    :param data: 字节数据
    :param start_pos: 起始位置
    :param count: 要解析的数量
    :return: (解析后的数字列表, 最终位置)
    """
    if not BATCH_GET_PRICE_AVAILABLE or _batch_get_price_native is None:
        # 降级到Python实现
        values = []
        pos = start_pos
        for _ in range(count):
            value, pos = get_price(data, pos)
            values.append(value)
        return values, pos

    try:
        values_list, positions_list = _batch_get_price_native(data, start_pos, count)
        # 转换为Python列表
        values = [int(v) for v in values_list]
        final_pos = int(positions_list[-1]) if len(positions_list) > 0 else start_pos
        return values, final_pos
    except Exception as e:
        # 降级到Python实现
        logger.debug(f"batch_get_price失败，降级到Python实现: {e}")
        values = []
        pos = start_pos
        for _ in range(count):
            value, pos = get_price(data, pos)
            values.append(value)
        return values, pos


def get_volume(vol):
    """
    获取交易量
    :param vol:
    :return:
    """
    logpoint = vol >> (8 * 3)

    hleax = (vol >> (8 * 2)) & 0xFF  # [2]
    lheax = (vol >> 8) & 0xFF  # [1]
    lleax = vol & 0xFF  # [0]

    dw_ecx = logpoint * 2 - 0x7F
    dw_edx = logpoint * 2 - 0x86

    dw_esi = logpoint * 2 - 0x8E
    dw_eax = logpoint * 2 - 0x96

    if dw_ecx < 0:
        tmp_eax = -dw_ecx
    else:
        tmp_eax = dw_ecx

    dbl_xmm6 = pow(2.0, tmp_eax)

    if dw_ecx < 0:
        dbl_xmm6 = 1.0 / dbl_xmm6

    if hleax > 0x80:
        dwtmpeax = dw_edx + 1
        tmpdbl_xmm3 = pow(2.0, dwtmpeax)

        dbl_xmm0 = pow(2.0, dw_edx) * 128.0
        dbl_xmm0 += (hleax & 0x7F) * tmpdbl_xmm3
        dbl_xmm4 = dbl_xmm0

    else:
        if dw_edx >= 0:
            dbl_xmm0 = pow(2.0, dw_edx) * hleax
        else:
            dbl_xmm0 = (1 / pow(2.0, dw_edx)) * hleax

        dbl_xmm4 = dbl_xmm0

    dbl_xmm3 = pow(2.0, dw_esi) * lheax
    dbl_xmm1 = pow(2.0, dw_eax) * lleax

    if hleax & 0x80:
        dbl_xmm3 *= 2.0
        dbl_xmm1 *= 2.0

    dbl_ret = dbl_xmm6 + dbl_xmm4 + dbl_xmm3 + dbl_xmm1

    return dbl_ret


def get_datetime(category, buffer, pos):
    """
    获取日期时间
    :param category:
    :param buffer:
    :param pos:
    :return:
    """
    minute = 0
    hour = 15

    if category < 4 or category == 7 or category == 8:
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        zip_day, minutes = struct.unpack_from("<HH", buffer, pos)

        month = int((zip_day % 2048) / 100)
        year = (zip_day >> 11) + 2004
        day = (zip_day % 2048) % 100

        minute = minutes % 60
        hour = int(minutes / 60)
    else:
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (zip_day,) = struct.unpack_from("<I", buffer, pos)

        month = int((zip_day % 10000) / 100)
        year = int(zip_day / 10000)
        day = zip_day % 100

    pos += 4

    return year, month, day, hour, minute, pos


def get_time(buffer, pos):
    """
    获取时间
    :param buffer:
    :param pos:
    :return:
    """
    # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
    (minutes,) = struct.unpack_from("<H", buffer, pos)

    hour = int(minutes / 60)
    minute = minutes % 60

    pos += 2

    return hour, minute, pos


def index_bytes(data, pos):
    """
    索引比特
    :param data:
    :param pos:
    :return:
    """
    return data[pos]


def get_security_coefficient(market=None, code=None):
    try:
        security_type = get_security_type(market=market, code=code)
        coefficient = SECURITY_COEFFICIENT[security_type]
        return coefficient[0]
    except NotImplementedError:
        logger.error("NotImplementedError", extra={"log_type": "SYSTEM"})
        return 0.01


def get_market_from_code(symbol: str, strict: bool = False) -> int:
    """
    根据品种代码获取市场代码（增强版）

    Args:
        symbol: 品种代码（如 '000001', '600000', '430001'）
        strict: 严格模式（True=抛出异常，False=返回默认值）

    Returns:
        市场代码: 0=深圳, 1=上海, 2=北京

    Raises:
        ValueError: 当 strict=True 且无法识别市场时

    Examples:
        >>> get_market_from_code('000001')  # 深圳
        0
        >>> get_market_from_code('600000')  # 上海
        1
        >>> get_market_from_code('430001')  # 北京
        2
    """
    symbol = str(symbol).strip()

    if not symbol:
        if strict:
            raise ValueError("品种代码不能为空")
        return 1  # 默认上海

    # 上海市场：6开头（主板+科创板）
    if symbol.startswith("6"):
        return 1

    # 深圳市场：0开头（主板）、3开头（创业板）
    elif symbol.startswith(("0", "3")):
        return 0

    # 北京市场（北交所）：4开头（新三板精选层）、8开头（创新层）、9开头（基础层）
    elif symbol.startswith(("4", "8", "9")):
        return 2

    # 未知市场
    else:
        if strict:
            raise ValueError(f"无法识别品种代码 '{symbol}' 的市场")
        logger.debug(f"无法识别品种代码 '{symbol}' 的市场，返回默认值（上海）")
        return 1  # 默认上海


def get_security_type(market, code):
    """
    获取股票类型, A股, B股, 指数等

    :param market: 市场
    :param code: 代码
    :return:
    """

    code = str(code)
    code_head = str(code)[:2]

    if market in ["SZ", "sz", 0]:
        if code_head in ["00", "30"]:
            return "SZ_A_STOCK"

        if code_head in ["20"]:
            return "SZ_B_STOCK"

        if code_head in ["39"]:
            return "SZ_INDEX"

        if code_head in ["15", "16"]:
            return "SZ_FUND"

        if code_head in ["10", "11", "12", "13", "14"]:
            return "SZ_BOND"

    if market in ["SH", "sh", 1]:
        if code_head in ["60", "68"]:  # 688XXX科创板
            return "SH_A_STOCK"

        if code_head in ["90"]:
            return "SH_B_STOCK"

        if code_head in ["00", "88", "99"]:
            return "SH_INDEX"

        if code_head in ["50", "51"]:
            return "SH_FUND"

        if code_head in ["01", "10", "11", "12", "13", "14", "20"]:
            return "SH_BOND"

    logger.debug("Unknown security exchange !")
    raise NotImplementedError


def dump(buf):
    from pprint import pprint

    try:
        from hexdump import hexdump

        pprint(hexdump(buf))
    except ImportError:
        pprint(buf)


def time_frame(current_time=None):
    """
    判断时间是否在交易时间段内
    :param current_time: 要检查的时间, 如果空则默认当前时间
    :return: 在交易时间段内返回 True， 否则返回 False
    """
    current_time = current_time or datetime.now()

    start_time = datetime.strptime(str(current_time.date()) + "9:30", "%Y-%m-%d%H:%M")
    end_time = datetime.strptime(str(current_time.date()) + "11:30", "%Y-%m-%d%H:%M")

    if start_time < current_time < end_time:
        return True

    start_time = datetime.strptime(str(current_time.date()) + "13:00", "%Y-%m-%d%H:%M")
    end_time = datetime.strptime(str(current_time.date()) + "15:00", "%Y-%m-%d%H:%M")

    if start_time < current_time < end_time:
        return True

    return False


def interval_to_category(interval: str) -> int:
    """
    将周期字符串转换为TDX category代码

    Args:
        interval: 周期字符串，如 "1d", "5m", "1m" 等

    Returns:
        TDX category代码:
        - 9: 日K线 (1d)
        - 0: 5分钟线 (5m)
        - 8: 1分钟线 (1m)
        - 4: 日K线 (兼容，等同于9)

    Raises:
        ValueError: 当interval不支持时

    Examples:
        >>> interval_to_category("1d")
        9
        >>> interval_to_category("5m")
        0
        >>> interval_to_category("1m")
        8
    """
    interval = str(interval).strip().lower()

    # 日K线
    if interval in ["1d", "day", "daily", "d"]:
        return 9

    # 5分钟线
    if interval in ["5m", "5min", "5minute"]:
        return 0

    # 1分钟线
    if interval in ["1m", "1min", "1minute", "min", "minute"]:
        return 8

    # 兼容旧格式
    if interval == "4":
        return 4

    raise ValueError(f"不支持的周期: {interval}")


def category_to_interval(category: int) -> str:
    """
    将TDX category代码转换为周期字符串

    Args:
        category: TDX category代码

    Returns:
        周期字符串:
        - 9, 4 -> "1d" (日K线)
        - 0 -> "5m" (5分钟线)
        - 8 -> "1m" (1分钟线)

    Raises:
        ValueError: 当category不支持时

    Examples:
        >>> category_to_interval(9)
        '1d'
        >>> category_to_interval(0)
        '5m'
        >>> category_to_interval(8)
        '1m'
    """
    # 日K线
    if category in [4, 9]:
        return "1d"

    # 5分钟线
    if category == 0:
        return "5m"

    # 1分钟线
    if category == 8:
        return "1m"

    raise ValueError(f"不支持的category: {category}")


# ==============================================================================
# 队列操作辅助函数
# ==============================================================================


def safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）

    Args:
        q: 队列对象
        item: 要入队的数据
        timeout: 超时时间（秒）
        queue_name: 队列名称（用于日志）
        worker_id: Worker ID（用于统计）

    Returns:
        bool: True=入队成功, False=入队失败（队列满）
    """
    try:
        q.put(item, timeout=timeout)
        return True
    except Exception as e:
        error_type = type(e).__name__
        stats_key = f"{queue_name}_{worker_id}" if worker_id is not None else queue_name
        with _queue_skip_lock:
            if stats_key not in _queue_skip_stats:
                _queue_skip_stats[stats_key] = {"skip_count": 0, "last_warning": 0}
            _queue_skip_stats[stats_key]["skip_count"] += 1
            skip_count = _queue_skip_stats[stats_key]["skip_count"]
            if skip_count % 10 == 1 or skip_count <= 3:
                logger.warning(
                    f"⚠️ 队列入队失败（{error_type}）: 队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次, 超时={timeout}s",
                    extra={"log_type": "SYSTEM"},
                )
            if skip_count == 100 or skip_count % 500 == 0:
                logger_alert.error(
                    f"🔥 队列严重积压告警: 队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次，消费者可能过慢！",
                    extra={"log_type": "ALERT"},
                )
        return False


def get_queue_skip_stats() -> Dict[str, Dict[str, int]]:
    """获取队列跳过统计（用于监控）

    Returns:
        队列跳过统计字典
    """
    with _queue_skip_lock:
        return dict(_queue_skip_stats)


def reset_queue_skip_stats():
    """重置队列跳过统计"""
    with _queue_skip_lock:
        _queue_skip_stats.clear()


# ==============================================================================
# 子进程日志配置辅助函数
# ==============================================================================


def configure_subprocess_logging(
    worker_id: int, task_type: str = "worker", scenario: Optional[str] = None
):
    """配置子进程日志系统，接入LogHub统一路由

    Args:
        worker_id: 子进程ID
        task_type: 任务类型（kline/ipo/finance/server_test等）
        scenario: 场景标记（用于日志路由，如data_download、manual_data_scan等）

    Returns:
        配置好的logger实例
    """
    try:
        from backend.infrastructure.system_vnpy.logging_system import get_logging_hub

        hub = get_logging_hub()
        root_logger = logging.getLogger()

        # 清理旧的handler
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        # 添加LogHub
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)

        # 创建子进程专用的logger
        logger_name = f"subprocess.{task_type}.{worker_id}"
        subprocess_logger = logging.getLogger(logger_name)
        subprocess_logger.propagate = True

        # 记录子进程日志接入信息（使用场景标记）
        log_extra = {"log_type": "SYSTEM"}
        if scenario:
            log_extra["scenario"] = scenario

        subprocess_logger.info(
            f"✅ 子进程 {worker_id} (类型: {task_type}) 日志系统已接入LogHub", extra=log_extra
        )
        subprocess_logger.debug(
            f"[SUBPROCESS-{worker_id}] 子进程日志配置完成: task_type={task_type}, scenario={scenario}",
            extra=log_extra,
        )

        return subprocess_logger
    except ImportError as e:
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.warning(
            f"⚠️ 子进程 {worker_id} LogHub导入失败，使用降级日志: {e}",
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        return fallback_logger
    except Exception as e:
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.error(
            f"❌ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}",
            exc_info=True,
            extra={"log_type": "SYSTEM", "scenario": scenario},
        )
        return fallback_logger


# 向后兼容：保留带下划线的函数名
_safe_put_queue = safe_put_queue
_configure_subprocess_logging = configure_subprocess_logging
_get_queue_skip_stats = get_queue_skip_stats
_reset_queue_skip_stats = reset_queue_skip_stats

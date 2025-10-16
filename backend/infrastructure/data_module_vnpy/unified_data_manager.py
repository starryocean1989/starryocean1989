# -*- coding: utf-8 -*-
"""统一数据管理器."""

from __future__ import annotations

import logging
from datetime import date, datetime
from threading import Lock
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple, TYPE_CHECKING, Union, cast

import pandas as pd
from pandas import Timestamp

from vnpy.trader.constant import Exchange
from vnpy.trader.object import SubscribeRequest

from .config import config_manager

if TYPE_CHECKING:  # pragma: no cover
    from .core import ChinaStockEngine
    from .preload_service import PreloadService


class UnifiedDataManager:
    """为上层模块提供统一的数据访问与订阅管理入口."""

    _VIRTUAL_MODULES = {"backtest", "replay", "virtual_gateway"}

    def __init__(
        self,
        engine: "ChinaStockEngine",
        *,
        preload_service: Optional["PreloadService"] = None,
    ) -> None:
        self.engine = engine
        self.logger = logging.getLogger(__name__)
        self.preload_service = preload_service
        self._module_subscriptions: Dict[str, Set[str]] = {}
        self._module_gateways: Dict[str, str] = {}
        self._gateway_symbols: Dict[str, Set[str]] = {"polling": set(), "virtual": set()}
        self._lock = Lock()

    # ------------------------------------------------------------------
    def get_kline_data(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
        use_preload: bool = True,
    ) -> Optional[pd.DataFrame]:
        frames = []

        if use_preload and self.preload_service:
            cached = self.preload_service.get_cached_dataframe(symbol, interval)
            if cached is not None and not cached.empty:
                frames.append(cached)

        storage_frame = self.engine.storage_manager.query_kline(symbol, interval, start_date, end_date)
        if storage_frame is not None and not storage_frame.empty:
            frames.append(storage_frame)

        recording_frame = self._query_recording_layer(symbol, interval)
        if recording_frame is not None and not recording_frame.empty:
            frames.append(recording_frame)

        realtime_frame = self._query_realtime_layer(symbol, interval)
        if realtime_frame is not None and not realtime_frame.empty:
            frames.append(realtime_frame)

        merged = self._merge_frames(frames, interval)

        if check_gaps and (merged is None or merged.empty):
            if config_manager.is_unified_manager_auto_download_enabled():
                self._trigger_backfill(symbol, start_date)
                storage_frame = self.engine.storage_manager.query_kline(
                    symbol, interval, start_date, end_date
                )
                merged = self._merge_frames([storage_frame] if storage_frame is not None else [], interval)

        if merged is None or merged.empty:
            return None

        trimmed = self._trim_range(merged, start_date, end_date)
        if check_gaps and config_manager.is_unified_manager_auto_download_enabled():
            self._enqueue_preload_if_needed(symbol, interval, trimmed)
        return trimmed

    # ------------------------------------------------------------------
    def get_multi_kline_data(
        self,
        symbols: Sequence[str],
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
    ) -> Dict[str, Optional[pd.DataFrame]]:
        result: Dict[str, Optional[pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = self.get_kline_data(
                symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )
        return result

    # ------------------------------------------------------------------
    def query_unified(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Union[pd.DataFrame, Dict]]:
        """
        统一查询接口（从core.py迁移）

        自动判断单品种还是多品种查询，返回适当的格式。

        Args:
            symbol: 单品种代码（可选）
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            **kwargs: 其他参数
                - symbols: 多品种列表（与symbol互斥）
                - frequency: 周期别名（优先级低于interval）
                - check_gaps: 是否检查缺口（默认True）

        Returns:
            单品种：DataFrame 或 None
            多品种：Dict {"success": bool, "data": {symbol: []}, "interval": str, "message": str}
        """
        symbols_param = kwargs.get("symbols")
        frequency = kwargs.get("frequency") or interval
        check_gaps = kwargs.get("check_gaps", True)

        # 多品种查询路径
        if symbols_param is not None:
            symbols_list = (
                [symbols_param] if isinstance(symbols_param, str) else list(symbols_param)
            )
            if not symbols_list:
                return {"success": True, "data": {}, "interval": frequency, "message": None}

            # 调用多品种查询
            datasets = self.get_multi_kline_data(
                symbols_list,
                interval=frequency,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            # 转换为字典格式
            payload = {
                sym: (df.to_dict("records") if df is not None else [])
                for sym, df in datasets.items()
            }

            success = any(payload.values())
            return {
                "success": success,
                "data": payload,
                "interval": frequency,
                "message": None if success else "未查询到数据",
            }

        # 单品种查询路径
        target_symbol = symbol or kwargs.get("symbols")
        if isinstance(target_symbol, (list, tuple)):
            target_symbol = target_symbol[0] if target_symbol else None
        if target_symbol is None:
            return None

        try:
            data = self.get_kline_data(
                target_symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            if data is not None and hasattr(data, "__len__"):
                self.logger.info(
                    "查询数据成功: %s %s, %d 条记录", target_symbol, interval, len(data)
                )
            else:
                self.logger.warning("未找到数据: %s %s", target_symbol, interval)

            return data

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", target_symbol, interval, e)
            return None

    # ------------------------------------------------------------------
    def subscribe(self, module: str, symbols: Iterable[str]) -> bool:
        gateway_name = self._resolve_gateway(module)
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            self.logger.warning("网关未初始化: %s", gateway_name)
            return False

        normalized = {s.strip() for s in symbols if s.strip()}
        if not normalized:
            return True

        with self._lock:
            module_symbols = self._module_subscriptions.get(module, set())
            new_symbols = normalized - module_symbols
            if not new_symbols:
                return True

            module_symbols.update(new_symbols)
            self._module_subscriptions[module] = module_symbols
            self._module_gateways[module] = gateway_name

            attach_set = self._gateway_symbols.setdefault(gateway_name, set())
            for symbol in sorted(new_symbols):
                if symbol in attach_set:
                    continue
                req = self._build_subscribe_request(symbol)
                if req is None:
                    continue
                try:
                    gateway.subscribe(req)
                    attach_set.add(symbol)
                except Exception as exc:  # pragma: no cover
                    self.logger.error("订阅 %s 失败: %s", symbol, exc, exc_info=True)
            return True

    # ------------------------------------------------------------------
    def unsubscribe(self, module: str, symbols: Optional[Iterable[str]] = None) -> None:
        with self._lock:
            if module not in self._module_subscriptions:
                return

            gateway_name = self._module_gateways.get(module, "polling")
            module_symbols = self._module_subscriptions[module]

            if symbols is None:
                removed = set(module_symbols)
                module_symbols.clear()
            else:
                targets = {s.strip() for s in symbols if s.strip()}
                removed = module_symbols & targets
                module_symbols.difference_update(targets)

            if not module_symbols:
                self._module_subscriptions.pop(module, None)
                self._module_gateways.pop(module, None)

            self._reconcile_gateway(gateway_name, removed)

    # ------------------------------------------------------------------
    def refresh_preload(self, symbols: Iterable[str], priority: bool = False) -> None:
        if not self.preload_service:
            return
        for symbol in symbols:
            self.preload_service.enqueue(symbol, priority=priority)

    # ------------------------------------------------------------------
    def _reconcile_gateway(self, gateway_name: str, removed: Set[str]) -> None:
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            return

        # 计算仍需要的品种
        required: Set[str] = set()
        for module, module_symbols in self._module_subscriptions.items():
            if self._module_gateways.get(module, "polling") == gateway_name:
                required.update(module_symbols)

        attach_set = self._gateway_symbols.setdefault(gateway_name, set())
        obsolete = (attach_set - required) & removed if removed else attach_set - required
        for symbol in sorted(obsolete):
            req = self._build_subscribe_request(symbol)
            if req is None:
                continue
            try:
                gateway.unsubscribe(req)
            except Exception as exc:  # pragma: no cover
                self.logger.error("取消订阅 %s 失败: %s", symbol, exc, exc_info=True)
            attach_set.discard(symbol)

    # ------------------------------------------------------------------
    def _resolve_gateway(self, module: str) -> str:
        return "virtual" if module.lower() in self._VIRTUAL_MODULES else "polling"

    # ------------------------------------------------------------------
    def _get_gateway(self, gateway_name: str):
        if gateway_name == "virtual":
            gateway = self.engine.virtual_gateway
            if gateway is None:
                if not self.engine.start_virtual_gateway(
                    start_datetime=config_manager.get("chinastock.virtual_gateway.start_datetime", ""),
                    speed=config_manager.get_virtual_gateway_speed(),
                    symbols=None,
                ):
                    return None
                gateway = self.engine.virtual_gateway
            return gateway

        gateway = self.engine.polling_gateway
        if gateway is None:
            if not self.engine.start_polling_gateway():
                return None
            gateway = self.engine.polling_gateway
        return gateway

    # ------------------------------------------------------------------
    def _build_subscribe_request(self, symbol: str) -> Optional[SubscribeRequest]:
        exchange = self._infer_exchange(symbol)
        if exchange is None:
            self.logger.debug("无法识别交易所: %s", symbol)
            return None
        return SubscribeRequest(symbol=symbol, exchange=exchange)

    # ------------------------------------------------------------------
    def _infer_exchange(self, symbol: str) -> Optional[Exchange]:
        if not symbol:
            return None
        code = symbol.strip()
        if code.startswith("6") or code.startswith("9"):
            return Exchange.SSE
        if code.startswith("0") or code.startswith("3"):
            return Exchange.SZSE
        if code.startswith("8"):
            # 北交所暂映射为深交所对象，后续可扩展
            return Exchange.SZSE
        return None

    # ------------------------------------------------------------------
    def _merge_frames(self, frames: Iterable[Optional[pd.DataFrame]], interval: str) -> Optional[pd.DataFrame]:
        normalized = []
        for frame in frames:
            prepared = self._normalize_frame(frame)
            if prepared is not None and not prepared.empty:
                normalized.append(prepared)

        if not normalized:
            return None

        merged = pd.concat(normalized, ignore_index=True)  # type: ignore[arg-type]
        if "datetime" in merged.columns:
            merged["datetime"] = pd.to_datetime(merged["datetime"])
            merged = merged.drop_duplicates(subset="datetime", keep="last")
            merged = merged.sort_values("datetime")
        return merged.reset_index(drop=True)

    # ------------------------------------------------------------------
    def _normalize_frame(self, frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if frame is None or frame.empty:
            return None
        df = frame.copy()
        if "datetime" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                index_name = df.index.name or "index"
                df = df.reset_index().rename(columns={index_name: "datetime"})
            else:
                df = df.reset_index(drop=False)
                if "datetime" not in df.columns and df.columns.size > 0:
                    candidate = str(df.columns[0])
                    if candidate != "datetime":
                        df = df.rename(columns={candidate: "datetime"})
        if "datetime" not in df.columns:
            return df
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        return df

    # ------------------------------------------------------------------
    def _trim_range(
        self,
        frame: pd.DataFrame,
        start_date: Optional[Union[str, date]],
        end_date: Optional[Union[str, date]],
    ) -> pd.DataFrame:
        if "datetime" not in frame.columns:
            return frame

        series = frame["datetime"]
        start = self._to_timestamp(start_date) if start_date else None
        end = self._to_timestamp(end_date) if end_date else None

        mask = pd.Series([True] * len(frame))
        if start is not None:
            mask &= series >= start
        if end is not None:
            mask &= series <= end
        return frame.loc[mask].reset_index(drop=True)

    # ------------------------------------------------------------------
    def _to_timestamp(self, value: Union[str, date, datetime]) -> Timestamp:
        if isinstance(value, datetime):
            return cast(Timestamp, pd.Timestamp(value))
        if isinstance(value, date):
            return cast(Timestamp, pd.Timestamp(datetime.combine(value, datetime.min.time())))
        return cast(Timestamp, pd.to_datetime(value))

    # ------------------------------------------------------------------
    def _trigger_backfill(self, symbol: str, start_date: Optional[Union[str, date]]) -> None:
        if start_date is None:
            return
        if isinstance(start_date, str):
            start = start_date
        elif isinstance(start_date, datetime):
            start = start_date.strftime("%Y-%m-%d")
        else:
            start = start_date.strftime("%Y-%m-%d")
        self.logger.info("触发自动增量下载: %s 从 %s", symbol, start)
        try:
            self.engine.download_incremental(start)
        except Exception as exc:  # pragma: no cover
            self.logger.error("自动下载失败: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    def _enqueue_preload_if_needed(
        self,
        symbol: str,
        interval: str,
        frame: Optional[pd.DataFrame],
    ) -> None:
        if not self.preload_service:
            return
        if frame is None or frame.empty:
            self.preload_service.enqueue(symbol, intervals=[interval], priority=True)

    # ------------------------------------------------------------------
    def _query_recording_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        # 预留对录制数据的查询接口
        return None

    # ------------------------------------------------------------------
    def _query_realtime_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        # 预留实时数据接口
        return None

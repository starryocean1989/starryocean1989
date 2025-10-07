# -*- coding: utf-8 -*-
"""
行情看板路由模块.

提供行情看板相关的API端点，包括图表数据、指标计算、实时数据等功能。
"""

import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse

from backend.api.dependencies import get_vnpy_service
from backend.core.models import (
    ChartConfig,
    GapInfo,
    IndicatorConfig,
)
from backend.utils.response import ApiResponse as ResponseUtil
from backend.api.websocket_manager import get_websocket_manager

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["行情看板"])


@router.get("/charts/data", response_class=JSONResponse)
async def get_chart_data(
    symbol: str,
    exchange: str,
    start_date: Optional[datetime] = Query(None, description="开始日期"),  # noqa: B008
    end_date: Optional[datetime] = Query(None, description="结束日期"),  # noqa: B008
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    limit: int = Query(1000, ge=1, le=10000, description="数据条数限制"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取图表数据."""
    try:
        logger.info(
            "获取图表数据请求: symbol=%s, exchange=%s, frequency=%s, "
            "start_date=%s, end_date=%s",
            symbol,
            exchange,
            frequency,
            start_date,
            end_date,
        )

        # 从VnPy服务获取历史数据
        vnpy_data = vnpy_service.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            limit=limit,
        )

        # 转换为图表格式
        chart_data = []
        for bar_data in vnpy_data:
            chart_data.append(
                {
                    "timestamp": int(
                        bar_data.datetime.timestamp() * 1000
                    ),  # 前端需要毫秒时间戳
                    "datetime": bar_data.datetime.isoformat(),
                    "open": float(bar_data.open_price),
                    "high": float(bar_data.high_price),
                    "low": float(bar_data.low_price),
                    "close": float(bar_data.close_price),
                    "volume": int(bar_data.volume),
                    "turnover": float(bar_data.turnover),
                    "open_interest": int(bar_data.open_interest),
                }
            )

        logger.info("返回图表数据: %d 条记录", len(chart_data))
        return JSONResponse(
            content=ResponseUtil.success(data=chart_data, message="获取图表数据成功")
        )

    except Exception as e:
        logger.error("获取图表数据失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取图表数据失败: {str(e)}"),
        )


@router.get("/charts/config", response_class=JSONResponse)
async def get_chart_config(
    symbol: str,
    exchange: str,
    chart_id: str = Query("default", description="图表ID"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取图表配置."""
    try:
        logger.info("获取图表配置请求: symbol=%s, exchange=%s", symbol, exchange)

        # 获取品种信息
        symbol_info = vnpy_service.get_symbol_info(symbol, exchange)
        if not symbol_info:
            raise HTTPException(status_code=404, detail="品种不存在")

        # 构建图表配置
        chart_config = ChartConfig(
            chart_id=chart_id,
            symbol=symbol,
            exchange=exchange,
            chart_type="kline",
            period="1m",
            indicators=[],
            overlays=[],
            theme="dark",
            auto_refresh=True,
        )

        # 将品种详细信息也返回
        config_data = chart_config.dict()
        config_data["symbol_info"] = {
            "name": getattr(symbol_info, "name", symbol),
            "product": getattr(symbol_info, "product", ""),
            "size": getattr(symbol_info, "size", 1),
            "pricetick": getattr(symbol_info, "pricetick", 0.01),
            "min_volume": getattr(symbol_info, "min_volume", 1),
        }

        logger.info("返回图表配置: %s", symbol)
        return JSONResponse(
            content=ResponseUtil.success(data=config_data, message="获取图表配置成功")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取图表配置失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取图表配置失败: {str(e)}"),
        )


@router.post("/indicators/calculate", response_class=JSONResponse)
async def calculate_indicators(
    symbol: str,
    exchange: str,
    indicator_config: IndicatorConfig,
    start_date: Optional[datetime] = Query(None, description="开始日期"),  # noqa: B008
    end_date: Optional[datetime] = Query(None, description="结束日期"),  # noqa: B008
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    limit: int = Query(1000, ge=1, le=10000, description="数据条数限制"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """计算技术指标."""
    try:
        logger.info(
            "计算技术指标请求: symbol=%s, exchange=%s, indicator=%s",
            symbol,
            exchange,
            indicator_config.name,
        )

        # 获取历史数据
        vnpy_data = vnpy_service.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            limit=limit,
        )

        if not vnpy_data:
            raise HTTPException(status_code=404, detail="无历史数据")

        # 计算指标
        indicator_values = []
        for i, bar_data in enumerate(vnpy_data):
            # 简单的移动平均线计算示例
            if indicator_config.name == "MA":
                period = indicator_config.parameters.get("period", 20)
                if i >= period - 1:
                    ma_value = (
                        sum(
                            vnpy_data[j].close_price
                            for j in range(i - period + 1, i + 1)
                        )
                        / period
                    )
                    indicator_values.append(
                        {
                            "timestamp": int(bar_data.datetime.timestamp() * 1000),
                            "datetime": bar_data.datetime.isoformat(),
                            "value": float(ma_value),
                            "indicator_name": indicator_config.name,
                            "parameters": indicator_config.parameters,
                        }
                    )
            # 其他指标可以在这里添加

        logger.info("返回指标计算结果: %d 条记录", len(indicator_values))
        return JSONResponse(
            content=ResponseUtil.success(data=indicator_values, message="指标计算成功")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("计算技术指标失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"计算技术指标失败: {str(e)}"),
        )


@router.get("/indicators/list", response_class=JSONResponse)
async def get_indicator_list() -> JSONResponse:
    """获取支持的指标列表."""
    try:
        logger.info("获取指标列表请求")

        indicators = [
            {
                "name": "MA",
                "display_name": "移动平均线",
                "description": "简单移动平均线",
                "parameters": [
                    {
                        "name": "period",
                        "type": "int",
                        "default": 20,
                        "min": 1,
                        "max": 200,
                    }
                ],
                "outputs": ["value"],
            },
            {
                "name": "EMA",
                "display_name": "指数移动平均线",
                "description": "指数移动平均线",
                "parameters": [
                    {
                        "name": "period",
                        "type": "int",
                        "default": 12,
                        "min": 1,
                        "max": 200,
                    }
                ],
                "outputs": ["value"],
            },
            {
                "name": "MACD",
                "display_name": "MACD指标",
                "description": "移动平均收敛散度",
                "parameters": [
                    {
                        "name": "fast_period",
                        "type": "int",
                        "default": 12,
                        "min": 1,
                        "max": 100,
                    },
                    {
                        "name": "slow_period",
                        "type": "int",
                        "default": 26,
                        "min": 1,
                        "max": 100,
                    },
                    {
                        "name": "signal_period",
                        "type": "int",
                        "default": 9,
                        "min": 1,
                        "max": 50,
                    },
                ],
                "outputs": ["macd", "signal", "histogram"],
            },
            {
                "name": "RSI",
                "display_name": "RSI指标",
                "description": "相对强弱指数",
                "parameters": [
                    {
                        "name": "period",
                        "type": "int",
                        "default": 14,
                        "min": 1,
                        "max": 100,
                    }
                ],
                "outputs": ["value"],
            },
            {
                "name": "KDJ",
                "display_name": "KDJ指标",
                "description": "随机指标",
                "parameters": [
                    {
                        "name": "k_period",
                        "type": "int",
                        "default": 9,
                        "min": 1,
                        "max": 50,
                    },
                    {
                        "name": "d_period",
                        "type": "int",
                        "default": 3,
                        "min": 1,
                        "max": 20,
                    },
                    {
                        "name": "j_period",
                        "type": "int",
                        "default": 3,
                        "min": 1,
                        "max": 20,
                    },
                ],
                "outputs": ["k", "d", "j"],
            },
        ]

        logger.info("返回指标列表: %d 个指标", len(indicators))
        return JSONResponse(
            content=ResponseUtil.success(data=indicators, message="获取指标列表成功")
        )

    except Exception as e:
        logger.error("获取指标列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取指标列表失败: {str(e)}"),
        )


@router.get("/real-time/tick", response_class=JSONResponse)
async def get_real_time_tick(
    symbol: str,
    exchange: str,
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取实时Tick数据."""
    try:
        logger.info("获取实时Tick数据请求: symbol=%s, exchange=%s", symbol, exchange)

        # 从VnPy获取最新Tick数据
        tick_data = vnpy_service.get_latest_tick(symbol, exchange)

        if not tick_data:
            raise HTTPException(status_code=404, detail="无实时数据")

        tick_info = {
            "symbol": tick_data.symbol,
            "exchange": tick_data.exchange,
            "datetime": tick_data.datetime.isoformat(),
            "timestamp": int(tick_data.datetime.timestamp() * 1000),
            "last_price": float(tick_data.last_price),
            "volume": int(tick_data.volume),
            "turnover": float(tick_data.turnover),
            "open_interest": int(tick_data.open_interest),
            "bid_price_1": (
                float(tick_data.bid_price_1) if tick_data.bid_price_1 > 0 else None
            ),
            "bid_volume_1": (
                int(tick_data.bid_volume_1) if tick_data.bid_volume_1 > 0 else 0
            ),
            "ask_price_1": (
                float(tick_data.ask_price_1) if tick_data.ask_price_1 > 0 else None
            ),
            "ask_volume_1": (
                int(tick_data.ask_volume_1) if tick_data.ask_volume_1 > 0 else 0
            ),
        }

        logger.info("返回实时Tick数据: %s.%s", symbol, exchange)
        return JSONResponse(
            content=ResponseUtil.success(data=tick_info, message="获取实时Tick数据成功")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取实时Tick数据失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取实时Tick数据失败: {str(e)}"),
        )


@router.get("/real-time/bar", response_class=JSONResponse)
async def get_real_time_bar(
    symbol: str,
    exchange: str,
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取实时K线数据."""
    try:
        logger.info(
            "获取实时K线数据请求: symbol=%s, exchange=%s, frequency=%s",
            symbol,
            exchange,
            frequency,
        )

        # 从VnPy获取最新Bar数据
        bar_data = vnpy_service.get_latest_bar(symbol, exchange, frequency)

        if not bar_data:
            raise HTTPException(status_code=404, detail="无实时K线数据")

        bar_info = {
            "symbol": bar_data.symbol,
            "exchange": bar_data.exchange,
            "datetime": bar_data.datetime.isoformat(),
            "timestamp": int(bar_data.datetime.timestamp() * 1000),
            "open": float(bar_data.open_price),
            "high": float(bar_data.high_price),
            "low": float(bar_data.low_price),
            "close": float(bar_data.close_price),
            "volume": int(bar_data.volume),
            "turnover": float(bar_data.turnover),
            "open_interest": int(bar_data.open_interest),
            "frequency": frequency,
        }

        logger.info("返回实时K线数据: %s.%s", symbol, exchange)
        return JSONResponse(
            content=ResponseUtil.success(data=bar_info, message="获取实时K线数据成功")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取实时K线数据失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取实时K线数据失败: {str(e)}"),
        )


@router.get("/gaps/search", response_class=JSONResponse)
async def search_data_gaps(
    symbol: str,
    exchange: str,
    start_date: datetime,
    end_date: datetime,
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """搜索数据断点."""
    try:
        logger.info(
            "搜索数据断点请求: symbol=%s, exchange=%s, start_date=%s, end_date=%s",
            symbol,
            exchange,
            start_date,
            end_date,
        )

        # 获取历史数据
        vnpy_data = vnpy_service.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
        )

        if not vnpy_data:
            return JSONResponse(
                content=ResponseUtil.success(data=[], message="无数据断点")
            )

        # 分析数据断点
        gaps = []
        expected_interval = _get_frequency_seconds(frequency)

        for i in range(1, len(vnpy_data)):
            prev_time = vnpy_data[i - 1].datetime
            curr_time = vnpy_data[i].datetime
            time_diff = (curr_time - prev_time).total_seconds()

            if time_diff > expected_interval * 1.5:  # 允许50%的误差
                gap_info = GapInfo(
                    symbol=symbol,
                    exchange=exchange,
                    gap_start=prev_time,
                    gap_end=curr_time,
                    gap_type="missing_data",
                    severity="medium",
                    suggested_action="下载缺失数据",
                )
                # 将模型转为字典并添加额外信息
                gap_dict = gap_info.dict()
                gap_dict["duration_seconds"] = int(time_diff)
                gap_dict["expected_interval"] = expected_interval
                gaps.append(gap_dict)

        logger.info("返回数据断点: %d 个断点", len(gaps))
        return JSONResponse(
            content=ResponseUtil.success(data=gaps, message="搜索数据断点成功")
        )

    except Exception as e:
        logger.error("搜索数据断点失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"搜索数据断点失败: {str(e)}"),
        )


@router.get("/statistics", response_class=JSONResponse)
async def get_market_statistics(
    symbol: str,
    exchange: str,
    start_date: Optional[datetime] = Query(None, description="开始日期"),  # noqa: B008
    end_date: Optional[datetime] = Query(None, description="结束日期"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取市场统计信息."""
    try:
        logger.info(
            "获取市场统计信息请求: symbol=%s, exchange=%s, start_date=%s, end_date=%s",
            symbol,
            exchange,
            start_date,
            end_date,
        )

        # 获取历史数据
        vnpy_data = vnpy_service.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
        )

        if not vnpy_data:
            return JSONResponse(
                content=ResponseUtil.success(
                    data={
                        "symbol": symbol,
                        "exchange": exchange,
                        "total_records": 0,
                        "start_date": None,
                        "end_date": None,
                        "price_range": {"min": 0, "max": 0, "avg": 0},
                        "volume_total": 0,
                        "turnover_total": 0,
                    },
                    message="无统计数据",
                )
            )

        # 计算统计信息
        prices = [
            bar_data.close_price for bar_data in vnpy_data if bar_data.close_price > 0
        ]
        volumes = [bar_data.volume for bar_data in vnpy_data if bar_data.volume > 0]
        turnovers = [
            bar_data.turnover for bar_data in vnpy_data if bar_data.turnover > 0
        ]

        stats = {
            "symbol": symbol,
            "exchange": exchange,
            "total_records": len(vnpy_data),
            "start_date": vnpy_data[0].datetime.isoformat(),
            "end_date": vnpy_data[-1].datetime.isoformat(),
            "price_range": {
                "min": float(min(prices)) if prices else 0,
                "max": float(max(prices)) if prices else 0,
                "avg": float(sum(prices) / len(prices)) if prices else 0,
            },
            "volume_total": sum(volumes),
            "volume_avg": sum(volumes) / len(volumes) if volumes else 0,
            "turnover_total": sum(turnovers),
            "turnover_avg": sum(turnovers) / len(turnovers) if turnovers else 0,
        }

        logger.info("返回市场统计信息: %s.%s", symbol, exchange)
        return JSONResponse(
            content=ResponseUtil.success(data=stats, message="获取市场统计信息成功")
        )

    except Exception as e:
        logger.error("获取市场统计信息失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取市场统计信息失败: {str(e)}"),
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str = Query(..., description="客户端ID"),  # noqa: B008
    websocket_manager=Depends(get_websocket_manager),  # noqa: B008
):
    """行情看板WebSocket连接."""
    websocket_manager = get_websocket_manager()

    try:
        # 接受WebSocket连接
        await websocket_manager.connect(websocket, client_id, "market_board")

        logger.info("行情看板WebSocket连接已建立: client_id=%s", client_id)

        # 订阅相关主题
        websocket_manager.subscribe_to_topic(client_id, "market_data")
        websocket_manager.subscribe_to_topic(client_id, "tick_data")
        websocket_manager.subscribe_to_topic(client_id, "bar_data")
        websocket_manager.subscribe_to_topic(client_id, "indicator_update")

        # 保持连接
        while True:
            try:
                # 接收客户端消息
                data = await websocket.receive_json()

                # 处理客户端消息
                message_type = data.get("type")
                if message_type == "subscribe":
                    topic = data.get("topic")
                    if topic:
                        websocket_manager.subscribe_to_topic(client_id, topic)
                        await websocket.send_json(
                            {
                                "type": "subscription_confirmed",
                                "topic": topic,
                                "message": f"已订阅主题: {topic}",
                            }
                        )
                elif message_type == "unsubscribe":
                    topic = data.get("topic")
                    if topic:
                        websocket_manager.unsubscribe_from_topic(client_id, topic)
                        await websocket.send_json(
                            {
                                "type": "unsubscription_confirmed",
                                "topic": topic,
                                "message": f"已取消订阅主题: {topic}",
                            }
                        )
                elif message_type == "ping":
                    await websocket.send_json(
                        {"type": "pong", "timestamp": datetime.now().isoformat()}
                    )

            except WebSocketDisconnect:
                logger.info("行情看板WebSocket连接已断开: client_id=%s", client_id)
                break
            except Exception as e:
                logger.error(
                    "处理WebSocket消息失败: client_id=%s, error=%s", client_id, e
                )
                await websocket.send_json(
                    {"type": "error", "message": f"处理消息失败: {str(e)}"}
                )

    except Exception as e:
        logger.error("行情看板WebSocket连接失败: client_id=%s, error=%s", client_id, e)
    finally:
        await websocket_manager.disconnect(client_id)


def _get_frequency_seconds(frequency: str) -> int:
    """获取频率对应的秒数."""
    frequency_map = {
        "1s": 1,
        "5s": 5,
        "10s": 10,
        "30s": 30,
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return frequency_map.get(frequency, 60)

# -*- coding: utf-8 -*-
"""
数据中心路由模块.

提供数据中心相关的API端点，包括品种管理、数据下载、本地数据查询等功能。
"""

import logging
from datetime import datetime, timedelta
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

from backend.api.dependencies import get_event_service, get_vnpy_service
from backend.core.models import (
    DataSourceConfig,
    DownloadTask,
    SymbolInfo,
)
from backend.utils.response import ApiResponse as ResponseUtil
from backend.api.websocket_manager import get_websocket_manager

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(tags=["数据中心"])


@router.get("/symbols", response_class=JSONResponse)
async def get_symbols(
    exchange: Optional[str] = Query(None, description="交易所过滤"),  # noqa: B008
    product: Optional[str] = Query(None, description="产品类型过滤"),  # noqa: B008
    is_active: Optional[bool] = Query(None, description="是否活跃过滤"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取品种列表."""
    try:
        logger.info(
            "获取品种列表请求: exchange=%s, product=%s, is_active=%s",
            exchange,
            product,
            is_active,
        )

        # 从VnPy服务获取品种信息
        vnpy_symbols = vnpy_service.get_symbols()

        # 转换为统一格式
        symbols = []
        for vnpy_symbol in vnpy_symbols:
            symbol_info = SymbolInfo(
                symbol=vnpy_symbol["symbol"],
                exchange=vnpy_symbol["exchange"],
                name=vnpy_symbol.get("name", vnpy_symbol["symbol"]),
                product=vnpy_symbol.get("product", ""),
                size=vnpy_symbol.get("size", 1),
                pricetick=vnpy_symbol.get("pricetick", 0.01),
                min_volume=1,
                max_volume=1000000,
                is_active=True,
                listed_date=None,
                expired_date=None,
            )

            # 应用过滤条件
            if exchange and symbol_info.exchange != exchange:
                continue
            if product and symbol_info.product != product:
                continue
            if is_active is not None and symbol_info.is_active != is_active:
                continue

            symbols.append(symbol_info.dict())

        logger.info("返回品种列表: %d 个品种", len(symbols))
        return JSONResponse(
            content=ResponseUtil.success(data=symbols, message="获取品种列表成功")
        )

    except Exception as e:
        logger.error("获取品种列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取品种列表失败: {str(e)}"),
        )


@router.get("/symbols/{symbol}", response_class=JSONResponse)
async def get_symbol_detail(
    symbol: str,
    exchange: str = Query(..., description="交易所代码"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008
) -> JSONResponse:
    """获取品种详情."""
    try:
        logger.info("获取品种详情请求: symbol=%s, exchange=%s", symbol, exchange)

        # 从VnPy服务获取品种信息
        vnpy_symbols = vnpy_service.get_symbols()

        # 查找指定品种
        target_symbol = None
        for vnpy_symbol in vnpy_symbols:
            if vnpy_symbol["symbol"] == symbol and vnpy_symbol["exchange"] == exchange:
                target_symbol = vnpy_symbol
                break

        if not target_symbol:
            raise HTTPException(status_code=404, detail="品种不存在")

        # 转换为统一格式
        symbol_info = SymbolInfo(
            symbol=target_symbol["symbol"],
            exchange=target_symbol["exchange"],
            name=target_symbol.get("name", target_symbol["symbol"]),
            product=target_symbol.get("product", ""),
            size=target_symbol.get("size", 1),
            pricetick=target_symbol.get("pricetick", 0.01),
            min_volume=1,
            max_volume=1000000,
            is_active=True,
            listed_date=None,
            expired_date=None,
        )

        logger.info("返回品种详情: %s", symbol)
        return JSONResponse(
            content=ResponseUtil.success(
                data=symbol_info.dict(), message="获取品种详情成功"
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取品种详情失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取品种详情失败: {str(e)}"),
        )


@router.post("/download", response_class=JSONResponse)
async def create_download_task(
    symbol: str,
    exchange: str,
    start_date: datetime,
    end_date: datetime,
    data_type: str = Query("bar", description="数据类型"),  # noqa: B008
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """创建数据下载任务."""
    try:
        logger.info(
            "创建下载任务请求: symbol=%s, exchange=%s, start_date=%s, end_date=%s, "
            "data_type=%s, frequency=%s",
            symbol,
            exchange,
            start_date,
            end_date,
            data_type,
            frequency,
        )

        # 验证参数
        if start_date >= end_date:
            raise HTTPException(status_code=400, detail="开始日期必须早于结束日期")

        if end_date > datetime.now():
            raise HTTPException(status_code=400, detail="结束日期不能晚于当前时间")

        # 生成任务ID
        task_id = f"download_{symbol}_{exchange}_{int(datetime.now().timestamp())}"

        # 创建下载任务
        download_task = DownloadTask(
            task_id=task_id,
            symbol=symbol,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
            data_type=data_type,
            frequency=frequency,
            status="pending",
            progress=0.0,
            error_message=None,
        )

        # 发送任务创建事件
        await event_service.emit_event("download_task_created", download_task.dict())

        logger.info("下载任务创建成功: task_id=%s", task_id)
        return JSONResponse(
            content=ResponseUtil.success(
                data=download_task.dict(), message="下载任务创建成功"
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建下载任务失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"创建下载任务失败: {str(e)}"),
        )


@router.get("/download/tasks", response_class=JSONResponse)
async def get_download_tasks(
    status: Optional[str] = Query(None, description="任务状态过滤"),  # noqa: B008
    symbol: Optional[str] = Query(None, description="品种过滤"),  # noqa: B008
    page: int = Query(1, ge=1, description="页码"),  # noqa: B008
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),  # noqa: B008
) -> JSONResponse:
    """获取下载任务列表."""
    try:
        logger.info(
            "获取下载任务列表请求: status=%s, symbol=%s, page=%d, page_size=%d",
            status,
            symbol,
            page,
            page_size,
        )

        # TODO: 从数据库获取下载任务列表
        # 这里先返回模拟数据
        mock_tasks = [
            {
                "task_id": "download_001",
                "symbol": "rb2501",
                "exchange": "SHFE",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-01-31T23:59:59",
                "data_type": "bar",
                "frequency": "1m",
                "status": "completed",
                "progress": 100.0,
                "total_count": 10000,
                "downloaded_count": 10000,
                "created_at": "2024-01-01T10:00:00",
                "updated_at": "2024-01-01T12:00:00",
            },
            {
                "task_id": "download_002",
                "symbol": "ag2501",
                "exchange": "SHFE",
                "start_date": "2024-02-01T00:00:00",
                "end_date": "2024-02-29T23:59:59",
                "data_type": "bar",
                "frequency": "1m",
                "status": "running",
                "progress": 65.0,
                "total_count": 15000,
                "downloaded_count": 9750,
                "created_at": "2024-02-01T09:00:00",
                "updated_at": "2024-02-01T11:30:00",
            },
        ]

        # 应用过滤条件
        filtered_tasks = mock_tasks
        if status:
            filtered_tasks = [
                task for task in filtered_tasks if task["status"] == status
            ]
        if symbol:
            filtered_tasks = [
                task for task in filtered_tasks if task["symbol"] == symbol
            ]

        # 分页
        total = len(filtered_tasks)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_tasks = filtered_tasks[start_idx:end_idx]

        logger.info("返回下载任务列表: %d 个任务", len(page_tasks))
        return JSONResponse(
            content=ResponseUtil.paginated(
                data=page_tasks,
                total=total,
                page=page,
                page_size=page_size,
                message="获取下载任务列表成功",
            )
        )

    except Exception as e:
        logger.error("获取下载任务列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取下载任务列表失败: {str(e)}"),
        )


@router.get("/download/tasks/{task_id}", response_class=JSONResponse)
async def get_download_task_detail(task_id: str) -> JSONResponse:
    """获取下载任务详情."""
    try:
        logger.info("获取下载任务详情请求: task_id=%s", task_id)

        # TODO: 从数据库获取任务详情
        # 这里先返回模拟数据
        mock_task = {
            "task_id": task_id,
            "symbol": "rb2501",
            "exchange": "SHFE",
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-01-31T23:59:59",
            "data_type": "bar",
            "frequency": "1m",
            "status": "completed",
            "progress": 100.0,
            "total_count": 10000,
            "downloaded_count": 10000,
            "error_message": None,
            "created_at": "2024-01-01T10:00:00",
            "updated_at": "2024-01-01T12:00:00",
        }

        logger.info("返回下载任务详情: %s", task_id)
        return JSONResponse(
            content=ResponseUtil.success(data=mock_task, message="获取下载任务详情成功")
        )

    except Exception as e:
        logger.error("获取下载任务详情失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取下载任务详情失败: {str(e)}"),
        )


@router.delete("/download/tasks/{task_id}", response_class=JSONResponse)
async def cancel_download_task(
    task_id: str,
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """取消下载任务."""
    try:
        logger.info("取消下载任务请求: task_id=%s", task_id)

        # TODO: 更新数据库中的任务状态
        # 发送任务取消事件
        await event_service.emit_event("download_task_cancelled", {"task_id": task_id})

        logger.info("下载任务取消成功: task_id=%s", task_id)
        return JSONResponse(content=ResponseUtil.success(message="下载任务取消成功"))

    except Exception as e:
        logger.error("取消下载任务失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"取消下载任务失败: {str(e)}"),
        )


@router.get("/data/local", response_class=JSONResponse)
async def get_local_data(
    symbol: str,
    exchange: str,
    start_date: Optional[datetime] = Query(None, description="开始日期"),  # noqa: B008
    end_date: Optional[datetime] = Query(None, description="结束日期"),  # noqa: B008
    data_type: str = Query("bar", description="数据类型"),  # noqa: B008
    frequency: str = Query("1m", description="数据频率"),  # noqa: B008
    limit: int = Query(1000, ge=1, le=10000, description="数据条数限制"),  # noqa: B008
    vnpy_service: "VnpyService" = Depends(get_vnpy_service),  # noqa: B008, ARG001
) -> JSONResponse:
    """获取本地数据."""
    try:
        logger.info(
            "获取本地数据请求: symbol=%s, exchange=%s, start_date=%s, end_date=%s, "
            "data_type=%s, frequency=%s",
            symbol,
            exchange,
            start_date,
            end_date,
            data_type,
            frequency,
        )

        # vnpy_service will be used for actual data fetching from VnPy DB
        _ = vnpy_service  # noqa: F841

        # TODO: 从VnPy数据库获取本地数据
        # 这里先返回模拟数据
        mock_data = []
        base_time = start_date or (datetime.now() - timedelta(days=1))

        for i in range(min(limit, 100)):
            timestamp = base_time + timedelta(minutes=i)
            mock_data.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "datetime": timestamp.isoformat(),
                    "open_price": 3500.0 + i * 0.5,
                    "high_price": 3500.0 + i * 0.5 + 10.0,
                    "low_price": 3500.0 + i * 0.5 - 5.0,
                    "close_price": 3500.0 + i * 0.5 + 2.0,
                    "volume": 1000 + i * 10,
                    "turnover": 3500000.0 + i * 1750.0,
                    "open_interest": 50000 + i * 100,
                }
            )

        logger.info("返回本地数据: %d 条记录", len(mock_data))
        return JSONResponse(
            content=ResponseUtil.success(data=mock_data, message="获取本地数据成功")
        )

    except Exception as e:
        logger.error("获取本地数据失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取本地数据失败: {str(e)}"),
        )


@router.get("/data/sources", response_class=JSONResponse)
async def get_data_sources() -> JSONResponse:
    """获取数据源配置列表."""
    try:
        logger.info("获取数据源配置列表请求")

        # TODO: 从数据库获取数据源配置
        # 这里先返回模拟数据
        mock_sources = [
            {
                "source_id": "source_001",
                "source_type": "tushare",
                "name": "Tushare数据源",
                "is_enabled": True,
                "is_connected": True,
                "config": {
                    "token": "your_tushare_token",
                    "timeout": 30,
                },
                "last_connected": "2024-01-01T10:00:00",
                "error_count": 0,
            },
            {
                "source_id": "source_002",
                "source_type": "akshare",
                "name": "AKShare数据源",
                "is_enabled": True,
                "is_connected": False,
                "config": {
                    "timeout": 30,
                },
                "last_connected": None,
                "error_count": 3,
            },
        ]

        logger.info("返回数据源配置列表: %d 个数据源", len(mock_sources))
        return JSONResponse(
            content=ResponseUtil.success(
                data=mock_sources, message="获取数据源配置列表成功"
            )
        )

    except Exception as e:
        logger.error("获取数据源配置列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取数据源配置列表失败: {str(e)}"),
        )


@router.post("/data/sources", response_class=JSONResponse)
async def create_data_source(
    source_config: DataSourceConfig,
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """创建数据源配置."""
    try:
        logger.info(
            "创建数据源配置请求: source_id=%s, source_type=%s",
            source_config.source_id,
            source_config.source_type,
        )

        # TODO: 保存到数据库
        # 发送数据源创建事件
        await event_service.emit_event("data_source_created", source_config.dict())

        logger.info("数据源配置创建成功: source_id=%s", source_config.source_id)
        return JSONResponse(
            content=ResponseUtil.success(
                data=source_config.dict(), message="数据源配置创建成功"
            )
        )

    except Exception as e:
        logger.error("创建数据源配置失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"创建数据源配置失败: {str(e)}"),
        )


@router.put("/data/sources/{source_id}", response_class=JSONResponse)
async def update_data_source(
    source_id: str,
    source_config: DataSourceConfig,
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """更新数据源配置."""
    try:
        logger.info("更新数据源配置请求: source_id=%s", source_id)

        # TODO: 更新数据库
        # 发送数据源更新事件
        await event_service.emit_event("data_source_updated", source_config.dict())

        logger.info("数据源配置更新成功: source_id=%s", source_id)
        return JSONResponse(
            content=ResponseUtil.success(
                data=source_config.dict(), message="数据源配置更新成功"
            )
        )

    except Exception as e:
        logger.error("更新数据源配置失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"更新数据源配置失败: {str(e)}"),
        )


@router.delete("/data/sources/{source_id}", response_class=JSONResponse)
async def delete_data_source(
    source_id: str,
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """删除数据源配置."""
    try:
        logger.info("删除数据源配置请求: source_id=%s", source_id)

        # TODO: 从数据库删除
        # 发送数据源删除事件
        await event_service.emit_event("data_source_deleted", {"source_id": source_id})

        logger.info("数据源配置删除成功: source_id=%s", source_id)
        return JSONResponse(content=ResponseUtil.success(message="数据源配置删除成功"))

    except Exception as e:
        logger.error("删除数据源配置失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"删除数据源配置失败: {str(e)}"),
        )


@router.post("/data/sources/{source_id}/test", response_class=JSONResponse)
async def test_data_source_connection(
    source_id: str,
    event_service: "EventService" = Depends(get_event_service),  # noqa: B008
) -> JSONResponse:
    """测试数据源连接."""
    try:
        logger.info("测试数据源连接请求: source_id=%s", source_id)

        # TODO: 实际测试数据源连接
        # 发送测试连接事件
        await event_service.emit_event("data_source_test", {"source_id": source_id})

        # 模拟测试结果
        test_result = {
            "source_id": source_id,
            "connection_status": "success",
            "response_time": 0.5,
            "test_time": datetime.now().isoformat(),
            "message": "连接测试成功",
        }

        logger.info(
            "数据源连接测试完成: source_id=%s, status=%s",
            source_id,
            test_result["connection_status"],
        )
        return JSONResponse(
            content=ResponseUtil.success(data=test_result, message="数据源连接测试完成")
        )

    except Exception as e:
        logger.error("测试数据源连接失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"测试数据源连接失败: {str(e)}"),
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str = Query(..., description="客户端ID"),  # noqa: B008
):
    """数据中心WebSocket连接."""
    websocket_manager = get_websocket_manager()

    try:
        # 接受WebSocket连接
        await websocket_manager.connect(websocket, client_id, "data_center")

        logger.info("数据中心WebSocket连接已建立: client_id=%s", client_id)

        # 订阅相关主题
        websocket_manager.subscribe_to_topic(client_id, "download_task")
        websocket_manager.subscribe_to_topic(client_id, "data_source")
        websocket_manager.subscribe_to_topic(client_id, "market_data")

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
                logger.info("数据中心WebSocket连接已断开: client_id=%s", client_id)
                break
            except Exception as e:
                logger.error(
                    "处理WebSocket消息失败: client_id=%s, error=%s", client_id, e
                )
                await websocket.send_json(
                    {"type": "error", "message": f"处理消息失败: {str(e)}"}
                )

    except Exception as e:
        logger.error("数据中心WebSocket连接失败: client_id=%s, error=%s", client_id, e)
    finally:
        # 断开连接
        await websocket_manager.disconnect(client_id)


# 导出路由器
__all__ = ["router"]

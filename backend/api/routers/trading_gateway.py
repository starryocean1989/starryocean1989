# -*- coding: utf-8 -*-
"""
交易网关路由模块.

提供交易网关相关的API端点，包括网关管理、策略池管理、交易监控等功能。
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from backend.utils.response import ApiResponse as ResponseUtil
from backend.api.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["交易网关"])


# 网关管理端点
@router.get("/gateways", response_class=JSONResponse)
async def get_gateways() -> JSONResponse:
    """获取网关列表."""
    try:
        mock_gateways = [
            {
                "instance_id": "gw_001",
                "gateway_type": "CTP",
                "instance_name": "CTP主力",
                "status": "connected",
                "connected_at": "2024-01-01T09:00:00",
            }
        ]
        return JSONResponse(
            content=ResponseUtil.success(data=mock_gateways, message="获取网关列表成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取网关列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取网关列表失败: {str(e)}"),
        )


@router.post("/gateways", response_class=JSONResponse)
async def create_gateway(
    gateway_type: str = Body(...),  # noqa: B008
    instance_name: str = Body(...),  # noqa: B008
    config: Dict[str, Any] = Body(...),  # noqa: B008
) -> JSONResponse:
    """创建网关实例."""
    try:
        instance = {
            "instance_id": f"gw_{int(datetime.now().timestamp())}",
            "gateway_type": gateway_type,
            "instance_name": instance_name,
            "config": config,
            "status": "disconnected",
            "created_at": datetime.now().isoformat(),
        }
        return JSONResponse(
            content=ResponseUtil.success(data=instance, message="网关创建成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("创建网关失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"创建网关失败: {str(e)}"),
        )


@router.post("/gateways/{gateway_id}/connect", response_class=JSONResponse)
async def connect_gateway(
    gateway_id: str,
    password: Optional[str] = Body(None),  # noqa: B008
) -> JSONResponse:
    """连接网关."""
    try:
        has_password = "with password" if password else "without password"
        logger.info("连接网关: gateway_id=%s, %s", gateway_id, has_password)
        return JSONResponse(content=ResponseUtil.success(message="网关连接成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("连接网关失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"连接网关失败: {str(e)}"),
        )


@router.post("/gateways/{gateway_id}/disconnect", response_class=JSONResponse)
async def disconnect_gateway(gateway_id: str) -> JSONResponse:
    """断开网关."""
    try:
        logger.info("断开网关: gateway_id=%s", gateway_id)
        return JSONResponse(content=ResponseUtil.success(message="网关断开成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("断开网关失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"断开网关失败: {str(e)}"),
        )


@router.delete("/gateways/{gateway_id}", response_class=JSONResponse)
async def delete_gateway(gateway_id: str) -> JSONResponse:
    """删除网关."""
    try:
        logger.info("删除网关: gateway_id=%s", gateway_id)
        return JSONResponse(content=ResponseUtil.success(message="网关删除成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("删除网关失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"删除网关失败: {str(e)}"),
        )


@router.get("/gateways/types/config-schema", response_class=JSONResponse)
async def get_gateway_config_schema(
    gateway_type: str = Query(..., description="网关类型"),  # noqa: B008
) -> JSONResponse:
    """获取网关配置模式."""
    try:
        # 动态表单生成
        if gateway_type == "PaperAccount":
            schema = {"fields": [{"name": "initial_capital", "type": "number"}]}
        else:
            schema = {
                "fields": [
                    {"name": "server", "type": "string"},
                    {"name": "username", "type": "string"},
                    {"name": "password", "type": "password"},
                ]
            }
        return JSONResponse(
            content=ResponseUtil.success(data=schema, message="获取配置模式成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取配置模式失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取配置模式失败: {str(e)}"),
        )


# 策略池端点
@router.get("/gateways/{gateway_id}/strategies", response_class=JSONResponse)
async def get_gateway_strategies(gateway_id: str) -> JSONResponse:
    """获取网关策略池."""
    try:
        logger.info("获取网关策略池: gateway_id=%s", gateway_id)
        mock_strategies = [
            {
                "strategy_id": "strat_001",
                "strategy_name": "MA Cross",
                "strategy_type": "ctastrategy",
                "status": "running",
            }
        ]
        return JSONResponse(
            content=ResponseUtil.success(data=mock_strategies, message="获取策略池成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取策略池失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取策略池失败: {str(e)}"),
        )


@router.post("/gateways/{gateway_id}/strategies", response_class=JSONResponse)
async def deploy_strategy(
    gateway_id: str,
    strategy_file_id: str = Body(...),  # noqa: B008
    strategy_name: str = Body(...),  # noqa: B008
    parameters: Dict[str, Any] = Body(default={}),  # noqa: B008
) -> JSONResponse:
    """部署策略到网关."""
    try:
        strategy = {
            "strategy_id": f"strat_{int(datetime.now().timestamp())}",
            "gateway_id": gateway_id,
            "strategy_file_id": strategy_file_id,
            "strategy_name": strategy_name,
            "parameters": parameters,
            "status": "stopped",
            "deployed_at": datetime.now().isoformat(),
        }
        return JSONResponse(
            content=ResponseUtil.success(data=strategy, message="策略部署成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("部署策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"部署策略失败: {str(e)}"),
        )


@router.post("/strategies/{strategy_id}/start", response_class=JSONResponse)
async def start_strategy(strategy_id: str) -> JSONResponse:
    """启动策略."""
    try:
        logger.info("启动策略: strategy_id=%s", strategy_id)
        return JSONResponse(content=ResponseUtil.success(message="策略启动成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("启动策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"启动策略失败: {str(e)}"),
        )


@router.post("/strategies/{strategy_id}/stop", response_class=JSONResponse)
async def stop_strategy(strategy_id: str) -> JSONResponse:
    """停止策略."""
    try:
        logger.info("停止策略: strategy_id=%s", strategy_id)
        return JSONResponse(content=ResponseUtil.success(message="策略停止成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("停止策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"停止策略失败: {str(e)}"),
        )


@router.post("/gateways/{gateway_id}/strategies/start-all")
async def start_all_strategies(gateway_id: str) -> JSONResponse:
    """启动所有策略."""
    try:
        logger.info("启动所有策略: gateway_id=%s", gateway_id)
        return JSONResponse(content=ResponseUtil.success(message="所有策略启动成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("启动所有策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"启动所有策略失败: {str(e)}"),
        )


@router.post("/gateways/{gateway_id}/strategies/stop-all")
async def stop_all_strategies(gateway_id: str) -> JSONResponse:
    """停止所有策略."""
    try:
        logger.info("停止所有策略: gateway_id=%s", gateway_id)
        return JSONResponse(content=ResponseUtil.success(message="所有策略停止成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("停止所有策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"停止所有策略失败: {str(e)}"),
        )


@router.delete("/strategies/{strategy_id}", response_class=JSONResponse)
async def delete_strategy(strategy_id: str) -> JSONResponse:
    """删除策略."""
    try:
        logger.info("删除策略: strategy_id=%s", strategy_id)
        return JSONResponse(content=ResponseUtil.success(message="策略删除成功"))
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("删除策略失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"删除策略失败: {str(e)}"),
        )


# 监控端点
@router.get("/monitoring/{gateway_id}", response_class=JSONResponse)
async def get_monitoring_data(gateway_id: str) -> JSONResponse:
    """获取网关监控数据."""
    try:
        mock_data = {
            "gateway_id": gateway_id,
            "orders_count": 10,
            "positions_count": 5,
            "account_balance": 1000000.0,
        }
        return JSONResponse(
            content=ResponseUtil.success(data=mock_data, message="获取监控数据成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取监控数据失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取监控数据失败: {str(e)}"),
        )


@router.get("/monitoring/{gateway_id}/orders", response_class=JSONResponse)
async def get_orders(gateway_id: str) -> JSONResponse:
    """获取委托列表."""
    try:
        logger.info("获取委托列表: gateway_id=%s", gateway_id)
        mock_orders = []
        return JSONResponse(
            content=ResponseUtil.success(data=mock_orders, message="获取委托列表成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取委托列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取委托列表失败: {str(e)}"),
        )


@router.get("/monitoring/{gateway_id}/positions", response_class=JSONResponse)
async def get_positions(gateway_id: str) -> JSONResponse:
    """获取持仓列表."""
    try:
        logger.info("获取持仓列表: gateway_id=%s", gateway_id)
        mock_positions = []
        return JSONResponse(
            content=ResponseUtil.success(
                data=mock_positions, message="获取持仓列表成功"
            )
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取持仓列表失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取持仓列表失败: {str(e)}"),
        )


@router.get("/monitoring/{gateway_id}/accounts", response_class=JSONResponse)
async def get_accounts(gateway_id: str) -> JSONResponse:
    """获取资金账户."""
    try:
        logger.info("获取资金账户: gateway_id=%s", gateway_id)
        mock_accounts = []
        return JSONResponse(
            content=ResponseUtil.success(data=mock_accounts, message="获取资金账户成功")
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("获取资金账户失败: %s", e)
        return JSONResponse(
            status_code=500,
            content=ResponseUtil.error(message=f"获取资金账户失败: {str(e)}"),
        )


# WebSocket
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str = Query(...),  # noqa: B008
):
    """交易网关WebSocket连接."""
    websocket_manager = get_websocket_manager()
    try:
        await websocket_manager.connect(websocket, client_id, "trading_gateway")
        logger.info("交易网关WebSocket连接已建立: client_id=%s", client_id)
        websocket_manager.subscribe_to_topic(client_id, "trading_data")
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get("type")
                if message_type == "ping":
                    await websocket.send_json(
                        {"type": "pong", "timestamp": datetime.now().isoformat()}
                    )
            except WebSocketDisconnect:
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("处理WebSocket消息失败: %s", e)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("交易网关WebSocket连接失败: %s", e)
    finally:
        await websocket_manager.disconnect(client_id)


__all__ = ["router"]

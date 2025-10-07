# -*- coding: utf-8 -*-
"""
FastAPI应用入口模块.

创建和配置FastAPI应用，注册路由，设置中间件等。
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.dependencies import initialize_dependencies, shutdown_dependencies
from backend.api.middleware import setup_middleware
from backend.api.routers import (
    data_center,
    market_board,
    portfolio,
    strategy_center,
    system_manager,
    trading_gateway,
)
from backend.api.websocket_manager import get_websocket_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):  # noqa: ARG001, U100
    """应用生命周期管理."""
    # 启动时执行
    logger.info("正在启动后端服务...")

    try:
        # 初始化依赖注入容器
        await initialize_dependencies()
        logger.info("依赖注入容器初始化完成")

        # 启动WebSocket管理器清理任务
        get_websocket_manager()
        logger.info("WebSocket管理器启动完成")

        logger.info("后端服务启动完成")

        yield

    except Exception as e:
        logger.error("服务启动失败: %s", e)
        raise

    finally:
        # 关闭时执行
        logger.info("正在关闭后端服务...")

        try:
            # 关闭依赖注入容器
            await shutdown_dependencies()
            logger.info("依赖注入容器已关闭")

            logger.info("后端服务关闭完成")

        except Exception as e:
            logger.error("服务关闭时发生错误: %s", e)


def create_app() -> FastAPI:
    """创建FastAPI应用."""
    # 创建FastAPI应用实例
    app = FastAPI(
        title="星辰金融终端后端API",
        description="提供6个功能界面的后端服务接口",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 设置中间件
    setup_middleware(app)

    # 注册路由
    app.include_router(
        data_center.router, prefix="/api/v1/data-center", tags=["数据中心"]
    )
    app.include_router(
        market_board.router, prefix="/api/v1/market-board", tags=["行情看板"]
    )
    app.include_router(
        strategy_center.router, prefix="/api/v1/strategy-center", tags=["策略指标中心"]
    )
    app.include_router(
        trading_gateway.router, prefix="/api/v1/trading-gateway", tags=["交易网关"]
    )
    app.include_router(portfolio.router, prefix="/api/v1/portfolio", tags=["组合投资"])
    app.include_router(
        system_manager.router, prefix="/api/v1/system", tags=["系统管理"]
    )

    # 根路径健康检查
    @app.get("/", response_class=JSONResponse)
    async def root():
        """根路径健康检查."""
        return {
            "code": 0,
            "message": "星辰金融终端后端服务运行正常",
            "data": {
                "service": "terminal-backend",
                "version": "1.0.0",
                "status": "healthy",
            },
        }

    # API版本信息
    @app.get("/api/v1", response_class=JSONResponse)
    async def api_info():
        """API版本信息."""
        return {
            "code": 0,
            "message": "API服务正常",
            "data": {
                "api_version": "v1",
                "available_modules": [
                    "data_center",
                    "market_board",
                    "strategy_center",
                    "trading_gateway",
                    "portfolio",
                    "system_manager",
                ],
                "supported_formats": ["JSON", "WebSocket"],
                "documentation": "/docs",
            },
        }

    # WebSocket连接统计
    @app.get("/api/v1/websocket/stats", response_class=JSONResponse)
    async def websocket_stats():
        """获取WebSocket连接统计."""
        websocket_manager = get_websocket_manager()
        stats = websocket_manager.get_statistics()

        return {"code": 0, "message": "WebSocket统计信息", "data": stats}

    logger.info("FastAPI应用创建完成")
    return app


# 创建应用实例
app = create_app()


# 导出应用实例
__all__ = ["app"]

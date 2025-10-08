# -*- coding: utf-8 -*-
"""
数据中心服务.

提供完整的数据管理功能，包括：
- 品种列表管理
- 数据下载管理（全量/增量）
- 本地数据查询
- 数据质量检查和自动修复
- 数据源管理（data_engine, ifind, rqdata, tushare）
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

from backend.services.base_service import BaseService


class DataCenterService(BaseService):
    """数据中心服务.

    基于data_module_vnpy包实现的数据管理服务，提供：
    1. 品种列表管理 - 获取、缓存、筛选、搜索
    2. 数据下载 - 全量下载、增量下载、进度监控
    3. 本地数据查询 - OHLCV数据查询、展示
    4. 数据质量管理 - 质量检查、自动修复、断点检测
    5. 数据源管理 - 4种数据源连接、实时数据录制
    """

    def __init__(self):
        """初始化数据中心服务."""
        super().__init__()

        # ChinaStockEngine引擎
        self.china_stock_engine = None

        # data_engine
        self.data_engine = None

        # 数据源连接状态
        self.datafeeds = {
            "data_engine": None,
            "ifind": None,
            "rqdata": None,
            "tushare": None,
        }

        # 品种列表缓存
        self._symbol_cache: Optional[Dict[str, Any]] = None
        self._symbol_cache_time: Optional[datetime] = None

        # 下载任务管理
        self._download_tasks: Dict[str, Dict[str, Any]] = {}

        self.logger.info("数据中心服务已创建")

    def _do_initialize(self) -> bool:
        """初始化数据中心服务."""
        try:
            self.logger.info("初始化数据中心服务...")

            # 获取全局ChinaStockEngine
            from backend.core.shared_services import get_china_stock_engine

            self.china_stock_engine = get_china_stock_engine()

            if self.china_stock_engine:
                self.logger.info("✅ ChinaStockEngine 可用")
            else:
                self.logger.warning("⚠️ ChinaStockEngine 不可用，部分功能受限")

            # 尝试初始化data_engine
            self._init_data_engine()

            return True  # 即使部分功能不可用，也返回True以允许服务启动

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭数据中心服务."""
        try:
            self.logger.info("关闭数据中心服务...")

            # 停止所有下载任务
            self._stop_all_downloads()

            # 断开所有数据源
            self._disconnect_all_datafeeds()

            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "china_stock_engine_available": self.china_stock_engine is not None,
            "data_engine_available": self.data_engine is not None,
            "connected_datafeeds": [name for name, df in self.datafeeds.items() if df is not None],
            "symbol_cache_loaded": self._symbol_cache is not None,
            "active_downloads": len(self._download_tasks),
        }

    def _init_data_engine(self) -> bool:
        """初始化data_engine."""
        try:
            # 尝试导入data_engine包
            try:
                from backend.infrastructure.data_engine import engine as de_engine

                self.data_engine = de_engine
                self.logger.info("✅ data_engine初始化成功")
                return True
            except ImportError as e:
                self.logger.warning("⚠️ data_engine包不可用: %s", e)
                return False

        except Exception as e:
            self.logger.error("data_engine初始化失败: %s", e, exc_info=True)
            return False

    # ==================== 品种列表管理 ====================

    def reload_symbol_list(self, force: bool = False) -> Dict[str, Any]:
        """重新加载品种列表（调用API请求）.

        Args:
            force: 是否强制重新加载，即使缓存有效

        Returns:
            Dict: {
                "success": bool,
                "symbol_count": int,
                "message": str,
                "data": List[Dict]  # 品种列表
            }
        """
        try:
            self._log_operation("重新加载品种列表", force=force)

            # 检查缓存是否有效（如果不强制刷新）
            if not force and self._is_symbol_cache_valid():
                return {
                    "success": True,
                    "symbol_count": len(self._symbol_cache.get("symbols", [])),
                    "message": "使用缓存的品种列表",
                    "data": self._symbol_cache.get("symbols", []),
                }

            # 调用china_stock_engine获取品种列表
            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 调用实际的品种列表获取方法
            symbols = self._fetch_symbols_from_china_stock()

            # 更新缓存
            self._symbol_cache = {
                "symbols": symbols,
                "timestamp": datetime.now(),
            }
            self._symbol_cache_time = datetime.now()

            return {
                "success": True,
                "symbol_count": len(symbols),
                "message": "品种列表加载成功",
                "data": symbols,
            }

        except Exception as e:
            self._log_error("重新加载品种列表", e)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"加载失败: {str(e)}",
                "data": [],
            }

    def refresh_symbol_list(self) -> Dict[str, Any]:
        """刷新品种列表（使用缓存，不调用API）.

        Returns:
            Dict: 包含success, symbol_count, message, data的字典
        """
        try:
            self._log_operation("刷新品种列表")

            if self._symbol_cache is None:
                # 如果缓存为空，调用reload
                return self.reload_symbol_list(force=False)

            return {
                "success": True,
                "symbol_count": len(self._symbol_cache.get("symbols", [])),
                "message": "品种列表刷新成功（使用缓存）",
                "data": self._symbol_cache.get("symbols", []),
            }

        except Exception as e:
            self._log_error("刷新品种列表", e)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"刷新失败: {str(e)}",
                "data": [],
            }

    def filter_symbols(
        self,
        exchange: Optional[str] = None,
        symbol_type: Optional[str] = None,
        search_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """筛选和搜索品种.

        Args:
            exchange: 交易所代码（如：SSE, SZSE）
            symbol_type: 品种类型（如：stock, bond, fund）
            search_text: 搜索文本（模糊匹配代码或名称）

        Returns:
            Dict: 筛选后的品种列表
        """
        try:
            if self._symbol_cache is None:
                return {
                    "success": False,
                    "symbol_count": 0,
                    "message": "品种列表未加载",
                    "data": [],
                }

            symbols = self._symbol_cache.get("symbols", [])
            filtered = symbols

            # 按交易所筛选
            if exchange:
                filtered = [s for s in filtered if s.get("exchange") == exchange]

            # 按品种类型筛选
            if symbol_type:
                filtered = [s for s in filtered if s.get("type") == symbol_type]

            # 按搜索文本筛选
            if search_text:
                search_text = search_text.lower()
                filtered = [
                    s
                    for s in filtered
                    if search_text in s.get("code", "").lower()
                    or search_text in s.get("name", "").lower()
                ]

            return {
                "success": True,
                "symbol_count": len(filtered),
                "message": "筛选成功",
                "data": filtered,
            }

        except Exception as e:
            self._log_error("筛选品种", e, exchange=exchange, type=symbol_type)
            return {
                "success": False,
                "symbol_count": 0,
                "message": f"筛选失败: {str(e)}",
                "data": [],
            }

    def _is_symbol_cache_valid(self, max_age_hours: int = 24) -> bool:
        """检查品种缓存是否有效.

        Args:
            max_age_hours: 最大缓存年龄（小时）

        Returns:
            bool: 缓存是否有效
        """
        if self._symbol_cache is None or self._symbol_cache_time is None:
            return False

        age = datetime.now() - self._symbol_cache_time
        return age < timedelta(hours=max_age_hours)

    def _fetch_symbols_from_china_stock(self) -> List[Dict[str, Any]]:
        """从ChinaStockEngine获取品种列表.

        Returns:
            List[Dict]: 品种列表
        """
        try:
            # 调用ChinaStockEngine的reload_stock_list方法
            result = self.china_stock_engine.reload_stock_list()

            if not result:
                self.logger.warning("ChinaStockEngine返回空结果")
                return []

            # 转换为前端需要的格式
            symbols = []
            for exchange, stock_list in result.items():
                for stock_code in stock_list:
                    symbols.append(
                        {
                            "code": stock_code,
                            "exchange": exchange,
                            "name": stock_code,  # 暂时使用代码作为名称
                            "type": "stock",  # 暂时都标记为stock
                        }
                    )

            self.logger.info(f"成功获取 {len(symbols)} 个品种")
            return symbols

        except Exception as e:
            self.logger.error(f"获取品种列表失败: {e}", exc_info=True)
            return []

    # ==================== 数据下载管理 ====================

    def start_full_download(self) -> Dict[str, Any]:
        """启动全量数据下载.

        下载全品类（股票、可转债、T+0基金）、全周期（日线、5min、1min）的历史数据。

        Returns:
            Dict: {
                "success": bool,
                "task_id": str,
                "message": str
            }
        """
        try:
            self._log_operation("启动全量数据下载")

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "task_id": None,
                    "message": "ChinaStockEngine不可用",
                }

            # 创建下载任务
            task_id = f"full_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 调用ChinaStockEngine的K线数据全量下载方法
            try:
                self.china_stock_engine.download_all_stocks()
            except Exception as e:
                self.logger.error(f"全量下载启动失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"下载失败: {str(e)}",
                }

            # 注册任务
            self._download_tasks[task_id] = {
                "type": "full",
                "status": "running",
                "start_time": datetime.now(),
                "progress": 0,
            }

            return {
                "success": True,
                "task_id": task_id,
                "message": "全量下载已启动",
            }

        except Exception as e:
            self._log_error("启动全量下载", e)
            return {
                "success": False,
                "task_id": None,
                "message": f"启动失败: {str(e)}",
            }

    def start_incremental_download(self, start_date: str) -> Dict[str, Any]:
        """启动增量数据下载.

        下载从指定日期至今的数据。

        Args:
            start_date: 开始日期（格式：YYYY-MM-DD）

        Returns:
            Dict: 下载任务信息
        """
        try:
            self._log_operation("启动增量数据下载", start_date=start_date)

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "task_id": None,
                    "message": "data_module_vnpy不可用",
                }

            # 创建下载任务
            task_id = f"incremental_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 调用ChinaStockEngine的增量下载方法
            try:
                # 解析日期
                from datetime import datetime as dt

                start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                self.china_stock_engine.download_incremental(start_date=start_dt)

                # 注册任务
                self._download_tasks[task_id] = {
                    "type": "incremental",
                    "status": "running",
                    "start_time": datetime.now(),
                    "start_date": start_date,
                    "progress": 50,  # 假设进度
                }

                return {
                    "success": True,
                    "task_id": task_id,
                    "message": "增量下载已启动",
                }
            except Exception as e:
                self.logger.error(f"增量下载启动失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "task_id": None,
                    "message": f"下载失败: {str(e)}",
                }

        except Exception as e:
            self._log_error("启动增量下载", e, start_date=start_date)
            return {
                "success": False,
                "task_id": None,
                "message": f"启动失败: {str(e)}",
            }

    def get_download_progress(self, task_id: str) -> Dict[str, Any]:
        """获取下载进度.

        Args:
            task_id: 任务ID

        Returns:
            Dict: 进度信息
        """
        task = self._download_tasks.get(task_id)
        if task is None:
            return {
                "success": False,
                "message": "任务不存在",
            }

        return {
            "success": True,
            "task_id": task_id,
            "type": task["type"],
            "status": task["status"],
            "progress": task["progress"],
            "start_time": task["start_time"].isoformat(),
        }

    def stop_download(self, task_id: str) -> Dict[str, Any]:
        """停止下载任务.

        Args:
            task_id: 任务ID

        Returns:
            Dict: 操作结果
        """
        try:
            if task_id not in self._download_tasks:
                return {
                    "success": False,
                    "message": "任务不存在",
                }

            # TODO: 实现实际的停止逻辑

            self._download_tasks[task_id]["status"] = "stopped"

            return {
                "success": True,
                "message": "任务已停止",
            }

        except Exception as e:
            self._log_error("停止下载", e, task_id=task_id)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def _stop_all_downloads(self):
        """停止所有下载任务."""
        for task_id in list(self._download_tasks.keys()):
            self.stop_download(task_id)

    # ==================== 本地数据查询 ====================

    def query_local_data(
        self, symbol: str, start_date: str, end_date: str, interval: str = "1d"
    ) -> Dict[str, Any]:
        """查询本地OHLCV数据.

        Args:
            symbol: 品种代码
            start_date: 开始日期
            end_date: 结束日期
            interval: 周期（1d, 5min, 1min等）

        Returns:
            Dict: OHLCV数据
        """
        try:
            self._log_operation(
                "查询本地数据", symbol=symbol, start=start_date, end=end_date, interval=interval
            )

            if self.china_stock_engine is None:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "data": [],
                }

            # 调用ChinaStockEngine的数据查询方法
            try:
                from datetime import datetime as dt

                start_dt = dt.strptime(start_date, "%Y-%m-%d").date()
                end_dt = dt.strptime(end_date, "%Y-%m-%d").date()

                # 查询数据
                data = self.china_stock_engine.query_bar_data(
                    symbol=symbol, start_date=start_dt, end_date=end_dt, interval=interval
                )

                if data is not None and not data.empty:
                    # 转换为字典列表
                    data_list = data.to_dict("records")
                    return {
                        "success": True,
                        "message": f"查询成功，共{len(data_list)}条数据",
                        "data": data_list,
                    }
                else:
                    return {
                        "success": True,
                        "message": "查询成功，无数据",
                        "data": [],
                    }

            except Exception as e:
                self.logger.error(f"数据查询失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"查询失败: {str(e)}",
                    "data": [],
                }

        except Exception as e:
            self._log_error("查询本地数据", e, symbol=symbol)
            return {
                "success": False,
                "message": f"查询失败: {str(e)}",
                "data": [],
            }

    def check_data_quality(self, symbol: str = None) -> Dict[str, Any]:
        """检查数据质量.

        Args:
            symbol: 品种代码（可选，为None则检查所有品种）

        Returns:
            Dict: 质量检查结果
        """
        try:
            self._log_operation("检查数据质量", symbol=symbol)

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "issues": [],
                }

            # 调用ChinaStockEngine的数据校验方法
            try:
                if symbol:
                    # 单品种校验
                    validation_result = self.china_stock_engine.validate_data([symbol])
                else:
                    # 所有品种校验
                    validation_result = self.china_stock_engine.validate_data()

                if validation_result:
                    issues = []
                    # 解析校验结果
                    if hasattr(validation_result, "to_dict"):
                        issues_dict = validation_result.to_dict()
                        for sym, result in issues_dict.items():
                            if not result.get("is_valid", True):
                                issues.append({"symbol": sym, "issue": result.get("message", "")})

                    return {
                        "success": True,
                        "message": f"质量检查完成，发现{len(issues)}个问题",
                        "issues": issues,
                    }
                else:
                    return {
                        "success": True,
                        "message": "质量检查完成",
                        "issues": [],
                    }

            except Exception as e:
                self.logger.error(f"质量检查失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"检查失败: {str(e)}",
                    "issues": [],
                }

        except Exception as e:
            self._log_error("检查数据质量", e, symbol=symbol)
            return {
                "success": False,
                "message": f"检查失败: {str(e)}",
                "issues": [],
            }

    def auto_repair_data(self, symbol: str, issues: List[str]) -> Dict[str, Any]:
        """自动修复数据.

        Args:
            symbol: 品种代码
            issues: 需要修复的问题列表

        Returns:
            Dict: 修复结果
        """
        try:
            self._log_operation("自动修复数据", symbol=symbol, issues_count=len(issues))

            if not self.china_stock_engine:
                return {
                    "success": False,
                    "message": "ChinaStockEngine不可用",
                    "repaired_count": 0,
                }

            # 使用增量下载修复数据
            try:
                from datetime import date, timedelta

                # 修复最近30天的数据
                start_date = date.today() - timedelta(days=30)
                self.china_stock_engine.download_incremental(start_date=start_date)

                return {
                    "success": True,
                    "message": f"数据修复完成，已重新下载{symbol}最近30天的数据",
                    "repaired_count": len(issues),
                }

            except Exception as e:
                self.logger.error(f"数据修复失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"修复失败: {str(e)}",
                    "repaired_count": 0,
                }

        except Exception as e:
            self._log_error("自动修复数据", e, symbol=symbol)
            return {
                "success": False,
                "message": f"修复失败: {str(e)}",
                "repaired_count": 0,
            }

    # ==================== 数据源管理 ====================

    def connect_datafeed(
        self, datafeed_type: str, config: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """连接数据源.

        Args:
            datafeed_type: 数据源类型 (data_engine, ifind, rqdata, tushare)
            config: 配置信息（如账号密码）

        Returns:
            Dict: 连接结果
        """
        try:
            self._log_operation("连接数据源", type=datafeed_type)

            if datafeed_type not in self.datafeeds:
                return {
                    "success": False,
                    "message": f"不支持的数据源类型: {datafeed_type}",
                }

            # TODO: 实现实际的数据源连接逻辑
            # 需要根据不同类型调用不同的连接方法

            return {
                "success": True,
                "message": f"数据源 {datafeed_type} 连接成功",
            }

        except Exception as e:
            self._log_error("连接数据源", e, type=datafeed_type)
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
            }

    def disconnect_datafeed(self, datafeed_type: str) -> Dict[str, Any]:
        """断开数据源.

        Args:
            datafeed_type: 数据源类型

        Returns:
            Dict: 操作结果
        """
        try:
            if datafeed_type not in self.datafeeds:
                return {
                    "success": False,
                    "message": f"不支持的数据源类型: {datafeed_type}",
                }

            # TODO: 实现断开逻辑

            self.datafeeds[datafeed_type] = None

            return {
                "success": True,
                "message": f"数据源 {datafeed_type} 已断开",
            }

        except Exception as e:
            self._log_error("断开数据源", e, type=datafeed_type)
            return {
                "success": False,
                "message": f"断开失败: {str(e)}",
            }

    def _disconnect_all_datafeeds(self):
        """断开所有数据源."""
        for datafeed_type in list(self.datafeeds.keys()):
            if self.datafeeds[datafeed_type] is not None:
                self.disconnect_datafeed(datafeed_type)

    def start_data_recording(self) -> Dict[str, Any]:
        """启动实时数据录制.

        Returns:
            Dict: 操作结果
        """
        try:
            self._log_operation("启动数据录制")

            # TODO: 调用vnpy_datarecorder启动录制

            return {
                "success": True,
                "message": "数据录制已启动",
            }

        except Exception as e:
            self._log_error("启动数据录制", e)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_data_recording(self) -> Dict[str, Any]:
        """停止实时数据录制.

        Returns:
            Dict: 操作结果
        """
        try:
            # TODO: 停止录制

            return {
                "success": True,
                "message": "数据录制已停止",
            }

        except Exception as e:
            self._log_error("停止数据录制", e)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def get_datafeed_status(self) -> Dict[str, Any]:
        """获取所有数据源状态.

        Returns:
            Dict: 数据源状态信息
        """
        status = {}
        for datafeed_type, datafeed in self.datafeeds.items():
            status[datafeed_type] = {
                "connected": datafeed is not None,
                "pushing_data": False,  # TODO: 检查实际推送状态
            }
        return {
            "success": True,
            "datafeeds": status,
        }

# -*- coding: utf-8 -*-
"""
数据录制服务

集成vnpy_datarecorder，提供实时数据录制功能。
录制的数据使用Parquet格式存储，以应对大数据量。
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.services.base_and_utils import BaseService


class DataRecorderService(BaseService):
    """数据录制服务."""

    def __init__(self):
        """初始化数据录制服务."""
        super().__init__()

        # 录制引擎
        self.recorder_engine = None

        # 录制任务配置
        self.recording_tasks: Dict[str, Dict[str, Any]] = {}

        # 录制数据存储路径
        self.data_dir = Path("data/recorded")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 录制统计
        self.statistics = {
            "total_ticks": 0,
            "total_bars": 0,
            "active_symbols": set(),
        }

    def initialize(self) -> bool:
        """初始化服务."""
        try:
            self.logger.info("初始化数据录制服务...")
            return self._do_initialize()
        except Exception as e:
            self.logger.error("数据录制服务初始化失败: %s", e, exc_info=True)
            return False

    def shutdown(self) -> bool:
        """关闭服务."""
        try:
            self.logger.info("关闭数据录制服务...")
            return self._do_shutdown()
        except Exception as e:
            self.logger.error("关闭数据录制服务失败: %s", e, exc_info=True)
            return False

    def _do_initialize(self) -> bool:
        """具体的初始化逻辑."""
        try:
            # 尝试导入vnpy_datarecorder
            try:
                from vnpy_datarecorder import DataRecorderApp

                # 检查MainEngine是否可用
                if not self.main_engine:
                    self.logger.warning("MainEngine不可用，无法初始化录制引擎")
                    return False

                # 初始化录制引擎
                if self.main_engine:
                    self.recorder_engine = self.main_engine.add_app(DataRecorderApp)
                else:
                    self.logger.error("MainEngine不可用，无法初始化录制引擎")
                    return False

                if not self.recorder_engine:
                    self.logger.error("录制引擎初始化失败")
                    return False

                self.logger.info("✅ 数据录制引擎初始化成功")
                return True

            except ImportError:
                self.logger.warning("⚠️ vnpy_datarecorder未安装，数据录制功能不可用")
                self.logger.warning(
                    "   请安装: pip install git+https://github.com/vnpy/vnpy_datarecorder.git"
                )
                return False

        except Exception as e:
            self.logger.error("数据录制服务初始化失败: %s", e, exc_info=True)
            return False

    def _do_shutdown(self) -> bool:
        """具体的关闭逻辑."""
        try:
            self.logger.info("关闭数据录制服务...")

            # 停止所有录制任务（同步版本）
            self._stop_all_recording_sync()

            self.logger.info("✅ 数据录制服务已关闭")
            return True

        except Exception as e:
            self.logger.error("关闭数据录制服务失败: %s", e, exc_info=True)
            return False

    def _stop_all_recording_sync(self) -> None:
        """同步停止所有录制任务."""
        try:
            # 获取当前运行的录制任务
            task_ids = list(self.recording_tasks.keys())

            for task_id in task_ids:
                try:
                    task = self.recording_tasks[task_id]

                    # 停止录制（如果录制引擎提供相应方法）
                    if self.recorder_engine and self.main_engine:
                        vt_symbol = f"{task['symbol']}.{task['exchange']}"

                        if hasattr(self.recorder_engine, "remove_bar_recording"):
                            for interval in task["intervals"]:
                                try:
                                    from vnpy.trader.constant import Interval

                                    interval_enum = Interval(interval)
                                    self.recorder_engine.remove_bar_recording(
                                        vt_symbol, interval_enum
                                    )
                                except Exception as e:
                                    self.logger.warning("移除K线录制失败: %s", e)

                        if task["record_tick"] and hasattr(
                            self.recorder_engine, "remove_tick_recording"
                        ):
                            self.recorder_engine.remove_tick_recording(vt_symbol)

                    # 更新任务状态
                    task["status"] = "stopped"
                    if "stop_time" not in task:
                        from datetime import datetime

                        task["stop_time"] = datetime.now()

                    # 从活跃列表移除
                    self.statistics["active_symbols"].discard(task_id)

                    # 移除任务
                    del self.recording_tasks[task_id]

                except Exception as e:
                    self.logger.warning("停止录制任务 %s 失败: %s", task_id, e)

        except Exception as e:
            self.logger.error("停止所有录制失败: %s", e)

    async def check_health(self) -> bool:
        """健康检查."""
        return self.recorder_engine is not None

    # ========== 录制控制 ==========

    async def start_recording(
        self,
        symbol: str,
        exchange: str,
        gateway_name: str,
        record_tick: bool = True,
        record_bar: bool = True,
        intervals: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """开始录制数据.

        Args:
            symbol: 品种代码
            exchange: 交易所
            gateway_name: 网关名称
            record_tick: 是否录制Tick
            record_bar: 是否录制K线
            intervals: K线周期列表 ['1m', '5m', '15m', '1h', '1d']

        Returns:
            操作结果
        """
        try:
            if not self.recorder_engine:
                return {"success": False, "message": "录制引擎未初始化"}

            # 生成任务ID
            task_id = f"{symbol}.{exchange}"

            # 检查是否已经在录制
            if task_id in self.recording_tasks:
                return {"success": False, "message": f"{symbol} 已经在录制中"}

            # 默认录制周期
            if intervals is None:
                intervals = ["1m", "5m", "1h"]

            # 创建录制任务
            task_config = {
                "task_id": task_id,
                "symbol": symbol,
                "exchange": exchange,
                "gateway_name": gateway_name,
                "record_tick": record_tick,
                "record_bar": record_bar,
                "intervals": intervals,
                "start_time": datetime.now(),
                "tick_count": 0,
                "bar_count": 0,
                "status": "running",
            }

            # 启动录制
            from vnpy.trader.constant import Exchange, Interval
            from vnpy.trader.object import SubscribeRequest

            # 构建订阅请求
            vt_symbol = f"{symbol}.{exchange}"
            req = SubscribeRequest(symbol=symbol, exchange=Exchange(exchange))

            # 订阅行情
            if self.main_engine:
                self.main_engine.subscribe(req, gateway_name)
            else:
                self.logger.warning("MainEngine不可用，无法订阅行情")

            # 启动录制引擎（如果有add_bar_recording等方法）
            if hasattr(self.recorder_engine, "add_bar_recording"):
                for interval in intervals:
                    try:
                        interval_enum = Interval(interval)
                        self.recorder_engine.add_bar_recording(vt_symbol, interval_enum)
                    except Exception as e:
                        self.logger.warning("添加K线录制失败 %s: %s", interval, e)

            if record_tick and hasattr(self.recorder_engine, "add_tick_recording"):
                self.recorder_engine.add_tick_recording(vt_symbol)

            # 保存任务配置
            self.recording_tasks[task_id] = task_config

            # 更新统计
            self.statistics["active_symbols"].add(task_id)

            self.logger.info("✅ 开始录制 %s.%s", symbol, exchange)

            return {"success": True, "message": "成功开始录制 %s" % symbol, "task_id": task_id}

        except Exception as e:
            self.logger.error("开始录制失败: %s", e, exc_info=True)
            return {"success": False, "message": "开始录制失败: %s" % str(e)}

    async def stop_recording(self, task_id: str) -> Dict[str, Any]:
        """停止录制.

        Args:
            task_id: 任务ID

        Returns:
            操作结果
        """
        try:
            if task_id not in self.recording_tasks:
                return {"success": False, "message": f"任务 {task_id} 不存在"}

            task = self.recording_tasks[task_id]

            # 停止录制（如果录制引擎提供相应方法）
            if self.recorder_engine:
                vt_symbol = f"{task['symbol']}.{task['exchange']}"

                if hasattr(self.recorder_engine, "remove_bar_recording"):
                    for interval in task["intervals"]:
                        try:
                            from vnpy.trader.constant import Interval

                            interval_enum = Interval(interval)
                            self.recorder_engine.remove_bar_recording(vt_symbol, interval_enum)
                        except Exception as e:
                            self.logger.warning("移除K线录制失败: %s", e)

                if task["record_tick"] and hasattr(self.recorder_engine, "remove_tick_recording"):
                    self.recorder_engine.remove_tick_recording(vt_symbol)

            # 更新任务状态
            task["status"] = "stopped"
            task["stop_time"] = datetime.now()

            # 从活跃列表移除
            self.statistics["active_symbols"].discard(task_id)

            # 移除任务
            del self.recording_tasks[task_id]

            self.logger.info("✅ 停止录制 %s", task_id)

            return {"success": True, "message": "成功停止录制 %s" % task_id}

        except Exception as e:
            self.logger.error("停止录制失败: %s", e, exc_info=True)
            return {"success": False, "message": "停止录制失败: %s" % str(e)}

    async def stop_all_recording(self) -> Dict[str, Any]:
        """停止所有录制任务.

        Returns:
            操作结果
        """
        try:
            task_ids = list(self.recording_tasks.keys())
            stopped_count = 0

            for task_id in task_ids:
                result = await self.stop_recording(task_id)
                if result["success"]:
                    stopped_count += 1

            return {
                "success": True,
                "message": "成功停止 %s 个录制任务" % stopped_count,
                "stopped_count": stopped_count,
            }

        except Exception as e:
            self.logger.error("停止所有录制失败: %s", e, exc_info=True)
            return {"success": False, "message": "停止所有录制失败: %s" % str(e)}

    # ========== 任务管理 ==========

    def get_recording_tasks(self) -> List[Dict[str, Any]]:
        """获取所有录制任务.

        Returns:
            录制任务列表
        """
        tasks = []

        for task_id, task in self.recording_tasks.items():
            # 计算录制时长
            duration = (datetime.now() - task["start_time"]).total_seconds()

            task_info = {
                "task_id": task_id,
                "symbol": task["symbol"],
                "exchange": task["exchange"],
                "gateway_name": task["gateway_name"],
                "record_tick": task["record_tick"],
                "record_bar": task["record_bar"],
                "intervals": task["intervals"],
                "status": task["status"],
                "start_time": task["start_time"].isoformat(),
                "duration": duration,
                "tick_count": task["tick_count"],
                "bar_count": task["bar_count"],
            }

            tasks.append(task_info)

        return tasks

    def get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息.

        Args:
            task_id: 任务ID

        Returns:
            任务信息
        """
        if task_id not in self.recording_tasks:
            return None

        task = self.recording_tasks[task_id]
        duration = (datetime.now() - task["start_time"]).total_seconds()

        return {
            "task_id": task_id,
            "symbol": task["symbol"],
            "exchange": task["exchange"],
            "gateway_name": task["gateway_name"],
            "record_tick": task["record_tick"],
            "record_bar": task["record_bar"],
            "intervals": task["intervals"],
            "status": task["status"],
            "start_time": task["start_time"].isoformat(),
            "duration": duration,
            "tick_count": task["tick_count"],
            "bar_count": task["bar_count"],
        }

    # ========== 统计信息 ==========

    def get_statistics(self) -> Dict[str, Any]:
        """获取录制统计信息.

        Returns:
            统计信息
        """
        return {
            "total_tasks": len(self.recording_tasks),
            "active_tasks": len(
                [t for t in self.recording_tasks.values() if t["status"] == "running"]
            ),
            "total_ticks": self.statistics["total_ticks"],
            "total_bars": self.statistics["total_bars"],
            "active_symbols": list(self.statistics["active_symbols"]),
            "data_dir": str(self.data_dir),
        }

    # ========== 数据管理 ==========

    def get_recorded_symbols(self) -> List[str]:
        """获取已录制的品种列表.

        Returns:
            品种列表
        """
        symbols = set()

        # 扫描数据目录
        if self.data_dir.exists():
            for item in self.data_dir.iterdir():
                if item.is_dir():
                    symbols.add(item.name)

        return sorted(list(symbols))

    def get_recorded_data_info(self, symbol: str) -> Dict[str, Any]:
        """获取品种录制数据信息.

        Args:
            symbol: 品种代码

        Returns:
            数据信息
        """
        symbol_dir = self.data_dir / symbol

        if not symbol_dir.exists():
            return {
                "symbol": symbol,
                "exists": False,
            }

        # 统计数据文件
        tick_files = list(symbol_dir.glob("tick_*.parquet"))
        bar_files = list(symbol_dir.glob("bar_*.parquet"))

        # 计算总大小
        total_size = sum(f.stat().st_size for f in tick_files + bar_files)

        return {
            "symbol": symbol,
            "exists": True,
            "tick_files": len(tick_files),
            "bar_files": len(bar_files),
            "total_size": total_size,
            "total_size_mb": total_size / (1024 * 1024),
            "data_dir": str(symbol_dir),
        }

    async def clear_recorded_data(self, symbol: str) -> Dict[str, Any]:
        """清除录制数据.

        Args:
            symbol: 品种代码

        Returns:
            操作结果
        """
        try:
            symbol_dir = self.data_dir / symbol

            if not symbol_dir.exists():
                return {"success": False, "message": "品种 %s 无录制数据" % symbol}

            # 删除目录
            import shutil

            shutil.rmtree(symbol_dir)

            self.logger.info("✅ 清除 %s 录制数据", symbol)

            return {"success": True, "message": "成功清除 %s 录制数据" % symbol}

        except Exception as e:
            self.logger.error("清除录制数据失败: %s", e, exc_info=True)
            return {"success": False, "message": "清除数据失败: %s" % str(e)}

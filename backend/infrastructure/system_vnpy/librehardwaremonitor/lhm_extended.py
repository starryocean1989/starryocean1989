# -*- coding: utf-8 -*-
"""LibreHardwareMonitor扩展包装器 - 支持所有传感器类型.

扩展功能:
- Temperature (温度)
- Power (功耗)
- Voltage (电压)
- Fan (风扇转速)
- Clock (时钟频率)
- Load (负载)
- Control (控制)
- Throughput (吞吐量)
- Data (数据)
"""

import logging
import os
import sys
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ExtendedLHMWrapper:
    """LibreHardwareMonitor扩展包装器.

    相比基础版本，支持更多传感器类型，用于全面的硬件监控。
    """

    def __init__(self):
        """初始化扩展包装器."""
        self._computer = None
        self._initialized = False
        self._dll_path = None
        self._SensorType = None
        self._Computer = None

        # 尝试初始化
        try:
            self._initialize()
        except Exception as e:
            logger.warning("ExtendedLHMWrapper初始化失败: %s", e, extra={"log_type": "SYSTEM"})
            logger.info("将回退到基础监控方式")

    def _initialize(self):
        """初始化.NET库和LibreHardwareMonitor."""
        # 1. 检查pythonnet
        try:
            import clr  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pythonnet未安装，请运行: pip install pythonnet") from exc

        # 2. 确定DLL路径
        self._dll_path = os.path.join(os.path.dirname(__file__), "LibreHardwareMonitorLib.dll")

        if not os.path.exists(self._dll_path):
            raise FileNotFoundError(
                f"LibreHardwareMonitorLib.dll未找到: {self._dll_path}\n"
                f"请按照README.md中的说明下载并放置DLL文件"
            )

        # 3. 添加DLL路径到搜索路径
        dll_dir = os.path.dirname(self._dll_path)
        if dll_dir not in sys.path:
            sys.path.append(dll_dir)

        # 4. 加载.NET程序集
        try:
            clr.AddReference("LibreHardwareMonitorLib")  # type: ignore
        except Exception as e:
            raise RuntimeError(f"无法加载LibreHardwareMonitorLib.dll: {e}") from e

        # 5. 导入.NET类型
        try:
            from LibreHardwareMonitor.Hardware import Computer, SensorType  # type: ignore

            self._Computer = Computer
            self._SensorType = SensorType
        except ImportError as e:
            raise RuntimeError(f"无法导入LibreHardwareMonitor类型: {e}") from e

        # 6. 创建Computer实例并启用所有硬件
        self._computer = self._Computer()
        self._computer.IsCpuEnabled = True
        self._computer.IsGpuEnabled = True
        self._computer.IsStorageEnabled = True
        self._computer.IsMotherboardEnabled = True
        self._computer.IsMemoryEnabled = True
        self._computer.IsControllerEnabled = True  # 风扇控制器
        self._computer.IsNetworkEnabled = True  # 网络适配器

        # 7. 创建UpdateVisitor（正确的LibreHardwareMonitor使用方式）
        try:
            self._update_visitor = self._create_update_visitor()
        except Exception as e:
            logger.warning("无法创建UpdateVisitor（将使用回退方法）: %s", e, extra={"log_type": "SYSTEM"})
            self._update_visitor = None

        # 8. 打开硬件监控
        try:
            self._computer.Open()
            self._initialized = True
            logger.info("✅ ExtendedLHMWrapper初始化成功")
        except Exception as e:
            if "WinRing0" in str(e) or "driver" in str(e).lower():
                raise RuntimeError(
                    "无法加载WinRing0驱动，请以管理员权限运行程序\n" f"详细错误: {e}"
                ) from e
            raise RuntimeError(f"无法打开硬件监控: {e}") from e

    def _create_update_visitor(self):
        """创建UpdateVisitor（Python实现）.

        由于pythonnet实现.NET接口比较复杂，我们使用简化的递归更新方法。

        Returns:
            None: 我们不实际创建visitor对象，而是在get_all_sensor_data中手动递归
        """
        # 尝试导入IVisitor接口
        try:
            from LibreHardwareMonitor.Hardware import IVisitor  # type: ignore

            # 如果成功导入，说明可以使用Visitor模式（但Python实现复杂，暂不实现）
            logger.debug("IVisitor接口可用（但使用手动递归更新）")
        except ImportError:
            logger.debug("IVisitor接口不可用（使用手动递归更新）")

        return None  # 使用手动递归更新方法

    def is_available(self) -> bool:
        """检查是否可用.

        Returns:
            bool: 如果初始化成功返回True
        """
        return self._initialized

    def get_all_sensor_data(self) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """获取所有传感器数据.

        Returns:
            Dict: 分类的传感器数据
            {
                "temperature": {设备名: [{label, current, high, critical, unit}]},
                "power": {设备名: [...]},
                "voltage": {设备名: [...]},
                "fan": {设备名: [...]},
                "clock": {设备名: [...]},
                "load": {设备名: [...]},
                "control": {设备名: [...]},
                "throughput": {设备名: [...]},
                "data": {设备名: [...]}
            }
        """
        if not self._initialized:
            return {}

        try:
            result = {
                "temperature": {},
                "power": {},
                "voltage": {},
                "fan": {},
                "clock": {},
                "load": {},
                "control": {},
                "throughput": {},
                "data": {},
            }

            # 遍历所有硬件（使用递归更新，模拟UpdateVisitor）
            for hardware in self._computer.Hardware:  # type: ignore
                self._update_hardware_recursive(hardware, result)

            return result

        except Exception as e:
            logger.error("获取传感器数据失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            return {}

    def _update_hardware_recursive(
        self, hardware, result: Dict[str, Dict[str, List[Dict[str, Any]]]]
    ):
        """递归更新硬件及其子硬件（模拟UpdateVisitor行为）.

        这是LibreHardwareMonitor的正确使用方式：
        1. 先调用hardware.Update()
        2. 收集当前硬件的传感器
        3. 递归处理所有子硬件

        Args:
            hardware: LibreHardwareMonitor的Hardware对象
            result: 结果字典（会被修改）
        """
        try:
            # 1. 更新硬件数据（这会刷新传感器值）
            hardware.Update()

            # 2. 收集该硬件的所有传感器
            device_name = str(hardware.Name)
            self._collect_all_sensors(hardware, device_name, result)

            # 3. 递归处理所有子硬件（关键！模拟UpdateVisitor的递归行为）
            for subhardware in hardware.SubHardware:
                # 递归调用自己，让每个子硬件也执行Update和收集
                self._update_hardware_recursive(subhardware, result)

        except Exception as e:
            logger.warning("更新硬件 %s 失败: %s", hardware.Name if hardware else "Unknown", e, extra={"log_type": "SYSTEM"})

    def _collect_all_sensors(
        self, hardware, device_name: str, result: Dict[str, Dict[str, List[Dict[str, Any]]]]
    ):
        """从硬件对象收集所有类型的传感器数据.

        Args:
            hardware: LibreHardwareMonitor的Hardware对象
            device_name: 设备名称
            result: 结果字典（会被修改）
        """
        # 确保SensorType已初始化
        if self._SensorType is None:
            return

        try:
            for sensor in hardware.Sensors:
                sensor_type = sensor.SensorType

                # 提取传感器值
                current = float(sensor.Value) if sensor.Value is not None else None
                max_val = float(sensor.Max) if sensor.Max is not None else None
                min_val = float(sensor.Min) if sensor.Min is not None else None

                if current is None:
                    continue

                sensor_data = {
                    "label": str(sensor.Name),
                    "current": current,
                    "min": min_val,
                    "max": max_val,
                    "unit": self._get_sensor_unit(sensor_type),
                }

                # 根据传感器类型分类存储
                if sensor_type == self._SensorType.Temperature:
                    category = "temperature"
                    # 温度传感器特殊处理：添加阈值估算
                    sensor_data["high"] = max_val if max_val and max_val > current else None
                    sensor_data["critical"] = None  # LHM不提供临界值

                elif sensor_type == self._SensorType.Power:
                    category = "power"

                elif sensor_type == self._SensorType.Voltage:
                    category = "voltage"

                elif sensor_type == self._SensorType.Fan:
                    category = "fan"

                elif sensor_type == self._SensorType.Clock:
                    category = "clock"

                elif sensor_type == self._SensorType.Load:
                    category = "load"

                elif sensor_type == self._SensorType.Control:
                    category = "control"

                elif sensor_type == self._SensorType.Throughput:
                    category = "throughput"

                elif sensor_type == self._SensorType.Data:
                    category = "data"

                else:
                    # 未知类型，跳过
                    continue

                # 存储到对应分类
                if device_name not in result[category]:
                    result[category][device_name] = []
                result[category][device_name].append(sensor_data)

        except Exception as e:
            logger.debug("收集传感器数据失败 (%s): %s", device_name, e)

    def _get_sensor_unit(self, sensor_type) -> str:
        """获取传感器单位.

        Args:
            sensor_type: 传感器类型

        Returns:
            str: 单位字符串
        """
        # 确保SensorType已初始化
        if self._SensorType is None:
            return ""

        unit_map = {
            self._SensorType.Temperature: "°C",
            self._SensorType.Power: "W",
            self._SensorType.Voltage: "V",
            self._SensorType.Fan: "RPM",
            self._SensorType.Clock: "MHz",
            self._SensorType.Load: "%",
            self._SensorType.Control: "%",
            self._SensorType.Throughput: "B/s",
            self._SensorType.Data: "GB",
        }
        return unit_map.get(sensor_type, "")

    def get_temperature_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """仅获取温度数据（向后兼容）.

        Returns:
            Dict: 温度数据
        """
        all_data = self.get_all_sensor_data()
        return all_data.get("temperature", {})

    def close(self):
        """关闭硬件监控并清理资源."""
        if self._computer:
            try:
                self._computer.Close()
                logger.info("ExtendedLHMWrapper已关闭")
            except Exception as e:
                logger.error("关闭ExtendedLHMWrapper失败: %s", e, extra={"log_type": "SYSTEM"}, exc_info=True)
            finally:
                self._computer = None
                self._initialized = False

    def __del__(self):
        """析构函数，确保资源被清理."""
        self.close()

    def get_status_summary(self) -> str:
        """获取状态摘要.

        Returns:
            str: 状态描述
        """
        if self._initialized:
            return "✅ LibreHardwareMonitor Extended (pythonnet)"
        return "❌ LibreHardwareMonitor Extended 不可用"


# 全局单例实例
_extended_lhm_wrapper: Optional[ExtendedLHMWrapper] = None


def get_extended_lhm_wrapper() -> ExtendedLHMWrapper:
    """获取扩展LHM包装器的单例实例.

    Returns:
        ExtendedLHMWrapper: 包装器实例
    """
    global _extended_lhm_wrapper  # noqa: PLW0603
    if _extended_lhm_wrapper is None:
        _extended_lhm_wrapper = ExtendedLHMWrapper()
    return _extended_lhm_wrapper


__all__ = ["ExtendedLHMWrapper", "get_extended_lhm_wrapper"]

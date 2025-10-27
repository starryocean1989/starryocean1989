# -*- coding: utf-8 -*-
"""
WMI SMART监控模块 - 纯Python实现，无需外部工具
使用Windows Management Instrumentation (WMI) 获取硬盘SMART数据
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class DiskType(Enum):
    """硬盘类型枚举"""

    UNKNOWN = "unknown"
    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"


@dataclass
class SmartAttribute:
    """SMART属性"""

    id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw_value: int
    status: str  # OK, WARNING, CRITICAL


@dataclass
class DiskSmartData:
    """硬盘SMART数据"""

    disk_name: str
    model: str
    serial: str
    capacity: str
    interface: str
    assessment: str  # PASS, FAIL, UNKNOWN
    temperature: Optional[int] = None
    power_on_hours: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    uncorrectable_errors: Optional[int] = None
    attributes: List[SmartAttribute] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = []
        if self.timestamp is None:
            self.timestamp = datetime.now()


class WMISmartMonitor:
    """
    基于WMI的SMART监控器 - 纯Python实现

    使用Windows WMI接口获取硬盘健康状态：
    - MSStorageDriver_FailurePredictStatus: 预测故障状态
    - MSStorageDriver_FailurePredictData: SMART属性数据
    - Win32_DiskDrive: 硬盘基本信息
    """

    def __init__(self):
        self._available = False
        self._wmi = None
        self._wmi_cimv2 = None
        self._disk_cache: Dict[str, Dict[str, Any]] = {}
        self._thread_local_wmi = {}  # 线程本地WMI实例
        self._initialize_wmi()

    def _initialize_wmi(self):
        """初始化WMI连接"""
        try:
            import wmi

            self._wmi = wmi.WMI(namespace="root\\wmi")
            self._wmi_cimv2 = wmi.WMI()  # 用于Win32_DiskDrive
            self._available = True
            logger.info("✓ WMI SMART监控器初始化成功")
        except ImportError:
            logger.warning("WMI模块未安装，SMART监控不可用 (pip install wmi)")
        except Exception as e:
            logger.warning("WMI初始化失败: %s", e)

    def _get_thread_wmi(self):
        """获取线程本地的WMI实例（COM线程安全）"""
        import threading

        thread_id = threading.current_thread().ident

        if thread_id not in self._thread_local_wmi:
            try:
                # 🔥 关键修复：在线程中初始化COM
                import pythoncom

                pythoncom.CoInitialize()

                import wmi

                self._thread_local_wmi[thread_id] = {
                    "wmi": wmi.WMI(namespace="root\\wmi"),
                    "wmi_cimv2": wmi.WMI(),
                }
                logger.info(f"[WMI-SMART] ✓ 为线程{thread_id}创建WMI实例")
            except Exception as e:
                logger.error(f"[WMI-SMART] ✗ 线程{thread_id}创建WMI实例失败: %s", e)
                return None

        return self._thread_local_wmi[thread_id]

    def is_available(self) -> bool:
        """检查WMI是否可用"""
        return self._available

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        """
        获取所有硬盘的SMART数据

        Returns:
            Dict[disk_name, DiskSmartData]: 硬盘名称到SMART数据的映射
        """
        if not self._available:
            logger.debug("[WMI-SMART] WMI不可用")
            return {}

        result = {}

        try:
            # 1. 获取硬盘基本信息
            disks_info = self._get_disks_basic_info()
            logger.debug(f"[WMI-SMART] 获取到 {len(disks_info)} 个硬盘基本信息")
            if disks_info:
                logger.debug(f"[WMI-SMART] 硬盘实例名: {list(disks_info.keys())}")

            # 2. 获取SMART健康状态
            health_status = self._get_failure_predict_status()
            logger.debug(f"[WMI-SMART] 获取到 {len(health_status)} 个健康状态")
            if health_status:
                logger.debug(f"[WMI-SMART] 健康状态实例名: {list(health_status.keys())}")

            # 3. 获取SMART详细数据
            smart_data = self._get_failure_predict_data()
            logger.debug(f"[WMI-SMART] 获取到 {len(smart_data)} 个SMART数据")
            if smart_data:
                logger.debug(f"[WMI-SMART] SMART数据实例名: {list(smart_data.keys())}")

            # 4. 合并数据
            # 🔧 即使没有SMART详细数据，也要显示硬盘基本信息
            for instance_name, disk_info in disks_info.items():
                try:
                    # 获取健康状态（可能为空，需要管理员权限）
                    health = health_status.get(instance_name, {})
                    predict_failure = health.get("predict_failure", False)

                    # 获取SMART属性（可能为空，需要管理员权限）
                    attributes = smart_data.get(instance_name, [])

                    # 解析关键SMART属性
                    temperature = None
                    power_on_hours = None
                    reallocated_sectors = None
                    pending_sectors = None
                    uncorrectable_errors = None

                    for attr in attributes:
                        if attr.id == 194:  # Temperature
                            temperature = attr.raw_value
                        elif attr.id == 9:  # Power On Hours
                            power_on_hours = attr.raw_value
                        elif attr.id == 5:  # Reallocated Sectors Count
                            reallocated_sectors = attr.raw_value
                        elif attr.id == 197:  # Current Pending Sector Count
                            pending_sectors = attr.raw_value
                        elif attr.id == 187 or attr.id == 188:  # Uncorrectable Errors
                            uncorrectable_errors = attr.raw_value

                    # 评估健康状态
                    # 如果没有SMART数据（权限不足），标记为UNKNOWN但仍显示基本信息
                    if not attributes and not health_status:
                        assessment = "未知（需要管理员权限）"
                    else:
                        assessment = self._assess_health(
                            predict_failure,
                            attributes,
                            reallocated_sectors,
                            pending_sectors,
                            uncorrectable_errors,
                        )

                    # 构建SMART数据对象
                    smart_data_obj = DiskSmartData(
                        disk_name=disk_info.get("name", instance_name),
                        model=disk_info.get("model", "Unknown"),
                        serial=disk_info.get("serial", "Unknown"),
                        capacity=disk_info.get("capacity", "Unknown"),
                        interface=disk_info.get("interface", "Unknown"),
                        assessment=assessment,
                        temperature=temperature,
                        power_on_hours=power_on_hours,
                        # 🔧 修复：将None值转换为0，避免后续类型错误
                        reallocated_sectors=(
                            reallocated_sectors if reallocated_sectors is not None else 0
                        ),
                        pending_sectors=pending_sectors if pending_sectors is not None else 0,
                        uncorrectable_errors=(
                            uncorrectable_errors if uncorrectable_errors is not None else 0
                        ),
                        attributes=attributes,
                        timestamp=datetime.now(),
                    )

                    result[disk_info.get("name", instance_name)] = smart_data_obj

                except Exception as e:
                    logger.debug("处理硬盘SMART数据失败 (%s): %s", instance_name, e)

            logger.info("成功读取 %d 个硬盘的WMI-SMART数据", len(result))

        except Exception as e:
            logger.exception("获取WMI-SMART数据失败: %s", e)

        return result

    def _get_disks_basic_info(self) -> Dict[str, Dict[str, Any]]:
        """获取硬盘基本信息（型号、序列号等）"""
        disks = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                logger.warning("[WMI-SMART] 无法获取线程本地WMI实例")
                return {}

            for disk in thread_wmi["wmi_cimv2"].Win32_DiskDrive():
                # 从PNPDeviceID提取实例名（用于匹配WMI命名空间）
                # 例如: SCSI\DISK&VEN_...\4&... -> SCSI_DISK&VEN_...
                instance_name = disk.PNPDeviceID.replace("\\", "_")

                # 提取PhysicalDrive编号
                device_id = disk.DeviceID  # \\.\PHYSICALDRIVE0
                disk_name = device_id.split("\\")[-1]  # PHYSICALDRIVE0

                # 检测硬盘类型
                disk_type = DiskType.UNKNOWN
                if disk.InterfaceType and "NVMe" in disk.InterfaceType:
                    disk_type = DiskType.NVME
                elif disk.Model and any(
                    kw in disk.Model.upper() for kw in ["SSD", "SOLID STATE", "NVME"]
                ):
                    disk_type = DiskType.SSD
                else:
                    disk_type = DiskType.HDD

                # 格式化容量
                capacity = "Unknown"
                if disk.Size:
                    capacity_gb = int(disk.Size) / (1024**3)
                    capacity = f"{capacity_gb:.1f} GB"

                disks[instance_name] = {
                    "name": disk_name,
                    "model": disk.Model or "Unknown",
                    "serial": disk.SerialNumber.strip() if disk.SerialNumber else "Unknown",
                    "capacity": capacity,
                    "interface": disk.InterfaceType or "Unknown",
                    "disk_type": disk_type.value,
                    "device_id": device_id,
                    "pnp_id": disk.PNPDeviceID,
                }

        except Exception as e:
            logger.debug("获取硬盘基本信息失败: %s", e)

        return disks

    def _get_failure_predict_status(self) -> Dict[str, Dict[str, Any]]:
        """获取故障预测状态（SMART健康状态）"""
        status_map = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictStatus():
                instance_name = item.InstanceName.strip("\x00")  # 移除空字符
                status_map[instance_name] = {
                    "predict_failure": item.PredictFailure,
                    "reason": item.Reason if hasattr(item, "Reason") else 0,
                }
        except Exception as e:
            logger.debug("获取故障预测状态失败: %s", e)

        return status_map

    def _get_failure_predict_data(self) -> Dict[str, List[SmartAttribute]]:
        """获取故障预测数据（SMART属性）"""
        data_map = {}

        try:
            # 使用线程本地WMI实例（COM线程安全）
            thread_wmi = self._get_thread_wmi()
            if not thread_wmi:
                return {}

            for item in thread_wmi["wmi"].MSStorageDriver_FailurePredictData():
                instance_name = item.InstanceName.strip("\x00")

                # 解析SMART数据（512字节）
                vendor_specific = item.VendorSpecific
                if not vendor_specific or len(vendor_specific) < 362:
                    continue

                attributes = []

                # SMART属性从字节2开始，每12字节一个属性，共30个属性
                for i in range(30):
                    offset = 2 + i * 12
                    if offset + 12 > len(vendor_specific):
                        break

                    attr_id = vendor_specific[offset]
                    if attr_id == 0:  # 无效属性
                        continue

                    # 提取属性值
                    flags = (vendor_specific[offset + 1] << 8) | vendor_specific[offset + 2]
                    value = vendor_specific[offset + 3]
                    worst = vendor_specific[offset + 4]
                    raw_value = sum(vendor_specific[offset + 5 + j] << (j * 8) for j in range(6))

                    # SMART属性ID到名称的映射
                    attr_name = self._get_smart_attr_name(attr_id)

                    # 阈值（通常需要从另一个WMI类获取，这里简化处理）
                    threshold = 0

                    # 状态评估
                    status = "OK"
                    if value < threshold and threshold > 0:
                        status = "CRITICAL"
                    elif value < worst:
                        status = "WARNING"

                    attr = SmartAttribute(
                        id=attr_id,
                        name=attr_name,
                        value=value,
                        worst=worst,
                        threshold=threshold,
                        raw_value=raw_value,
                        status=status,
                    )
                    attributes.append(attr)

                data_map[instance_name] = attributes

        except Exception as e:
            logger.debug("获取SMART属性失败: %s", e)

        return data_map

    def _get_smart_attr_name(self, attr_id: int) -> str:
        """获取SMART属性名称"""
        attr_names = {
            1: "Read Error Rate",
            5: "Reallocated Sectors Count",
            9: "Power-On Hours",
            10: "Spin Retry Count",
            12: "Power Cycle Count",
            187: "Reported Uncorrectable Errors",
            188: "Command Timeout",
            194: "Temperature",
            195: "Hardware ECC Recovered",
            196: "Reallocation Event Count",
            197: "Current Pending Sector Count",
            198: "Uncorrectable Sector Count",
            199: "UltraDMA CRC Error Count",
            200: "Multi-Zone Error Rate",
            241: "Total LBAs Written",
            242: "Total LBAs Read",
        }
        return attr_names.get(attr_id, f"Attribute_{attr_id}")

    def _assess_health(
        self,
        predict_failure: bool,
        attributes: List[SmartAttribute],
        reallocated_sectors: Optional[int],
        pending_sectors: Optional[int],
        uncorrectable_errors: Optional[int],
    ) -> str:
        """
        评估硬盘健康状态

        Returns:
            "正常": 健康
            "故障": 即将故障
            "警告": 警告
            "未知": 未知
        """
        # 如果WMI预测故障，直接返回故障
        if predict_failure:
            return "故障"

        # 检查关键SMART属性
        critical_issues = 0
        warning_issues = 0

        for attr in attributes:
            if attr.status == "CRITICAL":
                critical_issues += 1
            elif attr.status == "WARNING":
                warning_issues += 1

        # 检查重分配扇区
        if reallocated_sectors is not None and reallocated_sectors > 0:
            if reallocated_sectors > 50:
                critical_issues += 1
            elif reallocated_sectors > 10:
                warning_issues += 1

        # 检查待处理扇区
        if pending_sectors is not None and pending_sectors > 0:
            if pending_sectors > 10:
                critical_issues += 1
            elif pending_sectors > 0:
                warning_issues += 1

        # 检查不可纠正错误
        if uncorrectable_errors is not None and uncorrectable_errors > 0:
            critical_issues += 1

        # 综合评估
        if critical_issues > 0:
            return "故障"
        elif warning_issues > 0:
            return "警告"
        else:
            return "正常"


# 单例实例
_wmi_smart_monitor_instance: Optional[WMISmartMonitor] = None


def get_wmi_smart_monitor() -> WMISmartMonitor:
    """获取WMI SMART监控器单例"""
    global _wmi_smart_monitor_instance
    if _wmi_smart_monitor_instance is None:
        _wmi_smart_monitor_instance = WMISmartMonitor()
    return _wmi_smart_monitor_instance

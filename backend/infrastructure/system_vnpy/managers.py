# -*- coding: utf-8 -*-
"""
管理模块 - 服务/进程/安全管理.

v0.50重构：合并service_manager.py + process_manager.py + security_manager.py

包含：
- ServiceHealthChecker: 服务健康检查
- ServiceRestarter: 服务重启管理
- ProcessManager: 进程管理（启动、停止、监控）
- SecurityManager: 安全管理（访问控制、加密、审计）
- PermissionController: 权限控制
- EncryptionManager: 加密管理
- AuditLogger: 审计日志
"""

import base64
import datetime
import logging
import secrets
import threading
import time
from typing import Any, Dict

import psutil
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


# =============================================================================
# 服务健康检查和重启
# =============================================================================


class ServiceHealthChecker:
    """增强版服务健康检查器 - 支持业务指标、资源占用、外部依赖检查."""

    def __init__(self):
        """初始化服务健康检查器."""
        self.logger = logging.getLogger(__name__)
        self._monitoring_interval = 2  # 默认2秒推送频率
        self._main_process = psutil.Process()

    def set_monitoring_interval(self, interval: int):
        """设置监控推送频率.

        Args:
            interval: 推送间隔（秒），范围1-10
        """
        self._monitoring_interval = max(1, min(10, interval))
        self.logger.info("监控推送频率已设置为 %d 秒", self._monitoring_interval)

    def get_monitoring_interval(self) -> int:
        """获取当前监控推送频率."""
        return self._monitoring_interval

    def quick_check(self, service_name: str, service_manager) -> Dict[str, Any]:
        """快速检查服务健康状态（增强版）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 检查结果，包含基础指标、业务指标、资源占用
        """
        try:
            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "service_name": service_name,
                    "status": "not_found",
                    "online": False,
                    "response_time_ms": 0,
                    "message": "服务未注册",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

            # 检查服务是否初始化
            is_initialized = getattr(service, "is_initialized", False)

            # 测量响应时间（通过调用health_check）
            start_time = time.time()
            try:
                health_result = service.health_check() if hasattr(service, "health_check") else {}
                response_time_ms = (time.time() - start_time) * 1000

                # 收集业务指标（从性能跟踪器获取）
                call_count = 0
                success_rate = 100.0
                error_rate = 0.0

                try:
                    from backend.services.system_manager_service import performance_tracker

                    # 尝试从性能跟踪器获取服务相关指标
                    all_metrics = performance_tracker.get_all_metrics()
                    # 查找与服务相关的指标
                    service_metrics = {}
                    for _category, metrics_list in all_metrics.items():
                        # metrics_list 是一个列表，包含多个指标字典
                        for metric_dict in metrics_list:
                            # 遍历字典中的每个指标
                            for metric_name, metric_value in metric_dict.items():
                                if service_name.replace("_service", "") in metric_name.lower():
                                    # 存储指标值（注意：这里的 metric_value 可能是数值，不是字典）
                                    if isinstance(metric_value, dict):
                                        service_metrics[metric_name] = metric_value

                    # 聚合业务指标
                    if service_metrics:
                        total_calls = sum(m.get("total_calls", 0) for m in service_metrics.values())
                        if total_calls > 0:
                            call_count = total_calls
                            # 计算平均成功率
                            success_rates = [
                                m.get("success_rate", 100) for m in service_metrics.values()
                            ]
                            success_rate = sum(success_rates) / len(success_rates)
                            error_rate = 100.0 - success_rate
                except Exception as e:
                    self.logger.debug("获取业务指标失败 %s: %s", service_name, e)

                # 收集资源占用指标
                memory_mb = 0.0
                thread_count = 0

                try:
                    # 获取当前进程的内存占用
                    memory_info = self._main_process.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)

                    # 获取线程数
                    thread_count = threading.active_count()
                except Exception as e:
                    self.logger.debug("获取资源占用失败 %s: %s", service_name, e)

                return {
                    "service_name": service_name,
                    "status": "online",
                    "online": True,
                    "initialized": is_initialized,
                    "response_time_ms": round(response_time_ms, 2),
                    "health_details": health_result,
                    "message": "服务正常",
                    # 业务指标
                    "call_count": call_count,
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    # 资源占用
                    "memory_mb": round(memory_mb, 2),
                    "thread_count": thread_count,
                }
            except Exception as e:
                response_time_ms = (time.time() - start_time) * 1000
                return {
                    "service_name": service_name,
                    "status": "error",
                    "online": False,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": f"健康检查失败: {str(e)}",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 100.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

        except Exception as e:
            self.logger.error("快速检查服务失败 %s: %s", service_name, e)
            return {
                "service_name": service_name,
                "status": "error",
                "online": False,
                "response_time_ms": 0,
                "message": f"检查失败: {str(e)}",
                "call_count": 0,
                "success_rate": 0.0,
                "error_rate": 100.0,
                "memory_mb": 0.0,
                "thread_count": 0,
            }

    def check_response_time(self, service_name: str, service_manager) -> float:
        """检查服务响应时间.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            float: 响应时间（毫秒）
        """
        try:
            service = service_manager.get_service(service_name)
            if not service:
                return -1.0

            start_time = time.time()

            # 调用一个轻量级方法
            if hasattr(service, "health_check"):
                service.health_check()

            response_time_ms = (time.time() - start_time) * 1000
            return round(response_time_ms, 2)

        except Exception as e:
            self.logger.error("检查响应时间失败 %s: %s", service_name, e)
            return -1.0

    def check_external_dependencies(self) -> Dict[str, Any]:
        """检查外部依赖状态.

        Returns:
            Dict: 外部依赖检查结果
        """
        dependencies = {}

        # 1. 检查EventEngine
        try:
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if event_engine:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "online",
                    "online": True,
                    "message": "事件引擎运行正常",
                }
            else:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "offline",
                    "online": False,
                    "message": "事件引擎未初始化",
                }
        except Exception as e:
            dependencies["event_engine"] = {
                "name": "VnPy EventEngine",
                "status": "error",
                "online": False,
                "message": f"检查失败: {str(e)}",
            }

        # 2. 检查数据库连接
        try:
            import sqlite3

            from backend.infrastructure.data_module_vnpy.config import config_manager

            db_file = config_manager.get_db_file()
            if db_file.exists():
                # 尝试连接数据库
                conn = sqlite3.connect(str(db_file), timeout=1)
                conn.close()
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "online",
                    "online": True,
                    "message": "数据库连接正常",
                }
            else:
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "offline",
                    "online": False,
                    "message": "数据库文件不存在",
                }
        except Exception as e:
            dependencies["database"] = {
                "name": "SQLite数据库",
                "status": "error",
                "online": False,
                "message": f"连接失败: {str(e)}",
            }

        return dependencies

    def check_all_services(self, service_manager) -> Dict[str, Any]:
        """检查所有注册的服务（增强版 - 包含外部依赖）.

        Args:
            service_manager: 服务管理器实例

        Returns:
            Dict: 所有服务的检查结果，包含外部依赖状态
        """
        try:
            service_status = service_manager.get_service_status()
            results = []

            online_count = 0
            total_response_time = 0

            for service_name, _status in service_status.items():
                check_result = self.quick_check(service_name, service_manager)
                results.append(check_result)

                if check_result["online"]:
                    online_count += 1
                    total_response_time += check_result["response_time_ms"]

            total_count = len(results)
            health_score = (online_count / total_count * 100) if total_count > 0 else 0
            avg_response_time = (total_response_time / online_count) if online_count > 0 else 0

            # 检查外部依赖
            external_dependencies = self.check_external_dependencies()

            # 计算外部依赖健康度
            dep_online = sum(
                1 for dep in external_dependencies.values() if dep.get("online") is True
            )
            dep_total = len(external_dependencies)
            dep_health_score = (dep_online / dep_total * 100) if dep_total > 0 else 0

            # 综合健康评分（服务权重70%，依赖权重30%）
            overall_health_score = health_score * 0.7 + dep_health_score * 0.3

            return {
                "success": True,
                "total_services": total_count,
                "online_services": online_count,
                "health_score": round(overall_health_score, 1),
                "service_health_score": round(health_score, 1),
                "dependency_health_score": round(dep_health_score, 1),
                "avg_response_time_ms": round(avg_response_time, 2),
                "services": results,
                "external_dependencies": external_dependencies,
            }

        except Exception as e:
            self.logger.error("检查所有服务失败: %s", e)
            return {
                "success": False,
                "message": f"检查失败: {str(e)}",
                "services": [],
                "external_dependencies": {},
            }


class ServiceRestarter:
    """服务重启管理器."""

    def __init__(self):
        """初始化服务重启管理器."""
        self.logger = logging.getLogger(__name__)

    def restart_service(self, service_name: str, service_manager) -> Dict[str, Any]:
        """重启指定服务.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始重启服务: %s", service_name)

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 关闭服务
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("服务 %s 已关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)

            # 等待一小段时间
            time.sleep(0.5)

            # 重新初始化服务
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    if success:
                        self.logger.info("服务 %s 已重新初始化", service_name)
                        return {
                            "success": True,
                            "message": f"服务 {service_name} 重启成功",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                        }
                except Exception as e:
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            self.logger.error("重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
            }

    def graceful_restart(
        self, service_name: str, service_manager, timeout: int = 30
    ) -> Dict[str, Any]:
        """优雅地重启服务（带超时控制）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例
            timeout: 超时时间（秒）

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始优雅重启服务: %s (timeout=%ds)", service_name, timeout)

            start_time = time.time()

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 优雅关闭
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("服务 %s 已优雅关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)
                    # 继续执行，尝试重新初始化

            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "message": f"关闭服务超时 ({elapsed:.1f}s)",
                }

            # 等待资源释放
            time.sleep(1)

            # 重新初始化
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()

                    elapsed = time.time() - start_time

                    if success:
                        self.logger.info(
                            "服务 %s 优雅重启成功 (耗时: %.1fs)",
                            service_name,
                            elapsed,
                        )
                        return {
                            "success": True,
                            "message": f"服务 {service_name} 优雅重启成功",
                            "elapsed_time": round(elapsed, 1),
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                            "elapsed_time": round(elapsed, 1),
                        }

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                        "elapsed_time": round(elapsed, 1),
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error("优雅重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
                "elapsed_time": round(elapsed, 1),
            }


# =============================================================================
# 进程管理
# =============================================================================


class ProcessManager:
    """进程管理器 - 提供进程生命周期管理功能."""

    def __init__(self):
        """初始化进程管理器."""
        self.logger = logging.getLogger(__name__)

    def get_process_info(self, pid: int) -> Dict[str, Any]:
        """获取进程信息.

        Args:
            pid: 进程ID

        Returns:
            Dict: 进程信息
        """
        try:
            import psutil

            process = psutil.Process(pid)
            return {
                "pid": pid,
                "name": process.name(),
                "status": process.status(),
                "cpu_percent": process.cpu_percent(),
                "memory_percent": process.memory_percent(),
                "create_time": process.create_time(),
            }
        except Exception as e:
            self.logger.error("获取进程信息失败 (pid=%d): %s", pid, e)
            return {"pid": pid, "status": "unknown", "error": str(e)}

    def manage_process_lifecycle(self, action: str, params: Dict[str, Any]) -> bool:
        """管理进程生命周期.

        Args:
            action: 操作类型 (start, stop, restart, status)
            params: 进程配置参数

        Returns:
            bool: 操作是否成功

        Note:
            这是一个框架方法，需要根据具体需求实现实际的进程管理逻辑
        """
        self.logger.info("进程生命周期管理操作: %s, 参数: %s", action, params)
        raise NotImplementedError("进程生命周期管理需要实现实际的进程控制逻辑")


# =============================================================================
# 安全管理
# =============================================================================


class SecurityManager:
    """安全管理器 - 负责系统的整体安全管理,包括权限验证,安全策略执行等."""

    def __init__(self):
        """初始化安全管理器"""
        self.is_initialized = False
        self.security_policies = {}
        self.encryption_manager = EncryptionManager()
        self.audit_logger = AuditLogger()
        self.permission_controller = PermissionController()

    def initialize(self):
        """初始化安全系统"""
        try:
            # 初始化加密管理器
            self.encryption_manager.initialize()

            # 设置默认安全策略
            self.security_policies = {
                "password_min_length": 8,
                "session_timeout": 3600,  # 1小时
                "max_login_attempts": 5,
                "encryption_algorithm": "AES-256",
                "audit_log_retention_days": 90,
            }

            # 初始化审计日志
            self.audit_logger.initialize()

            # 初始化权限控制器
            self.permission_controller.initialize()

            self.is_initialized = True
            logger.info("SecurityManager initialized successfully")
            self.audit_logger.log_system_event(
                "security_init", "Security system initialized", "success"
            )

        except Exception as e:
            logger.error("Failed to initialize SecurityManager: %s", e)
            self.audit_logger.log_system_event(
                "security_init", f"Security system initialization failed: {e}", "error"
            )
            raise

    def validate_permissions(self, user_id: str, resource: str) -> bool:
        """验证用户权限

        Args:
            user_id: 用户ID
            resource: 资源标识

        Returns:
            bool: 是否有权限访问
        """
        if not self.is_initialized:
            logger.warning("SecurityManager not initialized")
            return False

        try:
            # 检查用户是否存在
            if not self.permission_controller.user_exists(user_id):
                logger.warning("User %s does not exist", user_id)
                self.audit_logger.log_user_action(
                    user_id, "access_denied", resource, "user_not_found"
                )
                return False

            # 验证权限
            has_permission = self.permission_controller.has_permission(user_id, resource)

            # 记录访问尝试
            result = "granted" if has_permission else "denied"
            self.audit_logger.log_user_action(user_id, "access_attempt", resource, result)

            return has_permission

        except (ValueError, RuntimeError, KeyError) as e:
            logger.error(
                "Permission validation error for user %s, resource %s: %s",
                user_id,
                resource,
                e,
            )
            self.audit_logger.log_user_action(user_id, "access_error", resource, f"error: {e}")
            return False


class PermissionController:
    """权限控制器 - 负责用户权限的分配,验证和管理."""

    def __init__(self):
        """初始化权限控制器"""
        self.permissions = {}
        self.user_roles = {}
        self.role_permissions = {}
        self.is_initialized = False

    def initialize(self):
        """初始化权限控制器"""
        # 设置默认角色和权限
        self.role_permissions = {
            "admin": {"read", "write", "delete", "manage_users", "system_config"},
            "trader": {"read", "write", "trading"},
            "viewer": {"read"},
            "analyst": {"read", "analysis"},
        }

        # 创建默认管理员用户
        self.user_roles["admin"] = "admin"
        self.permissions["admin"] = self.role_permissions["admin"].copy()

        self.is_initialized = True
        logger.info("PermissionController initialized")

    def user_exists(self, user_id: str) -> bool:
        """检查用户是否存在"""
        return user_id in self.user_roles

    def has_permission(self, user_id: str, resource: str) -> bool:
        """检查用户是否有特定权限"""
        if user_id not in self.permissions:
            return False

        # 检查直接权限
        if resource in self.permissions[user_id]:
            return True

        # 检查角色权限
        if user_id in self.user_roles:
            role = self.user_roles[user_id]
            if role in self.role_permissions:
                return resource in self.role_permissions[role]

        return False

    def grant_permission(self, user_id: str, permission: str):
        """授予用户权限

        Args:
            user_id: 用户ID
            permission: 权限标识
        """
        if not self.is_initialized:
            logger.warning("PermissionController not initialized")
            return

        if user_id not in self.permissions:
            self.permissions[user_id] = set()

        self.permissions[user_id].add(permission)
        logger.info("Granted permission %s to user %s", permission, user_id)

    def revoke_permission(self, user_id: str, permission: str):
        """撤销用户权限

        Args:
            user_id: 用户ID
            permission: 权限标识
        """
        if not self.is_initialized:
            logger.warning("PermissionController not initialized")
            return

        if user_id in self.permissions:
            self.permissions[user_id].discard(permission)
            logger.info("Revoked permission %s from user %s", permission, user_id)

    def assign_role(self, user_id: str, role: str):
        """为用户分配角色

        Args:
            user_id: 用户ID
            role: 角色名称
        """
        if role not in self.role_permissions:
            logger.error("Unknown role: %s", role)
            return

        self.user_roles[user_id] = role
        self.permissions[user_id] = self.role_permissions[role].copy()
        logger.info("Assigned role %s to user %s", role, user_id)


class EncryptionManager:
    """加密管理器 - 负责数据的加密,解密和密钥管理."""

    def __init__(self):
        """初始化加密管理器"""
        self.encryption_key = None
        self.fernet = None
        self.is_initialized = False

    def initialize(self):
        """初始化加密管理器"""
        try:
            # 生成或加载密钥
            self.generate_key()
            self.is_initialized = True
            logger.info("EncryptionManager initialized")
        except Exception as e:
            logger.error("Failed to initialize EncryptionManager: %s", e)
            raise

    def generate_key(self) -> str:
        """生成加密密钥

        Returns:
            str: 生成的密钥
        """
        # 使用PBKDF2生成密钥
        password = secrets.token_bytes(32)
        salt = secrets.token_bytes(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = base64.urlsafe_b64encode(kdf.derive(password))
        self.encryption_key = key
        self.fernet = Fernet(key)

        logger.info("Generated new encryption key")
        return key.decode()

    def encrypt_data(self, data: str) -> str:
        """加密数据

        Args:
            data: 要加密的数据

        Returns:
            str: 加密后的数据
        """
        if not self.is_initialized or not self.fernet:
            logger.error("EncryptionManager not properly initialized")
            raise RuntimeError("EncryptionManager not initialized")

        try:
            # 将字符串转换为字节
            data_bytes = data.encode("utf-8")

            # 使用Fernet加密
            encrypted_bytes = self.fernet.encrypt(data_bytes)

            # 转换为base64字符串
            encrypted_data = base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")

            logger.info("Data encrypted successfully")
            return encrypted_data

        except Exception as e:
            logger.error("Data encryption failed: %s", e)
            raise

    def decrypt_data(self, encrypted_data: str) -> str:
        """解密数据

        Args:
            encrypted_data: 加密的数据

        Returns:
            str: 解密后的数据
        """
        if not self.is_initialized or not self.fernet:
            logger.error("EncryptionManager not properly initialized")
            raise RuntimeError("EncryptionManager not initialized")

        try:
            # 将base64字符串转换为字节
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode("utf-8"))

            # 使用Fernet解密
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)

            # 转换为字符串
            decrypted_data = decrypted_bytes.decode("utf-8")

            logger.info("Data decrypted successfully")
            return decrypted_data

        except Exception as e:
            logger.error("Data decryption failed: %s", e)
            raise


class AuditLogger:
    """审计日志器 - 负责记录系统的安全审计日志,包括用户操作,权限变更等."""

    def __init__(self):
        """初始化审计日志器"""
        self.audit_logs = []
        self.is_initialized = False

    def initialize(self):
        """初始化审计日志器"""
        self.is_initialized = True
        logger.info("AuditLogger initialized")

    def log_user_action(self, user_id: str, action: str, resource: str, result: str):
        """记录用户操作日志

        Args:
            user_id: 用户ID
            action: 操作类型
            resource: 操作的资源
            result: 操作结果
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "result": result,
        }
        self.audit_logs.append(log_entry)
        logger.info("Audit log: %s performed %s on %s - %s", user_id, action, resource, result)

    def log_permission_change(
        self, admin_user: str, target_user: str, permission: str, action: str
    ):
        """记录权限变更日志

        Args:
            admin_user: 执行权限变更的管理员
            target_user: 目标用户
            permission: 权限标识
            action: 操作类型(grant/revoke)
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "admin_user": admin_user,
            "target_user": target_user,
            "permission": permission,
            "action": action,
        }
        self.audit_logs.append(log_entry)
        logger.info(
            "Permission audit: %s %sed %s for %s",
            admin_user,
            action,
            permission,
            target_user,
        )

    def log_system_event(self, event_type: str, description: str, result: str):
        """记录系统事件日志

        Args:
            event_type: 事件类型
            description: 事件描述
            result: 事件结果
        """
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": event_type,
            "description": description,
            "result": result,
            "source": "system",
        }
        self.audit_logs.append(log_entry)
        logger.info("System event: %s - %s (%s)", event_type, description, result)

    def get_audit_logs(self, user_id: str | None = None) -> list:
        """获取审计日志

        Args:
            user_id: 可选,指定用户ID过滤日志

        Returns:
            list: 审计日志列表
        """
        if user_id:
            return [
                log
                for log in self.audit_logs
                if (log.get("user_id") == user_id or log.get("target_user") == user_id)
            ]
        return self.audit_logs.copy()


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 服务管理
    "ServiceHealthChecker",
    "ServiceRestarter",
    # 进程管理
    "ProcessManager",
    # 安全管理
    "SecurityManager",
    "PermissionController",
    "EncryptionManager",
    "AuditLogger",
]

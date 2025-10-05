# -*- coding: utf-8 -*-
"""
安全管理模块

提供权限控制,加密解密,审计日志等安全功能.
"""

import base64
import datetime
import logging
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecurityManager:
    """安全管理器

    负责系统的整体安全管理,包括权限验证,安全策略执行等.
    """

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
                'password_min_length': 8,
                'session_timeout': 3600,  # 1小时
                'max_login_attempts': 5,
                'encryption_algorithm': 'AES-256',
                'audit_log_retention_days': 90
            }

            # 初始化审计日志
            self.audit_logger.initialize()

            # 初始化权限控制器
            self.permission_controller.initialize()

            self.is_initialized = True
            logger.info("SecurityManager initialized successfully")
            self.audit_logger.log_system_event(
                'security_init', 'Security system initialized', 'success')

        except Exception as e:
            logger.error("Failed to initialize SecurityManager: %s", e)
            self.audit_logger.log_system_event(
                'security_init', f'Security system initialization failed: {e}', 'error')
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
                    user_id, 'access_denied', resource, 'user_not_found')
                return False

            # 验证权限
            has_permission = self.permission_controller.has_permission(
                user_id, resource)

            # 记录访问尝试
            result = 'granted' if has_permission else 'denied'
            self.audit_logger.log_user_action(
                user_id, 'access_attempt', resource, result)

            return has_permission

        except (ValueError, RuntimeError, KeyError) as e:
            logger.error(
                "Permission validation error for user %s, resource %s: %s",
                user_id, resource, e)
            self.audit_logger.log_user_action(
                user_id, 'access_error', resource, f'error: {e}')
            return False


class PermissionController:
    """权限控制器

    负责用户权限的分配,验证和管理.
    """

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
            'admin': {'read', 'write', 'delete', 'manage_users', 'system_config'},
            'trader': {'read', 'write', 'trading'},
            'viewer': {'read'},
            'analyst': {'read', 'analysis'}
        }

        # 创建默认管理员用户
        self.user_roles['admin'] = 'admin'
        self.permissions['admin'] = self.role_permissions['admin'].copy()

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
    """加密管理器

    负责数据的加密,解密和密钥管理.
    """

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
            data_bytes = data.encode('utf-8')

            # 使用Fernet加密
            encrypted_bytes = self.fernet.encrypt(data_bytes)

            # 转换为base64字符串
            encrypted_data = base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8')

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
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))

            # 使用Fernet解密
            decrypted_bytes = self.fernet.decrypt(encrypted_bytes)

            # 转换为字符串
            decrypted_data = decrypted_bytes.decode('utf-8')

            logger.info("Data decrypted successfully")
            return decrypted_data

        except Exception as e:
            logger.error("Data decryption failed: %s", e)
            raise


class AuditLogger:
    """审计日志器

    负责记录系统的安全审计日志,包括用户操作,权限变更等.
    """

    def __init__(self):
        """初始化审计日志器"""
        self.audit_logs = []
        self.is_initialized = False

    def log_user_action(self, user_id: str, action: str, resource: str, result: str):
        """记录用户操作日志

        Args:
            user_id: 用户ID
            action: 操作类型
            resource: 操作的资源
            result: 操作结果
        """
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'user_id': user_id,
            'action': action,
            'resource': resource,
            'result': result
        }
        self.audit_logs.append(log_entry)
        logger.info(
            "Audit log: %s performed %s on %s - %s", user_id, action, resource, result)

    def log_permission_change(
            self, admin_user: str, target_user: str, permission: str, action: str):
        """记录权限变更日志

        Args:
            admin_user: 执行权限变更的管理员
            target_user: 目标用户
            permission: 权限标识
            action: 操作类型(grant/revoke)
        """
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'admin_user': admin_user,
            'target_user': target_user,
            'permission': permission,
            'action': action
        }
        self.audit_logs.append(log_entry)
        logger.info(
            "Permission audit: %s %sed %s for %s",
            admin_user, action, permission, target_user)

    def get_audit_logs(self, user_id: str = None) -> list:
        """获取审计日志

        Args:
            user_id: 可选,指定用户ID过滤日志

        Returns:
            list: 审计日志列表
        """
        if user_id:
            return [log for log in self.audit_logs
                    if (log.get('user_id') == user_id or
                        log.get('target_user') == user_id)]
        return self.audit_logs.copy()

    def initialize(self):
        """初始化审计日志器"""
        self.is_initialized = True
        logger.info("AuditLogger initialized")

    def log_system_event(self, event_type: str, description: str, result: str):
        """记录系统事件日志

        Args:
            event_type: 事件类型
            description: 事件描述
            result: 事件结果
        """
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'event_type': event_type,
            'description': description,
            'result': result,
            'source': 'system'
        }
        self.audit_logs.append(log_entry)
        logger.info(
            "System event: %s - %s (%s)",
            event_type, description, result)


__all__ = [
    "SecurityManager",
    "PermissionController",
    "EncryptionManager",
    "AuditLogger",
]
